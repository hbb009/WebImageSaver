# ==================== 标准库 ====================
import errno
import os
import shutil
import threading  # 侧键全局钩子用到线程与消息循环
import time       # 追踪“注入后等待下载”的超时窗口
import hashlib
from datetime import datetime

# ==================== 第三方：PyQt5 ====================
from PyQt5.QtCore import (
    Qt,
    QBuffer,
    QIODevice,
    QStandardPaths,
    QTimer,
    pyqtSignal,
    QAbstractNativeEventFilter,
    QCoreApplication,
    QMetaObject,
    Q_ARG,
)
from PyQt5.QtGui import QPixmap, QKeySequence, QGuiApplication, QCursor
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QShortcut,
    QComboBox,
    QTabWidget,
    QStackedWidget,
)

# ==================== 本地模块 ====================
from styles.common_styles import TEXT_STYLE, BUTTON_STYLE, LINEEDIT_STYLE

# ==================== Windows API ====================
import ctypes
import ctypes.wintypes as wintypes

# === 兼容：部分 Python 发行版没有 wintypes.LRESULT / wintypes.INT ===
try:
    LRESULT = wintypes.LRESULT        # 优先用系统自带
except AttributeError:
    LRESULT = ctypes.c_long if ctypes.sizeof(ctypes.c_void_p) == 4 else ctypes.c_longlong

try:
    INT = wintypes.INT
except AttributeError:
    INT = ctypes.c_int

# === 指针同位宽的 WPARAM/LPARAM/ULONG_PTR ===
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

# === 兼容：部分发行版没有 wintypes.ULONG_PTR ===
try:
    ULONG_PTR = wintypes.ULONG_PTR
except AttributeError:
    # 32 位用 unsigned long，64 位用 unsigned long long
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

# === 兼容：WPARAM/LPARAM 必须与指针同位宽（64 位要用 64 位）===
try:
    WPARAM = wintypes.WPARAM
except AttributeError:
    WPARAM = ctypes.c_size_t
try:
    LPARAM = wintypes.LPARAM
except AttributeError:
    LPARAM = ctypes.c_ssize_t
# 强制修正：部分 Python 把它们定义成了 32 位，手动按指针位宽纠正
if ctypes.sizeof(WPARAM) != ctypes.sizeof(ctypes.c_void_p):
    WPARAM = ctypes.c_size_t
if ctypes.sizeof(LPARAM) != ctypes.sizeof(ctypes.c_void_p):
    LPARAM = ctypes.c_ssize_t

WM_HOTKEY = 0x0312
VK_CODE = {"F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77}

# 手动速存依赖（仅在 Windows 下可用）
try:
    import pythoncom
    import win32com.client
    import pyperclip
    _WIN_OK = True
except Exception:
    _WIN_OK = False

from utils.file_utils import ensure_dir

def _safe_move(src: str, dst: str) -> bool:
    """
    优先用 os.replace()（同盘瞬移）；若跨盘/跨设备失败，则退回 copy2 + 删除。
    返回 True 表示已成功把文件放到 dst；可能覆盖同名文件。
    """
    try:
        os.replace(src, dst)
        return True
    except OSError as e:
        # EXDEV（跨设备）或常见跨盘错误 -> 用复制 + 删除 兜底
        if getattr(e, "errno", None) == errno.EXDEV or getattr(e, "winerror", None) in (17, 18):
            try:
                ensure_dir(os.path.dirname(dst))
                shutil.copy2(src, dst)
                try:
                    os.remove(src)  # 复制成功后删除源；若删除失败不影响最终结果
                except Exception:
                    pass
                return True
            except Exception:
                return False
        # 其它错误（如 32: 被占用）交给上层原有逻辑处理
        raise

# 共享队列（由 utils.server 推入）
_SHARED_QUEUE = []

class _GlobalHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, trigger_cb, hotkey_id):
        super().__init__()
        self.trigger_cb = trigger_cb
        self.hotkey_id = hotkey_id

    def nativeEventFilter(self, eventType, message):
        if eventType != "windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
            self.trigger_cb()
            return True, 0
        return False, 0

# =========================
# 全局侧键钩子（仅 Windows）
# =========================
class _GlobalSideButtonHook(threading.Thread):
    """
    仅做：被动监听全局键盘；当检测到 Alt+1 时，回调 on_trigger()。
    不安装鼠标钩子；不注入按键；不做任何复制/右键菜单操作。
    """
    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_SYSKEYDOWN = 0x0104

    # 键码
    VK_CONTROL = 0x11
    VK_MENU    = 0x12  # Alt
    VK_1       = 0x31  # 顶排数字 1
    VK_ADD     = 0x6B  # Numpad +（这版不再使用，仅留映射）

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    def __init__(self):
        super().__init__(daemon=True)
        self._user32 = ctypes.windll.user32

        # —— 关键：修正 WinAPI 函数签名（避免 64 位下 lParam 溢出）——
        HHOOK_T = getattr(wintypes, "HHOOK", wintypes.HANDLE)  # py3.11 无 HHOOK，则退回 HANDLE
        self._user32.CallNextHookEx.argtypes = [HHOOK_T, ctypes.c_int, WPARAM, LPARAM]
        self._user32.CallNextHookEx.restype  = LRESULT
        self._user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
        self._user32.SetWindowsHookExW.restype  = HHOOK_T

        self._kernel32 = ctypes.windll.kernel32
        self._kb_hook = None
        self._running = threading.Event()
        self._thread_id = None

        # 外部回调：一个负责把文本加到列表；一个负责“会话触发”
        self.on_event   = None   # def(text)
        self.on_trigger = None   # def(trigger_str)  —— 收到 Alt+1 时调用

        # 预声明 SendInput 原型（虽然本类不用，但保留兼容字段）
        self._user32.SendInput.restype  = wintypes.UINT

    def start_hook(self):
        if self.is_alive():
            self._running.set(); return
        self._running.set(); self.start()

    def stop_hook(self):
        self._running.clear()
        try:
            if self._kb_hook:
                self._user32.UnhookWindowsHookEx(self._kb_hook)
                self._kb_hook = None
            if self._thread_id:
                self._user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        except Exception:
            pass

    # 实时读修饰键状态
    def _mods_str(self) -> str:
        GetKeyState = self._user32.GetKeyState
        def down(vk): return GetKeyState(vk) < 0
        parts = []
        if down(self.VK_CONTROL): parts.append("Ctrl")
        if down(0x10):            parts.append("Shift")
        if down(self.VK_MENU):    parts.append("Alt")
        return "+".join(parts)

    def _notify(self, text: str):
        try:
            if callable(self.on_event): self.on_event(text)
        except Exception: pass

    def run(self):
        self._thread_id = self._kernel32.GetCurrentThreadId()

        @ctypes.WINFUNCTYPE(LRESULT, INT, WPARAM, LPARAM)
        def low_level_keyboard_proc(nCode, wParam, lParam):
            try:
                if nCode == 0 and self._running.is_set() and wParam in (self.WM_KEYDOWN, self.WM_SYSKEYDOWN):
                    kb = ctypes.cast(lParam, ctypes.POINTER(self.KBDLLHOOKSTRUCT)).contents
                    vk = int(kb.vkCode)

                    # 仅当 Alt+1 时，触发一次“会话开始”
                    if vk == self.VK_1:
                        mods = self._mods_str()
                        if mods == "Alt":  # 仅 Alt，无 Ctrl/Shift
                            self._notify("⌨️ 触发：Alt+1")
                            if callable(self.on_trigger):
                                self.on_trigger("Alt+1")

            except Exception:
                pass
            return self._user32.CallNextHookEx(self._kb_hook, nCode, wParam, lParam)

        # 安装键盘钩子
        self._kb_hook = self._user32.SetWindowsHookExW(self.WH_KEYBOARD_LL, low_level_keyboard_proc, 0, 0)
        self._notify("🟢 键盘监听就绪（Alt+1）" if self._kb_hook else f"❌ 键盘监听失败 (err={self._kernel32.GetLastError()})")

        # 消息循环
        msg = wintypes.MSG()
        while self._running.is_set() and self._user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))

        try:
            if self._kb_hook: self._user32.UnhookWindowsHookEx(self._kb_hook)
        except Exception: pass
        self._kb_hook = None

class PageFastSave(QWidget):
    STATE_IDLE = 0
    STATE_AUTO = 1
    STATE_MANUAL = 2
    # 跨线程日志信号（钩子线程 -> UI 线程）
    log_sig = pyqtSignal(str)
    op_begin_sig = pyqtSignal(str)  # 中文注释：钩子线程→主线程；触发“步骤1～4”的会话起点

    # 钩子线程 -> UI 线程：通知主线程去保存剪贴板图片
    copy_sig = pyqtSignal()

    @staticmethod
    def _typo(widget, name):
        widget.setProperty("typo", name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)

        # ===== 顶部两侧分组：自动 / 手动 =====
        row_top = QHBoxLayout()
        lay.addLayout(row_top)

        # 左：自动
        gb_auto = QGroupBox("图文自动保存")
        gb_auto.setProperty("titleVariant", "accent")  # 模板：浅蓝标题 + 18px 字号
        gb_auto.setObjectName("CardFastAuto")
        auto_box = QVBoxLayout(gb_auto)

        # 第1行：启用自动（保持原有样式）
        row_auto_line = QHBoxLayout()
        self.chk_auto = QCheckBox("启用自动")
        row_auto_line.addWidget(self.chk_auto)
        row_auto_line.addStretch(1)
        auto_box.addLayout(row_auto_line)

        # ✅ 自动保存：说明文字
        self.label_auto_hint = QLabel(
            '提示：推荐在浏览器里直接用"⚡ 速存图片：已开启（Alt+1）"保存图片；如需，也可安装配套扩展以增强兼容性（可选）。'
        )

        self.label_auto_hint.setWordWrap(True)                 # 开启自动换行，避免溢出
        self._typo(self.label_auto_hint, "muted")              # // 插入：套用“蓝框同款” muted 文本样式（更柔和的小号字）
        auto_box.addWidget(self.label_auto_hint)               # 保持原有布局

        # 右：速存图片（新增只存图开关）+ 保留原“图文手动（F7）”
        gb_manual = QGroupBox("速存图片")                 # 中文注释：原标题“图文手动保存”→“速存图片”
        gb_manual.setProperty("titleVariant", "accent")
        gb_manual.setObjectName("CardFastManual")
        manual_box = QVBoxLayout(gb_manual)

        # --- [新增] 速存图片（鼠标侧键）开关 ---
        row_imgonly_line = QHBoxLayout()
        self.chk_imgonly = QCheckBox("启用速存图片（扩展 Alt+1）")   # 勾选后启动侧键钩子 + 定时扫描
        row_imgonly_line.addWidget(self.chk_imgonly)
        row_imgonly_line.addStretch(1)
        manual_box.addLayout(row_imgonly_line)

        # --- [新增] 速存图片说明 ---
        self.label_imgonly_hint = QLabel(
            "在浏览器图片上按鼠标侧键（或按 Alt+1）即可快速保存到“图文保存路径”，程序只记录图片文件，不生成 .txt。"
        )

        self.label_imgonly_hint.setWordWrap(True)
        self._typo(self.label_imgonly_hint, "muted")
        manual_box.addWidget(self.label_imgonly_hint)

        # 下面继续保留你原有的“手动（F7）”控件（即：第一行启用手动 + 快捷键下拉等）

        # 第一行：启用手动 + 快捷键下拉
        row_manual_line = QHBoxLayout()
        self.chk_manual = QCheckBox("速存文本")  # 中文注释：仅改显示文字
        self.chk_manual.hide()  # 中文注释：隐藏复选框；F7 的启用/禁用由“速存图片”开关统一控制

        # 下拉选择快捷键：F5~F8（默认 F7）
        self.combo_manual_hotkey = QComboBox()
        self.combo_manual_hotkey.setObjectName("FastSaveHotkey")  # 供 app.qss 精准样式

        self.combo_manual_hotkey.addItems(["F5", "F6", "F7", "F8"])
        self.combo_manual_hotkey.setCurrentText("F7")
        self.combo_manual_hotkey.setFixedWidth(90)

        lbl_hotkey_tip = QLabel("文本快捷键")
        lbl_hotkey_tip.setObjectName("CalcFieldLabel")
        row_manual_line.addWidget(lbl_hotkey_tip)
        row_manual_line.addWidget(self.combo_manual_hotkey)
        row_manual_line.addStretch(1)
        manual_box.addLayout(row_manual_line)  # ★ 使用上面创建的 manual_box

        # ✅ 手动保存：说明文字
        self.label_manual_hint = QLabel(
            "在资源管理器选中文件后，按所选快捷键即可新建同名 .txt 并写入剪贴板文本（快捷键可改为 F5～F8，默认 F7）"
        )
        self.label_manual_hint.setWordWrap(True)               # 开启自动换行
        self._typo(self.label_manual_hint, "muted")            # // 插入：同样使用 muted 样式，风格与蓝框一致
        manual_box.addWidget(self.label_manual_hint)           # 保持原有布局

        row_top.addWidget(gb_auto)
        row_top.addWidget(gb_manual)
        row_top.setStretch(0, 1)
        row_top.setStretch(1, 1)

        # ===== 中下：共享（蓝色区域） 路径 + 日志 =====
        # 路径行
        row_path_title = QHBoxLayout(); lay.addLayout(row_path_title)
        self.label_path = QLabel("图文保存路径：")
        self._typo(self.label_path, "h3")   # 使用全局QSS的“h3”文字样式；_typo 会给控件设置属性 typo="h3" 并刷新样式

        row_path_title.addWidget(self.label_path)
        row_path_title.addStretch(1)

        row_path = QHBoxLayout(); lay.addLayout(row_path)
        self.save_path = QLineEdit("")  # 由 _init_save_dir 自行解析并填充
        self.btn_choose_dir = QPushButton("另选目录")
        row_path.addWidget(self.save_path)
        row_path.addWidget(self.btn_choose_dir)

        # 日志列表
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("FastSaveList")
        self.list_widget.setMinimumHeight(200)
        self.list_widget.setAttribute(Qt.WA_StyledBackground, True)

        # ↓ 关键：固定滚动条，避免宽度在悬停时变化而引发抖动
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setUniformItemSizes(True)

        lay.addWidget(self.list_widget)
        self.log_sig.connect(self._append_log)
        # 中文注释：跨线程触发会话，用于在列表稳定输出“步骤1~4”
        self.op_begin_sig.connect(self._op_begin)
        self.copy_sig.connect(self._save_clipboard_image_delayed)  # 复制完成 → 主线程延迟落盘

        # ===== 信号与状态 =====
        self.btn_choose_dir.clicked.connect(self._choose_dir)
        self.chk_auto.toggled.connect(self._on_auto_toggled)
        self.chk_manual.toggled.connect(self._on_manual_toggled)

        # --- [新增] 只存图：扫描器 + 已处理集合 ---
        self._imgonly_seen = set()           # 已处理的 imgonly_* 文件，防重复
        self._imgonly_timer = QTimer(self)   # 每秒扫一次“初始路径/保存路径”
        self._imgonly_timer.setInterval(1000)
        self._imgonly_timer.timeout.connect(self._scan_imgonly_files)

        self._pending_moves = {}  # ← 新增：{src_path: {"tries": 0}}

        # —— 本次操作会话（每次收到下载指令后开启会话）——
        # 结构：{"started_at": float, "deadline": float, "found": bool, "src": str|None}
        self._op = None

        # 追踪：注入 Numpad+ 后等待扩展下文件（≤5s）
        self._await_deadline = 0.0   # >0 表示等待窗口截止时间戳（time.time()）
        self._await_seen = False     # 已看到下载目录出现新文件
        self._dl_sub = ""            # 记录“下载/WebImageSaver”的真实路径（自检/提示用）
        self._suppress_existing_until = 0.0  # 切换保存目录后，在此时间点前静默“已保存”旧文件日志

        # 只存图：侧键全局钩子
        self._side_hook = _GlobalSideButtonHook()
        self._side_hook.on_event   = self._input_echo       # 仅作轻量回显
        self._side_hook.on_trigger = lambda trig: self.op_begin_sig.emit(trig)  # 中文注释：跨线程安全触发会话

        # --- [新增] 只存图：开关信号
        self.chk_imgonly.toggled.connect(self._on_imgonly_toggled)

        self.combo_manual_hotkey.currentTextChanged.connect(self._on_manual_hotkey_changed)

        # 路径文本变化时做轻量校验（不弹窗）
        self.save_path.textChanged.connect(self._on_path_edited)

        # 初始化一次默认可写目录（自愈）
        self._init_save_dir()

        # 页面内“手动速存”快捷键：跟随下拉选择
        self._sc_manual = QShortcut(QKeySequence(self.combo_manual_hotkey.currentText()), self)
        self._sc_manual.activated.connect(self.manual_fast_save)
        self._sc_manual.setEnabled(False)

        # 剪贴板
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self._check_clipboard)

        # 自动模式配对辅助
        self.last_saved_image = ""
        self._last_img_sig = None

        self._hotkey_id = 0x1001
        self._hotkey_filter = None

        self._hotkey_registered_key = None  # 记录已注册的热键，防止重复日志

        # 初始空闲
        self._enter_idle(reset_switches=True)

    # ===== 对外：供 Flask 推送使用 =====
    @staticmethod
    def shared_queue():
        return _SHARED_QUEUE

    def allow_accept(self):
        # 仅在自动模式下允许服务端推送接收
        return self.chk_auto.isChecked()

    def drain_queue(self):
        if not self.chk_auto.isChecked():
            return
        while _SHARED_QUEUE:
            item = _SHARED_QUEUE.pop(0)
            if item.get("type") == "image":
                self.list_widget.addItem(f"🖼️ 插件保存: {item.get('filename')}")
                self.last_saved_image = item.get('filename', '')

    def _register_global_hotkey(self, announce: bool = True):
        key = getattr(self, "_current_manual_key", lambda: "F7")()
        # 已经是同一个键，直接返回，避免重复日志
        if getattr(self, "_hotkey_registered_key", None) == key:
            return True

        # 重新注册
        self._unregister_global_hotkey()
        vk = VK_CODE.get(key, 0x76)
        ok = ctypes.windll.user32.RegisterHotKey(None, self._hotkey_id, 0x0000, vk)
        if not ok:
            try:
                self.list_widget.addItem(f"❌ 注册全局热键 {key} 失败，可能被占用")
            except Exception:
                pass
            self._hotkey_registered_key = None
            return False

        if self._hotkey_filter is None:
            self._hotkey_filter = _GlobalHotkeyFilter(self.manual_fast_save, self._hotkey_id)
            QCoreApplication.instance().installNativeEventFilter(self._hotkey_filter)

        self._hotkey_registered_key = key
        if announce:
            try:
                self.list_widget.addItem(f"🟡 全局热键已就绪：{key}")
            except Exception:
                pass
        return True

    def _unregister_global_hotkey(self):
        try:
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
        finally:
            self._hotkey_registered_key = None

    # ===== 互斥状态切换 =====
    def _on_auto_toggled(self, checked: bool):
        # 自动 与 速存图片 互斥
        if checked:
            # 先关“速存图片”
            if self.chk_imgonly.isChecked():
                self._block_switches(True)
                self.chk_imgonly.setChecked(False)
                self._block_switches(False)

            if not self._require_writable_path(interactive=True):
                self._block_switches(True); self.chk_auto.setChecked(False); self._block_switches(False)
                self.list_widget.addItem("⚠️ 保存路径不可用，已取消自动模式")
                return
            self._enter_auto()
        else:
            # 自动关闭后，如速存图片也没开，则进空闲
            if not self.chk_imgonly.isChecked():
                self._enter_idle()

    def _on_manual_toggled(self, checked: bool):
        if checked:
            if not self._require_writable_path(interactive=True):
                self._block_switches(True); self.chk_manual.setChecked(False); self._block_switches(False)
                self.list_widget.addItem("⚠️ 保存路径不可用，已取消手动模式")
                return
            self._enter_manual()
        else:
            if not self.chk_auto.isChecked():
                self._enter_idle()

    def _enter_idle(self, reset_switches: bool = False):
        """进入空闲：
        1) 可选复位所有开关（包含“速存图片”）
        2) 关闭页内 QShortcut + 注销全局热键
        3) 停止只存图扫描与侧键钩子
        """
        if reset_switches:
            self._block_switches(True)
            try:
                if hasattr(self, "chk_auto"):
                    self.chk_auto.setChecked(False)
                if hasattr(self, "chk_manual"):
                    self.chk_manual.setChecked(False)
                if hasattr(self, "chk_imgonly"):
                    self.chk_imgonly.setChecked(False)
            finally:
                self._block_switches(False)

        # 关闭页内 QShortcut（若存在）
        try:
            if hasattr(self, "_sc_manual") and self._sc_manual:
                self._sc_manual.setEnabled(False)
        except Exception:
            pass

        # 状态与全局热键复位
        self.state = self.STATE_IDLE
        self._unregister_global_hotkey()

        # 停止“速存图片”定时扫描与侧键钩子（若存在）
        try:
            if hasattr(self, "_imgonly_timer") and self._imgonly_timer:
                self._imgonly_timer.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "_side_hook"):
                self._side_hook.stop_hook()
        except Exception:
            pass

        # 日志
        try:
            self.list_widget.addItem("⏹️ 已停止保存（空闲）")
        except Exception:
            pass

    def _enter_auto(self):
        # 互斥：关手动
        self._block_switches(True)
        self.chk_manual.setChecked(False)
        self._block_switches(False)

        self._sc_manual.setEnabled(False)
        self.state = self.STATE_AUTO
        self.list_widget.addItem("🟢 自动保存进行中…")
        self._unregister_global_hotkey()

    def _enter_manual(self):
        # 互斥：关自动
        self._block_switches(True)
        self.chk_auto.setChecked(False)
        self._block_switches(False)

        self._sc_manual.setEnabled(True)
        self.state = self.STATE_MANUAL
        key = self._current_manual_key()
        if not _WIN_OK:
            self.list_widget.addItem("⚠️ 手动模式依赖 pywin32/pyperclip，当前不可用")
        else:
            # 合并为一句提示
            self.list_widget.addItem(f"🟡 手动模式已启用（按 {key} 创建同名 .txt）")

        # 注册全局热键，但不再额外打印“全局热键已就绪”
        self._register_global_hotkey(announce=False)

    # ==== 侧键复制完成 → 从剪贴板取图并保存 ====
    def _on_copy_request(self):
        """来自钩子后台线程的回调：不要在这里用 QTimer，转成信号进主线程"""
        try:
            self.copy_sig.emit()
        except Exception:
            pass

    def _save_clipboard_image_delayed(self):
        """已经在主线程：这里再用 QTimer 做 120ms 延迟，然后调用真正落盘"""
        try:
            QTimer.singleShot(120, self._save_clipboard_image)
        except Exception:
            # 理论上不会触发；只是兜底
            self.list_widget.addItem("❌ 定时器创建失败（主线程）")

    def _save_clipboard_image(self):
        try:
            save_dir = self.save_path.text().strip()
            if not save_dir or not os.path.isdir(save_dir):
                self.list_widget.addItem("❌ 保存失败：路径不可用")
                return

            # 轻量重试：最多 6 次，每次 80ms，兼容浏览器把位图放入剪贴板的延迟
            img = None
            for _ in range(6):
                tmp = self.clipboard.image()
                if not tmp.isNull():
                    img = tmp
                    break
                QTimer.singleShot(0, lambda: None)  # 让出事件循环
                ctypes.windll.kernel32.Sleep(80)

            if not img or img.isNull():
                # —— 后备模式：做光标附近区域截图 —— #
                pix = self._fallback_capture_region()
                if pix is None or pix.isNull():
                    self.list_widget.addItem("❌ 未检测到剪贴板图像（可能未点中图片或站点禁用复制）")
                    return
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                name = f"imgonly_snap_{ts}.png"
                full = os.path.join(save_dir, name)
                if pix.save(full, "PNG"):
                    self._imgonly_seen.add(name)
                    self.list_widget.addItem(f"🖼️ 复制失败，已改用区域截图: {name}")
                else:
                    self.list_widget.addItem("❌ 保存失败：写入 PNG 失败")
                return

            # 复制成功 → 从剪贴板保存
            pix = QPixmap.fromImage(img)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            name = f"imgonly_{ts}.png"
            full = os.path.join(save_dir, name)
            if pix.save(full, "PNG"):
                try:
                    self._imgonly_seen.add(name)   # 避免被扫描器重复记录
                except Exception:
                    pass
                self.list_widget.addItem(f"✅ 速存图片：已保存 {name} → {save_dir}")
            else:
                self.list_widget.addItem("❌ 保存失败：写入 PNG 失败")
        except Exception as e:
            self.list_widget.addItem(f"❌ 只存图异常：{e}")

    def _fallback_capture_region(self, w=480, h=480):
        """在光标附近截一块区域作为后备（不依赖站点或浏览器菜单）"""
        try:
            pos = QCursor.pos()
            # 找到光标所在屏幕
            screen = QGuiApplication.screenAt(pos)
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is None:
                return None
            geom = screen.geometry()
            x = max(geom.left(), min(pos.x() - w // 2, geom.right() - w + 1))
            y = max(geom.top(),  min(pos.y() - h // 2, geom.bottom() - h + 1))
            return screen.grabWindow(0, x, y, w, h)  # QPixmap
        except Exception:
            return None

    def _on_imgonly_toggled(self, checked: bool):
        """速存图片：开→关自动+装钩子+开扫描+开F7；关→卸钩子+停扫描+关F7"""
        try:
            save_dir = self.save_path.text().strip()
            ensure_dir(save_dir)

            if checked:
                # 互斥：先关“自动”
                if self.chk_auto.isChecked():
                    self._block_switches(True)
                    self.chk_auto.setChecked(False)
                    self._block_switches(False)

                # 扫描器：记录当前已存在的图片名，避免重复回显（不依赖前缀）
                exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg", ".avif", ".ico"}
                seen = set()
                # 目标保存目录
                for n in os.listdir(save_dir):
                    if n.lower().endswith(tuple(exts)) and not n.endswith(".crdownload"):
                        seen.add(n)
                # 下载目录/WebImageSaver
                dl = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or ""
                if dl and os.path.isdir(dl):
                    dl_sub = os.path.join(dl, "WebImageSaver")
                    if os.path.isdir(dl_sub):
                        for n in os.listdir(dl_sub):
                            if n.lower().endswith(tuple(exts)) and not n.endswith(".crdownload"):
                                seen.add(n)
                self._imgonly_seen = seen
                self._pending_moves = {}  # 开启时清空历史待搬运
                self._imgonly_timer.start()

                # 监控目录提示（便于核对扩展是否保存到相同子目录）
                dl = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or ""
                dl_sub = os.path.join(dl, "WebImageSaver") if dl else ""

                # 统一路径分隔符，并合并为一条清晰日志
                save_dir_disp = os.path.normpath(save_dir)                   # 例：C:\Users\...\Pictures\WebImageSaver
                dl_sub_disp   = os.path.normpath(dl_sub) if dl_sub else ""   # 例：C:\Users\...\Downloads\WebImageSaver

                if dl_sub_disp:
                    # 有扩展下载子目录 → 一条提示搞定
                    self.list_widget.addItem(f"📡 监控目录：{save_dir_disp}；扩展下载子目录：{dl_sub_disp}")
                else:
                    # 没有则明确说明将临时观察“下载”根目录 5s
                    self.list_widget.addItem(
                        f"📡 监控目录：{save_dir_disp}；扩展下载子目录：未检测到（本轮将临时观察“下载”根目录 5s）"
                    )

                # 记录下载子目录并自检
                self._dl_sub = dl_sub
                if not dl_sub or not os.path.isdir(dl_sub):
                    self.list_widget.addItem("🚫 检测不到下载子目录：下载/WebImageSaver（扩展应写入此处）")
                else:
                    self.list_widget.addItem("🧩 自检：下载子目录存在，可监控")

                # 侧键钩子：复用同一个实例并确保回调已绑定
                try:
                    if not getattr(self, "_side_hook", None):
                        self._side_hook = _GlobalSideButtonHook()
                    # 每次开启都重新绑定回调，保证 on_copy 不丢失
                    self._side_hook.on_event = self._input_echo
                    self._side_hook.start_hook()
                except Exception as e:
                    self.list_widget.addItem(f"❌ 速存图片开关错误: {e}")

                # —— 同时把“手动文本保存(F7)”一起开启 —— #
                self._sc_manual.setEnabled(True)
                self.state = self.STATE_MANUAL
                self._register_global_hotkey(announce=False)
                key = self._current_manual_key()
                self.list_widget.addItem("🖱️ 速存图片：已开启（鼠标侧键）")
                self.list_widget.addItem(f"🟡 手动文本保存：已启用（按 {key} 在资源管理器创建 .txt）")

            else:
                # 停扫描 + 卸钩子
                self._imgonly_timer.stop()
                if getattr(self, "_side_hook", None):
                    self._side_hook.stop_hook()

                # 关闭手动文本保存（除非你想保留，可改成不关闭）
                self._sc_manual.setEnabled(False)
                self._unregister_global_hotkey()
                self.state = self.STATE_IDLE if not self.chk_auto.isChecked() else self.STATE_AUTO

                self.list_widget.addItem("🖱️ 速存图片：已关闭")
        except Exception as e:
            self.list_widget.addItem(f"❌ 速存图片开关错误: {e}")

    def _scan_imgonly_files(self):
        """
        每秒扫描：
          1) 保存路径 save_dir
          2) 系统下载目录下的 WebImageSaver 子目录（若不存在且处于 5s 观察窗口，则临时观察下载根目录）
        新图片（按扩展名判断，排除 .crdownload）会被搬到保存路径；
        若被占用（Explorer 缩略图/预览/杀毒等）则进入重试队列。
        “步骤2/3/3a/4”始终输出，不再依赖 self._op。
        """
        try:
            save_dir = self.save_path.text().strip()
            if not save_dir:
                return

            # 组装要扫描的目录
            scan_dirs = []
            if os.path.isdir(save_dir):
                scan_dirs.append(save_dir)

            dl = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or ""
            dl_sub = os.path.join(dl, "WebImageSaver") if dl else ""
            watch_root = False
            if dl_sub and os.path.isdir(dl_sub):
                scan_dirs.append(dl_sub)
            else:
                # 注入后的 5s 内，临时观察下载根目录，帮助定位扩展是否落错位置
                if getattr(self, "_await_deadline", 0) and time.time() <= self._await_deadline and dl and os.path.isdir(dl):
                    scan_dirs.append(dl)
                    watch_root = True

            if not scan_dirs:
                return

            exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg", ".avif", ".ico"}

            # —— 1) 处理新文件 —— #
            for d in scan_dirs:
                for name in sorted(os.listdir(d)):
                    if name.endswith(".crdownload"):
                        continue
                    if os.path.splitext(name)[1].lower() not in exts:
                        continue

                    src = os.path.join(d, name)

                    # 已在保存目录且记过账 → 跳过
                    if name in self._imgonly_seen and d == save_dir:
                        continue

                    if d != save_dir:
                        # 发现新下载文件（从下载目录搬到保存目录）
                        base, ext = os.path.splitext(name)
                        dst = os.path.join(save_dir, name)
                        i = 1
                        while os.path.exists(dst):
                            dst = os.path.join(save_dir, f"{base}_{i}{ext}")
                            i += 1

                        where_label = (
                            "下载目录" if (dl_sub and os.path.normcase(d) == os.path.normcase(dl_sub))
                            else ("下载根目录" if (dl and os.path.normcase(d) == os.path.normcase(dl)) else "其它")
                        )
                        self.list_widget.addItem(f"🔎 发现新文件（{where_label}）：{name}")
                        self._op_step(f"🧩 步骤2：已检测到下载文件（{where_label}）：{name}")
                        self._op_step("🧩 步骤3：正在搬运到保存目录…")

                        self._await_seen = True
                        self._await_deadline = 0.0

                        try:
                            ensure_dir(save_dir)
                            if _safe_move(src, dst):
                                # 成功
                                self._op_step(f"🧩 步骤4：保存完成 → {save_dir}")
                                name = os.path.basename(dst)
                                self._imgonly_seen.add(name)
                                self.list_widget.addItem(f"✅ 速存图片：已保存 {name} → {save_dir}")
                                continue

                            # 失败但未抛异常 → 进入重试队列
                            self._pending_moves.setdefault(src, {"tries": 0})
                            self._op_step("🧩 步骤3a：文件暂不可搬运，进入重试")
                            self.list_widget.addItem(f"⏳ 文件暂不可搬运，等待释放：{os.path.basename(src)}")
                            continue

                        except OSError as e:
                            # WinError 32：文件被占用
                            if getattr(e, "winerror", None) == 32:
                                meta = self._pending_moves.setdefault(src, {"tries": 0})
                                tries = meta["tries"]
                                if tries == 0 or (tries % 5 == 0):
                                    self._op_step(f"🧩 步骤3a：文件被占用，重试中（第 {tries} 次）")
                                if tries == 0:
                                    self.list_widget.addItem(f"⏳ 文件被占用，等待释放：{name}")
                                continue
                            # 其它错误：忽略，下一轮再试
                            continue

                    else:
                        # 已在保存目录：记一次账；处于静默窗口内则不打印“已保存 …”
                        if name not in self._imgonly_seen:
                            self._imgonly_seen.add(name)
                            if time.time() >= getattr(self, "_suppress_existing_until", 0.0):
                                self.list_widget.addItem(f"✅ 速存图片：已保存 {name} → {save_dir}")

            # —— 2) 重试队列 —— #
            if self._pending_moves:
                still_pending = {}
                for src, meta in list(self._pending_moves.items()):
                    meta["tries"] += 1

                    if not os.path.exists(src):
                        # 可能已被前面的循环搬走或被删除
                        continue

                    name = os.path.basename(src)
                    base, ext = os.path.splitext(name)
                    dst = os.path.join(save_dir, name)
                    i = 1
                    while os.path.exists(dst):
                        dst = os.path.join(save_dir, f"{base}_{i}{ext}")
                        i += 1

                    try:
                        if _safe_move(src, dst):
                            # 重试成功
                            name = os.path.basename(dst)
                            self._imgonly_seen.add(name)
                            self._op_step(f"🧩 步骤4：保存完成 → {save_dir}")
                            self.list_widget.addItem(f"✅ 速存图片：已保存 {name} → {save_dir}")
                            continue
                    except Exception:
                        pass

                    if meta["tries"] % 5 == 0:
                        self._op_step(f"🧩 步骤3a：仍在等待释放（重试 {meta['tries']}）")
                        self.list_widget.addItem(f"⏳ 仍在等待释放：{name}（重试 {meta['tries']}）")

                    if meta["tries"] < 30:
                        still_pending[src] = meta
                    else:
                        self._op_step("🧩 终止：搬运超时放弃")
                        self.list_widget.addItem(f"⚠️ 文件被占用，搬运超时放弃：{name}")

                self._pending_moves = still_pending

            # —— 3) 注入后 5s 未见下载 → 超时诊断 —— #
            if self._op and (not self._op.get("found")) and time.time() > self._op.get("deadline", 0):
                self._op_step("🧩 步骤2：超时，未检测到下载文件（请检查：扩展是否运行、是否在图片上按键）")
                self._op_end()

        except Exception as e:
            self.list_widget.addItem(f"❌ 速存图片扫描错误: {e}")

    def _op_step(self, text: str):
        """
        中文：统一“步骤”日志入口。无条件写入列表并滚动到底部；
        任何地方需要输出“步骤1/2/3/3a/4/终止”都调用它。
        """
        try:
            self.list_widget.addItem(text)
            self.list_widget.scrollToBottom()
        except Exception:
            pass

    def _append_log(self, text: str):
        try:
            self.list_widget.addItem(text)
            self.list_widget.scrollToBottom()
        except Exception:
            pass

    # ===== 操作会话：仅在按下 Alt+1 时输出“步骤1/1a/超时” =====
    def _op_begin(self, trigger: str = "下载指令"):
        """开始一次 5 秒诊断会话，用于输出步骤1/1a/超时；与常规步骤2/3/4无关。"""
        now = time.time()
        self._op = {"started_at": now, "deadline": now + 5.0, "found": False, "src": None}
        self._await_deadline = now + 5.0
        self._await_seen = False
        self.list_widget.addItem(f"🧩 步骤1：已收到 {trigger}，等待扩展下载（<=5s）")
        if not (self._dl_sub and os.path.isdir(self._dl_sub)):
            self._op_step("🧩 步骤1a：未检测到 下载/WebImageSaver 子目录，本轮临时观察“下载”根目录")

    def _op_end(self):
        """结束本次诊断会话（不影响常规步骤输出）"""
        self._op = None

    def _input_echo(self, text: str):
        """钩子线程回调：把内容用信号丢回主线程"""
        try:
            self.log_sig.emit(text)
        except Exception:
            pass

    def _block_switches(self, yes: bool):
        """统一屏蔽/恢复所有开关信号，避免程序化改勾选引起联动"""
        if hasattr(self, "chk_auto"):
            self.chk_auto.blockSignals(yes)
        if hasattr(self, "chk_manual"):
            self.chk_manual.blockSignals(yes)
        if hasattr(self, "chk_imgonly"):
            self.chk_imgonly.blockSignals(yes)

    def _init_save_dir(self):
        """解析默认可写目录并填充到输入框"""
        path = self._resolve_default_dir()
        self.save_path.setText(path)
        self.list_widget.addItem(f"📁 初始路径：{path}")

    def _resolve_default_dir(self) -> str:
        """优先：图片库\\WebImageSaver → 用户目录\\WebImageSaver → 当前目录\\WebImageSaver → 让用户选"""
        candidates = []
        pic = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        if pic:
            candidates.append(os.path.join(pic, "WebImageSaver"))
        home = os.path.expanduser("~") or ""
        if home:
            candidates.append(os.path.join(home, "WebImageSaver"))
        candidates.append(os.path.join(os.getcwd(), "WebImageSaver"))
        for p in candidates:
            ok, norm, _ = self._ensure_writable_dir(p, create=True)
            if ok:
                return norm
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if folder:
            ok, norm, _ = self._ensure_writable_dir(folder, create=True)
            if ok:
                return norm
        fallback = os.path.join(home or os.getcwd(), "WebImageSaver")
        os.makedirs(fallback, exist_ok=True)
        return os.path.abspath(fallback)

    def _ensure_writable_dir(self, path: str, create: bool = True):
        """创建并测试可写性；返回 (ok, normalized_path, err)"""
        try:
            if not path:
                return False, "", "空路径"
            if create:
                os.makedirs(path, exist_ok=True)
            testfile = os.path.join(path, "__w_test__.tmp")
            with open(testfile, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(testfile)
            return True, os.path.abspath(path), ""
        except Exception as e:
            return False, path, str(e)

    def _prime_seen_and_quiet(self, path: str):
        """
        中文：切换保存目录后，把目录中已有的图片文件预载入到 _imgonly_seen，
        并在 2 秒内静默这些旧文件的“已保存”日志，避免一次性刷屏。
        """
        try:
            exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg", ".avif", ".ico"}
            names = set()
            if os.path.isdir(path):
                for n in os.listdir(path):
                    if os.path.splitext(n)[1].lower() in exts:
                        names.add(n)
            # 用新目录已有的图片名替换“已见集合”，并清空未搬运队列，防止跨目录遗留
            self._imgonly_seen = names
            self._pending_moves.clear()
            # 设置 2 秒静默窗口
            self._suppress_existing_until = time.time() + 2.0
            self.list_widget.addItem(f"📁 保存路径切换为：{path}（已忽略 {len(names)} 个已有文件）")
        except Exception as e:
            self.list_widget.addItem(f"⚠️ 预加载保存目录失败：{e}")

    def _require_writable_path(self, interactive: bool = True) -> bool:
        """确保当前输入框路径可写；interactive=True 时会弹窗要求用户选择"""
        path = self.save_path.text().strip()
        ok, norm, err = self._ensure_writable_dir(path, create=True)
        if ok:
            self.save_path.setStyleSheet("")
            if norm != path:
                self.save_path.setText(norm)
            return True

        if not interactive:
            self.save_path.setStyleSheet("QLineEdit{border:1px solid #f59e0b;}")
            if path:
                self.list_widget.addItem(f"⚠️ 路径不可用：{path}（{err}）")
            return False

        self.list_widget.addItem(f"⚠️ 路径不可写：{path}，请选择可写目录")
        while True:
            folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
            if not folder:
                return False
            ok2, norm2, err2 = self._ensure_writable_dir(folder, create=True)
            if ok2:
                self.save_path.setStyleSheet("")
                self.save_path.setText(norm2)
                # ✅ 切换成功：预加载已有文件并静默 2 秒，避免“已保存 …”刷屏
                self._prime_seen_and_quiet(norm2)
                return True
            else:
                self.list_widget.addItem(f"❌ 该目录不可写：{folder}（{err2}），请重新选择")

    def _on_path_edited(self, _=None):
        """用户编辑路径时做轻量校验（不弹窗、不打断）"""
        self._require_writable_path(interactive=False)

    def _current_manual_key(self) -> str:
        try:
            return self.combo_manual_hotkey.currentText() or "F7"
        except Exception:
            return "F7"

    def _on_manual_hotkey_changed(self, key: str):
        """同步更新页面内快捷键，并在手动模式下重注册全局热键"""
        if hasattr(self, "_sc_manual"):
            self._sc_manual.setKey(QKeySequence(key))
        if getattr(self, "state", self.STATE_IDLE) == self.STATE_MANUAL:
            self.list_widget.addItem(f"⌨️ 快捷键切换为：{key}")
            self._register_global_hotkey()

    # ===== 生命周期：离开页面强制复位 =====
    def hideEvent(self, e):
        """隐藏时仅禁用页内快捷键，避免‘无故关闭’"""
        try:
            if hasattr(self, "_sc_manual"):
                self._sc_manual.setEnabled(False)
        finally:
            super().hideEvent(e)

    def closeEvent(self, e):
        self._unregister_global_hotkey()
        super().closeEvent(e)

    def showEvent(self, e):
        if not hasattr(self, "_container"):
            self._bind_container_switch()
        super().showEvent(e)
        if getattr(self, "state", self.STATE_IDLE) == self.STATE_MANUAL:
            if hasattr(self, "_sc_manual"):
                self._sc_manual.setEnabled(True)
            self._register_global_hotkey()

    # ===== 共享区：路径选择 =====
    def _choose_dir(self):
        """中文：用户点击『另选目录』后选择新保存路径；校验成功则预载并静默旧文件"""
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if not folder:
            return
        self.save_path.setText(folder)
        if self._require_writable_path(interactive=True):
            self._prime_seen_and_quiet(self.save_path.text().strip())

    # ===== 自动模式：剪贴板处理 =====
    def _check_clipboard(self):
        if not self.chk_auto.isChecked():
            return
        md = self.clipboard.mimeData()
        save_dir = self.save_path.text().strip()
        ensure_dir(save_dir)
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        if md.hasImage():
            image = self.clipboard.image()
            buf = QBuffer(); buf.open(QIODevice.ReadWrite)
            QPixmap.fromImage(image).save(buf, "PNG")
            raw = bytes(buf.data())
            sig = hashlib.sha1(raw).hexdigest()
            if sig == self._last_img_sig:
                self.list_widget.addItem("🔁 检测到重复图片，已忽略")
                return
            self._last_img_sig = sig
            filename = f"img_clipboard_{now}.png"
            with open(os.path.join(save_dir, filename), 'wb') as f:
                f.write(raw)
            self.list_widget.addItem(f"🖼️ 图片保存: {filename}")
            self.last_saved_image = filename
        elif md.hasText() and self.last_saved_image:
            text = md.text().strip()
            txtname = os.path.splitext(self.last_saved_image)[0] + ".txt"
            with open(os.path.join(save_dir, txtname), 'w', encoding='utf-8') as f:
                f.write(text)
            self.list_widget.addItem(f"📄 文本保存: {txtname}")
            self.last_saved_image = ""

    # ===== 手动模式：F7 / 按钮 =====
    def manual_fast_save(self):
        """为资源管理器当前选中文件创建同名 .txt 并写入剪贴板文本"""
        if self.state != self.STATE_MANUAL:
            self.list_widget.addItem("⚠️ 未启用手动模式")
            return
        if not _WIN_OK:
            self.list_widget.addItem("❌ 手动功能不可用：缺少 pywin32/pyperclip")
            return
        try:
            pythoncom.CoInitialize()
            # 读取剪贴板文本
            try:
                clip_text = (pyperclip.paste() or "").strip()
            except Exception:
                clip_text = ""
            # 仅获取“当前活动的资源管理器窗口”的选中项
            shell = win32com.client.Dispatch("Shell.Application")
            selected_files = []
            try:
                active_hwnd = int(ctypes.windll.user32.GetForegroundWindow())
            except Exception:
                active_hwnd = 0
            for window in shell.Windows():
                try:
                    if int(getattr(window, "HWND", 0)) != active_hwnd:
                        continue
                    for item in window.Document.SelectedItems():
                        p = item.Path
                        if p and os.path.isfile(p):
                            selected_files.append(p)
                    break
                except Exception:
                    continue
            if not selected_files:
                self.list_widget.addItem("⚠️ 未检测到资源管理器选中文件")
                return
            count = 0
            for file_path in selected_files:
                base = os.path.splitext(os.path.basename(file_path))[0]
                dir_path = os.path.dirname(file_path)
                txt_path = os.path.join(dir_path, base + ".txt")
                if not os.path.exists(txt_path):
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(clip_text)
                    count += 1
            if count > 0:
                self.list_widget.addItem(f"✅ 已创建 {count} 个 .txt 并写入剪贴板内容")
            else:
                self.list_widget.addItem("⚠️ 所选文件已存在 .txt 或无效")
        except Exception as e:
            self.list_widget.addItem(f"❌ 手动速存图文错误: {e}")

    def _bind_container_switch(self):
        """向上寻找 QTabWidget / QStackedWidget，绑定切页信号"""
        w = self.parent()
        while w:
            if isinstance(w, (QTabWidget, QStackedWidget)):
                self._container = w
                try:
                    w.currentChanged.connect(self._on_container_current_changed)
                except Exception:
                    pass
                break
            w = w.parent()

    def _on_container_current_changed(self, idx: int):
        """v9.5：切换页面不再自动关闭速存功能，保持后台运行"""
        pass
