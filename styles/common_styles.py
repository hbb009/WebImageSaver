# styles/common_styles.py
TEXT_STYLE = """
QLabel, QCheckBox, QGroupBox {
    font-size: 14px;
    color: #FFFFFF;
}
"""

BUTTON_STYLE = """
QPushButton {
    background-color: #2B2E45;
    color: #FFFFFF;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 4px 16px;
    min-width: 80px; 
}
QPushButton:hover {
    background-color: #3A3D5C;
}
"""

# 需要更醒目时用（可选）
BUTTON_PRIMARY_STYLE = """
QPushButton {
    background-color: #3A3D5C;
    color: #FFFFFF;
    border: 2px solid #888;
    border-radius: 10px;
    padding: 4px 16px;
    min-width: 80px; 
}
QPushButton:hover {
    filter: brightness(1.05);
}
"""
LINEEDIT_STYLE = """
QLineEdit, QComboBox {
    background-color: #1E2030;
    color: #FFFFFF;
    border: 1px solid #555;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 14px;
    font-family: "微软雅黑";
}

/* 下拉列表面板样式 */
QComboBox QAbstractItemView {
    background-color: #1E2030;
    color: #FFFFFF;
    border: 1px solid #555;
    selection-background-color: #2B2E45;
}
"""
