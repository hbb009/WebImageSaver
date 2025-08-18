from styles.common_styles import TEXT_STYLE, BUTTON_STYLE, LINEEDIT_STYLE

import os
import hashlib
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget,
    QCheckBox, QFileDialog, QGroupBox, QShortcut, QComboBox
)

from PyQt5.QtCore import Qt, QBuffer, QIODevice, QStandardPaths
from PyQt5.QtGui import QPixmap, QKeySequence
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QAbstractNativeEventFilter, QCoreApplication
import ctypes
import ctypes.wintypes as wintypes

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

class PageFastSave(QWidget):
    STATE_IDLE = 0
    STATE_AUTO = 1
    STATE_MANUAL = 2

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)

        # ===== 顶部两侧分组：自动 / 手动 =====
        row_top = QHBoxLayout()
        lay.addLayout(row_top)

        # 左：自动
        gb_auto = QGroupBox("图文自动保存")
        gb_auto.setFlat(False);  gb_auto.setStyleSheet(TEXT_STYLE)

        # 原来是 QHBoxLayout(gb_auto)，改成垂直布局以便放提示文字
        auto_box = QVBoxLayout(gb_auto)

        # 第1行：启用自动（保持原有样式）
        row_auto_line = QHBoxLayout()
        self.chk_auto = QCheckBox("启用自动")
        self.chk_auto.setStyleSheet(TEXT_STYLE)
        row_auto_line.addWidget(self.chk_auto)
        row_auto_line.addStretch(1)
        auto_box.addLayout(row_auto_line)

        # 第2行：提示文字（自动换行、橙色小字）
        self.label_auto_hint = QLabel(
            '提示：如果用户使用的是 Google Chrome 浏览器，可以安装 "chrome_image_saver_configurable" 目录下的扩展程序，就能使用 Alt+鼠标左键 点击图片快速保存图片。'
        )
        self.label_auto_hint.setWordWrap(True)
        self.label_auto_hint.setStyleSheet("color:#00a67d;font-size:12px;")
        auto_box.addWidget(self.label_auto_hint)

        # 右：手动
        gb_manual = QGroupBox("图文手动保存")
        gb_manual.setFlat(False); gb_manual.setStyleSheet(TEXT_STYLE)
        manual_box = QVBoxLayout(gb_manual)

        row_manual_line = QHBoxLayout()
        self.chk_manual = QCheckBox("启用手动")
        self.chk_manual.setStyleSheet(TEXT_STYLE)

        # 下拉选择快捷键：F5~F8（默认 F7）
        self.combo_manual_hotkey = QComboBox()
        self.combo_manual_hotkey.addItems(["F5", "F6", "F7", "F8"])
        self.combo_manual_hotkey.setCurrentText("F7")
        self.combo_manual_hotkey.setFixedWidth(90)

        row_manual_line.addWidget(self.chk_manual)
        row_manual_line.addWidget(self.combo_manual_hotkey)
        row_manual_line.addStretch(1)
        manual_box.addLayout(row_manual_line)

        # 提示（自动换行）
        self.label_manual_hint = QLabel('在资源管理器选中文件后，按所选快捷键（默认 F7）即可新建同名 .txt 并写入剪贴板文本')
        self.label_manual_hint.setWordWrap(True)
        self.label_manual_hint.setStyleSheet("color:#00a67d;font-size:12px;")
        manual_box.addWidget(self.label_manual_hint)

        row_top.addWidget(gb_auto)
        row_top.addWidget(gb_manual)
        row_top.setStretch(0, 1)
        row_top.setStretch(1, 1)

        # ===== 中下：共享（蓝色区域） 路径 + 日志 =====
        # 路径行
        row_path_title = QHBoxLayout(); lay.addLayout(row_path_title)
        self.label_path = QLabel("图文保存路径：")
        self.label_path.setStyleSheet(TEXT_STYLE)
        row_path_title.addWidget(self.label_path)
        row_path_title.addStretch(1)

        row_path = QHBoxLayout(); lay.addLayout(row_path)
        self.save_path = QLineEdit("")  # 由 _init_save_dir 自行解析并填充
        self.save_path.setStyleSheet(LINEEDIT_STYLE)
        self.btn_choose_dir = QPushButton("另选目录")
        self.btn_choose_dir.setStyleSheet(BUTTON_STYLE)
        row_path.addWidget(self.save_path)
        row_path.addWidget(self.btn_choose_dir)

        # 日志列表
        self.list_widget = QListWidget()
        self.list_widget.setFixedHeight(380)
        lay.addWidget(self.list_widget)
        lay.addStretch()

        # ===== 信号与状态 =====
        self.btn_choose_dir.clicked.connect(self._choose_dir)
        self.chk_auto.toggled.connect(self._on_auto_toggled)
        self.chk_manual.toggled.connect(self._on_manual_toggled)
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

    def _register_global_hotkey(self):
        self._unregister_global_hotkey()
        key = getattr(self, "_current_manual_key", lambda: "F7")()
        vk = VK_CODE.get(key, 0x76)
        ok = ctypes.windll.user32.RegisterHotKey(None, self._hotkey_id, 0x0000, vk)
        if not ok:
            try:
                self.list_widget.addItem(f"❌ 注册全局热键 {key} 失败，可能被占用")
            except Exception:
                pass
            return False
        if self._hotkey_filter is None:
            self._hotkey_filter = _GlobalHotkeyFilter(self.manual_fast_save, self._hotkey_id)
            QCoreApplication.instance().installNativeEventFilter(self._hotkey_filter)
        try:
            self.list_widget.addItem(f"🟡 全局热键已就绪：{key}")
        except Exception:
            pass
        return True

    def _unregister_global_hotkey(self):
        try:
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
        except Exception:
            pass

    # ===== 互斥状态切换 =====
    def _on_auto_toggled(self, checked: bool):
        if checked:
            if not self._require_writable_path(interactive=True):
                self._block_switches(True); self.chk_auto.setChecked(False); self._block_switches(False)
                self.list_widget.addItem("⚠️ 保存路径不可用，已取消自动模式")
                return
            self._enter_auto()
        else:
            if not self.chk_manual.isChecked():
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
        if reset_switches:
            self._block_switches(True)
            self.chk_auto.setChecked(False)
            self.chk_manual.setChecked(False)
            self._block_switches(False)
        self._sc_manual.setEnabled(False)
        self.state = self.STATE_IDLE
        # 不清空日志，便于回看
        self._unregister_global_hotkey()

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
            self.list_widget.addItem(f"🟡 手动模式：可按 {key}")
        self._register_global_hotkey()

    def _block_switches(self, yes: bool):
        self.chk_auto.blockSignals(yes)
        self.chk_manual.blockSignals(yes)

    def _init_save_dir(self):
        """解析默认可写目录并填充到输入框"""
        path = self._resolve_default_dir()
        self.save_path.setText(path)
        self.list_widget.addItem(f"📁 初始路径：{path}")

    def _resolve_default_dir(self) -> str:
        """按顺序尝试：图片库\WebImageSaver → 用户目录\WebImageSaver → 当前目录\WebImageSaver → 让用户选择"""
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

        # 以上都不行则引导用户选择
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if folder:
            ok, norm, _ = self._ensure_writable_dir(folder, create=True)
            if ok:
                return norm

        # 兜底：回到用户目录/当前目录尝试创建
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

    def _require_writable_path(self, interactive: bool = True) -> bool:
        """确保当前输入框路径可写；interactive=True 时会循环弹窗要求选择"""
        path = self.save_path.text().strip()
        ok, norm, err = self._ensure_writable_dir(path, create=True)
        if ok:
            # 恢复正常样式
            self.save_path.setStyleSheet(LINEEDIT_STYLE)
            if norm != path:
                self.save_path.setText(norm)
            return True

        # 不打断，仅提示
        if not interactive:
            self.save_path.setStyleSheet(LINEEDIT_STYLE + "QLineEdit{border:1px solid #f59e0b;}")
            if path:
                self.list_widget.addItem(f"⚠️ 路径不可用：{path}（{err}）")
            return False

        # 交互式：循环直到选到可写目录或用户取消
        self.list_widget.addItem(f"⚠️ 路径不可写：{path}，请选择可写目录")
        while True:
            folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
            if not folder:
                return False
            ok2, norm2, err2 = self._ensure_writable_dir(folder, create=True)
            if ok2:
                self.save_path.setStyleSheet(LINEEDIT_STYLE)
                self.save_path.setText(norm2)
                self.list_widget.addItem(f"📁 保存路径切换为：{norm2}")
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
        # 同步更新页面内快捷键（F5~F8）
        if hasattr(self, "_sc_manual"):
            self._sc_manual.setKey(QKeySequence(key))
        if getattr(self, "state", self.STATE_IDLE) == self.STATE_MANUAL:
            self.list_widget.addItem(f"⌨️ 快捷键切换为：{key}")
        if getattr(self, "state", self.STATE_IDLE) == self.STATE_MANUAL:
            self._register_global_hotkey()

    # ===== 生命周期：离开页面强制复位 =====
    def hideEvent(self, e):
        self._enter_idle(reset_switches=True)
        super().hideEvent(e)

    def closeEvent(self, e):
        self._unregister_global_hotkey()
        super().closeEvent(e)

    # ===== 共享区：路径选择 =====
    def _choose_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if folder:
            self.save_path.setText(folder)
            self._require_writable_path(interactive=True)

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
            raw = bytes(buf.data())                           # 图片二进制
            sig = hashlib.sha1(raw).hexdigest()               # 指纹

            # 如果与上一张相同，直接返回，避免重复保存
            if sig == self._last_img_sig:
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

    # ===== 手动模式：F7 / 按钮 执行 =====
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

            # 获取资源管理器选中项
            shell = win32com.client.Dispatch("Shell.Application")
            selected_files = []
            for window in shell.Windows():
                try:
                    for item in window.Document.SelectedItems():
                        p = item.Path
                        if p and os.path.isfile(p):
                            selected_files.append(p)
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
