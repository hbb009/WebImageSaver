# styles/style_all.py
# ---------------------------------------------------------------------------
# 全站样式合并文件（原 style_theme.py / style_common.py / style_disk_treemap.py /
# style_douyin.py / style_ollama_tools.py / style_sd_comfyui.py 六个文件合并而来）。
#
# 【为什么合并】桌面小程序体量不大，6 个文件之间没有命名冲突，拆分带来的
# "改一处只影响一个文件"收益小于"多开 6 个文件找东西"的成本，遂合一。
#
# 【迁移方式】所有变量名/函数名完全不变，只是**模块路径**变了：
#     原来：from styles.style_theme import theme, tk, fmt
#     原来：from styles.style_common import make_card, install_card_title, ...
#     原来：from styles.style_disk_treemap import TAB_BAR_QSS, ...
#     原来：from styles.style_douyin import PAGE_QSS, ...
#     原来：from styles.style_ollama_tools import TAB_QSS, chk_style, ...
#     原来：from styles.style_sd_comfyui import TABS_QSS, console_qss, ...
#     现在统一改成：
#         from styles.style_all import theme, tk, fmt, make_card, install_card_title, ...
# 具体每个页面要改哪一行，见本次对话里给的迁移清单。
#
# 【结构】本文件从上到下分 6 段，段与段之间用大分隔注释隔开，对应原来的
# 6 个文件，方便你以后想找某段样式时用编辑器搜索段标题即可：
#   1. 主题引擎（原 style_theme.py）—— 全局色板、theme/tk/fmt，其它 5 段都依赖它
#   2. 全局卡片工具箱（原 style_common.py）
#   3. 磁盘分析组件专属（原 style_disk_treemap.py）
#   4. 抖音下载页专属（原 style_douyin.py）
#   5. Ollama 工具 / 文学写作页专属（原 style_ollama_tools.py）
#   6. SD Mini / ComfyUI Mini 专属（原 style_sd_comfyui.py）
# ---------------------------------------------------------------------------

from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtWidgets import (
    QLabel, QGroupBox, QFrame, QBoxLayout, QWidget, QHBoxLayout, QVBoxLayout,
    QSizePolicy, QLineEdit,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 主题引擎（原 styles/style_theme.py）
# ═══════════════════════════════════════════════════════════════════════════
# 全局色板中枢。
#
# 用法：
#   from styles.style_all import theme, tk, fmt
#
#   # 1) 样式模块里定义模板（占位符用 {token}）
#   PANEL_QSS = "QWidget{{ background:{panel}; border:1px solid {border}; }}"
#
#   # 2) 应用时格式化
#   self.setStyleSheet(fmt(PANEL_QSS))
#
#   # 3) 订阅主题变更
#   theme.changed.connect(self.refresh_theme)
#
# 注意：模板里字面量的花括号要写成 {{ }}（Python format 规则）。

# ── 深色（原 app.qss 色系）─────────────────────────────────────
DARK = {
    # 底层
    "bg":           "#0b1124",   # 窗口底
    "panel":        "#141b33",   # 卡片/面板
    "panel_2":      "#0e1530",   # 更深的次级面板（对话气泡、下拉）
    "panel_3":      "#10162c",   # tab 栏
    "panel_deep":   "#080f1c",   # 比 panel_2 更深一层（思考/来源气泡正文）
    "topbar":       "#0f1430",
    "canvas":       "#111110",   # WebEngine / 画布纯黑底

    # 输入控件
    "input_bg":     "#0d1b35",
    "input_bg_ro":  "#0a1428",   # readOnly
    "input_deep":   "#0a1220",   # SD/ComfyUI 的深输入框

    # 描边
    "border":       "#25345c",
    "border_soft":  "#1e2a45",
    "border_2":     "#2a3965",
    "border_3":     "#2d4070",

    # 文字
    "text":         "#d7def7",
    "text_strong":  "#cfe0ff",
    "text_mut":     "#9fb0d7",
    "text_dim":     "#6f7fa8",
    "text_faint":   "#5a6a8a",

    # 交互
    "accent":       "#3a8ee0",
    "accent_hover": "#2f7cc8",
    "accent_dis":   "#2a3454",
    "hover_veil":   "rgba(255,255,255,0.04)",
    "sel_bg":       "#1f3a8a",
    "sel_bg_hover": "#1e4a80",
    "sel_text":     "#93c5fd",
    "row_bg":       "#1a2138",
}

# ── 浅色（temp1.png 扁平平面：柔和灰蓝底 + 白卡片 + 淡紫强调）──
LIGHT = {
    "bg":           "#eef2f7",   # 窗外柔和底
    "panel":        "#ffffff",   # 卡片 / 侧栏
    "panel_2":      "#f8fafc",
    "panel_3":      "#f1f5f9",
    "panel_deep":   "#f1f5f9",
    "topbar":       "#ffffff",
    "canvas":       "#eef2f7",

    "input_bg":     "#f8fafc",
    "input_bg_ro":  "#f1f5f9",
    "input_deep":   "#f8fafc",

    "border":       "#e2e8f0",
    "border_soft":  "#eef2f7",
    "border_2":     "#e2e8f0",
    "border_3":     "#cbd5e1",

    "text":         "#334155",
    "text_strong":  "#0f172a",
    "text_mut":     "#64748b",
    "text_dim":     "#94a3b8",
    "text_faint":   "#94a3b8",

    "accent":       "#6366f1",   # 导航选中 / 强调（靛紫）
    "accent_hover": "#4f46e5",
    "accent_dis":   "#e2e8f0",
    "hover_veil":   "rgba(99,102,241,0.06)",
    "sel_bg":       "#eef2ff",
    "sel_bg_hover": "#e0e7ff",
    "sel_text":     "#4f46e5",
    "row_bg":       "#f8fafc",
}

# ── 语义强调色：两套主题通用，不参与切换 ───────────────────────
# （成功/失败/警告/品牌色 —— 深浅底上都够对比度，无需分叉）
ACCENTS = {
    "ok":      "#22c55e",
    "err":     "#ef4444",
    "warn":    "#f59e0b",
    "brand":   "#f97316",   # 抖音页橙色主题
    "info":    "#3b82f6",
    "purple":  "#a78bfa",
    "cyan":    "#7dd3fc",
}

_PALETTES = {"dark": DARK, "light": LIGHT}


class _ThemeManager(QObject):
    """全局单例。切换主题时发出 changed 信号，各页面自行重刷样式。"""

    changed = pyqtSignal(str)   # 参数：'dark' | 'light'

    def __init__(self):
        super().__init__()
        # 默认浅色，对齐 temp1.png 平面设计稿
        self._name = "light"

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_dark(self) -> bool:
        return self._name == "dark"

    @property
    def tokens(self) -> dict:
        d = dict(_PALETTES[self._name])
        d.update(ACCENTS)
        return d

    def set_theme(self, name: str):
        if name not in _PALETTES:
            raise ValueError(f"未知主题: {name}")
        if name == self._name:
            return
        self._name = name
        self.changed.emit(name)

    def toggle(self) -> str:
        self.set_theme("light" if self._name == "dark" else "dark")
        return self._name


theme = _ThemeManager()


def tk(key: str) -> str:
    """取单个色值：tk('panel') -> '#141b33'"""
    return theme.tokens[key]


def fmt(template: str) -> str:
    """把 {token} 占位符替换成当前主题色值。"""
    return template.format(**theme.tokens)


# 抖音「粘贴并解析」同款主操作按钮（橙渐变 + 深色字）。
# 深/浅主题同色；高度吃全局 padding 4px 14px，不设 min-height。
# 必须写在控件级 stylesheet：父级若 setStyleSheet("background:transparent")，
# 会打断应用级 QSS，字色被 *{color} 盖成浅色叠在橙底上等于「没字」。
BTN_DOWNLOAD_QSS = """
QPushButton#BtnDownload {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #f5ac4d, stop:1 #ea9530);
    border: 1px solid #d97f1e;
    color: #241300;
    font-weight: 700;
    padding: 4px 14px;
}
QPushButton#BtnDownload:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #f8bb66, stop:1 #f0a542);
    border-color: #e08b28;
    color: #241300;
}
QPushButton#BtnDownload:pressed {
    background: #d98a28;
    border-color: #c67a1e;
    color: #241300;
}
QPushButton#BtnDownload:disabled {
    background: rgba(240,165,66,0.35);
    border-color: rgba(240,165,66,0.30);
    color: rgba(36,19,0,0.55);
}
"""


def apply_btn_download(btn) -> None:
    """把按钮做成抖音「粘贴并解析」同款：objectName + 控件级样式 + 字色 palette。"""
    from PyQt5.QtGui import QColor, QPalette
    btn.setObjectName("BtnDownload")
    btn.setStyleSheet(BTN_DOWNLOAD_QSS)
    pal = btn.palette()
    fg = QColor("#241300")
    pal.setColor(QPalette.ButtonText, fg)
    pal.setColor(QPalette.WindowText, fg)
    pal.setColor(QPalette.Text, fg)
    btn.setPalette(pal)


# ═══════════════════════════════════════════════════════════════════════════
# 路径输入框（速存图文「文件夹」同款：圆角外框 + 左侧文件夹图标 + 路径文字）
# ───────────────────────────────────────────────────────────────────────────
# 用法：
#   from styles.style_all import apply_folder_path_edit, restyle_folder_path_edit
#   edit = QLineEdit()
#   act = apply_folder_path_edit(edit)           # 打标 + 加 📁 图标
#   # 主题切换时：
#   restyle_folder_path_edit(edit, act)
#
# 样式：QLineEdit[pathStyle="folder"]（app.qss / app_light.qss）
# ═══════════════════════════════════════════════════════════════════════════

FOLDER_PATH_GLYPH = "📁"
# 路径框左侧图标边长。16 时 emoji 下沿容易被 QLineEdit action 槽裁切，缩一号到 14。
FOLDER_PATH_ICON_PX = 14


def make_glyph_icon(glyph: str = FOLDER_PATH_GLYPH, px: int = 16, color: str = None) -> QIcon:
    """用文字符号画小图标（📁 / ⌨ 等），颜色默认跟当前主题次要文字色。"""
    if not color:
        try:
            color = content_secondary_color()
        except Exception:
            color = tk("text_mut")
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    font = QFont()
    # 字号略小于画布，给 emoji 上下留余量，避免底部被切
    font.setPixelSize(max(10, int(px * 0.78)))
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(pm.rect(), Qt.AlignCenter, glyph)
    painter.end()
    return QIcon(pm)


def apply_folder_path_edit(
    edit: QLineEdit, glyph: str = FOLDER_PATH_GLYPH, px: int = FOLDER_PATH_ICON_PX
):
    """把 QLineEdit 做成「文件夹路径」全局样式：圆角框 + 左侧图标。

    基准：速存图文 → 速存图片 → 文件夹路径框。
    返回 leading QAction（主题切换时 restyle_folder_path_edit 更新图标色）。
    """
    edit.setProperty("pathStyle", "folder")
    try:
        edit.setStyleSheet("")  # 让 QSS pathStyle 生效
    except Exception:
        pass
    for act in list(edit.actions()):
        try:
            if act.property("folderPathIcon"):
                edit.removeAction(act)
        except Exception:
            pass
    icon = make_glyph_icon(glyph, px=px)
    action = edit.addAction(icon, QLineEdit.LeadingPosition)
    action.setProperty("folderPathIcon", True)
    action.setProperty("folderPathGlyph", glyph)
    action.setProperty("folderPathIconPx", int(px))
    st = edit.style()
    if st is not None:
        st.unpolish(edit)
        st.polish(edit)
    edit.update()
    return action


def restyle_folder_path_edit(
    edit: QLineEdit, action=None, glyph: str = None, px: int = None
):
    """主题切换时刷新路径框左侧图标颜色。"""
    if action is None:
        for act in edit.actions():
            if act.property("folderPathIcon"):
                action = act
                break
    if action is None:
        return
    g = glyph or action.property("folderPathGlyph") or FOLDER_PATH_GLYPH
    if px is None:
        stored = action.property("folderPathIconPx")
        try:
            px = int(stored) if stored is not None else FOLDER_PATH_ICON_PX
        except (TypeError, ValueError):
            px = FOLDER_PATH_ICON_PX
    action.setIcon(make_glyph_icon(str(g), px=px))


# ═══════════════════════════════════════════════════════════════════════════
# 2. 全局卡片工具箱（原 styles/style_common.py）
# ═══════════════════════════════════════════════════════════════════════════
# 【不要删除本段】虽然 TEXT_STYLE 等常量是空字符串，但它们被多个页面 import：
#   pages/page_fast_save.py / page_dir_link.py / page_comfyui_mini.py
#   pages/page_screenshot.py / page_sd_mini.py
#
# 空字符串是有意义的：setStyleSheet("") 会清掉控件级样式，
# 让 assets/app.qss（或 app_light.qss）的全局规则接管 —— 这正是主题化想要的。
# 想彻底移除，得先把那 60 多处 setStyleSheet(TEXT_STYLE) 一起删掉。

TEXT_STYLE = ""
BUTTON_STYLE = ""
BUTTON_PRIMARY_STYLE = ""
LINEEDIT_STYLE = ""


# ── 卡片内嵌标题 + 网格对齐（v9.9 界面美容） ──
# 背景：QGroupBox 的原生标题默认画在“外边框线 / 外边距”上，
# 视觉上会把卡片的外层圆角矩形“咬开一个缺口”。
# v9.9   把标题挪到卡片内部顶端（QLabel），圆角矩形保持完整。
# v9.9.1 修复标题颜色被 QSS 级联覆盖导致的颜色/字号不统一。
# v9.9.2 修复更深层的问题：
#   1) 即便标题文字关掉了（setTitle("")），QGroupBox 原生仍会按“是否曾经
#      设置过标题”等隐藏状态，在不同卡片上保留【不完全相同】的预留高度——
#      这是标题上方留白始终对不齐（相差几像素）的根本原因，且这个差值
#      来自 QGroupBox 自身样式引擎的 subControlRect 计算，不可控、无法
#      单纯靠改 QSS 的 margin/padding 消除。
#      解决办法：不再用 QGroupBox 装标题，改用无原生装饰的 QFrame 作卡片
#      容器，边框/圆角/背景全部由我们自己显式画，标题、间距、行高全部由
#      布局代码精确摆放，不存在任何“框架自己偷偷留白”的隐藏变量。这也是
#      macOS/iOS 原生应用常用的做法：系统控件默认装饰不可控时，直接用无
#      装饰容器 + 手工布局取代，保证像素级可预测。
#   2) QLabel 在 Qt 里其实是 QFrame 的子类——给卡片写 `QFrame{...}` 这种
#      裸类型选择器会"连坐"到卡片内部所有 QLabel 身上，这才是"每一行都
#      莫名其妙出现一个边框方块"的真正根因。卡片外观样式必须用 ID 选择器
#      精确限定在卡片自身，不能向下传染给子控件。
#   3) 环境信息/资源监控两栏要逐行对齐，靠 CSS line-height 和"控件默认
#      高度"去凑是凑不齐的（字体行高与控件高度是两套不同的度量）。这里
#      统一改成"固定高度网格行"（make_grid_row）：不管行内放的是文字还是
#      进度条，都装进同样高度的容器里，逐行累加的位置就是完全确定的。

# ═══════════════════════════════════════════════════════════════════════════
# 功能区圆角矩形「标准卡」
# ───────────────────────────────────────────────────────────────────────────
# 基准：系统总览页「环境信息 / 资源监控 / 版本信息」三块区域。
# 统一管理入口（改这里即可全站生效）：
#   · CARD_RADIUS / CARD_BORDER_PX / _CARD_THEME
#   · make_card() / restyle_card_frame() / apply_func_card()
#   · build_func_card_qss()  → 由 ui_main._apply_qss 追加注入应用级样式
# 圆角：14 → 12 → 10（两次各减 2px）。
# ═══════════════════════════════════════════════════════════════════════════

# 配色（亮/暗）；标题色用于 install_card_title
_CARD_THEME = {
    "dark": dict(
        bg="#0f1430", border="#25345c",
        title="#6087BE", primary="#AFC6FF", secondary="#6087BE",
    ),
    "light": dict(
        bg="#ffffff", border="#e2e8f0",
        title="#64748b", primary="#334155", secondary="#64748b",
    ),
}

CARD_RADIUS = 10             # 功能区标准圆角（px）
CARD_BORDER_PX = 1           # 描边宽度
CARD_TITLE_FONT_SIZE = 12    # 标题字号（px）
CARD_TITLE_FONT_WEIGHT = 600 # 标题字重

# 内边距几何（与总览卡一致）
CARD_TOP_GAP = 12
CARD_LEFT_GAP = 12
CARD_RIGHT_GAP = 12
CARD_BOTTOM_GAP = 12
CARD_TITLE_BODY_GAP = 6   # 标题与正文间距（原 10，减 4，避免「环境信息」与「设备名」空得过大）


def _card_colors() -> dict:
    """取当前主题下功能区标准卡配色。"""
    return _CARD_THEME["dark" if theme.is_dark else "light"]


def content_primary_color() -> str:
    """主要文字颜色（如"资源监控"数值/标签），随主题变化。"""
    return _card_colors()["primary"]


def content_secondary_color() -> str:
    """次要文字颜色（如"环境信息"正文，与标题同色），随主题变化。"""
    return _card_colors()["secondary"]


_CARD_FRAME_QSS_TEMPLATE = """
QFrame#{name} {{
    background: {bg};
    border: {bw}px solid {border};
    border-radius: {radius}px;
}}
"""


def make_card(object_name: str) -> QFrame:
    """创建功能区标准卡（QFrame）。

    外观由 restyle_card_frame 按 _CARD_THEME + CARD_RADIUS 内联绘制；
    与系统总览三块卡同规格。object_name 必填且全页唯一（作 QSS id）。
    """
    frame = QFrame()
    frame.setObjectName(object_name)
    frame.setAttribute(Qt.WA_StyledBackground, True)
    apply_func_card(frame)
    restyle_card_frame(frame)
    return frame


def restyle_card_frame(frame: QFrame) -> None:
    """按当前主题重刷 make_card 帧外观；主题切换时调用。"""
    name = frame.objectName() or "FuncCardAnon"
    if not frame.objectName():
        frame.setObjectName(name)
    c = _card_colors()
    frame.setStyleSheet(
        _CARD_FRAME_QSS_TEMPLATE.format(
            name=name,
            bg=c["bg"],
            border=c["border"],
            bw=CARD_BORDER_PX,
            radius=CARD_RADIUS,
        )
    )


def apply_func_card(widget) -> None:
    """把任意 QGroupBox / QFrame 标记为功能区标准卡（供 QSS 统一命中）。"""
    try:
        widget.setProperty("funcCard", "1")
        widget.setAttribute(Qt.WA_StyledBackground, True)
        # 触发 property 选择器重新匹配
        st = widget.style()
        if st is not None:
            st.unpolish(widget)
            st.polish(widget)
        widget.update()
    except Exception:
        pass


def restyle_func_area(widget) -> None:
    """按功能区标准卡规格，内联刷写 QFrame / QGroupBox 外观。

    与 make_card / 系统总览三块卡同底色、同描边、同圆角（CARD_RADIUS）。
    优先走内联样式，避免被其它 QSS 规则冲掉；主题切换时由主窗口批量调用。
    """
    apply_func_card(widget)
    name = widget.objectName()
    if not name:
        name = f"FuncArea_{id(widget) & 0xFFFFFF:x}"
        widget.setObjectName(name)
    c = _card_colors()
    r, bw = CARD_RADIUS, CARD_BORDER_PX
    bg, border = c["bg"], c["border"]

    if isinstance(widget, QGroupBox):
        # 原生标题已由 install_card_title 清空；::title 收成 0，避免边框缺口
        widget.setStyleSheet(
            f"QGroupBox#{name}{{"
            f"background:{bg};border:{bw}px solid {border};"
            f"border-radius:{r}px;margin-top:0px;padding-top:4px;}}"
            f"QGroupBox#{name}::title{{"
            f"subcontrol-origin:margin;left:0;top:0;padding:0;"
            f"height:0px;width:0px;color:transparent;border:none;}}"
        )
    elif isinstance(widget, QFrame):
        restyle_card_frame(widget)
    else:
        widget.setStyleSheet(
            f"#{name}{{background:{bg};border:{bw}px solid {border};"
            f"border-radius:{r}px;}}"
        )


def restyle_all_func_cards(root: QWidget) -> None:
    """遍历 root 子树，重刷所有 funcCard=1 的功能区（主题切换时调用）。"""
    if root is None:
        return
    try:
        if str(root.property("funcCard")) == "1":
            restyle_func_area(root)
    except Exception:
        pass
    for w in root.findChildren(QWidget):
        try:
            if str(w.property("funcCard")) == "1":
                restyle_func_area(w)
        except Exception:
            pass


def build_func_card_qss(is_dark: bool = None) -> str:
    """生成功能区标准卡的应用级 QSS 片段（亮/暗各一套）。

    挂到 ui_main._apply_qss 末尾，覆盖 app*.qss 里旧的分散圆角规则，
    保证全站功能区（titleVariant=accent / variant=card / CalcTopBox 等）
    与系统总览三块卡同圆角、同描边、同底色。
    """
    if is_dark is None:
        is_dark = theme.is_dark
    c = _CARD_THEME["dark" if is_dark else "light"]
    r = CARD_RADIUS
    bw = CARD_BORDER_PX
    # 选择器：属性标记 + 历史兼容选择器 + 常见功能区 objectName
    return f"""
/* ════ 功能区标准卡 · style_all.build_func_card_qss · radius={r}px ════ */
QFrame[funcCard="1"],
QGroupBox[funcCard="1"],
QGroupBox[titleVariant="accent"],
QGroupBox[variant="card"],
QGroupBox[card="1"],
QGroupBox#CalcTopBox,
QGroupBox#RecordsBox,
QGroupBox#CardShotEnable,
QGroupBox#CardShotHotkey,
QGroupBox#CardShotOutput,
QGroupBox#CardShotLog,
QGroupBox#CardShotPreview,
QGroupBox#CardFastAuto,
QGroupBox#CardFastManual,
QFrame#PanelCard,
QWidget#FuncPanel {{
    background: {c["bg"]};
    border: {bw}px solid {c["border"]};
    border-radius: {r}px;
}}
QGroupBox[funcCard="1"]::title,
QGroupBox[titleVariant="accent"]::title,
QGroupBox[variant="card"]::title,
QGroupBox[card="1"]::title,
QGroupBox#CalcTopBox::title,
QGroupBox#RecordsBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 4px 6px;
    background: {c["bg"]};
    color: {c["title"]};
    font-size: {CARD_TITLE_FONT_SIZE}px;
    font-weight: {CARD_TITLE_FONT_WEIGHT};
}}
"""


def _title_qss(color: str) -> str:
    return (
        "QLabel{{background:transparent; color:{color}; "
        "font-size:{size}px; font-weight:{weight};}}"
    ).format(color=color, size=CARD_TITLE_FONT_SIZE, weight=CARD_TITLE_FONT_WEIGHT)


def install_card_title(box, layout: QBoxLayout, title: str, gap: int = None) -> QLabel:
    """把卡片标题放到 layout 内部顶端，并标记为功能区标准卡。

    标题与正文间距统一由全局 CARD_TITLE_BODY_GAP 控制（默认 6px），
    实现方式：标题包在 head 容器里，底部 margin = gap。
    这样即使 layout.setSpacing(n) > 0，也不会和 insertSpacing 再叠一层空隙。

    同时兼容两种容器：
      - QGroupBox（旧写法，会调用 setTitle("") 关闭原生标题）
      - QFrame / 其它普通容器（新写法，没有原生标题可关，直接跳过）

    参数：
        box   —— 目标容器（QGroupBox 或 QFrame）
        layout—— 该容器自己的顶层布局（QVBoxLayout / QHBoxLayout 均可）
        title —— 标题文字
        gap   —— 标题与正文间距；None 则用 CARD_TITLE_BODY_GAP（推荐不传，走全局）
    返回：
        新建的标题 QLabel（role="card-title"，主题切换时 restyle_card_title）
    """
    if gap is None:
        gap = CARD_TITLE_BODY_GAP
    gap = max(0, int(gap))

    # 凡走 install_card_title 的区域一律视为功能区标准卡（内联刷外观）
    if hasattr(box, "setTitle"):
        box.setTitle("")                     # QGroupBox：关闭原生标题，避免其画在边框线上打断圆角矩形
    restyle_func_area(box)

    lbl = QLabel(title)
    lbl.setProperty("role", "card-title")
    restyle_card_title(lbl)
    lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    # 标题头：底部空隙由全局 CARD_TITLE_BODY_GAP 控制。
    # layout.setSpacing(S) 会在 head 与下一控件之间再加 S，故底部 margin 取
    # max(0, gap - S)，使「标题文字 → 正文」总距约等于 gap，全站统一可调。
    lay_sp = max(0, int(layout.spacing()))
    bottom = max(0, gap - lay_sp)

    head = QWidget()
    head.setObjectName("CardTitleHead")
    head.setAttribute(Qt.WA_StyledBackground, True)
    head.setStyleSheet("background: transparent; border: none;")
    head.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    head_l = QVBoxLayout(head)
    head_l.setContentsMargins(0, 0, 0, bottom)
    head_l.setSpacing(0)
    head_l.addWidget(lbl)

    layout.insertWidget(0, head)
    return lbl


def restyle_card_title(label: QLabel) -> None:
    """按当前主题重新刷标题颜色；主题切换时调用一次即可。"""
    label.setStyleSheet(_title_qss(_card_colors()["title"]))


def make_grid_row(row_height: int, spacing: int = 8) -> tuple:
    """创建一个【固定高度】的横向行容器，用于让不同卡片的多行内容
    严格按同一网格对齐（类似排版里的“基线网格”）。
    不管行内放的是文字 QLabel 还是 QProgressBar，只要都装进这个固定
    高度的容器里，逐行累加下来的纵向位置就是完全确定、可预测的，
    不会因为字体行高、控件默认高度等“隐藏变量”产生累积误差。

    返回 (row_widget, row_layout)，调用方把内容加到 row_layout 里，
    再把 row_widget 加到卡片的外层 QVBoxLayout 上。
    """
    row_widget = QWidget()
    row_widget.setFixedHeight(row_height)
    # 显式透明背景：全局有一条 QWidget { background: ... } 规则，
    # 会给所有"裸" QWidget 刷上不透明底色；这里必须显式覆盖，否则每一行
    # 会变成一个视觉上的"色块"，而不是融入卡片背景。
    # 必须带 #id：无选择器的 background 会级联到子控件（如进度条），冲掉轨道底色。
    row_widget.setObjectName("GridRow")
    row_widget.setStyleSheet("#GridRow{background:transparent;}")
    row_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    row_layout = QHBoxLayout(row_widget)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(spacing)
    return row_widget, row_layout


# ═══════════════════════════════════════════════════════════════════════════
# 3. 磁盘分析组件专属（原 styles/style_disk_treemap.py）
# ═══════════════════════════════════════════════════════════════════════════
# 磁盘分析组件（pages/disk_treemap_widget.py）专属样式。
#
# 【使用方式】所有常量都是模板，必须包 fmt()：
#     from styles.style_all import fmt, TAB_BAR_QSS
#     self.tab_bar.setStyleSheet(fmt(TAB_BAR_QSS))
#
# 并在 __init__ 末尾加：  theme.changed.connect(self.refresh_theme)
#
# 【模板语法】字面花括号写成 {{ }}。
#
# 依赖运行时数据的颜色（DriveTabSub 的使用率红/橙/灰警告色）仍留在
# Python 代码中动态生成，本段只管与数据无关的静态样式。

# ── DriveTab（盘符 Tab 卡片）──────────────────────────────────────────

# 激活状态（accent 高亮 + 下划线）
DRIVE_TAB_ACTIVE_QSS = "#DriveTab {{ background: {hover_veil}; border-radius: 0; }}"
DRIVE_TAB_ACTIVE_MAIN_QSS = "color:{accent}; background:transparent;"
DRIVE_TAB_ACTIVE_UNDERLINE_QSS = "background:{accent}; border-radius: 0;"

# 非激活状态（透明 + hover 淡亮）
DRIVE_TAB_INACTIVE_QSS = (
    "#DriveTab {{ background: transparent; border-radius: 0; }}"
    "#DriveTab:hover {{ background: {hover_veil}; }}"
)
DRIVE_TAB_INACTIVE_MAIN_QSS = "color:{text_mut}; background:transparent;"
DRIVE_TAB_INACTIVE_UNDERLINE_QSS = "background: transparent; border-radius: 0;"

# 磁盘图标 emoji label
DRIVE_ICON_QSS = "font-size:17px; background:transparent;"

# 主标签（盘符名）正常态背景（字体/颜色在 _apply_style 里动态设置）
DRIVE_MAIN_BASE_QSS = "background:transparent;"

# ── Tab 栏容器 ─────────────────────────────────────────────────────────
TAB_BAR_QSS = "#DiskTabBar {{ background: {panel_3}; border-bottom: 1px solid {border}; }}"

# 扫描控制条
SCAN_BAR_QSS = "background:{panel}; border-bottom:1px solid {border};"

# 扫描按钮
SCAN_BTN_QSS = (
    "QPushButton {{ background:{accent}; color:#ffffff; border:none; border-radius:6px; "
    "padding:0 16px; font-size:12px; font-weight:600; }}"
    "QPushButton:hover {{ background:{accent_hover}; }}"
    "QPushButton:disabled {{ background:{accent_dis}; color:{text_dim}; }}"
)

# 扫描进度条
SCAN_PROGRESS_QSS = (
    "QProgressBar {{ background:{row_bg}; border:none; border-radius:4px; }}"
    "QProgressBar::chunk {{ background:{accent}; border-radius:4px; }}"
)

# 扫描状态文字
SCAN_STATUS_QSS = "color:{text_dim}; font-size:11px; background:transparent;"

# ── 右侧大文件排行榜面板 ───────────────────────────────────────────────
FILES_PANEL_QSS = "background:{panel_2}; border-left:1px solid {border};"

# 面板标题
FILES_TITLE_QSS = "color:{text_mut}; font-size:12px; font-weight:600; background:transparent;"

# 文件列表（透明底，无边框）
FILES_LIST_QSS = (
    "QListWidget{{background:transparent; border:none;}}"
    "QListWidget::item{{border:none; padding:0;}}"
)

# WebEngine 回退提示（无 PyQtWebEngine 时）
FALLBACK_LABEL_QSS = "color:{err}; font-size:13px; background:{canvas};"

# WebEngine 视图
WEB_VIEW_QSS = "background:{canvas}; border:none;"

# ── _FileRankRow（文件排行条目）────────────────────────────────────────
FILE_RANK_ROW_QSS = "_FileRankRow {{ background:{row_bg}; border-radius:6px; }}"

FILE_RANK_NUM_QSS  = "color:{text_faint}; font-size:11px; background:transparent;"
FILE_RANK_NAME_QSS = "color:{text}; font-size:12px; background:transparent;"
FILE_RANK_SIZE_QSS = "color:{accent}; font-size:11px; font-weight:600; background:transparent;"


# ═══════════════════════════════════════════════════════════════════════════
# 4. 抖音下载页专属（原 styles/style_douyin.py）
# ═══════════════════════════════════════════════════════════════════════════
# 抖音下载页（pages/page_douyin.py）专属样式。
# 该页主色调为橙色（brand），与全局蓝色体系有意区分 —— 橙色是语义/品牌色，
# 两套主题通用，不参与切换；底色、边框、文字则跟随主题。
#
# 【使用方式】必须包 fmt()：
#     from styles.style_all import fmt, PAGE_QSS
#     self.setStyleSheet(fmt(PAGE_QSS))

# 页面根组件样式（setStyleSheet 到 PageDouyin 自身）
PAGE_QSS = """
    QWidget {{ color: {text}; }}
    QLineEdit {{
        background: {input_bg}; color: {text};
        border: 1px solid {border_2}; border-radius: 4px;
        padding: 4px 8px; font-family: Consolas;
    }}
    QLineEdit:focus {{ border-color: {brand}; }}
    QLineEdit[readOnly="true"] {{
        background: {input_bg_ro}; color: {text_mut};
        border-color: {border_soft};
    }}
    QPushButton#BtnParse, QPushButton#BtnDownload {{
        background: {brand}; color: #ffffff;
        border: none; border-radius: 4px;
        padding: 6px 18px; font-weight: bold; font-size: 13px;
    }}
    QPushButton#BtnParse:hover, QPushButton#BtnDownload:hover {{
        background: #ea580c;
    }}
    QPushButton#BtnParse:disabled, QPushButton#BtnDownload:disabled {{
        background: {accent_dis}; color: {text_dim};
    }}
    QPushButton#BtnSmall {{
        background: {panel}; color: {text_mut};
        border: 1px solid {border_2}; border-radius: 4px;
        padding: 4px 10px; font-size: 12px;
    }}
    QPushButton#BtnSmall:hover {{ background: {panel_3}; color: {text_strong}; }}
    QPushButton#BtnCancel {{
        background: transparent; color: {err};
        border: 1px solid {err}; border-radius: 4px;
        padding: 4px 10px; font-size: 12px;
    }}
    QTextEdit {{
        background: {input_bg}; color: {text};
        border: none; font-family: Consolas; font-size: 11px;
    }}
    QProgressBar {{
        background: {panel}; border: 1px solid {border_3};
        border-radius: 4px; height: 22px;
        color: {text}; font-size: 12px; font-weight: bold;
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {brand}; border-radius: 3px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QLabel#SecTitle {{ color: {text_mut}; font-size: 12px; }}
    QLabel#StatusLbl {{ font-size: 12px; }}
"""

# GroupBox 卡片样式（左侧「下载设置」、右侧「Cookie + 链接」共用）
GB_STYLE = """
    QGroupBox {{
        color: {text_dim};
        font-size: 11px;
        border: 1px solid {border_3};
        border-radius: 6px;
        margin-top: 8px;
        padding: 6px 8px 6px 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        top: 0px;
        padding: 0 4px;
        background: {panel_2};
    }}
"""

# 媒体选择区分隔线
DIVIDER_QSS = "QFrame{{background:{border_3}; max-height:1px; min-height:1px;}}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Ollama 工具 / 文学写作页专属（原 styles/style_ollama_tools.py）
# ═══════════════════════════════════════════════════════════════════════════
# 服务于两个页面：
#     pages/page_ollama_tools.py
#     pages/page_literary_writing.py
#
# 【使用方式】
#   除 chk_style() 外，所有常量都是模板，必须包 fmt()：
#       from styles.style_all import fmt, TAB_QSS
#       self.tabs.setStyleSheet(fmt(TAB_QSS))
#
#   chk_style() 返回的已是成品 QSS，**不要**再包 fmt()。
#
# 【模板语法】字面花括号必须写成 {{ }}，否则 str.format 会报错。

# Tab 容器 QSS（作用域：#OllamaTabWidget，不污染全局）
TAB_QSS = """
/* ── pane：带圆角边框的内容容器，左下右下圆角，顶部与 Tab 衔接 ── */
QTabWidget#OllamaTabWidget::pane {{
    border: 1px solid {border_3};
    border-top: none;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
    background: {panel_2};
    margin-top: 0px;
}}
/* ── Tab 栏背景 ── */
QTabWidget#OllamaTabWidget > QTabBar {{
    background: transparent;
}}
/* ── 默认 Tab ── */
QTabWidget#OllamaTabWidget > QTabBar::tab {{
    background: {panel};
    color: {text_mut};
    padding: 6px 24px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid {border_3};
    border-bottom: none;
    font-size: 14px;
}}
/* ── 激活 Tab：底部与 pane 颜色一致，视觉上融合 ── */
QTabWidget#OllamaTabWidget > QTabBar::tab:selected {{
    background: {panel_2};
    color: {text_strong};
    border-color: {border_3};
    font-weight: bold;
}}
/* ── Hover ── */
QTabWidget#OllamaTabWidget > QTabBar::tab:hover:!selected {{
    background: {panel_3};
    color: {text};
}}
/* ── 内容区分割线 ── */
QFrame#SectionLine {{
    background: {border_3};
    max-height: 1px;
    min-height: 1px;
}}
/* ── 刷新按钮（图标式，无文字） ── */
QPushButton#BtnRefreshIcon {{
    background: {panel};
    border: 1px solid {border_soft};
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 16px;
    color: {text_mut};
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
}}
QPushButton#BtnRefreshIcon:hover   {{ background:{panel_3}; color:{text_strong}; }}
QPushButton#BtnRefreshIcon:pressed {{ background:{panel_2}; }}
/* ── 状态点 ── */
QLabel#StatusDot {{
    font-size: 12px;
}}

/* ── 联网 / 深度思考 切换按钮 ── */
QPushButton#BtnToggle {{
    background: {panel};
    border: 1px solid {border_3};
    border-radius: 14px;
    padding: 3px 14px;
    font-size: 13px;
    color: {text_mut};
    min-height: 28px;
}}
QPushButton#BtnToggle:hover {{ background: {panel_3}; color: {text}; }}
QPushButton#BtnToggle[active="true"] {{
    background: {sel_bg};
    border: 1px solid {info};
    color: {sel_text};
    font-weight: bold;
}}
QPushButton#BtnToggle[active="true"]:hover {{ background: {sel_bg_hover}; }}
"""

# 批量打标文件列表样式
LIST_BATCH_QSS = (
    "QListWidget{{border:none; background:transparent;}}"
    "QListWidget::item:hover{{background:{panel_3};}}"
)

# 对话气泡列表样式
LIST_CHAT_QSS = (
    "QListWidget,QListWidget::item{{background:transparent; border:none;}}"
    "QListWidget::item:hover{{background:transparent;}}"
    "QListWidget::item:selected{{background:transparent;}}"
)

# 深度思考气泡：标题
THINK_TITLE_QSS = (
    "color:{text_dim}; font-size:11px; font-weight:bold;"
    "padding:4px 8px; background:{panel_2};"
    "border:1px solid {border_3}; border-radius:4px;"
)

# 深度思考气泡：正文
THINK_BODY_QSS = (
    "color:{text_dim}; font-size:11px; padding:6px 10px;"
    "background:{panel_deep}; border:1px solid {border_2};"
)

# 参考来源气泡：标题
SRC_TITLE_QSS = (
    "color:{info}; font-size:11px; font-weight:bold;"
    "padding:4px 8px; background:{panel_2};"
    "border:1px solid {border_3}; border-radius:4px;"
)

# 参考来源气泡：正文容器
SRC_BODY_QSS = (
    "background:{panel_deep}; border:1px solid {border_2};"
    "border-radius:4px; margin-top:2px;"
)

# 参考来源链接标签
SRC_LINK_QSS = "color:{accent}; padding:2px 4px;"

# 输入框（无边框）
INPUT_TRANSPARENT_QSS = "QTextEdit{{border:none; background:{panel_2};}}"

# 反推预览框（虚线边框）
REV_PREVIEW_QSS = "QFrame#RevPreview{{border:1px dashed {border};border-radius:6px;}}"

# 反推：信息小字色
REV_INFO_QSS = "color:{text_mut}; font-size:12px;"

# 反推：EN 输出框
REV_EN_QSS = "QTextEdit{{border:none; background:transparent;}}"

# 时间戳标签
TIME_LABEL_QSS = "color:{text_faint}; font-size:12px;"

# 思考中动画点
THINKING_DOT_QSS = "font-size:13px;"

# 思考中文本
THINKING_TEXT_QSS = "color:{text_faint}; font-size:12px;"

# 用户气泡（原来内联写在 pages/page_ollama_tools.py L987
# 与 pages/page_literary_writing.py L556，两处重复，统一收到这里）
BUBBLE_USER_QSS = (
    "QLabel#ChatBubbleUser{{background:{panel_2};border:1px solid {border_2};"
    "border-radius:10px;padding:8px 12px;color:{text};}}"
)


# ── 复选框：带真实勾形的 SVG indicator ──────────────────────────────────
# 原实现每次调用都 mkstemp 一个新文件且从不清理。主题切换会重复触发，
# 长时间运行会在 %TEMP% 里堆积成百上千个 chk_*.svg。改为按 size 缓存。
_CHECK_SVG_CACHE = {}


def _check_svg_path(size: int) -> str:
    """返回指定尺寸勾形 SVG 的文件路径（同一 size 只写一次）。"""
    if size in _CHECK_SVG_CACHE:
        return _CHECK_SVG_CACHE[size]

    import tempfile, os
    m = round(size * 0.14, 1)
    pts = "{},{} {},{} {},{}".format(
        m,                      round(size * 0.52, 1),
        round(size * 0.42, 1),  round(size - m, 1),
        round(size - m, 1),     m,
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg"'
        ' width="{s}" height="{s}" viewBox="0 0 {s} {s}">'.format(s=size) +
        '<polyline points="{}" stroke="white" stroke-width="2"'.format(pts) +
        ' fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )
    fd, path = tempfile.mkstemp(suffix=".svg", prefix="chk_")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(svg)
    path = path.replace("\\", "/")
    _CHECK_SVG_CACHE[size] = path
    return path


def chk_style(bg: str, border: str, text_color: str, bold: bool, size: int = 15) -> str:
    """
    生成 QCheckBox 样式。

    bg / border / text_color 是「选中态」的语义强调色，由调用方传入
    （如联网=蓝、深度思考=紫），两套主题通用，不参与切换。
    「未选中态」的底色/边框/文字跟随主题。

    返回值已是最终 QSS，**不需要再包 fmt()**。
    """
    path = _check_svg_path(size)
    bold_str = "bold" if bold else "normal"
    label_size = 13 if size >= 15 else 12

    return (
        "QCheckBox{{color:{c}; font-size:{fs}px; spacing:6px;}}".format(
            c=tk("text_mut"), fs=label_size) +
        "QCheckBox::indicator{{width:{s}px; height:{s}px;"
        " border:1px solid {bd}; border-radius:3px; background:{bgc};}}".format(
            s=size, bd=tk("border_3"), bgc=tk("panel")) +
        "QCheckBox::indicator:checked{{background:{bg}; border-color:{br};"
        " image:url({p});}}".format(bg=bg, br=border, p=path) +
        "QCheckBox:checked{{color:{tc}; font-weight:{b};}}".format(
            tc=text_color, b=bold_str)
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. SD Mini / ComfyUI Mini 专属（原 styles/style_sd_comfyui.py）
# ═══════════════════════════════════════════════════════════════════════════
# SD Mini（pages/page_sd_mini.py）与 ComfyUI Mini（pages/page_comfyui_mini.py）共用样式。
# 两个页面的 Tab 结构、滚动区、进度条样式几乎完全相同，统一在此管理。
#
# 【使用方式】所有常量都是模板，必须包 fmt()：
#     from styles.style_all import fmt, TABS_QSS
#     self.tabs.setStyleSheet(fmt(TABS_QSS))
#
# 【模板语法】字面花括号写成 {{ }}。

# Tab 控件样式（underline 风格，无 pane 边框）
TABS_QSS = (
    "QTabWidget::pane{{border:none;}}"
    "QTabBar::tab{{background:{input_deep};color:{text_dim};padding:8px 20px;"
    "  border-bottom:2px solid transparent;font-size:13px;}}"
    "QTabBar::tab:selected{{color:{text_mut};border-bottom:2px solid {accent};}}"
    "QTabBar::tab:hover{{color:{text};}}"
)

# 左侧可滚动面板
SCROLL_LEFT_QSS = (
    "QScrollArea{{border:none;background:transparent;}}"
    "QScrollBar:vertical{{width:6px;background:{input_deep};}}"
    "QScrollBar::handle:vertical{{background:{border_3};border-radius:3px;}}"
)

# 生成进度条
PROGRESS_QSS = (
    "QProgressBar{{background:{input_deep};border:1px solid {border_3};border-radius:3px;"
    "color:{text_mut};font-size:11px;}}"
    "QProgressBar::chunk{{background:{accent};border-radius:3px;}}"
)

# 预览区占位图
PREVIEW_PLACEHOLDER_QSS = (
    "background:{input_deep};border:1px solid {border_3};border-radius:4px;"
    "color:{text_dim};font-size:13px;"
)

# 生成状态提示标签（提示文字小字色）
HINT_LABEL_QSS = "color:{text_dim};font-size:12px;"

# 状态标签：中性跟随主题，成功/失败用语义色（两套主题通用）
STATUS_NEUTRAL_QSS = "color:{text_mut};font-size:13px;"
STATUS_OK_QSS      = "color:{ok};font-size:13px;"
STATUS_ERR_QSS     = "color:{err};font-size:13px;"

# 节点标题（启动页 section 标题）
SECTION_TITLE_QSS = "color:{text_mut};font-size:18px;font-weight:bold;"

# 节点分隔线
SEPARATOR_QSS = "color:{border_3};"

# 提示 tips 小字
TIPS_QSS = "color:{text_dim};font-size:12px;"

# 参数信息 label/value 对（右侧元数据行）
META_LABEL_QSS = "color:{text_dim};font-size:12px;"
META_VALUE_QSS = "color:{text};font-size:12px;"

# ── SD Mini 专属：SD 命令文本框（只在 CmdPanel 使用）──
CMD_TEXT_QSS = (
    "QPlainTextEdit{{background:{panel_deep};color:{text_mut};"
    "border:none;font-family:Consolas,monospace;font-size:11px;}}"
)

# ── SD Mini 专属：架构提示（警告色用语义色）──
ARCH_HINT_NORMAL_QSS = "color:{text_dim};font-size:12px;"
ARCH_HINT_WARN_QSS   = "color:{warn};font-size:12px;"

# 采样参数小标签
ARCH_LABEL_QSS = "color:{text_mut};font-size:12px;font-weight:bold;"

# 模型选择按钮：未选中 / 选中（TabButton 切换）
TAB_BTN_NORMAL = (
    "background:{input_deep};border:1px solid {border_3};border-radius:4px;"
    "color:{text_dim};font-size:11px;padding:4px 2px;"
)
TAB_BTN_SELECTED = (
    "background:{sel_bg};border:1px solid {accent};border-radius:4px;"
    "color:{sel_text};font-size:11px;padding:4px 2px;"
)


# ── 命令输出控制台（CmdPanel）────────────────────────────────────────
# 黑底绿字是终端观感，两套主题下都保持深色（与 treemap 画布同理）。
# 想让它跟随主题，把 CONSOLE_FIXED 改成 False。
CONSOLE_FIXED = True

_CONSOLE_DARK = (   # 成品 QSS，不要 fmt()
    "QPlainTextEdit{background:#0c0e12;color:#39ff80;border:none;}"
    "QScrollBar:vertical{width:6px;background:#0c0e12;}"
    "QScrollBar::handle:vertical{background:#1e4030;border-radius:3px;}"
)

_CONSOLE_THEMED_TPL = (   # 模板，需 fmt()
    "QPlainTextEdit{{background:{panel_deep};color:{ok};border:none;}}"
    "QScrollBar:vertical{{width:6px;background:{panel_deep};}}"
    "QScrollBar::handle:vertical{{background:{border_3};border-radius:3px;}}"
)


def console_qss() -> str:
    """返回控制台样式（成品 QSS，不需要再包 fmt()）。"""
    if CONSOLE_FIXED:
        return _CONSOLE_DARK
    return fmt(_CONSOLE_THEMED_TPL)
