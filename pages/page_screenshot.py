from styles.common_styles import TEXT_STYLE, BUTTON_STYLE, LINEEDIT_STYLE

import os
import sys
import math
import subprocess
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QCheckBox, QFileDialog, QGroupBox, QComboBox,
    QButtonGroup, QRadioButton, QMenu, QApplication, QLineEdit as _QLineEdit
)
from PyQt5.QtCore import Qt, QRect, QPoint, QSize, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import (
    QPixmap, QPainter, QPen, QBrush, QColor, QIcon, QFont, QPolygon
)
import keyboard
from utils.file_utils import ensure_dir


# ============================================================
# 通用工具
# ============================================================
def open_in_file_manager(path, select=True):
    """在系统文件管理器中打开（select=True 时选中该文件）。跨平台兜底。"""
    try:
        norm = os.path.normpath(path)
        if sys.platform.startswith("win"):
            if select and os.path.isfile(norm):
                subprocess.Popen(["explorer", "/select,", norm])
            else:
                os.startfile(norm if os.path.isdir(norm) else os.path.dirname(norm))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", norm] if select else ["open", norm])
        else:
            subprocess.Popen(["xdg-open", norm if os.path.isdir(norm) else os.path.dirname(norm)])
    except Exception:
        try:
            os.startfile(os.path.dirname(path))
        except Exception:
            pass


def open_file(path):
    """用系统默认程序打开文件。"""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class _Signal(QObject):
    trigger = pyqtSignal()


# ============================================================
# 预览标签：保留原图，随控件尺寸等比缩放显示
# ============================================================
class PreviewLabel(QLabel):
    _PLACEHOLDER = "（选中左侧记录可预览）"

    def __init__(self):
        super().__init__()
        self._src = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(220, 220)
        self.setStyleSheet("color:#6b7aa0;")
        self.setText(self._PLACEHOLDER)

    def set_image(self, pixmap):
        self._src = pixmap if (pixmap is not None and not pixmap.isNull()) else None
        self._rescale()

    def _rescale(self):
        if self._src is None:
            self.clear()
            self.setText(self._PLACEHOLDER)
            return
        self.setPixmap(self._src.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, e):
        self._rescale()
        super().resizeEvent(e)


# ============================================================
# 全屏框选遮罩（高分屏坐标已修正；直接从冻结画面裁剪，不含红框）
# ============================================================
class Overlay(QWidget):
    def __init__(self, on_capture, on_cancel):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.start = self.end = None
        self.on_capture = on_capture
        self.on_cancel = on_cancel

        screen = QApplication.primaryScreen()
        geo = screen.geometry()
        self.bg = screen.grabWindow(0)
        self.bg.setDevicePixelRatio(1.0)
        self.dpr = (self.bg.width() / geo.width()) if geo.width() else 1.0

        self.setGeometry(geo)
        self.showFullScreen()
        self.raise_(); self.activateWindow(); self.setFocus()

    def _phys(self, r):
        d = self.dpr
        return QRect(int(r.x() * d), int(r.y() * d),
                     int(r.width() * d), int(r.height() * d))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.start = e.pos(); self.end = self.start; self.update()

    def mouseMoveEvent(self, e):
        if self.start:
            self.end = e.pos(); self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.RightButton:
            self.on_cancel(); self.close(); return
        if e.button() == Qt.LeftButton and self.start and self.end:
            rect = QRect(self.start, self.end).normalized()
            self.close()
            if rect.width() < 10 or rect.height() < 10:
                self.on_cancel(); return
            crop = self.bg.copy(self._phys(rect))
            crop.setDevicePixelRatio(1.0)
            self.on_capture(crop)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.on_cancel(); self.close()

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.bg)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        if self.start and self.end:
            sel = QRect(self.start, self.end).normalized()
            p.drawPixmap(sel, self.bg, self._phys(sel))
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor("#3aa0ff"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(sel)
            w = int(sel.width() * self.dpr); h = int(sel.height() * self.dpr)
            txt = f"{w} × {h}"
            f = QFont(); f.setPixelSize(13); p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(txt) + 12
            ty = sel.top() - 24 if sel.top() > 24 else sel.top() + 6
            p.fillRect(sel.left(), ty, tw, 20, QColor(0, 0, 0, 180))
            p.setPen(QColor("#ffffff"))
            p.drawText(sel.left() + 6, ty + 15, txt)


# ============================================================
# 标注画布：矩形 / 箭头 / 画笔 / 文字 / 马赛克
# ============================================================
class _Canvas(QWidget):
    def __init__(self, pixmap):
        super().__init__()
        self.base = pixmap
        iw, ih = pixmap.width(), pixmap.height()
        avail = QApplication.primaryScreen().availableGeometry()
        max_w = int(avail.width() * 0.9)
        max_h = int(avail.height() * 0.82)
        self.scale = min(1.0, max_w / iw, max_h / ih)
        self.setFixedSize(max(1, int(iw * self.scale)), max(1, int(ih * self.scale)))
        self.setMouseTracking(True)

        self.tool = "rect"
        self.color = QColor("#ff3b30")
        self.width = 3
        self.shapes = []
        self.start_ip = None
        self.cur = None
        self.drawing = False
        self._mosaic_cache = None
        self._text_edit = None

    def _to_img(self, pos):
        return QPoint(int(pos.x() / self.scale), int(pos.y() / self.scale))

    def _mosaic_base(self):
        if self._mosaic_cache is None:
            block = 14
            img = self.base.toImage()
            w, h = img.width(), img.height()
            small = img.scaled(max(1, w // block), max(1, h // block),
                               Qt.IgnoreAspectRatio, Qt.FastTransformation)
            self._mosaic_cache = QPixmap.fromImage(
                small.scaled(w, h, Qt.IgnoreAspectRatio, Qt.FastTransformation))
        return self._mosaic_cache

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        ip = self._to_img(e.pos())
        if self.tool == "text":
            self._begin_text(e.pos(), ip)
            return
        self.start_ip = ip
        self.drawing = True
        if self.tool in ("rect", "mosaic"):
            self.cur = {"type": self.tool, "rect": QRect(ip, ip),
                        "color": QColor(self.color), "width": self.width}
        elif self.tool == "arrow":
            self.cur = {"type": "arrow", "p1": ip, "p2": ip,
                        "color": QColor(self.color), "width": self.width}
        elif self.tool == "pen":
            self.cur = {"type": "pen", "points": [ip],
                        "color": QColor(self.color), "width": self.width}
        self.update()

    def mouseMoveEvent(self, e):
        if not self.drawing or self.cur is None:
            return
        ip = self._to_img(e.pos())
        t = self.cur["type"]
        if t in ("rect", "mosaic"):
            self.cur["rect"] = QRect(self.start_ip, ip).normalized()
        elif t == "arrow":
            self.cur["p2"] = ip
        elif t == "pen":
            self.cur["points"].append(ip)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self.cur is None:
            return
        keep = True
        t = self.cur["type"]
        if t in ("rect", "mosaic"):
            r = self.cur["rect"]; keep = r.width() > 3 and r.height() > 3
        elif t == "arrow":
            keep = (self.cur["p1"] - self.cur["p2"]).manhattanLength() > 5
        elif t == "pen":
            keep = len(self.cur["points"]) > 1
        if keep:
            self.shapes.append(self.cur)
        self.cur = None
        self.drawing = False
        self.update()

    def _begin_text(self, wpos, ipos):
        if self._text_edit is not None:
            self._commit_text()
        size = max(16, self.width * 6)
        le = _QLineEdit(self)
        le.setStyleSheet(
            f"background:rgba(0,0,0,140); color:{self.color.name()};"
            f"border:1px dashed {self.color.name()}; padding:2px;")
        f = QFont(); f.setPixelSize(max(12, int(size * self.scale))); le.setFont(f)
        le.move(wpos); le.setMinimumWidth(120)
        le.show(); le.setFocus()
        le._img_pos = ipos; le._font_size = size; le._committed = False
        le.returnPressed.connect(self._commit_text)
        le.editingFinished.connect(self._commit_text)
        self._text_edit = le

    def _commit_text(self):
        le = self._text_edit
        if le is None or getattr(le, "_committed", False):
            return
        le._committed = True
        text = le.text().strip()
        if text:
            self.shapes.append({
                "type": "text",
                "pos": QPoint(le._img_pos.x(), le._img_pos.y() + le._font_size),
                "text": text, "color": QColor(self.color), "size": le._font_size})
        self._text_edit = None
        le.deleteLater()
        self.update()

    def undo(self):
        if self.shapes:
            self.shapes.pop(); self.update()

    def _draw_shape(self, p, s):
        t = s["type"]
        if t == "rect":
            p.setPen(QPen(s["color"], s["width"])); p.setBrush(Qt.NoBrush)
            p.drawRect(s["rect"])
        elif t == "arrow":
            self._draw_arrow(p, s["p1"], s["p2"], s["color"], s["width"])
        elif t == "pen":
            p.setPen(QPen(s["color"], s["width"], Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            pts = s["points"]
            for i in range(1, len(pts)):
                p.drawLine(pts[i - 1], pts[i])
        elif t == "text":
            f = QFont(); f.setPixelSize(s["size"]); p.setFont(f)
            p.setPen(s["color"]); p.drawText(s["pos"], s["text"])
        elif t == "mosaic":
            p.drawPixmap(s["rect"], self._mosaic_base(), s["rect"])

    def _draw_arrow(self, p, p1, p2, color, width):
        p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(p1, p2)
        ang = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
        head = max(12, width * 4)
        a1 = ang + math.radians(150); a2 = ang - math.radians(150)
        q1 = QPoint(int(p2.x() + head * math.cos(a1)), int(p2.y() + head * math.sin(a1)))
        q2 = QPoint(int(p2.x() + head * math.cos(a2)), int(p2.y() + head * math.sin(a2)))
        p.setBrush(QBrush(color))
        p.drawPolygon(QPolygon([p2, q1, q2]))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.save()
        p.scale(self.scale, self.scale)
        p.drawPixmap(0, 0, self.base)
        for s in self.shapes:
            self._draw_shape(p, s)
        if self.cur is not None:
            self._draw_shape(p, self.cur)
        p.restore()

    def render_result(self):
        self._commit_text()
        out = QPixmap(self.base)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        for s in self.shapes:
            self._draw_shape(p, s)
        p.end()
        return out


# ============================================================
# 标注编辑窗口
# ============================================================
class AnnotationEditor(QWidget):
    def __init__(self, pixmap, on_save, on_copy, on_cancel):
        super().__init__()
        self.on_save = on_save
        self.on_copy = on_copy
        self.on_cancel = on_cancel
        self._done = False
        self.setWindowTitle("截图编辑")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("QWidget{background:#0f1424;}")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10); root.setSpacing(8)

        bar = QHBoxLayout(); bar.setSpacing(6); root.addLayout(bar)
        self.canvas = _Canvas(pixmap)

        self._tool_group = QButtonGroup(self); self._tool_group.setExclusive(True)
        for key, label in [("rect", "矩形"), ("arrow", "箭头"),
                           ("pen", "画笔"), ("text", "文字"), ("mosaic", "马赛克")]:
            b = QPushButton(label); b.setStyleSheet(BUTTON_STYLE)
            b.setCheckable(True); b.setFixedWidth(64)
            b.clicked.connect(lambda _, k=key: self._set_tool(k))
            self._tool_group.addButton(b); bar.addWidget(b)
            if key == "rect":
                b.setChecked(True)

        bar.addSpacing(8); bar.addWidget(self._sep())
        for name in ["#ff3b30", "#ffcc00", "#34c759", "#0a84ff", "#ffffff", "#000000"]:
            cb = QPushButton(); cb.setFixedSize(22, 22)
            cb.setStyleSheet(f"background:{name}; border:1px solid #444; border-radius:11px;")
            cb.clicked.connect(lambda _, c=name: self._set_color(c))
            bar.addWidget(cb)

        bar.addSpacing(8)
        self.width_combo = QComboBox(); self.width_combo.addItems(["细", "中", "粗"])
        self.width_combo.setCurrentIndex(1); self.width_combo.setStyleSheet(LINEEDIT_STYLE)
        self.width_combo.setFixedWidth(56)
        self.width_combo.currentIndexChanged.connect(
            lambda i: setattr(self.canvas, "width", [2, 3, 6][i]))
        bar.addWidget(self.width_combo)
        bar.addStretch()

        for label, slot in [("撤销", self.canvas.undo), ("取消", self._cancel),
                            ("复制", self._copy), ("保存", self._save)]:
            b = QPushButton(label); b.setStyleSheet(BUTTON_STYLE)
            b.setFixedWidth(64); b.clicked.connect(slot); bar.addWidget(b)

        root.addWidget(self.canvas, alignment=Qt.AlignCenter)
        self.adjustSize(); self._center()

    def _sep(self):
        s = QLabel("｜"); s.setStyleSheet("color:#33405f;"); return s

    def _center(self):
        g = QApplication.primaryScreen().availableGeometry()
        self.move(g.center().x() - self.width() // 2,
                  g.center().y() - self.height() // 2)

    def _set_tool(self, k): self.canvas.tool = k
    def _set_color(self, c): self.canvas.color = QColor(c)

    def _save(self):
        self._done = True; self.on_save(self.canvas.render_result()); self.close()

    def _copy(self):
        self._done = True; self.on_copy(self.canvas.render_result()); self.close()

    def _cancel(self):
        self._done = True; self.on_cancel(); self.close()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel()
        elif e.key() == Qt.Key_Z and (e.modifiers() & Qt.ControlModifier):
            self.canvas.undo()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter) and (e.modifiers() & Qt.ControlModifier):
            self._save()

    def closeEvent(self, e):
        if not self._done:
            self.on_cancel(); self._done = True
        super().closeEvent(e)


# ============================================================
# 截图页
# ============================================================
class PageScreenshot(QWidget):
    def __init__(self):
        super().__init__()
        self._main_win = None
        self._win_hidden = False

        lay = QVBoxLayout(self)

        # ================= 第 1 排：启用截图（带框，最左） + 保存路径 =================
        row1 = QHBoxLayout(); lay.addLayout(row1)

        gb_enable = QGroupBox("截图启用")
        gb_enable.setProperty("titleVariant", "accent")
        gb_enable.setFixedWidth(140)
        vb_en = QVBoxLayout(gb_enable)
        self.checkbox_enable = QCheckBox("启用截图")
        self.checkbox_enable.setStyleSheet(TEXT_STYLE)
        self.checkbox_enable.stateChanged.connect(self._toggle)
        vb_en.addWidget(self.checkbox_enable)
        row1.addWidget(gb_enable)

        path_col = QVBoxLayout(); row1.addLayout(path_col, 1)
        self.label_path = QLabel("截图保存路径：")
        self.label_path.setStyleSheet(TEXT_STYLE)
        path_col.addWidget(self.label_path)
        path_row = QHBoxLayout(); path_col.addLayout(path_row)
        self.path = QLineEdit(os.path.join(os.path.expanduser("~"), "Pictures", "ScreenshotImageSaver"))
        self.path.setStyleSheet(LINEEDIT_STYLE)
        self.btn_select_dir = QPushButton("另选保存")
        self.btn_select_dir.setStyleSheet(BUTTON_STYLE)
        self.btn_select_dir.clicked.connect(self._choose_dir)
        path_row.addWidget(self.path)
        path_row.addWidget(self.btn_select_dir)

        # ================= 第 2 排：组合键 + 输出设置 =================
        row2 = QHBoxLayout(); lay.addLayout(row2)

        gb_mod = QGroupBox("组合键")
        gb_mod.setProperty("titleVariant", "accent")
        vb_mod = QVBoxLayout(gb_mod)

        # —— 修饰键：Ctrl / Alt / Shift 三选一 ——
        lb_mod = QLabel("修饰键："); lb_mod.setStyleSheet(TEXT_STYLE)
        vb_mod.addWidget(lb_mod)
        self.mod_group = QButtonGroup(self)          # 独占单选
        mod_row = QHBoxLayout()
        for m in ["Ctrl", "Alt", "Shift"]:
            rb = QRadioButton(m); rb.setStyleSheet(TEXT_STYLE)
            self.mod_group.addButton(rb); mod_row.addWidget(rb)
        mod_row.addStretch()
        vb_mod.addLayout(mod_row)

        # —— 主键：左手键位 Q W E R / A S D F / Z X C V 十二选一 ——
        lb_key = QLabel("主键（左手键位）："); lb_key.setStyleSheet(TEXT_STYLE)
        vb_mod.addWidget(lb_key)
        self.key_group = QButtonGroup(self)          # 独占单选
        for line in [["Q", "W", "E", "R"], ["A", "S", "D", "F"], ["Z", "X", "C", "V"]]:
            krow = QHBoxLayout()
            for k in line:
                rb = QRadioButton(k); rb.setStyleSheet(TEXT_STYLE)
                rb.setFixedWidth(52)
                self.key_group.addButton(rb); krow.addWidget(rb)
            krow.addStretch()
            vb_mod.addLayout(krow)
        vb_mod.addStretch()
        row2.addWidget(gb_mod, 1)

        gb_out = QGroupBox("输出设置")
        gb_out.setProperty("titleVariant", "accent")
        vb_out = QVBoxLayout(gb_out)
        fmt_row = QHBoxLayout()
        lb_fmt = QLabel("格式："); lb_fmt.setStyleSheet(TEXT_STYLE)
        self.fmt_group = QButtonGroup(self)               # 格式单选
        self.rb_png = QRadioButton("PNG"); self.rb_png.setStyleSheet(TEXT_STYLE)
        self.rb_jpg = QRadioButton("JPG"); self.rb_jpg.setStyleSheet(TEXT_STYLE)
        self.fmt_group.addButton(self.rb_png); self.fmt_group.addButton(self.rb_jpg)
        self.rb_png.setChecked(True)
        fmt_row.addWidget(lb_fmt); fmt_row.addWidget(self.rb_png)
        fmt_row.addWidget(self.rb_jpg); fmt_row.addStretch()
        vb_out.addLayout(fmt_row)
        self.chk_edit = QCheckBox("截图后编辑标注")
        self.chk_copy = QCheckBox("自动复制到剪贴板")
        self.chk_hide = QCheckBox("隐藏当前窗口")
        for c in (self.chk_edit, self.chk_copy, self.chk_hide):
            c.setStyleSheet(TEXT_STYLE); vb_out.addWidget(c)
        self.chk_edit.setChecked(False)                   # ★ 默认不勾
        self.chk_copy.setChecked(True)
        row2.addWidget(gb_out, 1)

        # ================= 第 3 排（贴底）：操作记录 + 截图预览 =================
        row3 = QHBoxLayout(); lay.addLayout(row3, 1)   # 拉伸系数 1，撑到底部

        gb_log = QGroupBox("截图与操作记录")
        gb_log.setProperty("titleVariant", "accent")
        vb_log = QVBoxLayout(gb_log)
        self.list = QListWidget()
        self.list.setObjectName("ShotList")
        self.list.setAttribute(Qt.WA_StyledBackground, True)
        self.list.setStyleSheet(
            "QListWidget{color:#9fb0d7; font-size:15px;}"
            "QListWidget::item{padding:6px 2px;}")
        self.list.setSpacing(3)                     # 行距（参考图3）
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_menu)
        self.list.itemDoubleClicked.connect(self._on_dblclick)
        self.list.currentItemChanged.connect(self._on_current_changed)   # ★ 选中→右侧预览
        vb_log.addWidget(self.list)
        row3.addWidget(gb_log, 3)

        gb_prev = QGroupBox("截图预览")
        gb_prev.setProperty("titleVariant", "accent")
        vb_prev = QVBoxLayout(gb_prev)
        self.preview = PreviewLabel()
        vb_prev.addWidget(self.preview)
        row3.addWidget(gb_prev, 2)

        # 初始日志
        ensure_dir(self.path.text())
        self._log(f"📁 初始路径：{self.path.text()}")
        self._log("⏹️ 当前截图监听未启用（空闲）")

        # 信号与监听
        self._sig = _Signal()
        self._sig.trigger.connect(self._show_overlay)

        # 默认热键：Alt + A（单修饰键，避开 Ctrl+字母 的常见冲突）
        self._check_radio(self.mod_group, "Alt")
        self._check_radio(self.key_group, "A")
        self.hotkey = self._current_hotkey()
        self._hotkey_handler = None
        self.mod_group.buttonClicked.connect(self._on_hotkey_changed)
        self.key_group.buttonClicked.connect(self._on_hotkey_changed)

    # === 日志 ===
    def _log(self, text):
        self.list.addItem(text)
        self.list.scrollToBottom()

    # === 目录/热键 ===
    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择截图保存文件夹")
        if d:
            self.path.setText(d); ensure_dir(d)
            self._log(f"📁 保存路径切换为：{d}")

    def _toggle(self, st):
        if st == Qt.Checked:
            self._log(f"🟢 截图监听已启用（等待：{self.hotkey.upper()}）")
            self._bind_hotkey()
        else:
            self._log("⏹️ 已停止截图监听（空闲）")
            self._unbind_hotkey()

    @staticmethod
    def _check_radio(group, text):
        for b in group.buttons():
            if b.text() == text:
                b.setChecked(True); return

    def _current_hotkey(self):
        mb = self.mod_group.checkedButton()
        kb = self.key_group.checkedButton()
        mod = mb.text().lower() if mb else "alt"
        key = kb.text().lower() if kb else "a"
        return f"{mod}+{key}"

    def _bind_hotkey(self):
        self._unbind_hotkey()
        try:
            self._hotkey_handler = keyboard.add_hotkey(self.hotkey, lambda: self._sig.trigger.emit())
        except Exception as e:
            self._log(f"❌ 热键注册失败：{e}")

    def _unbind_hotkey(self):
        try:
            if self._hotkey_handler is not None:
                keyboard.remove_hotkey(self._hotkey_handler)
                self._hotkey_handler = None
        except Exception:
            pass

    def _on_hotkey_changed(self, *_):
        self.hotkey = self._current_hotkey()
        if self.checkbox_enable.isChecked():
            self._bind_hotkey()
            self._log(f"⌨️ 快捷键切换为：{self.hotkey.upper()}")

    # === 主窗口隐藏/恢复 ===
    def _hide_main(self):
        self._main_win = self.window()
        if self._main_win is not None:
            self._main_win.hide()
            self._win_hidden = True

    def _restore_main(self):
        if self._win_hidden and self._main_win is not None:
            self._main_win.show()
            self._main_win.raise_()
            self._main_win.activateWindow()
        self._win_hidden = False

    # === 截图流程 ===
    def _show_overlay(self):
        self._log("🔥 热键已触发")
        if self.chk_hide.isChecked():
            self._hide_main()
            QTimer.singleShot(180, self._start_overlay)   # 等窗口真正消失再抓屏
        else:
            self._start_overlay()

    def _start_overlay(self):
        self.overlay = Overlay(self._on_captured, self._on_overlay_cancel)

    def _on_overlay_cancel(self):
        self._restore_main()
        self._log("❌ 截图已取消")

    def _on_captured(self, pixmap):
        self._restore_main()      # 拿到图立即恢复主窗口，编辑阶段不必再藏
        if self.chk_edit.isChecked():
            self.editor = AnnotationEditor(
                pixmap,
                on_save=lambda pix: self._finalize(pix, do_copy=self.chk_copy.isChecked(), do_save=True),
                on_copy=lambda pix: self._finalize(pix, do_copy=True, do_save=False),
                on_cancel=lambda: self._log("❌ 已取消（未保存）"))
            self.editor.show()
            self.editor.raise_(); self.editor.activateWindow()
        else:
            self._finalize(pixmap, do_copy=self.chk_copy.isChecked(), do_save=True)

    def _build_filepath(self):
        ext = "jpg" if self.rb_jpg.isChecked() else "png"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"screenshot_{stamp}"
        folder = self.path.text()
        candidate = os.path.join(folder, f"{base}.{ext}")
        i = 1
        while os.path.exists(candidate):
            candidate = os.path.join(folder, f"{base}_{i:03d}.{ext}")
            i += 1
        return candidate, ext

    def _finalize(self, pixmap, do_copy, do_save):
        if do_copy:
            QApplication.clipboard().setPixmap(pixmap)
            self._log("📋 已复制到剪贴板")
        if not do_save:
            return
        ensure_dir(self.path.text())
        full, ext = self._build_filepath()
        fmt = "JPG" if ext == "jpg" else "PNG"
        quality = 92 if fmt == "JPG" else -1
        try:
            ok = pixmap.save(full, fmt, quality)
            if ok:
                self._add_shot_item(full)
                self._log(f"📸 已保存：{full}")
            else:
                self._log(f"❌ 保存失败：写入被拒绝（{full}）")
        except Exception as e:
            self._log(f"❌ 保存失败：{type(e).__name__}: {e}")

    # === 记录条目（纯文本，路径存 UserRole；预览交给右侧面板）===
    def _add_shot_item(self, path):
        item = QListWidgetItem(f"📸 {os.path.basename(path)}")
        item.setData(Qt.UserRole, path)
        item.setToolTip(path)
        self.list.addItem(item)
        self.list.setCurrentItem(item)     # 选中即在右侧预览
        self.list.scrollToBottom()

    def _on_current_changed(self, cur, _prev):
        if cur is None:
            self.preview.set_image(None); return
        path = cur.data(Qt.UserRole)
        if path and os.path.exists(path):
            self.preview.set_image(QPixmap(path))
        else:
            self.preview.set_image(None)

    def _on_dblclick(self, item):
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path):
            open_file(path)

    def _on_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        path = item.data(Qt.UserRole)
        if not path:
            return
        menu = QMenu(self)
        act_open = menu.addAction("打开")
        act_copy = menu.addAction("复制到剪贴板")
        act_loc = menu.addAction("在文件夹中显示")
        menu.addSeparator()
        act_rm = menu.addAction("从列表移除")
        act_del = menu.addAction("删除文件")
        chosen = menu.exec_(self.list.mapToGlobal(pos))
        if chosen is None:
            return
        exists = os.path.exists(path)
        if chosen == act_open and exists:
            open_file(path)
        elif chosen == act_copy and exists:
            pm = QPixmap(path)
            if not pm.isNull():
                QApplication.clipboard().setPixmap(pm)
                self._log("📋 已复制到剪贴板")
        elif chosen == act_loc and exists:
            open_in_file_manager(path, select=True)
        elif chosen == act_rm:
            self.list.takeItem(self.list.row(item))
        elif chosen == act_del:
            try:
                if exists:
                    os.remove(path)
                self.list.takeItem(self.list.row(item))
                self._log(f"🗑️ 已删除文件：{path}")
            except Exception as e:
                self._log(f"❌ 删除失败：{type(e).__name__}: {e}")

    # === 对外：停止监听 ===
    def ensure_stopped(self):
        if self.checkbox_enable.isChecked():
            self.checkbox_enable.setChecked(False)
        self._unbind_hotkey()
        self._restore_main()
