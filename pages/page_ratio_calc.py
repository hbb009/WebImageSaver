# pages/page_ratio_calc.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QButtonGroup, QGroupBox, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer
from styles.style_all import (
    install_card_title,
    restyle_card_title,
    make_card,
    CARD_TOP_GAP,
    CARD_LEFT_GAP,
    CARD_RIGHT_GAP,
    CARD_BOTTOM_GAP,
    theme,
)
from utils.flow_layout import FlowLayout
import ast


class PageRatioCalc(QWidget):
    def __init__(self):
        super().__init__()

        def _typo(w: QLabel, name: str):
            w.setProperty("typo", name)
            w.style().unpolish(w); w.style().polish(w)

        # 卡片标题：内联样式渲染，主题切换需要手动重刷（见 style_common.restyle_card_title）
        self._theme_titles = []

        # 外层滚动区，内容较多时可垂直滚动；横向滚动条强制关闭——
        # 窗口变窄时靠内部各处的 FlowLayout 自动换行，不允许左右拖动。
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        # 顶层：左（比例 + 大小写 + 大写汉字）· 右（计算器 + 汇率）
        # 与系统总览一致：ContentRoot 已有左右内边距，页面不再叠第二层
        root = QHBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.setAlignment(Qt.AlignTop)

        # ═══════════════ 左列 ═══════════════
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignTop)
        left.setSpacing(10)
        root.addLayout(left, 2)

        # 内部状态文案（用于各操作提示，如"计算完成"/"已复制"），不再显示绿灯+文字条
        self.status = QLabel("🟢 就绪")
        _typo(self.status, "body")

        # ── 比例计算器（功能区标准卡） ──────────────────────
        gb_ratio = make_card("CardRatioCalc")
        ratio_box = QVBoxLayout(gb_ratio)
        ratio_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        self._theme_titles.append(install_card_title(gb_ratio, ratio_box, "比例计算器"))
        left.addWidget(gb_ratio)

        self.a, self.b, self.c, self.d = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        for w, p, obj in [
            (self.a, 'A', 'RatioA'), (self.b, 'B', 'RatioB'),
            (self.c, 'C', 'RatioC'), (self.d, 'D', 'RatioD'),
        ]:
            w.setPlaceholderText(p); w.setObjectName(obj)
            w.setFixedHeight(40); w.setAlignment(Qt.AlignCenter)
            w.setStyleSheet("font-size:16px;")
        self.d.setReadOnly(True); self.d.setEnabled(False)

        self._debounce = QTimer(self); self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._ratio_calc)
        for w in (self.a, self.b, self.c):
            w.textChanged.connect(lambda _=None: self._debounce.start(600))

        r1 = QHBoxLayout()
        labA = QLabel("A"); _typo(labA, "body")
        labC = QLabel("C"); _typo(labC, "body")
        r1.addWidget(labA); r1.addWidget(self.a); r1.addStretch(1)
        r1.addWidget(labC); r1.addWidget(self.c)
        btn_copy_c = QPushButton("复制")
        btn_copy_c.setProperty("role", "nav")
        btn_copy_c.style().unpolish(btn_copy_c); btn_copy_c.style().polish(btn_copy_c)
        btn_copy_c.setToolTip("复制 C 值到剪贴板")
        btn_copy_c.clicked.connect(self._copy_c)
        r1.addWidget(btn_copy_c)
        ratio_box.addLayout(r1)

        r2 = QHBoxLayout()
        labB = QLabel("B"); _typo(labB, "body")
        labD = QLabel("D"); _typo(labD, "body")
        r2.addWidget(labB); r2.addWidget(self.b); r2.addStretch(1)
        r2.addWidget(labD); r2.addWidget(self.d)
        btn_copy_d = QPushButton("复制")
        btn_copy_d.setProperty("role", "nav")
        btn_copy_d.style().unpolish(btn_copy_d); btn_copy_d.style().polish(btn_copy_d)
        btn_copy_d.setToolTip("复制 D 值到剪贴板")
        btn_copy_d.clicked.connect(self._copy_d)
        r2.addWidget(btn_copy_d)
        ratio_box.addLayout(r2)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.NoFrame)   # 4.15：QFrame 一旦吃到 QSS，原生 frameShape 画法会失效，改用实心矩形
        sep1.setObjectName("RatioSep")
        sep1.setFixedHeight(1)
        ratio_box.addWidget(sep1)

        chips_row = FlowLayout(h_spacing=8, v_spacing=8)
        ratio_box.addLayout(chips_row)
        presets = [
            ("1:1",   1,  1, 1536), ("16:9", 16,  9, 1536),
            ("4:3",   4,  3, 1536), ("3:2",   3,  2, 1536),
            ("3:4",   3,  4, 1536), ("2:3",   2,  3, 1536),
            ("9:16",  9, 16, 1536), ("21:9", 21,  9, 2048),
        ]
        self._chip_group = QButtonGroup(self); self._chip_group.setExclusive(True)
        for name, ra, rb, long_side in presets:
            short = round(long_side * rb / ra) if ra >= rb else round(long_side * ra / rb)
            w_px  = long_side if ra >= rb else short
            h_px  = short     if ra >= rb else long_side
            b = QPushButton(name); b.setCheckable(True); b.setObjectName("RatioChip")
            b.setProperty("role", "nav")
            b.setToolTip(f"{w_px}×{h_px} px（点击自动填入 C={long_side}）")
            b.style().unpolish(b); b.style().polish(b)
            b.clicked.connect(lambda _, a=ra, bb=rb, label=name, c=long_side:
                              self._apply_ratio(a, bb, label, c))
            self._chip_group.addButton(b); chips_row.addWidget(b)
        lbl_swap = QLabel("A与B数值互换"); _typo(lbl_swap, "muted")
        chips_row.addWidget(lbl_swap)
        btn_swap = QPushButton("交换")
        btn_swap.setProperty("role", "nav")
        btn_swap.style().unpolish(btn_swap); btn_swap.style().polish(btn_swap)
        btn_swap.clicked.connect(self._swap)
        chips_row.addWidget(btn_swap)

        # ── 金额大小写转换（功能区标准卡） ──────────────────
        gb_case = make_card("CardRatioCase")
        case_box = QVBoxLayout(gb_case)
        case_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        self._theme_titles.append(install_card_title(gb_case, case_box, "金额大小写转换"))
        left.addWidget(gb_case)

        row_in = QHBoxLayout()
        lbl_small = QLabel("小写金额："); _typo(lbl_small, "body"); lbl_small.setFixedWidth(72)
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("输入数字金额，如 1688.99")
        self.amount_input.setFixedHeight(40); self.amount_input.setStyleSheet("font-size:16px;")
        btn_convert = QPushButton("转换")
        btn_convert.setProperty("role", "primary")
        btn_convert.style().unpolish(btn_convert); btn_convert.style().polish(btn_convert)
        btn_convert.setFixedHeight(40)
        btn_convert.clicked.connect(self._convert_amount)
        self.amount_input.returnPressed.connect(self._convert_amount)
        row_in.addWidget(lbl_small); row_in.addWidget(self.amount_input); row_in.addWidget(btn_convert)
        case_box.addLayout(row_in)

        row_out = QHBoxLayout()
        lbl_big = QLabel("大写金额："); _typo(lbl_big, "body"); lbl_big.setFixedWidth(72)
        self.amount_output = QLineEdit()
        self.amount_output.setReadOnly(True); self.amount_output.setFixedHeight(40)
        self.amount_output.setStyleSheet("font-size:16px;")
        btn_copy_amt = QPushButton("复制")
        btn_copy_amt.setProperty("role", "nav")
        btn_copy_amt.style().unpolish(btn_copy_amt); btn_copy_amt.style().polish(btn_copy_amt)
        btn_copy_amt.setFixedHeight(40)
        btn_copy_amt.clicked.connect(self._copy_amount)
        row_out.addWidget(lbl_big); row_out.addWidget(self.amount_output); row_out.addWidget(btn_copy_amt)
        case_box.addLayout(row_out)

        # ── 大写汉字速查（功能区标准卡） ────────────────────
        gb_chars = make_card("CardRatioChars")
        chars_box = QVBoxLayout(gb_chars)
        chars_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        self._theme_titles.append(install_card_title(gb_chars, chars_box, "人民币大写汉字速查"))
        left.addWidget(gb_chars)

        hint = QLabel("点击单字即可复制到剪贴板"); _typo(hint, "muted")
        chars_box.addWidget(hint)

        CHARS_ROW1 = ["零","壹","贰","叁","肆","伍","陆","柒","捌","玖"]
        CHARS_ROW2 = ["拾","佰","仟","万","亿","元","角","分","整","负"]
        self._char_status = QLabel("")
        _typo(self._char_status, "muted")

        for row_chars in (CHARS_ROW1, CHARS_ROW2):
            row_layout = FlowLayout(h_spacing=6, v_spacing=6)
            chars_box.addLayout(row_layout)
            for ch in row_chars:
                btn = QPushButton(ch)
                btn.setFixedSize(46, 42)
                btn.setObjectName("CharChip")
                btn.setToolTip(f"复制「{ch}」")
                btn.setStyleSheet("font-size:17px; font-weight:500;")
                btn.clicked.connect(lambda _, c=ch: self._copy_char(c))
                row_layout.addWidget(btn)
        chars_box.addWidget(self._char_status)

        # ═══════════════ 右列 ═══════════════
        right = QVBoxLayout()
        right.setSpacing(10)
        right.setAlignment(Qt.AlignTop)
        root.addLayout(right, 1)

        # ── 简易计算器（功能区标准卡） ──────────────────────
        gb_calc = make_card("CardRatioSimple")
        calc_box = QVBoxLayout(gb_calc)
        calc_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        self._theme_titles.append(install_card_title(gb_calc, calc_box, "简易计算器"))
        right.addWidget(gb_calc)

        self.calc_expr = QLineEdit()
        self.calc_expr.setPlaceholderText("输入表达式，例如：(1920/1080)*1.5")
        self.calc_expr.setFixedHeight(40); self.calc_expr.setAlignment(Qt.AlignLeft)
        self.calc_expr.setStyleSheet("font-size:16px;")
        calc_box.addWidget(self.calc_expr)

        btn_calc_row = QHBoxLayout()
        calc_box.addLayout(btn_calc_row)
        btn_eval = QPushButton("计算"); btn_eval.setProperty("role", "primary")
        btn_eval.style().unpolish(btn_eval); btn_eval.style().polish(btn_eval)
        btn_eval.clicked.connect(self._calc_eval); btn_calc_row.addWidget(btn_eval)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(lambda: (self.calc_expr.clear(), self.calc_result.clear()))
        btn_calc_row.addWidget(btn_clear); btn_calc_row.addStretch(1)

        self.calc_result = QLineEdit(); self.calc_result.setReadOnly(True)
        self.calc_result.setPlaceholderText("结果")
        self.calc_result.setFixedHeight(40); self.calc_result.setAlignment(Qt.AlignLeft)
        self.calc_result.setStyleSheet("font-size:16px;")
        calc_box.addWidget(self.calc_result)
        self.calc_expr.returnPressed.connect(self._calc_eval)

        # 右列底部留白（汇率转换器已迁移至「时区汇率」页）
        right.addStretch(1)

        # 卡片标题是内联样式（install_card_title 按当前主题烤进颜色），
        # 不吃全局 QSS 级联，主题切换需要手动重刷一遍（见标准文档 4.4）
        theme.changed.connect(self._apply_theme)

    def _apply_theme(self, *_args):
        for lbl in self._theme_titles:
            restyle_card_title(lbl)

    # ──────── 比例计算 ────────
    def _ratio_calc(self):
        try:
            a = float(self.a.text()); b = float(self.b.text()); c = float(self.c.text())
            if a == 0: raise ZeroDivisionError
            d = b * c / a
            self.d.setText(f"{d:.2f}")
            self.status.setText("🟢 计算完成")
        except Exception:
            self.d.clear()
            self.status.setText("⚪ 等待输入…")

    def _swap(self):
        a_txt, b_txt = self.a.text(), self.b.text()
        self.a.blockSignals(True); self.b.blockSignals(True)
        self.a.setText(b_txt); self.b.setText(a_txt)
        self.a.blockSignals(False); self.b.blockSignals(False)
        self._ratio_calc(); self.a.setFocus()

    def _copy_d(self):
        val = self.d.text().split(".")[0]
        from PyQt5.QtCore import QMimeData
        from PyQt5.QtWidgets import QApplication
        m = QMimeData(); m.setText(val); QApplication.clipboard().setMimeData(m)
        self.status.setText("🟢 已复制D整数部分到剪贴板")

    def _copy_c(self):
        val = self.c.text().strip()
        if not val:
            self.status.setText("⚪ C 值为空，无法复制")
            return
        from PyQt5.QtCore import QMimeData
        from PyQt5.QtWidgets import QApplication
        m = QMimeData(); m.setText(val); QApplication.clipboard().setMimeData(m)
        self.status.setText("🟢 已复制C值到剪贴板")

    def _apply_ratio(self, ra: int, rb: int, name: str, c: int = 0):
        self.a.blockSignals(True); self.b.blockSignals(True)
        self.a.setText(str(ra)); self.b.setText(str(rb))
        self.a.blockSignals(False); self.b.blockSignals(False)
        if c:
            self.c.blockSignals(True)
            self.c.setText(str(c))
            self.c.blockSignals(False)
        self._ratio_calc()
        if c:
            short = round(c * rb / ra) if ra >= rb else round(c * ra / rb)
            w_px  = c     if ra >= rb else short
            h_px  = short if ra >= rb else c
            self.status.setText(f"🟢 {name}  →  {w_px}×{h_px} px（已自动计算）")
        else:
            self.status.setText(f"🟡 已选择比例 {name}，请在 C 输入具体数值")

    # ──────── 简易计算器 ────────
    def _calc_eval(self):
        expr = (self.calc_expr.text() or "").strip()
        try:
            res = self._safe_eval(expr)
            self.calc_result.setText(str(res))
            self.status.setText("🟢 计算器完成")
        except Exception:
            self.calc_result.setText("表达式错误")
            self.status.setText("❌ 表达式错误")

    def _safe_eval(self, expr: str):
        if not expr: return ""
        node = ast.parse(expr, mode="eval")
        def _eval(n):
            if isinstance(n, ast.Expression): return _eval(n.body)
            if isinstance(n, ast.Num): return n.n
            if hasattr(ast, "Constant") and isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
            if isinstance(n, ast.BinOp):
                l, r = _eval(n.left), _eval(n.right)
                if isinstance(n.op, ast.Add): return l + r
                if isinstance(n.op, ast.Sub): return l - r
                if isinstance(n.op, ast.Mult): return l * r
                if isinstance(n.op, ast.Div): return l / r
                if isinstance(n.op, ast.FloorDiv): return l // r
                if isinstance(n.op, ast.Mod): return l % r
                if isinstance(n.op, ast.Pow): return l ** r
                raise ValueError("不支持的运算符")
            if isinstance(n, ast.UnaryOp):
                v = _eval(n.operand)
                if isinstance(n.op, ast.UAdd): return +v
                if isinstance(n.op, ast.USub): return -v
                raise ValueError("不支持的前缀运算")
            raise ValueError("不支持的表达式")
        return _eval(node)

    # ──────── 金额大小写转换 ────────
    def _convert_amount(self):
        txt = self.amount_input.text().strip()
        try:
            result = self._num_to_rmb(txt)
            self.amount_output.setText(result)
            self.status.setText("🟢 转换完成")
        except Exception:
            self.amount_output.setText("输入有误")
            self.status.setText("❌ 请输入有效数字金额")

    def _num_to_rmb(self, num_str: str) -> str:
        """数字字符串 → 人民币大写（支持小数最多两位、负数）"""
        DIGITS   = "零壹贰叁肆伍陆柒捌玖"
        UNITS    = ["", "拾", "佰", "仟"]
        SECTIONS = ["", "万", "亿"]

        negative = num_str.startswith("-")
        num_str  = num_str.lstrip("-")

        if "." in num_str:
            int_str, dec_str = num_str.split(".", 1)
            dec_str = (dec_str + "00")[:2]
        else:
            int_str, dec_str = num_str, "00"

        int_val = int(int_str) if int_str else 0
        jiao    = int(dec_str[0])
        fen     = int(dec_str[1])

        def _group4(n: int) -> str:
            if n == 0: return ""
            digits = []
            for _ in range(4):
                digits.append(n % 10); n //= 10
            digits.reverse()
            res = ""; need_zero = False
            for i, d in enumerate(digits):
                if d == 0:
                    need_zero = True
                else:
                    if need_zero: res += "零"
                    res += DIGITS[d] + UNITS[3 - i]
                    need_zero = False
            return res

        if int_val == 0:
            int_chinese = "零"
        else:
            groups = []
            tmp = int_val
            while tmp > 0:
                groups.append(tmp % 10000); tmp //= 10000
            groups.reverse()
            parts = []
            prev_zero = False
            for i, g in enumerate(groups):
                if g == 0:
                    prev_zero = True
                else:
                    gc = _group4(g)
                    if prev_zero and parts: gc = "零" + gc
                    parts.append(gc + SECTIONS[len(groups) - 1 - i])
                    prev_zero = False
            int_chinese = "".join(parts)

        result = ("负" if negative else "") + int_chinese + "元"
        if jiao == 0 and fen == 0:
            result += "整"
        else:
            if jiao > 0: result += DIGITS[jiao] + "角"
            if fen  > 0: result += DIGITS[fen]  + "分"
        return result

    def _copy_amount(self):
        val = self.amount_output.text()
        if val and val != "输入有误":
            from PyQt5.QtCore import QMimeData
            from PyQt5.QtWidgets import QApplication
            m = QMimeData(); m.setText(val); QApplication.clipboard().setMimeData(m)
            self.status.setText("🟢 已复制大写金额到剪贴板")

    # ──────── 大写汉字速查 ────────
    def _copy_char(self, char: str):
        from PyQt5.QtCore import QMimeData
        from PyQt5.QtWidgets import QApplication
        m = QMimeData(); m.setText(char); QApplication.clipboard().setMimeData(m)
        self._char_status.setText(f"✅ 已复制「{char}」")
