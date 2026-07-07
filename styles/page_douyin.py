# styles/page_douyin.py
# 抖音下载页（PageDouyin）专属样式
# 该页整体色调为橙色主题，与全局蓝色体系有意区分，因此独立管理。

# 页面根组件样式（setStyleSheet 到 PageDouyin 自身）
PAGE_QSS = """
    QWidget { color: #f1f5f9; }
    QLineEdit {
        background: #0d1b35; color: #f1f5f9;
        border: 1px solid #334155; border-radius: 4px;
        padding: 4px 8px; font-family: Consolas;
    }
    QLineEdit:focus { border-color: #f97316; }
    QLineEdit[readOnly="true"] {
        background: #0a1428; color: #94a3b8;
        border-color: #1e2d4a;
    }
    QPushButton#BtnParse, QPushButton#BtnDownload {
        background: #f97316; color: white;
        border: none; border-radius: 4px;
        padding: 6px 18px; font-weight: bold; font-size: 13px;
    }
    QPushButton#BtnParse:hover, QPushButton#BtnDownload:hover {
        background: #ea580c;
    }
    QPushButton#BtnParse:disabled, QPushButton#BtnDownload:disabled {
        background: #4b3520; color: #7c6040;
    }
    QPushButton#BtnSmall {
        background: #1e2a45; color: #94a3b8;
        border: 1px solid #334155; border-radius: 4px;
        padding: 4px 10px; font-size: 12px;
    }
    QPushButton#BtnSmall:hover { background: #162035; color: #e2e8f0; }
    QPushButton#BtnCancel {
        background: transparent; color: #ef4444;
        border: 1px solid #ef4444; border-radius: 4px;
        padding: 4px 10px; font-size: 12px;
    }
    QTextEdit {
        background: #0d1b35; color: #f1f5f9;
        border: none; font-family: Consolas; font-size: 11px;
    }
    QProgressBar {
        background: #16213e; border: 1px solid #2d4070;
        border-radius: 4px; height: 22px;
        color: #f1f5f9; font-size: 12px; font-weight: bold;
        text-align: center;
    }
    QProgressBar::chunk { background: #f97316; border-radius: 3px; }
    QScrollArea { border: none; background: transparent; }
    QLabel#SecTitle { color: #94a3b8; font-size: 12px; }
    QLabel#StatusLbl { font-size: 12px; }
"""

# GroupBox 卡片样式（左侧"下载设置"、右侧"Cookie + 链接"共用）
GB_STYLE = """
    QGroupBox {
        color: #64748b;
        font-size: 11px;
        border: 1px solid #2d4070;
        border-radius: 6px;
        margin-top: 8px;
        padding: 6px 8px 6px 8px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        top: 0px;
        padding: 0 4px;
        background: #0d1933;
    }
"""

# 媒体选择区分隔线
DIVIDER_QSS = "QFrame{background:#2d4070; max-height:1px; min-height:1px;}"
