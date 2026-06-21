# pages/page_batch_tag.py  v9.5
# 升级：从"生成占位 txt"改为"调用 Ollama 视觉模型真正打标"
import os
import glob
import base64

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QListWidget, QCheckBox, QComboBox, QMessageBox,
    QGroupBox, QProgressBar,
)

try:
    from utils import ollama_client as oc
except Exception:
    oc = None


def _list_vision_models():
    if oc and oc.is_alive():
        models = oc.list_models()
        # 优先列出视觉模型
        vision = [m for m in models if oc._is_vision_model_name(m)]
        others = [m for m in models if not oc._is_vision_model_name(m)]
        return vision + others
    return ["（未检测到 Ollama）"]


class _TagWorker(QThread):
    progress = pyqtSignal(int, int, str)   # current, total, filename
    done     = pyqtSignal(int, int)        # ok, total

    def __init__(self, folder, model, prompt_tpl, overwrite, lang):
        super().__init__()
        self.folder     = folder
        self.model      = model
        self.prompt_tpl = prompt_tpl
        self.overwrite  = overwrite
        self.lang       = lang
        self._stop      = False

    def stop(self):
        self._stop = True

    def run(self):
        exts  = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp")
        files = []
        for e in exts:
            files += glob.glob(os.path.join(self.folder, e))
        total = len(files)
        ok    = 0

        for idx, img_path in enumerate(files, 1):
            if self._stop:
                break
            name    = os.path.basename(img_path)
            caption = os.path.splitext(img_path)[0] + ".txt"
            self.progress.emit(idx, total, name)

            if (not self.overwrite) and os.path.exists(caption):
                ok += 1
                continue

            content = self._tag_image(img_path)
            if content is not None:
                try:
                    with open(caption, "w", encoding="utf-8") as f:
                        f.write(content)
                    ok += 1
                except Exception:
                    pass

        self.done.emit(ok, total)

    def _tag_image(self, img_path: str):
        """
        用 Ollama 视觉模型为单张图片生成标签/提示词。
        失败返回 None。
        """
        if not oc or not oc.is_alive():
            return None
        try:
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")

            prompt = self.prompt_tpl
            msgs = [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64],
                }
            ]
            parts = []
            for piece in oc.stream_chat(self.model, msgs):
                if isinstance(piece, str):
                    parts.append(piece)
            return "".join(parts).strip() or None
        except Exception:
            return None


# 内置提示词模板
PROMPT_TEMPLATES = {
    "Booru 标签（英文）":
        "Write a list of Booru tags for this image. "
        "Use lowercase, underscores, comma-separated. Output only tags, no explanation.",
    "SD 训练提示词（英文）":
        "Write a stable diffusion training prompt for this image. "
        "Comma-separated phrases, English only. No extra text.",
    "自然语言描述（中文）":
        "请用中文简洁描述这张图片的内容，包括主体、风格、色调、构图等要素，适合用于 AI 训练数据。",
    "自然语言描述（英文）":
        "Describe this image in English concisely, covering subject, style, color tone, and composition. "
        "Suitable for AI training data.",
    "中英双语描述":
        "Describe this image in both Chinese and English. "
        "Format: 中文描述 / English description.",
}


class PageBatchTag(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 12)
        lay.setSpacing(10)

        # ── 文件夹选择 ────────────────────────────────────────────────────────
        top = QHBoxLayout()
        lay.addLayout(top)
        self.path_lab = QLabel("未选择文件夹")
        self.path_lab.setWordWrap(True)
        self.btn_pick = QPushButton("选择文件夹")
        self.btn_pick.clicked.connect(self._pick)
        top.addWidget(self.path_lab, 1)
        top.addWidget(self.btn_pick)

        # ── 模型 + 提示词模板 ─────────────────────────────────────────────────
        grp_model = QGroupBox("Ollama 视觉模型 & 提示词")
        grp_model.setProperty("titleVariant", "accent")
        glay = QVBoxLayout(grp_model)
        lay.addWidget(grp_model)

        row_m = QHBoxLayout()
        glay.addLayout(row_m)
        row_m.addWidget(QLabel("模型："))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        self.model_combo.addItems(_list_vision_models())
        row_m.addWidget(self.model_combo)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setFixedWidth(60)
        self.btn_refresh.clicked.connect(self._refresh_models)
        row_m.addWidget(self.btn_refresh)
        row_m.addStretch(1)

        row_p = QHBoxLayout()
        glay.addLayout(row_p)
        row_p.addWidget(QLabel("提示词："))
        self.prompt_combo = QComboBox()
        self.prompt_combo.setMinimumWidth(260)
        for k in PROMPT_TEMPLATES:
            self.prompt_combo.addItem(k)
        row_p.addWidget(self.prompt_combo)
        row_p.addStretch(1)

        # ── 选项 ─────────────────────────────────────────────────────────────
        ops = QHBoxLayout()
        lay.addLayout(ops)
        self.over = QCheckBox("覆盖已存在的 .txt")
        ops.addWidget(self.over)
        ops.addStretch(1)

        # ── 进度条 ────────────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        lay.addWidget(self.progress_label)

        # ── 文件列表 ──────────────────────────────────────────────────────────
        self.list = QListWidget()
        lay.addWidget(self.list, 1)

        # ── 按钮行 ────────────────────────────────────────────────────────────
        row_btn = QHBoxLayout()
        lay.addLayout(row_btn)
        row_btn.addStretch(1)
        self.btn_go   = QPushButton("开始打标")
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        row_btn.addWidget(self.btn_go)
        row_btn.addWidget(self.btn_stop)
        self.btn_go.clicked.connect(self._run)
        self.btn_stop.clicked.connect(self._stop)

        self.folder = None
        self.worker = None

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "选择图片文件夹", "")
        if d:
            self.folder = d
            self.path_lab.setText(d)
            self._fill_list()

    def _fill_list(self):
        self.list.clear()
        if not self.folder:
            return
        for e in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"):
            for p in glob.glob(os.path.join(self.folder, e)):
                self.list.addItem(os.path.basename(p))

    def _refresh_models(self):
        models = _list_vision_models()
        self.model_combo.clear()
        self.model_combo.addItems(models)

    def _run(self):
        if not self.folder:
            QMessageBox.warning(self, "提示", "请先选择文件夹")
            return
        model = self.model_combo.currentText().strip()
        if not model or "未检测到" in model:
            QMessageBox.warning(self, "提示", "未检测到 Ollama 服务或模型，请先启动 Ollama")
            return
        if not (oc and oc.is_alive()):
            QMessageBox.warning(self, "提示", "Ollama 服务未运行")
            return

        prompt_key = self.prompt_combo.currentText()
        prompt_tpl = PROMPT_TEMPLATES.get(prompt_key, list(PROMPT_TEMPLATES.values())[0])

        self.btn_go.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)

        self.worker = _TagWorker(
            folder=self.folder,
            model=model,
            prompt_tpl=prompt_tpl,
            overwrite=self.over.isChecked(),
            lang="",
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.start()

    def _stop(self):
        if self.worker:
            self.worker.stop()
        self.btn_stop.setEnabled(False)

    def _on_progress(self, current: int, total: int, name: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"正在处理（{current}/{total}）：{name}")

    def _on_done(self, ok: int, total: int):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.btn_go.setEnabled(True)
        self.btn_stop.setEnabled(False)
        QMessageBox.information(
            self, "完成",
            f"共发现 {total} 张图片，成功生成/覆盖 {ok} 个 .txt"
        )
