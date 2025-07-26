from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit,
    QFileDialog, QListWidget, QGridLayout, QVBoxLayout, QHBoxLayout,
    QCheckBox, QFrame, QSpacerItem, QSizePolicy  # ✅ 一次性加全
)
from PyQt5.QtGui import QFont, QIcon, QIntValidator  # ✅ 你已经正确加了 QIntValidator

import sys
import os
import io
import requests
import threading
import time
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit,
    QFileDialog, QListWidget, QGridLayout, QVBoxLayout, QHBoxLayout
)
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtCore import Qt, QTimer, QMimeData
from PIL import ImageGrab, Image


class MainApp(QWidget):
    def __init__(self):
        super().__init__()
        self.toggle_checkbox = QCheckBox("启用自动保存")
        self.toggle_checkbox.setChecked(True)  # 默认勾选
        self.toggle_checkbox.setStyleSheet("font-size: 13px;")

        self.setWindowTitle("网页图片 + 文本笔记 + 比例工具 v4.1")
        self.setFixedSize(800, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)

        self.save_path = QLineEdit()
        self.save_path.setText(os.path.join(os.path.expanduser("~"), "Pictures", "WebImageSaver"))
        self.save_path.setStyleSheet("padding: 5px; font-size: 14px;")
        self.browse_btn = QPushButton("另选目录")
        self.browse_btn.setStyleSheet("padding: 5px;")
        self.browse_btn.clicked.connect(self.select_path)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("font-size: 14px;")

        # 左侧布局（图文）
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.toggle_checkbox)
        left_layout.addWidget(QLabel("图文保存路径:"))
        h1 = QHBoxLayout()
        h1.addWidget(self.save_path)
        h1.addWidget(self.browse_btn)
        left_layout.addLayout(h1)
        left_layout.addWidget(self.list_widget)

        # 添加提示标签到左下角
        self.left_hint_label = QLabel(
            "提示：如有安装 Google Chrome 浏览器扩展程序，就可以使用\n"
            "Alt+鼠标左键点击图片快速保存图片\n"
            "快捷保存图片后，进行复制操作的文字会保存为同名文本"
        )
        self.left_hint_label.setStyleSheet("""
            font-size: 13px; 
            color: #444;
            padding: 10px;
            background-color: #f8f8f8;
            border-radius: 8px;
            line-height: 1.6;
        """)
        self.left_hint_label.setFixedWidth(180)  # 控制最大宽度

        self.left_hint_label.setWordWrap(True)  # 允许换行

        # 比例计算器标题
        ratio_title = QLabel("比例计算器")
        ratio_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        ratio_title.setAlignment(Qt.AlignHCenter)

        # 输入框设置
        self.input_a = QLineEdit(); self.input_a.setPlaceholderText("A")
        self.input_b = QLineEdit(); self.input_b.setPlaceholderText("B")
        self.input_c = QLineEdit(); self.input_c.setPlaceholderText("C")
        self.input_d = QLineEdit(); self.input_d.setPlaceholderText("D")
        self.input_d.setReadOnly(True)
        self.input_d.setEnabled(False)  # 🔒 禁止编辑（灰色样式）

        for i in [self.input_a, self.input_b, self.input_c, self.input_d]:
            i.setFixedWidth(100)
            i.setAlignment(Qt.AlignCenter)
            i.setStyleSheet("font-size: 14px; padding: 6px; border-radius: 6px;")

        int_validator = QIntValidator(0, 99999)  # 最多5位整数（0~99999）
        self.input_a.setValidator(int_validator)
        self.input_b.setValidator(int_validator)
        self.input_c.setValidator(int_validator)

        # 延迟计算逻辑
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.update_result)
        for inp in [self.input_a, self.input_b, self.input_c]:
            inp.textChanged.connect(lambda: self.timer.start(1000))

        # AB交换按钮
        self.swap_btn = QPushButton("AB交换")
        self.swap_btn.setFixedWidth(80)
        self.swap_btn.setStyleSheet("padding: 5px; font-size: 13px;")
        self.swap_btn.clicked.connect(self.swap_ab)

        # 水平线和按钮插入 layout
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("margin-top: 10px; margin-bottom: 10px;")

        # 右侧布局
        right_layout = QVBoxLayout()
        right_layout.addWidget(ratio_title)
        right_layout.setAlignment(Qt.AlignTop)

        def row(label_text, widget):
            lbl = QLabel(label_text)
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setFixedWidth(20)
            h = QHBoxLayout()
            h.addWidget(lbl)
            h.addWidget(widget)
            right_layout.addLayout(h)

        row("A", self.input_a)
        row("B", self.input_b)
        right_layout.addWidget(self.swap_btn, alignment=Qt.AlignLeft)
        right_layout.addWidget(separator)  # 插入分隔线
        row("C", self.input_c)
        row("D", self.input_d)

        # 添加“复制D数”按钮
        self.copy_d_btn = QPushButton("复制D数")
        self.copy_d_btn.setFixedWidth(80)
        self.copy_d_btn.setStyleSheet("padding: 5px; font-size: 13px;")
        self.copy_d_btn.clicked.connect(self.copy_d_value)
        right_layout.addWidget(self.copy_d_btn, alignment=Qt.AlignLeft)

        right_layout.addSpacing(10)  # 上方留点空间

        self.left_hint_label.setStyleSheet("font-size: 12px; color: gray; padding: 4px;")
        self.left_hint_label.setWordWrap(True)
        right_layout.addWidget(self.left_hint_label)

        # 主体分区
        main_layout = QHBoxLayout()
        main_layout.addLayout(left_layout, 2)

        # ✅ 添加12px水平空白间距
        spacer = QSpacerItem(12, 0, QSizePolicy.Fixed, QSizePolicy.Minimum)
        main_layout.addSpacerItem(spacer)

        main_layout.addLayout(right_layout, 1)

        self.setLayout(main_layout)

        # 启动剪贴板监控线程
        self.last_saved_image = ""
        self.clipboard = QApplication.clipboard()
        self.last_text = ""
        self.clipboard.dataChanged.connect(self.handle_clipboard)

    def select_path(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if folder:
            self.save_path.setText(folder)

    def update_result(self):
        try:
            a = float(self.input_a.text())
            b = float(self.input_b.text())
            c = float(self.input_c.text())
            d = b * c / a
            self.input_d.setText(f"{d:.2f}")  # 保留2位小数
        except:
            self.input_d.setText("")

    def swap_ab(self):
        a_val = self.input_a.text()
        b_val = self.input_b.text()
        self.input_a.setText(b_val)
        self.input_b.setText(a_val)
        self.timer.start(1000)  # 启动延迟更新

    def copy_d_value(self):
        text = self.input_d.text().split(".")[0]  # 取整数部分
        mime = QMimeData()
        mime.setText(text)
        self.clipboard.blockSignals(True)  # ✅ 关键：临时屏蔽 clipboard 的信号
        self.clipboard.setMimeData(mime)
        self.clipboard.blockSignals(False)  # ✅ 再恢复信号

    def handle_clipboard(self):
        if not self.toggle_checkbox.isChecked():
            return  # ✅ 如果未勾选，跳过保存逻辑
        md = self.clipboard.mimeData()
        path = self.save_path.text()
        if not os.path.exists(path):
            os.makedirs(path)

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        if md.hasImage():
            image = self.clipboard.image()
            buffer = QImageToBytes(image)
            filename = f"img_clipboard_{now}.png"
            with open(os.path.join(path, filename), "wb") as f:
                f.write(buffer)
            self.list_widget.addItem(f"🖼️ 剪贴板图片已保存: {filename}")
            self.last_saved_image = filename

        elif md.hasText():
            text = md.text().strip()
            if self.last_saved_image:
                txtname = self.last_saved_image.rsplit(".", 1)[0] + ".txt"
                with open(os.path.join(path, txtname), "w", encoding="utf-8") as f:
                    f.write(text)
                self.list_widget.addItem(f"📄 已保存: {txtname}")
                self.last_saved_image = ""
            else:
                self.list_widget.addItem("⚠️ 无关联图片，忽略文本。")


from PyQt5.QtCore import QBuffer, QIODevice
from PyQt5.QtGui import QPixmap

def QPixmapToBytes(pixmap):
    buffer = QBuffer()
    buffer.open(QIODevice.ReadWrite)
    pixmap.save(buffer, "PNG")
    return buffer.data().data()  # 返回字节数据

def QImageToBytes(image):
    pixmap = QPixmap.fromImage(image)
    return QPixmapToBytes(pixmap)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec_())
