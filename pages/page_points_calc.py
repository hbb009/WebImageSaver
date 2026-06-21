"""
page_points_calc.py  —  积分计算页
放在 pages/ 目录下，与其他页面同级。
记录文件存到：项目根目录 / records / points_calc.txt
"""

import os
import json
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QScrollArea, QFrame, QMessageBox,
    QSizePolicy, QComboBox,
)

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


# ── 记录行（单行）────────────────────────────────────────────────────────────
class RecordRow(QFrame):
    """一行显示一条记录：[平台] [日期] [费用] [用途·消耗] [成本]  [编辑][删除]"""
    def __init__(self, record: dict, on_edit, on_delete, is_even=False, parent=None):
        super().__init__(parent)
        self.setObjectName("RecordCard")          # hover/border 都靠这个名字
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumHeight(38)
        # ⑤ 双数行直接用内联样式叠加轻微背景，不影响 objectName 的 hover 选择器
        if is_even:
            self.setStyleSheet("QFrame#RecordCard { background-color: rgba(255,255,255,0.045); }")

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
            lbl = QLabel(text)
            lbl.setObjectName(obj_name)
            lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            lbl.setWordWrap(False)
            row.addWidget(lbl, stretch)
            return lbl

        _cell(record.get("platform", "未命名"), "RecordName",   2)
        _cell(record.get("date", ""),            "RecordDate",   2)
        _cell(fee_str,                           "RecordSub",    2)
        _cell(usage_label,                       "RecordSub",    3)
        _cell(cost_label,                        "RecordResult", 2)

        for txt, obj, cb in [
            ("编辑", "RecordEditBtn", lambda: on_edit(record)),
            ("删除", "RecordDelBtn",  lambda: on_delete(record)),
        ]:
            btn = QPushButton(txt)
            btn.setObjectName(obj)
            btn.setFixedSize(52, 26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(cb)
            row.addWidget(btn)


# ── 主页面 ───────────────────────────────────────────────────────────────────
class PagePointsCalc(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PageRoot")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._editing_id  = None
        self._last_result = None
        self._fee_type    = "monthly"
        self._currency    = "CNY"
        self._usage_type  = "image"
        self._video_secs  = 10

        self._build_ui()
        self._set_usage_type("image")   # 初始化结果卡片与时长选择器的显隐
        self._refresh_records()

    # ── UI 构建 ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(16, 12, 16, 12)
        page_layout.setSpacing(10)

        # 上半：左侧输入 + 右侧结果，固定高度，不拉伸
        top_row = QHBoxLayout()
        top_row.setSpacing(14)
        top_row.addWidget(self._build_input_panel(), 3)
        top_row.addWidget(self._build_result_panel(), 2)
        page_layout.addLayout(top_row, 0)

        # 下半：历史记录吃掉剩余全部空间
        page_layout.addWidget(self._build_records_panel(), 1)

    # ── 输入面板 ─────────────────────────────────────────────────────────────
    def _build_input_panel(self) -> QGroupBox:
        box = QGroupBox("输入参数")
        box.setObjectName("CalcInputBox")
        box.setAttribute(Qt.WA_StyledBackground, True)

        form = QVBoxLayout(box)
        form.setContentsMargins(12, 10, 12, 10)
        form.setSpacing(6)

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

        # ── 行4：用途类型 ＋ 视频时长步进器 ＋ 立即计算 ──────────────────────
        row4 = QHBoxLayout(); row4.setSpacing(8)
        lbl_u = self._lbl("用途类型"); lbl_u.setFixedWidth(72)
        row4.addWidget(lbl_u)
        self.btn_usage_image = self._toggle("生图",   True,  lambda: self._set_usage_type("image"))
        self.btn_usage_video = self._toggle("生视频", False, lambda: self._set_usage_type("video"))
        self.btn_usage_image.setFixedWidth(64); self.btn_usage_video.setFixedWidth(72)
        row4.addWidget(self.btn_usage_image)
        row4.addWidget(self.btn_usage_video)

        # 视频时长步进器：|◀  ◀  [10秒]  ▶  ▶|
        lbl_dur = self._lbl("视频时长"); lbl_dur.setFixedWidth(56)
        row4.addWidget(lbl_dur)

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
            row4.addWidget(w)

        row4.addStretch(1)

        # ② 立即计算按钮：专用 objectName 保证宽度足够
        self.btn_calc = QPushButton("立即计算")
        self.btn_calc.setObjectName("CalcRunBtn")
        self.btn_calc.setCursor(Qt.PointingHandCursor)
        self.btn_calc.setFixedHeight(28)
        self.btn_calc.setMinimumWidth(90)
        self.btn_calc.clicked.connect(self._calc)
        row4.addWidget(self.btn_calc)
        form.addLayout(row4)

        # video_dur_row 占位（避免 _set_usage_type 报 AttributeError）
        self.video_dur_row = QWidget()

        return box

    # ── 结果面板 ─────────────────────────────────────────────────────────────
    def _build_result_panel(self) -> QGroupBox:
        box = QGroupBox("计算结果")
        box.setObjectName("CalcResultBox")
        box.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 每行：[标签·左弹性] [金额·固定宽右对齐]，QFrame 确保 QSS 背景生效
        def metric_row(label_text, value_init="—"):
            w = QFrame()
            w.setObjectName("MetricCard")
            w.setAttribute(Qt.WA_StyledBackground, True)
            w.setFrameShape(QFrame.NoFrame)
            w.setFixedHeight(40)
            hl = QHBoxLayout(w)
            hl.setContentsMargins(12, 0, 12, 0)
            hl.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setObjectName("MetricLabel")
            lbl.setAttribute(Qt.WA_StyledBackground, True)
            val = QLabel(value_init)
            val.setObjectName("MetricValue")
            val.setAttribute(Qt.WA_StyledBackground, True)
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
        self.result_hint.setFixedHeight(32)   # 始终占这么高，不再 setVisible
        layout.addWidget(self.result_hint)

        layout.addStretch(1)

        self.btn_save = QPushButton("保存到记录")
        self.btn_save.setObjectName("SaveBtn")
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setFixedHeight(34)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_record)
        layout.addWidget(self.btn_save)

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
    def _build_records_panel(self) -> QGroupBox:
        box = QGroupBox("历史记录")
        box.setObjectName("RecordsBox")
        box.setAttribute(Qt.WA_StyledBackground, True)

        outer = QVBoxLayout(box)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        def _make_section(title_text, icon):
            sec = QWidget()
            sec.setAttribute(Qt.WA_StyledBackground, True)
            vl = QVBoxLayout(sec)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)

            # 小标题
            title_bar = QWidget()
            title_bar.setObjectName("RecordSectionTitle")
            title_bar.setAttribute(Qt.WA_StyledBackground, True)
            tb = QHBoxLayout(title_bar)
            tb.setContentsMargins(10, 4, 10, 4)
            lbl = QLabel(f"{icon}  {title_text}")
            lbl.setObjectName("RecordSectionLabel")
            tb.addWidget(lbl); tb.addStretch(1)
            vl.addWidget(title_bar)

            # 表头
            header = QWidget()
            header.setObjectName("RecordHeader")
            header.setAttribute(Qt.WA_StyledBackground, True)
            hh = QHBoxLayout(header)
            hh.setContentsMargins(10, 3, 8, 3)
            hh.setSpacing(6)
            for txt, stretch in [("平台",2),("时间",2),("费用",2),("用途/消耗",3),("成本",2)]:
                hl = QLabel(txt); hl.setObjectName("RecordHeaderCell")
                hh.addWidget(hl, stretch)
            sp = QWidget(); sp.setFixedWidth(52*2+6+16)
            hh.addWidget(sp, 0)
            vl.addWidget(header)

            sep = QFrame(); sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("RecordDivider")
            vl.addWidget(sep)

            # 滚动区
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setObjectName("RecordsScroll")
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
        b = QPushButton(text); b.setObjectName("ToggleBtn")
        b.setCheckable(True); b.setChecked(checked)
        b.setFixedHeight(28); b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot); return b

    def _hrow(self, *widgets):
        h = QHBoxLayout(); h.setSpacing(6)
        for w in widgets: h.addWidget(w)
        h.addStretch(1); return h

    # ── 状态切换 ─────────────────────────────────────────────────────────────
    def _set_fee_type(self, t):
        self._fee_type = t
        self.btn_monthly.setChecked(t == "monthly")
        self.btn_yearly.setChecked(t == "yearly")

    def _set_currency(self, c):
        self._currency = c
        self.btn_cny.setChecked(c == "CNY")
        self.btn_usd.setChecked(c == "USD")

    def _set_usage_type(self, t):
        self._usage_type = t
        self.btn_usage_image.setChecked(t == "image")
        self.btn_usage_video.setChecked(t == "video")
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

        def _fill(layout, recs, empty_text):
            if not recs:
                lbl = QLabel(empty_text)
                lbl.setObjectName("RecordEmpty")
                lbl.setAlignment(Qt.AlignCenter)
                layout.insertWidget(0, lbl)
                return
            for i, record in enumerate(reversed(recs)):
                row = RecordRow(record, self._edit_record, self._delete_record, is_even=(i % 2 == 1))
                layout.insertWidget(i, row)

        _fill(self.layout_image, img_recs, "暂无生图记录")
        _fill(self.layout_video, vid_recs, "暂无生视频记录")
