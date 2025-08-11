from styles.common_styles import TEXT_STYLE, BUTTON_STYLE

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QTimer

class PageRatioCalc(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        f = QFont("微软雅黑", 18)
        self.a, self.b, self.c, self.d = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        for w,p in [(self.a,'A'),(self.b,'B'),(self.c,'C'),(self.d,'D')]:
            w.setPlaceholderText(p)
            w.setFont(f)
            w.setFixedHeight(40)
            w.setAlignment(Qt.AlignCenter)
        self.d.setReadOnly(True)
        self.d.setEnabled(False)
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(self._calc)
        for w in (self.a,self.b,self.c): w.textChanged.connect(lambda: t.start(600))
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("A"))
        r1.addWidget(self.a)
        r1.addStretch()
        r1.addWidget(QLabel("C"))
        r1.addWidget(self.c)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("B"))
        r2.addWidget(self.b)
        r2.addStretch()
        r2.addWidget(QLabel("D"))
        r2.addWidget(self.d)
        
        r3 = QHBoxLayout()

        self.swap_label = QLabel("A与B数值互换")
        self.swap_label.setStyleSheet(TEXT_STYLE)
        r3.addWidget(self.swap_label)

        swap = QPushButton("交换")
        swap.setStyleSheet(BUTTON_STYLE)
        swap.clicked.connect(self._swap)  # 绑定事件
        r3.addWidget(swap)

        r3.addStretch()

        self.precision_label = QLabel("D精值")
        self.precision_label.setStyleSheet(TEXT_STYLE)
        r3.addWidget(self.precision_label)

        copyd = QPushButton("复制")
        copyd.setStyleSheet(BUTTON_STYLE)
        copyd.clicked.connect(self._copy)  # 绑定事件
        r3.addWidget(copyd)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        lay.addLayout(r1)
        lay.addLayout(r2)
        lay.addLayout(r3)
        lay.addWidget(line)
    def _calc(self):
        try:
            a=float(self.a.text())
            b=float(self.b.text())
            c=float(self.c.text())
            d=b*c/a; self.d.setText(f"{d:.2f}")
        except: self.d.clear()
        
    def _swap(self):
        self.a.setText(self.b.text())
        self.b.setText("")
        self.a.setFocus()
    def _copy(self):
        val = self.d.text().split(".")[0]
        from PyQt5.QtCore import QMimeData
        from PyQt5.QtWidgets import QApplication
        m = QMimeData(); m.setText(val); QApplication.clipboard().setMimeData(m)