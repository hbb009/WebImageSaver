# pages/page_ratio_calc.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QButtonGroup, QGroupBox  # ← 新增：分组容器
)
from PyQt5.QtCore import Qt, QTimer
import ast

class PageRatioCalc(QWidget):
    def __init__(self):
        super().__init__()

        # ---------- 小工具：统一字阶 ----------
        def _typo(w: QLabel, name: str):
            w.setProperty("typo", name)
            w.style().unpolish(w); w.style().polish(w)

        # 顶层：左（比例计算） + 右（简易计算器）
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 0, 12, 12)
        root.setSpacing(12)

        # ================= 左侧：比例计算 =================
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignTop)  # ← 左列内的所有控件顶对齐（关键）
        left.setSpacing(10)
        root.addLayout(left, 2)

        # 状态条
        self.status = QLabel("🟢 就绪")
        _typo(self.status, "body")
        left.addWidget(self.status, 0, Qt.AlignLeft)

        # === 左侧：比例计算器 分组（套用通用标题模板；无卡片背景/直角边） ===
        gb_left = QGroupBox("比例计算器")
        gb_left.setProperty("titleVariant", "accent")   # 使用通用标题模板（浅蓝标题 + 18px）
        left_box = QVBoxLayout(gb_left)                 # 分组内部专用布局
        left.addWidget(gb_left)                         # 把分组挂到左列

        # ---- 输入框 A/B/C/D ----
        self.a, self.b, self.c, self.d = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        for w, p, obj in [
            (self.a, 'A', 'RatioA'),
            (self.b, 'B', 'RatioB'),
            (self.c, 'C', 'RatioC'),
            (self.d, 'D', 'RatioD'),
        ]:
            w.setPlaceholderText(p)
            w.setObjectName(obj)
            w.setFixedHeight(40)
            w.setAlignment(Qt.AlignCenter)
            # 仅作用于本页输入框字号（与 body=16px 对齐，不影响其他页）
            w.setStyleSheet("font-size:16px;")

        self.d.setReadOnly(True)
        self.d.setEnabled(False)

        # 防抖计算：A/B/C 改变 600ms 后计算 D = B*C/A
        self._debounce = QTimer(self); self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._calc)
        for w in (self.a, self.b, self.c):
            w.textChanged.connect(lambda _=None: self._debounce.start(600))  # 中文注释：接收信号的文本参数，避免 TypeError

        # 行1：A、C
        r1 = QHBoxLayout()
        labA = QLabel("A"); _typo(labA, "body")
        labC = QLabel("C"); _typo(labC, "body")
        r1.addWidget(labA); r1.addWidget(self.a)
        r1.addStretch(1)
        r1.addWidget(labC); r1.addWidget(self.c)
        left_box.addLayout(r1)   # A / C 行

        # 行2：B、D
        r2 = QHBoxLayout()
        labB = QLabel("B"); _typo(labB, "body")
        labD = QLabel("D"); _typo(labD, "body")
        r2.addWidget(labB); r2.addWidget(self.b)
        r2.addStretch(1)
        r2.addWidget(labD); r2.addWidget(self.d)
        left_box.addLayout(r2)   # B / D 行

        # 行3：交换 / D精值 / 复制
        r3 = QHBoxLayout()
        self.swap_label = QLabel("A与B数值互换"); _typo(self.swap_label, "muted")
        r3.addWidget(self.swap_label)
        btn_swap = QPushButton("交换")
        btn_swap.setProperty("role","nav"); btn_swap.style().unpolish(btn_swap); btn_swap.style().polish(btn_swap)
        btn_swap.clicked.connect(self._swap)
        r3.addWidget(btn_swap)
        r3.addStretch(1)
        self.precision_label = QLabel("D精值"); _typo(self.precision_label, "muted")
        r3.addWidget(self.precision_label)
        btn_copy = QPushButton("复制")
        btn_copy.setProperty("role","nav"); btn_copy.style().unpolish(btn_copy); btn_copy.style().polish(btn_copy)
        btn_copy.clicked.connect(self._copy)
        r3.addWidget(btn_copy)
        left_box.addLayout(r3)   # 交换 / 复制 行

        # 分割线
        line = QFrame(); line.setFrameShape(QFrame.HLine)
        left_box.addWidget(line) # 分割线

        # ---- 常用文生图比例（分割线下）----
        chips = QHBoxLayout(); chips.setSpacing(8)
        left_box.addLayout(chips) # 常用比例按钮行

        # 格式：(显示名, A比, B比, 长边像素值)  ← 长边自动填入 C
        presets = [
            ("1:1",   1,  1, 1536),
            ("16:9", 16,  9, 1536),
            ("4:3",   4,  3, 1536),
            ("3:2",   3,  2, 1536),
            ("3:4",   3,  4, 1536),
            ("2:3",   2,  3, 1536),
            ("9:16",  9, 16, 1536),
            ("21:9", 21,  9, 2048),
        ]
        self._chip_group = QButtonGroup(self); self._chip_group.setExclusive(True)
        for name, ra, rb, long_side in presets:
            # 计算短边用于 tooltip
            short = round(long_side * rb / ra) if ra >= rb else round(long_side * ra / rb)
            w_px  = long_side if ra >= rb else short
            h_px  = short     if ra >= rb else long_side
            b = QPushButton(name)
            b.setCheckable(True)
            b.setObjectName("RatioChip")
            b.setProperty("role","nav")
            b.setToolTip(f"{w_px} × {h_px} px（点击自动填入 C={long_side}）")
            b.style().unpolish(b); b.style().polish(b)
            b.clicked.connect(lambda _, a=ra, bb=rb, label=name, c=long_side:
                              self._apply_ratio(a, bb, label, c))
            self._chip_group.addButton(b)
            chips.addWidget(b)
        chips.addStretch(1)

        # ================= 右侧：简易计算器 =================
        right = QVBoxLayout()
        right.setSpacing(10)
        root.addLayout(right, 1)
        right.setAlignment(Qt.AlignTop)   # ← 让右侧内容从顶部开始

        # === 右侧：简易计算器 分组（同样套用标题模板） ===
        gb_calc = QGroupBox("简易计算器")
        gb_calc.setProperty("titleVariant", "accent")   # 浅蓝标题 + 18px
        right_box = QVBoxLayout(gb_calc)                # 分组内部专用布局
        right.addWidget(gb_calc)                        # 把分组挂到右列

        self.calc_expr = QLineEdit()
        self.calc_expr.setPlaceholderText("输入表达式，例如： (1920/1080)*1.5")
        self.calc_expr.setFixedHeight(40)
        self.calc_expr.setAlignment(Qt.AlignLeft)
        self.calc_expr.setStyleSheet("font-size:16px;")
        right_box.addWidget(self.calc_expr)     # 表达式输入

        btn_row = QHBoxLayout()
        right_box.addLayout(btn_row)            # 计算/清空按钮行
        btn_eval = QPushButton("计算")
        btn_eval.setProperty("role","primary")
        btn_eval.style().unpolish(btn_eval)
        btn_eval.style().polish(btn_eval)
        btn_eval.clicked.connect(self._calc_eval)
        btn_row.addWidget(btn_eval)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(lambda: (self.calc_expr.clear(), self.calc_result.clear()))
        btn_row.addWidget(btn_clear)
        btn_row.addStretch(1)

        self.calc_result = QLineEdit()
        self.calc_result.setReadOnly(True)
        self.calc_result.setPlaceholderText("结果")
        self.calc_result.setFixedHeight(40)
        self.calc_result.setAlignment(Qt.AlignLeft)
        self.calc_result.setStyleSheet("font-size:16px;")
        right_box.addWidget(self.calc_result)   # 结果框

        # Enter 直接计算
        self.calc_expr.returnPressed.connect(self._calc_eval)

    # ------------ 业务：比例计算 ------------
    def _calc(self):
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
        self._calc()
        self.a.setFocus()

    def _copy(self):
        val = self.d.text().split(".")[0]
        from PyQt5.QtCore import QMimeData
        from PyQt5.QtWidgets import QApplication
        m = QMimeData(); m.setText(val); QApplication.clipboard().setMimeData(m)
        self.status.setText("🟢 已复制整数部分到剪贴板")

    def _apply_ratio(self, ra: int, rb: int, name: str, c: int = 0):
        """点击常用比例按钮：写入 A、B，并自动填 C（长边像素）后计算 D"""
        self.a.blockSignals(True); self.b.blockSignals(True)
        self.a.setText(str(ra)); self.b.setText(str(rb))
        self.a.blockSignals(False); self.b.blockSignals(False)
        if c:
            self.c.blockSignals(True)
            self.c.setText(str(c))
            self.c.blockSignals(False)
        self._calc()
        if c:
            short = round(c * rb / ra) if ra >= rb else round(c * ra / rb)
            w_px  = c     if ra >= rb else short
            h_px  = short if ra >= rb else c
            self.status.setText(f"🟢 {name}  →  {w_px} × {h_px} px（已自动计算）")
        else:
            self.status.setText(f"🟡 已选择比例 {name}，请在 C 输入具体数值")

    # ------------ 业务：简易计算器（安全执行） ------------
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
        """仅支持 + - * / // % ** 和括号的安全计算"""
        if not expr:
            return ""
        node = ast.parse(expr, mode="eval")

        def _eval(n):
            if isinstance(n, ast.Expression):
                return _eval(n.body)
            if isinstance(n, ast.Num):
                return n.n
            if hasattr(ast, "Constant") and isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return n.value
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
