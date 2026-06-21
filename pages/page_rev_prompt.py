# pages/page_rev_prompt.py  v9.5
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGroupBox, QFormLayout, QFileDialog,
    QTextEdit, QComboBox, QGridLayout, QRadioButton, QButtonGroup,
    QSizePolicy, QSpacerItem, QCheckBox,
)
from PyQt5.QtGui import QPixmap, QColor, QBrush, QImageReader

import os
import base64

try:
    from utils import ollama_client as oc
except Exception:
    oc = None

# ── 9 种模式 ────────────────────────────────────────────────────────────────
JOY_TEMPLATES = {
    "Descriptive":             "根据以下图像要点生成客观、完整、结构化中文描述，适合生成模型使用：{BASE}",
    "Descriptive (Informal)":  "以轻松口吻用中文描述以下图像要点，控制在3-6句：{BASE}",
    "Training Prompt":         "将以下要素整理成训练提示词（中英各一行，短语、逗号分隔）：{BASE}",
    "MidJourney":              "把以下信息改写成 MidJourney 风格提示词（英文、逗号分隔，含风格/光线/镜头/后期）：{BASE}",
    "Booru tag list":          "整理为 Booru 标签（英文小写、下划线、逗号分隔、重要在前）：{BASE}",
    "Booru-like tag list":     "输出接近 Booru 的标签（英文小写，含风格与构图，逗号分隔）：{BASE}",
    "Art Critic":              "以美术评论视角（中文）分三段分析：构图、光影与色彩、风格与情绪：{BASE}",
    "Product Listing":         "改写成商品文案（中文：标题一句+卖点3-5条，每条≤20字）：{BASE}",
    "Social Media Post":       "生成社媒文案（先中文标题+正文，再给英文等价版本）：{BASE}",
}
JOY_MODE_LIST = list(JOY_TEMPLATES.keys())

MODE_CN = {
    "Descriptive":            "描述",
    "Descriptive (Informal)": "口语描述",
    "Training Prompt":        "训练提示词",
    "MidJourney":             "MJ风格",
    "Booru tag list":         "Booru 标签",
    "Booru-like tag list":    "类 Booru 标签",
    "Art Critic":             "艺术评论",
    "Product Listing":        "商品文案",
    "Social Media Post":      "社媒文案",
}

# ── 模型列表（带视觉标色）────────────────────────────────────────────────────
def _list_ollama_models():
    if oc and oc.is_alive():
        return oc.list_models()
    return ["（未检测到 Ollama）"]

def _is_vision_name(name: str) -> bool:
    if oc:
        return oc._is_vision_model_name(name)
    return False

class _ModelCombo(QComboBox):
    def _colorize_items(self):
        for i in range(self.count()):
            name = self.itemText(i)
            color = "#22c55e" if _is_vision_name(name) else "#ef4444"
            self.setItemData(i, QBrush(QColor(color)), Qt.ForegroundRole)

    def showPopup(self):
        self._colorize_items()
        super().showPopup()

# ── Worker ───────────────────────────────────────────────────────────────────
class _Worker(QThread):
    chunk = pyqtSignal(str)   # 流式每片
    done  = pyqtSignal(str)   # 完整结果
    fail  = pyqtSignal(str)

    def __init__(self, model: str, mode: str, image_path: str = None,
                 force_vision: bool = False):
        super().__init__()
        self.model       = model
        self.mode        = mode
        self.image_path  = image_path
        self.force_vision = force_vision

    def _build_prompt(self) -> tuple[str, str]:
        mode   = (self.mode or "").strip()
        length = "medium-length"
        sys_p  = (
            "Reply in English only. The task is strictly SFW (safe for work). "
            "Do not produce sexual/explicit content or sexualize people; "
            "use neutral, age-appropriate terms. Return only the requested result."
        )
        prompts = {
            "Descriptive":
                f"Write a {length} descriptive caption for this image in a formal tone.",
            "Descriptive (Informal)":
                f"Write a {length} descriptive caption for this image in a casual tone.",
            "Training Prompt":
                f"Write a {length} stable diffusion prompt for this image.",
            "MidJourney":
                f"Write a {length} MidJourney prompt for this image.",
            "Booru tag list":
                f"Write a {length} list of Booru tags for this image.",
            "Booru-like tag list":
                f"Write a {length} list of Booru-like tags for this image.",
            "Art Critic":
                f"Analyze this image like an art critic would, focusing on composition, "
                f"style, symbolism, color, light, and movement. Keep it {length}.",
            "Product Listing":
                f"Write a {length} caption for this image as though it were a product listing.",
            "Social Media Post":
                f"Write a {length} caption for this image as if it were being used for a social media post.",
        }
        user_p = prompts.get(mode) or prompts["Descriptive"]
        if mode in ("Booru tag list", "Booru-like tag list"):
            user_p += (
                " Output as a single line of comma-separated tags. "
                "Use lowercase and underscores. Do not output JSON, arrays, ids, or scores."
            )
        elif mode == "Product Listing":
            user_p += " One sentence overview plus 4 bullet points starting with '- '."
        elif mode == "Social Media Post":
            user_p += " 1-2 sentences plus 5 relevant hashtags."
        return sys_p, user_p

    def _should_send_image(self) -> bool:
        if self.force_vision:
            return True
        if oc:
            return oc._is_vision_model_name(self.model)
        return False

    def run(self):
        try:
            if not oc or not oc.is_alive():
                raise RuntimeError("Ollama 服务未启动")
            if not oc.has_model(self.model):
                raise RuntimeError(f"未找到模型：{self.model}")

            sys_p, user_p = self._build_prompt()
            msgs = [{"role": "system", "content": sys_p}]
            user = {"role": "user", "content": user_p}

            # 附图（视觉模型 或 强制模式）
            if self.image_path and os.path.isfile(self.image_path) and self._should_send_image():
                with open(self.image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                user["images"] = [b64]

            msgs.append(user)

            # 流式接收
            full = []
            for piece in oc.stream_chat(self.model, msgs):
                if isinstance(piece, str) and piece:
                    full.append(piece)
                    self.chunk.emit(piece)
            result = "".join(full).strip()

            # 如果空且有图，用简单提示重试一次
            if not result and "images" in user:
                user["content"] = "Describe the image in English in one paragraph."
                full = []
                for piece in oc.stream_chat(self.model, msgs):
                    if isinstance(piece, str) and piece:
                        full.append(piece)
                        self.chunk.emit(piece)
                result = "".join(full).strip()

            self.done.emit(result)
        except Exception as e:
            self.fail.emit(str(e))

# ── 预览框 ───────────────────────────────────────────────────────────────────
class _Preview(QFrame):
    def __init__(self, on_set_image, on_choose=None, parent=None):
        super().__init__(parent)
        self._set_cb    = on_set_image
        self._choose_cb = on_choose
        self._path      = None

        self.setObjectName("RevPreview")
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#RevPreview{border:1px dashed #25345c;border-radius:8px;}")

        box = QVBoxLayout(self)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(8)

        self.img = QLabel("拖放图片到此，或点击【选择图片】")
        self.img.setAlignment(Qt.AlignCenter)
        self.img.setWordWrap(True)
        self.img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        box.addWidget(self.img, 1)
        box.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)
        bar.addStretch(1)
        self.name = QLabel("")
        self.name.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bar.addWidget(self.name, 0, Qt.AlignRight)
        box.addLayout(bar)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.isfile(p):
                self.set_image(p)
                break

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.setFixedHeight(self.width())
        if self._path and self.img.pixmap():
            self._scale_to_fit()

    def set_image(self, path: str):
        self._path = path
        self.name.setText(os.path.basename(path) if path else "")
        if path and os.path.exists(path):
            self.img.setText("")
            self.img.setPixmap(QPixmap(path))
            self._scale_to_fit()
        if self._set_cb:
            self._set_cb(path)

    def _scale_to_fit(self):
        if not (self.img.pixmap() and not self.img.pixmap().isNull()):
            return
        w = max(1, self.width() - 24)
        h = max(1, self.height() - 48)
        pm = self.img.pixmap().scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.img.setPixmap(pm)

# ── 主页面 ───────────────────────────────────────────────────────────────────
class PageRevPrompt(QWidget):
    def __init__(self):
        super().__init__()
        self.image_path = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 0, 12, 12)
        root.setSpacing(10)

        # ── 顶栏：选图 / 状态 / 刷新 / 强制视觉 / 模型下拉 / 生成 ──────────
        top = QHBoxLayout()
        root.addLayout(top)

        self.btn_pick = QPushButton("选择图片")
        self.btn_pick.clicked.connect(self._pick)
        top.addWidget(self.btn_pick)

        self.status = QLabel("🟢 就绪")
        top.addWidget(self.status, 1)

        self.btn_refresh = QPushButton("刷新模型")
        self.btn_refresh.setToolTip("重新从 Ollama 获取模型列表")
        self.btn_refresh.clicked.connect(self._refresh_models)
        top.addWidget(self.btn_refresh)

        self.chk_force_vision = QCheckBox("强制发送图片")
        self.chk_force_vision.setToolTip(
            "勾选后，无论模型名称是否被识别为视觉模型，\n"
            "都会把图片附加在请求中发送给 Ollama。\n"
            "适用于名字不规范但实际支持视觉的模型。"
        )
        top.addWidget(self.chk_force_vision)

        self.model = _ModelCombo()
        self.model.setEditable(False)
        self.model.setFixedWidth(240)
        self.model.addItems(_list_ollama_models())
        self.model._colorize_items()
        top.addWidget(self.model)

        self.btn_run = QPushButton("生成提示词")
        self.btn_run.clicked.connect(self._run)
        top.addWidget(self.btn_run)

        # ── 中间：左列（预览 + 图片信息）/ 右列（模式 + 输出框）──────────────
        mid = QHBoxLayout()
        root.addLayout(mid, 1)
        mid.setSpacing(16)

        # 左列
        left_col = QVBoxLayout()
        left_col.setAlignment(Qt.AlignTop)
        mid.addLayout(left_col, 1)

        self.preview = _Preview(self._set_image, on_choose=self._pick)
        left_col.addWidget(self.preview)

        self.grp_info = QGroupBox("图片信息")
        self.grp_info.setObjectName("RevImageInfo")
        self.grp_info.setProperty("titleVariant", "accent")
        self.grp_info.setMinimumHeight(140)
        info_form = QFormLayout(self.grp_info)
        info_form.setContentsMargins(12, 8, 12, 8)
        self.info_name = QLabel("—")
        self.info_size = QLabel("—")
        self.info_dim  = QLabel("—")
        self.info_fmt  = QLabel("—")
        self.info_path = QLabel("—")
        self.info_path.setWordWrap(True)
        info_form.addRow("文件名：", self.info_name)
        info_form.addRow("大小：",   self.info_size)
        info_form.addRow("尺寸：",   self.info_dim)
        info_form.addRow("格式：",   self.info_fmt)
        info_form.addRow("路径：",   self.info_path)
        left_col.addWidget(self.grp_info)

        # 右列
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignTop)
        mid.addLayout(right, 1)

        # 模式选择
        self._mode_group   = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_buttons = []
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for i, key in enumerate(JOY_MODE_LIST):
            text = f"{key}（{MODE_CN.get(key, '')}）"
            rb = QRadioButton(text)
            rb.setProperty("mode_key", key)
            if i == 0:
                rb.setChecked(True)
            self._mode_group.addButton(rb)
            self._mode_buttons.append(rb)
            grid.addWidget(rb, i // 2, i % 2)
        grp_modes = QGroupBox("模式选择")
        grp_modes.setObjectName("RevModeBox")
        grp_box = QVBoxLayout(grp_modes)
        grp_box.setContentsMargins(12, 8, 12, 8)
        grp_box.addLayout(grid)
        right.addWidget(grp_modes)

        # 输出：英文框（带复制按钮）
        row_en = QHBoxLayout()
        self.en_label = QLabel("生成结果（英文）")
        row_en.addWidget(self.en_label)
        row_en.addStretch(1)
        self.btn_copy = QPushButton("复制")
        self.btn_copy.setFixedWidth(64)
        self.btn_copy.clicked.connect(self._copy_result)
        row_en.addWidget(self.btn_copy)
        right.addLayout(row_en)

        self.en = QTextEdit()
        self.en.setReadOnly(False)
        self.en.setPlaceholderText("生成的提示词将显示在这里…")
        right.addWidget(self.en, 1)

    # ── 选图 ─────────────────────────────────────────────────────────────────
    def _pick(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff)"
        )
        if p:
            self.preview.set_image(p)

    def _set_image(self, p):
        self.image_path = p if (p and os.path.isfile(p)) else None
        self.status.setText("🟡 图片已载入，选择模式后点【生成提示词】")
        self._update_image_info(self.image_path)

    # ── 刷新模型列表 ─────────────────────────────────────────────────────────
    def _refresh_models(self):
        self.status.setText("🟡 正在获取模型列表…")
        self.btn_refresh.setEnabled(False)
        models = _list_ollama_models()
        self.model.clear()
        self.model.addItems(models)
        self.model._colorize_items()
        self.btn_refresh.setEnabled(True)
        if "（未检测到 Ollama）" in models:
            self.status.setText("⚠️ 未检测到 Ollama 服务")
        else:
            self.status.setText(f"🟢 已加载 {len(models)} 个模型（绿=视觉 / 红=文本）")

    # ── 图片信息 ──────────────────────────────────────────────────────────────
    def _fmt_size(self, n: int) -> str:
        f = float(n or 0)
        for u in ("B", "KB", "MB", "GB"):
            if f < 1024.0:
                return f"{f:.2f} {u}" if u != "B" else f"{int(f)} {u}"
            f /= 1024.0
        return f"{f:.2f} TB"

    def _update_image_info(self, path: str):
        if not path or not os.path.isfile(path):
            for lbl in (self.info_name, self.info_size, self.info_dim,
                        self.info_fmt, self.info_path):
                lbl.setText("—")
            return
        self.info_name.setText(os.path.basename(path))
        try:
            self.info_size.setText(self._fmt_size(os.path.getsize(path)))
        except Exception:
            self.info_size.setText("—")
        self.info_path.setText(path)
        w = h = 0
        fmt = "—"
        try:
            reader = QImageReader(path)
            sz = reader.size()
            w, h = sz.width(), sz.height()
            raw = reader.format()
            if raw:
                fmt = (bytes(raw).decode("utf-8", errors="ignore")
                       if isinstance(raw, (bytes, bytearray)) else str(raw)).upper()
        except Exception:
            pass
        if w <= 0 or h <= 0:
            try:
                pm = QPixmap(path)
                w, h = pm.width(), pm.height()
            except Exception:
                pass
        self.info_dim.setText(f"{w} × {h}" if (w and h) else "—")
        self.info_fmt.setText(fmt)

    # ── 生成 ─────────────────────────────────────────────────────────────────
    def _run(self):
        model = self.model.currentText().strip()
        if not model or "未检测到" in model:
            self.status.setText("⚠️ 未检测到 Ollama 或模型")
            return

        btn = self._mode_group.checkedButton()
        mode_name = JOY_MODE_LIST[0]
        if btn is not None:
            key = btn.property("mode_key")
            if isinstance(key, str) and key.strip():
                mode_name = key.strip()

        force = self.chk_force_vision.isChecked()

        # 提示用户当前图片是否会被附加
        if self.image_path:
            will_send = force or (oc and oc._is_vision_model_name(model))
            if will_send:
                self.status.setText(f"🟡 生成中（附图）…")
            else:
                self.status.setText(
                    "🟡 生成中（纯文本，模型未识别为视觉模型）…\n"
                    "如需附图，请勾选「强制发送图片」"
                )
        else:
            self.status.setText("🟡 生成中（未选图，仅文本模式）…")

        self.en.clear()
        self.btn_run.setEnabled(False)
        self.btn_refresh.setEnabled(False)

        self.worker = _Worker(
            model=model,
            mode=mode_name,
            image_path=self.image_path,
            force_vision=force,
        )
        self.worker.chunk.connect(self._on_chunk)
        self.worker.done.connect(self._on_done)
        self.worker.fail.connect(self._on_fail)
        self.worker.start()

    def _on_chunk(self, piece: str):
        # 流式追加到文本框
        self.en.moveCursor(self.en.textCursor().End)
        self.en.insertPlainText(piece)
        self.en.moveCursor(self.en.textCursor().End)

    def _on_done(self, result: str):
        if not result.strip():
            self.status.setText("⚠️ 模型返回空结果（可重试，或换模式/模型）")
        else:
            self.status.setText("🟢 完成")
        self.btn_run.setEnabled(True)
        self.btn_refresh.setEnabled(True)

    def _on_fail(self, msg: str):
        self.status.setText(f"❌ 出错：{msg}")
        self.btn_run.setEnabled(True)
        self.btn_refresh.setEnabled(True)

    def _copy_result(self):
        text = self.en.toPlainText().strip()
        if text:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self.status.setText("✅ 已复制到剪贴板")
