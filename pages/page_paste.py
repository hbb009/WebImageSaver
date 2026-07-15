# -*- coding: utf-8 -*-
"""
page_paste.py  —  粘贴助手（提示词仓库）

集成于「桌面助手」主程序，作为侧边栏「粘贴助手」页面（PagePaste）。
记录文件：<项目根>/records/paste_helper.txt

功能：
  · 录入：主题 + 内容 + 七色选色 + 保存/更新
  · 仓库：彩色主题卡片（流式排列，可拖拽改序）
  · 单击卡片：复制内容 + 选中 + 进入修改（填回录入区）
  · 再点同一张：只复制，不重刷表单（避免抖动）
  · 右键卡片：删除
"""

import os
import re
import sys
import json
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from styles.style_all import (
    tk, install_card_title, apply_btn_download, make_card,
    CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP,
)

from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, QRectF, QSize, QMimeData, QEvent, QPointF
from PyQt5.QtGui import (
    QFont, QFontMetrics, QColor, QDrag, QPixmap, QPainter, QPen, QBrush, QPolygonF,
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QAbstractButton,
    QLineEdit, QTextEdit, QGroupBox, QScrollArea, QFrame, QMessageBox,
    QSizePolicy, QApplication, QLayout, QButtonGroup, QAbstractScrollArea,
)

# 色块基准边长（旧圆点 22px）；录入菱形 = 一半，筛选圆 = 30%/70%
_SWATCH_BASE = 22

# ── 路径 ─────────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(_HERE) if os.path.basename(_HERE).lower() == "pages" else _HERE
RECORD_FILE = os.path.join(_ROOT, "records", "paste_helper.txt")

# 七种常用色：红、橙、黄、绿、青、蓝、紫
CARD_COLORS = [
    ("#ef4444", "红"),
    ("#f97316", "橙"),
    ("#eab308", "黄"),
    ("#22c55e", "绿"),
    ("#06b6d4", "青"),
    ("#3b82f6", "蓝"),
    ("#a855f7", "紫"),
]
DEFAULT_COLOR = CARD_COLORS[0][0]

# 卡片尺寸：一排稳放 4 个汉字，可排两行（固定，不随悬停变化）
# 边距须与 ThemeCard 内 layout margins 一致，否则会少算可用字宽
_CARD_MARGIN_X = 8
_CARD_MARGIN_Y = 6


def _card_metrics():
    f = QFont("微软雅黑", 10)
    f.setBold(True)
    fm = QFontMetrics(f)
    # 用真实四字串测宽（比单字×4 更准）。旧版只留 4px 余量，粗体+抗锯齿下
    # 四个汉字会被挤折行（如「处理背景」显示成「处理背/景」），这里把余量加到
    # 18px，并把最小宽度抬到 104，保证 4 个全角汉字稳稳排在一行。
    text_w = max(fm.horizontalAdvance("汉字汉字"), fm.boundingRect("汉字汉字").width())
    text_h = fm.lineSpacing() * 2
    w = text_w + _CARD_MARGIN_X * 2 + 18
    h = text_h + _CARD_MARGIN_Y * 2
    return max(104, w), max(50, h)

MIME_CARD_ID = "application/x-paste-helper-card-id"
DRAG_THRESHOLD = 8  # 像素，超过才算拖拽，避免误触


def _tok(name, fallback):
    try:
        v = tk(name)
        return v if v else fallback
    except Exception:
        return fallback


def _transparent_bg(w: QWidget) -> QWidget:
    """中间层容器透明底：避免吃到全局 QWidget 画布色，与 GroupBox 功能区色不一致。"""
    w.setAttribute(Qt.WA_StyledBackground, True)
    w.setAutoFillBackground(False)
    w.setStyleSheet("background: transparent;")
    return w


class _FormHintLabel(QLabel):
    """录入区说明文字：可换行，但不把 heightForWidth 上报成窗口最小高度。"""

    def minimumSizeHint(self):
        return QSize(0, 36)

    def hasHeightForWidth(self):
        # 关闭后布局不按「越窄越高」撑死主窗口；需要时由 _sync_hint_height 设高
        return False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # 仅在宽度变化时重算，且高度不变则不 setFixedHeight，避免触发布局抖动环
        if not self.wordWrap() or self.width() <= 0:
            return
        h = max(36, min(self.heightForWidth(self.width()), 120))
        if abs(self.height() - h) > 1:
            self.setFixedHeight(h)


# ── 存储 ─────────────────────────────────────────────────────────────────────
def _ensure_dir():
    os.makedirs(os.path.dirname(RECORD_FILE), exist_ok=True)


def _normalize_record(r: dict) -> dict:
    if "theme" not in r and "title" in r:
        r["theme"] = r.get("title") or ""
    if "color" not in r or not r.get("color"):
        r["color"] = DEFAULT_COLOR
    if "order" not in r:
        r["order"] = 0
    return r


def _load_records() -> list:
    if not os.path.exists(RECORD_FILE):
        return []
    records = []
    with open(RECORD_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(_normalize_record(json.loads(line)))
            except json.JSONDecodeError:
                continue
    # 旧数据无 order：按原文件顺序编号
    if records and all(int(r.get("order") or 0) == 0 for r in records):
        for i, r in enumerate(records):
            r["order"] = i
    return records


def _save_records(records: list):
    _ensure_dir()
    with open(RECORD_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _sorted_by_order(records: list) -> list:
    return sorted(records, key=lambda r: int(r.get("order") or 0))


def _reindex(records: list) -> list:
    """按当前列表顺序重写 order：0..n-1"""
    for i, r in enumerate(records):
        r["order"] = i
    return records


# ── 流式布局 ─────────────────────────────────────────────────────────────────
class FlowLayout(QLayout):
    """
    卡片自动换行。

    注意：minimumSize / sizeHint 只按「单张卡片」算，绝不按
    heightForWidth(窄宽度) 把所有卡片竖着叠起来的高度上报——
    否则会一路顶到顶层窗口，把 minimumHeight 越撑越大，窗口再也缩不小
   （主程序里 wordWrap / FlowLayout 踩过的同类坑）。
    """

    def __init__(self, parent=None, margin=0, h_spacing=10, v_spacing=10):
        super().__init__(parent)
        self._h = h_spacing
        self._v = v_spacing
        self._items = []
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._layout(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self):
        # 给滚动区一个「单行高度」的合理提示，不把整列卡片高度上报
        return self.minimumSize()

    def minimumSize(self):
        # 只取子项中最大的那一个，不累加、不按窄宽叠高
        s = QSize(0, 0)
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
            s = s.expandedTo(it.sizeHint())
        if s.width() <= 0 or s.height() <= 0:
            cw, ch = _card_metrics()
            s = QSize(cw, ch)
        l, t, r, b = self.getContentsMargins()
        return s + QSize(l + r, t + b)

    def _layout(self, rect, test_only):
        l, t, r, b = self.getContentsMargins()
        effective = rect.adjusted(l, t, -r, -b)
        x, y = effective.x(), effective.y()
        line_h = 0
        # 宽度无效时按单行处理，避免测试布局时算出夸张高度
        if effective.width() <= 0:
            for it in self._items:
                hint = it.sizeHint()
                line_h = max(line_h, hint.height())
            return line_h + t + b

        for it in self._items:
            hint = it.sizeHint()
            next_x = x + hint.width() + self._h
            if next_x - self._h > effective.right() and line_h > 0:
                x = effective.x()
                y = y + line_h + self._v
                next_x = x + hint.width() + self._h
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + b


# ── 颜色工具 ─────────────────────────────────────────────────────────────────
def _contrast_text(bg_hex: str) -> str:
    c = QColor(bg_hex)
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return "#ffffff" if lum < 160 else "#1a1a1a"


def _lighten(hex_color: str, factor: float = 0.14) -> str:
    c = QColor(hex_color)
    return QColor(
        min(255, int(c.red() + (255 - c.red()) * factor)),
        min(255, int(c.green() + (255 - c.green()) * factor)),
        min(255, int(c.blue() + (255 - c.blue()) * factor)),
    ).name()


# ── 自绘色块：录入菱形 / 筛选圆点 ─────────────────────────────────────────────
class DiamondSwatch(QAbstractButton):
    """录入区色块：菱形小方块，边长约为旧圆点的一半。"""

    # 旧基准 22 的一半
    SIZE = max(10, _SWATCH_BASE // 2)  # 11

    def __init__(self, color_hex: str, parent=None):
        super().__init__(parent)
        self._color = color_hex
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.SIZE + 4, self.SIZE + 4)  # 略留描边余量
        self.setProperty("swatch", color_hex)
        # 透明底：菱形外四角不套全局 QWidget 画布色
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        # 菱形外接：对角线 = SIZE
        half = self.SIZE / 2.0
        poly = QPolygonF([
            QPointF(cx, cy - half),
            QPointF(cx + half, cy),
            QPointF(cx, cy + half),
            QPointF(cx - half, cy),
        ])
        p.setBrush(QBrush(QColor(self._color)))
        if self.isChecked():
            pen = QPen(QColor("#ffffff"), 1.6)
        elif self.underMouse():
            pen = QPen(QColor(255, 255, 255, 200), 1.2)
        else:
            pen = QPen(QColor(255, 255, 255, 70), 1.0)
        p.setPen(pen)
        p.drawPolygon(poly)
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class CircleFilterSwatch(QAbstractButton):
    """
    筛选色块：槽位固定为旧尺寸，避免布局抖动。
    未选中：直径 = 基准 × 30%；选中：直径 = 基准 × 70%。
    """

    SLOT = _SWATCH_BASE  # 22，占位固定
    R_OFF = 0.30
    R_ON = 0.70

    def __init__(self, color_hex: str, parent=None):
        super().__init__(parent)
        self._color = color_hex
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.SLOT, self.SLOT)
        self.setProperty("swatch", color_hex)
        # 透明底：圆外槽位不套全局 QWidget 画布色
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        ratio = self.R_ON if self.isChecked() else self.R_OFF
        d = self.SLOT * ratio
        x = (self.width() - d) / 2.0
        y = (self.height() - d) / 2.0
        p.setBrush(QBrush(QColor(self._color)))
        if self.isChecked():
            pen = QPen(QColor("#ffffff"), 1.5)
        elif self.underMouse():
            pen = QPen(QColor(255, 255, 255, 200), 1.2)
        else:
            pen = QPen(QColor(255, 255, 255, 60), 1.0)
        p.setPen(pen)
        p.drawEllipse(QRectF(x, y, d, d))
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


# ── 录入区：七色选色条 ───────────────────────────────────────────────────────
class ColorPickerBar(QWidget):
    """七色菱形，单选。菱形为旧圆点一半大。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        _transparent_bg(self)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._color = DEFAULT_COLOR

        wrap = QVBoxLayout(self)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(6)

        lbl = QLabel("颜色")
        lbl.setObjectName("CalcFieldLabel")
        wrap.addWidget(lbl)

        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        for i, (hex_c, name) in enumerate(CARD_COLORS):
            btn = DiamondSwatch(hex_c)
            btn.setToolTip(name)
            self._group.addButton(btn, i)
            lay.addWidget(btn)

        lay.addStretch(1)
        wrap.addLayout(lay)
        self._group.buttonClicked.connect(self._on_clicked)
        first = self._group.button(0)
        if first:
            first.setChecked(True)

    def _on_clicked(self, btn):
        self._color = btn.property("swatch") or DEFAULT_COLOR
        # 菱形自绘，勾选态在 paintEvent 里读 isChecked()
        for b in self._group.buttons():
            b.update()

    def color(self) -> str:
        return self._color or DEFAULT_COLOR

    def set_color(self, color: str):
        color = (color or DEFAULT_COLOR).lower()
        matched = False
        for b in self._group.buttons():
            hex_c = (b.property("swatch") or "").lower()
            if hex_c == color:
                b.setChecked(True)
                self._color = b.property("swatch")
                matched = True
            else:
                b.setChecked(False)
        if not matched:
            b0 = self._group.button(0)
            if b0:
                b0.setChecked(True)
                self._color = DEFAULT_COLOR
        for b in self._group.buttons():
            b.update()


# ── 仓库区：七色快速过滤（支持多色同时选中）────────────────────────────────
class ColorFilterBar(QWidget):
    """
    [筛选/取消] + 七色圆点（可多选）。
    · 无文字标签；按钮文案：无色选中时「筛选」，有色选中时「取消」
    · 点「取消」：清空所有颜色筛选
    · 未选中小圆 30%，选中中圆 70%；槽位固定不抖布局
    """

    def __init__(self, on_change, parent=None):
        super().__init__(parent)
        _transparent_bg(self)
        self._on_change = on_change
        self._swatches = []  # CircleFilterSwatch 列表

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.btn_action = QPushButton("筛选")
        self.btn_action.setFixedHeight(26)
        self.btn_action.setMinimumWidth(52)
        self.btn_action.setCursor(Qt.PointingHandCursor)
        self.btn_action.setObjectName("ColorFilterAction")
        self.btn_action.setToolTip("点色块可多选筛选；有筛选时点此取消")
        self.btn_action.clicked.connect(self._on_action_clicked)
        lay.addWidget(self.btn_action)

        for hex_c, name in CARD_COLORS:
            btn = CircleFilterSwatch(hex_c)
            btn.setToolTip(f"{name}（可多选）")
            btn.clicked.connect(self._on_swatch_clicked)
            self._swatches.append(btn)
            lay.addWidget(btn)

        lay.addStretch(1)
        self._sync_action_btn()

    def _action_qss(self, active: bool) -> str:
        """active=True 表示当前有颜色筛选，按钮显示「取消」。"""
        if active:
            return f"""
                QPushButton#ColorFilterAction {{
                    background: rgba(240,165,66,0.16);
                    border: 1px solid rgba(240,165,66,0.50);
                    border-radius: 6px;
                    color: {_tok('warn', '#f0a542')};
                    font-size: 12px;
                    font-weight: 700;
                    padding: 0 10px;
                }}
                QPushButton#ColorFilterAction:hover {{
                    background: rgba(240,165,66,0.28);
                }}
            """
        # 未筛选：半透明底，跟功能区同色系，不套全局画布色
        return f"""
            QPushButton#ColorFilterAction {{
                background: {_tok('hover_veil', 'rgba(255,255,255,0.05)')};
                border: 1px solid {_tok('border_soft', 'rgba(255,255,255,0.18)')};
                border-radius: 6px;
                color: {_tok('text_mut', '#9fb0d7')};
                font-size: 12px;
                font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton#ColorFilterAction:hover {{
                background: {_tok('row_bg', 'rgba(255,255,255,0.09)')};
            }}
        """

    def selected_colors(self) -> list:
        """当前勾选的颜色 hex 列表（可多个）。"""
        return [
            b.property("swatch")
            for b in self._swatches
            if b.isChecked() and b.property("swatch")
        ]

    def _sync_action_btn(self):
        colors = self.selected_colors()
        active = len(colors) > 0
        self.btn_action.setText("取消" if active else "筛选")
        self.btn_action.setStyleSheet(self._action_qss(active))
        for b in self._swatches:
            b.update()

    def _emit(self):
        if callable(self._on_change):
            self._on_change(self.selected_colors())

    def _on_swatch_clicked(self):
        # 多选：每个色块独立勾选/取消，不互斥
        self._sync_action_btn()
        self._emit()

    def _on_action_clicked(self):
        if self.selected_colors():
            # 「取消」：清空所有颜色筛选
            self.clear()
            self._emit()
        # 无筛选时点「筛选」：无需操作（靠点色块开始筛）

    def clear(self):
        for b in self._swatches:
            b.setChecked(False)
            b.update()
        self._sync_action_btn()


# ── 主题卡片 ─────────────────────────────────────────────────────────────────
class ThemeCard(QFrame):
    """
    仓库卡片：只显示主题文字。
    · 单击 = 复制 + 进入修改
    · 拖拽 = 改顺序
    · 右键 = 删除
    热区：仅边框/亮度变化，尺寸始终不变。
    """

    def __init__(self, record, page, parent=None):
        super().__init__(parent)
        self._record = record
        self._page = page
        self._press_pos = None
        self._dragging = False
        self._selected = False

        self.setObjectName("ThemeCard")
        self.setAcceptDrops(True)
        self.setCursor(Qt.OpenHandCursor)
        # 固定尺寸：约 4 字宽 × 2 行高，杜绝悬停变大变小
        cw, ch = _card_metrics()
        self.setFixedSize(cw, ch)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        theme = (record.get("theme") or record.get("title") or "未命名").strip() or "未命名"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(_CARD_MARGIN_X, _CARD_MARGIN_Y, _CARD_MARGIN_X, _CARD_MARGIN_Y)
        lay.setSpacing(0)

        self.lbl_theme = QLabel(theme)
        self.lbl_theme.setObjectName("ThemeCardTitle")
        self.lbl_theme.setAlignment(Qt.AlignCenter)
        self.lbl_theme.setWordWrap(True)
        f = QFont("微软雅黑", 10)
        f.setBold(True)
        self.lbl_theme.setFont(f)
        # 最多两行，超出省略（由固定高度约束）
        self.lbl_theme.setMaximumHeight(QFontMetrics(f).lineSpacing() * 2)
        lay.addWidget(self.lbl_theme, 1)

        self._apply_style(record.get("color") or DEFAULT_COLOR, selected=False)

    def record_id(self):
        return self._record.get("id")

    def set_selected(self, selected: bool):
        # 状态未变则跳过：避免重复 setStyleSheet 引发卡片/流式布局闪动
        if self._selected == selected:
            return
        self._selected = selected
        self._apply_style(self._record.get("color") or DEFAULT_COLOR, selected=selected)

    def _apply_style(self, color: str, selected: bool = False):
        text = _contrast_text(color)
        hover = _lighten(color, 0.10)
        # 边框始终 2px，只改颜色——选中时若 1px↔2px 切换，流式排布会抖一下
        if selected:
            border = "#ffffff"
        else:
            border = "rgba(255,255,255,0.14)"
        border_w = 2
        # 注意：hover 不改变 width/height/padding/margin，只改颜色与边框色
        self.setStyleSheet(f"""
            QFrame#ThemeCard {{
                background-color: {color};
                border: {border_w}px solid {border};
                border-radius: 12px;
            }}
            QFrame#ThemeCard:hover {{
                background-color: {hover};
                border: {border_w}px solid rgba(255,255,255,0.55);
            }}
            QLabel#ThemeCardTitle {{
                color: {text};
                background: transparent;
                font-weight: 700;
            }}
        """)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_pos = e.pos()
            self._dragging = False
            self.setCursor(Qt.ClosedHandCursor)
        elif e.button() == Qt.RightButton:
            self._page._delete(self._record)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if not (e.buttons() & Qt.LeftButton) or self._press_pos is None:
            return
        if (e.pos() - self._press_pos).manhattanLength() < DRAG_THRESHOLD:
            return
        self._dragging = True
        self._start_drag()

    def mouseReleaseEvent(self, e):
        self.setCursor(Qt.OpenHandCursor)
        if e.button() == Qt.LeftButton and not self._dragging:
            # 单击：复制 + 选中 + 进入录入区编辑
            self._page._click_card(self._record)
        self._press_pos = None
        self._dragging = False
        super().mouseReleaseEvent(e)

    def _start_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_CARD_ID, str(self.record_id()).encode("utf-8"))
        drag.setMimeData(mime)

        # 半透明拖影（尺寸与卡片一致，不放大）
        pix = QPixmap(self.size())
        pix.fill(Qt.transparent)
        self.render(pix)
        painter = QPainter(pix)
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        painter.fillRect(pix.rect(), QColor(0, 0, 0, 170))
        painter.end()
        drag.setPixmap(pix)
        drag.setHotSpot(self._press_pos if self._press_pos else QPoint(self.width() // 2, self.height() // 2))

        # 拖拽结束后可能仍会收到 release，保持 _dragging 避免误触发单击复制
        drag.exec_(Qt.MoveAction)
        self._dragging = True

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_CARD_ID):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME_CARD_ID):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(MIME_CARD_ID):
            e.ignore()
            return
        src_id = bytes(e.mimeData().data(MIME_CARD_ID)).decode("utf-8")
        tgt_id = str(self.record_id())
        if src_id and src_id != tgt_id:
            # 放到目标卡片的左/右半：决定插在前还是后
            insert_after = e.pos().x() > self.width() / 2
            self._page._reorder_cards(src_id, tgt_id, insert_after=insert_after)
        e.acceptProposedAction()


# ── 卡片容器（空白处也可接住拖放）────────────────────────────────────────────
class CardsDropHost(QWidget):
    def __init__(self, page, parent=None):
        super().__init__(parent)
        self._page = page
        self.setAcceptDrops(True)
        self.setObjectName("RecordsContainer")
        _transparent_bg(self)
        # 不把卡片总高度/总宽度当成窗口最小尺寸（交给外层 QScrollArea 滚动）
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def minimumSizeHint(self):
        # 阻断 FlowLayout.heightForWidth 把「竖着叠满」的高度传给主窗口
        cw, ch = _card_metrics()
        return QSize(cw, ch)

    def sizeHint(self):
        lay = self.layout()
        if lay is not None and lay.hasHeightForWidth():
            w = max(self.width(), self.minimumSizeHint().width())
            return QSize(w, lay.heightForWidth(w))
        return self.minimumSizeHint()

    def _card_at(self, pos):
        w = self.childAt(pos)
        while w is not None and w is not self:
            if isinstance(w, ThemeCard):
                return w
            w = w.parentWidget()
        return None

    def mousePressEvent(self, e):
        # 仓库空白处左键 = 取消选中
        if e.button() == Qt.LeftButton and self._card_at(e.pos()) is None:
            self._page._cancel_edit()
        super().mousePressEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_CARD_ID):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME_CARD_ID):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(MIME_CARD_ID):
            e.ignore()
            return
        src_id = bytes(e.mimeData().data(MIME_CARD_ID)).decode("utf-8")
        card = self._card_at(e.pos())
        if card is not None:
            insert_after = e.pos().x() > card.geometry().center().x()
            self._page._reorder_cards(src_id, str(card.record_id()), insert_after=insert_after)
        else:
            self._page._reorder_to_end(src_id)
        e.acceptProposedAction()


# ── 主页面 ───────────────────────────────────────────────────────────────────
class PagePaste(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PageRoot")
        self.setAttribute(Qt.WA_StyledBackground, True)
        # 页面本身不向外强加最小尺寸，由外层窗口 setMinimumSize 说了算
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._selected_id = None   # 仓库卡片选中（高亮），不等于录入编辑
        self._editing_id = None    # 仅双击进入「主题/内容」编辑时才有值
        self._all_records = []
        self._card_widgets = {}  # id -> ThemeCard
        self._filter_colors = set()  # 空集合=不限颜色；可多色同时筛选

        self._build_ui()
        self._install_blank_click_filter()
        self._reload()

    def minimumSizeHint(self):
        # 防止子控件（FlowLayout / 标签）把最小高度顶破窗口
        return QSize(0, 0)

    def sizeHint(self):
        return QSize(1080, 720)

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        page = QVBoxLayout(self)
        # 与系统总览一致：ContentRoot 已有左右内边距，页面不再叠第二层
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(12)
        # 录入区约占 25% 高度，仓库约占 75%（录入区在原 35% 基础上再让出 10%）
        page.addWidget(self._build_entry_panel(), 25)
        page.addWidget(self._build_warehouse_panel(), 75)

    def _build_entry_panel(self) -> QWidget:
        """
        录入区布局：
          整体高度约占页面 35%
          左 75%：主题 + 内容
          中 12px：空隙
          右 25%：颜色 / 保存·删除 / 提示文字（顶对齐；相对原 35% 收窄约 10% 总宽）
        """
        box = make_card("CardPasteEntry")
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        form = QVBoxLayout(box)
        form.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        # 标题空隙由 CARD_TITLE_BODY_GAP 统一；此处 spacing 只作用正文之间
        form.setSpacing(8)
        install_card_title(box, form, "录入")

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)  # 中间 12px 分隔
        body.setAlignment(Qt.AlignTop)

        # ── 左 75%：主题 + 内容 ────────────────────────────────────────────
        left = _transparent_bg(QWidget())
        left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(8)

        row_t = QHBoxLayout()
        row_t.setSpacing(8)
        lbl = QLabel("主题")
        lbl.setObjectName("CalcFieldLabel")
        lbl.setFixedWidth(40)
        row_t.addWidget(lbl)
        # 主题 / 内容：圆角浅色底（PasteThemeInput / PasteContentEdit，见 app.qss）
        self.inp_theme = QLineEdit()
        self.inp_theme.setObjectName("PasteThemeInput")
        self.inp_theme.setPlaceholderText("好记的名字，例如：写实人像")
        self.inp_theme.setFixedHeight(32)
        row_t.addWidget(self.inp_theme, 1)
        left_l.addLayout(row_t)

        row_c = QHBoxLayout()
        row_c.setSpacing(8)
        lbl2 = QLabel("内容")
        lbl2.setObjectName("CalcFieldLabel")
        lbl2.setFixedWidth(40)
        lbl2.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        row_c.addWidget(lbl2)
        self.inp_content = QTextEdit()
        self.inp_content.setObjectName("PasteContentEdit")
        self.inp_content.setPlaceholderText("在这里粘贴或编写完整提示词，支持多行。")
        self.inp_content.setMinimumHeight(60)
        self.inp_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 竖向滚动条样式对齐截图工具「截图与操作记录」(recordStyle dashed 标准)
        self.inp_content.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.inp_content.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        row_c.addWidget(self.inp_content, 1)
        left_l.addLayout(row_c, 1)

        # ── 右 25%：颜色 + 按钮 + 提示（顶对齐，高度随内容）────────────────
        right = _transparent_bg(QWidget())
        # 纵向 Maximum：不跟左侧一起被拉高，配合 AlignTop 贴顶
        right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(10)
        right_l.setAlignment(Qt.AlignTop)

        self.color_bar = ColorPickerBar()
        right_l.addWidget(self.color_bar, 0, Qt.AlignTop)

        self._row_btn_h = 28

        # 第 1 行：保存 / 更新（占满宽）
        row_save = QHBoxLayout()
        row_save.setContentsMargins(0, 0, 0, 0)
        row_save.setSpacing(0)
        self.btn_save = QPushButton("保存")
        apply_btn_download(self.btn_save)
        self.btn_save.setFixedHeight(self._row_btn_h)
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_save.clicked.connect(self._save)
        row_save.addWidget(self.btn_save, 1)
        right_l.addLayout(row_save)

        # 第 2 行：复制 | 删除（编辑态显示）
        # 槽位高度固定：隐藏按钮时仍占位，避免录入区高度涨缩带动整页抖动
        self.edit_actions = _transparent_bg(QWidget())
        self.edit_actions.setFixedHeight(self._row_btn_h)
        self.edit_actions.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row_edit = QHBoxLayout(self.edit_actions)
        row_edit.setContentsMargins(0, 0, 0, 0)
        row_edit.setSpacing(8)

        self.btn_copy = QPushButton("复制")
        self.btn_copy.setObjectName("RecordCopyBtn")
        self.btn_copy.setFixedHeight(self._row_btn_h)
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_copy.setToolTip("复制当前卡片：主题名 + 序号")
        self.btn_copy.clicked.connect(self._duplicate_selected)
        row_edit.addWidget(self.btn_copy, 1)

        self.btn_delete = QPushButton("删除")
        self.btn_delete.setObjectName("RecordDelBtn")
        self.btn_delete.setFixedHeight(self._row_btn_h)
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_delete.setToolTip("删除当前选中的卡片")
        self.btn_delete.clicked.connect(self._delete_selected)
        row_edit.addWidget(self.btn_delete, 1)

        right_l.addWidget(self.edit_actions)
        self._set_selection_actions_visible(False)

        # 说明文字：允许换行；min 高度钉死，避免 heightForWidth 顶高主窗口
        self.form_hint = _FormHintLabel(self._default_hint())
        self.form_hint.setObjectName("ResultHint")
        self.form_hint.setWordWrap(True)
        self.form_hint.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.form_hint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        right_l.addWidget(self.form_hint, 0, Qt.AlignTop)

        # 左 75% : 右 25%（原 65:35，右侧占宽减少 10 个百分点）
        body.addWidget(left, 75)
        body.addWidget(right, 25, Qt.AlignTop)
        form.addLayout(body, 1)
        return box

    def _build_warehouse_panel(self) -> QWidget:
        box = make_card("CardPasteWarehouse")

        outer = QVBoxLayout(box)
        outer.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        # spacing 与标题空隙由 install_card_title 补偿；正文行距用 spacing=8
        outer.setSpacing(8)
        install_card_title(box, outer, "仓库")

        # 工具条：左 50% 七色筛选 | 右 50% 搜索 + 取消 + 计数
        tool = QHBoxLayout()
        tool.setContentsMargins(0, 0, 0, 0)
        tool.setSpacing(12)

        left_tool = _transparent_bg(QWidget())
        left_l = QHBoxLayout(left_tool)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(0)
        self.color_filter = ColorFilterBar(on_change=self._on_color_filter)
        left_l.addWidget(self.color_filter, 1)

        right_tool = _transparent_bg(QWidget())
        right_l = QHBoxLayout(right_tool)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(8)

        self.inp_search = QLineEdit()
        self.inp_search.setObjectName("CalcInput")
        self.inp_search.setPlaceholderText("搜索主题或内容…")
        self.inp_search.setFixedHeight(30)
        self.inp_search.textChanged.connect(self._on_search_changed)
        right_l.addWidget(self.inp_search, 1)

        # 有搜索内容时才显示；高度与搜索框一致，不超出
        self.btn_clear_search = QPushButton("取消")
        self.btn_clear_search.setObjectName("SearchClearBtn")
        self.btn_clear_search.setFixedHeight(30)
        self.btn_clear_search.setMinimumWidth(72)
        self.btn_clear_search.setCursor(Qt.PointingHandCursor)
        self.btn_clear_search.setToolTip("清空搜索")
        self.btn_clear_search.clicked.connect(self._clear_search)
        self.btn_clear_search.setVisible(False)
        right_l.addWidget(self.btn_clear_search)

        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("RecordDate")
        right_l.addWidget(self.lbl_count, 0)

        tool.addWidget(left_tool, 50)
        tool.addWidget(right_tool, 50)
        outer.addLayout(tool)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("RecordsScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # 滚动区自己吃掉内容高度，不把内容最小高度上报给窗口
        scroll.setMinimumHeight(0)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        try:
            scroll.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
        except Exception:
            pass
        # 视口默认用调色板 Base 色 / 全局 QWidget 画布色，会与 RecordsBox 功能区色不一致
        scroll.viewport().setAutoFillBackground(False)
        scroll.setStyleSheet(
            "QScrollArea#RecordsScroll{background:transparent;border:none;}"
            "QScrollArea#RecordsScroll > QWidget > QWidget{background:transparent;}"
        )

        self.cards_host = CardsDropHost(self)
        self.cards_layout = FlowLayout(self.cards_host, margin=4, h_spacing=10, v_spacing=10)
        scroll.setWidget(self.cards_host)
        self._warehouse_scroll = scroll
        outer.addWidget(scroll, 1)

        # 仓库卡片区可压缩，录入区保持内容高度
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return box

    # ── 刷新 ─────────────────────────────────────────────────────────────────
    def _reload(self):
        self._all_records = _load_records()
        self._refresh_cards()

    def _on_color_filter(self, colors):
        """colors: 选中的颜色 hex 列表，空列表表示不筛选。"""
        self._filter_colors = {(c or "").lower() for c in (colors or []) if c}
        self._refresh_cards()

    def _on_search_changed(self, text):
        has = bool((text or "").strip())
        self.btn_clear_search.setVisible(has)
        self._refresh_cards()

    def _clear_search(self):
        self.inp_search.clear()
        # textChanged 会触发隐藏取消按钮并刷新

    def _refresh_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._card_widgets = {}

        kw = (self.inp_search.text() or "").strip().lower()
        recs = _sorted_by_order(self._all_records)

        # 颜色多选筛选：卡片颜色属于任一勾选色即显示
        if self._filter_colors:
            recs = [
                r for r in recs
                if (r.get("color") or "").lower() in self._filter_colors
            ]

        if kw:
            recs = [
                r for r in recs
                if kw in (r.get("theme") or r.get("title") or "").lower()
                or kw in (r.get("content") or "").lower()
            ]

        self.lbl_count.setText(f"共 {len(recs)} 条")

        if not recs:
            if not self._all_records:
                empty_msg = "仓库还是空的，在上面录入一条提示词吧～"
            elif self._filter_colors or kw:
                empty_msg = "没有匹配的提示词（可换颜色或点「取消」清空筛选）"
            else:
                empty_msg = "没有匹配的提示词"
            empty = QLabel(empty_msg)
            empty.setObjectName("RecordEmpty")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(120)
            self.cards_layout.addWidget(empty)
            return

        for record in recs:
            card = ThemeCard(record, page=self, parent=self.cards_host)
            if self._selected_id is not None and str(record.get("id")) == str(self._selected_id):
                card.set_selected(True)
            self.cards_layout.addWidget(card)
            self._card_widgets[str(record.get("id"))] = card
            # 新建卡片也挂上空白点击过滤器（卡片本身会被排除，不影响选中）
            card.installEventFilter(self)
            for child in card.findChildren(QWidget):
                child.installEventFilter(self)

    def _mark_selected(self):
        sid = str(self._selected_id) if self._selected_id is not None else None
        for rid, card in self._card_widgets.items():
            card.set_selected(sid is not None and rid == sid)

    def _active_card_id(self):
        """当前业务目标卡：优先编辑中的，否则仓库选中的。"""
        if self._editing_id is not None:
            return self._editing_id
        return self._selected_id

    # ── 空白点击 = 取消选中 ───────────────────────────────────────────────────
    def _install_blank_click_filter(self):
        """子控件点击冒泡检测：点到非交互空白处时取消选中。"""
        self.installEventFilter(self)
        for w in self.findChildren(QWidget):
            w.installEventFilter(self)

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.MouseButtonPress
            and event.button() == Qt.LeftButton
            and (self._selected_id or self._editing_id)
            and self._is_blank_deselect_target(obj)
        ):
            self._cancel_edit()
            return False
        return super().eventFilter(obj, event)

    def _is_blank_deselect_target(self, obj) -> bool:
        """判断这次点击是否落在“空白区”（非输入、非按钮、非卡片本体）。"""
        w = obj
        while w is not None:
            if isinstance(w, ThemeCard):
                return False
            if w in (
                self.btn_save, self.btn_copy, self.btn_delete,
                self.btn_clear_search,
                self.inp_theme, self.inp_content, self.inp_search,
            ):
                return False
            if isinstance(w, (QLineEdit, QTextEdit)):
                return False
            # 颜色菱形/圆点、以及其它功能按钮
            if isinstance(w, (QPushButton, QAbstractButton)):
                return False
            if w is self:
                break
            w = w.parentWidget()
        return True

    # ── 业务 ─────────────────────────────────────────────────────────────────
    def _sync_hint_height(self):
        """按当前宽度同步说明文字高度；高度不变则不写 setFixedHeight。"""
        if not hasattr(self, "form_hint") or self.form_hint.width() <= 0:
            return
        h = max(36, min(self.form_hint.heightForWidth(self.form_hint.width()), 120))
        if abs(self.form_hint.height() - h) > 1:
            self.form_hint.setFixedHeight(h)

    def _show_hint(self, text: str):
        if self.form_hint.text() == text:
            return  # 文案未变，跳过，避免无谓几何更新
        self.form_hint.setText(text)
        self._sync_hint_height()

    def _default_hint(self):
        return (
            "填写左侧主题与内容，选色后点保存。"
            "点仓库卡片可复制内容并进入修改。"
            "空白处点击可取消选中。"
        )

    def _edit_hint(self, copied: bool = False) -> str:
        # 编辑态提示固定长度：避免「已复制…」前缀导致换行高度变化、整页跟着抖
        base = (
            "正在修改，改完点更新保存。"
            "复制可按名字加序号多出一张卡。"
            "点空白处取消选中，或删除移除本条。"
        )
        if copied:
            return "已复制到剪贴板。" + base
        return base

    def _set_selection_actions_visible(self, visible: bool):
        # 只显隐按钮，槽位高度始终固定，录入区不因显隐涨缩
        self.btn_copy.setVisible(visible)
        self.btn_delete.setVisible(visible)
        if hasattr(self, "edit_actions"):
            h = getattr(self, "_row_btn_h", 28)
            self.edit_actions.setFixedHeight(h)
            self.edit_actions.setVisible(True)

    def _clear_form(self):
        self._selected_id = None
        self._editing_id = None
        self.inp_theme.clear()
        self.inp_content.clear()
        self.color_bar.set_color(DEFAULT_COLOR)
        self.btn_save.setText("保存")
        self._set_selection_actions_visible(False)
        self._show_hint(self._default_hint())
        self._mark_selected()

    def _bump_use_count(self, record_id):
        records = _load_records()
        for r in records:
            if r.get("id") == record_id:
                r["use_count"] = int(r.get("use_count") or 0) + 1
                break
        _save_records(records)
        self._all_records = records

    def _click_card(self, record):
        """单击卡片：复制内容 + 选中 + 进入主题/内容编辑。"""
        content = record.get("content") or ""
        QApplication.clipboard().setText(content)
        self._bump_use_count(record.get("id"))

        rid = record.get("id")
        # 已在编辑同一张：只复制+提示，不重刷表单（避免抖动）
        if self._editing_id is not None and str(self._editing_id) == str(rid):
            self._selected_id = rid
            self._set_selection_actions_visible(True)
            self._mark_selected()
            self._show_hint(self._edit_hint(copied=True))
            return

        self._enter_edit(record, copied=True)

    def _enter_edit(self, record, copied: bool = False):
        same = (
            self._editing_id is not None
            and str(self._editing_id) == str(record.get("id"))
        )
        self._selected_id = record.get("id")
        self._editing_id = record.get("id")
        theme = record.get("theme") or record.get("title") or ""
        # 同卡重复进入时不要反复 setText/setPlainText（会重置光标并触发布局）
        if not same:
            self.inp_theme.setText(theme)
            self.inp_content.setPlainText(record.get("content") or "")
            self.color_bar.set_color(record.get("color") or DEFAULT_COLOR)
        self.btn_save.setText("更新")
        self._set_selection_actions_visible(True)
        self._show_hint(self._edit_hint(copied=copied))
        self._mark_selected()
        # 点卡：只选中并填入数据，不进入主题/内容文本编辑（不抢光标、不闪烁插入符）
        # 用户若要改字，再自己点对应输入框即可
        self.inp_theme.clearFocus()
        self.inp_content.clearFocus()
        self.setFocus(Qt.OtherFocusReason)

    def _save(self):
        theme = self.inp_theme.text().strip()
        content = self.inp_content.toPlainText().strip()
        color = self.color_bar.color()

        if not content:
            self._show_hint("内容不能为空")
            return
        if not theme:
            theme = content[:12] + ("…" if len(content) > 12 else "")

        records = _sorted_by_order(_load_records())
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        is_update = bool(self._editing_id)

        if is_update:
            found = False
            for r in records:
                if r.get("id") == self._editing_id:
                    r["theme"] = theme
                    r["title"] = theme
                    r["content"] = content
                    r["color"] = color
                    r["date"] = now
                    found = True
                    break
            if not found:
                is_update = False
                self._editing_id = None

        if not is_update:
            max_order = max((int(r.get("order") or 0) for r in records), default=-1)
            records.append({
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "theme": theme,
                "title": theme,
                "content": content,
                "color": color,
                "date": now,
                "use_count": 0,
                "order": max_order + 1,
            })

        _save_records(records)
        hint = "已更新" if is_update else "已存入仓库"
        self._selected_id = None
        self._editing_id = None
        self.inp_theme.clear()
        self.inp_content.clear()
        self.color_bar.set_color(DEFAULT_COLOR)
        self.btn_save.setText("保存")
        self._set_selection_actions_visible(False)
        self._show_hint(hint)
        QTimer.singleShot(1400, lambda: self._show_hint(self._default_hint()))
        self._all_records = records
        self._refresh_cards()

    def _cancel_edit(self):
        """空白处：取消选中 + 退出编辑。"""
        self._clear_form()

    @staticmethod
    def _next_copy_theme(base_theme: str, existing_themes: set) -> str:
        """生成「名字 + 序号」：豆绘1 → 豆绘2；Grok → Grok2（遇重名递增）。"""
        name = (base_theme or "未命名").strip() or "未命名"
        m = re.match(r"^(.*?)(\d+)$", name)
        if m:
            stem, start = m.group(1), int(m.group(2))
        else:
            stem, start = name, 1
        n = start + 1
        # 防止 stem 为空时只剩纯数字
        while True:
            candidate = f"{stem}{n}" if stem else str(n)
            if candidate not in existing_themes:
                return candidate
            n += 1

    def _duplicate_selected(self):
        """「复制」：在仓库中新增一张 名字+序号 的同内容卡片（基于选中/编辑中的卡）。"""
        rid = self._active_card_id()
        if not rid:
            self._show_hint("请先点选一张卡片再复制")
            return

        # 编辑态以表单为准；仅选中时以原卡为准
        theme = self.inp_theme.text().strip() if self._editing_id else ""
        content = self.inp_content.toPlainText().strip() if self._editing_id else ""
        color = self.color_bar.color() if self._editing_id else ""

        src = next(
            (r for r in self._all_records if r.get("id") == rid),
            None,
        )
        if src is None:
            records_disk = _load_records()
            src = next((r for r in records_disk if r.get("id") == rid), None)
        if src is None and not content:
            self._show_hint("找不到要复制的卡片")
            return

        if not content:
            content = (src or {}).get("content") or ""
        if not content:
            self._show_hint("内容不能为空，无法复制")
            return
        if not theme:
            theme = (src or {}).get("theme") or (src or {}).get("title") or "未命名"
        if not color:
            color = (src or {}).get("color") or DEFAULT_COLOR

        records = _sorted_by_order(_load_records())
        existing = {
            (r.get("theme") or r.get("title") or "").strip()
            for r in records
        }
        new_theme = self._next_copy_theme(theme, existing)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        # 插在当前卡后面
        src_order = int((src or {}).get("order") or 0)
        new_rec = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "theme": new_theme,
            "title": new_theme,
            "content": content,
            "color": color,
            "date": now,
            "use_count": 0,
            "order": src_order + 1,
        }
        # 其后卡片 order +1
        for r in records:
            if int(r.get("order") or 0) > src_order:
                r["order"] = int(r.get("order") or 0) + 1
        records.append(new_rec)
        records = _reindex(_sorted_by_order(records))
        _save_records(records)
        self._all_records = records
        self._refresh_cards()
        # 进入新卡编辑态，方便继续改
        self._enter_edit(new_rec, copied=False)
        self._show_hint(f"已复制为 {new_theme}")
        QTimer.singleShot(1600, lambda: self._show_hint(self._edit_hint(copied=False)))

    def _delete_selected(self):
        """「删除」：删掉当前选中（或编辑中）的卡片。"""
        rid = self._active_card_id()
        if not rid:
            self._show_hint("请先点选一张卡片再删除")
            return
        record = next(
            (r for r in self._all_records if r.get("id") == rid),
            None,
        )
        if record is None:
            # 内存与磁盘不一致时兜底
            records = _load_records()
            record = next((r for r in records if r.get("id") == rid), None)
        if record is None:
            self._clear_form()
            self._show_hint("找不到要删除的卡片")
            return
        self._delete(record)

    def _delete(self, record):
        theme = record.get("theme") or record.get("title") or "此卡片"
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定删除「{theme}」吗？\n删除后无法恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        records = [r for r in _load_records() if r.get("id") != record.get("id")]
        records = _reindex(_sorted_by_order(records))
        _save_records(records)
        rid = record.get("id")
        if self._editing_id == rid or self._selected_id == rid:
            self._clear_form()
        self._all_records = records
        self._refresh_cards()

    def _reorder_cards(self, src_id: str, tgt_id: str, insert_after: bool = False):
        records = _sorted_by_order(_load_records())
        src = next((r for r in records if str(r.get("id")) == str(src_id)), None)
        if src is None:
            return
        records = [r for r in records if str(r.get("id")) != str(src_id)]
        tgt_index = next((i for i, r in enumerate(records) if str(r.get("id")) == str(tgt_id)), None)
        if tgt_index is None:
            records.append(src)
        else:
            insert_at = tgt_index + 1 if insert_after else tgt_index
            records.insert(insert_at, src)
        records = _reindex(records)
        _save_records(records)
        self._all_records = records
        self._refresh_cards()

    def _reorder_to_end(self, src_id: str):
        records = _sorted_by_order(_load_records())
        src = next((r for r in records if str(r.get("id")) == str(src_id)), None)
        if src is None:
            return
        records = [r for r in records if str(r.get("id")) != str(src_id)]
        records.append(src)
        records = _reindex(records)
        _save_records(records)
        self._all_records = records
        self._refresh_cards()
