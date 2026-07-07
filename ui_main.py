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
from pages.page_overview import PageOverview
from pages.page_ollama_tools import PageOllamaTools
from pages.page_douyin import PageDouyin
from pages.page_dir_link import PageDirLink
from pages.page_timezone_fx import PageTimezoneFx
from pages.page_sd_mini import PageSdMini
from pages.page_comfyui_mini import PageComfyUiMini

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

ASSETS_DIR = resource_path("assets")

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("AppRoot")
        self.setAttribute(Qt.WA_StyledBackground, True)

        qss_path = os.path.join(ASSETS_DIR, 'app.qss')
        if os.path.exists(qss_path):
            with open(qss_path, 'r', encoding='utf-8') as f:
                QApplication.instance().setStyleSheet(f.read())

        self.setWindowIcon(QIcon(os.path.join(ASSETS_DIR, 'star.ico')))
        self.setWindowTitle("桌面助手 v9.8")
        self.setFixedSize(1400, 900)
        QTimer.singleShot(0, self._apply_dark_titlebar)
        self.setFont(QFont("微软雅黑", 14))

        # 页面堆栈
        self.stack = QStackedWidget()
        self.stack.setAttribute(Qt.WA_StyledBackground, True)
        self.stack.setObjectName("StackArea")

        # ======= 外层垂直根布局（主题区 + 主体行） =======
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        # 顶部主题区
        self.theme_bar = QWidget()
        self.theme_bar.setObjectName("ThemeBar")
        self.theme_bar.setMinimumHeight(56)
        self.theme_bar.setAttribute(Qt.WA_StyledBackground, True)

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
        cap_h.setContentsMargins(0, 0, 0, 0)
        cap_h.setSpacing(8)

        cap_text = QLabel("探索更多有趣内容")
        cap_text.setObjectName("ThemeCapsuleText")
        cap_h.addWidget(cap_text)

        def add_link_text(text: str, url: str):
            btn = QPushButton(text)
            btn.setObjectName("LinkIcon")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFlat(True)
            btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            cap_h.addWidget(btn)

        add_link_text("B站", "https://www.bilibili.com/")
        add_link_text("❤",  "https://www.buymeacoffee.com/")
        add_link_text("YT",  "https://www.youtube.com/")
        add_link_text("🐱",  "https://space.bilibili.com/")

        theme_h.addWidget(capsule, 0, Qt.AlignRight | Qt.AlignVCenter)
        outer.addWidget(self.theme_bar, 0)

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

        # TopBar
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

        self.topbar.setVisible(False)
        self.topbar.setMaximumHeight(0)
        self.topbar.setMinimumHeight(0)
        tb.setContentsMargins(0, 0, 0, 0)

        # ---- 左侧侧边栏 ----
        self.side_wrap = QWidget()
        self.side_wrap.setObjectName("SideBar")
        self.side_wrap.setFixedWidth(200)

        side = QVBoxLayout(self.side_wrap)
        side.setContentsMargins(12, 4, 12, 4)
        side.setSpacing(6)

        # ── 普通功能按钮 ──
        self.btn_overview  = QPushButton("系统总览")
        self.btn_fast      = QPushButton("速存图文")
        self.btn_points    = QPushButton("积分计算")
        self.btn_shot      = QPushButton("截图工具")
        self.btn_ratio     = QPushButton("比例计算")
        self.btn_douyin    = QPushButton("抖音下载")
        self.btn_dir_link  = QPushButton("目录映射")
        self.btn_tz_fx     = QPushButton("时区汇率")
        self.btn_sd_mini      = QPushButton("StableDiffusion\nMini")
        self.btn_comfyui_mini = QPushButton("ComfyUI\nMini")

        # ── Ollama 工具（贴底）──
        self.btn_ollama_tools = QPushButton("Ollama 工具")

        # side_btns 用于高亮轮询，顺序无关
        self.side_btns = [
            self.btn_overview, self.btn_fast, self.btn_points,
            self.btn_shot, self.btn_ratio, self.btn_douyin,
            self.btn_dir_link, self.btn_tz_fx, self.btn_sd_mini, self.btn_comfyui_mini,
            self.btn_ollama_tools,
        ]

        # LED 指示灯
        self.led_fast = QPushButton("✓")
        self.led_fast.setObjectName("SideLed")
        self.led_fast.setCheckable(True)
        self.led_fast.setChecked(False)
        self.led_fast.setFixedSize(18, 18)
        self.led_fast.setCursor(Qt.PointingHandCursor)
        self.led_fast.setToolTip("速存全功能：点击一键开/关图片·文本·文件夹")

        self.led_shot = QPushButton("✓")
        self.led_shot.setObjectName("SideLed")
        self.led_shot.setCheckable(True)
        self.led_shot.setChecked(False)
        self.led_shot.setFixedSize(18, 18)
        self.led_shot.setCursor(Qt.PointingHandCursor)
        self.led_shot.setToolTip("截图监听：点击开/关")

        # 普通按钮加入侧边栏（上半区，不含 SD Mini）
        normal_btns = [
            self.btn_overview, self.btn_fast, self.btn_points,
            self.btn_shot, self.btn_ratio, self.btn_douyin,
            self.btn_dir_link, self.btn_tz_fx,
        ]
        for b in normal_btns:
            b.setFixedHeight(44)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setProperty("kind", "side")
            b.setProperty("active", False)
            b.setCursor(Qt.PointingHandCursor)
            b.style().unpolish(b); b.style().polish(b)
            side.addWidget(b)

        # 弹性空白 → 下方区域贴底
        side.addStretch(1)

        # 分割线 + "本地算力" 标签
        lbl_local = QLabel("本地算力")
        lbl_local.setAlignment(Qt.AlignCenter)
        lbl_local.setStyleSheet(
            "color: #3a5a8a; font-size: 11px; font-weight: normal; "
            "padding: 0; margin: 0;"
        )
        side.addWidget(lbl_local)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("QFrame{background:#1e2a45; max-height:1px; min-height:1px;}")
        side.addWidget(sep)

        # SD Mini 按钮（线下，ComfyUI Mini 上面）
        self.btn_sd_mini.setFixedHeight(54)
        self.btn_sd_mini.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_sd_mini.setProperty("kind", "side")
        self.btn_sd_mini.setProperty("active", False)
        self.btn_sd_mini.setCursor(Qt.PointingHandCursor)
        self.btn_sd_mini.style().unpolish(self.btn_sd_mini)
        self.btn_sd_mini.style().polish(self.btn_sd_mini)
        side.addWidget(self.btn_sd_mini)

        # ComfyUI Mini 按钮（SD Mini 下，Ollama 上）
        self.btn_comfyui_mini.setFixedHeight(54)
        self.btn_comfyui_mini.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_comfyui_mini.setProperty("kind", "side")
        self.btn_comfyui_mini.setProperty("active", False)
        self.btn_comfyui_mini.setCursor(Qt.PointingHandCursor)
        self.btn_comfyui_mini.style().unpolish(self.btn_comfyui_mini)
        self.btn_comfyui_mini.style().polish(self.btn_comfyui_mini)
        side.addWidget(self.btn_comfyui_mini)

        # Ollama 工具按钮（贴底）
        self.btn_ollama_tools.setFixedHeight(44)
        self.btn_ollama_tools.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_ollama_tools.setProperty("kind", "side")
        self.btn_ollama_tools.setProperty("active", False)
        self.btn_ollama_tools.setCursor(Qt.PointingHandCursor)
        self.btn_ollama_tools.style().unpolish(self.btn_ollama_tools)
        self.btn_ollama_tools.style().polish(self.btn_ollama_tools)
        side.addWidget(self.btn_ollama_tools)

        # LED 绝对定位到 side_wrap
        self.led_fast.setParent(self.side_wrap)
        self.led_fast.raise_()
        self.led_shot.setParent(self.side_wrap)
        self.led_shot.raise_()

        root.addWidget(self.side_wrap)
        root.addWidget(content_wrap, 1)
        outer.addWidget(row_wrap, 1)

        # ======= 页面注册 =======
        self.page_fast         = PageFastSave()
        self.page_points       = PagePointsCalc()
        self.page_shot         = PageScreenshot()
        self.page_ratio        = PageRatioCalc()
        self.page_overview     = PageOverview()
        self.page_douyin       = PageDouyin()
        self.page_dir_link     = PageDirLink()
        self.page_tz_fx        = PageTimezoneFx()
        self.page_sd_mini      = PageSdMini()
        self.page_comfyui_mini = PageComfyUiMini()
        self.page_ollama_tools = PageOllamaTools()

        for p in (
            self.page_overview,
            self.page_fast, self.page_points, self.page_shot,
            self.page_ratio, self.page_douyin, self.page_dir_link, self.page_tz_fx,
            self.page_sd_mini,
            self.page_comfyui_mini,
            self.page_ollama_tools,
        ):
            p.setAttribute(Qt.WA_StyledBackground, True)
            p.setObjectName("PageRoot")
            self.stack.addWidget(p)

        # 默认停在「系统总览」
        self.stack.setCurrentWidget(self.page_overview)
        self._highlight(self.btn_overview)
        self.top_title.setText("系统总览")

        # ======= 连接切换 =======
        self.btn_overview.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_overview), self.btn_overview))
        self.btn_fast.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_fast), self.btn_fast))
        self.btn_points.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_points), self.btn_points))
        self.btn_shot.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_shot), self.btn_shot))
        self.btn_ratio.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_ratio), self.btn_ratio))
        self.btn_douyin.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_douyin), self.btn_douyin))
        self.btn_dir_link.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_dir_link), self.btn_dir_link))
        self.btn_tz_fx.clicked.connect(
            lambda: (
                self._switch(self.stack.indexOf(self.page_tz_fx), self.btn_tz_fx),
                self.page_tz_fx.on_enter()
            )
        )
        self.btn_sd_mini.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_sd_mini), self.btn_sd_mini))
        self.btn_comfyui_mini.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_comfyui_mini), self.btn_comfyui_mini))
        self.btn_ollama_tools.clicked.connect(
            lambda: (
                self._switch(self.stack.indexOf(self.page_ollama_tools), self.btn_ollama_tools),
                self.page_ollama_tools.on_enter()
            )
        )

        # LED 开关（单一总开关）
        self.led_fast.clicked.connect(self._toggle_fast_led)
        self.led_shot.clicked.connect(self._toggle_shot_led)
        # 任意子功能变化时同步 LED 状态
        self.page_fast.chk_imgonly.toggled.connect(self._sync_fast_led)
        self.page_fast.chk_manual.toggled.connect(self._sync_fast_led)
        self.page_fast.chk_mkdir.toggled.connect(self._sync_fast_led)
        # 速存启用总开关与 LED 双向联动
        self.page_fast.chk_enable_all.toggled.connect(self._sync_fast_led)
        self.page_shot.checkbox_enable.toggled.connect(
            lambda checked: self.led_shot.setChecked(checked))

    def _switch(self, index, btn):
        self.stack.setCurrentIndex(index)
        self._highlight(btn)
        self.top_title.setText(self._title_for(self.stack.currentWidget()))

    def _title_for(self, w: QWidget) -> str:
        if w is getattr(self, "page_overview",     None): return "系统总览"
        if w is getattr(self, "page_fast",         None): return "速存图文"
        if w is getattr(self, "page_points",       None): return "积分计算"
        if w is getattr(self, "page_shot",         None): return "截图工具"
        if w is getattr(self, "page_ratio",        None): return "比例计算"
        if w is getattr(self, "page_douyin",       None): return "抖音下载"
        if w is getattr(self, "page_dir_link",     None): return "目录映射"
        if w is getattr(self, "page_tz_fx",        None): return "时区汇率"
        if w is getattr(self, "page_sd_mini",      None): return "StableDiffusion Mini"
        if w is getattr(self, "page_comfyui_mini", None): return "ComfyUI Mini"
        if w is getattr(self, "page_ollama_tools", None): return "Ollama 工具"
        return "桌面助手"

    def _sync_fast_led(self, _=None):
        """任意速存子功能变化时，LED 亮起条件：至少一个功能开启"""
        self.led_fast.setChecked(self.page_fast.is_any_active())

    def _toggle_fast_led(self):
        """点击 LED：全部一键开 / 全部一键关"""
        currently_any = self.page_fast.is_any_active()
        self.page_fast.set_all_features(not currently_any)
        self.led_fast.setChecked(not currently_any)
        # 同步页面内总开关显示
        self.page_fast._sync_enable_all_display()

    def _toggle_fast_txt_led(self):
        self.page_fast.chk_manual.setChecked(not self.page_fast.chk_manual.isChecked())

    def _toggle_shot_led(self):
        self.page_shot.checkbox_enable.setChecked(not self.page_shot.checkbox_enable.isChecked())

    def _highlight(self, active_btn):
        for b in self.side_btns:
            b.setProperty("kind", "side")
            b.setProperty("active", b is active_btn)
            b.style().unpolish(b)
            b.style().polish(b)

    def _reposition_leds(self):
        led_w, led_h = 18, 18
        margin_right = 6

        pos = self.btn_fast.mapTo(self.side_wrap, self.btn_fast.rect().topRight())
        y   = pos.y() + (self.btn_fast.height() - led_h) // 2
        x   = pos.x() - led_w - margin_right
        self.led_fast.move(x, y)
        self.led_fast.raise_()

        pos = self.btn_shot.mapTo(self.side_wrap, self.btn_shot.rect().topRight())
        x = pos.x() - led_w - margin_right
        y = pos.y() + (self.btn_shot.height() - led_h) // 2
        self.led_shot.move(x, y); self.led_shot.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._reposition_leds)

    def closeEvent(self, event):
        """关闭主窗口前，先停掉所有后台线程，避免 QThread destroyed 崩溃"""
        try:
            self.page_comfyui_mini._startup_tab.cleanup()
            self.page_comfyui_mini._gen_tab.cleanup()
        except Exception:
            pass
        super().closeEvent(event)

    def _apply_dark_titlebar(self):
        try:
            hwnd = int(self.winId())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass
