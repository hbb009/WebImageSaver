# pages/page_ollama_tools.py  v9.6
# 三合一 Ollama 工具页：反推 / 打标 / 对话
# 顶栏：刷新图标(左一) → 模型下拉(左二,拉宽) → stretch → 状态灯+文字(右)
# Tab 样式扁平化，内部用分割线代替 GroupBox 嵌套

import os, glob, base64, re

_DDGS_OK = False
try:
    from ddgs import DDGS
    _DDGS_OK = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        _DDGS_OK = True
    except ImportError:
        pass



from PyQt5.QtCore  import Qt, QThread, pyqtSignal, QTimer, QSize, QEvent
from PyQt5.QtGui   import (QPixmap, QColor, QBrush, QImageReader,
                           QFont, QTextCursor, QFontMetrics)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QFormLayout, QFileDialog, QTextEdit, QComboBox,
    QGridLayout, QRadioButton, QButtonGroup, QSizePolicy, QSpacerItem,
    QCheckBox, QTabWidget, QListWidget, QListWidgetItem, QMessageBox,
    QProgressBar, QAbstractItemView, QApplication,
)

try:
    from utils import ollama_client as oc
except Exception:
    oc = None

from styles.page_ollama_tools import (
    TAB_QSS as _TAB_QSS,
    LIST_BATCH_QSS, LIST_CHAT_QSS,
    THINK_TITLE_QSS, THINK_BODY_QSS,
    SRC_TITLE_QSS, SRC_BODY_QSS, SRC_LINK_QSS,
    INPUT_TRANSPARENT_QSS, REV_PREVIEW_QSS,
    REV_INFO_QSS, REV_EN_QSS,
    TIME_LABEL_QSS, THINKING_DOT_QSS, THINKING_TEXT_QSS,
    chk_style as _chk_style_fn,
)

# ── Tab + 顶栏 QSS（内联，不污染全局）────────────────────────────────────────


def _make_hline():
    f = QFrame()
    f.setObjectName("SectionLine")
    f.setFrameShape(QFrame.HLine)
    return f


# ═══════════════════════════════════════════════════════════════════
#  共享工具
# ═══════════════════════════════════════════════════════════════════

def _list_models():
    if oc and oc.is_alive():
        return oc.list_models()
    return ["（未检测到 Ollama）"]

def _is_vision(name: str) -> bool:
    return oc._is_vision_model_name(name) if oc else False

class _ModelCombo(QComboBox):
    def _colorize(self):
        for i in range(self.count()):
            n = self.itemText(i)
            self.setItemData(i, QBrush(QColor("#22c55e" if _is_vision(n) else "#ef4444")),
                             Qt.ForegroundRole)
    def showPopup(self):
        self._colorize()
        super().showPopup()


# ═══════════════════════════════════════════════════════════════════
#  子页：反推提示词
# ═══════════════════════════════════════════════════════════════════

JOY_MODE_LIST = [
    "Descriptive", "Descriptive (Informal)", "Training Prompt", "MidJourney",
    "Booru tag list", "Booru-like tag list", "Art Critic", "Product Listing", "Social Media Post",
]
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


class _RevWorker(QThread):
    chunk = pyqtSignal(str)
    done  = pyqtSignal(str)
    fail  = pyqtSignal(str)

    def __init__(self, model, mode, image_path=None, force_vision=False):
        super().__init__()
        self.model = model; self.mode = mode
        self.image_path = image_path; self.force_vision = force_vision

    def _build_prompt(self):
        mode = (self.mode or "").strip()
        L = "medium-length"
        sys_p = ("Reply in English only. SFW only. Return only the requested result.")
        prompts = {
            "Descriptive":            f"Write a {L} descriptive caption for this image in a formal tone.",
            "Descriptive (Informal)": f"Write a {L} descriptive caption for this image in a casual tone.",
            "Training Prompt":        f"Write a {L} stable diffusion prompt for this image.",
            "MidJourney":             f"Write a {L} MidJourney prompt for this image.",
            "Booru tag list":         f"Write a {L} list of Booru tags for this image.",
            "Booru-like tag list":    f"Write a {L} list of Booru-like tags for this image.",
            "Art Critic":             f"Analyze this image like an art critic. Focus on composition, style, color, light. Keep it {L}.",
            "Product Listing":        f"Write a {L} caption for this image as a product listing.",
            "Social Media Post":      f"Write a {L} caption for this image as a social media post.",
        }
        user_p = prompts.get(mode) or prompts["Descriptive"]
        if mode in ("Booru tag list", "Booru-like tag list"):
            user_p += " Output as a single line of comma-separated tags. Use lowercase and underscores."
        elif mode == "Product Listing":
            user_p += " One sentence overview plus 4 bullet points starting with '- '."
        elif mode == "Social Media Post":
            user_p += " 1-2 sentences plus 5 relevant hashtags."
        return sys_p, user_p

    def _should_send_image(self):
        return self.force_vision or (oc and oc._is_vision_model_name(self.model))

    def run(self):
        try:
            if not oc or not oc.is_alive(): raise RuntimeError("Ollama 服务未启动")
            if not oc.has_model(self.model): raise RuntimeError(f"未找到模型：{self.model}")
            sys_p, user_p = self._build_prompt()
            msgs = [{"role": "system", "content": sys_p}]
            user = {"role": "user", "content": user_p}
            if self.image_path and os.path.isfile(self.image_path) and self._should_send_image():
                with open(self.image_path, "rb") as f:
                    user["images"] = [base64.b64encode(f.read()).decode()]
            msgs.append(user)
            full = []
            for piece in oc.stream_chat(self.model, msgs):
                if isinstance(piece, str) and piece:
                    full.append(piece); self.chunk.emit(piece)
            result = "".join(full).strip()
            if not result and "images" in user:
                user["content"] = "Describe the image in English in one paragraph."
                full = []
                for piece in oc.stream_chat(self.model, msgs):
                    if isinstance(piece, str) and piece:
                        full.append(piece); self.chunk.emit(piece)
                result = "".join(full).strip()
            self.done.emit(result)
        except Exception as e:
            self.fail.emit(str(e))


class _Preview(QFrame):
    def __init__(self, on_set_image, parent=None):
        super().__init__(parent)
        self._set_cb = on_set_image; self._path = None
        self.setObjectName("RevPreview")
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(REV_PREVIEW_QSS)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        box = QVBoxLayout(self)
        box.setContentsMargins(8, 8, 8, 8)
        self.img = QLabel("拖放图片到此，或点击【选择图片】")
        self.img.setAlignment(Qt.AlignCenter)
        self.img.setWordWrap(True)
        self.img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        box.addWidget(self.img, 1)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.isfile(p): self.set_image(p); break

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._path and self.img.pixmap(): self._scale()

    def set_image(self, path):
        self._path = path
        if path and os.path.exists(path):
            self.img.setText("")
            self.img.setPixmap(QPixmap(path))
            self._scale()
        if self._set_cb: self._set_cb(path)

    def _scale(self):
        if not (self.img.pixmap() and not self.img.pixmap().isNull()): return
        pm = self.img.pixmap().scaled(
            max(1, self.width() - 16), max(1, self.height() - 16),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.img.setPixmap(pm)


class TabRevPrompt(QWidget):
    status_msg = pyqtSignal(str)

    def __init__(self, get_model_fn, parent=None):
        super().__init__(parent)
        self._get_model = get_model_fn
        self.image_path = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 10, 8, 4)
        root.setSpacing(8)

        # ── 工具栏：选图 / 强制视觉 / 生成 ──────────────────────────────────
        top = QHBoxLayout()
        self.btn_pick = QPushButton("选择图片")
        self.btn_pick.clicked.connect(self._pick)
        top.addWidget(self.btn_pick)

        self.chk_force = QCheckBox("强制发送图片")
        self.chk_force.setToolTip("勾选后无论模型名称是否视觉模型都附图发送")
        top.addWidget(self.chk_force)
        top.addStretch(1)

        self.btn_run = QPushButton("生成提示词")
        self.btn_run.clicked.connect(self._run)
        top.addWidget(self.btn_run)
        root.addLayout(top)

        root.addWidget(_make_hline())

        # ── 主体：左（预览+信息） / 右（模式+输出） ──────────────────────────
        mid = QHBoxLayout()
        mid.setSpacing(16)
        root.addLayout(mid, 1)

        # 左列：预览区撑满，信息区贴底
        left = QVBoxLayout()
        left.setSpacing(6)
        left.setContentsMargins(0, 0, 0, 0)
        mid.addLayout(left, 1)

        self.preview = _Preview(self._set_image)
        left.addWidget(self.preview, 1)   # stretch=1 撑满剩余高度

        # 图片信息区固定在底部
        lbl_info = QLabel("图片信息")
        lbl_info.setStyleSheet(REV_INFO_QSS)
        left.addWidget(lbl_info, 0)
        left.addWidget(_make_hline(), 0)

        info_form = QFormLayout()
        info_form.setContentsMargins(4, 4, 4, 4)
        info_form.setSpacing(4)
        self.info_name = QLabel("—"); self.info_size = QLabel("—")
        self.info_dim  = QLabel("—"); self.info_fmt  = QLabel("—")
        self.info_path = QLabel("—"); self.info_path.setWordWrap(True)
        for label, w in [("文件名：", self.info_name), ("大小：", self.info_size),
                         ("尺寸：",   self.info_dim),  ("格式：", self.info_fmt),
                         ("路径：",   self.info_path)]:
            info_form.addRow(label, w)
        left.addLayout(info_form)
        left.addStretch(0)

        # 右列
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignTop)
        right.setSpacing(8)
        mid.addLayout(right, 1)

        lbl_mode = QLabel("输出模式")
        lbl_mode.setStyleSheet(REV_INFO_QSS)
        right.addWidget(lbl_mode)
        right.addWidget(_make_hline())

        self._mode_group   = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_buttons = []
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for i, key in enumerate(JOY_MODE_LIST):
            rb = QRadioButton(f"{key}（{MODE_CN.get(key, '')}）")
            rb.setProperty("mode_key", key)
            if i == 0: rb.setChecked(True)
            self._mode_group.addButton(rb)
            self._mode_buttons.append(rb)
            grid.addWidget(rb, i // 2, i % 2)
        right.addLayout(grid)

        right.addWidget(_make_hline())

        row_out = QHBoxLayout()
        row_out.addWidget(QLabel("生成结果（英文）"))
        row_out.addStretch(1)
        self.btn_copy = QPushButton("复制")
        self.btn_copy.setFixedWidth(60)
        self.btn_copy.clicked.connect(self._copy)
        row_out.addWidget(self.btn_copy)
        right.addLayout(row_out)

        self.en = QTextEdit()
        self.en.setPlaceholderText("生成的提示词将显示在这里…")
        self.en.setStyleSheet(REV_EN_QSS)
        right.addWidget(self.en, 1)

    def _pick(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff)")
        if p: self.preview.set_image(p)

    def _set_image(self, p):
        self.image_path = p if (p and os.path.isfile(p)) else None
        self.status_msg.emit("🟡 图片已载入，选择模式后点【生成提示词】")
        self._update_info(self.image_path)

    def _fmt_size(self, n):
        f = float(n or 0)
        for u in ("B","KB","MB","GB"):
            if f < 1024: return f"{f:.2f} {u}" if u!="B" else f"{int(f)} B"
            f /= 1024
        return f"{f:.2f} TB"

    def _update_info(self, path):
        empty = not path or not os.path.isfile(path)
        if empty:
            for l in (self.info_name,self.info_size,self.info_dim,self.info_fmt,self.info_path):
                l.setText("—")
            return
        self.info_name.setText(os.path.basename(path))
        try: self.info_size.setText(self._fmt_size(os.path.getsize(path)))
        except: self.info_size.setText("—")
        self.info_path.setText(path)
        w = h = 0; fmt = "—"
        try:
            reader = QImageReader(path); sz = reader.size()
            w, h = sz.width(), sz.height()
            raw = reader.format()
            if raw: fmt = (bytes(raw).decode("utf-8","ignore") if isinstance(raw,(bytes,bytearray)) else str(raw)).upper()
        except: pass
        if w <= 0 or h <= 0:
            try: pm = QPixmap(path); w,h = pm.width(),pm.height()
            except: pass
        self.info_dim.setText(f"{w} × {h}" if (w and h) else "—")
        self.info_fmt.setText(fmt)

    def _run(self):
        model = self._get_model()
        if not model or "未检测到" in model:
            self.status_msg.emit("⚠️ 未检测到 Ollama 或模型"); return
        btn = self._mode_group.checkedButton()
        mode_name = JOY_MODE_LIST[0]
        if btn:
            k = btn.property("mode_key")
            if isinstance(k, str) and k.strip(): mode_name = k.strip()
        force = self.chk_force.isChecked()
        if self.image_path:
            will_send = force or (oc and oc._is_vision_model_name(model))
            self.status_msg.emit("🟡 生成中（附图）…" if will_send
                                 else "🟡 生成中（纯文本，如需附图请勾选「强制发送图片」）…")
        else:
            self.status_msg.emit("🟡 生成中（未选图）…")
        self.en.clear()
        self.btn_run.setEnabled(False)
        self.worker = _RevWorker(model=model, mode=mode_name,
                                 image_path=self.image_path, force_vision=force)
        self.worker.chunk.connect(lambda p: (self.en.moveCursor(self.en.textCursor().End),
                                             self.en.insertPlainText(p),
                                             self.en.moveCursor(self.en.textCursor().End)))
        self.worker.done.connect(lambda r: (self.status_msg.emit("🟢 完成" if r.strip() else "⚠️ 返回空结果"),
                                            self.btn_run.setEnabled(True)))
        self.worker.fail.connect(lambda m: (self.status_msg.emit(f"❌ {m}"),
                                            self.btn_run.setEnabled(True)))
        self.worker.start()

    def _copy(self):
        t = self.en.toPlainText().strip()
        if t:
            QApplication.clipboard().setText(t)
            self.status_msg.emit("✅ 已复制到剪贴板")


# ═══════════════════════════════════════════════════════════════════
#  子页：批量打标
# ═══════════════════════════════════════════════════════════════════

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
        "Describe this image in English concisely, covering subject, style, color tone, and composition.",
    "中英双语描述":
        "Describe this image in both Chinese and English. Format: 中文描述 / English description.",
}


class _TagWorker(QThread):
    progress = pyqtSignal(int, int, str)
    done     = pyqtSignal(int, int)

    def __init__(self, folder, model, prompt_tpl, overwrite):
        super().__init__()
        self.folder = folder; self.model = model
        self.prompt_tpl = prompt_tpl; self.overwrite = overwrite
        self._stop = False

    def stop(self): self._stop = True

    def run(self):
        exts = ("*.png","*.jpg","*.jpeg","*.webp","*.bmp")
        files = []
        for e in exts: files += glob.glob(os.path.join(self.folder, e))
        total = len(files); ok = 0
        for idx, img_path in enumerate(files, 1):
            if self._stop: break
            name = os.path.basename(img_path)
            caption = os.path.splitext(img_path)[0] + ".txt"
            self.progress.emit(idx, total, name)
            if (not self.overwrite) and os.path.exists(caption):
                ok += 1; continue
            content = self._tag(img_path)
            if content is not None:
                try:
                    with open(caption, "w", encoding="utf-8") as f: f.write(content)
                    ok += 1
                except: pass
        self.done.emit(ok, total)

    def _tag(self, img_path):
        if not oc or not oc.is_alive(): return None
        try:
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            msgs = [{"role":"user","content":self.prompt_tpl,"images":[b64]}]
            parts = []
            for piece in oc.stream_chat(self.model, msgs):
                if isinstance(piece, str): parts.append(piece)
            return "".join(parts).strip() or None
        except: return None


class TabBatchTag(QWidget):
    status_msg = pyqtSignal(str)

    def __init__(self, get_model_fn, parent=None):
        super().__init__(parent)
        self._get_model = get_model_fn
        self.folder = None; self.worker = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 10, 8, 4)
        lay.setSpacing(8)

        # 文件夹行
        row_f = QHBoxLayout()
        row_f.addWidget(QLabel("图片文件夹："))
        self.path_lab = QLabel("未选择")
        self.path_lab.setWordWrap(True)
        self.path_lab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row_f.addWidget(self.path_lab, 1)
        self.btn_pick = QPushButton("选择文件夹")
        self.btn_pick.clicked.connect(self._pick)
        row_f.addWidget(self.btn_pick)
        lay.addLayout(row_f)

        lay.addWidget(_make_hline())

        # 提示词模板行
        row_p = QHBoxLayout()
        row_p.addWidget(QLabel("提示词模板："))
        self.prompt_combo = QComboBox()
        self.prompt_combo.setMinimumWidth(260)
        for k in PROMPT_TEMPLATES: self.prompt_combo.addItem(k)
        row_p.addWidget(self.prompt_combo)
        row_p.addStretch(1)
        lay.addLayout(row_p)

        # 选项行
        row_o = QHBoxLayout()
        self.over = QCheckBox("覆盖已存在的 .txt")
        row_o.addWidget(self.over)
        row_o.addStretch(1)
        lay.addLayout(row_o)

        lay.addWidget(_make_hline())

        # 进度
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        lay.addWidget(self.progress_label)

        # 文件列表
        self.list = QListWidget()
        self.list.setStyleSheet(LIST_BATCH_QSS)
        lay.addWidget(self.list, 1)

        lay.addWidget(_make_hline())

        # 按钮行
        row_btn = QHBoxLayout()
        row_btn.addStretch(1)
        self.btn_go   = QPushButton("开始打标")
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        row_btn.addWidget(self.btn_go)
        row_btn.addWidget(self.btn_stop)
        self.btn_go.clicked.connect(self._run)
        self.btn_stop.clicked.connect(self._stop)
        lay.addLayout(row_btn)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "选择图片文件夹", "")
        if d:
            self.folder = d; self.path_lab.setText(d); self._fill_list()

    def _fill_list(self):
        self.list.clear()
        if not self.folder: return
        for e in ("*.png","*.jpg","*.jpeg","*.webp","*.bmp"):
            for p in glob.glob(os.path.join(self.folder, e)):
                self.list.addItem(os.path.basename(p))

    def _run(self):
        if not self.folder:
            QMessageBox.warning(self, "提示", "请先选择文件夹"); return
        model = self._get_model()
        if not model or "未检测到" in model:
            QMessageBox.warning(self, "提示", "未检测到 Ollama 服务或模型"); return
        if not (oc and oc.is_alive()):
            QMessageBox.warning(self, "提示", "Ollama 服务未运行"); return
        prompt_key = self.prompt_combo.currentText()
        prompt_tpl = PROMPT_TEMPLATES.get(prompt_key, list(PROMPT_TEMPLATES.values())[0])
        self.btn_go.setEnabled(False); self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0); self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.status_msg.emit("🟡 正在批量打标…")
        self.worker = _TagWorker(folder=self.folder, model=model,
                                 prompt_tpl=prompt_tpl, overwrite=self.over.isChecked())
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.start()

    def _stop(self):
        if self.worker: self.worker.stop()
        self.btn_stop.setEnabled(False); self.status_msg.emit("🟠 已停止")

    def _on_progress(self, cur, tot, name):
        self.progress_bar.setMaximum(tot); self.progress_bar.setValue(cur)
        self.progress_label.setText(f"正在处理（{cur}/{tot}）：{name}")

    def _on_done(self, ok, total):
        self.progress_bar.setVisible(False); self.progress_label.setVisible(False)
        self.btn_go.setEnabled(True); self.btn_stop.setEnabled(False)
        self.status_msg.emit(f"🟢 完成：{ok}/{total} 张")
        QMessageBox.information(self, "完成", f"共 {total} 张，成功生成 {ok} 个 .txt")


# ═══════════════════════════════════════════════════════════════════
#  子页：Ollama 对话助理
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
#  联网搜索工具函数
# ═══════════════════════════════════════════════════════════════════

# 触发联网的关键词（用户问题中含有这些词时自动联网）
_WEB_KEYWORDS = [
    "上网", "联网", "搜索", "搜一下", "查一下", "查查", "查询",
    "最新", "最近", "现在", "今天", "今年", "2024", "2025", "2026",
    "新闻", "实时", "当前", "目前", "帮我找", "查资料", "网上",
    "有哪些新", "最火", "最热", "热门", "排行", "榜单",
]

def _should_auto_search(text: str) -> bool:
    """判断用户问题是否应自动触发联网"""
    return any(k in text for k in _WEB_KEYWORDS)


def _web_search(query: str, max_results: int = 5) -> tuple[str, list]:
    """
    用 DuckDuckGo 搜索，返回 (结果文本, 来源列表)
    失败时返回 ("", []) 保证 web_ctx 为假值，不污染 prompt
    """
    if not _DDGS_OK:
        return "", []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "", []
        lines, sources = [], []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body  = r.get("body",  "")
            href  = r.get("href",  "")
            lines.append(f"[{i}] {title}\n{body}\n来源：{href}")
            sources.append({"title": title, "href": href})
        return "\n\n".join(lines), sources
    except Exception:
        return "", []


# ═══════════════════════════════════════════════════════════════════
#  对话 Worker（支持联网 + 深度思考）
# ═══════════════════════════════════════════════════════════════════

class _ChatWorker(QThread):
    chunk     = pyqtSignal(str)
    error     = pyqtSignal(str)
    status    = pyqtSignal(str)
    sources   = pyqtSignal(list)   # 搜索来源列表，回答结束后发给 UI

    def __init__(self, model, messages, web_search=False, deep_think=False):
        super().__init__()
        self.model      = model
        self.messages   = list(messages)
        self.web_search = web_search
        self.deep_think = deep_think

    def run(self):
        try:
            if not oc or not oc.is_alive():
                raise RuntimeError("Ollama 服务未启动")

            last_user = next(
                (m["content"] for m in reversed(self.messages) if m["role"] == "user"),
                ""
            )

            # ── Step 1：深度思考 ──────────────────────────────────────────
            optimized_query = last_user
            think_summary   = ""
            if self.deep_think:
                self.status.emit("🧠 深度思考：分析问题中…")
                think_msgs = [
                    {
                        "role": "system",
                        "content": (
                            "你是一位专业的问题分析专家。"
                            "请分析用户问题的核心意图，列出回答该问题需要考虑的关键要点（3-5条），"
                            "然后在最后一行输出一个更完整清晰的搜索查询词（以[查询词:]开头）。"
                            "全程使用中文。不要直接回答问题本身。"
                        ),
                    },
                    {"role": "user", "content": last_user},
                ]
                think_parts = []
                for piece in oc.stream_chat(self.model, think_msgs):
                    if piece:
                        think_parts.append(piece)
                raw_think = "".join(think_parts).strip()

                query_line = ""
                for line in reversed(raw_think.splitlines()):
                    line = line.strip()
                    if line.startswith("[查询词:]") or line.startswith("[查询词：]"):
                        query_line = line.split("]", 1)[-1].strip()
                        break
                optimized_query = query_line if query_line else last_user
                think_summary   = raw_think
                self.status.emit(f"🧠 分析完成，查询词：{optimized_query[:50]}")
                if think_summary:
                    self.chunk.emit(f"\x00THINK\x00{think_summary}\x00/THINK\x00")

            # ── Step 2：判断是否联网（开关开启 OR 关键词自动触发）──────
            do_search = self.web_search or (
                _DDGS_OK and _should_auto_search(last_user)
            )
            web_ctx  = ""
            src_list = []
            if do_search:
                if not _DDGS_OK:
                    self.status.emit("⚠️ duckduckgo-search 未安装，跳过联网")
                else:
                    hint = "（手动开启）" if self.web_search else "（自动检测）"
                    self.status.emit(f"🌐 联网搜索中{hint}…")
                    web_ctx, src_list = _web_search(optimized_query)
                    if web_ctx:
                        self.status.emit(f"🌐 搜索完成（{len(src_list)} 条结果），生成回答中…")
                    else:
                        self.status.emit("⚠️ 搜索无结果，使用模型自身知识回答")

            # ── Step 3：组装 messages 并流式回答 ─────────────────────────
            final_messages = list(self.messages)

            if web_ctx:
                inject = (
                    "以下是联网搜索到的最新参考资料，请优先基于这些资料回答，"
                    "不要依赖训练数据中的旧知识：\n\n"
                    f"{web_ctx}\n\n"
                    f"---\n用户问题：{last_user}"
                )
                for i in range(len(final_messages) - 1, -1, -1):
                    if final_messages[i]["role"] == "user":
                        final_messages[i] = {"role": "user", "content": inject}
                        break

            if think_summary:
                injected = False
                for i, m in enumerate(final_messages):
                    if m["role"] == "system":
                        final_messages[i] = {
                            "role": "system",
                            "content": m["content"] + f"\n\n【背景分析】\n{think_summary}",
                        }
                        injected = True
                        break
                if not injected:
                    final_messages.insert(0, {
                        "role": "system",
                        "content": f"请用中文回答。\n\n【背景分析】\n{think_summary}",
                    })

            self.status.emit("🟡 生成回答中…")
            for piece in oc.stream_chat(self.model, final_messages):
                if piece:
                    self.chunk.emit(piece)

            # 回答完毕后发送来源列表
            if src_list:
                self.sources.emit(src_list)

        except Exception as e:
            self.error.emit(str(e))



def _chk_style(bg: str, border: str, text_color: str, bold: bool, size: int = 15) -> str:
    return _chk_style_fn(bg, border, text_color, bold, size)

class TabOllamaChat(QWidget):
    # status_msg 只用于右上角：仅界面操作类消息（开关切换、清空等）
    status_msg = pyqtSignal(str)

    def __init__(self, get_model_fn, parent=None):
        super().__init__(parent)
        self._get_model = get_model_fn
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._flush_render)
        self._last_rendered_len = 0
        self.chat_history  = []
        self.current_ai_label = None
        self.input_history = []
        self.history_index = -1
        self._buf = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 10, 8, 4)
        lay.setSpacing(6)

        # ── 时间戳行 ──────────────────────────────────────────────────
        self.time_label = QLabel()
        self.time_label.setStyleSheet(TIME_LABEL_QSS)
        self.time_label.setAlignment(Qt.AlignRight)
        lay.addWidget(self.time_label)
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._clock.start(1000)
        self._tick()

        lay.addWidget(_make_hline())

        # ── 功能开关栏：复选框样式 ────────────────────────────────────
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(16)

        self.chk_web = QCheckBox("联网搜索")
        self.chk_web.setStyleSheet(_chk_style("#1d4ed8", "#3b82f6", "#93c5fd", True, 15))
        self.chk_web.setToolTip("勾选后发送时自动联网搜索\n问题含[上网/搜索/最新]等词也会自动触发")
        self.chk_web.stateChanged.connect(self._on_web_changed)
        toggle_row.addWidget(self.chk_web)

        self.chk_think = QCheckBox("深度思考")
        self.chk_think.setStyleSheet(_chk_style("#6d28d9", "#a78bfa", "#c4b5fd", True, 15))
        self.chk_think.setToolTip("勾选后，模型先分析问题再作答，回答更有条理")
        self.chk_think.stateChanged.connect(self._on_think_changed)
        toggle_row.addWidget(self.chk_think)

        toggle_row.addStretch(1)
        lay.addLayout(toggle_row)

        lay.addWidget(_make_hline())

        # ── 对话气泡列表 ──────────────────────────────────────────────
        self.list = QListWidget()
        self.list.setMinimumHeight(260)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.setStyleSheet(LIST_CHAT_QSS)
        lay.addWidget(self.list, 1)

        line_px = QFontMetrics(self.list.font()).lineSpacing() + 2
        self._scroll_step = line_px
        sb = self.list.verticalScrollBar()
        sb.setSingleStep(line_px)
        sb.setPageStep(max(1, self.list.viewport().height() - line_px))
        self.list.viewport().installEventFilter(self)

        lay.addWidget(_make_hline())

        # ── 内部状态栏（AI过程提示，位于输入框上方）─────────────────
        status_row = QHBoxLayout()
        status_row.setContentsMargins(4, 2, 4, 2)
        status_row.setSpacing(6)
        self._inner_dot = QLabel("⚪")
        self._inner_dot.setFixedWidth(18)
        self._inner_dot.setAlignment(Qt.AlignCenter)
        self._inner_dot.setStyleSheet(THINKING_DOT_QSS)
        status_row.addWidget(self._inner_dot)
        self._inner_text = QLabel("就绪")
        self._inner_text.setStyleSheet(THINKING_TEXT_QSS)
        self._inner_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_row.addWidget(self._inner_text)
        lay.addLayout(status_row)

        # ── 输入框 ───────────────────────────────────────────────────
        lay.addWidget(QLabel("输入问题："))
        self.input = QTextEdit()
        self.input.setMinimumHeight(80)
        self.input.setMaximumHeight(160)
        self.input.setStyleSheet(INPUT_TRANSPARENT_QSS)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)

        # ── 按钮行 ───────────────────────────────────────────────────
        row = QHBoxLayout()
        row.addStretch()

        self.chk_enter = QCheckBox("回车发送")
        self.chk_enter.setChecked(True)   # 默认勾选
        self.chk_enter.setStyleSheet(_chk_style("#1d4ed8", "#3b82f6", "#93c5fd", False, 13))
        self.chk_enter.setToolTip("勾选：直接按 Enter 发送\n取消：按 Shift+Enter 换行，Enter 换行")
        row.addWidget(self.chk_enter)
        row.addSpacing(12)

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)
        self.up = QPushButton("上条指令")
        self.up.setEnabled(False)
        self.up.clicked.connect(self._load_prev)
        row.addWidget(self.up)
        self.clear_btn = QPushButton("清空对话")
        self.clear_btn.clicked.connect(self._clear)
        row.addWidget(self.clear_btn)
        row.addStretch()
        lay.addLayout(row)

    # ── 内部状态栏 ────────────────────────────────────────────────────
    def _set_inner(self, msg: str):
        dot_map = {
            "🟢": ("🟢", "#22c55e"),
            "🟡": ("🟡", "#f59e0b"),
            "⚪": ("⚪", "#5a6a8a"),
            "⚠️": ("🟠", "#f97316"),
            "❌": ("🔴", "#ef4444"),
            "✅": ("🟢", "#22c55e"),
            "🌐": ("🔵", "#3b82f6"),
            "🧠": ("🟣", "#a78bfa"),
        }
        dot, color = "⚪", "#5a6a8a"
        text = msg
        for prefix, (d, c) in dot_map.items():
            if msg.startswith(prefix):
                dot, color = d, c
                text = msg[len(prefix):].lstrip()
                break
        self._inner_dot.setText(dot)
        self._inner_text.setText(text)
        self._inner_text.setStyleSheet(f"color:{color}; font-size:12px;")

    def _tick(self):
        from datetime import datetime
        self.time_label.setText(datetime.now().strftime("%Y年%m月%d日  %A  %H:%M:%S"))

    # ── 开关回调（只通知右上角）─────────────────────────────────────
    def _on_web_changed(self, state):
        if state and not _DDGS_OK:
            self._set_inner("⚠️ 未安装 duckduckgo-search，请执行: pip install duckduckgo-search")
        else:
            self.status_msg.emit("🟢 联网搜索已开启" if state else "⚪ 联网搜索已关闭")

    def _on_think_changed(self, state):
        self.status_msg.emit("🟢 深度思考已开启" if state else "⚪ 深度思考已关闭")

    def _send(self):
        self._buf = ""; self._last_rendered_len = 0; self.current_ai_item = None
        if not oc.is_alive():
            self._set_inner("⚠️ 未运行 Ollama"); return
        model = self._get_model()
        if not model:
            self._set_inner("⚠️ 未选择模型"); return
        if not oc.has_model(model):
            self._set_inner(f"⚠️ 未发现模型 {model}"); return
        prompt = self.input.toPlainText().strip()
        if not prompt: return

        self.input_history.append(prompt); self.history_index = len(self.input_history)
        if not self.chat_history:
            self.chat_history.append({"role": "system", "content": "请用中文简洁回答。"})
        self.chat_history.append({"role": "user", "content": prompt})
        self._add_bubble(prompt, is_user=True)
        self.input.clear(); self.current_ai_label = None
        self.up.setEnabled(True)

        modes = []
        if self.chk_web.isChecked():             modes.append("联网")
        elif _DDGS_OK and _should_auto_search(prompt): modes.append("自动联网")
        if self.chk_think.isChecked():           modes.append("深度思考")
        hint = "（" + " + ".join(modes) + "）" if modes else ""
        self._set_inner(f"🟡 回答生成中{hint}…")

        self.worker = _ChatWorker(
            model, self.chat_history,
            web_search=self.chk_web.isChecked(),
            deep_think=self.chk_think.isChecked(),
        )
        self.worker.chunk.connect(self._on_chunk)
        self.worker.status.connect(self._set_inner)      # AI 进度 → 内部状态栏
        self.worker.sources.connect(self._show_sources)
        self.worker.error.connect(lambda m: self._set_inner("❌ " + m))
        self.worker.finished.connect(self._on_done)
        self.worker.start()

    def _on_chunk(self, piece):
        if piece.startswith("\x00THINK\x00") and piece.endswith("\x00/THINK\x00"):
            summary = piece[len("\x00THINK\x00"):-len("\x00/THINK\x00")]
            self._add_think_bubble(summary)
            return
        self._buf += piece
        if not self._render_timer.isActive(): self._render_timer.start(40)

    def _add_think_bubble(self, summary: str):
        w = QWidget()
        title = QLabel("🧠 深度思考过程（点击展开）")
        title.setStyleSheet(THINK_TITLE_QSS)
        title.setCursor(Qt.PointingHandCursor)
        body = QLabel(summary); body.setWordWrap(True)
        body.setFont(QFont("微软雅黑", 9))
        body.setStyleSheet(THINK_BODY_QSS + "border-radius:4px; margin-top:2px;")
        body.setVisible(False)
        body.setFixedWidth(int(self.list.viewport().width() * 0.88))
        item = QListWidgetItem()
        def _toggle(_=None):
            body.setVisible(not body.isVisible()); item.setSizeHint(w.sizeHint())
        title.mousePressEvent = _toggle
        vlay = QVBoxLayout(); vlay.setContentsMargins(0,0,0,0); vlay.setSpacing(2)
        vlay.addWidget(title); vlay.addWidget(body)
        outer = QHBoxLayout(); outer.setContentsMargins(20,1,20,4)
        outer.addLayout(vlay); outer.addStretch()
        w.setLayout(outer)
        item.setSizeHint(w.sizeHint()); item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(item); self.list.setItemWidget(item, w); self.list.scrollToBottom()

    def _add_bubble(self, text, is_user):
        w = QWidget(); lab = QLabel(text)
        lab.setWordWrap(True); lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lab.setFont(QFont("微软雅黑", 10))
        lab.setFixedWidth(int(self.list.viewport().width() * (0.70 if is_user else 0.88)))
        if is_user:
            lab.setObjectName("ChatBubbleUser")
            lab.setStyleSheet("QLabel#ChatBubbleUser{background:#0e1530;border:1px solid #2a3965;"
                              "border-radius:8px;padding:6px 10px;}")
        out = QHBoxLayout(); out.setContentsMargins(20,1,20,6)
        inner = QVBoxLayout(); inner.setContentsMargins(0,0,0,0); inner.addWidget(lab)
        if is_user: out.addStretch(); out.addLayout(inner)
        else:       out.addLayout(inner); out.addStretch()
        w.setLayout(out)
        item = QListWidgetItem(); item.setSizeHint(w.sizeHint())
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(item); self.list.setItemWidget(item, w)
        return lab, item

    def _clear(self):
        self.list.clear(); self.chat_history = []
        self.current_ai_label = self.current_ai_item = None
        self._buf = ""; self._last_rendered_len = 0
        self._set_inner("⚪ 对话已清空")
        self.status_msg.emit("⚪ 对话已清空")

    def _load_prev(self):
        if not self.input_history: return
        self.history_index = max(0, self.history_index - 1)
        self.input.setPlainText(self.input_history[self.history_index])
        self.input.moveCursor(QTextCursor.End)

    def _flush_render(self):
        filtered = re.sub(r"<\s*think\s*>.*?<\s*/\s*think\s*>", "", self._buf, flags=re.I|re.S)
        if self.current_ai_label is None:
            self.current_ai_label, self.current_ai_item = self._add_bubble(filtered, is_user=False)
            self._last_rendered_len = len(filtered)
        elif len(filtered) > self._last_rendered_len:
            self.current_ai_label.setText(filtered)
            container = self.list.itemWidget(self.current_ai_item)
            nh = container.sizeHint()
            if nh != self.current_ai_item.sizeHint(): self.current_ai_item.setSizeHint(nh)
            self._last_rendered_len = len(filtered)
        self.list.scrollToBottom()

    def _on_done(self):
        if not self._buf.endswith("\n"): self._buf += "\n"
        self._flush_render()
        sp = QListWidgetItem(); sp.setSizeHint(QSize(1,10))
        sp.setFlags(sp.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(sp); self.list.scrollToBottom()
        self._set_inner("🟢 回答完成")

    def _show_sources(self, src_list: list):
        if not src_list: return
        w = QWidget()
        title = QLabel(f"🔗 参考来源（{len(src_list)} 条，点击展开）")
        title.setStyleSheet(SRC_TITLE_QSS)
        title.setCursor(Qt.PointingHandCursor)
        body = QWidget()
        body_lay = QVBoxLayout(body); body_lay.setContentsMargins(4,4,4,4); body_lay.setSpacing(3)
        for i, s in enumerate(src_list, 1):
            lbl = QLabel(f'<a href="{s["href"]}" style="color:#60a5fa;">'
                         f'[{i}] {s["title"][:60]}{"…" if len(s["title"])>60 else ""}</a>')
            lbl.setOpenExternalLinks(True); lbl.setWordWrap(True)
            lbl.setFont(QFont("微软雅黑", 9))
            lbl.setStyleSheet(SRC_LINK_QSS)
            body_lay.addWidget(lbl)
        body.setStyleSheet(SRC_BODY_QSS)
        body.setFixedWidth(int(self.list.viewport().width() * 0.88))
        body.setVisible(False)
        item = QListWidgetItem()
        def _toggle(_=None):
            body.setVisible(not body.isVisible())
            item.setSizeHint(w.sizeHint()); self.list.scrollToBottom()
        title.mousePressEvent = _toggle
        vlay = QVBoxLayout(); vlay.setContentsMargins(0,0,0,0); vlay.setSpacing(2)
        vlay.addWidget(title); vlay.addWidget(body)
        outer = QHBoxLayout(); outer.setContentsMargins(20,1,20,6)
        outer.addLayout(vlay); outer.addStretch()
        w.setLayout(outer)
        item.setSizeHint(w.sizeHint()); item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(item); self.list.setItemWidget(item, w); self.list.scrollToBottom()

    def eventFilter(self, obj, event):
        if obj is self.list.viewport() and event.type() == QEvent.Wheel:
            delta = event.angleDelta().y()
            if delta:
                sb = self.list.verticalScrollBar()
                sb.setValue(sb.value() - (self._scroll_step if delta > 0 else -self._scroll_step))
                return True
        if obj is self.input and event.type() == QEvent.KeyPress:
            ke = event
            if ke.key() in (Qt.Key_Return, Qt.Key_Enter):
                if ke.modifiers() == Qt.NoModifier and self.chk_enter.isChecked():
                    # 回车发送模式：Enter 直接发送
                    self._send()
                    return True
                elif ke.modifiers() == Qt.ShiftModifier:
                    # Shift+Enter 始终换行（不拦截，交给 QTextEdit 默认处理）
                    pass
        return super().eventFilter(obj, event)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        sb = self.list.verticalScrollBar()
        sb.setPageStep(max(1, self.list.viewport().height() - getattr(self, "_scroll_step", 16)))


class _ModelListWorker(QThread):
    done = pyqtSignal(list)
    fail = pyqtSignal(str)
    def run(self):
        try: self.done.emit(oc.list_models() if oc else [])
        except Exception as e: self.fail.emit(str(e))


class PageOllamaTools(QWidget):
    def __init__(self):
        super().__init__()
        self._models_loaded = False
        self._list_worker   = None

        # 注入局部 QSS
        self.setStyleSheet(_TAB_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 12)
        root.setSpacing(6)

        # ── 共享顶栏：[🔄] [模型下拉──────────────] <stretch> [● 状态文字] ──
        top = QHBoxLayout()
        top.setSpacing(8)

        # 刷新图标按钮
        self.btn_refresh = QPushButton("↻")
        self.btn_refresh.setObjectName("BtnRefreshIcon")
        self.btn_refresh.setToolTip("重新从 Ollama 获取模型列表")
        self.btn_refresh.clicked.connect(self._refresh)
        top.addWidget(self.btn_refresh)

        # 模型下拉（尽量宽）
        self.model_combo = _ModelCombo()
        self.model_combo.setEnabled(False)
        self.model_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.model_combo.setMinimumWidth(280)
        top.addWidget(self.model_combo, 1)   # stretch=1 让它占满剩余

        top.addStretch(0)

        # 状态点 + 文字
        self.status_dot = QLabel("⚪")
        self.status_dot.setObjectName("StatusDot")
        top.addWidget(self.status_dot)

        self.status = QLabel("等待连接 Ollama…")
        self.status.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        top.addWidget(self.status)

        root.addLayout(top)

        # ── Tab ──────────────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setObjectName("OllamaTabWidget")
        root.addWidget(self.tabs, 1)

        def _get_model():
            return self.model_combo.currentText().strip()

        self.tab_rev   = TabRevPrompt(get_model_fn=_get_model)
        self.tab_batch = TabBatchTag(get_model_fn=_get_model)
        self.tab_chat  = TabOllamaChat(get_model_fn=_get_model)

        self.tabs.addTab(self.tab_rev,   "🖼  反推")
        self.tabs.addTab(self.tab_batch, "🏷  打标")
        self.tabs.addTab(self.tab_chat,  "💬  对话")

        # 子页状态 → 顶栏
        for tab in (self.tab_rev, self.tab_batch, self.tab_chat):
            tab.status_msg.connect(self._set_status)

    def _set_status(self, msg: str):
        """解析状态信息：emoji 前缀→点，其余→文字"""
        dot_map = {"🟢":"🟢", "🟡":"🟡", "⚪":"⚪", "⚠️":"🟠", "❌":"🔴", "✅":"🟢"}
        dot = "⚪"
        text = msg
        for prefix, d in dot_map.items():
            if msg.startswith(prefix):
                dot = d
                text = msg[len(prefix):].lstrip()
                break
        self.status_dot.setText(dot)
        self.status.setText(text)

    def _refresh(self):
        self._set_status("🟡 正在获取模型列表…")
        self.btn_refresh.setEnabled(False)
        self.model_combo.setEnabled(False)
        self._list_worker = _ModelListWorker()
        self._list_worker.done.connect(self._fill_models)
        self._list_worker.fail.connect(self._on_model_fail)
        self._list_worker.start()

    def _fill_models(self, models):
        self.model_combo.clear()
        if not models:
            self.model_combo.addItem("（未检测到 Ollama）")
            self._set_status("⚠️ 未检测到 Ollama 服务")
        else:
            self.model_combo.addItems(models)
            self.model_combo._colorize()
            self.model_combo.setEnabled(True)
            self._set_status(f"🟢 已加载 {len(models)} 个模型（绿=视觉 / 红=文本）")
        self._models_loaded = True
        self.btn_refresh.setEnabled(True)

    def _on_model_fail(self, msg):
        self._set_status(f"❌ 读取模型失败：{msg}")
        self.btn_refresh.setEnabled(True)

    def on_enter(self):
        if not self._models_loaded:
            self._refresh()
