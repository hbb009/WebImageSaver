# styles/page_ollama_tools.py
# Ollama 工具页（PageOllamaTools）专属样式

# Tab 容器 QSS（作用域：#OllamaTabWidget，不污染全局）
TAB_QSS = """
/* ── pane：带圆角边框的内容容器，左下右下圆角，顶部与 Tab 衔接 ── */
QTabWidget#OllamaTabWidget::pane {
    border: 1px solid #2d4070;
    border-top: none;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
    background: #0d1525;
    margin-top: 0px;
}
/* ── Tab 栏背景 ── */
QTabWidget#OllamaTabWidget > QTabBar {
    background: transparent;
}
/* ── 默认 Tab ── */
QTabWidget#OllamaTabWidget > QTabBar::tab {
    background: #111827;
    color: #8b9ab8;
    padding: 6px 24px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #2d4070;
    border-bottom: none;
    font-size: 14px;
}
/* ── 激活 Tab：底部与 pane 颜色一致，视觉上融合 ── */
QTabWidget#OllamaTabWidget > QTabBar::tab:selected {
    background: #0d1525;
    color: #e2e8f0;
    border-color: #2d4070;
    font-weight: bold;
}
/* ── Hover ── */
QTabWidget#OllamaTabWidget > QTabBar::tab:hover:!selected {
    background: #162035;
    color: #c8d4ec;
}
/* ── 内容区分割线（蓝色） ── */
QFrame#SectionLine {
    background: #2d4070;
    max-height: 1px;
    min-height: 1px;
}
/* ── 刷新按钮（图标式，无文字） ── */
QPushButton#BtnRefreshIcon {
    background: #111827;
    border: 1px solid #1e2a45;
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 16px;
    color: #8b9ab8;
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
}
QPushButton#BtnRefreshIcon:hover  { background:#162035; color:#e2e8f0; }
QPushButton#BtnRefreshIcon:pressed{ background:#0d1525; }
/* ── 状态点 ── */
QLabel#StatusDot {
    font-size: 12px;
}

/* ── 联网 / 深度思考 切换按钮 ── */
QPushButton#BtnToggle {
    background: #111827;
    border: 1px solid #2d4070;
    border-radius: 14px;
    padding: 3px 14px;
    font-size: 13px;
    color: #8b9ab8;
    min-height: 28px;
}
QPushButton#BtnToggle:hover { background: #162035; color: #c8d4ec; }
QPushButton#BtnToggle[active="true"] {
    background: #0f3460;
    border: 1px solid #3b82f6;
    color: #93c5fd;
    font-weight: bold;
}
QPushButton#BtnToggle[active="true"]:hover { background: #1e4a80; }
"""

# 批量打标文件列表样式
LIST_BATCH_QSS = (
    "QListWidget{border:none; background:transparent;}"
    "QListWidget::item:hover{background:#162035;}"
)

# 对话气泡列表样式
LIST_CHAT_QSS = (
    "QListWidget,QListWidget::item{background:transparent; border:none;}"
    "QListWidget::item:hover{background:transparent;}"
    "QListWidget::item:selected{background:transparent;}"
)

# 深度思考气泡：标题
THINK_TITLE_QSS = (
    "color:#64748b; font-size:11px; font-weight:bold;"
    "padding:4px 8px; background:#0d1a2d;"
    "border:1px solid #1e3a5f; border-radius:4px;"
)

# 深度思考气泡：正文
THINK_BODY_QSS = (
    "color:#4a6080; font-size:11px; padding:6px 10px;"
    "background:#080f1c; border:1px solid #1a2e4a;"
)

# 参考来源气泡：标题
SRC_TITLE_QSS = (
    "color:#3b82f6; font-size:11px; font-weight:bold;"
    "padding:4px 8px; background:#0a1628;"
    "border:1px solid #1e3a6e; border-radius:4px;"
)

# 参考来源气泡：正文容器
SRC_BODY_QSS = "background:#060e1c; border:1px solid #1a2e4a; border-radius:4px; margin-top:2px;"

# 参考来源链接标签
SRC_LINK_QSS = "color:#60a5fa; padding:2px 4px;"

# 输入框（无边框透明底）
INPUT_TRANSPARENT_QSS = "QTextEdit{border:none; background:#0d1525;}"

# 反推预览框（虚线边框）
REV_PREVIEW_QSS = "QFrame#RevPreview{border:1px dashed #25345c;border-radius:6px;}"

# 反推：信息小字色
REV_INFO_QSS = "color:#8b9ab8; font-size:12px;"

# 反推：EN 输出框
REV_EN_QSS = "QTextEdit{border:none; background:transparent;}"

# 时间戳标签
TIME_LABEL_QSS = "color:#5a6a8a; font-size:12px;"

# 思考中动画点
THINKING_DOT_QSS = "font-size:13px;"

# 思考中文本
THINKING_TEXT_QSS = "color:#5a6a8a; font-size:12px;"


def chk_style(bg: str, border: str, text_color: str, bold: bool, size: int = 15) -> str:
    """生成含真实勾形的 QCheckBox 样式（在系统 temp 目录写一个 SVG 文件）。"""
    import tempfile, os
    m = round(size * 0.14, 1)
    pts = "{},{} {},{} {},{}".format(
        m,              round(size * 0.52, 1),
        round(size * 0.42, 1), round(size - m, 1),
        round(size - m, 1), m,
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
    bold_str = "bold" if bold else "normal"
    return (
        "QCheckBox{{color:#8b9ab8; font-size:{}px; spacing:6px;}}".format(13 if size >= 15 else 12) +
        "QCheckBox::indicator{{width:{}px; height:{}px;".format(size, size) +
        " border:1px solid #2d4070; border-radius:3px; background:#111827;}" +
        "QCheckBox::indicator:checked{{background:{}; border-color:{};".format(bg, border) +
        " image:url({});}}".format(path) +
        "QCheckBox:checked{{color:{}; font-weight:{};}}".format(text_color, bold_str)
    )
