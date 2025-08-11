from styles.common_styles import TEXT_STYLE, BUTTON_STYLE

import sys, os
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget, QSizePolicy
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt, QTimer
from pages.page_fast_save import PageFastSave
from pages.page_screenshot import PageScreenshot
from pages.page_ratio_calc import PageRatioCalc
from pages.page_ollama import PageOllama

try:
    from utils.server import start_server_thread
except Exception:
    start_server_thread = None

def resource_path(*paths):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *paths)

ASSETS_DIR = resource_path("assets")  # ← 替换你原来的 ASSETS_DIR

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        # ✅ 顶级窗口命名，便于 QSS 精准命中
        self.setObjectName("MainRoot")

        # ✅ 只加载全局 QSS，不再写局部 setStyleSheet
        qss_path = os.path.join(ASSETS_DIR, 'app.qss')
        if os.path.exists(qss_path):
            with open(qss_path, 'r', encoding='utf-8') as f:
                QApplication.instance().setStyleSheet(f.read())

        self.setWindowIcon(QIcon(os.path.join(ASSETS_DIR, 'star.ico')))
        self.setWindowTitle("桌面助手 v8.0")
        self.setFixedSize(960, 640)
        self.setFont(QFont("微软雅黑", 14))

        self.stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)  # 可选：更紧凑
        layout.setSpacing(8)
        layout.addWidget(self.stack)

        # 页面
        self.page_fast = PageFastSave()
        self.page_shot = PageScreenshot()
        self.page_ratio = PageRatioCalc()
        self.page_ollama = PageOllama()

        for p in (self.page_fast, self.page_shot, self.page_ratio, self.page_ollama):
            self.stack.addWidget(p)

        # 底部导航
        bottom = QHBoxLayout()
        self.btn_fast = QPushButton("速存图文")
        self.btn_shot = QPushButton("截图工具")
        self.btn_ratio = QPushButton("比例计算")
        self.btn_ollama = QPushButton("Ollama助理")
        for b in (self.btn_fast, self.btn_shot, self.btn_ratio, self.btn_ollama):
            b.setFixedHeight(40)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setProperty("role", "nav")   # ← 新增
            b.style().unpolish(b); b.style().polish(b)
            bottom.addWidget(b)  # ← 这里要加
        layout.addLayout(bottom)

        # 切换
        self.btn_fast.clicked.connect(lambda: self._switch(0, self.btn_fast))
        self.btn_shot.clicked.connect(lambda: self._switch(1, self.btn_shot))
        self.btn_ratio.clicked.connect(lambda: self._switch(2, self.btn_ratio))
        self.btn_ollama.clicked.connect(lambda: (self._switch(3, self.btn_ollama), self.page_ollama.on_enter()))
        self._highlight(self.btn_fast)

        # 速存图文的队列轮询（如需）
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.page_fast.drain_queue)
        self.timer.start(1000)

        # 可选：启动 Flask 服务（速存图文）
        if start_server_thread:
            start_server_thread(self.page_fast)

    def _switch(self, index, btn):
        self.stack.setCurrentIndex(index)
        self._highlight(btn)
        # 离开截图页时，自动关闭监听
        if self.stack.currentWidget() is not self.page_shot:
            self.page_shot.ensure_stopped()

    def _highlight(self, active_btn):
        for b in (self.btn_fast, self.btn_shot, self.btn_ratio, self.btn_ollama):
            b.setProperty("role", "nav")
            if b is active_btn:
                b.setProperty("role", "primary")
            b.style().unpolish(b)
            b.style().polish(b)
