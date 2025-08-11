from styles.common_styles import TEXT_STYLE, BUTTON_STYLE, LINEEDIT_STYLE

import os
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QCheckBox, QFileDialog
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QBuffer, QIODevice
from PyQt5.QtWidgets import QApplication
import hashlib
from utils.file_utils import ensure_dir

# 共享队列（由 utils.server 推入）
_SHARED_QUEUE = []

class PageFastSave(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        # 开关 + 路径
        row1 = QHBoxLayout(); lay.addLayout(row1)
        self.label_path = QLabel("图文保存路径：")
        self.label_path.setStyleSheet(TEXT_STYLE)
        row1.addWidget(self.label_path)

        self.enabled_checkbox = QCheckBox("启用速存")
        self.enabled_checkbox.setStyleSheet(TEXT_STYLE)

        row1.addStretch()
        row1.addWidget(self.enabled_checkbox)

        row2 = QHBoxLayout()
        lay.addLayout(row2)
        self.save_path = QLineEdit(os.path.join(os.path.expanduser("~"), "Pictures", "WebImageSaver"))
        self.save_path.setStyleSheet(LINEEDIT_STYLE)  # 应用样式
        btn = QPushButton("另选目录")
        btn.setStyleSheet(BUTTON_STYLE)  # ✅ 统一按钮样式
        btn.clicked.connect(self._choose_dir)     # ← 新增
        btn.style().unpolish(btn)
        btn.style().polish(btn)

        row2.addWidget(self.save_path)
        row2.addWidget(btn)

        self.list_widget = QListWidget()
        self.list_widget.setFixedHeight(420)   # 由 200 调到 360（或你喜欢的值）
        lay.addWidget(self.list_widget)
        lay.addStretch()

        # 剪贴板监听（可后续细化）
        self.clipboard = QApplication.clipboard()
        self.last_saved_image = ""        # 仍用于配套文本
        self._last_img_sig = None         # 新增：上一张图的指纹
        self.clipboard.dataChanged.connect(self._check_clipboard)  # 用信号触发

    # 提供给 Flask 服务用于推送
    @staticmethod
    def shared_queue():
        return _SHARED_QUEUE

    def allow_accept(self):
        return self.enabled_checkbox.isChecked()

    def drain_queue(self):
        if not self.enabled_checkbox.isChecked():
            return
        while _SHARED_QUEUE:
            item = _SHARED_QUEUE.pop(0)
            if item.get("type") == "image":
                self.list_widget.addItem(f"🖼️ 插件保存: {item.get('filename')}")
                self.last_saved_image = item.get('filename', '')

    def _choose_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if folder:
            self.save_path.setText(folder)

    def _check_clipboard(self):
        if not self.enabled_checkbox.isChecked():
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