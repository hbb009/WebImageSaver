# 标准库
import os
import sys
import threading
import requests
from datetime import datetime

# 第三方库
import numpy as np
import keyboard
import pyautogui
from flask import Flask, request, jsonify
from flask_cors import CORS

# PyQt5 - Widgets
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit, QFileDialog,
    QListWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QCheckBox, QComboBox, QStackedWidget, QGridLayout
)

# PyQt5 - Core
from PyQt5.QtCore import (
    Qt, QTimer, QMimeData, QBuffer, QIODevice, pyqtSignal,
    QRect, QPoint, QObject
)

# PyQt5 - Gui
from PyQt5.QtGui import (
    QFont, QIcon, QPixmap, QPainter, QColor, QPen, QImage
)

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
        self.setWindowIcon(QIcon("star.ico"))
        self.setWindowTitle("桌面助手 v6.7")
        self.setFixedWidth(600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)

        self.setFont(QFont("微软雅黑", 14))  # 原字体大小是8-9，提升为12更清晰
        self.setStyleSheet("""
            QWidget {
                background-color: #20233A;
                color: #ffffff;
                font-family: '微软雅黑';
            }
            QPushButton {
                background-color: #2B2E45;
                color: white;
                border: 1px solid #444;
                padding: 8px;
                border-radius: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #3A3D5C;
            }
            QLineEdit {
                background-color: #2B2E45;
                color: white;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px;
            }
            QListWidget {
                background-color: #2B2E45;
                border: 1px solid #444;
                padding: 4px;
                color: white;
            }
            QLabel {
                color: white;
                font-size: 14px;
            }
            QCheckBox {
                font-size: 14px;
            }
            QComboBox {
                background-color: #2B2E45;
                color: white;
                border: 1px solid #444;
                padding: 4px;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: #2B2E45;
            }
            QPushButton {
                min-height: 40px;
                font-size: 15px;
                border-radius: 12px;
            }
            QCheckBox, QLabel {
                font-size: 14px;
            }
            QLineEdit, QComboBox {
                min-height: 34px;
                font-size: 14px;
            }
            VBoxLayout, QHBoxLayout {
                spacing: 12px;
            }
        """)

        threading.Thread(target=start_flask, daemon=True).start()

        self.screenshot_listener_thread = None
        self.screenshot_listener_active = False

        self.signal = ScreenshotSignal()
        self.signal.trigger.connect(self.activate_overlay)

        self.stack = QStackedWidget()

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.stack)

        self.init_tab_fast_save()
        self.init_tab_screenshot()
        self.init_tab_ratio()
        self.init_tab_settings()

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.check_queue)
        self.update_timer.start(1000)

        # ✅ 创建底部导航按钮栏
        bottom_bar = QHBoxLayout()
        self.btn_fast = QPushButton("速存图文")
        self.btn_shot = QPushButton("截图工具")
        self.btn_calc = QPushButton("比例计算")
        self.btn_setting = QPushButton("系统设置")

        for btn in [self.btn_fast, self.btn_shot, self.btn_calc, self.btn_setting]:
            btn.setFixedHeight(40)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2B2E45;
                    color: white;
                    font-size: 14px;
                    border: 1px solid #444;
                    border-radius: 10px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #3A3D5C;
                }
            """)

        bottom_bar.addWidget(self.btn_fast)
        bottom_bar.addWidget(self.btn_shot)
        bottom_bar.addWidget(self.btn_calc)
        bottom_bar.addWidget(self.btn_setting)

        self.layout().addLayout(bottom_bar)
        self.set_active_button(self.btn_fast)

        # ✅ 绑定切换功能页
        self.btn_fast.clicked.connect(lambda: (self.stack.setCurrentIndex(0), self.set_active_button(self.btn_fast)))
        self.btn_shot.clicked.connect(lambda: (self.stack.setCurrentIndex(1), self.set_active_button(self.btn_shot)))
        self.btn_calc.clicked.connect(lambda: (self.stack.setCurrentIndex(2), self.set_active_button(self.btn_calc)))
        self.btn_setting.clicked.connect(lambda: (self.stack.setCurrentIndex(3), self.set_active_button(self.btn_setting)))

    def init_tab_fast_save(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)

        self.enabled_checkbox = QCheckBox("启用")
        self.enabled_checkbox.setChecked(True)
        self.enabled_checkbox.clicked.connect(self.toggle_hint)

        self.save_path = QLineEdit()
        self.save_path.setText(os.path.join(os.path.expanduser("~"), "Pictures", "WebImageSaver"))
        self.save_path.setStyleSheet("padding: 5px; font-size: 14px;")

        self.browse_btn = QPushButton("另选目录")
        self.browse_btn.setStyleSheet("padding: 5px;")
        self.browse_btn.clicked.connect(self.select_path)

        # 第1行：左文字 + 右启用框
        row1 = QHBoxLayout()
        label = QLabel("图文保存路径:")
        label.setStyleSheet("font-size: 14px; min-width: 100px;")
        row1.addWidget(label)
        row1.addStretch()
        row1.addWidget(self.enabled_checkbox)
        layout.addLayout(row1)

        # 第2行：左路径 + 右按钮
        row2 = QHBoxLayout()
        row2.addWidget(self.save_path)
        row2.addWidget(self.browse_btn)
        layout.addLayout(row2)

        self.list_widget = QListWidget()
        self.list_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.list_widget.setFixedHeight(200)
        self.list_widget.setStyleSheet("font-size: 14px;")

        hint = QLabel("提示：如有安装扩展程序，可使用 Alt+鼠标左键保存图片，复制的文字会自动保存为文本")
        hint.setStyleSheet("font-size: 18px; color: gray; padding: 0px; margin-top: 12px;")
        hint.setWordWrap(True)

        layout.addWidget(self.list_widget)
        layout.addStretch()  # 把上面控件顶上去
        layout.addWidget(hint, alignment=Qt.AlignBottom)
        self.stack.addWidget(page)

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
        layout.setContentsMargins(20, 20, 20, 20)

        # 第1行：左=文字，右=启用截图
        row1 = QHBoxLayout()
        label = QLabel("截图保存路径：")
        label.setStyleSheet("font-size: 14px;")
        row1.addWidget(label)

        row1.addStretch()

        self.screenshot_toggle = QCheckBox("启用截图")

        self.function_combo = QComboBox()
        self.screenshot_toggle.stateChanged.connect(self.toggle_screenshot_listener)
        row1.addWidget(self.screenshot_toggle)

        layout.addLayout(row1)

        # 第2行：左=路径栏，右=按钮
        row2 = QHBoxLayout()
        self.screenshot_path = QLineEdit()
        self.screenshot_path.setText(os.path.join(os.path.expanduser("~"), "Pictures", "WebImageSaver"))
        self.screenshot_path.setStyleSheet("padding: 5px; font-size: 14px;")
        row2.addWidget(self.screenshot_path)

        path_btn = QPushButton("另选保存")
        path_btn.setStyleSheet("padding: 5px;")
        path_btn.clicked.connect(self.select_screenshot_path)
        row2.addWidget(path_btn)
        
        layout.addLayout(row2)

        # 第3行：左列表，右组合+功能键
        row3 = QHBoxLayout()

        # 左边文件列表
        self.screenshot_list = QListWidget()
        self.screenshot_list.setStyleSheet("font-size: 16px;")
        self.screenshot_list.setFixedHeight(200)
        row3.addWidget(self.screenshot_list, 3)  # 左边占比3份

        # 右边：垂直组合键 + 功能键
        right_col = QVBoxLayout()
        right_col.addWidget(QLabel("组合键："))
        self.modifier_combo = QComboBox()
        self.modifier_combo.addItems(["Ctrl", "Alt", "Shift"])
        right_col.addWidget(self.modifier_combo)

        right_col.addWidget(QLabel("功能键："))
        self.function_combo = QComboBox()
        self.function_combo.addItems([f"F{i}" for i in range(1, 13)])
        right_col.addWidget(self.function_combo)

        row3.addLayout(right_col, 1)  # 右边占比1份
        layout.addLayout(row3)

        # 第4行：状态栏
        self.screenshot_status = QLabel("当前截图监听未启用")
        self.screenshot_status.setStyleSheet("font-size: 18px; color: gray;")
        layout.addWidget(self.screenshot_status)

        self.stack.addWidget(page)

    def select_screenshot_path(self):
        folder = QFileDialog.getExistingDirectory(self, "选择截图保存文件夹")
        if folder:
            self.screenshot_path.setText(folder)

    def toggle_screenshot_listener(self, state):
        if state == Qt.Checked:
            self.screenshot_status.setText("截图监听已启用（等待快捷键）")
            self.screenshot_status.setStyleSheet("font-size: 18px; color: green;")
            self.screenshot_listener_active = True
            self.start_screenshot_listener()
        else:
            self.screenshot_status.setText("当前截图监听未启用")
            self.screenshot_status.setStyleSheet("font-size: 18px; color: gray;")
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
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)

        font18 = QFont("微软雅黑", 18)

        # 输入框
        self.input_a = QLineEdit(); self.input_a.setPlaceholderText("A")
        self.input_b = QLineEdit(); self.input_b.setPlaceholderText("B")
        self.input_c = QLineEdit(); self.input_c.setPlaceholderText("C")
        self.input_d = QLineEdit(); self.input_d.setPlaceholderText("D")
        self.input_d.setReadOnly(True)
        self.input_d.setEnabled(False)

        for w in [self.input_a, self.input_b, self.input_c, self.input_d]:
            w.setFont(font18)
            w.setFixedHeight(40)
            w.setAlignment(Qt.AlignCenter)
            w.setStyleSheet("padding: 6px; border-radius: 6px;")

        from PyQt5.QtGui import QIntValidator

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

        # 第1行：A 与 C
        row1 = QHBoxLayout()
        left_group = QHBoxLayout()
        a_label = QLabel("A")
        a_label.setFont(font18)
        a_label.setFixedWidth(30)
        row1.addWidget(a_label)
        row1.addWidget(self.input_a)
        right_group = QHBoxLayout()
        row1.addStretch()
        c_label = QLabel("C")
        c_label.setFont(font18)
        c_label.setFixedWidth(30)
        row1.addWidget(c_label)
        row1.addWidget(self.input_c)

        # 第2行：B 与 D
        row2 = QHBoxLayout()
        b_label = QLabel("B")
        b_label.setFont(font18)
        b_label.setFixedWidth(30)
        row2.addWidget(b_label)
        row2.addWidget(self.input_b)
        row2.addStretch()
        d_label = QLabel("D")
        d_label.setFont(font18)
        d_label.setFixedWidth(30)
        row2.addWidget(d_label)
        row2.addWidget(self.input_d)

        # 第3行：按钮 + 说明标签
        row3 = QHBoxLayout()

        ab_label = QLabel("A与B数值互换")
        ab_label.setFont(font18)
        self.swap_btn = QPushButton("交换")
        self.swap_btn.setFont(font18)
        self.swap_btn.setFixedWidth(100)
        self.swap_btn.clicked.connect(self.swap_ab)

        d_label = QLabel("D数值")
        d_label.setFont(font18)
        self.copy_d_btn = QPushButton("复制")
        self.copy_d_btn.setFont(font18)
        self.copy_d_btn.setFixedWidth(100)
        self.copy_d_btn.clicked.connect(self.copy_d_value)

        left_part = QHBoxLayout()
        left_part.addWidget(ab_label)
        left_part.addWidget(self.swap_btn)
        right_part = QHBoxLayout()
        right_part.addWidget(d_label)
        right_part.addWidget(self.copy_d_btn)
        row3.addLayout(left_part)
        row3.addStretch()
        row3.addLayout(right_part)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        # 底部说明文字
        tip = QLabel("""请输入 A、B、C 任意数值，系统将自动计算出：A : B = C : D\n点击“交换”可对换 A 与 B 数值；\n点击“复制”可将 D 的整数部分复制到剪贴板。""")
        tip.setFont(QFont("微软雅黑", 16))
        tip.setStyleSheet("color: gray;")
        tip.setWordWrap(True)

        # 装入主 layout
        row1_wrapper = QHBoxLayout()
        row1_wrapper.addStretch()
        row1_wrapper.addLayout(row1)
        row1_wrapper.addStretch()
        layout.addLayout(row1_wrapper)

        row2_wrapper = QHBoxLayout()
        row2_wrapper.addStretch()
        row2_wrapper.addLayout(row2)
        row2_wrapper.addStretch()
        layout.addLayout(row2_wrapper)

        layout.addLayout(row3)  # ✅ 把第三行按钮添加进主布局
        layout.addWidget(line)
        layout.addWidget(tip)
        layout.addStretch()

        self.stack.addWidget(page)

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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(QLabel("【设置】功能开发中..."))
        self.stack.addWidget(page)

    def set_active_button(self, active_btn):
        # 页面切换时，自动关闭不该启用的功能
        if active_btn != self.btn_fast:
            if self.enabled_checkbox.isChecked():
                self.enabled_checkbox.setChecked(False)
                self.toggle_hint(False)

        if active_btn != self.btn_shot:
            if self.screenshot_toggle.isChecked():
                self.screenshot_toggle.setChecked(False)
                self.toggle_screenshot_listener(Qt.Unchecked)

        for btn in [self.btn_fast, self.btn_shot, self.btn_calc, self.btn_setting]:
            if btn == active_btn:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3A3D5C;
                        color: white;
                        font-size: 14px;
                        border: 2px solid #888;
                        border-radius: 10px;
                        min-width: 80px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2B2E45;
                        color: white;
                        font-size: 14px;
                        border: 1px solid #444;
                        border-radius: 10px;
                        min-width: 80px;
                    }
                    QPushButton:hover {
                        background-color: #3A3D5C;
                    }
                """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainApp()
    win.show()
    sys.exit(app.exec_())
