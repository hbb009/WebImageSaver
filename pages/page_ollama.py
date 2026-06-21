# pages/page_ollama.py  v9.5
# 样式全部由 app.qss 管理，已移除所有 setStyleSheet(TEXT_STYLE/BUTTON_STYLE/LINEEDIT_STYLE) 调用

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont, QTextCursor, QFontMetrics
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QListWidget, QListWidgetItem, QComboBox, QAbstractItemView,
)
from PyQt5.QtCore import QEvent

from utils import ollama_client as oc
import re


class _ModelListWorker(QThread):
    done = pyqtSignal(list)
    fail = pyqtSignal(str)

    def run(self):
        try:
            from utils import ollama_client as oc
            self.done.emit(oc.list_models())
        except Exception as e:
            self.fail.emit(str(e))


class ChatWorker(QThread):
    chunk = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, model, messages):
        super().__init__()
        self.model    = model
        self.messages = messages

    def run(self):
        try:
            for piece in oc.stream_chat(self.model, self.messages):
                if piece:
                    self.chunk.emit(piece)
        except Exception as e:
            self.error.emit(str(e))


class PageOllama(QWidget):
    def __init__(self):
        super().__init__()
        self._models_loaded  = False
        self._list_worker    = None
        self._render_timer   = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._flush_render)
        self._last_rendered_len = 0
        self.chat_history    = []
        self.current_ai_label = None
        self.input_history   = []
        self.history_index   = -1

        lay = QVBoxLayout(self)

        # 顶部状态 + 模型下拉
        top = QHBoxLayout()
        lay.addLayout(top)

        self.status = QLabel("✅ 等待输入中...")
        top.addWidget(self.status, 8)
        top.addStretch()

        self.model_combo = QComboBox()
        self.model_combo.setFixedWidth(200)
        self.model_combo.setEnabled(False)
        top.addWidget(self.model_combo)

        # 对话列表
        self.list = QListWidget()
        self.list.setMinimumHeight(320)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setFocusPolicy(Qt.NoFocus)
        # 气泡背景透明，不再硬编码颜色
        self.list.setStyleSheet(
            "QListWidget, QListWidget::item { background: transparent; }"
            "QListWidget::item:hover { background: transparent; }"
            "QListWidget::item:selected { background: transparent; }"
        )
        lay.addWidget(self.list)

        line_px = QFontMetrics(self.list.font()).lineSpacing() + 2
        self._scroll_step = line_px
        sb = self.list.verticalScrollBar()
        sb.setSingleStep(line_px)
        sb.setPageStep(max(1, self.list.viewport().height() - line_px))
        self.list.viewport().installEventFilter(self)
        lay.addSpacing(6)

        # 输入区标签
        self.label_input = QLabel("用户请输入问题：")
        self.label_input.setContentsMargins(2, 4, 0, 4)
        lay.addWidget(self.label_input)

        self.input = QTextEdit()
        self.input.setMinimumHeight(80)
        lay.addWidget(self.input)

        row = QHBoxLayout()
        lay.addLayout(row)
        row.addStretch()

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)

        self.up = QPushButton("上条指令")
        self.up.setEnabled(False)
        self.up.clicked.connect(self.load_previous_input)
        row.addWidget(self.up)

        self.clear_btn = QPushButton("清空对话")
        self.clear_btn.clicked.connect(self._clear)
        row.addWidget(self.clear_btn)
        row.addStretch()

    def on_enter(self):
        if oc.is_alive():
            self.status.setText("🟡 正在读取本地模型…")
            self.model_combo.setEnabled(False)
            if self._models_loaded:
                self.model_combo.setEnabled(True)
                self.status.setText("🟢 已加载模型列表")
                return
            self._list_worker = _ModelListWorker()
            self._list_worker.done.connect(self._fill_models)
            self._list_worker.fail.connect(lambda msg: self._set_err(f"读取模型失败：{msg}"))
            self._list_worker.start()
        else:
            self.model_combo.clear()
            self.model_combo.setEnabled(False)
            self.status.setText("⚪ 未检测到 Ollama（其余功能可正常使用）")

    def _send(self):
        self._buf = ""
        self._last_rendered_len = 0
        self.current_ai_item = None
        if not oc.is_alive():
            self.status.setText("⚠️ 未运行 Ollama")
            return
        model = self.model_combo.currentText().strip()
        if not model:
            self.status.setText("⚠️ 未选择模型")
            return
        if not oc.has_model(model):
            self.status.setText(f"⚠️ 本机未发现模型 {model}，请先 pull")
            return
        prompt = self.input.toPlainText().strip()
        if not prompt:
            return
        self.input_history.append(prompt)
        self.history_index = len(self.input_history)
        if not self.chat_history:
            self.chat_history.append({"role": "system", "content": "请用中文简洁回答。"})
        self.chat_history.append({"role": "user", "content": prompt})
        self._add_bubble(prompt, is_user=True)
        self.input.clear()
        self.current_ai_label = None
        self.up.setEnabled(True)
        self.status.setText("🟡 回答生成中...")
        self.worker = ChatWorker(model, self.chat_history)
        self.worker.chunk.connect(self._on_chunk)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_done)
        self.worker.start()

    def _on_chunk(self, piece: str):
        if not hasattr(self, "_buf"):
            self._buf = ""
        self._buf += piece
        if not self._render_timer.isActive():
            self._render_timer.start(40)

    def _on_error(self, msg: str):
        self.status.setText("❌ " + msg)

    def _add_bubble(self, text, is_user):
        w   = QWidget()
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lab.setFont(QFont("微软雅黑", 10))
        lab.setFixedWidth(int(self.list.viewport().width() * (0.70 if is_user else 0.88)))

        # 用户气泡：使用主题颜色变量而非硬编码
        if is_user:
            lab.setObjectName("ChatBubbleUser")
            lab.setStyleSheet(
                "QLabel#ChatBubbleUser{"
                "background:#0e1530;"
                "border:1px solid #2a3965;"
                "border-radius:8px;"
                "padding:6px 10px;"
                "}"
            )

        out   = QHBoxLayout()
        out.setContentsMargins(20, 1, 20, 6)
        inner = QVBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(lab)
        if is_user:
            out.addStretch()
            out.addLayout(inner)
        else:
            out.addLayout(inner)
            out.addStretch()

        w.setLayout(out)
        item = QListWidgetItem()
        item.setSizeHint(w.sizeHint())
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(item)
        self.list.setItemWidget(item, w)
        return lab, item

    def _clear(self):
        self.list.clear()
        self.chat_history          = []
        self.current_ai_label      = None
        self.current_ai_item       = None
        self._buf                  = ""
        self._last_rendered_len    = 0

    def load_previous_input(self):
        if not self.input_history:
            return
        if self.history_index > 0:
            self.history_index -= 1
        else:
            self.history_index = 0
        self.input.setPlainText(self.input_history[self.history_index])
        self.input.moveCursor(QTextCursor.End)

    def _fill_models(self, models: list):
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(m)
        self.model_combo.setEnabled(True)
        self.status.setText("🟢 已加载模型列表")
        self._models_loaded = True
        self._list_worker   = None

    def _set_err(self, msg: str):
        self.status.setText("❌ " + msg)
        self._list_worker = None

    def _flush_render(self):
        filtered = re.sub(r"<\s*think\s*>.*?<\s*/\s*think\s*>", "", self._buf,
                          flags=re.I | re.S)
        if self.current_ai_label is None:
            self.current_ai_label, self.current_ai_item = self._add_bubble(filtered, is_user=False)
            self._last_rendered_len = len(filtered)
        else:
            if len(filtered) > self._last_rendered_len:
                self.current_ai_label.setText(filtered)
                container = self.list.itemWidget(self.current_ai_item)
                new_hint  = container.sizeHint()
                if new_hint != self.current_ai_item.sizeHint():
                    self.current_ai_item.setSizeHint(new_hint)
                self._last_rendered_len = len(filtered)
        self.list.scrollToBottom()

    def _on_done(self):
        if not hasattr(self, "_buf"):
            self._buf = ""
        if not self._buf.endswith("\n"):
            self._buf += "\n"
        self._flush_render()
        self._add_tail_spacer(10)
        self.list.scrollToBottom()
        self.status.setText("🟢 回答完成")

    def _add_tail_spacer(self, h: int = 8):
        spacer = QListWidgetItem()
        spacer.setSizeHint(QSize(1, h))
        spacer.setFlags(spacer.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(spacer)

    def eventFilter(self, obj, event):
        if obj is self.list.viewport() and event.type() == QEvent.Wheel:
            delta = event.angleDelta().y()
            if delta:
                sb = self.list.verticalScrollBar()
                sb.setValue(sb.value() - (self._scroll_step if delta > 0 else -self._scroll_step))
                return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        sb = self.list.verticalScrollBar()
        sb.setPageStep(max(1, self.list.viewport().height() - getattr(self, "_scroll_step", 16)))
