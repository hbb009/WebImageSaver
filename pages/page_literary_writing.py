# pages/page_literary_writing.py  v5.0
# 本地大模型 · Skill 加载器
#   顶栏：刷新 / 模型下拉 / 状态
#   主体：左 70% 对话（回合制 + 附件 + 斜杠命令） + 右 30% 功能区（Skill 目录 + 日志 + 附件）
#
# v5 新增：
#   1) 斜杠命令 /clear（/reset /new 同义）——清空当前对话历史、释放记忆；输入框直接输入即可；
#      /help 查看命令。原“清空对话”按钮同样可用。
#   2) 对话改为“回合制”（一问一答成一回合），每回合可独立操作：
#      · 用户气泡：复制 | 修改（把问题载回输入框，改完重发；会移除该回合及其之后的内容）
#      · AI 气泡：复制 | 刷新（用新种子重生成该回答）| 删除（删除整回合，释放记忆）
#
# Skill 机制：Ollama 无 skill 系统；Skill = 注入系统上下文的一段指令。勾选启用，未勾不生效。

import os, re, sys, base64, shutil
from datetime import datetime

from PyQt5.QtCore  import Qt, QTimer, QSize, QEvent, pyqtSignal, QUrl
from PyQt5.QtGui   import (QColor, QBrush, QFont, QTextCursor, QFontMetrics,
                           QDesktopServices, QPixmap)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTextEdit, QComboBox, QSizePolicy, QCheckBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QApplication, QMessageBox, QFileDialog, QScrollArea,
)

try:
    from utils import ollama_client as oc
except Exception:
    oc = None

from pages.page_ollama_tools import (
    _ChatWorker, _ModelCombo, _ModelListWorker,
    _make_hline, _chk_style, _should_auto_search, _DDGS_OK,
)

from styles.style_all import (
    theme,
    fmt,
    tk,
    TAB_QSS as _BASE_QSS,
    LIST_CHAT_QSS,
    INPUT_TRANSPARENT_QSS,
    TIME_LABEL_QSS,
    THINKING_DOT_QSS,
    THINKING_TEXT_QSS,
    THINK_TITLE_QSS,
    THINK_BODY_QSS,
    SRC_TITLE_QSS,
    SRC_BODY_QSS,
    SRC_LINK_QSS,
    BUBBLE_USER_QSS,
)


def resource_path(*paths):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *paths)


SKILLS_DIR = os.path.abspath(resource_path("skills"))
DEFAULT_SYSTEM_PROMPT = "你是一个乐于助人、思路清晰的中文 AI 助手。请根据用户需求准确、简洁地作答。"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
ATTACH_TEXT_MAX = 40000
_READ_ENCODINGS = ("utf-8", "utf-8-sig", "gbk", "gb18030", "big5", "latin-1")


# ═══════════════════════════════════════════════════════════════════
#  局部样式
# ═══════════════════════════════════════════════════════════════════
PANEL_QSS = """
#FuncPanel {{ background:{bg}; border:1px solid {border_soft}; border-radius:10px; }}
#FuncPanelTitle {{ color:{sel_text}; font-size:14px; font-weight:bold; padding:2px 2px 6px 2px; }}
#PanelCard {{ background:{panel_2}; border:1px solid {border_2}; border-radius:8px; }}
#PanelSection {{ color:{text_mut}; font-size:12px; font-weight:bold; }}
#PanelHint {{ color:{text_faint}; font-size:11px; }}
#PathLabel {{ color:{text_dim}; font-size:11px; }}
#StatusKey {{ color:{text_faint}; font-size:12px; }}
#StatusVal {{ color:{text}; font-size:12px; }}
#SkillList {{ background:{panel_deep}; border:1px solid {border_2}; border-radius:6px; color:{text}; }}
#SkillList::item {{ padding:4px 6px; }}
#SkillList::item:selected {{ background:{sel_bg}; color:{sel_text}; }}
#SkillLog {{ background:{panel_deep}; border:1px solid {border_2}; border-radius:6px; color:{text_mut}; }}
#AttachScroll {{ background:{panel_deep}; border:1px solid {border_2}; border-radius:6px; }}
#AttachRow {{ background:{panel}; border:1px solid {border_2}; border-radius:6px; }}
#AttachChipText {{ color:{text_strong}; font-size:11px; padding:0 2px; }}
#SysNote {{ color:{text_faint}; font-size:11px; }}
QPushButton#PanelBtn {{ background:{panel}; color:{text_strong}; border:1px solid {border_2}; border-radius:6px; padding:5px 8px; font-size:12px; }}
QPushButton#PanelBtn:hover  {{ background:{panel_3}; }}
QPushButton#PanelBtn:pressed{{ background:{panel_deep}; }}
QPushButton#AddAttachBtn {{ background:{sel_bg}; color:{sel_text}; border:1px solid {ok}; border-radius:6px; padding:5px 8px; font-size:12px; }}
QPushButton#AddAttachBtn:hover {{ background:{sel_bg_hover}; }}
QPushButton#AttachX {{ background:transparent; color:{text_dim}; border:none; font-size:13px; padding:0 2px; }}
QPushButton#AttachX:hover {{ color:{err}; }}
QPushButton#ChatActBtn {{
    background:{panel_2}; color:{text_mut}; border:1px solid {border_2};
    border-radius:11px; padding:2px 12px; font-size:11px;
}}
QPushButton#ChatActBtn:hover  {{ background:{panel_3}; color:{text_strong}; border-color:{border_3}; }}
QPushButton#ChatActBtn:pressed{{ background:{panel_deep}; }}
QPushButton#ChatActBtn[active="true"] {{
    background:{sel_bg}; color:{sel_text}; border-color:{ok}; font-weight:bold;
}}
#AttachCard {{ background:{panel_2}; border:1px solid {border_2}; border-radius:8px; }}
#AttachThumb {{ background:{panel_deep}; border:1px solid {border_2}; border-radius:5px; color:{text_mut}; }}
#AttachName {{ color:{text_strong}; font-size:10px; }}
#AttachCardX {{ background:{panel}; color:{text}; border:1px solid {border_2}; border-radius:8px; font-size:12px; padding:0; }}
#AttachCardX:hover {{ color:{err}; border-color:{err}; }}
QToolTip {{ background:{panel_2}; color:{text_strong}; border:1px solid {border_2}; padding:4px 6px; }}
"""

# ═══════════════════════════════════════════════════════════════════
#  文件读取（多编码兼容）
# ═══════════════════════════════════════════════════════════════════
def read_text_file(path, limit=None):
    for enc in _READ_ENCODINGS:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read() if limit is None else f.read(limit)
        except UnicodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read() if limit is None else f.read(limit)


# ═══════════════════════════════════════════════════════════════════
#  Skill 文件解析 / 扫描
# ═══════════════════════════════════════════════════════════════════
def _slug(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_") or "skill"


def parse_skill_text(text: str, fallback_name: str) -> dict:
    name, desc = fallback_name, ""
    stripped = text.lstrip("\ufeff").lstrip()
    if stripped.startswith("---"):
        lines = stripped.splitlines()
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i; break
        if end is not None:
            for ln in lines[1:end]:
                if ":" in ln or "：" in ln:
                    k, v = re.split(r"[:：]", ln, 1)
                    k = k.strip().lstrip("#").strip().lower(); v = v.strip().strip('"\'')
                    if k in ("name", "名称") and v: name = v
                    elif k in ("description", "desc", "描述") and v: desc = v
            body = "\n".join(lines[end + 1:]).strip()
            return {"name": name, "desc": desc, "prompt": body or stripped}
    lines = text.splitlines()
    sep = None
    for i, ln in enumerate(lines):
        if ln.strip() in ("---", "===", "———"):
            sep = i; break
    if sep is not None:
        for ln in lines[:sep]:
            s = ln.strip().lstrip("#").strip()
            if ":" in s or "：" in s:
                k, v = re.split(r"[:：]", s, 1)
                k = k.strip().lower(); v = v.strip()
                if k in ("名称", "name") and v: name = v
                elif k in ("描述", "desc", "description") and v: desc = v
        body = "\n".join(lines[sep + 1:]).strip()
        if body:
            return {"name": name, "desc": desc, "prompt": body}
    first = next((l.strip() for l in lines if l.strip()), "")
    return {"name": name, "desc": desc or (first[:30] if first else ""), "prompt": text.strip()}


def scan_skills():
    errors = []
    try:
        os.makedirs(SKILLS_DIR, exist_ok=True)
        files = sorted(f for f in os.listdir(SKILLS_DIR)
                       if f.lower().endswith((".md", ".markdown")))
    except Exception as e:
        return [], [f"目录不可读：{e}"], 0
    skills, seen = [], set()
    for fn in files:
        fp = os.path.join(SKILLS_DIR, fn)
        try:
            sk = parse_skill_text(read_text_file(fp), os.path.splitext(fn)[0])
            sk["path"] = fp; sk["file"] = fn
            if not sk["prompt"].strip():
                errors.append(f"{fn}（内容为空）"); continue
            if sk["name"] in seen:
                errors.append(f"{fn}（名称重复：{sk['name']}）"); continue
            skills.append(sk); seen.add(sk["name"])
        except Exception as e:
            errors.append(f"{fn}（读取失败：{e}）")
    return skills, errors, len(files)


def load_skills() -> list:
    return scan_skills()[0]


def compose_system_prompt(skills: list) -> str:
    if not skills:
        return DEFAULT_SYSTEM_PROMPT
    head = "你已加载以下技能（Skill）。请理解每个技能的用途，并在合适的场景主动运用它们来完成用户的任务。\n"
    blocks = []
    for i, s in enumerate(skills, 1):
        b = f"\n━━ 技能 {i}：{s['name']} ━━"
        if s.get("desc"):
            b += f"\n【用途】{s['desc']}"
        b += f"\n{s['prompt']}"
        blocks.append(b)
    return head + "\n".join(blocks)


def _clear_layout(layout):
    while layout.count():
        it = layout.takeAt(0)
        w = it.widget()
        if w is not None:
            w.setParent(None)


# ═══════════════════════════════════════════════════════════════════
#  把拖入文件当作附件的输入框
# ═══════════════════════════════════════════════════════════════════
class _ChatInput(QTextEdit):
    files_dropped = pyqtSignal(list)

    def canInsertFromMimeData(self, source):
        if source.hasUrls():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasUrls():
            files = [u.toLocalFile() for u in source.urls()
                     if u.toLocalFile() and os.path.isfile(u.toLocalFile())]
            if files:
                self.files_dropped.emit(files)
                return
        super().insertFromMimeData(source)


# ═══════════════════════════════════════════════════════════════════
#  左侧：回合制对话区
# ═══════════════════════════════════════════════════════════════════
SLASH_HELP = "可用命令：/clear 清空对话并释放记忆（/reset、/new 同义）；/help 显示帮助。"


class SkillChat(QWidget):
    status_msg          = pyqtSignal(str)
    history_changed     = pyqtSignal()
    attachments_changed = pyqtSignal(list)

    def __init__(self, get_model_fn, parent=None):
        super().__init__(parent)
        self._get_model = get_model_fn
        self._system_prompt = DEFAULT_SYSTEM_PROMPT
        self._active_skills = []
        self._attachments = []

        # 回合制状态
        self.turns = []           # 每个回合: dict（见 _new_turn）
        self._cur_turn = None
        self._busy = False

        self._render_timer = QTimer(self); self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._flush_render)
        self._last_rendered_len = 0
        self.current_ai_label = self.current_ai_item = None
        self.input_history = []; self.history_index = -1
        self._buf = ""

        # 标签页贴齐主内容区左右（外边距由 ContentRoot 统一提供）
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 4, 0, 0); lay.setSpacing(6)

        toggle_row = QHBoxLayout(); toggle_row.setSpacing(16)
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
        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.time_label.setStyleSheet(fmt(TIME_LABEL_QSS))
        toggle_row.addWidget(self.time_label)
        lay.addLayout(toggle_row)
        self._clock = QTimer(self); self._clock.timeout.connect(self._tick)
        self._clock.start(1000); self._tick()

        lay.addWidget(_make_hline())

        self.list = QListWidget()
        self.list.setMinimumHeight(260)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.setStyleSheet(fmt(LIST_CHAT_QSS))
        lay.addWidget(self.list, 1)

        line_px = QFontMetrics(self.list.font()).lineSpacing() + 2
        self._scroll_step = line_px
        sb = self.list.verticalScrollBar()
        sb.setSingleStep(line_px); sb.setPageStep(max(1, self.list.viewport().height() - line_px))
        self.list.viewport().installEventFilter(self)

        lay.addWidget(_make_hline())

        status_row = QHBoxLayout(); status_row.setContentsMargins(4, 2, 4, 2); status_row.setSpacing(6)
        self._inner_dot = QLabel("⚪"); self._inner_dot.setFixedWidth(18)
        self._inner_dot.setAlignment(Qt.AlignCenter); self._inner_dot.setStyleSheet(fmt(THINKING_DOT_QSS))
        status_row.addWidget(self._inner_dot)
        self._inner_text = QLabel("就绪  ·  输入 /clear 可清空对话"); self._inner_text.setStyleSheet(fmt(THINKING_TEXT_QSS))
        self._inner_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_row.addWidget(self._inner_text); lay.addLayout(status_row)

        lay.addWidget(QLabel("输入内容（可拖文件进来作附件；输入 /clear 清空对话）："))
        self.input = _ChatInput()
        self.input.setMinimumHeight(90); self.input.setMaximumHeight(170)
        self.input.setStyleSheet(fmt(INPUT_TRANSPARENT_QSS)); self.input.installEventFilter(self)
        self.input.files_dropped.connect(self.add_attachment_paths)
        lay.addWidget(self.input)

        row = QHBoxLayout(); row.addStretch()
        self.chk_enter = QCheckBox("回车发送"); self.chk_enter.setChecked(True)
        self.chk_enter.setStyleSheet(_chk_style("#1d4ed8", "#3b82f6", "#93c5fd", False, 13))
        self.chk_enter.setToolTip("勾选：Enter 直接发送\n取消：Shift+Enter 换行")
        row.addWidget(self.chk_enter); row.addSpacing(12)
        self.send_btn = QPushButton("发送"); self.send_btn.clicked.connect(self._send); row.addWidget(self.send_btn)
        self.up = QPushButton("上条指令"); self.up.setEnabled(False)
        self.up.clicked.connect(self._load_prev); row.addWidget(self.up)
        self.clear_btn = QPushButton("清空对话")
        self.clear_btn.setToolTip("等同于输入 /clear：清空对话并释放记忆")
        self.clear_btn.clicked.connect(lambda: self._handle_command("/clear"))
        row.addWidget(self.clear_btn); row.addStretch()
        lay.addLayout(row)

    # ── 回合数据 ──────────────────────────────────────────────────────
    @staticmethod
    def _new_turn(prompt, user_msg):
        return {"prompt": prompt, "user_msg": user_msg, "assistant": None,
                "user_item": None, "resp_items": [], "ai_item": None, "ai_label": None}

    def _build_history(self):
        hist = [{"role": "system", "content": self._system_prompt}]
        for t in self.turns:
            hist.append(t["user_msg"])
            if t["assistant"] is not None:
                hist.append({"role": "assistant", "content": t["assistant"]})
        return hist

    def message_count(self) -> int:
        return sum(1 + (1 if t["assistant"] is not None else 0) for t in self.turns)

    # ── Skill 注入 ────────────────────────────────────────────────────
    def apply_skills(self, skills: list):
        self._active_skills = list(skills)
        self._system_prompt = compose_system_prompt(skills)   # 下次生成自动生效
        if skills:
            names = "、".join(s["name"] for s in skills)
            self._set_inner(f"🟢 已启用 {len(skills)} 个 Skill：{names}")
            self.status_msg.emit(f"🟢 已启用 {len(skills)} 个 Skill")
        else:
            self._set_inner("⚪ 未启用 Skill（通用助手）")
            self.status_msg.emit("⚪ 未启用 Skill")

    # ── 附件 ──────────────────────────────────────────────────────────
    def _classify(self, path):
        return "image" if os.path.splitext(path)[1].lower() in IMAGE_EXTS else "text"

    def pick_attachments(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择要发送的文件", "",
            "常用文件 (*.txt *.md *.py *.js *.ts *.json *.csv *.html *.css *.xml "
            "*.yaml *.yml *.log *.sql *.java *.c *.cpp *.go *.rs *.png *.jpg *.jpeg *.webp);;所有文件 (*.*)")
        self.add_attachment_paths(paths)

    def add_attachment_paths(self, paths):
        changed = False
        for p in paths or []:
            if not os.path.isfile(p) or any(a["path"] == p for a in self._attachments):
                continue
            try: size = os.path.getsize(p)
            except Exception: size = 0
            self._attachments.append(
                {"path": p, "name": os.path.basename(p), "kind": self._classify(p), "size": size})
            changed = True
        if changed:
            self._emit_attachments()

    def remove_attachment(self, path):
        n = len(self._attachments)
        self._attachments = [a for a in self._attachments if a["path"] != path]
        if len(self._attachments) != n:
            self._emit_attachments()

    def clear_attachments(self):
        if self._attachments:
            self._attachments = []
            self._emit_attachments()

    def _emit_attachments(self):
        self.attachments_changed.emit(list(self._attachments))

    def _read_text_attachment(self, path):
        try:
            data = read_text_file(path, ATTACH_TEXT_MAX + 1)
        except Exception as e:
            return f"（读取失败：{e}）", False
        return data[:ATTACH_TEXT_MAX], len(data) > ATTACH_TEXT_MAX

    def _build_user_message(self, prompt, model):
        content = prompt
        images, img_ignored, names = [], False, []
        vision = bool(oc and oc._is_vision_model_name(model))
        for a in self._attachments:
            names.append(a["name"])
            if a["kind"] == "image":
                if vision:
                    try:
                        with open(a["path"], "rb") as f:
                            images.append(base64.b64encode(f.read()).decode())
                    except Exception:
                        img_ignored = True
                else:
                    img_ignored = True
            else:
                txt, trunc = self._read_text_attachment(a["path"])
                content += f"\n\n【附件：{a['name']}】\n{txt}"
                if trunc:
                    content += "\n…（内容过长，已截断）"
        if img_ignored:
            content += "\n\n（注：附带了图片，但当前模型非视觉模型，图片已忽略）"
        msg = {"role": "user", "content": content}
        if images:
            msg["images"] = images
        disp = prompt + (("\n\n📎 " + "、".join(names)) if names else "")
        return msg, disp

    def refresh_theme(self, *_):
        """重刷本组件全部控件级样式。"""
        self.time_label.setStyleSheet(fmt(TIME_LABEL_QSS))
        self.list.setStyleSheet(fmt(LIST_CHAT_QSS))
        self._inner_dot.setStyleSheet(fmt(THINKING_DOT_QSS))
        self.input.setStyleSheet(fmt(INPUT_TRANSPARENT_QSS))
        self.chk_web.setStyleSheet(_chk_style("#1d4ed8", "#3b82f6", "#93c5fd", True, 15))
        self.chk_think.setStyleSheet(_chk_style("#6d28d9", "#a78bfa", "#c4b5fd", True, 15))
        self.chk_enter.setStyleSheet(_chk_style("#1d4ed8", "#3b82f6", "#93c5fd", False, 13))
        self._set_inner(getattr(self, "_inner_msg", "就绪  ·  输入 /clear 可清空对话"))
        # 已渲染的用户气泡
        for i in range(self.list.count()):
            w = self.list.itemWidget(self.list.item(i))
            if w is None:
                continue
            for lab in w.findChildren(QLabel):
                if lab.objectName() == "ChatBubbleUser":
                    lab.setStyleSheet(fmt(BUBBLE_USER_QSS))

    # ── 内部状态栏 ────────────────────────────────────────────────────
    def _set_inner(self, msg: str):
        self._inner_msg = msg          # 记住原始消息（含 emoji 前缀），主题切换时重算颜色
        dot_map = {
            "🟢": ("🟢", "#22c55e"), "🟡": ("🟡", "#f59e0b"), "⚪": ("⚪", tk("text_faint")),
            "⚠️": ("🟠", "#f97316"), "❌": ("🔴", "#ef4444"), "✅": ("🟢", "#22c55e"),
            "🌐": ("🔵", "#3b82f6"), "🧠": ("🟣", "#a78bfa"), "🔄": ("🟣", "#a78bfa"),
            "✏️": ("🟡", "#f59e0b"), "🧹": ("🟢", "#22c55e"),
        }
        dot, color, text = "⚪", tk("text_faint"), msg
        for prefix, (d, c) in dot_map.items():
            if msg.startswith(prefix):
                dot, color = d, c; text = msg[len(prefix):].lstrip(); break
        self._inner_dot.setText(dot); self._inner_text.setText(text)
        self._inner_text.setStyleSheet(f"color:{color}; font-size:12px;")

    def _tick(self):
        self.time_label.setText(datetime.now().strftime("%Y年%m月%d日  %A  %H:%M:%S"))

    def _on_web_changed(self, state):
        if state and not _DDGS_OK:
            self._set_inner("⚠️ 未安装 duckduckgo-search，请执行: pip install duckduckgo-search")
        else:
            self.status_msg.emit("🟢 联网搜索已开启" if state else "⚪ 联网搜索已关闭")

    def _on_think_changed(self, state):
        self.status_msg.emit("🟢 深度思考已开启" if state else "⚪ 深度思考已关闭")

    # ── 斜杠命令 ──────────────────────────────────────────────────────
    def _handle_command(self, text):
        cmd = text.strip().split()[0].lower()
        if cmd in ("/clear", "/reset", "/new", "/cls"):
            self._clear()
            self._add_system_note("🧹 已清空对话记忆（上下文已释放）")
            return True
        if cmd in ("/help", "/?", "/命令"):
            self._add_system_note(SLASH_HELP)
            return True
        return False

    # ── 发送 ──────────────────────────────────────────────────────────
    def _send(self):
        text = self.input.toPlainText().strip()
        if text.startswith("/") and self._handle_command(text):
            self.input.clear(); return
        if self._busy:
            self._set_inner("⚠️ 正在生成，请稍候…"); return
        if not (oc and oc.is_alive()):
            self._set_inner("⚠️ 未运行 Ollama"); return
        model = self._get_model()
        if not model:
            self._set_inner("⚠️ 未选择模型"); return
        if not oc.has_model(model):
            self._set_inner(f"⚠️ 未发现模型 {model}"); return
        if not text and not self._attachments:
            return

        umsg, disp = self._build_user_message(text, model)
        turn = self._new_turn(text, umsg)
        self.turns.append(turn)
        _, item = self._add_bubble(disp, is_user=True, turn=turn)
        turn["user_item"] = item
        self.input.clear(); self.clear_attachments()
        self.input_history.append(text); self.history_index = len(self.input_history)
        self.up.setEnabled(True)
        self._start_generation(turn)

    def _start_generation(self, turn):
        model = self._get_model()
        if not (oc and oc.is_alive()):
            self._set_inner("⚠️ 未运行 Ollama"); return
        if not model or not oc.has_model(model):
            self._set_inner("⚠️ 模型不可用"); return
        self._buf = ""; self._last_rendered_len = 0
        self.current_ai_label = self.current_ai_item = None
        self._cur_turn = turn
        self._busy = True
        history = self._build_history()

        modes = []
        if self.chk_web.isChecked():                     modes.append("联网")
        elif _DDGS_OK and _should_auto_search(turn["prompt"]): modes.append("自动联网")
        if self.chk_think.isChecked():                   modes.append("深度思考")
        hint = "（" + " + ".join(modes) + "）" if modes else ""
        self._set_inner(f"🟡 回答生成中{hint}…")

        self.worker = _ChatWorker(
            model, history,
            web_search=self.chk_web.isChecked(), deep_think=self.chk_think.isChecked(),
        )
        self.worker.chunk.connect(self._on_chunk)
        self.worker.status.connect(self._set_inner)
        self.worker.sources.connect(self._show_sources)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_done)
        self.worker.start()
        self.history_changed.emit()

    def _on_chunk(self, piece):
        if piece.startswith("\x00THINK\x00") and piece.endswith("\x00/THINK\x00"):
            self._add_think_bubble(piece[len("\x00THINK\x00"):-len("\x00/THINK\x00")]); return
        self._buf += piece
        if not self._render_timer.isActive(): self._render_timer.start(40)

    def _on_error(self, m):
        self._busy = False
        self._set_inner("❌ " + m)

    # ── 气泡 ──────────────────────────────────────────────────────────
    def _add_bubble(self, text, is_user, turn=None):
        w = QWidget(); lab = QLabel(text)
        lab.setWordWrap(True); lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lab.setFont(QFont("微软雅黑", 10))
        lab.setFixedWidth(int(self.list.viewport().width() * (0.70 if is_user else 0.88)))
        if is_user:
            lab.setObjectName("ChatBubbleUser")
            lab.setStyleSheet(fmt(BUBBLE_USER_QSS))
        inner = QVBoxLayout(); inner.setContentsMargins(0, 0, 0, 0); inner.setSpacing(2)
        inner.addWidget(lab)
        item = QListWidgetItem()
        inner.addWidget(self._make_action_bar(lab, item, is_user, turn))
        out = QHBoxLayout(); out.setContentsMargins(20, 1, 20, 6)
        if is_user: out.addStretch(); out.addLayout(inner)
        else:       out.addLayout(inner); out.addStretch()
        w.setLayout(out)
        item.setSizeHint(w.sizeHint()); item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(item); self.list.setItemWidget(item, w)
        if not is_user and turn is not None:
            turn["resp_items"].append(item)
        return lab, item

    def _make_action_bar(self, lab, item, is_user, turn):
        bar = QWidget(); h = QHBoxLayout(bar); h.setContentsMargins(2, 2, 2, 0); h.setSpacing(8)
        if is_user: h.addStretch()
        h.addWidget(self._make_act_btn(
            "复制", "已复制", lambda: QApplication.clipboard().setText(lab.text())))
        if is_user:
            h.addWidget(self._make_act_btn(
                "修改", "已载入", lambda: self._edit_turn(turn),
                tip="把该问题载回输入框修改；会移除此回合及其之后的内容"))
        else:
            h.addWidget(self._make_act_btn(
                "刷新", "已重生成", lambda: self._regen_turn(turn),
                tip="用新种子重新生成该回答"))
            h.addWidget(self._make_act_btn(
                "删除", "已删除", lambda: self._delete_turn(turn),
                tip="删除整回合（问题+回答），释放记忆"))
            h.addStretch()
        return bar

    def _make_act_btn(self, text, done_text, handler, tip=""):
        btn = QPushButton(text); btn.setObjectName("ChatActBtn")
        btn.setCursor(Qt.PointingHandCursor)
        if tip: btn.setToolTip(tip)
        def on_click():
            handler()
            self._flash_btn(btn, text, done_text)
        btn.clicked.connect(on_click)
        return btn

    def _flash_btn(self, btn, normal_text, done_text):
        # 明显的“已完成”状态，5 秒后自动恢复；若按钮已随气泡销毁则安全忽略
        try:
            btn.setText(done_text)
            btn.setProperty("active", True)
            btn.style().unpolish(btn); btn.style().polish(btn)
        except RuntimeError:
            return
        def revert():
            try:
                btn.setText(normal_text)
                btn.setProperty("active", False)
                btn.style().unpolish(btn); btn.style().polish(btn)
            except RuntimeError:
                pass
        QTimer.singleShot(5000, revert)

    def _add_think_bubble(self, summary: str):
        w = QWidget()
        title = QLabel("🧠 深度思考过程（点击展开）")
        title.setStyleSheet(fmt(THINK_TITLE_QSS)); title.setCursor(Qt.PointingHandCursor)
        body = QLabel(summary); body.setWordWrap(True); body.setFont(QFont("微软雅黑", 9))
        body.setStyleSheet(fmt(THINK_BODY_QSS) + "border-radius:4px; margin-top:2px;")
        body.setVisible(False); body.setFixedWidth(int(self.list.viewport().width() * 0.88))
        item = QListWidgetItem()
        def _toggle(_=None):
            body.setVisible(not body.isVisible()); item.setSizeHint(w.sizeHint())
        title.mousePressEvent = _toggle
        vlay = QVBoxLayout(); vlay.setContentsMargins(0, 0, 0, 0); vlay.setSpacing(2)
        vlay.addWidget(title); vlay.addWidget(body)
        outer = QHBoxLayout(); outer.setContentsMargins(20, 1, 20, 4)
        outer.addLayout(vlay); outer.addStretch(); w.setLayout(outer)
        item.setSizeHint(w.sizeHint()); item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(item); self.list.setItemWidget(item, w)
        if self._cur_turn is not None:
            self._cur_turn["resp_items"].append(item)
        self.list.scrollToBottom()

    def _add_system_note(self, text):
        w = QWidget(); lab = QLabel(text); lab.setObjectName("SysNote")
        lab.setWordWrap(True); lab.setAlignment(Qt.AlignCenter)
        lab.setFixedWidth(int(self.list.viewport().width() * 0.9))
        h = QHBoxLayout(w); h.setContentsMargins(20, 4, 20, 4)
        h.addStretch(); h.addWidget(lab); h.addStretch()
        item = QListWidgetItem(); item.setSizeHint(w.sizeHint())
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(item); self.list.setItemWidget(item, w); self.list.scrollToBottom()

    # ── 回合操作：修改 / 刷新 / 删除 ─────────────────────────────────
    def _remove_turn_items(self, t, include_user):
        items = list(t.get("resp_items", []))
        if include_user and t.get("user_item") is not None:
            items.append(t["user_item"])
        for it in items:
            r = self.list.row(it)
            if r >= 0:
                self.list.takeItem(r)

    def _truncate_from(self, idx, keep_question):
        # 移除 idx 之后的所有回合
        for t in self.turns[idx + 1:]:
            self._remove_turn_items(t, include_user=True)
        if keep_question:
            t = self.turns[idx]
            self._remove_turn_items(t, include_user=False)
            t["resp_items"] = []; t["assistant"] = None
            t["ai_item"] = None; t["ai_label"] = None
            self.turns = self.turns[:idx + 1]
        else:
            self._remove_turn_items(self.turns[idx], include_user=True)
            self.turns = self.turns[:idx]
        self.history_changed.emit()

    def _edit_turn(self, turn):
        if self._busy:
            self._set_inner("⚠️ 生成中，暂不能修改"); return
        if turn not in self.turns:
            return
        idx = self.turns.index(turn)
        prompt = turn["prompt"]
        self._truncate_from(idx, keep_question=False)
        self.input.setPlainText(prompt)
        self.input.moveCursor(QTextCursor.End); self.input.setFocus()
        self._set_inner("✏️ 已载入该问题，修改后点“发送”")

    def _regen_turn(self, turn):
        if self._busy:
            self._set_inner("⚠️ 正在生成，请稍候…"); return
        if turn not in self.turns:
            return
        idx = self.turns.index(turn)
        self._truncate_from(idx, keep_question=True)
        self._set_inner("🔄 换个种子重新生成中…")
        self._start_generation(turn)

    def _delete_turn(self, turn):
        if self._busy:
            self._set_inner("⚠️ 生成中，暂不能删除"); return
        if turn not in self.turns:
            return
        self._remove_turn_items(turn, include_user=True)
        self.turns.remove(turn)
        self._set_inner("⚪ 已删除该回合（记忆已更新）")
        self.history_changed.emit()

    # ── 清空 ──────────────────────────────────────────────────────────
    def _clear(self):
        self.list.clear(); self.turns = []
        self._cur_turn = None
        self.current_ai_label = self.current_ai_item = None
        self._buf = ""; self._last_rendered_len = 0
        self.clear_attachments()
        self._set_inner("🧹 对话已清空（记忆已释放）")
        self.status_msg.emit("⚪ 对话已清空")
        self.history_changed.emit()

    def _load_prev(self):
        if not self.input_history: return
        self.history_index = max(0, self.history_index - 1)
        self.input.setPlainText(self.input_history[self.history_index])
        self.input.moveCursor(QTextCursor.End)

    # ── 流式渲染 ──────────────────────────────────────────────────────
    def _flush_render(self):
        filtered = re.sub(r"<\s*think\s*>.*?<\s*/\s*think\s*>", "", self._buf, flags=re.I | re.S)
        if self.current_ai_label is None:
            self.current_ai_label, self.current_ai_item = self._add_bubble(
                filtered, is_user=False, turn=self._cur_turn)
            if self._cur_turn is not None:
                self._cur_turn["ai_item"] = self.current_ai_item
                self._cur_turn["ai_label"] = self.current_ai_label
            self._last_rendered_len = len(filtered)
        elif len(filtered) > self._last_rendered_len:
            self.current_ai_label.setText(filtered)
            container = self.list.itemWidget(self.current_ai_item)
            if container is not None:
                nh = container.sizeHint()
                if nh != self.current_ai_item.sizeHint(): self.current_ai_item.setSizeHint(nh)
            self._last_rendered_len = len(filtered)
        self.list.scrollToBottom()

    def _on_done(self):
        self._busy = False
        if not self._buf.endswith("\n"): self._buf += "\n"
        self._flush_render()
        final = re.sub(r"<\s*think\s*>.*?<\s*/\s*think\s*>", "", self._buf, flags=re.I | re.S).strip()
        t = self._cur_turn
        if final and t is not None:
            t["assistant"] = final
            sp = QListWidgetItem(); sp.setSizeHint(QSize(1, 10))
            sp.setFlags(sp.flags() & ~Qt.ItemIsSelectable)
            self.list.addItem(sp); t["resp_items"].append(sp)
            self._set_inner("🟢 回答完成")
        else:
            self._set_inner("🟡 无内容返回")
        self.list.scrollToBottom()
        self.history_changed.emit()

    def _show_sources(self, src_list: list):
        if not src_list: return
        w = QWidget()
        title = QLabel(f"🔗 参考来源（{len(src_list)} 条，点击展开）")
        title.setStyleSheet(fmt(SRC_TITLE_QSS)); title.setCursor(Qt.PointingHandCursor)
        body = QWidget(); body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(4, 4, 4, 4); body_lay.setSpacing(3)
        for i, s in enumerate(src_list, 1):
            lbl = QLabel(f'<a href="{s["href"]}" style="color:{tk("accent")};">'
                         f'[{i}] {s["title"][:60]}{"…" if len(s["title"])>60 else ""}</a>')
            lbl.setOpenExternalLinks(True); lbl.setWordWrap(True)
            lbl.setFont(QFont("微软雅黑", 9)); lbl.setStyleSheet(fmt(SRC_LINK_QSS))
            body_lay.addWidget(lbl)
        body.setStyleSheet(fmt(SRC_BODY_QSS))
        body.setFixedWidth(int(self.list.viewport().width() * 0.88)); body.setVisible(False)
        item = QListWidgetItem()
        def _toggle(_=None):
            body.setVisible(not body.isVisible())
            item.setSizeHint(w.sizeHint()); self.list.scrollToBottom()
        title.mousePressEvent = _toggle
        vlay = QVBoxLayout(); vlay.setContentsMargins(0, 0, 0, 0); vlay.setSpacing(2)
        vlay.addWidget(title); vlay.addWidget(body)
        outer = QHBoxLayout(); outer.setContentsMargins(20, 1, 20, 6)
        outer.addLayout(vlay); outer.addStretch(); w.setLayout(outer)
        item.setSizeHint(w.sizeHint()); item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(item); self.list.setItemWidget(item, w)
        if self._cur_turn is not None:
            self._cur_turn["resp_items"].append(item)
        self.list.scrollToBottom()

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
                    self._send(); return True
                elif ke.modifiers() == Qt.ShiftModifier:
                    pass
        return super().eventFilter(obj, event)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        sb = self.list.verticalScrollBar()
        sb.setPageStep(max(1, self.list.viewport().height() - getattr(self, "_scroll_step", 16)))


# ═══════════════════════════════════════════════════════════════════
#  可接收拖拽 .md 的 Skill 列表
# ═══════════════════════════════════════════════════════════════════
class _SkillDropList(QListWidget):
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            mds = [u.toLocalFile() for u in e.mimeData().urls()
                   if u.toLocalFile().lower().endswith((".md", ".markdown")) and os.path.isfile(u.toLocalFile())]
            if mds:
                self.files_dropped.emit(mds); e.acceptProposedAction(); return
        super().dropEvent(e)


# ═══════════════════════════════════════════════════════════════════
#  右侧：功能区
# ═══════════════════════════════════════════════════════════════════
class FunctionPanel(QWidget):
    skills_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FuncPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(fmt(PANEL_QSS))
        self._skills = []
        self._loading = False
        self._chat = None
        self._last_connected = None

        root = QVBoxLayout(self); root.setContentsMargins(10, 10, 10, 10); root.setSpacing(8)

        title = QLabel("🧩 Skill 加载器"); title.setObjectName("FuncPanelTitle")
        root.addWidget(title)

        card = QFrame(); card.setObjectName("PanelCard")
        cv = QVBoxLayout(card); cv.setContentsMargins(10, 8, 10, 8); cv.setSpacing(4)
        sec = QLabel("当前状态"); sec.setObjectName("PanelSection"); cv.addWidget(sec)
        self._st_model = self._status_row(cv, "模型", "—")
        self._st_skill = self._status_row(cv, "已启用", "无（通用助手）")
        self._st_count = self._status_row(cv, "对话", "0 条")
        self._st_conn  = self._status_row(cv, "连接", "未连接")
        root.addWidget(card)

        sec2 = QLabel("Skill 库（勾选 = 让模型获得该能力）")
        sec2.setObjectName("PanelSection"); root.addWidget(sec2)
        self.skill_list = _SkillDropList(); self.skill_list.setObjectName("SkillList")
        self.skill_list.setMinimumHeight(96)
        self.skill_list.currentRowChanged.connect(self._on_select)
        self.skill_list.itemChanged.connect(self._on_item_changed)
        self.skill_list.files_dropped.connect(self._on_files_dropped)
        root.addWidget(self.skill_list, 1)

        r = QHBoxLayout(); r.setSpacing(6)
        r.addWidget(self._panel_btn("打开目录", lambda: self._open_dir()))
        r.addWidget(self._panel_btn("刷新", lambda: self.reload_skills()))
        root.addLayout(r)

        self.path_label = QLabel(f"目录：{SKILLS_DIR}")
        self.path_label.setObjectName("PathLabel"); self.path_label.setWordWrap(True)
        root.addWidget(self.path_label)

        sec3 = QLabel("操作记录与状态"); sec3.setObjectName("PanelSection")
        root.addWidget(sec3)
        self.log = QTextEdit(); self.log.setObjectName("SkillLog"); self.log.setReadOnly(True)
        self.log.setMinimumHeight(150); self.log.setFont(QFont("微软雅黑", 8))
        self.log.document().setDocumentMargin(4)
        root.addWidget(self.log, 1)

        head = QHBoxLayout(); head.setSpacing(6)
        sec4 = QLabel("附件"); sec4.setObjectName("PanelSection")
        head.addWidget(sec4)
        cap = QLabel("· 文本注入上下文 / 图片需视觉模型")
        cap.setObjectName("PanelHint"); head.addWidget(cap)
        head.addStretch()
        self.btn_add_attach = QPushButton("➕ 添加"); self.btn_add_attach.setObjectName("AddAttachBtn")
        self.btn_add_attach.setCursor(Qt.PointingHandCursor)
        self.btn_add_attach.setToolTip("添加文件为附件；也可把文件直接拖到左侧输入框")
        self.btn_add_attach.clicked.connect(lambda: self._chat and self._chat.pick_attachments())
        head.addWidget(self.btn_add_attach)
        root.addLayout(head)

        # 附件用横向“图片卡”展示，占用面积小
        self.attach_scroll = QScrollArea(); self.attach_scroll.setObjectName("AttachScroll")
        self.attach_scroll.setWidgetResizable(True); self.attach_scroll.setFixedHeight(74)
        self.attach_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.attach_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.attach_holder = QWidget()
        self.attach_layout = QHBoxLayout(self.attach_holder)
        self.attach_layout.setContentsMargins(6, 4, 6, 4); self.attach_layout.setSpacing(6)
        self.attach_layout.addStretch()
        self.attach_scroll.setWidget(self.attach_holder)
        root.addWidget(self.attach_scroll)

        self.render_attachments([])
        self.reload_skills(initial=True)


    def refresh_theme(self, *_):
        self.setStyleSheet(fmt(PANEL_QSS))
        self._emit_enabled()          # 重算 skill 状态文字色
        self.update_status(connected=self._last_connected)

    def bind_chat(self, chat):
        self._chat = chat

    def _status_row(self, parent_lay, key, val):
        r = QHBoxLayout(); r.setSpacing(6)
        k = QLabel(key + "："); k.setObjectName("StatusKey"); k.setFixedWidth(52)
        v = QLabel(val); v.setObjectName("StatusVal"); v.setWordWrap(True)
        v.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        r.addWidget(k); r.addWidget(v, 1); parent_lay.addLayout(r)
        return v

    def _panel_btn(self, text, cb):
        b = QPushButton(text); b.setObjectName("PanelBtn"); b.setCursor(Qt.PointingHandCursor)
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); b.clicked.connect(cb)
        return b

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")
        self.log.moveCursor(QTextCursor.End)

    def reload_skills(self, initial=False):
        prev_enabled = {s["name"] for s in self._enabled_skills()} if self.skill_list.count() else set()
        self._loading = True
        self._skills, errors, raw = scan_skills()
        self.skill_list.clear()
        for sk in self._skills:
            it = QListWidgetItem(sk["name"])
            it.setToolTip(f"{sk.get('desc','')}\n文件：{sk.get('file','')}")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if sk["name"] in prev_enabled else Qt.Unchecked)
            self.skill_list.addItem(it)
        self._loading = False
        self._log(f"🔄 扫描：{SKILLS_DIR}")
        if raw == 0:
            self._log("📂 目录内没有 .md 文件。放入 .md 后再点【刷新】。")
        else:
            self._log(f"发现 {raw} 个 .md，成功加载 {len(self._skills)} 个。")
        for e in errors:
            self._log(f"⚠️ 跳过 {e}")
        self._emit_enabled()

    def _enabled_skills(self):
        out = []
        for i in range(self.skill_list.count()):
            it = self.skill_list.item(i)
            if it.checkState() == Qt.Checked and 0 <= i < len(self._skills):
                out.append(self._skills[i])
        return out

    def _emit_enabled(self):
        if self._loading: return
        en = self._enabled_skills()
        self.skills_changed.emit(en)
        if en:
            names = "、".join(s["name"] for s in en)
            self._st_skill.setText(f"{len(en)} 个：{names}")
            self._st_skill.setStyleSheet(f"color:{tk('cyan')}; font-size:12px;")
        else:
            self._st_skill.setText("无（通用助手）")
            self._st_skill.setStyleSheet(f"color:{tk('text')}; font-size:12px;")

    def _on_item_changed(self, item):
        if self._loading: return
        idx = self.skill_list.row(item)
        if 0 <= idx < len(self._skills):
            sk = self._skills[idx]
            if item.checkState() == Qt.Checked:
                self._log(f"✓ 启用【{sk['name']}】{sk.get('desc','')}")
            else:
                self._log(f"✗ 停用【{sk['name']}】")
        self._emit_enabled()

    def _on_select(self, row):
        if 0 <= row < len(self._skills):
            sk = self._skills[row]
            self._log(f"· 查看【{sk['name']}】{sk.get('desc','')}")

    def _on_files_dropped(self, paths):
        try:
            os.makedirs(SKILLS_DIR, exist_ok=True)
            copied = 0
            for p in paths:
                dst = os.path.join(SKILLS_DIR, os.path.basename(p))
                if os.path.abspath(p) != os.path.abspath(dst):
                    shutil.copy2(p, dst)
                copied += 1
            self._log(f"📥 已拖入 {copied} 个 .md 到目录")
        except Exception as e:
            self._log(f"❌ 拖入失败：{e}")
        self.reload_skills()

    def _open_dir(self):
        try:
            os.makedirs(SKILLS_DIR, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(SKILLS_DIR))
            self._log(f"📂 已打开目录：{SKILLS_DIR}")
        except Exception as e:
            self._log(f"❌ 打开目录失败：{e}")

    def render_attachments(self, atts):
        _clear_layout(self.attach_layout)
        if not atts:
            ph = QLabel("（无附件）"); ph.setObjectName("PanelHint")
            self.attach_layout.addWidget(ph); self.attach_layout.addStretch()
            return
        fm = QFontMetrics(QFont("微软雅黑", 8))
        for a in atts:
            self.attach_layout.addWidget(self._make_attach_card(a, fm))
        self.attach_layout.addStretch()

    def _make_attach_card(self, a, fm):
        card = QFrame(); card.setObjectName("AttachCard")
        card.setFixedSize(58, 62)
        v = QVBoxLayout(card); v.setContentsMargins(3, 3, 3, 3); v.setSpacing(1)

        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0); top.addStretch()
        x = QPushButton("×"); x.setObjectName("AttachCardX")
        x.setFixedSize(15, 15); x.setCursor(Qt.PointingHandCursor); x.setToolTip("移除附件")
        x.clicked.connect(lambda _=False, p=a["path"]: self._chat and self._chat.remove_attachment(p))
        top.addWidget(x); v.addLayout(top)

        thumb = QLabel(); thumb.setObjectName("AttachThumb")
        thumb.setFixedSize(52, 28); thumb.setAlignment(Qt.AlignCenter)
        pm = None
        if a["kind"] == "image":
            p = QPixmap(a["path"])
            if not p.isNull():
                pm = p.scaled(52, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if pm is not None:
            thumb.setPixmap(pm)
        else:
            thumb.setText("🖼" if a["kind"] == "image" else "📄")
        v.addWidget(thumb, 0, Qt.AlignHCenter)

        name = QLabel(fm.elidedText(a["name"], Qt.ElideMiddle, 52))
        name.setObjectName("AttachName"); name.setAlignment(Qt.AlignHCenter)
        name.setToolTip(a["name"])
        v.addWidget(name)
        card.setToolTip(a["name"])
        return card

    def update_status(self, model="", count=None, connected=None):
        if model:
            self._st_model.setText(model or "—")
        if count is not None:
            self._st_count.setText(f"{count} 条")
        if connected is not None:
            self._last_connected = connected
            self._st_conn.setText("已连接" if connected else "未连接")
            self._st_conn.setStyleSheet(
                f"color:{tk('ok') if connected else tk('err')}; font-size:12px;")


# ═══════════════════════════════════════════════════════════════════
#  页面
# ═══════════════════════════════════════════════════════════════════
class PageLiteraryWriting(QWidget):
    # ===== 窗口高度 BUG 根治（与 Grok 诊断一致：heightForWidth 把虚高传给主窗口）=====
    # 本页有两重病因：① 含 wordWrap 标签使 hasHeightForWidth()=True，把宽度相关的虚高
    # 传给主窗口；② 本页内容本身就“真高”（首选高度约 888，超过侧边栏的 736），即便断掉
    # heightForWidth，仍会把窗口首选高度顶过 900。二者都会让真机上一拖窗口就长高、缩不回。
    # 修法：既对外声明“高度不随宽度变化”，又把对外首选高度压到不超过侧边栏（≤700）。
    # 实际布局仍会把可用高度分给本页，聊天列表等 Expanding 子控件照常填满并内部滚动，
    # 标签内部照常换行、不截断文字，视觉无变化。经真实平台验证：本页窗口首选高度由 965
    # 回落到 836，与 6 个正常页面一致。
    def hasHeightForWidth(self):
        return False

    def sizeHint(self):
        s = super().sizeHint()
        return QSize(s.width(), min(s.height(), 700))

    def __init__(self):
        super().__init__()
        self._models_loaded = False
        self._list_worker = None
        self.setStyleSheet(fmt(_BASE_QSS) + fmt(PANEL_QSS))

        root = QVBoxLayout(self)
        # 与系统总览一致：ContentRoot 已有左右内边距，页面不再叠第二层
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        top = QHBoxLayout(); top.setSpacing(8)
        self.btn_refresh = QPushButton("↻"); self.btn_refresh.setObjectName("BtnRefreshIcon")
        self.btn_refresh.setToolTip("重新从 Ollama 获取模型列表")
        self.btn_refresh.clicked.connect(self._refresh); top.addWidget(self.btn_refresh)

        self.model_combo = _ModelCombo(); self.model_combo.setEnabled(False)
        self.model_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.model_combo.setMinimumWidth(280)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        top.addWidget(self.model_combo, 1); top.addStretch(0)

        self.status_dot = QLabel("⚪"); self.status_dot.setObjectName("StatusDot")
        top.addWidget(self.status_dot)
        self.status = QLabel("等待连接 Ollama…")
        self.status.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        top.addWidget(self.status); root.addLayout(top)

        root.addWidget(_make_hline())

        body = QHBoxLayout(); body.setSpacing(10)

        def _get_model():
            return self.model_combo.currentText().strip()

        self.chat  = SkillChat(get_model_fn=_get_model)
        self.panel = FunctionPanel()
        self.panel.bind_chat(self.chat)
        body.addWidget(self.chat, 7)
        body.addWidget(self.panel, 3)
        root.addLayout(body, 1)

        self.chat.status_msg.connect(self._set_status)
        self.panel.skills_changed.connect(self.chat.apply_skills)
        self.chat.history_changed.connect(self._sync_panel)
        self.chat.attachments_changed.connect(self.panel.render_attachments)

        theme.changed.connect(self.refresh_theme)

    def refresh_theme(self, *_):
        """重刷本页全部控件级样式（只 setStyleSheet，不重建控件）。"""
        self.setStyleSheet(fmt(_BASE_QSS) + fmt(PANEL_QSS))
        self.chat.refresh_theme()
        self.panel.refresh_theme()

    def _set_status(self, msg: str):
        dot_map = {"🟢": "🟢", "🟡": "🟡", "⚪": "⚪", "⚠️": "🟠", "❌": "🔴", "✅": "🟢"}
        dot, text = "⚪", msg
        for prefix, d in dot_map.items():
            if msg.startswith(prefix):
                dot = d; text = msg[len(prefix):].lstrip(); break
        self.status_dot.setText(dot); self.status.setText(text)

    def _on_model_changed(self, _=None):
        self._sync_panel()

    def _sync_panel(self, *_):
        model = self.model_combo.currentText().strip()
        connected = bool(oc and oc.is_alive())
        self.panel.update_status(model=model, count=self.chat.message_count(), connected=connected)

    def _refresh(self):
        self._set_status("🟡 正在获取模型列表…")
        self.btn_refresh.setEnabled(False); self.model_combo.setEnabled(False)
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
            self.model_combo.addItems(models); self.model_combo._colorize()
            self.model_combo.setEnabled(True)
            self._set_status(f"🟢 已加载 {len(models)} 个模型（绿=视觉 / 红=文本）")
        self._models_loaded = True; self.btn_refresh.setEnabled(True); self._sync_panel()

    def _on_model_fail(self, msg):
        self._set_status(f"❌ 读取模型失败：{msg}")
        self.btn_refresh.setEnabled(True); self._sync_panel()

    def on_enter(self):
        if not self._models_loaded:
            self._refresh()
        self._sync_panel()
