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
    QAbstractNativeEventFilter, QCoreApplication, QSize,
)
from PyQt5.QtGui import QKeySequence, QIcon, QPixmap, QPainter, QFont, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget,
    QCheckBox, QFileDialog, QShortcut,
    QComboBox, QTabWidget, QStackedWidget,
    QRadioButton, QButtonGroup,
    QFrame, QSizePolicy,
)

# ==================== 本地模块 ====================
from styles.style_all import (
    TEXT_STYLE,
    BUTTON_STYLE,
    LINEEDIT_STYLE,
    install_card_title,
    make_card,
    apply_folder_path_edit,
    restyle_folder_path_edit,
    make_glyph_icon,
    restyle_card_frame,
    restyle_card_title,
    content_primary_color,
    content_secondary_color,
    CARD_TOP_GAP,
    CARD_LEFT_GAP,
    CARD_RIGHT_GAP,
    CARD_BOTTOM_GAP,
    theme,
    tk,
)

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
# 预览标签（格式对齐「截图工具」PageScreenshot.PreviewLabel）
# · 主区域 stretch 占满：占位文案居中 / 图片等比缩放 / 非图片记录显示文字
# · 尺寸随控件 resize 重算；minimumSizeHint 钉死，避免长文字把窗口顶高
# ═══════════════════════════════════════════════════════════════
class FastPreviewLabel(QLabel):
    _PLACEHOLDER = "（选中左侧记录可预览）"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._src = None          # QPixmap or None
        self._mode = "empty"      # empty | image | text
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(220, 220)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._apply_style()
        self.setText(self._PLACEHOLDER)

    def minimumSizeHint(self):
        # 阻断 wordWrap 文本的 heightForWidth 向上传染（同截图预览的尺寸兜底思路）
        return QSize(220, 220)

    def sizeHint(self):
        return QSize(280, 280)

    def refresh_theme(self, *_):
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(f"background:transparent; color:{tk('text_dim')};")

    def show_empty(self):
        self._src = None
        self._mode = "empty"
        self._apply_style()
        self.clear()
        self.setAlignment(Qt.AlignCenter)
        self.setText(self._PLACEHOLDER)

    def set_image(self, pixmap):
        self._src = pixmap if (pixmap is not None and not pixmap.isNull()) else None
        if self._src is None:
            self.show_empty()
            return
        self._mode = "image"
        self._apply_style()
        self.setAlignment(Qt.AlignCenter)
        self._rescale()

    def set_text_content(self, text: str):
        """非图片运行记录：主区域展示文字（顶左对齐，格式贴近截图预览的主区占用）。"""
        self._src = None
        self._mode = "text"
        self._apply_style()
        self.clear()
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setText(text or self._PLACEHOLDER)

    def _rescale(self):
        if self._mode != "image" or self._src is None:
            return
        self.setPixmap(self._src.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, e):
        self._rescale()
        super().resizeEvent(e)


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

    @staticmethod
    def _set_qprop(w, name, value):
        """设置一个 Qt 动态属性并刷新样式——用于命中 app.qss / app_light.qss 里的属性选择器。"""
        w.setProperty(name, value)
        w.style().unpolish(w)
        w.style().polish(w)

    @staticmethod
    def _make_glyph_icon(glyph: str, px: int = 16, color: str = "#8fa3d9") -> QIcon:
        """兼容旧调用；实现已迁到 style_all.make_glyph_icon。"""
        return make_glyph_icon(glyph, px=px, color=color)

    # ===== 窗口高度 BUG 根治（与 Grok 诊断一致：heightForWidth 把虚高传给主窗口）=====
    # 本页含 wordWrap 自动换行标签，会让整页 hasHeightForWidth()=True。Qt 据此按当前
    # （较窄的）宽度把页面高度算大，这个虚高顺着布局链一路传到主窗口，抬高了窗口的
    # “首选高度”，于是真机上一拖标题栏，窗口就往首选高度长高、且缩不回去（切到没有此
    # 特性的页面才松开）。对照 6 个正常页面：它们 hasHeightForWidth()=False，窗口首选
    # 高度稳定在侧边栏决定的 836（<900），从不长高。
    # 修法：本页对外声明“高度不随宽度变化”，并把对外“首选高度”压到不超过侧边栏——
    #   · 标签内部仍照常换行，不截断文字（只是不把该属性外传给窗口）；
    #   · 实际布局仍会把可用高度分配给本页，Expanding 子控件照常填满，视觉无变化。
    def hasHeightForWidth(self):
        return False

    def sizeHint(self):
        s = super().sizeHint()
        return QSize(s.width(), min(s.height(), 700))

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setSpacing(9)
        # 与系统总览一致：ContentRoot 已有左右内边距，页面不再叠第二层
        lay.setContentsMargins(0, 0, 0, 0)

        # ══════════ 顶部两卡片 ══════════
        row_top = QHBoxLayout()
        row_top.setSpacing(8)
        lay.addLayout(row_top)

        # ── 最左：速存启用（总开关，与左侧菜单 LED 联动） ──
        self._theme_frames = []
        self._theme_titles = []
        self._theme_secondary_bold = []
        self._theme_secondary_plain = []

        gb_enable = make_card("CardFastEnable")
        gb_enable.setMinimumWidth(150)
        self._theme_frames.append(gb_enable)
        enable_box = QVBoxLayout(gb_enable)
        enable_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        enable_box.setSpacing(0)
        title_enable = install_card_title(gb_enable, enable_box, "速存启用")
        self._theme_titles.append(title_enable)

        self.chk_enable_all = QCheckBox("启用速存")
        self.chk_enable_all.setStyleSheet("background: transparent;")
        enable_box.addWidget(self.chk_enable_all)
        enable_box.addSpacing(8)

        # 插件状态（状态灯 + 提示文字）—— 所有更新都直接显示在这一行，不再单独维护问题记录列表
        row_plugin = QHBoxLayout()
        row_plugin.setSpacing(4)
        row_plugin.setContentsMargins(0, 0, 0, 0)

        self.lbl_plugin_dot = QLabel("●")
        self.lbl_plugin_dot.setFixedWidth(16)
        self.lbl_plugin_dot.setStyleSheet("background: transparent; color: #f0a500; font-size: 14px;")  # 初始黄灯：检测中

        self.lbl_nm_status = QLabel("检测中...")
        self.lbl_nm_status.setWordWrap(True)
        self.lbl_nm_status.setStyleSheet("background: transparent;")
        self._typo(self.lbl_nm_status, "muted")

        row_plugin.addWidget(self.lbl_plugin_dot)
        row_plugin.addWidget(self.lbl_nm_status, 1)
        enable_box.addLayout(row_plugin)
        enable_box.addStretch(1)   # 内容顶部对齐，多余高度留在卡片底部

        # ── 速存图片 ──
        gb_img  = make_card("CardFastAuto")
        self._theme_frames.append(gb_img)
        img_box = QVBoxLayout(gb_img)
        img_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        img_box.setSpacing(0)
        title_img = install_card_title(gb_img, img_box, "速存图片")
        self._theme_titles.append(title_img)

        self.chk_imgonly = QCheckBox("启用速存图片")
        self.chk_imgonly.setVisible(False)  # 子开关不展示，由速存启用总开关控制

        # 安装按钮 + 提示语（原来的“快捷键 Alt+1”整块不再展示，只保留隐藏对象供内部逻辑引用）
        row_kb = QHBoxLayout()
        row_kb.setSpacing(6)
        self.btn_plugin_help = QPushButton("安装")
        self.btn_plugin_help.setToolTip("如何安装速存图片插件 MV3")
        self.btn_plugin_help.setProperty("kind", "mini")
        self.btn_plugin_help.style().unpolish(self.btn_plugin_help)
        self.btn_plugin_help.style().polish(self.btn_plugin_help)
        row_kb.addWidget(self.btn_plugin_help)

        lbl_img_hint = QLabel("鼠标停在图片上，按 Alt+1 保存原图")
        lbl_img_hint.setWordWrap(True)
        lbl_img_hint.setStyleSheet("background: transparent;")
        self._typo(lbl_img_hint, "muted")
        row_kb.addWidget(lbl_img_hint, 1)
        img_box.addLayout(row_kb)
        img_box.addSpacing(6)

        # 快捷键下拉框保留对象（内部逻辑仍会用到），但不再显示在界面上
        self.combo_img_hotkey = QComboBox()
        self.combo_img_hotkey.setObjectName("FastSaveHotkey")
        self.combo_img_hotkey.addItems(["Alt+1"])
        self.combo_img_hotkey.setItemIcon(0, self._make_glyph_icon("⌨", color=content_secondary_color()))
        self.combo_img_hotkey.setCurrentText("Alt+1")
        self.combo_img_hotkey.setEnabled(False)   # 固定 Alt+1，不提供改键
        self.combo_img_hotkey.setVisible(False)

        # 保存路径 —— 全局「文件夹路径」样式（圆角框 + 📁）
        row_path = QHBoxLayout()
        row_path.setSpacing(4)
        self.save_path = QLineEdit("")
        self._path_icon_action = apply_folder_path_edit(self.save_path)
        row_path.addWidget(self.save_path, 1)
        img_box.addLayout(row_path)
        img_box.addSpacing(6)

        self.btn_choose_dir = QPushButton("另选目录")
        img_box.addWidget(self.btn_choose_dir)
        img_box.addStretch(1)

        # ── 速存文本 ──
        gb_txt  = make_card("CardFastManual")
        self._theme_frames.append(gb_txt)
        txt_box = QVBoxLayout(gb_txt)
        txt_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        txt_box.setSpacing(0)
        title_txt = install_card_title(gb_txt, txt_box, "速存文本")
        self._theme_titles.append(title_txt)

        self.chk_manual = QCheckBox("启用速存文本")
        self.chk_manual.setVisible(False)  # 子开关不展示，由速存启用总开关控制

        lbl_hint = QLabel("可快速创建主体同名文本文件")
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("background: transparent;")
        self._typo(lbl_hint, "muted")
        txt_box.addWidget(lbl_hint)
        txt_box.addSpacing(6)
        self._txt_hotkey_group = QButtonGroup(self)
        row_radios = QHBoxLayout()
        row_radios.setSpacing(4)
        self._txt_radio = {}
        for key in ["F3", "F4"]:
            rb = QRadioButton(key)
            rb.setStyleSheet("background: transparent;")
            self._txt_radio[key] = rb
            self._txt_hotkey_group.addButton(rb)
            row_radios.addWidget(rb)
        self._txt_radio["F4"].setChecked(True)
        row_radios.addStretch(1)
        txt_box.addLayout(row_radios)
        txt_box.addStretch(1)

        # ── 速建文件夹（回到顶部，与 A/B/C 同排） ──
        gb_mkdir = make_card("CardFastMkdir")
        gb_mkdir.setMinimumWidth(230)
        self._theme_frames.append(gb_mkdir)
        mkdir_box = QVBoxLayout(gb_mkdir)
        mkdir_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        mkdir_box.setSpacing(0)
        title_mkdir = install_card_title(gb_mkdir, mkdir_box, "速建文件夹")
        self._theme_titles.append(title_mkdir)

        self.chk_mkdir = QCheckBox("启用速建文件夹")
        self.chk_mkdir.setVisible(False)  # 子开关不展示，由速存启用总开关控制

        row_mkdir_key = QHBoxLayout()
        row_mkdir_key.setSpacing(4)
        lbl_seq = QLabel("顺序新建")
        lbl_seq.setStyleSheet(f"background:transparent; color:{content_secondary_color()}; font-weight:600;")
        self._theme_secondary_bold.append(lbl_seq)
        row_mkdir_key.addWidget(lbl_seq)
        self._mkdir_hotkey_group = QButtonGroup(self)
        self._mkdir_radio = {}
        for key in ["F5", "F6", "F7", "F8"]:
            rb = QRadioButton(key)
            rb.setStyleSheet("background: transparent;")
            self._mkdir_radio[key] = rb
            self._mkdir_hotkey_group.addButton(rb)
            row_mkdir_key.addWidget(rb)
        self._mkdir_radio["F8"].setChecked(True)
        row_mkdir_key.addStretch(1)
        mkdir_box.addLayout(row_mkdir_key)
        mkdir_box.addSpacing(6)

        row_mkdir_f9 = QHBoxLayout()
        row_mkdir_f9.setSpacing(4)
        lbl_f9 = QLabel("F9 直接新建")
        lbl_f9.setStyleSheet(f"background:transparent; color:{content_secondary_color()};")
        self._theme_secondary_plain.append(lbl_f9)
        row_mkdir_f9.addWidget(lbl_f9)
        self.mkdir_name = QLineEdit("Grok")
        self.mkdir_name.setPlaceholderText("默认 Grok")
        self.mkdir_name.setFixedWidth(100)
        self.mkdir_name.setProperty("inputStyle", "underline")
        self.mkdir_name.style().unpolish(self.mkdir_name)
        self.mkdir_name.style().polish(self.mkdir_name)
        row_mkdir_f9.addWidget(self.mkdir_name)
        row_mkdir_f9.addStretch(1)
        mkdir_box.addLayout(row_mkdir_f9)
        mkdir_box.addSpacing(4)

        row_mkdir_f10 = QHBoxLayout()
        row_mkdir_f10.setSpacing(4)
        lbl_f10 = QLabel("F10 直接新建")
        lbl_f10.setStyleSheet(f"background:transparent; color:{content_secondary_color()};")
        self._theme_secondary_plain.append(lbl_f10)
        row_mkdir_f10.addWidget(lbl_f10)
        self.mkdir_name_b = QLineEdit("Qwen")
        self.mkdir_name_b.setPlaceholderText("默认 Qwen")
        self.mkdir_name_b.setFixedWidth(100)
        self.mkdir_name_b.setProperty("inputStyle", "underline")
        self.mkdir_name_b.style().unpolish(self.mkdir_name_b)
        self.mkdir_name_b.style().polish(self.mkdir_name_b)
        row_mkdir_f10.addWidget(self.mkdir_name_b)
        row_mkdir_f10.addStretch(1)
        mkdir_box.addLayout(row_mkdir_f10)
        mkdir_box.addSpacing(6)

        lbl_mkdir_hint = QLabel("选中文件夹按所选键顺序新建；未选中时 F9/F10 直接新建对应文件夹")
        lbl_mkdir_hint.setWordWrap(True)
        lbl_mkdir_hint.setStyleSheet("background: transparent;")
        self._typo(lbl_mkdir_hint, "muted")
        mkdir_box.addWidget(lbl_mkdir_hint)
        mkdir_box.addStretch(1)

        row_top.addWidget(gb_enable, 10)   # 速存启用：约 10%
        row_top.addWidget(gb_img, 30)      # 速存图片：37 减少 20% → 约 30%
        row_top.addWidget(gb_txt, 11)      # 速存文本：18 减少 40% → 约 11%
        row_top.addWidget(gb_mkdir, 49)    # 速建文件夹：吸收 B/C 让出的份额，尽量加大 → 约 49%

        # 顶部四卡片整体限高，进一步降低高度
        # 注：这里必须用 setFixedHeight（同时钉住上下限），不能只用 setMaximumHeight。
        # 卡片内部有 lbl_nm_status 这种 setWordWrap(True) 的标签，心跳刷新时文字
        # 内容/粗细会变，导致其内部布局要的高度也跟着变；如果只封了上限，这个
        # 变化仍会通过 sizeHint 向外层（row_top → 页面 → 主窗口）渗透，使主窗口的
        # 最小高度被悄悄推高——顶层窗口不能比这个最小高度还小，于是窗口只会越
        # 变越高、不会缩回去（表现为"移动一次窗口，内容就往下掉一截"）。
        # setFixedHeight 会把该 QWidget 的 sizeHint 直接钉死在这个值上，内部子控件
        # 再怎么变化都不会再影响外层布局的尺寸计算。
        for _card in (gb_enable, gb_img, gb_txt, gb_mkdir):
            _card.setFixedHeight(175)

        # ══════════ 底部：运行记录（大，占主要空间） + 预览区（右侧，选中左侧记录可预览） ══════════
        row_bottom = QHBoxLayout()
        row_bottom.setSpacing(8)
        lay.addLayout(row_bottom, 1)   # 底部区域吸收窗口剩余高度

        card_runlog = make_card("CardFastRunLog")
        self._theme_frames.append(card_runlog)
        runlog_box = QVBoxLayout(card_runlog)
        runlog_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        runlog_box.setSpacing(0)
        title_runlog = install_card_title(card_runlog, runlog_box, "运行记录")
        self._theme_titles.append(title_runlog)

        self.list_widget = QListWidget()
        self.list_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSpacing(3)  # 与截图工具记录列表一致
        self.list_widget.setProperty("recordStyle", "dashed")   # 只保留上边虚线，滚动条重做
        self.list_widget.style().unpolish(self.list_widget)
        self.list_widget.style().polish(self.list_widget)
        runlog_box.addWidget(self.list_widget, 1)

        # 宽度比对齐截图工具：记录 3 : 预览 2
        row_bottom.addWidget(card_runlog, 3)

        # ── 预览区：格式对齐「截图工具 → 截图预览」──────────────────────────
        #   主区 stretch 吃满高度（占位/图/文字）+ 底部固定 meta 行
        card_preview = make_card("CardFastPreview")
        self._theme_frames.append(card_preview)
        preview_box = QVBoxLayout(card_preview)
        preview_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        preview_box.setSpacing(0)
        title_preview = install_card_title(card_preview, preview_box, "预览区")
        self._theme_titles.append(title_preview)

        self.preview = FastPreviewLabel()
        preview_box.addWidget(self.preview, 1)

        self.lbl_preview_meta = QLabel()
        self.lbl_preview_meta.setAlignment(Qt.AlignHCenter)
        self.lbl_preview_meta.setWordWrap(True)
        # 钉死高度：文件名过长交给 tooltip，避免 heightForWidth 顶高主窗口
        self.lbl_preview_meta.setFixedHeight(40)
        self.lbl_preview_meta.setProperty("typo", "muted")
        self.lbl_preview_meta.setVisible(False)
        preview_box.addWidget(self.lbl_preview_meta)

        row_bottom.addWidget(card_preview, 2)

        self.list_widget.currentItemChanged.connect(self._on_runlog_item_selected)

        self._theme_glyph_actions = [
            (self._path_icon_action, "📁"),
        ]
        self._theme_glyph_combo_items = [
            (self.combo_img_hotkey, 0, "⌨"),
        ]

        # ══════════ 信号与槽 ══════════
        self.log_sig.connect(self._append_log)
        self.plugin_status_sig.connect(self._apply_plugin_ui)
        self.btn_choose_dir.clicked.connect(self._choose_dir)
        self.btn_plugin_help.clicked.connect(self._show_plugin_help)
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
        self._closing = False   # 主窗口关闭时置 True，阻止后台检测线程再碰已销毁的界面
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

        # 速建文件夹热键（顺序新建，F5-F8 可选）
        self._mkdir_hotkey_id     = 0x1003
        self._mkdir_hotkey_filter = None
        self._mkdir_hotkey_registered = False
        # 直接新建 A（F9）
        self._mkdir_direct_id     = 0x1004
        self._mkdir_direct_filter = None
        # 直接新建 B（F10）
        self._mkdir_direct_b_id     = 0x1005
        self._mkdir_direct_b_filter = None
        self.chk_mkdir.toggled.connect(self._on_mkdir_toggled)

        self.clipboard = QApplication.clipboard()
        self.state     = self.STATE_IDLE

        self._init_save_dir()
        self._enter_idle(reset_switches=True)

        theme.changed.connect(self._apply_theme)

    def _apply_theme(self, *_args):
        """主题切换时重刷卡片外观（内联样式方案，不吃全局 QSS 级联，需手动重刷）。
        注：记录列表虚线框 / 下划线输入框 / 迷你按钮已迁移到 app.qss、app_light.qss 的
        属性选择器（recordStyle / inputStyle / kind），会随应用级样式表切换自动生效，
        这里只需要处理内联画色的部分：卡片外观、标题、次要文字、以及程序绘制的符号图标。"""
        for frame in self._theme_frames:
            restyle_card_frame(frame)
        for lbl in self._theme_titles:
            restyle_card_title(lbl)
        secondary = content_secondary_color()
        for lbl in self._theme_secondary_bold:
            lbl.setStyleSheet(f"background:transparent; color:{secondary}; font-weight:600;")
        for lbl in self._theme_secondary_plain:
            lbl.setStyleSheet(f"background:transparent; color:{secondary};")
        if hasattr(self, "save_path"):
            restyle_folder_path_edit(self.save_path, getattr(self, "_path_icon_action", None))
        for action, glyph in getattr(self, "_theme_glyph_actions", []):
            if action is getattr(self, "_path_icon_action", None):
                continue  # 已由 restyle_folder_path_edit 处理
            action.setIcon(self._make_glyph_icon(glyph, color=secondary))
        for combo, idx, glyph in getattr(self, "_theme_glyph_combo_items", []):
            combo.setItemIcon(idx, self._make_glyph_icon(glyph, color=secondary))
        if hasattr(self, "preview"):
            self.preview.refresh_theme()

    _IMG_LOG_RE = re.compile(r"已保存图片[：:]\s*(.+?\.(?:jpg|jpeg|png|gif|bmp|webp))", re.IGNORECASE)

    def _on_runlog_item_selected(self, current, _previous):
        """预览区联动（格式对齐截图工具）：
        · 图片记录 → 主区等比图 + 底部「文件名\\n宽×高」
        · 其它记录 → 主区文字；无选中 → 居中占位文案
        """
        if current is None:
            self.preview.show_empty()
            self.lbl_preview_meta.clear()
            self.lbl_preview_meta.setVisible(False)
            return

        text = current.text()

        m = self._IMG_LOG_RE.search(text)
        if m:
            filename = m.group(1).strip()
            full_path = os.path.join(self.save_path.text().strip(), filename)
            if os.path.isfile(full_path):
                pix = QPixmap(full_path)
                if not pix.isNull():
                    self.preview.set_image(pix)
                    # 与截图预览一致：文件名一行，分辨率一行
                    meta_text = f"{filename}\n{pix.width()}×{pix.height()}"
                    self.lbl_preview_meta.setText(meta_text)
                    self.lbl_preview_meta.setToolTip(meta_text)
                    self.lbl_preview_meta.setVisible(True)
                    return

        # 非图片记录（或图片文件已找不到）：主区文字，隐藏 meta
        self.preview.set_text_content(text)
        self.lbl_preview_meta.clear()
        self.lbl_preview_meta.setVisible(False)

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
            # 主窗口正在关闭 / 已关闭：这次检测的结果不用再传回界面了，直接退出
            if self._closing:
                return
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
                self._set_plugin_ui(GREEN, f"插件已连接\n{int(secs)}s 前心跳", bold=True)
                return
            # 4. 有连接但心跳超时 → 可能挂起，无法判定 → 黄
            if has_sock and secs >= _WS_PING_TTL:
                self._set_plugin_ui(YELLOW, f"⚠ 连接存在但无心跳\n{int(secs)}s 无心跳，插件可能挂起")
                return
            # 5. 刚断开不久 → 可能马上重连，无法判定 → 黄
            if secs < 120:
                self._set_plugin_ui(YELLOW, f"⚠ 插件已断开\n{int(secs)}s 前最后心跳")
                return

            # 6. 从未连接 / 很久没连 → 看 Chrome 是否在运行
            if _check_chrome_running():
                # Chrome 在跑但插件没连上 → 等待中 → 黄
                self._set_plugin_ui(YELLOW, "Chrome 运行中，等待插件连接…")
            else:
                # Chrome 没开，插件根本连不上 → 不能用 → 红
                self._set_plugin_ui(RED, "Chrome 未运行，插件无法连接（不能用）")

        if self._closing:
            return
        import threading as _th
        _th.Thread(target=_do_check, daemon=True).start()

    def _set_plugin_ui(self, color: str, text: str, bold: bool = False):
        """线程安全：通过信号把结果切回主线程更新（不能在子线程里直接碰 UI/定时器）。
        _closing 关闭了大部分竞态窗口；外层 try/except 是最后一道保险——
        万一检测线程正好卡在"判断完 _closing、还没来得及 emit"这一瞬间被关闭，
        C/C++ 侧对象已经没了，emit 会抛 RuntimeError，这里兜住，不让它冒到线程外面。"""
        if self._closing:
            return
        try:
            self.plugin_status_sig.emit(color, text, bool(bold))
        except RuntimeError:
            pass

    def _apply_plugin_ui(self, color: str, text: str, bold: bool):
        """在主线程真正更新状态灯与提示文字（由 plugin_status_sig 触发）。"""
        self._last_plugin_text = text
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
        """不再单独维护「问题记录」列表，诊断/连接/错误类信息直接显示在
        速存启用卡片里绿点右侧的状态提示文字上。"""
        try:
            self.lbl_nm_status.setText(msg)
        except Exception:
            pass

    def _diagnose(self):
        """把当前关键状态整理成一条多行文字，显示在插件状态提示上，方便排查“为什么没存/没反应”。"""
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
        lines = [
            "🔧 诊断：",
            f"• 本地端口 {_WS_PORT}：{port}",
            f"• 插件连接：{conn}",
            f"• 浏览器暂存目录：{staging}（当前 {n_img} 张图）",
            f"• 归档保存路径：{target or '（未设置）'}",
        ]
        if same_dir:
            lines.append("• ⚠ 两者相同：图片会直接留在此目录、不再搬运（正常，只是不移动）")
        lines.append(f"• 启用状态：{'开' if self.chk_imgonly.isChecked() else '关'}")
        self._log_problem("\n".join(lines))

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

            doc, n_tabs = self._resolve_active_view(fg_hwnd, prefer_selected=True)

            if doc is None and n_tabs == 0:
                self.list_widget.addItem("⚠️ 前台窗口不是资源管理器，请先切换到资源管理器再按快捷键")
                return
            if doc is None:
                self.list_widget.addItem(
                    f"⚠️ 未选中任何文件，请先选中一个文件再按快捷键（检测到 {n_tabs} 个标签）"
                )
                return

            # ── 第二步：获取选中项，限制为"恰好 1 个文件" ────────────
            try:
                sel = doc.SelectedItems()
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
        self.save_path.setStyleSheet(f"border: 1px solid {tk('err')};")
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
        推算下一个文件夹名：自动定位名称中的数字段并加 1，保留其余文字与位数。
          纯数字            511      → 512
          数字在结尾        H04      → H05 ；记录8 → 记录9
          数字在开头        5单元    → 6单元
          数字在中间        第2章    → 第3章
          含多段数字        2024第1季 → 2024第2季（默认对最后一段数字加 1）
          完全不含数字      服装     → 服装002
        位数处理：进位不足则补零保持原宽度（04→05）；超出原宽度则不截断（99→100，第9章→第10章）。
        """
        matches = list(re.finditer(r'\d+', name))
        if not matches:
            # 完全没有数字：追加 002 作为起始序号
            return name + "002"
        m = matches[-1]                       # 默认对最后一段数字加 1
        num_str = m.group(0)
        next_str = str(int(num_str) + 1).zfill(len(num_str))  # zfill 只补零、超宽不截断
        return name[:m.start()] + next_str + name[m.end():]

    @staticmethod
    def _next_available_folder_name(parent_dir: str, name: str) -> str:
        """
        目录感知的顺序新建：不是简单对选中名 +1，而是扫描同级目录里所有
        「同前缀 + 数字段 + 同后缀」的文件夹，取其中最大编号再 +1，从而自动跳过
        已存在的编号，一次建到位。
          选中 09，目录已有 10、11            → 12
          选中 H16B，目录已有 H15B/H16B/H17B → H18B
        位宽沿用选中名数字段的宽度（zfill 补零、超宽不截断）；若结果仍意外存在则
        继续 +1 直到空位。名称完全不含数字时，退回 name + 三位序号 起始。
        """
        matches = list(re.finditer(r'\d+', name))
        if not matches:
            # 无数字：从 name002 起向后找第一个空位
            n, width = 2, 3
            while True:
                cand = f"{name}{str(n).zfill(width)}"
                if not os.path.exists(os.path.join(parent_dir, cand)):
                    return cand
                n += 1

        m = matches[-1]                       # 定位最后一段数字
        prefix, suffix = name[:m.start()], name[m.end():]
        width  = len(m.group(0))
        max_num = int(m.group(0))             # 起点至少是选中名本身的编号

        # 扫描同级目录里「同前缀、同后缀」的文件夹，取最大编号
        pat = re.compile(r'^' + re.escape(prefix) + r'(\d+)' + re.escape(suffix) + r'$')
        try:
            for entry in os.listdir(parent_dir):
                if os.path.isdir(os.path.join(parent_dir, entry)):
                    mm = pat.match(entry)
                    if mm:
                        max_num = max(max_num, int(mm.group(1)))
        except OSError:
            pass

        # 从 max_num+1 起，找第一个不存在的编号
        n = max_num + 1
        while True:
            cand = prefix + str(n).zfill(width) + suffix
            if not os.path.exists(os.path.join(parent_dir, cand)):
                return cand
            n += 1

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

            # 注册 F9「直接新建 A」
            ok9 = ctypes.windll.user32.RegisterHotKey(
                None, self._mkdir_direct_id, 0x0000, VK_CODE["F9"]
            )
            if ok9 and self._mkdir_direct_filter is None:
                self._mkdir_direct_filter = _GlobalHotkeyFilter(
                    self.mkdir_direct_create_a, self._mkdir_direct_id
                )
                QCoreApplication.instance().installNativeEventFilter(self._mkdir_direct_filter)

            # 注册 F10「直接新建 B」
            ok10 = ctypes.windll.user32.RegisterHotKey(
                None, self._mkdir_direct_b_id, 0x0000, VK_CODE["F10"]
            )
            if ok10 and self._mkdir_direct_b_filter is None:
                self._mkdir_direct_b_filter = _GlobalHotkeyFilter(
                    self.mkdir_direct_create_b, self._mkdir_direct_b_id
                )
                QCoreApplication.instance().installNativeEventFilter(self._mkdir_direct_b_filter)

            if ok9 and ok10:
                self.list_widget.addItem(
                    f"🟢 速建文件夹：已启用（{seq_key} 顺序新建 / F9 · F10 直接新建 就绪）"
                )
            else:
                failed = " ".join(k for k, ok in (("F9", ok9), ("F10", ok10)) if not ok)
                self.list_widget.addItem(
                    f"🟢 速建文件夹：{seq_key} 已启用；⚠️ {failed} 注册失败（可能被占用）"
                )
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
            ctypes.windll.user32.UnregisterHotKey(None, self._mkdir_direct_b_id)
        finally:
            self._mkdir_hotkey_registered = False

    # ────────────────────────────────────────
    # 资源管理器（含 Win10/11 多标签）活动视图解析
    # ────────────────────────────────────────

    @staticmethod
    def _view_path(doc) -> str:
        """取某个文件夹视图当前所在目录，失败返回空串。

        注意：不能用 callable() 来区分「属性」和「方法」——
        pywin32 的 COM 对象实现了 __call__（默认属性），callable() 恒为真，
        误判会导致把属性当方法调用而取不到路径。这里改为直接按顺序试。
        """
        # 路径 1：pywin32（ShellFolderView）——属性式访问
        try:
            p = doc.Folder.Self.Path
            if p:
                return p
        except Exception:
            pass
        # 路径 2：comtypes dynamic 包装——方法式访问
        try:
            p = doc.Folder().Self().Path
            if p:
                return p
        except Exception:
            pass
        return ""

    @staticmethod
    def _children_by_zorder(hwnd):
        """按 z-order（从最顶层开始）列出 hwnd 的直接子窗口。"""
        import win32gui
        import win32con
        res = []
        try:
            h = win32gui.GetWindow(hwnd, win32con.GW_CHILD)   # z-order 最顶的子窗口
            guard = 0
            while h and guard < 256:
                res.append(h)
                h = win32gui.GetWindow(h, win32con.GW_HWNDNEXT)
                guard += 1
        except Exception:
            pass
        return res

    def _active_tab_hwnd(self, fg_hwnd):
        """取「当前活动标签」的控件窗口句柄（Win11 标签式资源管理器）。

        依据：每个标签都有自己的 ShellTabWindowClass 控件窗口，
        而【活动标签的控件窗口始终位于 z-order 最顶端】。
        注意：不能用「窗口是否可见」来判断 —— 对 Win11 资源管理器无效，
        非活动标签的窗口同样报告为可见（这正是之前几版失败的原因）。

        无标签（Win10 原生）时返回 0，调用方直接用主窗口即可。
        """
        import win32gui
        for h in self._children_by_zorder(fg_hwnd):
            try:
                if win32gui.GetClassName(h) == "ShellTabWindowClass":
                    return h          # 第一个即 z-order 最顶 = 活动标签
            except Exception:
                continue
        return 0

    def _tab_hwnd_of_window(self, w):
        """取某个 Shell 窗口对象（IWebBrowser2）所属【标签】的控件窗口句柄。

        关键：w.HWND 返回的是主窗口句柄（多标签下三个候选全一样，无法区分）；
        而 IShellBrowser::GetWindow() 返回的才是该标签自己的 ShellTabWindowClass 句柄。
        pywin32 原生支持 IServiceProvider::QueryService，可直接取到 IShellBrowser。
        """
        import pythoncom
        try:
            from win32com.shell import shell as _shell
            iid_sb = _shell.IID_IShellBrowser
        except Exception:
            iid_sb = pythoncom.MakeIID("{000214E2-0000-0000-C000-000000000046}")
        try:
            sp = w._oleobj_.QueryInterface(pythoncom.IID_IServiceProvider)
            sb = sp.QueryService(iid_sb, iid_sb)
            return int(sb.GetWindow())
        except Exception as e:
            self._sb_err = f"{e}"
            return 0

    def _resolve_active_view(self, fg_hwnd, prefer_selected: bool = False):
        """解析前台资源管理器「当前活动标签」的文件夹视图。

        返回 (doc, n_tabs)：
          doc 非 None            → 拿到活动视图，可用 .SelectedItems() / .Folder.Self.Path
          doc 为 None 且 n_tabs==0 → 前台窗口不是资源管理器
          doc 为 None 且 n_tabs>0  → 是资源管理器，但多标签下无法确定活动标签
        """
        import win32gui
        import win32com.client

        self._sb_err = ""
        shell = win32com.client.Dispatch("Shell.Application")
        candidates = []
        for w in shell.Windows():
            try:
                if int(w.HWND) == fg_hwnd:
                    candidates.append(w)
            except Exception:
                continue

        if not candidates:
            return None, 0
        if len(candidates) == 1:
            try:
                return candidates[0].Document, 1
            except Exception:
                return None, 1

        # ── 1. 主路径：z-order 最顶的 ShellTabWindowClass = 活动标签，
        #        再用 IShellBrowser::GetWindow() 找出属于它的那个 Shell 窗口对象 ──
        active_tab = self._active_tab_hwnd(fg_hwnd)
        self._last_tab_diag = f"活动标签 hwnd={active_tab}，候选 {len(candidates)} 个"
        if active_tab:
            seen = []
            for w in candidates:
                tab = self._tab_hwnd_of_window(w)
                seen.append(tab)
                if tab and tab == active_tab:
                    try:
                        return w.Document, len(candidates)
                    except Exception:
                        pass
            self._last_tab_diag += f"，各标签 hwnd={seen}"
            if self._sb_err:
                self._last_tab_diag += f"，IShellBrowser 错误({self._sb_err})"

        # ── 2. 回退：窗口标题与各标签目录比对 ──
        try:
            title = (win32gui.GetWindowText(fg_hwnd) or "").strip()
        except Exception:
            title = ""
        if title:
            def _leaf(s: str) -> str:
                return re.split(r'[\\/]', s.rstrip("\\/"))[-1].lower()
            t_full, t_leaf = title.rstrip("\\/").lower(), _leaf(title)
            for w in candidates:
                try:
                    doc_w = w.Document
                except Exception:
                    continue
                p = self._view_path(doc_w)
                if p and (p.rstrip("\\/").lower() == t_full or _leaf(p) == t_leaf):
                    return doc_w, len(candidates)

        # ── 3. 回退：选用「确实有选中项」的标签（仅需要选中项的功能可用）──
        if prefer_selected:
            for w in candidates:
                try:
                    doc_w = w.Document
                    if doc_w.SelectedItems().Count > 0:
                        return doc_w, len(candidates)
                except Exception:
                    continue

        return None, len(candidates)

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

            doc, n_tabs = self._resolve_active_view(fg_hwnd, prefer_selected=True)

            if doc is None and n_tabs == 0:
                self.list_widget.addItem("⚠️ 前台窗口不是资源管理器")
                return
            if doc is None:
                self.list_widget.addItem(
                    f"⚠️ 未选中任何文件夹，请先选中一个文件夹再按 {self._current_mkdir_key()}"
                    f"（检测到 {n_tabs} 个标签）"
                )
                return

            try:
                sel = doc.SelectedItems()
                count = sel.Count
            except Exception:
                self.list_widget.addItem("❌ 无法读取选中项")
                return

            if count == 0:
                self.list_widget.addItem(
                    f"⚠️ 未选中任何文件夹，请先选中一个文件夹再按 {self._current_mkdir_key()}"
                )
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
            # 目录感知：扫描同级同模式文件夹取最大编号 +1，跳过已存在的编号
            new_name    = self._next_available_folder_name(parent_dir, folder_name)
            new_path    = os.path.join(parent_dir, new_name)

            os.makedirs(new_path)
            self.list_widget.addItem(f"✅ 速建文件夹成功：{new_name}")
            self.list_widget.scrollToBottom()

        except Exception as e:
            self.list_widget.addItem(f"❌ 速建文件夹错误：{e}")

    def mkdir_direct_create_a(self):
        """F9 触发：新建名称 A（默认 Grok）的文件夹。"""
        self._mkdir_direct_create(self.mkdir_name, "Grok", "F9")

    def mkdir_direct_create_b(self):
        """F10 触发：新建名称 B（默认 Qwen）的文件夹。"""
        self._mkdir_direct_create(self.mkdir_name_b, "Qwen", "F10")

    def _mkdir_direct_create(self, name_edit, default_name: str, key_label: str):
        """在当前资源管理器活动标签内，仅当未选中任何项时，
        新建一个以 name_edit 内容命名的空文件夹。"""
        if not self.chk_mkdir.isChecked():
            self.list_widget.addItem("⚠️ 请先启用速建文件夹")
            return
        if not _WIN_OK:
            self.list_widget.addItem("❌ 功能不可用：缺少 pywin32")
            return
        name = name_edit.text().strip() or default_name
        # 清洗非法字符；若清洗后只剩下划线/空白（如输入了 "///"），回退默认名
        name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
        if not name.strip("_ "):
            name = default_name
        try:
            import win32com.client
            import win32gui

            fg_hwnd = win32gui.GetForegroundWindow()
            if not fg_hwnd:
                self.list_widget.addItem("⚠️ 无法获取前台窗口，请先点击资源管理器")
                return

            doc, n_tabs = self._resolve_active_view(fg_hwnd, prefer_selected=False)

            if doc is None and n_tabs == 0:
                self.list_widget.addItem("⚠️ 前台窗口不是资源管理器")
                return
            if doc is None:
                # 认不出当前活动标签：宁可不建，也不要建到错误的目录里
                diag = getattr(self, "_last_tab_diag", "无诊断")
                self.list_widget.addItem(f"⚠️ 无法确定当前标签，已取消新建")
                self.list_widget.addItem(f"🔍 诊断：{diag}；Shell.Windows 候选 {n_tabs} 个")
                self.list_widget.scrollToBottom()
                self._log_problem(f"🔍 {key_label} 定位失败：{diag}；候选 {n_tabs} 个")
                return

            # 仅在“未选中任何项”时才直接新建
            try:
                count = doc.SelectedItems().Count
            except Exception:
                count = 0
            if count > 0:
                self.list_widget.addItem(
                    f"ℹ️ 已选中 {count} 项，{key_label} 直接新建仅在未选中任何项时生效"
                )
                return

            # 取当前活动标签所在目录
            cur_dir = self._view_path(doc)
            if not cur_dir or not os.path.isdir(cur_dir):
                self.list_widget.addItem(
                    f"⚠️ 无法确定当前文件夹｜取到的路径={cur_dir!r}｜doc={type(doc).__name__}"
                )
                self.list_widget.scrollToBottom()
                return

            new_path = self._unique_path(os.path.join(cur_dir, name))
            os.makedirs(new_path)
            self.list_widget.addItem(f"✅ 直接新建成功：{new_path}")
            self.list_widget.scrollToBottom()

        except Exception as e:
            self.list_widget.addItem(f"❌ 直接新建错误：{e}")

    def closeEvent(self, e):
        self.stop_background_checks()
        self._unregister_txt_hotkey()
        self._unregister_mkdir_hotkey()
        super().closeEvent(e)

    def stop_background_checks(self):
        """主窗口真正关闭时调用（见 ui_main.py MainWindow.closeEvent）。
        本页面是嵌在 QStackedWidget 里的子页面，Qt 不会对它单独触发 closeEvent，
        所以之前那个 closeEvent 里的清理其实从没被执行过——这才是报错的根本原因。
        这里先置位 _closing 挡住新的检测线程，再停掉定时器；已经在跑的检测线程
        自己也会在 _do_check / _set_plugin_ui 里检查这个标志位，安全退出。"""
        if self._closing:
            return
        self._closing = True
        try:
            self._nm_check_timer.stop()
        except Exception:
            pass
        try:
            self._imgonly_timer.stop()
        except Exception:
            pass

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
