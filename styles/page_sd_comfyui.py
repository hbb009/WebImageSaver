# styles/page_sd_comfyui.py
# SD Mini（page_sd_mini.py）与 ComfyUI Mini（page_comfyui_mini.py）共用样式
# 两个页面的 Tab 结构、滚动区、进度条样式几乎完全相同，统一在此管理。

# Tab 控件样式（underline 风格，无 pane 边框）
TABS_QSS = (
    "QTabWidget::pane{border:none;}"
    "QTabBar::tab{background:#0f1826;color:#5a7098;padding:8px 20px;"
    "  border-bottom:2px solid transparent;font-size:13px;}"
    "QTabBar::tab:selected{color:#9fb0d7;border-bottom:2px solid #4a7fc1;}"
    "QTabBar::tab:hover{color:#7a9ac0;}"
)

# 左侧可滚动面板
SCROLL_LEFT_QSS = (
    "QScrollArea{border:none;background:transparent;}"
    "QScrollBar:vertical{width:6px;background:#0f1826;}"
    "QScrollBar::handle:vertical{background:#2d3d5a;border-radius:3px;}"
)

# 生成进度条
PROGRESS_QSS = (
    "QProgressBar{background:#0a1220;border:1px solid #2d3d5a;border-radius:3px;"
    "color:#9fb0d7;font-size:11px;}"
    "QProgressBar::chunk{background:#1e5fa8;border-radius:3px;}"
)

# 预览区占位图
PREVIEW_PLACEHOLDER_QSS = (
    "background:#0a1220;border:1px solid #2d3d5a;border-radius:4px;"
    "color:#3a5070;font-size:13px;"
)

# 生成状态提示标签（提示文字小字色）
HINT_LABEL_QSS = "color:#4a6080;font-size:12px;"

# 状态标签（中性）
STATUS_NEUTRAL_QSS = "color:#9fb0d7;font-size:13px;"
STATUS_OK_QSS      = "color:#4ac880;font-size:13px;"
STATUS_ERR_QSS     = "color:#c04040;font-size:13px;"

# 节点标题（启动页 section 标题）
SECTION_TITLE_QSS = "color:#9fb0d7;font-size:18px;font-weight:bold;"

# 节点分隔线
SEPARATOR_QSS = "color:#2d3d5a;"

# 提示 tips 小字
TIPS_QSS = "color:#4a6080;font-size:12px;"

# 参数信息 label/value 对（右侧元数据行）
META_LABEL_QSS = "color:#4a6080;font-size:12px;"
META_VALUE_QSS = "color:#7a9ac0;font-size:12px;"

# ── SD Mini 专属：SD 命令文本框（只在 CmdPanel 使用）──
CMD_TEXT_QSS = (
    "QPlainTextEdit{background:#090e1a;color:#8ba8c8;"
    "border:none;font-family:Consolas,monospace;font-size:11px;}"
)

# ── SD Mini 专属：架构提示（含警告色）──
ARCH_HINT_NORMAL_QSS = "color:#4a6080;font-size:12px;"
ARCH_HINT_WARN_QSS   = "color:#c0a030;font-size:12px;"

# 采样参数小标签（右侧数值显示，与 TEXT_STYLE 对齐，已由全局覆盖，可留空备用）
ARCH_LABEL_QSS = "color:#9fb0d7;font-size:12px;font-weight:bold;"

# 模型选择按钮：未选中 / 选中（TabButton 切换）
TAB_BTN_NORMAL   = "background:#0f1826;border:1px solid #2d3d5a;border-radius:4px;color:#5a7098;font-size:11px;padding:4px 2px;"
TAB_BTN_SELECTED = "background:#0e2040;border:1px solid #4a7fc1;border-radius:4px;color:#9fb0d7;font-size:11px;padding:4px 2px;"
