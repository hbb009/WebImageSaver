import pythoncom
import win32com.client
import pyperclip
import ctypes

from PyQt5.QtCore import Qt, QUrl, QSize, QTimer
from PyQt5.QtGui import QIcon, QDesktopServices
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget, QPushButton
from pages.page_points_calc import PagePointsCalc

# 进度条/分组框
from PyQt5.QtWidgets import QProgressBar, QGroupBox
from PyQt5.QtGui import QFont

# 系统资源
import psutil
import subprocess

from PyQt5.QtWidgets import QShortcut
from PyQt5.QtGui import QKeySequence

import sys, os
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget, QSizePolicy, QLabel, QFrame
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt, QTimer
from pages.page_fast_save import PageFastSave
from pages.page_screenshot import PageScreenshot
from pages.page_ratio_calc import PageRatioCalc
from pages.page_ollama import PageOllama
from pages.page_overview import PageOverview
from pages.page_rev_prompt import PageRevPrompt
from pages.page_batch_tag import PageBatchTag

# === 新增：主题区域（标题下面一条） ===
from PyQt5.QtCore import QUrl, QSize, Qt
from PyQt5.QtGui import QIcon, QPixmap, QDesktopServices
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

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
        self.setObjectName("AppRoot")            # 让 app.qss 的 QWidget#AppRoot 命中
        self.setAttribute(Qt.WA_StyledBackground, True)

        # ✅ 只加载全局 QSS，不再写局部 setStyleSheet
        qss_path = os.path.join(ASSETS_DIR, 'app.qss')
        if os.path.exists(qss_path):
            with open(qss_path, 'r', encoding='utf-8') as f:
                QApplication.instance().setStyleSheet(f.read())

        self.setWindowIcon(QIcon(os.path.join(ASSETS_DIR, 'star.ico')))
        self.setWindowTitle("桌面助手 v9.5")
        self.setFixedSize(1400, 900)
        QTimer.singleShot(0, self._apply_dark_titlebar)
        self.setFont(QFont("微软雅黑", 14))

        # 页面堆栈
        self.stack = QStackedWidget()
        self.stack.setAttribute(Qt.WA_StyledBackground, True)
        self.stack.setObjectName("StackArea")

        # ======= 新：外层垂直根布局（主题区 + 主体行） =======
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        # 顶部主题区（贯穿整窗）
        self.theme_bar = QWidget()
        self.theme_bar.setObjectName("ThemeBar")
        self.theme_bar.setMinimumHeight(56)              # 需要更厚/更薄可改这个数
        self.theme_bar.setAttribute(Qt.WA_StyledBackground, True)

        # === ThemeBar 内容（左：口号；右：文字链接，全部无底色）===
        theme_h = QHBoxLayout(self.theme_bar)
        theme_h.setContentsMargins(12, 8, 12, 8)
        theme_h.setSpacing(8)

        tagline = QLabel("给 AI 人的口袋瑞士军刀 🔧🧠")
        tagline.setObjectName("ThemeTagline")
        theme_h.addWidget(tagline, 0, Qt.AlignVCenter)

        theme_h.addStretch(1)

        capsule = QWidget()
        capsule.setObjectName("ThemeCapsule")
        cap_h = QHBoxLayout(capsule)
        cap_h.setContentsMargins(0, 0, 0, 0)   # 去外框留白
        cap_h.setSpacing(8)

        cap_text = QLabel("探索更多有趣内容")
        cap_text.setObjectName("ThemeCapsuleText")
        cap_h.addWidget(cap_text)

        def add_link_text(text: str, url: str):
            btn = QPushButton(text)                  # 只用字符，不再尝试图标文件
            btn.setObjectName("LinkIcon")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFlat(True)
            btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            cap_h.addWidget(btn)

        # 右侧四个“字符图标”
        add_link_text("B站", "https://www.bilibili.com/")
        add_link_text("❤",  "https://www.buymeacoffee.com/")
        add_link_text("YT",  "https://www.youtube.com/")
        add_link_text("🐱",  "https://space.bilibili.com/")

        theme_h.addWidget(capsule, 0, Qt.AlignRight | Qt.AlignVCenter)
        outer.addWidget(self.theme_bar, 0)   # ← 把主题栏挂到最外层竖向布局

        # ======= 主体一行（左侧菜单 / 右侧分页） =======
        row_wrap = QWidget()
        root = QHBoxLayout(row_wrap)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        content_wrap = QWidget()
        content_wrap.setObjectName("ContentRoot")
        content_wrap.setAttribute(Qt.WA_StyledBackground, True)

        content_layout = QVBoxLayout(content_wrap)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # ==== 主题栏（TopBar） ====
        self.topbar = QWidget()
        self.topbar.setObjectName("TopBar")
        self.topbar.setAttribute(Qt.WA_StyledBackground, True)

        tb = QHBoxLayout(self.topbar)
        tb.setContentsMargins(12, 4, 12, 4)
        tb.setSpacing(6)

        self.top_title = QLabel("系统总览")
        self.top_title.setObjectName("PageTitle")

        tb.addWidget(self.top_title)
        tb.addStretch(1)

        content_layout.addWidget(self.topbar, 0)
        content_layout.addWidget(self.stack, 1)

        # —— 折叠并隐藏 TopBar（“系统总览”所在整块区域）
        self.topbar.setVisible(False)
        self.topbar.setMaximumHeight(0)
        self.topbar.setMinimumHeight(0)
        tb.setContentsMargins(0, 0, 0, 0)   # 顶栏占位为 0

        # ---- 左侧：侧边栏容器（先创建，再加入根布局）----
        self.side_wrap = QWidget()
        self.side_wrap.setObjectName("SideBar")
        self.side_wrap.setFixedWidth(200)

        side = QVBoxLayout(self.side_wrap)
        side.setContentsMargins(12, 4, 12, 4)  # 上下外边距略小一点
        side.setSpacing(6)                        # 按钮之间的缝隙从 10 减到 6

        # 侧边按钮（左对齐，激活态高亮）
        self.btn_overview = QPushButton("系统总览")
        self.btn_fast     = QPushButton("速存图文")
        self.btn_points   = QPushButton("积分计算")
        self.btn_shot     = QPushButton("截图工具")
        self.btn_ratio    = QPushButton("比例计算")
        self.btn_rev      = QPushButton("反推提示词")
        self.btn_batch    = QPushButton("批量打标")
        self.btn_ollama   = QPushButton("Ollama 助理")

        self.side_btns = [
            self.btn_overview, self.btn_fast, self.btn_points, self.btn_shot, self.btn_ratio,
            self.btn_rev, self.btn_batch, self.btn_ollama,
        ]

        # 为"速存图文"和"截图工具"各创建一个 LED 指示灯开关
        # QPushButton 用 checkable=True 模拟 LED，样式由 QSS #SideLed 控制
        self.led_fast = QPushButton("✓")
        self.led_fast.setObjectName("SideLed")
        self.led_fast.setCheckable(True)
        self.led_fast.setChecked(False)
        self.led_fast.setFixedSize(18, 18)
        self.led_fast.setCursor(Qt.PointingHandCursor)
        self.led_fast.setToolTip("速存图片：点击开/关")

        self.led_fast_txt = QPushButton("✓")
        self.led_fast_txt.setObjectName("SideLed")
        self.led_fast_txt.setCheckable(True)
        self.led_fast_txt.setChecked(False)
        self.led_fast_txt.setFixedSize(18, 18)
        self.led_fast_txt.setCursor(Qt.PointingHandCursor)
        self.led_fast_txt.setToolTip("速存文本：点击开/关")

        self.led_shot = QPushButton("✓")
        self.led_shot.setObjectName("SideLed")
        self.led_shot.setCheckable(True)
        self.led_shot.setChecked(False)
        self.led_shot.setFixedSize(18, 18)
        self.led_shot.setCursor(Qt.PointingHandCursor)
        self.led_shot.setToolTip("截图监听：点击开/关")

        for b in self.side_btns:
            b.setFixedHeight(44)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setProperty("kind", "side")
            b.setProperty("active", False)
            b.setCursor(Qt.PointingHandCursor)
            b.style().unpolish(b); b.style().polish(b)
            side.addWidget(b)
        side.addStretch(1)

        # LED 用 setParent 挂到 side_wrap 上，用 move() 绝对定位到按钮右边
        # 实际位置在 _reposition_leds() 里计算，窗口 show 后调用一次
        self.led_fast.setParent(self.side_wrap)
        self.led_fast.raise_()
        self.led_fast_txt.setParent(self.side_wrap)
        self.led_fast_txt.raise_()
        self.led_shot.setParent(self.side_wrap)
        self.led_shot.raise_()

        # 最后把“左侧侧栏 + 右侧内容”加入根布局（顺序不能反）
        root.addWidget(self.side_wrap)
        root.addWidget(content_wrap, 1)
        outer.addWidget(row_wrap, 1)

        # ======= 页面注册 =======
        self.page_fast     = PageFastSave()
        self.page_points   = PagePointsCalc()
        self.page_shot     = PageScreenshot()
        self.page_ratio    = PageRatioCalc()
        self.page_ollama   = PageOllama()
        self.page_overview = PageOverview()
        self.page_rev      = PageRevPrompt()
        self.page_batch    = PageBatchTag()

        for p in (
            self.page_overview,  # 先加入总览，后面默认就能直接定位它
            self.page_fast, self.page_points, self.page_shot, self.page_ratio,
            self.page_rev, self.page_batch, self.page_ollama,
        ):
            p.setAttribute(Qt.WA_StyledBackground, True)
            p.setObjectName("PageRoot")
            self.stack.addWidget(p)

        # 默认停在「系统总览」
        self.stack.setCurrentWidget(self.page_overview)
        self._highlight(self.btn_overview)
        self.top_title.setText("系统总览")

        # ======= 连接切换 =======
        self.btn_overview.clicked.connect(lambda: self._switch(self.stack.indexOf(self.page_overview), self.btn_overview))
        self.btn_fast.clicked.connect    (lambda: self._switch(self.stack.indexOf(self.page_fast),     self.btn_fast))
        self.btn_points.clicked.connect  (lambda: self._switch(self.stack.indexOf(self.page_points),   self.btn_points))
        self.btn_shot.clicked.connect    (lambda: self._switch(self.stack.indexOf(self.page_shot),     self.btn_shot))
        self.btn_ratio.clicked.connect   (lambda: self._switch(self.stack.indexOf(self.page_ratio),    self.btn_ratio))
        self.btn_rev.clicked.connect     (lambda: self._switch(self.stack.indexOf(self.page_rev),      self.btn_rev))
        self.btn_batch.clicked.connect   (lambda: self._switch(self.stack.indexOf(self.page_batch),    self.btn_batch))
        self.btn_ollama.clicked.connect  (lambda: (self._switch(self.stack.indexOf(self.page_ollama),  self.btn_ollama), self.page_ollama.on_enter()))

        # LED 开关：速存图片
        self.led_fast.clicked.connect(self._toggle_fast_led)
        # LED 开关：速存文本
        self.led_fast_txt.clicked.connect(self._toggle_fast_txt_led)
        # LED 开关：截图监听
        self.led_shot.clicked.connect(self._toggle_shot_led)
        # 让速存页状态变化时同步 LED
        self.page_fast.chk_imgonly.toggled.connect(
            lambda checked: self.led_fast.setChecked(checked)
        )
        self.page_fast.chk_manual.toggled.connect(
            lambda checked: self.led_fast_txt.setChecked(checked)
        )
        self.page_shot.checkbox_enable.toggled.connect(
            lambda checked: self.led_shot.setChecked(checked)
        )

    def _switch(self, index, btn):
        self.stack.setCurrentIndex(index)
        self._highlight(btn)
        self.top_title.setText(self._title_for(self.stack.currentWidget()))
        # v9.5：切换页面不再自动关闭任何功能，后台保持运行

    def _title_for(self, w: QWidget) -> str:
        if w is getattr(self, "page_overview", None): return "系统总览"
        if w is getattr(self, "page_fast", None):     return "速存图文"
        if w is getattr(self, "page_points", None):   return "积分计算"
        if w is getattr(self, "page_shot", None):     return "截图工具"
        if w is getattr(self, "page_ratio", None):    return "比例计算"
        if w is getattr(self, "page_rev", None):      return "反推提示词"
        if w is getattr(self, "page_batch", None):    return "批量打标"
        if w is getattr(self, "page_ollama", None):   return "Ollama 助理"
        return "桌面助手"

    def _toggle_fast_led(self):
        """点击 LED 直接切换速存图片开关，不需要先切换到该页面"""
        target = not self.page_fast.chk_imgonly.isChecked()
        self.page_fast.chk_imgonly.setChecked(target)

    def _toggle_fast_txt_led(self):
        """点击 LED 直接切换速存文本开关，不需要先切换到该页面"""
        target = not self.page_fast.chk_manual.isChecked()
        self.page_fast.chk_manual.setChecked(target)

    def _toggle_shot_led(self):
        """点击 LED 直接切换截图监听开关"""
        target = not self.page_shot.checkbox_enable.isChecked()
        self.page_shot.checkbox_enable.setChecked(target)

    def _highlight(self, active_btn):
        for b in self.side_btns:
            b.setProperty("kind", "side")
            b.setProperty("active", b is active_btn)
            b.style().unpolish(b)
            b.style().polish(b)

    def _reposition_leds(self):
        """把 LED 绝对定位到对应按钮的右侧中央（side_wrap 坐标系）"""
        led_w, led_h = 18, 18
        gap = 3            # 两个 LED 之间的间距
        margin_right = 6   # 距按钮右边缘的间距

        # btn_fast 有两个 LED：led_fast（图片）在右，led_fast_txt（文本）在最右
        pos = self.btn_fast.mapTo(self.side_wrap, self.btn_fast.rect().topRight())
        y   = pos.y() + (self.btn_fast.height() - led_h) // 2
        x2  = pos.x() - led_w - margin_right          # led_fast_txt 最右
        x1  = x2 - led_w - gap                         # led_fast 在其左侧
        self.led_fast.move(x1, y)
        self.led_fast.raise_()
        self.led_fast_txt.move(x2, y)
        self.led_fast_txt.raise_()

        # btn_shot 只有一个 LED
        pos = self.btn_shot.mapTo(self.side_wrap, self.btn_shot.rect().topRight())
        x = pos.x() - led_w - margin_right
        y = pos.y() + (self.btn_shot.height() - led_h) // 2
        self.led_shot.move(x, y)
        self.led_shot.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        # 窗口显示后布局稳定，再定位 LED
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._reposition_leds)

    def _apply_dark_titlebar(self):
        """启用 Win10/11 深色标题栏（最简方式）。"""
        try:
            hwnd = int(self.winId())
            value = ctypes.c_int(1)
            # 先试 20（Win10 1903+），再回退 19（1809）
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass
