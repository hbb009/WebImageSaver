# styles/disk_treemap.py
# 磁盘分析组件（disk_treemap_widget.py）专属样式
#
# 注意：DriveTab._apply_style() 中的颜色（蓝色激活/透明默认）以及
# DriveTabSub 的使用率警告色（红/橙/灰）依赖运行时数据，保留在 Python 代码中动态生成；
# 此文件只管理与数据无关的静态样式。

# ── DriveTab（盘符 Tab 卡片）──────────────────────────────────────────

# 激活状态（蓝色高亮 + 下划线）
DRIVE_TAB_ACTIVE_QSS = "#DriveTab { background: rgba(58,142,224,0.12); border-radius: 0; }"
DRIVE_TAB_ACTIVE_MAIN_QSS = "color:#3a8ee0; background:transparent;"
DRIVE_TAB_ACTIVE_UNDERLINE_QSS = "background:#3a8ee0; border-radius: 0;"

# 非激活状态（透明 + hover 淡亮）
DRIVE_TAB_INACTIVE_QSS = (
    "#DriveTab { background: transparent; border-radius: 0; }"
    "#DriveTab:hover { background: rgba(255,255,255,0.04); }"
)
DRIVE_TAB_INACTIVE_MAIN_QSS = "color:#9fb0d7; background:transparent;"
DRIVE_TAB_INACTIVE_UNDERLINE_QSS = "background: transparent; border-radius: 0;"

# 磁盘图标 emoji label
DRIVE_ICON_QSS = "font-size:17px; background:transparent;"

# 主标签（盘符名）正常态背景（字体/颜色在 _apply_style 里动态设置）
DRIVE_MAIN_BASE_QSS = "background:transparent;"

# ── Tab 栏容器 ─────────────────────────────────────────────────────────
TAB_BAR_QSS = "#DiskTabBar { background: #10162c; border-bottom: 1px solid #25345c; }"

# 扫描控制条
SCAN_BAR_QSS = "background:#141b33; border-bottom:1px solid #25345c;"

# 扫描按钮
SCAN_BTN_QSS = (
    "QPushButton { background:#3a8ee0; color:white; border:none; border-radius:6px; "
    "padding:0 16px; font-size:12px; font-weight:600; }"
    "QPushButton:hover { background:#2f7cc8; }"
    "QPushButton:disabled { background:#2a3454; color:#6f7fa8; }"
)

# 扫描进度条
SCAN_PROGRESS_QSS = (
    "QProgressBar { background:#1a2138; border:none; border-radius:4px; }"
    "QProgressBar::chunk { background:#3a8ee0; border-radius:4px; }"
)

# 扫描状态文字
SCAN_STATUS_QSS = "color:#6f7fa8; font-size:11px; background:transparent;"

# ── 右侧大文件排行榜面板 ───────────────────────────────────────────────
FILES_PANEL_QSS = "background:#15192c; border-left:1px solid #25345c;"

# 面板标题
FILES_TITLE_QSS = "color:#9fb0d7; font-size:12px; font-weight:600; background:transparent;"

# 文件列表（透明底，无边框）
FILES_LIST_QSS = (
    "QListWidget{background:transparent; border:none;}"
    "QListWidget::item{border:none; padding:0;}"
)

# WebEngine 回退提示（无 PyQtWebEngine 时）
FALLBACK_LABEL_QSS = "color:#e34948; font-size:13px; background:#111110;"

# WebEngine 视图（无边框纯黑底）
WEB_VIEW_QSS = "background:#111110; border:none;"

# ── _FileRankRow（文件排行条目）────────────────────────────────────────
FILE_RANK_ROW_QSS = "_FileRankRow { background:#1a2138; border-radius:6px; }"

FILE_RANK_NUM_QSS  = "color:#4a5578; font-size:11px; background:transparent;"
FILE_RANK_NAME_QSS = "color:#d7def7; font-size:12px; background:transparent;"
FILE_RANK_SIZE_QSS = "color:#3a8ee0; font-size:11px; font-weight:600; background:transparent;"
