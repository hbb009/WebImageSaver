# ==================== 标准库 ====================
import os
import re
import shutil
import base64
import hashlib
import threading
import time

# ==================== 第三方：PyQt5 ====================
from PyQt5.QtCore import (
    Qt, QStandardPaths, QTimer, pyqtSignal,
    QAbstractNativeEventFilter, QCoreApplication,
)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget,
    QCheckBox, QFileDialog, QGroupBox, QShortcut,
    QComboBox, QTabWidget, QStackedWidget,
    QRadioButton, QButtonGroup,
)

# ==================== 本地模块 ====================
from styles.common_styles import TEXT_STYLE, BUTTON_STYLE, LINEEDIT_STYLE

# ==================== Windows API ====================
import ctypes
import ctypes.wintypes as wintypes
import socket

try:
    LRESULT = wintypes.LRESULT
except AttributeError:
    LRESULT = ctypes.c_long if ctypes.sizeof(ctypes.c_void_p) == 4 else ctypes.c_longlong
try:
    INT = wintypes.INT
except AttributeError:
    INT = ctypes.c_int
try:
    WPARAM = wintypes.WPARAM
    LPARAM = wintypes.LPARAM
except AttributeError:
    WPARAM = ctypes.c_size_t
    LPARAM = ctypes.c_ssize_t
try:
    ULONG_PTR = wintypes.ULONG_PTR
except AttributeError:
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

if ctypes.sizeof(WPARAM) != ctypes.sizeof(ctypes.c_void_p):
    WPARAM = ctypes.c_size_t
if ctypes.sizeof(LPARAM) != ctypes.sizeof(ctypes.c_void_p):
    LPARAM = ctypes.c_ssize_t

WM_HOTKEY = 0x0312
VK_CODE   = {"F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79}

# 手动速存依赖（只需 win32clipboard + pyperclip）
try:
    import win32clipboard as _win32clipboard
    import win32gui as _win32gui
    import pyperclip
    _WIN_OK = True
except Exception:
    _WIN_OK = False

_SHARED_QUEUE = []

# ── WebSocket Server（供插件连接） ─────────────────────────────
_WS_PORT        = 19876
_ws_clients     = set()          # 当前 socket 连接集合
_ws_lock        = threading.Lock()
_ws_last_ping   = 0.0            # 最后一次收到插件 PING 的时间戳
_WS_PING_TTL    = 35.0           # 插件每 20s 发一次 PING，35s 内没收到视为断连
_ws_send_lock   = threading.Lock()   # 多线程往同一 socket 写时加锁，避免帧交错
_ws_enabled     = False          # 桌面程序侧“启用速存图片”的状态，会推送给插件

def _ws_handshake(conn):
    data = conn.recv(4096).decode("utf-8", errors="ignore")
    key  = next((l.split(":",1)[1].strip() for l in data.split("\r\n")
                 if l.lower().startswith("sec-websocket-key:")), None)
    if not key: return False
    accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
    ).decode()
    conn.sendall((
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
    ).encode())
    return True

def _ws_send(conn, text):
    p = text.encode()
    n = len(p)
    h = bytes([0x81, n]) if n < 126 else bytes([0x81, 126, n>>8, n&0xFF])
    conn.sendall(h + p)

def _ws_recv(conn):
    try:
        h = conn.recv(2)
        if len(h) < 2: return None
        masked = h[1] & 0x80
        n = h[1] & 0x7F
        if n == 126: n = int.from_bytes(conn.recv(2), "big")
        mask = conn.recv(4) if masked else b"\x00\x00\x00\x00"
        data = bytearray(conn.recv(n))
        if masked:
            for i in range(len(data)): data[i] ^= mask[i%4]
        return data.decode("utf-8", errors="ignore") if (h[0]&0x0F) in (1,2) else ""
    except: return None

def _ws_client(conn):
    global _ws_last_ping
    try:
        if not _ws_handshake(conn): return
        with _ws_lock:
            _ws_clients.add(conn)
            _ws_last_ping = time.time()   # 握手成功即视为一次心跳
        # 连上即告知当前启用状态
        with _ws_send_lock:
            try: _ws_send(conn, "ENABLE" if _ws_enabled else "DISABLE")
            except: pass
        while True:
            msg = _ws_recv(conn)
            if msg is None: break
            if msg == "PING":
                with _ws_lock:
                    _ws_last_ping = time.time()
    except: pass
    finally:
        with _ws_lock: _ws_clients.discard(conn)
        try: conn.close()
        except: pass

def _ws_server():
    global _ws_server_ok
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", _WS_PORT))
        srv.listen(10)
        srv.settimeout(1.0)
        _ws_server_ok = True
        while True:
            try:
                conn, _ = srv.accept()
                threading.Thread(target=_ws_client, args=(conn,), daemon=True).start()
            except socket.timeout: continue
            except: break
    except Exception:
        _ws_server_ok = False

def _ws_broadcast(text):
    """把一条消息发给所有已连接的插件（线程安全）。"""
    with _ws_lock: clients = list(_ws_clients)
    for c in clients:
        with _ws_send_lock:
            try: _ws_send(c, text)
            except:
                with _ws_lock: _ws_clients.discard(c)

def _ws_set_enabled(enabled: bool):
    """更新启用状态并立即推送给插件。"""
    global _ws_enabled
    _ws_enabled = bool(enabled)
    _ws_broadcast("ENABLE" if _ws_enabled else "DISABLE")

def _ws_connected():
    """判断插件是否活跃：35 秒内收到过 PING 且 socket 还在"""
    with _ws_lock:
        has_socket = len(_ws_clients) > 0
        ping_fresh = (time.time() - _ws_last_ping) < _WS_PING_TTL
    return has_socket or ping_fresh   # socket 在 OR 最近有过心跳都算连接

def _ws_seconds_since_ping() -> float:
    with _ws_lock: return time.time() - _ws_last_ping

# 服务器启动状态：None=启动中, True=正常, False=端口被占用
_ws_server_ok = None
threading.Thread(target=_ws_server, daemon=True).start()

def _ws_state_pusher():
    """每 10 秒重发一次当前启用状态。插件据此判断“程序是否在线”，
    程序一旦关闭就不再发送，插件在新鲜度窗口过期后自动停止保存。"""
    while True:
        time.sleep(10)
        try: _ws_broadcast("ENABLE" if _ws_enabled else "DISABLE")
        except: pass
threading.Thread(target=_ws_state_pusher, daemon=True).start()






# ─────────────────────────────────────────────
# 全局热键过滤器（速存文本用）
# ─────────────────────────────────────────────
class _GlobalHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, cb, hid):
        super().__init__()
        self.cb  = cb
        self.hid = hid

    def nativeEventFilter(self, eventType, message):
        if eventType != "windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and msg.wParam == self.hid:
            self.cb()
            return True, 0
        return False, 0


def _check_chrome_running() -> bool:
    """检测系统中是否有 Chrome 进程在运行"""
    try:
        import subprocess
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            stderr=subprocess.DEVNULL, creationflags=0x08000000  # CREATE_NO_WINDOW
        ).decode("gbk", errors="ignore")
        return "chrome.exe" in out.lower()
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# PageFastSave
# ═══════════════════════════════════════════════════════════════
class PageFastSave(QWidget):
    STATE_IDLE    = 0
    STATE_IMGSAVE = 1

    log_sig     = pyqtSignal(str)
    # 插件状态更新信号（color, text, bold）——供后台检测线程安全地切回主线程更新 UI
    plugin_status_sig = pyqtSignal(str, str, bool)

    @staticmethod
    def _typo(w, name):
        w.setProperty("typo", name)
        w.style().unpolish(w)
        w.style().polish(w)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setSpacing(3)
        lay.setContentsMargins(6, 4, 6, 4)

        # ══════════ 顶部两卡片 ══════════
        row_top = QHBoxLayout()
        row_top.setSpacing(6)
        lay.addLayout(row_top)

        # ── 最左：速存启用（总开关，与左侧菜单 LED 联动） ──
        gb_enable = QGroupBox("速存启用")
        gb_enable.setProperty("titleVariant", "accent")
        gb_enable.setObjectName("CardFastEnable")
        enable_box = QVBoxLayout(gb_enable)
        enable_box.setSpacing(3)
        enable_box.setContentsMargins(8, 4, 8, 4)

        self.chk_enable_all = QCheckBox("启用速存")
        enable_box.addWidget(self.chk_enable_all)
        enable_box.addStretch(1)

        # ── 速存图片 ──
        gb_img  = QGroupBox("速存图片")
        gb_img.setProperty("titleVariant", "accent")
        gb_img.setObjectName("CardFastAuto")
        img_box = QVBoxLayout(gb_img)
        img_box.setSpacing(3)
        img_box.setContentsMargins(8, 4, 8, 4)

        self.chk_imgonly = QCheckBox("启用速存图片")
        self.chk_imgonly.setVisible(False)  # 子开关不展示，由速存启用总开关控制

        # 插件状态（状态灯 + 提示文字）—— 仅状态灯，无刷新按钮
        row_plugin = QHBoxLayout()
        row_plugin.setSpacing(4)
        row_plugin.setContentsMargins(0, 0, 0, 0)

        self.lbl_plugin_dot = QLabel("●")
        self.lbl_plugin_dot.setFixedWidth(16)
        self.lbl_plugin_dot.setStyleSheet("color: #f0a500; font-size: 14px;")  # 初始黄灯：检测中

        self.lbl_nm_status = QLabel("检测中...")
        self.lbl_nm_status.setWordWrap(True)
        self._typo(self.lbl_nm_status, "muted")

        row_plugin.addWidget(self.lbl_plugin_dot)
        row_plugin.addWidget(self.lbl_nm_status, 1)
        img_box.addLayout(row_plugin)

        # 快捷键（单行）
        row_kb = QHBoxLayout()
        row_kb.setSpacing(4)
        self.btn_plugin_help = QPushButton("?")
        self.btn_plugin_help.setFixedSize(22, 22)
        self.btn_plugin_help.setToolTip("如何安装速存图片插件 MV3")
        self.btn_plugin_help.setStyleSheet(
            "QPushButton { padding: 0; font-size: 13px; font-weight: bold; }"
        )
        row_kb.addWidget(self.btn_plugin_help)
        row_kb.addWidget(QLabel("快捷键"))
        self.combo_img_hotkey = QComboBox()
        self.combo_img_hotkey.setObjectName("FastSaveHotkey")
        self.combo_img_hotkey.addItems(["Alt+1"])
        self.combo_img_hotkey.setCurrentText("Alt+1")
        self.combo_img_hotkey.setEnabled(False)   # 固定 Alt+1，不提供改键
        self.combo_img_hotkey.setFixedWidth(100)
        row_kb.addWidget(self.combo_img_hotkey)
        row_kb.addStretch(1)
        img_box.addLayout(row_kb)

        lbl_img_hint = QLabel("（在浏览器里把鼠标停在图片上，按 Alt+1 保存原图）")
        lbl_img_hint.setWordWrap(True)
        self._typo(lbl_img_hint, "muted")
        img_box.addWidget(lbl_img_hint)

        # ── 速存文本 ──
        gb_txt  = QGroupBox("速存文本")
        gb_txt.setProperty("titleVariant", "accent")
        gb_txt.setObjectName("CardFastManual")
        txt_box = QVBoxLayout(gb_txt)
        txt_box.setSpacing(3)
        txt_box.setContentsMargins(8, 4, 8, 4)

        self.chk_manual = QCheckBox("启用速存文本")
        self.chk_manual.setVisible(False)  # 子开关不展示，由速存启用总开关控制

        txt_box.addWidget(QLabel("文本快捷键"))
        self._txt_hotkey_group = QButtonGroup(self)
        row_radios = QHBoxLayout()
        row_radios.setSpacing(4)
        self._txt_radio = {}
        for key in ["F3", "F4"]:
            rb = QRadioButton(key)
            self._txt_radio[key] = rb
            self._txt_hotkey_group.addButton(rb)
            row_radios.addWidget(rb)
        self._txt_radio["F4"].setChecked(True)
        row_radios.addStretch(1)
        txt_box.addLayout(row_radios)

        lbl_hint = QLabel("（全局热键，在资源管理器操作即可生效）")
        lbl_hint.setWordWrap(True)
        self._typo(lbl_hint, "muted")
        txt_box.addWidget(lbl_hint)

        # ── 速建文件夹 ──
        gb_mkdir = QGroupBox("速建文件夹")
        gb_mkdir.setProperty("titleVariant", "accent")
        gb_mkdir.setObjectName("CardFastMkdir")
        mkdir_box = QVBoxLayout(gb_mkdir)
        mkdir_box.setSpacing(3)
        mkdir_box.setContentsMargins(8, 4, 8, 4)

        self.chk_mkdir = QCheckBox("启用速建文件夹")
        self.chk_mkdir.setVisible(False)  # 子开关不展示，由速存启用总开关控制

        mkdir_box.addWidget(QLabel("文件夹快捷键"))
        row_mkdir_key = QHBoxLayout()
        row_mkdir_key.setSpacing(4)
        row_mkdir_key.addWidget(QLabel("顺序新建"))
        self._mkdir_hotkey_group = QButtonGroup(self)
        self._mkdir_radio = {}
        for key in ["F5", "F6", "F7", "F8"]:
            rb = QRadioButton(key)
            self._mkdir_radio[key] = rb
            self._mkdir_hotkey_group.addButton(rb)
            row_mkdir_key.addWidget(rb)
        self._mkdir_radio["F8"].setChecked(True)
        row_mkdir_key.addStretch(1)
        mkdir_box.addLayout(row_mkdir_key)

        row_mkdir_direct = QHBoxLayout()
        row_mkdir_direct.setSpacing(4)
        row_mkdir_direct.addWidget(QLabel("F9 直接新建"))
        self.mkdir_name = QLineEdit("Grok")
        self.mkdir_name.setPlaceholderText("默认 Grok")
        self.mkdir_name.setFixedWidth(120)
        row_mkdir_direct.addWidget(self.mkdir_name)
        row_mkdir_direct.addStretch(1)
        mkdir_box.addLayout(row_mkdir_direct)

        lbl_mkdir_hint = QLabel("（选中文件夹后按所选键顺序新建；未选中任何项时按 F9 直接新建上方名称的文件夹）")
        lbl_mkdir_hint.setWordWrap(True)
        self._typo(lbl_mkdir_hint, "muted")
        mkdir_box.addWidget(lbl_mkdir_hint)

        row_top.addWidget(gb_enable)
        row_top.addWidget(gb_img)
        row_top.addWidget(gb_txt)
        row_top.addWidget(gb_mkdir)
        row_top.setStretch(0, 0)   # 速存启用：固定宽度不拉伸
        row_top.setStretch(1, 1)
        row_top.setStretch(2, 1)
        row_top.setStretch(3, 1)

        # ══════════ 路径 ══════════
        row_p = QHBoxLayout()
        row_p.setSpacing(4)
        self.label_path = QLabel("保存路径：")
        self.save_path      = QLineEdit("")
        self.btn_choose_dir = QPushButton("另选目录")
        self.btn_choose_dir.setFixedWidth(96)
        row_p.addWidget(self.label_path)
        row_p.addWidget(self.save_path)
        row_p.addWidget(self.btn_choose_dir)
        lay.addLayout(row_p)

        # ══════════ 日志区：上「运行记录」/ 下「问题记录」 ══════════
        lay.addWidget(QLabel("运行记录"))
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("FastSaveList")
        self.list_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setUniformItemSizes(True)
        lay.addWidget(self.list_widget, 3)          # 运行记录占大头

        prob_head = QHBoxLayout()
        prob_head.addWidget(QLabel("问题记录（诊断 / 连接 / 错误）"))
        self.btn_clear_problems = QPushButton("清空")
        self.btn_clear_problems.setFixedWidth(56)
        prob_head.addStretch(1)
        prob_head.addWidget(self.btn_clear_problems)
        lay.addLayout(prob_head)
        self.problem_widget = QListWidget()
        self.problem_widget.setObjectName("FastSaveList")
        self.problem_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.problem_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.problem_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.problem_widget.setStyleSheet("font-size: 11px;")   # 问题记录字体小一些
        lay.addWidget(self.problem_widget, 1)       # 问题记录占小头

        # ══════════ 信号与槽 ══════════
        self.log_sig.connect(self._append_log)
        self.plugin_status_sig.connect(self._apply_plugin_ui)
        self.btn_choose_dir.clicked.connect(self._choose_dir)
        self.btn_plugin_help.clicked.connect(self._show_plugin_help)
        self.btn_clear_problems.clicked.connect(self.problem_widget.clear)
        self.chk_imgonly.toggled.connect(self._on_imgonly_toggled)
        self.chk_manual.toggled.connect(self._on_manual_toggled)
        self.combo_img_hotkey.currentTextChanged.connect(self._on_img_hotkey_changed)
        self._txt_hotkey_group.buttonClicked.connect(self._on_txt_hotkey_changed)
        self._mkdir_hotkey_group.buttonClicked.connect(self._on_mkdir_hotkey_changed)
        self.save_path.textChanged.connect(self._on_path_edited)
        # 速存启用总开关
        self.chk_enable_all.toggled.connect(self._on_enable_all_toggled)
        # 子功能变化时同步总开关显示
        self.chk_imgonly.toggled.connect(self._sync_enable_all_display)
        self.chk_manual.toggled.connect(self._sync_enable_all_display)
        self.chk_mkdir.toggled.connect(self._sync_enable_all_display)

        # ══════════ 状态 ══════════
        # 目录监控：把浏览器暂存目录里的新图片移动到保存路径
        self._archived_seen = set()   # 当“保存路径==暂存区”时，用于记录已见过的文件
        self._imgonly_timer = QTimer(self)
        self._imgonly_timer.setInterval(1000)
        self._imgonly_timer.timeout.connect(self._scan_imgonly_files)

        # 心跳：每 5 秒自动刷新插件连接状态
        self._nm_check_timer = QTimer(self)
        self._nm_check_timer.setInterval(5000)
        self._nm_check_timer.timeout.connect(self._update_nm_status)
        self._nm_check_timer.start()
        QTimer.singleShot(1000, self._update_nm_status)  # 启动 1s 后做第一次检测

        # 速存文本热键
        self._hotkey_id              = 0x1002
        self._hotkey_filter          = None
        self._hotkey_registered_key  = None

        self._sc_manual = QShortcut(QKeySequence(self._current_txt_key()), self)
        self._sc_manual.activated.connect(self.manual_fast_save)
        self._sc_manual.setEnabled(False)

        # 速建文件夹热键（F9）
        self._mkdir_hotkey_id     = 0x1003
        self._mkdir_hotkey_filter = None
        self._mkdir_hotkey_registered = False
        # 直接新建热键（F9）
        self._mkdir_direct_id     = 0x1004
        self._mkdir_direct_filter = None
        self.chk_mkdir.toggled.connect(self._on_mkdir_toggled)

        self.clipboard = QApplication.clipboard()
        self.state     = self.STATE_IDLE

        self._init_save_dir()
        self._enter_idle(reset_switches=True)

    # ────────────────────────────────────────
    # 对外接口（兼容旧版 server.py）
    # ────────────────────────────────────────
    @staticmethod
    def shared_queue(): return _SHARED_QUEUE
    def allow_accept(self): return False
    def drain_queue(self): pass

    def is_img_active(self):  return self.chk_imgonly.isChecked()
    def is_txt_active(self):  return self.chk_manual.isChecked()
    def is_mkdir_active(self): return self.chk_mkdir.isChecked()
    def is_any_active(self):  return self.is_img_active() or self.is_txt_active() or self.is_mkdir_active()
    def is_all_active(self):  return self.is_img_active() and self.is_txt_active() and self.is_mkdir_active()

    def _on_enable_all_toggled(self, checked: bool):
        """速存启用总开关：与左侧菜单 LED 等价，开/关全部子功能"""
        self.set_all_features(checked)

    def _sync_enable_all_display(self, _=None):
        """子功能变化时同步总开关的勾选显示（不触发信号循环）"""
        self.chk_enable_all.blockSignals(True)
        self.chk_enable_all.setChecked(self.is_any_active())
        self.chk_enable_all.blockSignals(False)

    def set_all_features(self, enabled: bool):
        """一键开/关三个功能（供外部 LED 调用）"""
        self._block_switches(True)
        self.chk_mkdir.blockSignals(True)
        try:
            self.chk_imgonly.setChecked(enabled)
            self.chk_manual.setChecked(enabled)
            self.chk_mkdir.setChecked(enabled)
        finally:
            self._block_switches(False)
            self.chk_mkdir.blockSignals(False)
        # 手动触发各自逻辑
        self._on_imgonly_toggled(enabled)
        self._on_manual_toggled(enabled)
        self._on_mkdir_toggled(enabled)

    # ────────────────────────────────────────
    # 速存图片：触发逻辑
    # ────────────────────────────────────────
    def _update_nm_status(self):
        """后台检测插件连接状态，映射为三色灯：
           绿=能用（插件已连接）；红=不能用（端口被占用 / Chrome 未运行）；
           黄=无法判定（服务启动中 / 等待插件 / 心跳超时 / 刚断开）。"""
        GREEN, RED, YELLOW = "#4caf50", "#e05252", "#f0a500"

        def _do_check():
            # 1. 端口被占用 → 服务起不来，肯定不能用 → 红
            if _ws_server_ok is False:
                self._set_plugin_ui(RED, f"❌ 端口 {_WS_PORT} 被占用，无法监听（不能用）")
                return
            # 2. 服务还在启动 → 暂时无法判定 → 黄
            if _ws_server_ok is None:
                self._set_plugin_ui(YELLOW, "⏳ 服务启动中…（检测中）")
                return

            secs = _ws_seconds_since_ping()
            has_sock = len(_ws_clients) > 0

            # 3. 有连接且心跳新鲜 → 能用 → 绿
            if has_sock and secs < _WS_PING_TTL:
                self._set_plugin_ui(GREEN, f"✓ 插件已连接（{int(secs)}s 前心跳）", bold=True)
                return
            # 4. 有连接但心跳超时 → 可能挂起，无法判定 → 黄
            if has_sock and secs >= _WS_PING_TTL:
                self._set_plugin_ui(YELLOW, f"⚠ 连接存在但 {int(secs)}s 无心跳（插件可能挂起）")
                return
            # 5. 刚断开不久 → 可能马上重连，无法判定 → 黄
            if secs < 120:
                self._set_plugin_ui(YELLOW, f"⚠ 插件已断开（{int(secs)}s 前最后心跳）")
                return

            # 6. 从未连接 / 很久没连 → 看 Chrome 是否在运行
            if _check_chrome_running():
                # Chrome 在跑但插件没连上 → 等待中 → 黄
                self._set_plugin_ui(YELLOW, "● Chrome 运行中，等待插件连接…")
            else:
                # Chrome 没开，插件根本连不上 → 不能用 → 红
                self._set_plugin_ui(RED, "● Chrome 未运行，插件无法连接（不能用）")

        import threading as _th
        _th.Thread(target=_do_check, daemon=True).start()

    def _set_plugin_ui(self, color: str, text: str, bold: bool = False):
        """线程安全：通过信号把结果切回主线程更新（不能在子线程里直接碰 UI/定时器）。"""
        self.plugin_status_sig.emit(color, text, bool(bold))

    def _apply_plugin_ui(self, color: str, text: str, bold: bool):
        """在主线程真正更新状态灯与提示文字（由 plugin_status_sig 触发）。"""
        # 状态发生变化时往「问题记录」追加一条（仅变化时，避免刷屏）
        if getattr(self, "_last_plugin_text", None) != text:
            self._last_plugin_text = text
            self._log_problem(f"🔌 {text}")
        self.lbl_plugin_dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        self.lbl_nm_status.setText(text)
        weight = "bold" if bold else "normal"
        self.lbl_nm_status.setStyleSheet(f"color: {color}; font-weight: {weight};")


    # ────────────────────────────────────────

    # ────────────────────────────────────────
    # 速存图片：开关与设置变更
    # ────────────────────────────────────────
    def _on_imgonly_toggled(self, checked: bool):
        if checked:
            if not self._require_writable_path(interactive=True):
                self._block_switches(True)
                self.chk_imgonly.setChecked(False)
                self._block_switches(False)
                _ws_set_enabled(False)          # 路径不可用 → 通知插件停用
                self._log_problem("⚠️ 保存路径不可用，已取消速存图片")
                return

            self._diagnose()                    # 启用即打印诊断，问题一眼可见
            self._prime_seen_and_quiet()        # 处理暂存区已有的图片
            self._imgonly_timer.start()

            self.state = self.STATE_IMGSAVE
            _ws_set_enabled(True)               # 通知插件：可以开始存图
            self.list_widget.addItem("🟢 速存图片：已启用（在浏览器里把鼠标停在图片上按 Alt+1）")
            self.list_widget.addItem(f"📁 图片将归档到：{self.save_path.text().strip()}")
        else:
            self._imgonly_timer.stop()
            self.state = self.STATE_IDLE
            _ws_set_enabled(False)              # 通知插件：停止存图
            self.list_widget.addItem("⏹️ 速存图片：已关闭")

    def _on_img_hotkey_changed(self, key: str):
        # 快捷键固定为 Alt+1，不再需要与浏览器同步，这里保留空实现以兼容信号连接
        pass

    def _show_plugin_help(self):
        """弹窗说明如何把「图片速存助手」MV3 插件装进 Chrome，并把快捷键设为 Alt+1。"""
        from PyQt5.QtWidgets import QMessageBox
        text = (
            "1. 打开 Chrome，地址栏输入 chrome://extensions/ 后回车\n\n"
            "2. 打开右上角「开发者模式」开关\n\n"
            "3. 点「加载已解压的扩展程序」，选择插件的 MV3 文件夹\n"
            "    （该文件夹内需包含 manifest.json）\n\n"
            "4. 加载成功后会出现「图片速存助手」，确认右下角开关已开启（蓝色）\n\n"
            "5. 打开 chrome://extensions/shortcuts，把\n"
            "    「保存光标下的图片」的快捷键设为 Alt+1\n\n"
            "6. 回到本程序，勾选「启用速存」，状态灯变绿即表示插件已连接"
        )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("如何安装速存图片插件 MV3")
        box.setText(text)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec_()



    # ────────────────────────────────────────
    # 目录监控：显示插件保存的新文件
    # ────────────────────────────────────────
    def _get_plugin_save_dir(self) -> str:
        """插件把图片存到：系统下载目录/WebImageSaver"""
        from PyQt5.QtCore import QStandardPaths
        dl = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        if not dl:
            dl = os.path.join(os.path.expanduser("~"), "Downloads")
        return os.path.join(dl, "WebImageSaver")

    _IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".avif", ".ico"}

    def _scan_imgonly_files(self):
        """每秒扫描浏览器暂存目录（下载目录/WebImageSaver）：
        - 若保存路径与暂存目录不同 → 把新图移动过去并记录；
        - 若保存路径就等于暂存目录 → 图片本就在此，直接记录（不搬运）。"""
        try:
            self._archive_new(log=True)
        except Exception as e:
            self._log_problem(f"❌ 图片归档错误：{e}")

    @staticmethod
    def _file_sig(path):
        st = os.stat(path)
        return (os.path.basename(path), st.st_size, int(st.st_mtime))

    def _archive_new(self, log: bool = True):
        staging = self._get_plugin_save_dir()
        if not os.path.isdir(staging):
            return
        target = self.save_path.text().strip()
        if not target:
            return
        try:
            os.makedirs(target, exist_ok=True)
        except Exception as e:
            if log:
                self._log_problem(f"❌ 保存路径不可用：{target}（{e}）")
            return

        same_dir = os.path.abspath(staging) == os.path.abspath(target)
        for name in sorted(os.listdir(staging)):
            if name.endswith(".crdownload"):
                continue
            if os.path.splitext(name)[1].lower() not in self._IMG_EXTS:
                continue
            src = os.path.join(staging, name)
            if not os.path.isfile(src):
                continue
            try:
                sig = self._file_sig(src)
            except OSError:
                continue   # 文件可能刚被移走/占用，下一轮再看

            if sig in self._archived_seen:
                # 这张已经处理过；若是搬运模式，上次可能“复制成功但删除失败”，顺手清一下暂存副本
                if not same_dir:
                    try: os.remove(src)
                    except OSError: pass
                continue

            if same_dir:
                # 目标即暂存区：不搬运，只记录
                self._archived_seen.add(sig)
                if log:
                    self.list_widget.addItem(f"✅ 已保存图片：{name}")
                    self.list_widget.scrollToBottom()
            else:
                # 跨目录：先复制（成功即代表图片已安全落到目标），记录后再删暂存副本
                dst = self._unique_path(os.path.join(target, name))
                try:
                    shutil.copy2(src, dst)
                except (PermissionError, OSError):
                    continue   # 文件可能仍在写入或被占用，下一轮重试（不记录、不标记）
                self._archived_seen.add(sig)   # 复制成功即标记，避免重复
                if log:
                    self.list_widget.addItem(f"✅ 已保存图片：{os.path.basename(dst)}")
                    self.list_widget.scrollToBottom()
                try:
                    os.remove(src)             # 再删暂存副本；删不掉也没关系，下一轮会再清
                except OSError:
                    pass

    @staticmethod
    def _unique_path(path: str) -> str:
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        i = 1
        while os.path.exists(f"{base} ({i}){ext}"):
            i += 1
        return f"{base} ({i}){ext}"

    def _prime_seen_and_quiet(self, scan_dir=None):
        """启用/切换保存路径时调用：
        - 目标≠暂存区 → 把暂存区已有的图片搬过去并记录；
        - 目标==暂存区 → 把已有文件标记为已知（不刷屏），之后只记录新图。"""
        staging = self._get_plugin_save_dir()
        target = self.save_path.text().strip()
        try:
            same_dir = bool(target) and os.path.isdir(staging) \
                and os.path.abspath(staging) == os.path.abspath(target)
        except Exception:
            same_dir = False
        if same_dir:
            self._archived_seen = set()
            try:
                for n in os.listdir(staging):
                    p = os.path.join(staging, n)
                    if os.path.isfile(p):
                        try: self._archived_seen.add(self._file_sig(p))
                        except OSError: pass
            except Exception:
                pass
        else:
            try:
                self._archive_new(log=True)
            except Exception:
                pass

    def _log_problem(self, msg: str):
        """把诊断/连接/错误类信息写到下方「问题记录」栏。"""
        try:
            self.problem_widget.addItem(msg)
            self.problem_widget.scrollToBottom()
        except Exception:
            pass

    def _diagnose(self):
        """把当前关键状态打到「问题记录」栏，方便排查“为什么没存/没反应”。"""
        staging = self._get_plugin_save_dir()
        target = self.save_path.text().strip()
        try:
            same_dir = bool(target) and os.path.abspath(staging) == os.path.abspath(target)
        except Exception:
            same_dir = False
        try:
            n_img = len([f for f in os.listdir(staging)
                         if os.path.splitext(f)[1].lower() in self._IMG_EXTS]) \
                    if os.path.isdir(staging) else 0
        except Exception:
            n_img = -1
        conn = "已连接" if _ws_connected() else "未连接（浏览器扩展没连上或程序刚启动）"
        port = ("监听正常" if _ws_server_ok is True
                else "端口被占用" if _ws_server_ok is False else "启动中")
        self._log_problem("🔧 诊断：")
        self._log_problem(f"   • 本地端口 {_WS_PORT}：{port}")
        self._log_problem(f"   • 插件连接：{conn}")
        self._log_problem(f"   • 浏览器暂存目录：{staging}（当前 {n_img} 张图）")
        self._log_problem(f"   • 归档保存路径：{target or '（未设置）'}")
        if same_dir:
            self._log_problem("   • ⚠ 两者相同：图片会直接留在此目录、不再搬运（正常，只是不移动）")
        self._log_problem(f"   • 启用状态：{'开' if self.chk_imgonly.isChecked() else '关'}")

    # ────────────────────────────────────────
    # 速存文本
    # ────────────────────────────────────────
    def _current_txt_key(self) -> str:
        for key, rb in self._txt_radio.items():
            if rb.isChecked():
                return key
        return "F4"

    def _on_txt_hotkey_changed(self, _=None):
        key = self._current_txt_key()
        if hasattr(self, "_sc_manual"):
            self._sc_manual.setKey(QKeySequence(key))
        # 无论是否启用，都在「运行记录」留一条改键记录
        self.list_widget.addItem(f"⌨️ 文本快捷键已切换为：{key}")
        self.list_widget.scrollToBottom()
        # 仅在已启用时才真正重注册全局热键
        if self.chk_manual.isChecked():
            self._register_txt_hotkey(announce=False)

    def _on_manual_toggled(self, checked: bool):
        if checked:
            self._sc_manual.setEnabled(True)
            self._register_txt_hotkey(announce=False)
            self.list_widget.addItem(
                f"🟡 速存文本：已启用（按 {self._current_txt_key()} 在资源管理器创建 .txt）"
            )
        else:
            self._sc_manual.setEnabled(False)
            self._unregister_txt_hotkey()
            self.list_widget.addItem("⏹️ 速存文本：已关闭")

    def _register_txt_hotkey(self, announce: bool = True) -> bool:
        key = self._current_txt_key()
        if getattr(self, "_hotkey_registered_key", None) == key:
            return True
        self._unregister_txt_hotkey()
        vk = VK_CODE.get(key, VK_CODE["F4"])
        ok = ctypes.windll.user32.RegisterHotKey(None, self._hotkey_id, 0x0000, vk)
        if not ok:
            self.list_widget.addItem(f"❌ 注册热键 {key} 失败，可能被其它程序占用")
            self._hotkey_registered_key = None
            return False
        if self._hotkey_filter is None:
            self._hotkey_filter = _GlobalHotkeyFilter(self.manual_fast_save, self._hotkey_id)
            QCoreApplication.instance().installNativeEventFilter(self._hotkey_filter)
        self._hotkey_registered_key = key
        if announce:
            self.list_widget.addItem(f"🟡 速存文本全局热键就绪：{key}")
        return True

    def _unregister_txt_hotkey(self):
        try:
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
        finally:
            self._hotkey_registered_key = None

    def manual_fast_save(self):
        if not self.chk_manual.isChecked():
            self.list_widget.addItem("⚠️ 请先启用速存文本")
            return
        if not _WIN_OK:
            self.list_widget.addItem("❌ 手动功能不可用：缺少 pywin32/pyperclip")
            return
        try:
            import win32com.client
            import win32gui

            # ── 第一步：只取"前台激活"的资源管理器窗口 ──────────────
            fg_hwnd = win32gui.GetForegroundWindow()
            if not fg_hwnd:
                self.list_widget.addItem("⚠️ 无法获取前台窗口，请先点击资源管理器再按快捷键")
                return

            shell    = win32com.client.Dispatch("Shell.Application")
            active_window = None
            for window in shell.Windows():
                try:
                    if int(window.HWND) == fg_hwnd:
                        active_window = window
                        break
                except Exception:
                    continue

            if active_window is None:
                self.list_widget.addItem("⚠️ 前台窗口不是资源管理器，请先切换到资源管理器再按快捷键")
                return

            # ── 第二步：获取选中项，限制为"恰好 1 个文件" ────────────
            try:
                sel = active_window.Document.SelectedItems()
                count = sel.Count
            except Exception:
                self.list_widget.addItem("❌ 无法读取选中项")
                return

            if count == 0:
                self.list_widget.addItem("⚠️ 未选中任何文件，请先选中一个文件再按快捷键")
                return
            if count > 1:
                self.list_widget.addItem(f"⚠️ 选中了 {count} 个项目，每次只能对 1 个文件操作，请重新选择")
                return

            item = sel.Item(0)
            target_path = item.Path

            # 排除文件夹
            if os.path.isdir(target_path):
                self.list_widget.addItem(f"⚠️ 选中的是文件夹，不支持对文件夹操作：{os.path.basename(target_path)}")
                return

            # ── 第三步：读取剪贴板 ───────────────────────────────────
            clip_text = ""
            try:
                clip_text = pyperclip.paste().strip()
            except Exception:
                pass

            self.list_widget.addItem(
                f"📋 剪贴板{'有内容' if clip_text else '无内容（将写入空文件）'}"
            )

            # ── 第四步：写入同名 .txt ────────────────────────────────
            txt_path = os.path.splitext(target_path)[0] + ".txt"
            try:
                with open(txt_path, "w", encoding="utf-8") as fp:
                    fp.write(clip_text)
                self.list_widget.addItem(f"✅ 速存文本成功：{os.path.basename(txt_path)}")
            except Exception as e:
                self.list_widget.addItem(f"❌ 写入失败：{txt_path}（{e}）")

            self.list_widget.scrollToBottom()
        except Exception as e:
            self.list_widget.addItem(f"❌ 速存文本错误：{e}")

    # ────────────────────────────────────────
    # 公共工具
    # ────────────────────────────────────────
    def _enter_idle(self, reset_switches=False):
        if reset_switches:
            self._block_switches(True)
            try:
                self.chk_imgonly.setChecked(False)
                self.chk_manual.setChecked(False)
            finally:
                self._block_switches(False)
        try:
            self._sc_manual.setEnabled(False)
        except Exception:
            pass
        self.state = self.STATE_IDLE
        self._unregister_txt_hotkey()
        for h in [self._imgonly_timer]:
            try:
                if hasattr(h, "stop"): h.stop()
            except Exception:
                pass

    def _block_switches(self, yes: bool):
        for w in [self.chk_imgonly, self.chk_manual]:
            try: w.blockSignals(yes)
            except Exception: pass

    def _append_log(self, text: str):
        try:
            self.list_widget.addItem(text)
            self.list_widget.scrollToBottom()
        except Exception:
            pass

    def _init_save_dir(self):
        path = self._resolve_default_dir()
        self.save_path.setText(path)
        self.list_widget.addItem(f"📁 初始路径：{path}")

    def _resolve_default_dir(self) -> str:
        candidates = []
        pic = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        if pic: candidates.append(os.path.join(pic, "WebImageSaver"))
        home = os.path.expanduser("~") or ""
        if home: candidates.append(os.path.join(home, "WebImageSaver"))
        candidates.append(os.path.join(os.getcwd(), "WebImageSaver"))
        for p in candidates:
            ok, norm, _ = self._ensure_writable_dir(p, create=True)
            if ok: return norm
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if folder:
            ok, norm, _ = self._ensure_writable_dir(folder, create=True)
            if ok: return norm
        fallback = os.path.join(home or os.getcwd(), "WebImageSaver")
        os.makedirs(fallback, exist_ok=True)
        return os.path.abspath(fallback)

    def _ensure_writable_dir(self, path, create=True):
        try:
            if not path: return False, "", "空路径"
            if create: os.makedirs(path, exist_ok=True)
            tf = os.path.join(path, "__w_test__.tmp")
            with open(tf, "w") as f: f.write("ok")
            os.remove(tf)
            return True, os.path.abspath(path), ""
        except Exception as e:
            return False, path, str(e)

    def _require_writable_path(self, interactive=True) -> bool:
        path = self.save_path.text().strip()
        ok, norm, err = self._ensure_writable_dir(path, create=True)
        if ok:
            self.save_path.setStyleSheet("")
            if norm != path: self.save_path.setText(norm)
            return True
        self.save_path.setStyleSheet("border: 1px solid #e05;")
        if not interactive:
            return False
        if path: self.list_widget.addItem(f"⚠️ 路径不可用：{path}（{err}）")
        while True:
            folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
            if not folder: return False
            ok2, norm2, err2 = self._ensure_writable_dir(folder, create=True)
            if ok2:
                self.save_path.setStyleSheet("")
                self.save_path.setText(norm2)
                self._prime_seen_and_quiet(norm2)
                return True
            self.list_widget.addItem(f"❌ 该目录不可写：{folder}（{err2}），请重新选择")

    def _on_path_edited(self, _=None):
        self._require_writable_path(interactive=False)

    def _choose_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if not folder: return
        self.save_path.setText(folder)
        if self._require_writable_path(interactive=True):
            path = self.save_path.text().strip()
            self.list_widget.addItem(f"📁 保存路径已改为：{path}")
            self.list_widget.scrollToBottom()
            self._prime_seen_and_quiet(path)

    # ────────────────────────────────────────
    # 生命周期
    # ────────────────────────────────────────
    def hideEvent(self, e):
        try: self._sc_manual.setEnabled(False)
        finally: super().hideEvent(e)

    def showEvent(self, e):
        if not hasattr(self, "_container"):
            self._bind_container_switch()
        super().showEvent(e)
        if self.chk_manual.isChecked():
            self._sc_manual.setEnabled(True)
            self._register_txt_hotkey(announce=False)

    # ────────────────────────────────────────
    # 速建文件夹
    # ────────────────────────────────────────
    @staticmethod
    def _next_folder_name(name: str) -> str:
        """
        推算下一个文件夹名：
          纯数字              511  → 512  （保持同位数，不进位补零）
          字母+数字后缀       H04  → H05  （保持数字段位数）
          汉字/文字+数字后缀  记录8 → 记录9
          无数字后缀          服装  → 服装002
        """
        m = re.search(r'^(.*?)(\d+)$', name)
        if not m:
            # 无数字结尾：追加 002
            return name + "002"
        prefix, num_str = m.group(1), m.group(2)
        next_num = int(num_str) + 1
        # 保持原位数（如 04→05，04→10 时不截断）
        width = len(num_str)
        next_str = str(next_num).zfill(width) if len(str(next_num)) <= width else str(next_num)
        return prefix + next_str

    def _current_mkdir_key(self) -> str:
        """当前顺序新建所选热键（F5-F8），默认 F8。"""
        for key, rb in self._mkdir_radio.items():
            if rb.isChecked():
                return key
        return "F8"

    def _register_mkdir_seq(self, announce: bool = True) -> bool:
        """注册（或按所选键重注册）顺序新建热键。"""
        ctypes.windll.user32.UnregisterHotKey(None, self._mkdir_hotkey_id)
        seq_key = self._current_mkdir_key()
        ok = ctypes.windll.user32.RegisterHotKey(
            None, self._mkdir_hotkey_id, 0x0000, VK_CODE[seq_key]
        )
        if not ok:
            self._mkdir_hotkey_registered = False
            return False
        if self._mkdir_hotkey_filter is None:
            self._mkdir_hotkey_filter = _GlobalHotkeyFilter(
                self.mkdir_fast_create, self._mkdir_hotkey_id
            )
            QCoreApplication.instance().installNativeEventFilter(self._mkdir_hotkey_filter)
        self._mkdir_hotkey_registered = True
        if announce:
            self.list_widget.addItem(f"⌨️ 顺序新建热键切换为：{seq_key}")
        return True

    def _on_mkdir_hotkey_changed(self, _=None):
        """切换顺序新建可选键：始终记录一条；仅已启用时才真正重注册热键。"""
        seq_key = self._current_mkdir_key()
        self.list_widget.addItem(f"⌨️ 顺序新建热键已切换为：{seq_key}")
        self.list_widget.scrollToBottom()
        if self.chk_mkdir.isChecked():
            self._register_mkdir_seq(announce=False)

    def _on_mkdir_toggled(self, checked: bool):
        if checked:
            seq_key = self._current_mkdir_key()
            if not self._register_mkdir_seq(announce=False):
                self.list_widget.addItem(f"❌ 注册 {seq_key} 热键失败，可能被其他程序占用")
                return

            # 同时注册 F9「直接新建」
            ok9 = ctypes.windll.user32.RegisterHotKey(
                None, self._mkdir_direct_id, 0x0000, VK_CODE["F9"]
            )
            if ok9:
                if self._mkdir_direct_filter is None:
                    self._mkdir_direct_filter = _GlobalHotkeyFilter(
                        self.mkdir_direct_create, self._mkdir_direct_id
                    )
                    QCoreApplication.instance().installNativeEventFilter(self._mkdir_direct_filter)
                self.list_widget.addItem(f"🟢 速建文件夹：已启用（{seq_key} 顺序新建 / F9 直接新建 就绪）")
            else:
                self.list_widget.addItem(f"🟢 速建文件夹：{seq_key} 已启用；⚠️ F9 注册失败（可能被占用）")
        else:
            self._unregister_mkdir_hotkey()
            self.list_widget.addItem("⏹️ 速建文件夹：已关闭")

    def _block_mkdir(self, yes: bool):
        try: self.chk_mkdir.blockSignals(yes)
        except Exception: pass

    def _unregister_mkdir_hotkey(self):
        try:
            ctypes.windll.user32.UnregisterHotKey(None, self._mkdir_hotkey_id)
            ctypes.windll.user32.UnregisterHotKey(None, self._mkdir_direct_id)
        finally:
            self._mkdir_hotkey_registered = False

    def mkdir_fast_create(self):
        """顺序新建热键触发：在当前资源管理器选中文件夹旁边新建下一个编号文件夹。"""
        if not self.chk_mkdir.isChecked():
            self.list_widget.addItem("⚠️ 请先启用速建文件夹")
            return
        if not _WIN_OK:
            self.list_widget.addItem("❌ 功能不可用：缺少 pywin32")
            return
        try:
            import win32com.client
            import win32gui

            fg_hwnd = win32gui.GetForegroundWindow()
            if not fg_hwnd:
                self.list_widget.addItem("⚠️ 无法获取前台窗口，请先点击资源管理器")
                return

            shell = win32com.client.Dispatch("Shell.Application")
            active_window = None
            for window in shell.Windows():
                try:
                    if int(window.HWND) == fg_hwnd:
                        active_window = window
                        break
                except Exception:
                    continue

            if active_window is None:
                self.list_widget.addItem("⚠️ 前台窗口不是资源管理器")
                return

            try:
                sel = active_window.Document.SelectedItems()
                count = sel.Count
            except Exception:
                self.list_widget.addItem("❌ 无法读取选中项")
                return

            if count == 0:
                self.list_widget.addItem(f"⚠️ 未选中任何文件夹，请先选中一个文件夹再按 {self._current_mkdir_key()}")
                return
            if count > 1:
                self.list_widget.addItem(f"⚠️ 选中了 {count} 个项目，每次只能对 1 个文件夹操作")
                return

            item = sel.Item(0)
            target_path = item.Path

            if not os.path.isdir(target_path):
                self.list_widget.addItem(f"⚠️ 选中的是文件，请选中一个文件夹再按 {self._current_mkdir_key()}")
                return

            parent_dir  = os.path.dirname(target_path)
            folder_name = os.path.basename(target_path)
            new_name    = self._next_folder_name(folder_name)
            new_path    = os.path.join(parent_dir, new_name)

            if os.path.exists(new_path):
                self.list_widget.addItem(f"⚠️ 目标已存在，跳过：{new_name}")
                return

            os.makedirs(new_path)
            self.list_widget.addItem(f"✅ 速建文件夹成功：{new_name}")
            self.list_widget.scrollToBottom()

        except Exception as e:
            self.list_widget.addItem(f"❌ 速建文件夹错误：{e}")

    def mkdir_direct_create(self):
        """F9 触发：在当前资源管理器窗口内，仅当未选中任何项时，
        新建一个以「直接新建」文本框内容命名的空文件夹（默认 Grok）。"""
        if not self.chk_mkdir.isChecked():
            self.list_widget.addItem("⚠️ 请先启用速建文件夹")
            return
        if not _WIN_OK:
            self.list_widget.addItem("❌ 功能不可用：缺少 pywin32")
            return
        name = self.mkdir_name.text().strip() or "Grok"
        name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "Grok"
        try:
            import win32com.client
            import win32gui

            fg_hwnd = win32gui.GetForegroundWindow()
            if not fg_hwnd:
                self.list_widget.addItem("⚠️ 无法获取前台窗口，请先点击资源管理器")
                return

            shell = win32com.client.Dispatch("Shell.Application")
            active_window = None
            for window in shell.Windows():
                try:
                    if int(window.HWND) == fg_hwnd:
                        active_window = window
                        break
                except Exception:
                    continue

            if active_window is None:
                self.list_widget.addItem("⚠️ 前台窗口不是资源管理器")
                return

            # 仅在“未选中任何项”时才直接新建
            try:
                count = active_window.Document.SelectedItems().Count
            except Exception:
                count = 0
            if count > 0:
                self.list_widget.addItem(f"ℹ️ 已选中 {count} 项，F9 直接新建仅在未选中任何项时生效")
                return

            # 取当前窗口所在目录
            try:
                cur_dir = active_window.Document.Folder.Self.Path
            except Exception:
                cur_dir = ""
            if not cur_dir or not os.path.isdir(cur_dir):
                self.list_widget.addItem("⚠️ 无法确定当前文件夹（可能在“此电脑”等特殊位置）")
                return

            new_path = self._unique_path(os.path.join(cur_dir, name))
            os.makedirs(new_path)
            self.list_widget.addItem(f"✅ 直接新建成功：{os.path.basename(new_path)}")
            self.list_widget.scrollToBottom()

        except Exception as e:
            self.list_widget.addItem(f"❌ 直接新建错误：{e}")

    def closeEvent(self, e):
        self._unregister_txt_hotkey()
        self._unregister_mkdir_hotkey()
        super().closeEvent(e)

    def _bind_container_switch(self):
        w = self.parent()
        while w:
            if isinstance(w, (QTabWidget, QStackedWidget)):
                self._container = w
                try: w.currentChanged.connect(self._on_container_current_changed)
                except Exception: pass
                break
            w = w.parent()

    def _on_container_current_changed(self, idx: int):
        pass
