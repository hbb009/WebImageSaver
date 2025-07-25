import os
import sys
import threading
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import QFileSystemWatcher, Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QClipboard, QFont, QBrush, QColor, QPixmap, QIcon
from flask import Flask, request
from flask_cors import CORS
import requests
from PIL import Image
import io

# === Flask后台服务器（运行在子线程中） ===
app = Flask(__name__)
CORS(app)
image_save_folder = ""
status_text = ""
ui_reference = None  # 外部注入界面对象

@app.route("/save", methods=["POST"])
def save_image():
    global status_text, ui_reference
    try:
        data = request.get_json(force=True)
        url = data.get("url", "")
        if not url:
            return "没有收到图片地址", 400

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": url
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            filename = datetime.now().strftime("img_%Y%m%d_%H%M%S.jpg")
            save_path = os.path.join(image_save_folder, filename)
            with open(save_path, "wb") as f:
                f.write(response.content)
            status_text = f"✅ 已保存图片：{filename}"
            print(status_text)

            if ui_reference:
                ui_reference.signal_add_log.emit(f"已保存图片：{filename}|image")
                ui_reference.last_saved_image = filename

            return "OK", 200
        else:
            status_text = f"❌ 图片下载失败（状态码：{response.status_code}）"
            print(status_text)
            return "下载失败", 500
    except Exception as e:
        status_text = f"❌ 异常：{e}"
        print(status_text)
        return "异常", 500

def start_flask_server():
    app.run(host="127.0.0.1", port=8787, debug=False)


# === 主界面类 ===
class Communicate(QObject):
    signal_add_log = pyqtSignal(str)  # 带类型的日志传输（text|image）

class ImageTextTool(QWidget):
    signal_add_log = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("网页图片 + 文本笔记保存器 v3.1")
        self.setGeometry(300, 300, 580, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # UI 字体样式
        self.setFont(QFont("Microsoft YaHei", 11))
        self.setStyleSheet("""
            QLabel { font-size: 12pt; }
            QPushButton { font-size: 11pt; }
            QLineEdit { font-size: 11pt; }
            QListWidget { font-size: 11pt; }
        """)

        self.supported_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
        self.saved_images = []
        self.last_saved_image = ""

        self.folder_path = os.path.join(os.path.expanduser("~"), "Pictures", "WebImageSaver")
        os.makedirs(self.folder_path, exist_ok=True)

        # ========= UI 控件 =========
        layout = QVBoxLayout()

        self.label = QLabel("保存路径：")
        layout.addWidget(self.label)

        self.path_input = QLineEdit(self.folder_path)
        layout.addWidget(self.path_input)

        self.browse_btn = QPushButton("浏览")
        self.browse_btn.clicked.connect(self.select_folder)
        layout.addWidget(self.browse_btn)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        self.status_label = QLabel("✍️ Alt+左键图片 或 复制图片/文字 即可保存")
        self.status_label.setStyleSheet("color: #006600; font-weight: bold; font-size: 12pt")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        # ========= 功能绑定 =========
        self.fs_watcher = QFileSystemWatcher()
        self.fs_watcher.directoryChanged.connect(self.refresh_images)
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.handle_clipboard)
        self.signal_add_log.connect(self.receive_log_from_thread)

        self.refresh_images()
        self.update_status_timer()

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存路径", "")
        if folder:
            self.folder_path = folder
            self.path_input.setText(folder)
            global image_save_folder
            image_save_folder = folder
            self.fs_watcher.addPath(folder)
            self.refresh_images()

    def refresh_images(self):
        if not self.folder_path:
            return
        files = os.listdir(self.folder_path)
        self.saved_images = [f for f in files if os.path.splitext(f)[1].lower() in self.supported_exts]

    def handle_clipboard(self):
        if not self.folder_path:
            return

        # === 1. 图像剪贴板 ===
        image = self.clipboard.image()
        if not image.isNull():
            from PyQt5.QtCore import QBuffer, QIODevice
            buffer = QBuffer()
            buffer.open(QIODevice.ReadWrite)
            image.save(buffer, "PNG")
            pil_image = Image.open(io.BytesIO(buffer.data()))
            buffer.close()

            filename = datetime.now().strftime("img_clipboard_%Y%m%d_%H%M%S.png")
            path = os.path.join(self.folder_path, filename)
            pil_image.save(path)

            self.last_saved_image = filename
            self.add_log(f"剪贴板图片已保存：{filename}", "image")
            return

        # === 2. 文本剪贴板 ===
        text = self.clipboard.text().strip()
        if not text or not self.last_saved_image:
            return

        base, _ = os.path.splitext(self.last_saved_image)
        txt_path = os.path.join(self.folder_path, f"{base}.txt")
        if not os.path.exists(txt_path):
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text)
            self.add_log(f"已保存文本：{base}.txt", "text")

    def update_status_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status_label)
        self.timer.start(1000)

    def update_status_label(self):
        self.status_label.setText(status_text)

    def add_log(self, text, type_="text"):
        item = QListWidgetItem(text)
        if type_ == "text":
            item.setForeground(QBrush(QColor("#007acc")))
        elif type_ == "image":
            item.setForeground(QBrush(QColor("#009900")))
        self.list_widget.addItem(item)
        self.list_widget.scrollToBottom()

    def receive_log_from_thread(self, full_text):
        # 接收来自 Flask 的信号
        if "|" in full_text:
            msg, type_ = full_text.split("|", 1)
            self.add_log(msg, type_)

# === 启动入口 ===
if __name__ == '__main__':
    app_qt = QApplication(sys.argv)
    window = ImageTextTool()
    ui_reference = window
    image_save_folder = window.folder_path

    flask_thread = threading.Thread(target=start_flask_server)
    flask_thread.daemon = True
    flask_thread.start()

    window.show()
    sys.exit(app_qt.exec_())
