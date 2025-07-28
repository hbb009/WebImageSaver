from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit,
    QFileDialog, QListWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QSizePolicy, QTabWidget, QCheckBox
)
from PyQt5.QtGui import QFont, QIcon, QPixmap
from PyQt5.QtCore import Qt, QTimer, QMimeData, QBuffer, QIODevice
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QFrame, QWidget

from PyQt5.QtCore import pyqtSignal, QRect, QPoint, QObject
from PyQt5.QtGui import QPainter, QColor, QPen

from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from PyQt5.QtCore import pyqtSignal, QRect, QPoint, QObject
from PyQt5.QtGui import QPainter, QPen
from PyQt5.QtWidgets import QComboBox
from PyQt5.QtGui import QImage

import numpy as np
import threading
import requests
import sys
import os
import keyboard
import pyautogui

# Flask 服务
flask_app = Flask(__name__)
CORS(flask_app)
SAVE_FOLDER = os.path.expanduser("~/Pictures/WebImageSaver")
shared_queue = []

@flask_app.route('/save', methods=['POST'])
def save_from_url():
    data = request.json
    url = data.get("url")
    if not url:
        return jsonify({"error": "no url"}), 400
    try:
        r = requests.get(url)
        ext = url.split('.')[-1].split('?')[0][:4]
        filename = f"img_ext_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        os.makedirs(SAVE_FOLDER, exist_ok=True)
        full_path = os.path.join(SAVE_FOLDER, filename)
        with open(full_path, 'wb') as f:
            f.write(r.content)
        print("✅ 图片已保存：", filename)
        main_window: MainApp = QApplication.instance().activeWindow()
        if main_window and hasattr(main_window, "enabled_checkbox") and main_window.enabled_checkbox.isChecked():
            shared_queue.append({"type": "image", "filename": filename})
        else:
            print("⚠️ 插件请求被忽略（未启用速存图文功能）")

        return jsonify({"status": "ok"})
    except Exception as e:
        print("❌ 保存失败：", e)
        return jsonify({"error": str(e)}), 500

def start_flask():
    flask_app.run(port=8787, debug=False, use_reloader=False)

class ScreenshotSignal(QObject):
    trigger = pyqtSignal()

class Overlay(QWidget):
    def __init__(self, on_capture, on_cancel):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowState(Qt.WindowFullScreen)
        self.start = self.end = None
        self.on_capture = on_capture
        self.on_cancel = on_cancel
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)  # ✅ 设置鼠标样式为十字

        # ✅ 使用 numpy 将 screenshot 转为 QPixmap（完全不依赖 ImageQt）
        screenshot = pyautogui.screenshot()
        img_np = np.array(screenshot.convert("RGB"))
        h, w, ch = img_np.shape
        qimage = QImage(img_np.data, w, h, w * ch, QImage.Format_RGB888)
        self.background = QPixmap.fromImage(qimage)

        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start = event.pos()
            self.end = self.start
            self.update()

    def mouseMoveEvent(self, event):
        if self.start:
            self.end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.on_cancel()
            self.close()
        elif event.button() == Qt.LeftButton and self.start and self.end:
            rect = QRect(self.start, self.end).normalized()
            self.on_capture(rect)
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)  # ✅ 先初始化
        if hasattr(self, 'background'):
            painter.drawPixmap(0, 0, self.background)  # ⬅ 显示冻结背景

        # 左上角提示
        painter.setPen(QPen(Qt.white))
        painter.setFont(QFont("Arial", 14))
        painter.drawText(20, 30, "拖动截图区域，右键取消，ESC退出")

        if self.start and self.end:
            painter.setRenderHint(QPainter.Antialiasing)
            # painter.setBrush(QColor(0, 0, 0, 100))  # 半透明遮罩
            # painter.drawRect(self.rect())

            pen = QPen(Qt.red, 2)
            painter.setPen(pen)
            painter.drawRect(QRect(self.start, self.end))

            # ⬇️ 在拖动矩形右下角显示尺寸
            width = abs(self.end.x() - self.start.x())
            height = abs(self.end.y() - self.start.y())
            size_text = f"{width} × {height}"
            painter.setFont(QFont("Arial", 12))
            painter.setPen(QPen(Qt.yellow))
            painter.drawText(self.end + QPoint(10, -10), size_text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.on_cancel()
            self.close()


class MainApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("桌面助手 v6.1")
        self.setFixedSize(600, 406)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)

        threading.Thread(target=start_flask, daemon=True).start()

        self.screenshot_listener_thread = None
        self.screenshot_listener_active = False

        self.signal = ScreenshotSignal()
        self.signal.trigger.connect(self.activate_overlay)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.tabs)

        self.init_tab_fast_save()
        self.init_tab_screenshot()
        self.init_tab_ratio()
        self.init_tab_settings()

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.check_queue)
        self.update_timer.start(1000)

    def init_tab_fast_save(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # 添加在 top_row 之前
        top_bar = QHBoxLayout()
        top_bar.addStretch()

        # ✅ 创建、设置状态
        self.enabled_checkbox = QCheckBox("启用")
        self.enabled_checkbox.setChecked(True)

        # ✅ 添加到界面
        top_bar.addWidget(self.enabled_checkbox)
        layout.addLayout(top_bar)

        # 绑定信号放最后
        self.enabled_checkbox.clicked.connect(self.toggle_hint)

        self.save_path = QLineEdit()
        self.save_path.setText(os.path.join(os.path.expanduser("~"), "Pictures", "WebImageSaver"))
        self.save_path.setStyleSheet("padding: 5px; font-size: 14px;")

        self.browse_btn = QPushButton("另选目录")
        self.browse_btn.setStyleSheet("padding: 5px;")
        self.browse_btn.clicked.connect(self.select_path)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("图文保存路径:"))
        top_row.addWidget(self.save_path)
        top_row.addWidget(self.browse_btn)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("font-size: 14px;")

        hint = QLabel("提示：如有安装扩展程序，可使用 Alt+鼠标左键保存图片，复制的文字会自动保存为文本")
        hint.setStyleSheet("font-size: 12px; color: gray; padding: 4px;")
        hint.setWordWrap(True)

        layout.addLayout(top_row)
        layout.addWidget(self.list_widget)
        layout.addWidget(hint)
        self.tabs.addTab(page, "速存图文")

        self.last_saved_image = ""
        self.clipboard = QApplication.clipboard()
        self.last_text = ""
        self.clipboard.dataChanged.connect(self.handle_clipboard)

    def toggle_hint(self, state):
        if self.enabled_checkbox.isChecked():
            self.list_widget.addItem("✅ 已启用自动保存功能。")
        else:
            self.list_widget.addItem("⛔ 已关闭自动保存功能。")
        self.list_widget.scrollToBottom()

    def check_queue(self):
        # ❗判断是否启用了速存功能
        if not self.enabled_checkbox.isChecked():
            return  # 功能未启用，不处理插件请求
        while shared_queue:
            item = shared_queue.pop(0)
            if item["type"] == "image":
                filename = item["filename"]
                self.list_widget.addItem(f"🖼️ 插件保存: {filename}")
                self.list_widget.scrollToBottom()
                self.last_saved_image = filename

    def handle_clipboard(self):
        if not self.enabled_checkbox.isChecked():
            return
        md = self.clipboard.mimeData()
        path = self.save_path.text()
        if not os.path.exists(path):
            os.makedirs(path)

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        if md.hasImage():
            image = self.clipboard.image()
            buffer = self.qimage_to_bytes(image)
            filename = f"img_clipboard_{now}.png"
            with open(os.path.join(path, filename), "wb") as f:
                f.write(buffer)
            self.list_widget.addItem(f"🖼️ 图片保存: {filename}")
            self.list_widget.scrollToBottom()
            self.last_saved_image = filename

        elif md.hasText():
            text = md.text().strip()
            if self.last_saved_image:
                txtname = self.last_saved_image.rsplit(".", 1)[0] + ".txt"
                with open(os.path.join(path, txtname), "w", encoding="utf-8") as f:
                    f.write(text)
                self.list_widget.addItem(f"📄 文本保存: {txtname}")
                self.list_widget.scrollToBottom()
                self.last_saved_image = ""
            else:
                self.list_widget.addItem("⚠️ 无图片，忽略文本。")

    def select_path(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if folder:
            self.save_path.setText(folder)

    def init_tab_screenshot(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("组合键: "))
        self.modifier_combo = QComboBox()
        self.modifier_combo.addItems(["Ctrl", "Alt", "Shift"])
        key_row.addWidget(self.modifier_combo)

        key_row.addWidget(QLabel("功能键: "))
        self.function_combo = QComboBox()
        self.function_combo.addItems([f"F{i}" for i in range(1, 13)])
        key_row.addWidget(self.function_combo)

        self.screenshot_toggle = QCheckBox("启用截图监听")
        self.screenshot_toggle.stateChanged.connect(self.toggle_screenshot_listener)
        key_row.addWidget(self.screenshot_toggle)

        layout.addLayout(key_row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("截图保存路径:"))
        self.screenshot_path = QLineEdit()
        self.screenshot_path.setText(os.path.expanduser("~/Pictures/WebImageSaver"))
        path_btn = QPushButton("浏览")
        path_btn.clicked.connect(self.select_screenshot_path)
        path_row.addWidget(self.screenshot_path)
        path_row.addWidget(path_btn)
        layout.addLayout(path_row)

        self.screenshot_list = QListWidget()
        self.screenshot_list.setStyleSheet("font-size: 13px;")
        layout.addWidget(self.screenshot_list)

        self.screenshot_status = QLabel("当前截图监听未启用")
        self.screenshot_status.setStyleSheet("color: gray;")
        layout.addWidget(self.screenshot_status)

        self.tabs.addTab(page, "截图")

    def select_screenshot_path(self):
        folder = QFileDialog.getExistingDirectory(self, "选择截图保存文件夹")
        if folder:
            self.screenshot_path.setText(folder)

    def toggle_screenshot_listener(self, state):
        if state == Qt.Checked:
            self.screenshot_status.setText("截图监听已启用（等待快捷键）")
            self.screenshot_status.setStyleSheet("color: green;")
            self.screenshot_listener_active = True
            self.start_screenshot_listener()
        else:
            self.screenshot_status.setText("当前截图监听未启用")
            self.screenshot_status.setStyleSheet("color: gray;")
            self.screenshot_listener_active = False
            keyboard.unhook_all_hotkeys()

    def start_screenshot_listener(self):
        def listen():
            modifier = self.modifier_combo.currentText().lower()
            func_key = self.function_combo.currentText().upper()
            hotkey = f"{modifier}+{func_key}"
            print("✅ 正在监听快捷键：", hotkey)
            try:
                keyboard.add_hotkey(hotkey, lambda: self.signal.trigger.emit())
            except Exception as e:
                print("❌ 快捷键监听错误：", e)

        if self.screenshot_listener_thread and self.screenshot_listener_thread.is_alive():
            return
        self.screenshot_listener_thread = threading.Thread(target=listen, daemon=True)
        self.screenshot_listener_thread.start()

    def activate_overlay(self):
        self.screenshot_list.addItem("🔥 热键已触发")
        QTimer.singleShot(0, self._show_overlay)  # 使用主线程显示截图框

    def _show_overlay(self):
        print("🟩 正在创建 Overlay 截图窗口...")
        self.overlay = Overlay(self.capture_region, self.cancel_capture)
        self.overlay.show()

    def capture_region(self, rect):
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{now}.png"
        save_path = self.screenshot_path.text().strip()
        full_path = os.path.join(save_path, filename)

        try:
            screenshot = pyautogui.screenshot(region=(rect.x(), rect.y(), rect.width(), rect.height()))
            screenshot.save(full_path)
            image = QPixmap(full_path)
            QApplication.clipboard().setPixmap(image)
            self.screenshot_status.setText(f"✅ 截图完成：{filename}")
            self.screenshot_list.addItem(f"📸 {filename}")
        except Exception as e:
            print("❌ 截图失败：", e)
            self.screenshot_status.setText("❌ 截图失败，请检查权限")

    def cancel_capture(self):
        self.screenshot_status.setText("❌ 截图已取消")

    def init_tab_ratio(self):
        page = QWidget()
        main_layout = QHBoxLayout(page)  # ✅ 添加这一行定义主布局

        # 左侧：原比例计算器
        left_layout = QVBoxLayout()
        title = QLabel("比例计算器")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setAlignment(Qt.AlignHCenter)
        left_layout.addWidget(title)

        self.input_a = QLineEdit(); self.input_a.setPlaceholderText("A")
        self.input_b = QLineEdit(); self.input_b.setPlaceholderText("B")
        self.input_c = QLineEdit(); self.input_c.setPlaceholderText("C")
        self.input_d = QLineEdit(); self.input_d.setPlaceholderText("D")
        self.input_d.setReadOnly(True)
        self.input_d.setEnabled(False)

        for i in [self.input_a, self.input_b, self.input_c, self.input_d]:
            i.setFixedWidth(100)
            i.setAlignment(Qt.AlignCenter)
            i.setStyleSheet("font-size: 14px; padding: 6px; border-radius: 6px;")

        from PyQt5.QtGui import QIntValidator
        validator = QIntValidator(0, 99999)
        self.input_a.setValidator(validator)
        self.input_b.setValidator(validator)
        self.input_c.setValidator(validator)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.update_result)
        for inp in [self.input_a, self.input_b, self.input_c]:
            inp.textChanged.connect(lambda: self.timer.start(1000))

        self.swap_btn = QPushButton("AB交换")
        self.swap_btn.setFixedWidth(80)
        self.swap_btn.setStyleSheet("padding: 5px; font-size: 13px;")
        self.swap_btn.clicked.connect(self.swap_ab)

        self.copy_d_btn = QPushButton("复制D数")
        self.copy_d_btn.setFixedWidth(80)
        self.copy_d_btn.setStyleSheet("padding: 5px; font-size: 13px;")
        self.copy_d_btn.clicked.connect(self.copy_d_value)

        def row(label, widget):
            h = QHBoxLayout()
            h.addWidget(QLabel(label))
            h.addWidget(widget)
            return h

        left_layout.addLayout(row("A", self.input_a))
        left_layout.addLayout(row("B", self.input_b))
        left_layout.addWidget(self.swap_btn, alignment=Qt.AlignLeft)
        left_layout.addWidget(QFrame(frameShape=QFrame.HLine), alignment=Qt.AlignBottom)
        left_layout.addLayout(row("C", self.input_c))
        left_layout.addLayout(row("D", self.input_d))
        left_layout.addWidget(self.copy_d_btn, alignment=Qt.AlignLeft)

        # 中间竖线
        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setFrameShadow(QFrame.Sunken)

        # 右侧说明
        right_layout = QVBoxLayout()
        guide = QLabel()
        guide.setText("""
        请输入A、B、C任意数值，系统将自动计算出D = B × C ÷ A。
        点击“AB交换”可快速对换A与B数值。
        点击“复制D数”可将D的整数部分复制到剪贴板。
        """)

        guide.setWordWrap(True)
        guide.setStyleSheet("font-size: 13px; color: gray;")
        right_layout.addWidget(guide)

        # ✅ 用一个包裹层把左边内容顶上去
        left_wrapper = QVBoxLayout()
        left_wrapper.addLayout(left_layout)
        left_wrapper.addStretch()  # ⬅ 保证下方空白，内容靠上
        main_layout.addLayout(left_wrapper)
        # ✅ 中间竖线和右侧说明保持不变
        main_layout.addWidget(vline)
        main_layout.addLayout(right_layout)

        self.tabs.addTab(page, "比例计算器")

    def update_result(self):
        try:
            a = float(self.input_a.text())
            b = float(self.input_b.text())
            c = float(self.input_c.text())
            d = b * c / a
            self.input_d.setText(f"{d:.2f}")
        except:
            self.input_d.setText("")

    def swap_ab(self):
        a_val = self.input_a.text()
        b_val = self.input_b.text()
        self.input_a.setText(b_val)
        self.input_b.setText(a_val)
        self.timer.start(1000)

    def copy_d_value(self):
        text = self.input_d.text().split(".")[0]
        mime = QMimeData()
        mime.setText(text)
        self.clipboard.blockSignals(True)
        self.clipboard.setMimeData(mime)
        self.clipboard.blockSignals(False)

    def qimage_to_bytes(self, image):
        pixmap = QPixmap.fromImage(image)
        buffer = QBuffer()
        buffer.open(QIODevice.ReadWrite)
        pixmap.save(buffer, "PNG")
        return buffer.data().data()

    def init_tab_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("【设置】功能开发中..."))
        self.tabs.addTab(page, "设置")

    def on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)

        # 强制关闭速存图文
        if hasattr(self, 'enabled_checkbox') and self.enabled_checkbox.isChecked():
            self.enabled_checkbox.setChecked(False)

        # 强制关闭截图监听
        if hasattr(self, 'screenshot_toggle') and self.screenshot_toggle.isChecked():
            self.screenshot_toggle.setChecked(False)

        # 其他功能页如“截图”、“比例计算器”等将来也可以在这里加：
        # elif tab_name == "截图":
        #     self.start_screenshot_mode()
        # elif tab_name == "比例计算器":
        #     self.activate_ratio_tool()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainApp()
    win.show()
    sys.exit(app.exec_())
