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
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget, QSizePolicy, QLabel, QFrame, QLineEdit,
)
from PyQt5.QtGui import QIcon, QFont, QPixmap
from PyQt5.QtCore import Qt, QTimer
from pages.page_fast_save import PageFastSave
from pages.page_paste import PagePaste
from pages.page_screenshot import PageScreenshot
from pages.page_ratio_calc import PageRatioCalc
from pages.page_overview import PageOverview
from pages.page_ollama_tools import PageOllamaTools
from pages.page_literary_writing import PageLiteraryWriting
from pages.page_douyin import PageDouyin
from pages.page_dir_link import PageDirLink
from pages.page_timezone_fx import PageTimezoneFx
from pages.page_director import PageDirector

# === 新增：主题区域（标题下面一条） ===
from PyQt5.QtCore import QUrl, QSize, Qt
from PyQt5.QtGui import QIcon, QPixmap, QDesktopServices
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from styles.style_all import theme, tk, build_func_card_qss, restyle_all_func_cards

try:
    from utils.server import start_server_thread
except Exception:
    start_server_thread = None

def resource_path(*paths):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *paths)

ASSETS_DIR = resource_path("assets")


class _CurrentOnlyStack(QStackedWidget):
    """v9.9.6 关键修复：普通 QStackedWidget 的 sizeHint()/minimumSizeHint()
    默认是"所有已加入的子页面里最大的那个"，不是只看当前正显示的这一页——这是
    Qt 的一个经典陷阱。也就是说，只要某一个页面（不管现在是不是正显示它）曾经
    被计算出过一个偏大的最小尺寸，整个主窗口就会被这个"历史最大值"钉住，之后
    切回任何别的页面都缩不回去，表现就是"窗口莫名其妙缩不小、好像有什么参数
    把最小高度锁住了"——而且这个锁定和你当前在哪个页面完全无关，很难对上号。
    这里重写这两个方法，只以 currentWidget() 的尺寸为准，其它没在显示的页面
    再怎么样都不会连累主窗口。这是从架构上兜底：就算以后某个页面又冒出类似
    "内容驱动的最小尺寸不稳定"的问题，影响范围也只会局限在那个页面自己被
    显示的时候，不会污染整个程序的窗口尺寸。"""

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return w.minimumSizeHint() if w is not None else super().minimumSizeHint()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("AppRoot")
        self.setAttribute(Qt.WA_StyledBackground, True)

        # 默认浅色平面稿（temp1.png）；深色仍可通过侧栏切换
        self.is_light_theme = True
        self._apply_qss('app_light.qss')
        theme.set_theme("light")

        self.setWindowIcon(QIcon(os.path.join(ASSETS_DIR, 'star.ico')))
        self.setWindowTitle("桌面助手 v9.9")
        self.setMinimumSize(1060, 900)  # 最小尺寸保持不变
        self.resize(1400, 900)
        QTimer.singleShot(0, lambda: self._set_titlebar_theme(False))
        self.setFont(QFont("微软雅黑", 13))

        # 页面堆栈
        self.stack = _CurrentOnlyStack()
        self.stack.setAttribute(Qt.WA_StyledBackground, True)
        self.stack.setObjectName("StackArea")

        # ======= 根布局：侧栏 + 主内容（扁平浮动卡片，无顶部通栏） =======
        outer = QHBoxLayout(self)
        # 左边距收紧：侧栏贴窗；右/上下仍留余量给主内容卡
        outer.setContentsMargins(8, 18, 18, 18)
        # 侧栏与主内容区间距略收，避免中间「空一条」
        outer.setSpacing(8)

        # ── 左侧侧栏 ─────────────────────────────────────
        self.side_wrap = QWidget()
        self.side_wrap.setObjectName("SideBar")
        self.side_wrap.setFixedWidth(220)
        self.side_wrap.setAttribute(Qt.WA_StyledBackground, True)

        side = QVBoxLayout(self.side_wrap)
        # 左 9px（4+5）；右 4px，让菜单更贴近主内容区
        side.setContentsMargins(9, 16, 4, 14)
        side.setSpacing(4)

        # 品牌区：左侧 star.ico（高度约等于标题+副标题两行）
        brand = QWidget()
        brand.setObjectName("SideBrand")
        brand.setAttribute(Qt.WA_StyledBackground, True)
        brand_l = QHBoxLayout(brand)
        brand_l.setContentsMargins(0, 0, 0, 12)
        brand_l.setSpacing(10)
        self.logo = QLabel()
        self.logo.setObjectName("SideLogo")
        self.logo.setFixedSize(40, 40)
        self.logo.setAlignment(Qt.AlignCenter)
        star_path = os.path.join(ASSETS_DIR, "star.ico")
        star_pix = QPixmap(star_path)
        if not star_pix.isNull():
            self.logo.setPixmap(
                star_pix.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.logo.setText("★")
        brand_l.addWidget(self.logo, 0, Qt.AlignVCenter)
        brand_txt = QVBoxLayout()
        brand_txt.setContentsMargins(0, 0, 0, 0)
        brand_txt.setSpacing(0)
        self.lbl_brand_title = QLabel("桌面助手 v9.9")
        self.lbl_brand_title.setObjectName("SideBrandTitle")
        self.lbl_brand_sub = QLabel("给 AI 人的口袋瑞士军刀")
        self.lbl_brand_sub.setObjectName("SideBrandSub")
        brand_txt.addWidget(self.lbl_brand_title)
        brand_txt.addWidget(self.lbl_brand_sub)
        brand_l.addLayout(brand_txt, 1)
        side.addWidget(brand)

        # 导航按钮：统一窄图标（单码位符号），避免 emoji 宽窄不一把文案挤偏
        def _nav(icon: str, label: str) -> QPushButton:
            # 图标固定前缀宽度感：icon + 两个空格 + 文案
            b = QPushButton(f"{icon}  {label}")
            b.setFixedHeight(40)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setProperty("kind", "side")
            b.setProperty("active", False)
            b.setCursor(Qt.PointingHandCursor)
            b.setFlat(True)
            # 不要焦点：点击后 Qt 会把按钮 raise 到浮动 LED 之上，导致勾选框被盖住
            b.setFocusPolicy(Qt.NoFocus)
            b.setStyleSheet("")  # 走 QSS，不吃全局按钮描边
            b.style().unpolish(b); b.style().polish(b)
            return b

        self.btn_overview  = _nav("○", "系统总览")
        self.btn_fast      = _nav("↓", "速存图文")   # 不用 ⬇，避免比其它图标更宽
        self.btn_paste     = _nav("≡", "粘贴助手")
        self.btn_points    = _nav("★", "积分计算")
        self.btn_shot      = _nav("□", "截图工具")
        self.btn_ratio     = _nav("↔", "比例计算")
        self.btn_douyin    = _nav("♪", "抖音下载")
        self.btn_dir_link  = _nav("▣", "目录映射")
        self.btn_tz_fx     = _nav("◎", "时区汇率")
        self.btn_director  = _nav("▷", "导演台")     # 不用 🎬 emoji
        self.btn_ollama_tools = _nav("◇", "Ollama 工具")
        self.btn_literary  = _nav("✎", "文学写作")

        self.side_btns = [
            self.btn_overview, self.btn_fast, self.btn_paste, self.btn_points,
            self.btn_shot, self.btn_ratio, self.btn_douyin,
            self.btn_dir_link, self.btn_tz_fx,
            self.btn_director, self.btn_ollama_tools, self.btn_literary,
        ]

        # LED 指示灯（浮动叠在对应菜单右侧；须始终 raise 在菜单按钮之上）
        self.led_fast = QPushButton("✓")
        self.led_fast.setObjectName("SideLed")
        self.led_fast.setCheckable(True)
        self.led_fast.setChecked(False)
        self.led_fast.setFixedSize(16, 16)
        self.led_fast.setFocusPolicy(Qt.NoFocus)
        self.led_fast.setCursor(Qt.PointingHandCursor)
        self.led_fast.setToolTip("速存全功能：点击一键开/关图片·文本·文件夹")
        self.led_fast.setAttribute(Qt.WA_StyledBackground, True)

        self.led_shot = QPushButton("✓")
        self.led_shot.setObjectName("SideLed")
        self.led_shot.setCheckable(True)
        self.led_shot.setChecked(False)
        self.led_shot.setFixedSize(16, 16)
        self.led_shot.setFocusPolicy(Qt.NoFocus)
        self.led_shot.setCursor(Qt.PointingHandCursor)
        self.led_shot.setToolTip("截图监听：点击开/关")
        self.led_shot.setAttribute(Qt.WA_StyledBackground, True)

        # 右侧给 LED 留空，避免文案顶到勾选框
        for _b in (self.btn_fast, self.btn_shot):
            _b.setProperty("hasLed", True)
            _b.style().unpolish(_b)
            _b.style().polish(_b)

        for b in (
            self.btn_overview, self.btn_fast, self.btn_paste, self.btn_points,
            self.btn_shot, self.btn_ratio, self.btn_douyin,
            self.btn_dir_link, self.btn_tz_fx,
        ):
            side.addWidget(b)

        side.addStretch(1)

        self.lbl_local = QLabel("本地算力")
        self.lbl_local.setObjectName("SideSectionLabel")
        self.lbl_local.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        side.addWidget(self.lbl_local)

        self.sep = QFrame()
        self.sep.setObjectName("SideSep")
        self.sep.setFrameShape(QFrame.HLine)
        side.addWidget(self.sep)
        self._style_sidebar_extras()

        for b in (self.btn_director, self.btn_ollama_tools, self.btn_literary):
            side.addWidget(b)

        # 底栏：设置占位 + 主题切换
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 10, 0, 0)
        foot.setSpacing(6)
        # 与菜单同规范：固定窄图标 + 文案，避免悬停时 padding/字重变化闪动
        self.btn_settings = QPushButton("⚙  设置")
        self.btn_settings.setObjectName("SideFootBtn")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setToolTip("关于软件：版本、下载地址与联系方式")
        self.btn_settings.setFixedHeight(38)
        self.btn_settings.setFlat(True)
        self.btn_settings.setStyleSheet("")
        self.btn_settings.clicked.connect(self._show_settings_about)
        foot.addWidget(self.btn_settings, 1)

        self.btn_theme = QPushButton("🌙")
        self.btn_theme.setObjectName("SideThemeBtn")
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        self.btn_theme.setFlat(False)   # flat 在 Windows 上易吃掉样式/裁切图标
        self.btn_theme.setFixedSize(36, 36)
        self.btn_theme.setMinimumSize(36, 36)
        self.btn_theme.setMaximumSize(36, 36)
        self.btn_theme.setToolTip("切换外观：深色 / 浅色")
        self.btn_theme.clicked.connect(self._toggle_theme)
        foot.addWidget(self.btn_theme, 0, Qt.AlignRight | Qt.AlignVCenter)
        side.addLayout(foot)

        self.led_fast.setParent(self.side_wrap)
        self.led_fast.raise_()
        self.led_shot.setParent(self.side_wrap)
        self.led_shot.raise_()

        # ── 右侧主内容卡片 ─────────────────────────────────────
        content_wrap = QWidget()
        content_wrap.setObjectName("ContentRoot")
        content_wrap.setAttribute(Qt.WA_StyledBackground, True)

        content_layout = QVBoxLayout(content_wrap)
        content_layout.setContentsMargins(18, 14, 18, 14)
        content_layout.setSpacing(10)

        # 顶栏：页面标题 + 搜索提示 + 外链
        self.theme_bar = QWidget()
        self.theme_bar.setObjectName("ThemeBar")
        self.theme_bar.setAttribute(Qt.WA_StyledBackground, True)
        theme_h = QHBoxLayout(self.theme_bar)
        theme_h.setContentsMargins(0, 0, 0, 4)
        theme_h.setSpacing(10)

        self.top_title = QLabel("系统总览")
        self.top_title.setObjectName("PageTitle")
        theme_h.addWidget(self.top_title, 0, Qt.AlignVCenter)
        theme_h.addStretch(1)

        # 顶栏统一控件高度（搜索与右侧 1:1 按钮对齐）
        _hdr_h = 34

        # 顶栏搜索：胶囊外形，高度与右侧按钮一致
        self.search_wrap = QWidget()
        self.search_wrap.setObjectName("HeaderSearch")
        self.search_wrap.setFixedHeight(_hdr_h)
        self.search_wrap.setMinimumWidth(220)
        self.search_wrap.setMaximumWidth(280)
        self.search_wrap.setAttribute(Qt.WA_StyledBackground, True)
        search_l = QHBoxLayout(self.search_wrap)
        search_l.setContentsMargins(14, 0, 12, 0)
        search_l.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("HeaderSearchInput")
        self.search_edit.setPlaceholderText("搜索更多有趣内容")
        self.search_edit.setFrame(False)
        self.search_edit.setClearButtonEnabled(False)
        self.search_icon = QLabel("⌕")
        self.search_icon.setObjectName("HeaderSearchIcon")
        self.search_icon.setAlignment(Qt.AlignCenter)
        self.search_icon.setFixedWidth(20)
        search_l.addWidget(self.search_edit, 1)
        search_l.addWidget(self.search_icon, 0)
        theme_h.addWidget(self.search_wrap, 0, Qt.AlignVCenter)

        # 兼容旧引用名
        self.search_hint = self.search_wrap

        def add_link_text(text: str, url: str, tooltip: str):
            # 1:1 方形按钮，与搜索同高
            btn = QPushButton(text)
            btn.setObjectName("LinkIcon")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFlat(False)
            btn.setFixedSize(_hdr_h, _hdr_h)
            btn.setMinimumSize(_hdr_h, _hdr_h)
            btn.setMaximumSize(_hdr_h, _hdr_h)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            theme_h.addWidget(btn, 0, Qt.AlignVCenter)

        add_link_text("B站", "https://www.bilibili.com/", "B站教程：获取最新 AI 工作流与使用指南")
        add_link_text("❤",  "https://www.buymeacoffee.com/", "赞助与支持：给开发者请杯咖啡 ☕")
        add_link_text("YT",  "https://www.youtube.com/", "YouTube：观看海外超清实操演示")
        add_link_text("🐱",  "https://space.bilibili.com/", "作者主页：关注大胡获取最新动态")

        content_layout.addWidget(self.theme_bar, 0)
        content_layout.addWidget(self.stack, 1)

        # 兼容旧代码引用（隐藏顶栏）
        self.topbar = QWidget()
        self.topbar.setVisible(False)
        self.topbar.setMaximumHeight(0)

        outer.addWidget(self.side_wrap, 0)
        outer.addWidget(content_wrap, 1)

        # ======= 页面注册 =======
        self.page_fast         = PageFastSave()
        self.page_paste        = PagePaste()
        self.page_points       = PagePointsCalc()
        self.page_shot         = PageScreenshot()
        self.page_ratio        = PageRatioCalc()
        self.page_overview     = PageOverview()
        self.page_douyin       = PageDouyin()
        self.page_dir_link     = PageDirLink()
        self.page_tz_fx        = PageTimezoneFx()
        self.page_director     = PageDirector()
        self.page_ollama_tools = PageOllamaTools()
        self.page_literary     = PageLiteraryWriting()

        for p in (
            self.page_overview,
            self.page_fast, self.page_paste, self.page_points, self.page_shot,
            self.page_ratio, self.page_douyin, self.page_dir_link, self.page_tz_fx,
            self.page_director,
            self.page_ollama_tools,
            self.page_literary,
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
        self.btn_paste.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_paste), self.btn_paste))
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
        self.btn_director.clicked.connect(
            lambda: self._switch(self.stack.indexOf(self.page_director), self.btn_director))
        self.btn_ollama_tools.clicked.connect(
            lambda: (
                self._switch(self.stack.indexOf(self.page_ollama_tools), self.btn_ollama_tools),
                self.page_ollama_tools.on_enter()
            )
        )
        self.btn_literary.clicked.connect(
            lambda: (
                self._switch(self.stack.indexOf(self.page_literary), self.btn_literary),
                self.page_literary.on_enter()
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
        # 切页后 currentWidget() 变了，_CurrentOnlyStack 的 sizeHint 也该跟着变——
        # 主动 invalidate 一下，逼 Qt 立刻重新问一遍尺寸，不等下次窗口事件才生效。
        self.stack.updateGeometry()
        # 选中态 polish / 点击焦点会把菜单按钮抬到 LED 上面 → 勾选框“消失”
        self._raise_side_leds()
        QTimer.singleShot(0, self._raise_side_leds)

    def _title_for(self, w: QWidget) -> str:
        if w is getattr(self, "page_overview",     None): return "系统总览"
        if w is getattr(self, "page_fast",         None): return "速存图文"
        if w is getattr(self, "page_paste",        None): return "粘贴助手"
        if w is getattr(self, "page_points",       None): return "积分计算"
        if w is getattr(self, "page_shot",         None): return "截图工具"
        if w is getattr(self, "page_ratio",        None): return "比例计算"
        if w is getattr(self, "page_douyin",       None): return "抖音下载"
        if w is getattr(self, "page_dir_link",     None): return "目录映射"
        if w is getattr(self, "page_tz_fx",        None): return "时区汇率"
        if w is getattr(self, "page_director",     None): return "导演台"
        if w is getattr(self, "page_ollama_tools", None): return "Ollama 工具"
        if w is getattr(self, "page_literary",     None): return "文学写作"
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
        # polish 会打乱叠放顺序，立刻把 LED 抬回最上
        self._raise_side_leds()

    def _raise_side_leds(self):
        """保证侧栏 LED 勾选框画在对应菜单按钮之上（不被选中热区盖住）。"""
        for led in (getattr(self, "led_fast", None), getattr(self, "led_shot", None)):
            if led is None:
                continue
            try:
                led.show()
                led.raise_()
            except Exception:
                pass

    def _reposition_leds(self):
        led_w, led_h = 18, 18
        margin_right = 6

        pos = self.btn_fast.mapTo(self.side_wrap, self.btn_fast.rect().topRight())
        y   = pos.y() + (self.btn_fast.height() - led_h) // 2
        x   = pos.x() - led_w - margin_right
        self.led_fast.move(x, y)

        pos = self.btn_shot.mapTo(self.side_wrap, self.btn_shot.rect().topRight())
        x = pos.x() - led_w - margin_right
        y = pos.y() + (self.btn_shot.height() - led_h) // 2
        self.led_shot.move(x, y)
        self._raise_side_leds()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._reposition_leds)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_leds()

    def closeEvent(self, event):
        """关闭主窗口前，先停掉所有后台线程，避免 QThread destroyed 崩溃"""
        # 速存图文页是挂在 QStackedWidget 里的子页面，Qt 不会单独对它触发
        # closeEvent，所以它自己的定时器/后台检测线程必须在这里手动喊停，
        # 否则会出现"窗口已关、后台线程还在往界面发消息"的报错。
        try:
            self.page_fast.stop_background_checks()
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

    def _apply_qss(self, filename: str):
        """加载应用级样式表，并追加功能区标准卡 QSS（统一圆角/描边/底色）。"""
        qss_path = os.path.join(ASSETS_DIR, filename)
        if os.path.exists(qss_path):
            with open(qss_path, 'r', encoding='utf-8') as f:
                base = f.read()
            # 功能区标准卡：以系统总览三块卡为基准，圆角/配色由 style_all 统一管理
            is_dark = not self.is_light_theme
            base = base + "\n" + build_func_card_qss(is_dark=is_dark)
            QApplication.instance().setStyleSheet(base)

    def _style_sidebar_extras(self):
        """侧边栏「本地算力」标签与分割线（随主题内联）。"""
        self.lbl_local.setStyleSheet(
            f"color: {tk('text_faint')}; font-size: 11px; font-weight: 600; "
            f"padding: 8px 8px 2px 8px; margin: 0; background: transparent;"
        )
        self.sep.setStyleSheet(
            f"QFrame#SideSep{{background:{tk('border')}; max-height:1px; min-height:1px; border:none;}}"
        )

    def _show_settings_about(self):
        """设置按钮：弹出关于信息（风格同抖音页「安装」说明弹窗）。"""
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "关于 · 桌面助手",
            "1. 软件当前版本\n"
            "   桌面助手 v9.9\n\n"
            "2. 软件地址（方便分享）\n"
            "   https://github.com/hbb009/WebImageSaver\n\n"
            "3. 联系方式\n"
            "   邮箱：hubobin3251@gmail.com\n"
            "   微信：15201773251",
        )

    def _toggle_theme(self):
        self.is_light_theme = not self.is_light_theme
        name = "light" if self.is_light_theme else "dark"

        # 浅色界面显示月亮（切到深色）；深色界面显示太阳（切到浅色）
        self.btn_theme.setText("🌙" if self.is_light_theme else "☀")
        self._set_titlebar_theme(not self.is_light_theme)

        # 1) 应用级 QSS
        self._apply_qss('app_light.qss' if self.is_light_theme else 'app.qss')

        # 2) 广播给所有控件级样式的订阅者
        theme.set_theme(name)

        # 3) 主窗口自身的内联样式
        self._style_sidebar_extras()

        # 4) 侧边栏按钮用了 property 选择器，需要重新 polish
        for b in self.side_btns:
            b.style().unpolish(b); b.style().polish(b)
        if hasattr(self, "btn_settings"):
            self.btn_settings.style().unpolish(self.btn_settings)
            self.btn_settings.style().polish(self.btn_settings)
        if hasattr(self, "btn_theme"):
            self.btn_theme.style().unpolish(self.btn_theme)
            self.btn_theme.style().polish(self.btn_theme)

        # 5) 全站功能区标准卡：按新主题重刷内联外观（与系统总览三块一致）
        restyle_all_func_cards(self)

    def _set_titlebar_theme(self, is_dark):
        # 动态控制 Windows 原生标题栏颜色
        try:
            hwnd = int(self.winId())
            value = ctypes.c_int(1 if is_dark else 0)
            for attr in (20, 19):   # 20=新版 Win10/11，19=20H1 之前的旧属性号
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass