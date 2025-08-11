from styles.common_styles import TEXT_STYLE, BUTTON_STYLE, LINEEDIT_STYLE

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QCheckBox, QFileDialog, QGroupBox, QComboBox
)
from PyQt5.QtCore import Qt, QRect, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap, QPainter, QPen, QImage
import pyautogui, numpy as np, keyboard
from utils.file_utils import ensure_dir

class _Signal(QObject):
    trigger = pyqtSignal()

class Overlay(QWidget):
    def __init__(self, on_capture, on_cancel):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowState(Qt.WindowFullScreen)
        self.start = self.end = None
        self.on_capture = on_capture
        self.on_cancel = on_cancel
        self.setCursor(Qt.CrossCursor)
        img = pyautogui.screenshot().convert("RGB")
        np_img = np.array(img)
        h, w, ch = np_img.shape
        qimg = QImage(np_img.data, w, h, w*ch, QImage.Format_RGB888)
        self.bg = QPixmap.fromImage(qimg)
        self.show(); self.raise_(); self.activateWindow(); self.setFocus()

    def mousePressEvent(self, e):
        if e.button()==Qt.LeftButton:
            self.start = e.pos(); self.end = self.start; self.update()

    def mouseMoveEvent(self, e):
        if self.start:
            self.end = e.pos(); self.update()

    def mouseReleaseEvent(self, e):
        if e.button()==Qt.RightButton:
            self.on_cancel(); self.close()
        elif e.button()==Qt.LeftButton and self.start and self.end:
            rect = QRect(self.start, self.end).normalized(); self.on_capture(rect); self.close()

    def keyPressEvent(self, e):
        if e.key()==Qt.Key_Escape:
            self.on_cancel(); self.close()

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawPixmap(0,0,self.bg)
        if self.start and self.end:
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(Qt.red,2))
            p.drawRect(QRect(self.start, self.end))

class PageScreenshot(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)

        # 行1：开关
        r1 = QHBoxLayout()
        lay.addLayout(r1)
        self.label_path = QLabel("截图保存路径：")
        self.label_path.setStyleSheet(TEXT_STYLE)
        r1.addWidget(self.label_path)  # 加上这一行
        r1.addStretch()

        self.checkbox_enable = QCheckBox("启用截图")
        self.checkbox_enable.setStyleSheet(TEXT_STYLE)
        r1.addWidget(self.checkbox_enable)
        self.checkbox_enable.stateChanged.connect(self._toggle)

        # 行2：路径
        r2 = QHBoxLayout(); lay.addLayout(r2)
        self.path = QLineEdit(os.path.join(os.path.expanduser("~"), "Pictures", "ScreenshotImageSaver"))
        self.path.setStyleSheet(LINEEDIT_STYLE)
        self.btn_select_dir = QPushButton("另选保存")
        self.btn_select_dir.setStyleSheet(BUTTON_STYLE)
        self.btn_select_dir.clicked.connect(self._choose_dir)

        r2.addWidget(self.path)
        r2.addWidget(self.btn_select_dir)

        # 第3行：左列表 + 右侧设置
        r3 = QHBoxLayout(); lay.addLayout(r3)

        # 左侧文件列表
        self.list = QListWidget()
        self.list.setFixedHeight(400)  # 你想要的高度
        r3.addWidget(self.list, 3)     # 左边占比3

        right_col = QVBoxLayout(); r3.addLayout(right_col, 1)

        gb_mod = QGroupBox("组合键")
        gb_mod.setStyleSheet(TEXT_STYLE)
        vb_mod = QVBoxLayout(gb_mod)

        # 组合键（修饰键）
        self.modifier_combo = QComboBox()
        self.modifier_combo.addItems(["Ctrl", "Alt", "Shift", "Ctrl+Shift", "Alt+Shift", "Ctrl+Alt"])
        self.modifier_combo.setStyleSheet(LINEEDIT_STYLE)

        # 主键（支持 F1~F12 + A~Z + 0~9 + Space/Insert）
        self.function_combo = QComboBox()
        keys = [f"F{i}" for i in range(1, 13)] + [chr(c) for c in range(65, 91)] + [str(d) for d in range(0, 10)] + ["Space", "Insert"]
        self.function_combo.addItems(keys)
        self.function_combo.setStyleSheet(LINEEDIT_STYLE)

        vb_mod.addWidget(self.modifier_combo)
        vb_mod.addWidget(self.function_combo)
        right_col.addWidget(gb_mod)
        right_col.addStretch()

        # 行4：状态栏
        self.label_status = QLabel("当前截图监听未启用")
        self.label_status.setStyleSheet(TEXT_STYLE)
        lay.addWidget(self.label_status)

        # 信号与监听
        self._sig = _Signal()
        self._sig.trigger.connect(self._show_overlay)

        # 默认热键
        self.modifier_combo.setCurrentText("Ctrl+Shift")
        self.function_combo.setCurrentText("A")   # 默认 Ctrl+Shift+A，更适合笔记本
        self.hotkey = self._current_hotkey()
        self._hotkey_handler = None

        # 组合键改变时自动重绑
        self.modifier_combo.currentTextChanged.connect(self._on_hotkey_changed)
        self.function_combo.currentTextChanged.connect(self._on_hotkey_changed)

    # === 事件 ===
    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择截图保存文件夹")
        if d: self.path.setText(d)

    def _toggle(self, st):
        if st == Qt.Checked:
            self.label_status.setText(f"截图监听已启用（等待快捷键：{self.hotkey.upper()}）")
            self._bind_hotkey()
        else:
            self.label_status.setText("当前截图监听未启用")
            self._unbind_hotkey()

    # === 热键 ===
    def _current_hotkey(self):
        mod = self.modifier_combo.currentText().lower()   # 如 "ctrl+shift"
        key = self.function_combo.currentText()           # 如 "A" / "7" / "Space" / "F6"
        name_map = {"Space": "space", "Insert": "insert"} # 统一大小写/名称
        key = name_map.get(key, key).lower()
        return f"{mod}+{key}"

    def _on_hotkey_changed(self, *_):
        self.hotkey = self._current_hotkey()
        if self.checkbox_enable.isChecked():
            self._bind_hotkey()
            self.label_status.setText(f"快捷键已设置为：{self.hotkey.upper()}")

    def _bind_hotkey(self):
        self._unbind_hotkey()
        try:
            self._hotkey_handler = keyboard.add_hotkey(self.hotkey, lambda: self._sig.trigger.emit())
        except Exception as e:
            print("热键注册失败：", e)

    def _unbind_hotkey(self):
        try:
            if self._hotkey_handler is not None:
                keyboard.remove_hotkey(self._hotkey_handler)
                self._hotkey_handler = None
        except Exception:
            pass  # 兼容旧版本 keyboard

    # === 截图 ===
    def _show_overlay(self):
        self.list.addItem("🔥 热键已触发")
        self.overlay = Overlay(self._capture, lambda: self.label_status.setText("❌ 截图已取消"))

    def _capture(self, rect):
        if rect.width() < 10 or rect.height() < 10:
            self.label_status.setText("❗ 选区太小，已取消")
            return        ensure_dir(self.path.text())
        from datetime import datetime
        name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        full = os.path.join(self.path.text(), name)
        try:
            img = pyautogui.screenshot(region=(rect.x(), rect.y(), rect.width(), rect.height()))
            img.save(full)
            self.list.addItem(f"📸 {name}")
            self.label_status.setText("✅ 截图完成")
        except Exception:
            self.label_status.setText("❌ 截图失败")

    def ensure_stopped(self):
        if self.checkbox_enable.isChecked():
            self.checkbox_enable.setChecked(False)
        self._unbind_hotkey()
        self.label_status.setText("当前截图监听未启用")  # ← 新增

