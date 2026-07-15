"""
page_points_calc.py  —  积分计算页
放在 pages/ 目录下，与其他页面同级。
记录文件存到：项目根目录 / records / points_calc.txt
"""

import os
import json
from datetime import datetime

from styles.style_all import (
    install_card_title, restyle_card_title, theme, apply_btn_download, make_card,
    CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP, CARD_TITLE_BODY_GAP,
)

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QScrollArea, QFrame, QMessageBox,
    QSizePolicy, QComboBox,
)


def _record_zebra_bg() -> str:
    """历史记录斑马纹底色：暗/亮两套都要能看清深浅差。"""
    if theme.is_dark:
        # 在 #0f1430 功能区上略提亮（比 hover_veil 更明显一点）
        return "rgba(255, 255, 255, 0.07)"
    # 白底上用实色浅灰，半透明几乎看不出来
    return "#e8ecf2"


def _style_toggle_btn(btn: QPushButton):
    """切换按钮反色选中态。

    不用全局 QSS：`* { color:… }` 会把选中态文字仍刷成浅色，叠在浅底上像“字消失了”。
    这里用控件级 stylesheet + palette 双保险，暗/亮各自反色。
    """
    checked = btn.isChecked()
    if theme.is_dark:
        if checked:
            bg, fg, bd = "#e8eefc", "#0b1124", "#c5d0ea"
        else:
            bg, fg, bd = "rgba(255,255,255,0.06)", "#9fb0d7", "rgba(255,255,255,0.22)"
    else:
        if checked:
            bg, fg, bd = "#1f2937", "#f9fafb", "#111827"
        else:
            bg, fg, bd = "rgba(0,0,0,0.04)", "#4b5563", "rgba(0,0,0,0.14)"

    weight = "700" if checked else "600"
    # padding 要配合 setFixedHeight(28)，过大竖向 padding 会把字裁没
    btn.setStyleSheet(
        f"QPushButton#ToggleBtn {{"
        f"  background: {bg};"
        f"  color: {fg};"
        f"  border: 1px solid {bd};"
        f"  border-radius: 6px;"
        f"  padding: 2px 8px;"
        f"  font-size: 13px;"
        f"  font-weight: {weight};"
        f"}}"
        f"QPushButton#ToggleBtn:hover {{"
        f"  background: {bg};"
        f"  color: {fg};"
        f"  border: 1px solid {bd};"
        f"}}"
        f"QPushButton#ToggleBtn:checked {{"
        f"  background: {bg};"
        f"  color: {fg};"
        f"  border: 1px solid {bd};"
        f"}}"
    )
    # Windows 原生样式有时仍读 palette 画字色，这里同步写上
    pal = btn.palette()
    c_fg = QColor(fg)
    c_bg = QColor(bg) if not str(bg).startswith("rgba") else QColor(0, 0, 0, 0)
    pal.setColor(QPalette.ButtonText, c_fg)
    pal.setColor(QPalette.WindowText, c_fg)
    pal.setColor(QPalette.Text, c_fg)
    if c_bg.isValid() and c_bg.alpha() > 0:
        pal.setColor(QPalette.Button, c_bg)
    btn.setPalette(pal)

# ── 记录文件路径 ─────────────────────────────────────────────────────────────
RECORD_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "records", "points_calc.txt"
)

# ── 工具函数 ─────────────────────────────────────────────────────────────────
def _ensure_dir():
    os.makedirs(os.path.dirname(RECORD_FILE), exist_ok=True)

def _load_records() -> list:
    if not os.path.exists(RECORD_FILE):
        return []
    records = []
    with open(RECORD_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records

def _save_records(records: list):
    _ensure_dir()
    with open(RECORD_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ── 单行省略号标签 ───────────────────────────────────────────────────────────
class _ElideLabel(QLabel):
    """记录行里用：宽度不够时用"…"省略，而不是 setWordWrap(True) 自动换行。
    v9.9.6 修复：wordWrap(True) 配合 QSizePolicy.Ignored 会让这个标签的高度
    依赖当前宽度（hasHeightForWidth），窗口在被拖动/跨屏幕 DPI 重新布局时，
    Qt 有时会拿一个瞬时的、不准确的宽度去算这次的高度，算出来的高度又没被
    正确地重新收敛回去，日积月累就把主窗口的最小高度越撑越高（拖一次窗口，
    内容往下掉一截）——这跟之前"速存图文"页面遇到的是同一类问题。
    改成单行 + 手动省略号后，标签高度只取决于字体，跟宽度完全无关，
    从根上不会再有这种高度传染问题；原文完整内容放到 tooltip 里，鼠标悬停可看全。"""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setWordWrap(False)
        super().setText(text)

    def setText(self, text):
        self._full_text = text or ""
        self._refresh_elided()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refresh_elided()

    def _refresh_elided(self):
        fm = self.fontMetrics()
        elided = fm.elidedText(self._full_text, Qt.ElideRight, max(0, self.width()))
        super().setText(elided)
        self.setToolTip(self._full_text if elided != self._full_text else "")


# ── 记录行（单行）────────────────────────────────────────────────────────────
class RecordRow(QFrame):
    """一行显示一条记录：[平台] [日期] [费用] [用途·消耗] [成本]  [编辑][删除]"""
    def __init__(self, record: dict, on_edit, on_delete, on_cancel, is_even=False, is_editing=False, parent=None):
        super().__init__(parent)
        self._is_even = bool(is_even)
        self.setObjectName("RecordCard")          # hover/编辑态 都靠这个名字
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumHeight(38)
        # 斑马纹：控件级背景（暗/亮都可见）。QSS 属性选择器在部分 Qt 版本上不可靠，
        # 这里用主题色 + refresh_theme 双保险，保证两套主题都有深浅差。
        self._apply_zebra_bg()

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 8, 4)
        row.setSpacing(6)

        fee_label = "月费" if record.get("fee_type") == "monthly" else "年费"
        currency  = record.get("currency", "CNY")
        amount    = record.get("amount", 0)
        rate      = record.get("rate", 1.0)
        # ① 金额整数显示
        amt_disp  = int(amount) if float(amount) == int(float(amount)) else amount
        fee_str   = (f"{fee_label} ${amt_disp}（×{rate}）"
                     if currency == "USD" else f"{fee_label} ¥{amt_disp}")

        cost_per    = record.get("cost_per", 0)
        consume     = record.get("consume_pts", 0)
        is_video    = record.get("usage_type", "image") == "video"
        video_secs  = record.get("video_secs", 10)
        usage_label = f"生视频 {consume}积分/次({video_secs}秒)" if is_video else f"生图 {consume}积分/次"
        cost_str    = f"{cost_per:.4f}".rstrip("0").rstrip(".")
        cost_label  = f"每秒 ¥{cost_str}" if is_video else f"每张 ¥{cost_str}"

        def _cell(text, obj_name, stretch=1):
            lbl = _ElideLabel(text)
            lbl.setObjectName(obj_name)
            lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            lbl.setMinimumWidth(0)         # 允许被压缩到比文字自然宽度更窄（超出部分用省略号）
            lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            row.addWidget(lbl, stretch)
            return lbl

        _cell(record.get("platform", "未命名"), "RecordName",   2)
        _cell(record.get("date", ""),            "RecordDate",   2)
        _cell(fee_str,                           "RecordSub",    2)
        _cell(usage_label,                       "RecordSub",    3)
        _cell(cost_label,                        "RecordResult", 2)

        # 编辑 / 删除：正常态显示；编辑态时二者隐藏，换成单独的"取消编辑"
        self.btn_edit = QPushButton("编辑")
        self.btn_edit.setObjectName("RecordEditBtn")
        self.btn_edit.setFixedSize(52, 26)
        self.btn_edit.setCursor(Qt.PointingHandCursor)
        self.btn_edit.clicked.connect(lambda: on_edit(record))
        row.addWidget(self.btn_edit)

        self.btn_del = QPushButton("删除")
        self.btn_del.setObjectName("RecordDelBtn")
        self.btn_del.setFixedSize(52, 26)
        self.btn_del.setCursor(Qt.PointingHandCursor)
        self.btn_del.clicked.connect(lambda: on_delete(record))
        row.addWidget(self.btn_del)

        self.btn_cancel = QPushButton("取消编辑")
        self.btn_cancel.setObjectName("RecordCancelBtn")
        self.btn_cancel.setFixedSize(110, 26)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(lambda: on_cancel())
        row.addWidget(self.btn_cancel)

        self.set_editing(is_editing)

    def _apply_zebra_bg(self):
        """奇数/偶数行底色；偶数行用斑马纹，奇数行透明交给 QSS。"""
        if self._is_even:
            bg = _record_zebra_bg()
            self.setStyleSheet(
                f"QFrame#RecordCard {{ background-color: {bg}; }}"
            )
        else:
            self.setStyleSheet("")

    def refresh_theme(self, *_):
        """主题切换后重刷斑马纹（内联色不会随 app.qss 自动变）。"""
        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_zebra_bg()

    def set_editing(self, editing: bool):
        """切换到编辑态：编辑/删除 ↔ 取消编辑，同时驱动橙色外框选择器。"""
        self.setProperty("editing", "true" if editing else "false")
        self.btn_edit.setVisible(not editing)
        self.btn_del.setVisible(not editing)
        self.btn_cancel.setVisible(editing)
        self.style().unpolish(self)
        self.style().polish(self)
        # polish 之后再写斑马纹，避免被冲掉
        self._apply_zebra_bg()



# ── 主页面 ───────────────────────────────────────────────────────────────────
class PagePointsCalc(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PageRoot")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._editing_id  = None
        self._record_rows = {}
        self._toggle_btns = []   # 月费/CNY/生图 等切换按钮，主题切换时重刷反色
        self._last_result = None
        self._fee_type    = "monthly"
        self._currency    = "CNY"
        self._usage_type  = "image"
        self._video_secs  = 10

        self._build_ui()
        self._set_usage_type("image")   # 初始化结果卡片与时长选择器的显隐
        self._refresh_records()
        # 主题切换：斑马纹 + 切换按钮反色
        theme.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, *_):
        for row in getattr(self, "_record_rows", {}).values():
            if hasattr(row, "refresh_theme"):
                row.refresh_theme()
        for b in getattr(self, "_toggle_btns", []):
            _style_toggle_btn(b)

    # ── UI 构建 ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        page_layout = QVBoxLayout(self)
        # 与系统总览一致：ContentRoot 已有左右内边距，页面不再叠第二层
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(10)

        # 上半：输入参数 + 计算结果合并为一个区域，中间用竖线分隔，固定高度不拉伸
        page_layout.addWidget(self._build_top_panel(), 0)

        # 下半：历史记录吃掉剩余全部空间
        page_layout.addWidget(self._build_records_panel(), 1)

    # ── 顶部合并面板：左"输入参数" + 竖线分隔 + 右"计算结果" ────────────────────
    def _build_top_panel(self) -> QWidget:
        # 功能区标准卡：输入参数 + 计算结果（同一张卡，中间竖线分隔）
        box = make_card("CardPointsTop")

        outer = QHBoxLayout(box)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 左：输入参数 ─────────────────────────────────────────────────────
        left_wrap = QWidget()
        left_wrap.setStyleSheet("background: transparent;")
        form = QVBoxLayout(left_wrap)
        form.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, 14, CARD_BOTTOM_GAP)
        # spacing 与 CARD_TITLE_BODY_GAP 由 install_card_title 自动补偿，不叠加大空隙
        form.setSpacing(5)
        install_card_title(box, form, "输入参数")

        # ── 行1：平台名称 ＋ 月费/年费 ──────────────────────────────────────
        row1 = QHBoxLayout(); row1.setSpacing(8)
        lbl_p = self._lbl("平台名称"); lbl_p.setFixedWidth(72)
        row1.addWidget(lbl_p)
        self.inp_platform = self._inp("例：可灵、Midjourney、即梦…")
        row1.addWidget(self.inp_platform, 1)
        self.btn_monthly = self._toggle("月费", True,  lambda: self._set_fee_type("monthly"))
        self.btn_yearly  = self._toggle("年费", False, lambda: self._set_fee_type("yearly"))
        self.btn_monthly.setFixedWidth(64); self.btn_yearly.setFixedWidth(64)
        row1.addWidget(self.btn_monthly)
        row1.addWidget(self.btn_yearly)
        form.addLayout(row1)

        # ── 行2：订阅金额 ＋ CNY/USD ＋ 汇率 ─────────────────────────────────
        row2 = QHBoxLayout(); row2.setSpacing(8)
        lbl_a = self._lbl("订阅金额"); lbl_a.setFixedWidth(72)
        row2.addWidget(lbl_a)
        self.inp_amount = self._inp("输入金额")
        row2.addWidget(self.inp_amount, 1)
        self.btn_cny = self._toggle("CNY ¥", True,  lambda: self._set_currency("CNY"))
        self.btn_usd = self._toggle("USD $", False, lambda: self._set_currency("USD"))
        self.btn_cny.setFixedWidth(64); self.btn_usd.setFixedWidth(64)
        row2.addWidget(self.btn_cny)
        row2.addWidget(self.btn_usd)
        rate_lbl = self._lbl("汇率"); rate_lbl.setFixedWidth(28)
        self.inp_rate = QLineEdit("7.25")
        self.inp_rate.setObjectName("CalcInput")
        self.inp_rate.setFixedWidth(52); self.inp_rate.setFixedHeight(28)
        self.inp_rate.setToolTip("USD → CNY 汇率")
        row2.addWidget(rate_lbl)
        row2.addWidget(self.inp_rate)
        form.addLayout(row2)

        # ── 行3：每月积分 ＋ 单次消耗 ────────────────────────────────────────
        row3 = QHBoxLayout(); row3.setSpacing(8)
        lbl_mp = self._lbl("每月到账积分"); lbl_mp.setFixedWidth(80)
        row3.addWidget(lbl_mp)
        self.inp_monthly_pts = self._inp("例：3000")
        row3.addWidget(self.inp_monthly_pts, 1)
        lbl_cp = self._lbl("单次消耗积分"); lbl_cp.setFixedWidth(80)
        row3.addWidget(lbl_cp)
        self.inp_consume = self._inp("例：100")
        row3.addWidget(self.inp_consume, 1)
        form.addLayout(row3)

        # ── 行4a：用途类型 ＋ 立即计算 ────────────────────────────────────────
        row4a = QHBoxLayout(); row4a.setSpacing(8)
        lbl_u = self._lbl("用途类型"); lbl_u.setFixedWidth(72)
        row4a.addWidget(lbl_u)
        self.btn_usage_image = self._toggle("生图",   True,  lambda: self._set_usage_type("image"))
        self.btn_usage_video = self._toggle("生视频", False, lambda: self._set_usage_type("video"))
        self.btn_usage_image.setFixedWidth(64); self.btn_usage_video.setFixedWidth(72)
        row4a.addWidget(self.btn_usage_image)
        row4a.addWidget(self.btn_usage_video)
        row4a.addStretch(1)

        # ② 立即计算按钮：专用 objectName 保证宽度足够
        self.btn_calc = QPushButton("立即计算")
        self.btn_calc.setObjectName("CalcRunBtn")
        self.btn_calc.setCursor(Qt.PointingHandCursor)
        self.btn_calc.setFixedHeight(28)
        self.btn_calc.setMinimumWidth(90)
        self.btn_calc.clicked.connect(self._calc)
        row4a.addWidget(self.btn_calc)
        form.addLayout(row4a)

        # ── 行4b：视频时长步进器（单独一行，窗口变窄也不会跟行4a挤在一起撑出横向滚动条）──
        row4b = QHBoxLayout(); row4b.setSpacing(8)

        # 视频时长步进器：|◀  ◀  [10秒]  ▶  ▶|
        lbl_dur = self._lbl("视频时长"); lbl_dur.setFixedWidth(56)
        row4b.addWidget(lbl_dur)

        def _stepper_btn(symbol):
            b = QPushButton(symbol)
            b.setObjectName("StepperBtn")
            b.setFixedSize(26, 28)
            b.setCursor(Qt.PointingHandCursor)
            return b

        self._video_secs = 10
        self.lbl_secs_display = QLabel("10 秒")
        self.lbl_secs_display.setObjectName("SecsDisplay")
        self.lbl_secs_display.setAlignment(Qt.AlignCenter)
        self.lbl_secs_display.setFixedWidth(48)
        self.lbl_secs_display.setFixedHeight(28)

        btn_min  = _stepper_btn("◀◀")
        btn_dec  = _stepper_btn("◀")
        btn_inc  = _stepper_btn("▶")
        btn_max  = _stepper_btn("▶▶")

        def _set_secs(s):
            self._video_secs = max(4, min(15, s))   # ③ 最小4秒
            self.lbl_secs_display.setText(f"{self._video_secs} 秒")
            idx = self.cmb_video_secs.findData(self._video_secs)
            if idx >= 0: self.cmb_video_secs.blockSignals(True); self.cmb_video_secs.setCurrentIndex(idx); self.cmb_video_secs.blockSignals(False)

        btn_min.clicked.connect(lambda: _set_secs(4))
        btn_dec.clicked.connect(lambda: _set_secs(self._video_secs - 1))
        btn_inc.clicked.connect(lambda: _set_secs(self._video_secs + 1))
        btn_max.clicked.connect(lambda: _set_secs(15))

        # 隐藏的 QComboBox 仅用于 _edit_record 回填
        self.cmb_video_secs = QComboBox()
        self.cmb_video_secs.setVisible(False)
        for s in range(4, 16):   # ③ 从4秒开始
            self.cmb_video_secs.addItem(f"{s} 秒", s)
        self.cmb_video_secs.setCurrentIndex(6)   # 默认10秒（index=6 in 4..15）

        for w in (btn_min, btn_dec, self.lbl_secs_display, btn_inc, btn_max):
            row4b.addWidget(w)
        row4b.addStretch(1)
        form.addLayout(row4b)

        # video_dur_row 占位（避免 _set_usage_type 报 AttributeError）
        self.video_dur_row = QWidget()

        outer.addWidget(left_wrap, 3)

        # ── 中：不显眼的竖直分隔线（替代原来两个独立卡片的双重边框）──────────
        divider = QFrame()
        divider.setObjectName("CalcTopDivider")
        divider.setFrameShape(QFrame.VLine)
        divider.setFrameShadow(QFrame.Plain)
        outer.addWidget(divider)

        # ── 右：计算结果 ─────────────────────────────────────────────────────
        right_wrap = QWidget()
        right_wrap.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(right_wrap)
        layout.setContentsMargins(14, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        layout.setSpacing(5)
        # 右侧标题：与 install_card_title 同规范（全局 CARD_TITLE_BODY_GAP）
        t_res = QLabel("计算结果")
        t_res.setProperty("role", "card-title")
        restyle_card_title(t_res)
        t_res.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        head = QWidget()
        head.setStyleSheet("background:transparent;border:none;")
        head.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        head_l = QVBoxLayout(head)
        head_l.setContentsMargins(0, 0, 0, max(0, CARD_TITLE_BODY_GAP - max(0, layout.spacing())))
        head_l.setSpacing(0)
        head_l.addWidget(t_res)
        layout.insertWidget(0, head)

        # 每行：[标签·左弹性] [金额·固定宽右对齐]，QFrame 确保 QSS 背景生效
        def metric_row(label_text, value_init="—"):
            w = QFrame()
            w.setObjectName("MetricCard")
            w.setAttribute(Qt.WA_StyledBackground, True)
            w.setFrameShape(QFrame.NoFrame)
            w.setFixedHeight(32)   # 压缩行高，配合整个区域瘦身
            hl = QHBoxLayout(w)
            hl.setContentsMargins(12, 0, 12, 0)
            hl.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setObjectName("MetricLabel")
            lbl.setAttribute(Qt.WA_StyledBackground, True)
            lbl.setStyleSheet("background: transparent;")   # 兜底：避免文字后出现色块
            val = QLabel(value_init)
            val.setObjectName("MetricValue")
            val.setAttribute(Qt.WA_StyledBackground, True)
            val.setStyleSheet("background: transparent;")   # 兜底：避免文字后出现色块
            val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            hl.addWidget(lbl, 1)
            hl.addWidget(val, 1)
            return w, val

        self.lbl_cost_image = metric_row("图片生成（每张）", "—")
        self.lbl_cost_video = metric_row("视频生成（每秒）", "—")
        self.lbl_monthly    = metric_row("月均订阅成本（人民币）", "—")
        layout.addWidget(self.lbl_cost_image[0])
        layout.addWidget(self.lbl_cost_video[0])
        layout.addWidget(self.lbl_monthly[0])

        # ③ 提示文字：固定高度占位，文字内容变但容器尺寸不变
        self.result_hint = QLabel("")
        self.result_hint.setObjectName("ResultHint")
        self.result_hint.setAlignment(Qt.AlignCenter)
        self.result_hint.setWordWrap(True)
        self.result_hint.setFixedHeight(24)   # 压缩，始终占这么高，不再 setVisible
        layout.addWidget(self.result_hint)

        # 主操作：与抖音「粘贴并解析」同款（控件级样式，防父级 transparent 盖掉字色）
        self.btn_save = QPushButton("保存到记录")
        apply_btn_download(self.btn_save)
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_record)
        layout.addWidget(self.btn_save)

        outer.addWidget(right_wrap, 2)

        return box


    def _metric(self, label_text, value_text):
        """兼容旧调用（未使用，保留避免报错）"""
        c = QWidget(); c.setObjectName("MetricCard"); c.setAttribute(Qt.WA_StyledBackground, True)
        v = QVBoxLayout(c); v.setContentsMargins(12, 8, 12, 8); v.setSpacing(2)
        lbl = QLabel(label_text); lbl.setObjectName("MetricLabel")
        val = QLabel(value_text); val.setObjectName("MetricValue")
        v.addWidget(lbl); v.addWidget(val)
        return c, val

    # ── 历史记录面板 ─────────────────────────────────────────────────────────
    def _build_records_panel(self) -> QWidget:
        box = make_card("CardPointsRecords")

        outer = QVBoxLayout(box)
        outer.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        # 与 CARD_TITLE_BODY_GAP 自动补偿，正文区块间距 8
        outer.setSpacing(8)
        install_card_title(box, outer, "历史记录")

        def _make_section(title_text, icon):
            sec = QWidget()
            sec.setAttribute(Qt.WA_StyledBackground, True)
            sec.setStyleSheet("background: transparent;")   # 避免退回全局 QWidget 底色、和卡片背景不一致出现色块
            vl = QVBoxLayout(sec)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)

            # 表头：第一列直接用"图标 + 分区名"替换原来的"平台"文字，
            # 不再单独占一行小标题，整体更紧凑
            header = QWidget()
            header.setObjectName("RecordHeader")
            header.setAttribute(Qt.WA_StyledBackground, True)
            hh = QHBoxLayout(header)
            hh.setContentsMargins(10, 4, 8, 4)
            hh.setSpacing(6)
            columns = [(f"{icon}  {title_text}", 2, "RecordSectionHeaderCell")] + [
                (txt, stretch, "RecordHeaderCell")
                for txt, stretch in [("时间", 2), ("费用", 2), ("用途/消耗", 3), ("成本", 2)]
            ]
            for txt, stretch, obj in columns:
                hl = _ElideLabel(txt); hl.setObjectName(obj)
                hl.setMinimumWidth(0)
                hl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                hh.addWidget(hl, stretch)
            sp = QWidget(); sp.setFixedWidth(52*2+6+16)
            hh.addWidget(sp, 0)
            vl.addWidget(header)

            sep = QFrame(); sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("RecordDivider")
            vl.addWidget(sep)

            # 滚动区（竖向滚动条：记录区标准，同截图工具）
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setObjectName("RecordsScroll")
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            container = QWidget()
            container.setObjectName("RecordsContainer")
            container.setAttribute(Qt.WA_StyledBackground, True)
            rec_layout = QVBoxLayout(container)
            rec_layout.setContentsMargins(0, 4, 0, 4)
            rec_layout.setSpacing(3)
            rec_layout.addStretch(1)
            scroll.setWidget(container)
            vl.addWidget(scroll, 1)
            return sec, rec_layout

        sec_img, self.layout_image = _make_section("生图记录", "🖼")
        sec_vid, self.layout_video = _make_section("生视频记录", "🎬")

        hline = QFrame(); hline.setFrameShape(QFrame.HLine)
        hline.setObjectName("RecordDivider")

        outer.addWidget(sec_img, 1)
        outer.addWidget(hline)
        outer.addWidget(sec_vid, 1)
        return box

    # ── 控件工厂 ─────────────────────────────────────────────────────────────
    def _lbl(self, text):
        l = QLabel(text); l.setObjectName("CalcFieldLabel"); return l

    def _inp(self, placeholder=""):
        e = QLineEdit(); e.setObjectName("CalcInput")
        e.setPlaceholderText(placeholder); e.setFixedHeight(28); return e

    def _toggle(self, text, checked, slot):
        b = QPushButton(text)
        b.setObjectName("ToggleBtn")
        b.setCheckable(True)
        b.setChecked(checked)
        b.setFixedHeight(28)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        # 选中态变化时重刷反色（含程序里 setChecked 联动的另一颗按钮）
        b.toggled.connect(lambda _c, btn=b: _style_toggle_btn(btn))
        _style_toggle_btn(b)
        self._toggle_btns.append(b)
        return b

    def _hrow(self, *widgets):
        h = QHBoxLayout(); h.setSpacing(6)
        for w in widgets: h.addWidget(w)
        h.addStretch(1); return h

    # ── 状态切换 ─────────────────────────────────────────────────────────────
    def _set_fee_type(self, t):
        self._fee_type = t
        self.btn_monthly.setChecked(t == "monthly")
        self.btn_yearly.setChecked(t == "yearly")
        _style_toggle_btn(self.btn_monthly)
        _style_toggle_btn(self.btn_yearly)

    def _set_currency(self, c):
        self._currency = c
        self.btn_cny.setChecked(c == "CNY")
        self.btn_usd.setChecked(c == "USD")
        _style_toggle_btn(self.btn_cny)
        _style_toggle_btn(self.btn_usd)

    def _set_usage_type(self, t):
        self._usage_type = t
        self.btn_usage_image.setChecked(t == "image")
        self.btn_usage_video.setChecked(t == "video")
        _style_toggle_btn(self.btn_usage_image)
        _style_toggle_btn(self.btn_usage_video)
        self.lbl_cost_image[0].setVisible(t == "image")
        self.lbl_cost_video[0].setVisible(t == "video")

    # ── 计算 ─────────────────────────────────────────────────────────────────
    def _calc(self):
        platform = self.inp_platform.text().strip() or "未命名平台"

        try:
            amount = float(self.inp_amount.text().strip()); assert amount > 0
        except Exception:
            self._show_hint("⚠ 请输入有效的订阅金额"); return

        is_usd = (self._currency == "USD")
        if is_usd:
            try:
                rate = float(self.inp_rate.text().strip()); assert rate > 0
            except Exception:
                self._show_hint("⚠ 请输入有效的汇率"); return
        else:
            rate = 1.0

        try:
            monthly_pts = int(self.inp_monthly_pts.text().strip()); assert monthly_pts > 0
        except Exception:
            self._show_hint("⚠ 请输入有效的每月积分数"); return

        try:
            consume = int(self.inp_consume.text().strip()); assert consume > 0
        except Exception:
            self._show_hint("⚠ 请输入有效的单次消耗积分"); return

        amount_cny       = amount * rate if is_usd else amount
        monthly_cost_cny = amount_cny if self._fee_type == "monthly" else amount_cny / 12
        uses_per_mo      = monthly_pts // consume
        cost_per_use     = monthly_cost_cny / uses_per_mo if uses_per_mo > 0 else float("inf")

        is_video = self._usage_type == "video"
        if is_video:
            video_secs   = self._video_secs
            cost_per_sec = cost_per_use / video_secs if video_secs > 0 else float("inf")
            cost_str     = f"{cost_per_sec:.4f}".rstrip("0").rstrip(".")
            self.lbl_cost_video[1].setText(f"¥ {cost_str}")   # 去掉 / 秒
            cost_per = cost_per_sec
        else:
            video_secs = 0
            cost_str   = f"{cost_per_use:.4f}".rstrip("0").rstrip(".")
            self.lbl_cost_image[1].setText(f"¥ {cost_str}")
            cost_per = cost_per_use

        monthly_str = f"{monthly_cost_cny:.2f}".rstrip("0").rstrip(".")
        self.lbl_monthly[1].setText(f"¥ {monthly_str}")
        self._show_hint("")
        self.btn_save.setEnabled(True)

        self._last_result = {
            "id":               self._editing_id or datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "platform":         platform,
            "date":             datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fee_type":         self._fee_type,
            "currency":         "USD" if is_usd else "CNY",
            "amount":           amount,
            "rate":             rate if is_usd else 1.0,
            "monthly_pts":      monthly_pts,
            "consume_pts":      consume,
            "usage_type":       self._usage_type,
            "video_secs":       video_secs,
            "monthly_cost_cny": round(monthly_cost_cny, 4),
            "cost_per":         round(cost_per, 6),
            "uses_per_mo":      uses_per_mo,
        }

    def _show_hint(self, text):
        self.result_hint.setText(text)

    # ── 保存 / 编辑 / 删除 ──────────────────────────────────────────────────
    def _save_record(self):
        if not self._last_result: return
        records = _load_records()
        if self._editing_id:
            records = [r for r in records if r.get("id") != self._editing_id]
            self._editing_id = None
            self.btn_calc.setText("立即计算")
            self.btn_save.setText("保存到记录")
        records.append(self._last_result)
        _save_records(records)
        self._last_result = None
        self.btn_save.setEnabled(False)
        self._refresh_records()

    def _edit_record(self, record):
        self._editing_id = record.get("id")
        self.inp_platform.setText(record.get("platform", ""))
        self._set_fee_type(record.get("fee_type", "monthly"))
        currency = record.get("currency", "CNY")
        self._set_currency(currency)
        # ① 金额不显示小数
        amount = record.get("amount", "")
        self.inp_amount.setText(str(int(amount)) if isinstance(amount, float) and amount == int(amount) else str(amount))
        # ① 汇率：CNY记录存的是1.0，不应回填，只有USD才显示真实汇率
        if currency == "USD":
            self.inp_rate.setText(str(record.get("rate", "7.25")))
        else:
            self.inp_rate.setText("7.25")
        self.inp_monthly_pts.setText(str(record.get("monthly_pts", "")))
        self.inp_consume.setText(str(record.get("consume_pts", "")))
        self._set_usage_type(record.get("usage_type", "image"))
        # 恢复视频时长 → 同步步进器显示
        video_secs = record.get("video_secs", 10)
        self._video_secs = video_secs
        self.lbl_secs_display.setText(f"{video_secs} 秒")
        idx = self.cmb_video_secs.findData(video_secs)
        if idx >= 0:
            self.cmb_video_secs.blockSignals(True)
            self.cmb_video_secs.setCurrentIndex(idx)
            self.cmb_video_secs.blockSignals(False)
        self.btn_calc.setText("重新计算")
        self.btn_save.setText("保存修改")
        self.btn_save.setEnabled(False)
        self._show_hint("📝 编辑模式：修改后请点击「重新计算」再保存")
        self._mark_editing_row(self._editing_id)

    def _mark_editing_row(self, record_id):
        """把记录行的“编辑/删除 ↔ 取消编辑”状态，切换到 record_id 对应的那一行（None 表示全部取消）。"""
        for rid, row in getattr(self, "_record_rows", {}).items():
            row.set_editing(rid == record_id)

    def _cancel_edit(self):
        """点击某条记录的「取消编辑」：退出编辑模式，输入区恢复初始状态，不保存任何修改。"""
        self._editing_id  = None
        self._last_result = None
        self.inp_platform.clear()
        self.inp_amount.clear()
        self.inp_rate.setText("7.25")
        self._set_currency("CNY")
        self._set_fee_type("monthly")
        self.inp_monthly_pts.clear()
        self.inp_consume.clear()
        self._set_usage_type("image")
        self._video_secs = 10
        self.lbl_secs_display.setText("10 秒")
        self.cmb_video_secs.blockSignals(True)
        self.cmb_video_secs.setCurrentIndex(6)
        self.cmb_video_secs.blockSignals(False)
        self.btn_calc.setText("立即计算")
        self.btn_save.setText("保存到记录")
        self.btn_save.setEnabled(False)
        self._show_hint("")
        self._mark_editing_row(None)

    def _delete_record(self, record):
        if QMessageBox.question(
            self, "确认删除",
            f"确定要删除「{record.get('platform', '此记录')}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) == QMessageBox.Yes:
            records = [r for r in _load_records() if r.get("id") != record.get("id")]
            _save_records(records)
            self._refresh_records()

    def _refresh_records(self):
        for layout in (self.layout_image, self.layout_video):
            while layout.count() > 1:
                item = layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()

        records   = _load_records()
        img_recs  = [r for r in records if r.get("usage_type", "image") == "image"]
        vid_recs  = [r for r in records if r.get("usage_type", "image") != "image"]

        self._record_rows = {}

        def _fill(layout, recs, empty_text):
            if not recs:
                lbl = QLabel(empty_text)
                lbl.setObjectName("RecordEmpty")
                lbl.setAlignment(Qt.AlignCenter)
                layout.insertWidget(0, lbl)
                return
            for i, record in enumerate(reversed(recs)):
                rid = record.get("id")
                row = RecordRow(record, self._edit_record, self._delete_record, self._cancel_edit,
                                 is_even=(i % 2 == 1), is_editing=(rid == self._editing_id))
                layout.insertWidget(i, row)
                self._record_rows[rid] = row

        _fill(self.layout_image, img_recs, "暂无生图记录")
        _fill(self.layout_video, vid_recs, "暂无生视频记录")
