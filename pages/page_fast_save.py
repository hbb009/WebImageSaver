# ==================== 标准库 ====================
import os
import re
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
VK_CODE   = {"F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77}

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
_WS_PORT    = 19876
_ws_clients = set()
_ws_lock    = threading.Lock()

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
    try:
        if not _ws_handshake(conn): return
        with _ws_lock: _ws_clients.add(conn)
        while _ws_recv(conn) is not None: pass
    except: pass
    finally:
        with _ws_lock: _ws_clients.discard(conn)
        try: conn.close()
        except: pass

def _ws_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", _WS_PORT))
    srv.listen(10)
    srv.settimeout(1.0)
    while True:
        try:
            conn, _ = srv.accept()
            threading.Thread(target=_ws_client, args=(conn,), daemon=True).start()
        except socket.timeout: continue
        except: break

def _ws_trigger(log_cb=None):
    with _ws_lock: clients = list(_ws_clients)
    if not clients:
        if log_cb: log_cb("⚠️ 插件未连接")
        return
    for c in clients:
        try: _ws_send(c, "TRIGGER")
        except:
            with _ws_lock: _ws_clients.discard(c)

def _ws_connected():
    with _ws_lock: return len(_ws_clients) > 0

threading.Thread(target=_ws_server, daemon=True).start()






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


# ═══════════════════════════════════════════════════════════════
# PageFastSave
# ═══════════════════════════════════════════════════════════════
class PageFastSave(QWidget):
    STATE_IDLE    = 0
    STATE_IMGSAVE = 1

    log_sig     = pyqtSignal(str)

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

        # ── 左：速存图片 ──
        gb_img  = QGroupBox("速存图片")
        gb_img.setProperty("titleVariant", "accent")
        gb_img.setObjectName("CardFastAuto")
        img_box = QVBoxLayout(gb_img)
        img_box.setSpacing(3)
        img_box.setContentsMargins(8, 4, 8, 4)

        self.chk_imgonly = QCheckBox("启用速存图片")
        img_box.addWidget(self.chk_imgonly)

        # 插件状态（紧凑单行）
        self.lbl_nm_status = QLabel("● 插件：检测中...")
        self._typo(self.lbl_nm_status, "muted")
        img_box.addWidget(self.lbl_nm_status)

        # 快捷键（单行）
        row_kb = QHBoxLayout()
        row_kb.setSpacing(4)
        row_kb.addWidget(QLabel("快捷键"))
        self.combo_img_hotkey = QComboBox()
        self.combo_img_hotkey.setObjectName("FastSaveHotkey")
        self.combo_img_hotkey.addItems(["Alt+1", "Alt+2", "Alt+3", "Ctrl+1", "Ctrl+2", "Ctrl+3"])
        self.combo_img_hotkey.setCurrentText("Alt+1")
        self.combo_img_hotkey.setFixedWidth(100)
        row_kb.addWidget(self.combo_img_hotkey)
        row_kb.addStretch(1)
        img_box.addLayout(row_kb)

        # ── 右：速存文本 ──
        gb_txt  = QGroupBox("速存文本")
        gb_txt.setProperty("titleVariant", "accent")
        gb_txt.setObjectName("CardFastManual")
        txt_box = QVBoxLayout(gb_txt)
        txt_box.setSpacing(3)
        txt_box.setContentsMargins(8, 4, 8, 4)

        self.chk_manual = QCheckBox("启用速存文本")
        txt_box.addWidget(self.chk_manual)

        txt_box.addWidget(QLabel("文本快捷键"))
        self._txt_hotkey_group = QButtonGroup(self)
        row_radios = QHBoxLayout()
        row_radios.setSpacing(4)
        self._txt_radio = {}
        for key in ["F5", "F6", "F7", "F8"]:
            rb = QRadioButton(key)
            self._txt_radio[key] = rb
            self._txt_hotkey_group.addButton(rb)
            row_radios.addWidget(rb)
        self._txt_radio["F7"].setChecked(True)
        row_radios.addStretch(1)
        txt_box.addLayout(row_radios)

        lbl_hint = QLabel("（全局热键，在资源管理器操作即可生效）")
        lbl_hint.setWordWrap(True)
        self._typo(lbl_hint, "muted")
        txt_box.addWidget(lbl_hint)

        row_top.addWidget(gb_img)
        row_top.addWidget(gb_txt)
        row_top.setStretch(0, 1)
        row_top.setStretch(1, 1)

        # ══════════ 路径 ══════════
        row_p = QHBoxLayout()
        row_p.setSpacing(4)
        self.label_path = QLabel("保存路径：")
        self.save_path      = QLineEdit("")
        self.btn_choose_dir = QPushButton("另选目录")
        self.btn_choose_dir.setFixedWidth(72)
        row_p.addWidget(self.label_path)
        row_p.addWidget(self.save_path)
        row_p.addWidget(self.btn_choose_dir)
        lay.addLayout(row_p)

        # ══════════ 日志列表（占满剩余空间） ══════════
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("FastSaveList")
        self.list_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setUniformItemSizes(True)
        lay.addWidget(self.list_widget, 1)

        # ══════════ 信号与槽 ══════════
        self.log_sig.connect(self._append_log)
        self.btn_choose_dir.clicked.connect(self._choose_dir)
        self.chk_imgonly.toggled.connect(self._on_imgonly_toggled)
        self.chk_manual.toggled.connect(self._on_manual_toggled)
        self.combo_img_hotkey.currentTextChanged.connect(self._on_img_hotkey_changed)
        self._txt_hotkey_group.buttonClicked.connect(self._on_txt_hotkey_changed)
        self.save_path.textChanged.connect(self._on_path_edited)

        # ══════════ 状态 ══════════
        # 目录监控：显示插件保存过来的新文件
        self._imgonly_seen  = set()
        self._imgonly_lock  = threading.Lock()
        self._imgonly_timer = QTimer(self)
        self._imgonly_timer.setInterval(1000)
        self._imgonly_timer.timeout.connect(self._scan_imgonly_files)
        self._suppress_existing_until = 0.0

        # 心跳：每2秒检测插件是否已连接
        self._nm_check_timer = QTimer(self)
        self._nm_check_timer.setInterval(2000)
        self._nm_check_timer.timeout.connect(self._update_nm_status)
        self._nm_check_timer.start()
        QTimer.singleShot(500, self._update_nm_status)

        # 鼠标侧键钩子（suppress + 触发插件保存）


        # 速存文本热键
        self._hotkey_id              = 0x1002
        self._hotkey_filter          = None
        self._hotkey_registered_key  = None

        self._sc_manual = QShortcut(QKeySequence(self._current_txt_key()), self)
        self._sc_manual.activated.connect(self.manual_fast_save)
        self._sc_manual.setEnabled(False)

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
    def is_any_active(self):  return self.is_img_active() or self.is_txt_active()

    # ────────────────────────────────────────
    # 速存图片：触发逻辑
    # ────────────────────────────────────────
    def _update_nm_status(self):
        """更新插件连接状态"""
        if _ws_connected():
            self.lbl_nm_status.setText("● 插件：已连接 ✓")
            self.lbl_nm_status.setStyleSheet("color: #4caf50; font-weight: bold;")
        else:
            self.lbl_nm_status.setText("● 插件：未连接（请确认已安装插件且 Chrome 已打开）")
            self.lbl_nm_status.setStyleSheet("color: #888;")


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
                self.list_widget.addItem("⚠️ 保存路径不可用，已取消速存图片")
                return

            self._prime_seen_and_quiet()
            self._imgonly_timer.start()


            self.state = self.STATE_IMGSAVE
            self.list_widget.addItem("🟢 速存图片：已启用")
            self.list_widget.addItem(f"📁 图片将保存至：{self._get_plugin_save_dir()}")
        else:
            self._imgonly_timer.stop()
            self.state = self.STATE_IDLE
            self.list_widget.addItem("⏹️ 速存图片：已关闭")

    def _on_img_hotkey_changed(self, key: str):
        if self.state == self.STATE_IMGSAVE:
            self.list_widget.addItem(f"ℹ️ 键盘快捷键已切换为：{key}（请在 chrome://extensions/shortcuts 同步更新）")



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

    def _scan_imgonly_files(self):
        """每秒扫描插件的保存目录（下载目录/WebImageSaver），有新图片就显示在日志里。"""
        try:
            scan_dir = self._get_plugin_save_dir()
            if not os.path.isdir(scan_dir):
                return
            exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg", ".avif", ".ico"}
            for name in sorted(os.listdir(scan_dir)):
                if name.endswith(".crdownload"):
                    continue
                if os.path.splitext(name)[1].lower() not in exts:
                    continue
                with self._imgonly_lock:
                    already = name in self._imgonly_seen
                    if not already:
                        self._imgonly_seen.add(name)
                if not already and time.time() >= self._suppress_existing_until:
                    self.list_widget.addItem(f"✅ 已保存图片：{name}")
                    self.list_widget.scrollToBottom()
        except Exception as e:
            self.list_widget.addItem(f"❌ 目录扫描错误：{e}")

    def _prime_seen_and_quiet(self, scan_dir=None):
        """启动时把插件保存目录里已有的图片标记为已知，避免误报。"""
        try:
            if scan_dir is None:
                scan_dir = self._get_plugin_save_dir()
            exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg", ".avif", ".ico"}
            names = set()
            if os.path.isdir(scan_dir):
                for n in os.listdir(scan_dir):
                    if os.path.splitext(n)[1].lower() in exts:
                        names.add(n)
            with self._imgonly_lock:
                self._imgonly_seen = names
            self._suppress_existing_until = time.time() + 2.0
        except Exception:
            pass

    # ────────────────────────────────────────
    # 速存文本
    # ────────────────────────────────────────
    def _current_txt_key(self) -> str:
        for key, rb in self._txt_radio.items():
            if rb.isChecked():
                return key
        return "F7"

    def _on_txt_hotkey_changed(self, _=None):
        key = self._current_txt_key()
        if hasattr(self, "_sc_manual"):
            self._sc_manual.setKey(QKeySequence(key))
        if self.chk_manual.isChecked():
            self.list_widget.addItem(f"⌨️ 文本快捷键切换为：{key}")
            self._register_txt_hotkey()

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
        vk = VK_CODE.get(key, 0x76)
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
            self._prime_seen_and_quiet(self.save_path.text().strip())

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

    def closeEvent(self, e):
        self._unregister_txt_hotkey()
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
