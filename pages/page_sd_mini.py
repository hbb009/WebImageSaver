"""
page_sd_mini.py  —  Stable Diffusion Mini
界面三分页：启动 / 生成 / CMD输出

核心架构：
  生成时用启动页确认的 Python（A1111/ComfyUI）执行 sd_generate_worker.py
  主程序与生成进程完全隔离，彻底解决 DLL 路径混乱问题
"""

import os, sys, json, glob, random, shutil, platform, subprocess
from datetime import datetime

from styles.common_styles import TEXT_STYLE, BUTTON_STYLE, LINEEDIT_STYLE
from styles.page_sd_comfyui import (
    TABS_QSS, SCROLL_LEFT_QSS, PROGRESS_QSS, PREVIEW_PLACEHOLDER_QSS,
    HINT_LABEL_QSS, STATUS_NEUTRAL_QSS, STATUS_OK_QSS, STATUS_ERR_QSS,
    SECTION_TITLE_QSS, SEPARATOR_QSS, TIPS_QSS,
    META_LABEL_QSS, META_VALUE_QSS,
    CMD_TEXT_QSS, ARCH_HINT_NORMAL_QSS, ARCH_HINT_WARN_QSS, ARCH_LABEL_QSS,
    TAB_BTN_NORMAL, TAB_BTN_SELECTED,
)

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QComboBox, QSlider,
    QGroupBox, QFileDialog, QSizePolicy, QButtonGroup,
    QScrollArea, QSpinBox, QCheckBox, QProgressBar,
    QTabWidget, QPlainTextEdit, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QProcess
from PyQt5.QtGui import QPixmap, QFont, QTextCursor

# worker 脚本路径（与本文件同目录）
_WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sd_generate_worker.py")

# ──────────────────────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────────────────────
def _guess_arch(filename: str) -> str:
    name = filename.lower()
    # Flux 优先
    if any(k in name for k in ["flux", "flux1", "flux.1"]):
        return "flux"
    # SD1.5 先判断，避免被短关键词误伤
    _SD15 = [
        "v1-5", "v1_5", "1.5", "sd15", "sd1.5",
        "chilloutmix", "chillout",
        "dreamshaper", "anything", "deliberate",
        "realistic", "photon", "majicmix", "majic",
        "meinamix", "meina", "ghostmix", "counterfeit",
        "lyriel", "toonyou", "clarity",
        "prunedfp32", "prunedfp16", "emaonly",
    ]
    if any(k in name for k in _SD15):
        return "sd15"
    # SDXL：xl 要求有分隔符，避免误匹配含 xl 字母的普通词
    _SDXL = [
        "sdxl", "_xl", "-xl", "xl_", "xl-", ".xl",
        "pony", "illustrious", "noob",
        "animagine", "wai", "equinox",
        "bss", "kohaku", "animefull",
    ]
    if any(k in name for k in _SDXL):
        return "sdxl"
    return "sdxl"

_ARCH_TIPS = {
    "flux":    "Flux.1 — CFG 固定为 1，步数 20~28，建议 3090（24GB）",
    "sdxl":    "SDXL / Pony / Illustrious — 推荐 1024²，CFG 7，步数 20",
    "sd15":    "SD 1.5 — 推荐 512² 或 768²，CFG 7，步数 20~30",
    "unknown": "未能识别架构，将以 SDXL 方式尝试",
}

_SAMPLER_LIST = [
    "Euler a", "Euler", "DPM++ 2M", "DPM++ 2M Karras",
    "DPM++ SDE", "DPM++ SDE Karras", "DDIM", "UniPC", "LMS", "Heun",
]
_SAMPLERS_FLUX = ["Euler"]

_SIZES = {
    "sdxl": [("1:1",1024,1024),("4:3",1152,896),("3:2",1216,832),
             ("2:3",832,1216),("9:16",768,1344),("16:9",1344,768)],
    "sd15": [("1:1",512,512),("4:3",640,512),("3:2",768,512),
             ("2:3",512,768),("9:16",512,768),("16:9",768,432),("768²",768,768)],
    "flux": [("1:1",1024,1024),("4:3",1152,896),("3:2",1216,832),
             ("2:3",832,1216),("9:16",768,1344),("16:9",1344,768)],
}

_COMMON_NEG = (
    "worst quality, low quality, normal quality, lowres, "
    "bad anatomy, bad hands, text, error, missing fingers, "
    "extra digit, fewer digits, cropped, jpeg artifacts, "
    "signature, watermark, username, blurry"
)

_KNOWN_PYTHONS = [
    r"D:\sd-webui-aki-v4.10\python\python.exe",
    r"D:\stable-diffusion-webui\python\python.exe",
    r"D:\ComfyUI\ComfyUI\venv\Scripts\python.exe",
    r"D:\ComfyUI\python_embeded\python.exe",
    r"D:\ComfyUI_windows_portable\python_embeded\python.exe",
]


# ──────────────────────────────────────────────────────────────
# 环境检测 Worker
# ──────────────────────────────────────────────────────────────
class EnvCheckWorker(QThread):
    sig_line = pyqtSignal(str)
    sig_done = pyqtSignal(bool, str)

    def __init__(self, python_exe):
        super().__init__()
        self.python_exe = python_exe

    def run(self):
        exe = self.python_exe
        self.sig_line.emit(f"► Python : {exe}")
        checks = {
            "torch":        "import torch; print(torch.__version__)",
            "cuda":         "import torch; print(torch.cuda.is_available())",
            "diffusers":    "import diffusers; print(diffusers.__version__)",
            "transformers": "import transformers; print(transformers.__version__)",
            "accelerate":   "import accelerate; print(accelerate.__version__)",
        }
        results = {}
        for pkg, cmd in checks.items():
            try:
                out = subprocess.check_output(
                    [exe, "-c", cmd], stderr=subprocess.PIPE, timeout=20
                ).decode().strip()
                results[pkg] = out
                if pkg == "cuda":
                    icon = "✅ CUDA 可用" if out == "True" else "❌ CUDA 不可用"
                    self.sig_line.emit(f"   {icon}")
                else:
                    self.sig_line.emit(f"   {pkg:<14}: {out}  ✅")
            except Exception as e:
                results[pkg] = None
                msg = str(e)
                if "1114" in msg or "DLL" in msg:
                    self.sig_line.emit(f"   {pkg:<14}: ❌ DLL 初始化失败")
                else:
                    self.sig_line.emit(f"   {pkg:<14}: ❌ 未安装")

        missing = [k for k, v in results.items() if v is None and k != "cuda"]
        cuda_ok = results.get("cuda") == "True"

        if missing:
            self.sig_line.emit(f"\n⚠️ 缺少：{', '.join(missing)}")
            self.sig_line.emit(f"  {exe} -m pip install {' '.join(missing)}")
            self.sig_done.emit(False, f"缺少 {', '.join(missing)}")
        elif not cuda_ok:
            self.sig_line.emit("\n❌ CUDA 不可用")
            self.sig_done.emit(False, "CUDA 不可用")
        else:
            try:
                gpu = subprocess.check_output(
                    [exe, "-c",
                     "import torch; p=torch.cuda.get_device_properties(0);"
                     "print(p.name, round(p.total_memory/1024**3,1))"],
                    stderr=subprocess.DEVNULL, timeout=15
                ).decode().strip()
                self.sig_line.emit(f"\n🖥️  GPU : {gpu} GB")
            except Exception:
                pass
            self.sig_line.emit("\n✅ 环境检测通过，可以开始生图！")
            self.sig_done.emit(True, "OK")


# ──────────────────────────────────────────────────────────────
# 生成 Worker（subprocess 调用 A1111 Python）
# ──────────────────────────────────────────────────────────────
class GenerateWorker(QThread):
    sig_log      = pyqtSignal(str)
    sig_progress = pyqtSignal(int)
    sig_finished = pyqtSignal(list, float, int)
    sig_error    = pyqtSignal(str)

    def __init__(self, python_exe: str, params: dict):
        super().__init__()
        self.python_exe = python_exe   # ← A1111 的 python.exe
        self.p = params
        self._proc = None

    def run(self):
        try:
            self._run_subprocess()
        except Exception as e:
            import traceback
            self.sig_error.emit(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

    def _run_subprocess(self):
        if not os.path.isfile(_WORKER_SCRIPT):
            self.sig_error.emit(
                f"找不到生成脚本：{_WORKER_SCRIPT}\n"
                "请确认 sd_generate_worker.py 与 page_sd_mini.py 在同一目录")
            return

        self.sig_log.emit(f"► 使用 Python：{self.python_exe}")
        self.sig_log.emit(f"► 生成脚本：{_WORKER_SCRIPT}")

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"   # 强制子进程 stdout 用 UTF-8
        self._proc = subprocess.Popen(
            [self.python_exe, _WORKER_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env,
        )

        # 通过 stdin 传参数
        param_json = json.dumps(self.p, ensure_ascii=False)
        self._proc.stdin.write(param_json)
        self._proc.stdin.close()

        # 逐行读取输出
        paths, elapsed, seed = [], 0.0, -1
        for line in self._proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                t = obj.get("type")
                if t == "log":
                    self.sig_log.emit(obj["msg"])
                elif t == "progress":
                    self.sig_progress.emit(obj["pct"])
                elif t == "done":
                    paths   = obj["paths"]
                    elapsed = obj["elapsed"]
                    seed    = obj["seed"]
                elif t == "error":
                    self.sig_error.emit(obj["msg"])
                    return
            except json.JSONDecodeError:
                # 非 JSON 行直接当日志显示（pip 警告等）
                self.sig_log.emit(line)

        self._proc.wait()
        if self._proc.returncode != 0 and not paths:
            self.sig_error.emit(f"生成进程退出码：{self._proc.returncode}")
            return

        if paths:
            self.sig_progress.emit(100)
            self.sig_finished.emit(paths, elapsed, seed)

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


# ──────────────────────────────────────────────────────────────
# CMD 面板（黑底绿字）
# ──────────────────────────────────────────────────────────────
class CmdPanel(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setFont(QFont("Consolas", 11))
        self.txt.setStyleSheet(
            "QPlainTextEdit{background:#0c0e12;color:#39ff80;border:none;}"
            "QScrollBar:vertical{width:6px;background:#0c0e12;}"
            "QScrollBar::handle:vertical{background:#1e4030;border-radius:3px;}")
        lay.addWidget(self.txt)

        bot = QHBoxLayout()
        btn_clr = QPushButton("清空"); btn_clr.setStyleSheet(BUTTON_STYLE)
        btn_clr.setFixedWidth(72); btn_clr.clicked.connect(self.txt.clear)
        btn_copy = QPushButton("复制全部"); btn_copy.setStyleSheet(BUTTON_STYLE)
        btn_copy.setFixedWidth(80)
        btn_copy.clicked.connect(lambda: (
            self.txt.selectAll(), self.txt.copy(),
            self.txt.moveCursor(QTextCursor.End)))
        bot.addStretch(); bot.addWidget(btn_clr); bot.addWidget(btn_copy)
        lay.addLayout(bot)

    def append(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.txt.appendPlainText(f"[{ts}] {msg}")
        self.txt.moveCursor(QTextCursor.End)

    def append_raw(self, msg: str):
        self.txt.appendPlainText(msg)
        self.txt.moveCursor(QTextCursor.End)


# ──────────────────────────────────────────────────────────────
# 启动 Tab
# ──────────────────────────────────────────────────────────────
class StartupTab(QWidget):
    sig_python_ok = pyqtSignal(str)

    def __init__(self, cmd_panel: CmdPanel):
        super().__init__()
        self._cmd = cmd_panel
        self._check_worker = None
        self._selected_exe = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        title = QLabel("SD Mini — 环境启动")
        title.setStyleSheet(SECTION_TITLE_QSS)
        lay.addWidget(title)
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(SEPARATOR_QSS); lay.addWidget(sep)

        gb = QGroupBox("选择 Python 环境"); gb.setProperty("titleVariant","accent")
        vb = QVBoxLayout(gb)

        hint = QLabel("直接使用 A1111 或 ComfyUI 的 Python，已内置 torch + CUDA，无需重装。")
        hint.setStyleSheet(TIPS_QSS); hint.setWordWrap(True)
        vb.addWidget(hint)

        lbl_q = QLabel("快速选择："); lbl_q.setStyleSheet(TEXT_STYLE)
        vb.addWidget(lbl_q)
        self.combo_known = QComboBox(); self.combo_known.setStyleSheet(LINEEDIT_STYLE)
        self.combo_known.addItem("— 手动输入 —", "")
        for p in _KNOWN_PYTHONS:
            icon = "✅" if os.path.isfile(p) else "✗ "
            self.combo_known.addItem(f"{icon}  {p}", p)
        self.combo_known.currentIndexChanged.connect(self._on_quick_select)
        vb.addWidget(self.combo_known)

        r = QHBoxLayout()
        lbl_p = QLabel("路径："); lbl_p.setStyleSheet(TEXT_STYLE); lbl_p.setFixedWidth(48)
        self.py_path = QLineEdit(); self.py_path.setStyleSheet(LINEEDIT_STYLE)
        self.py_path.setPlaceholderText(r"D:\sd-webui-aki-v4.10\python\python.exe")
        btn_b = QPushButton("浏览"); btn_b.setStyleSheet(BUTTON_STYLE)
        btn_b.clicked.connect(self._browse)
        r.addWidget(lbl_p); r.addWidget(self.py_path,1); r.addWidget(btn_b)
        vb.addLayout(r)
        lay.addWidget(gb)

        self.btn_check = QPushButton("🔍  检测环境")
        self.btn_check.setStyleSheet(BUTTON_STYLE); self.btn_check.setFixedHeight(38)
        self.btn_check.clicked.connect(self._run_check)
        lay.addWidget(self.btn_check)

        self.lbl_status = QLabel("尚未检测")
        self.lbl_status.setStyleSheet(STATUS_NEUTRAL_QSS)
        lay.addWidget(self.lbl_status)

        self.btn_confirm = QPushButton("✅  确认使用此环境，前往生成")
        self.btn_confirm.setStyleSheet(BUTTON_STYLE); self.btn_confirm.setFixedHeight(40)
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.clicked.connect(self._confirm)
        lay.addWidget(self.btn_confirm)

        gb_tip = QGroupBox("常见问题"); gb_tip.setProperty("titleVariant","accent")
        vb2 = QVBoxLayout(gb_tip)
        tips = QLabel(
            "A1111 Python：<b>D:\\sd-webui-aki-v4.10\\python\\python.exe</b><br>"
            "ComfyUI venv：<b>D:\\ComfyUI\\ComfyUI\\venv\\Scripts\\python.exe</b><br><br>"
            "检测失败？<br>"
            "① WinError 1114 → 换另一个环境（ComfyUI venv 试试）<br>"
            "② 缺少 diffusers → 在该环境运行：<br>"
            "&nbsp;&nbsp;&nbsp;python -m pip install diffusers transformers accelerate"
        )
        tips.setStyleSheet(TIPS_QSS); tips.setWordWrap(True)
        vb2.addWidget(tips)
        lay.addWidget(gb_tip)
        lay.addStretch()

        # 预填 A1111 路径
        a1111 = r"D:\sd-webui-aki-v4.10\python\python.exe"
        if os.path.isfile(a1111):
            self.py_path.setText(a1111)
            for i in range(self.combo_known.count()):
                if self.combo_known.itemData(i) == a1111:
                    self.combo_known.setCurrentIndex(i); break

    def _on_quick_select(self, idx):
        val = self.combo_known.itemData(idx)
        if val: self.py_path.setText(val)

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(self,"选择 python.exe","","python.exe (python.exe);;所有文件 (*)")
        if f: self.py_path.setText(os.path.normpath(f))

    def _run_check(self):
        exe = self.py_path.text().strip()
        if not exe or not os.path.isfile(exe):
            self.lbl_status.setText("❌ 路径无效"); return
        self.btn_check.setEnabled(False); self.btn_confirm.setEnabled(False)
        self.lbl_status.setText("⏳ 检测中…")
        self.lbl_status.setStyleSheet(STATUS_NEUTRAL_QSS)
        self._cmd.append(f"► 检测环境：{exe}")
        self._check_worker = EnvCheckWorker(exe)
        self._check_worker.sig_line.connect(self._cmd.append_raw)
        self._check_worker.sig_done.connect(self._on_done)
        self._check_worker.start()

    def _on_done(self, ok, summary):
        self.btn_check.setEnabled(True)
        if ok:
            self._selected_exe = self.py_path.text().strip()
            self.lbl_status.setText(f"✅ 环境正常")
            self.lbl_status.setStyleSheet(STATUS_OK_QSS)
            self.btn_confirm.setEnabled(True)
        else:
            self.lbl_status.setText(f"❌ {summary}  ↑ 详情见 CMD 分页")
            self.lbl_status.setStyleSheet(STATUS_ERR_QSS)

    def _confirm(self):
        self.sig_python_ok.emit(self._selected_exe)


# ──────────────────────────────────────────────────────────────
# 生成 Tab
# ──────────────────────────────────────────────────────────────
class GenerateTab(QWidget):
    def __init__(self, cmd_panel: CmdPanel):
        super().__init__()
        self._cmd        = cmd_panel
        self._worker     = None
        self._python_exe = ""          # ← 由启动页传入
        self._last_imgs  = []
        self._last_img   = None
        self._arch       = "sdxl"
        self._preview_idx = 0
        self._save_dir   = os.path.join(os.path.expanduser("~"), "Pictures", "SD_Mini")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8,8,8,8); outer.setSpacing(10)

        # 左列（可滚动）
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(SCROLL_LEFT_QSS)
        lw = QWidget(); lw.setAttribute(Qt.WA_StyledBackground, True)
        left = QVBoxLayout(lw); left.setContentsMargins(0,0,6,0); left.setSpacing(8)
        scroll.setWidget(lw); outer.addWidget(scroll,1)

        right = QVBoxLayout(); right.setSpacing(8); outer.addLayout(right)

        # ── 模型
        gb = QGroupBox("模型"); gb.setProperty("titleVariant","accent")
        vb = QVBoxLayout(gb)
        self.model_combo = QComboBox(); self.model_combo.setStyleSheet(LINEEDIT_STYLE)
        self.model_combo.setPlaceholderText("— 扫描后选择 —")
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        vb.addWidget(self.model_combo)
        r = QHBoxLayout()
        lbl = QLabel("目录："); lbl.setStyleSheet(TEXT_STYLE)
        self.model_dir = QLineEdit(r"D:\sd-webui-aki-v4.10\models\Stable-diffusion")
        self.model_dir.setStyleSheet(LINEEDIT_STYLE)
        b1 = QPushButton("浏览"); b1.setStyleSheet(BUTTON_STYLE); b1.clicked.connect(self._browse_model_dir)
        b2 = QPushButton("扫描"); b2.setStyleSheet(BUTTON_STYLE); b2.clicked.connect(self._scan_models)
        r.addWidget(lbl); r.addWidget(self.model_dir,1); r.addWidget(b1); r.addWidget(b2)
        vb.addLayout(r)
        # 架构识别结果 + 手动覆盖
        r_arch = QHBoxLayout()
        self.arch_tip = QLabel("← 请手动选择架构，右侧自动识别仅供参考")
        self.arch_tip.setStyleSheet(ARCH_HINT_NORMAL_QSS)
        r_arch.addWidget(self.arch_tip, 1)
        lbl_arch_o = QLabel("架构："); lbl_arch_o.setStyleSheet(ARCH_LABEL_QSS)
        self.arch_override = QComboBox(); self.arch_override.setStyleSheet(LINEEDIT_STYLE)
        self.arch_override.setFixedWidth(110)
        self.arch_override.addItems(["SD 1.5", "SDXL", "Flux", "自动识别"])
        self.arch_override.currentIndexChanged.connect(self._on_arch_override)
        r_arch.addWidget(lbl_arch_o); r_arch.addWidget(self.arch_override)
        vb.addLayout(r_arch)
        left.addWidget(gb)

        # ── Prompt
        gb = QGroupBox("Prompt"); gb.setProperty("titleVariant","accent")
        vb = QVBoxLayout(gb)
        self.prompt = QTextEdit(); self.prompt.setStyleSheet(LINEEDIT_STYLE)
        self.prompt.setPlaceholderText("masterpiece, best quality, 1girl, solo, ...")
        self.prompt.setFixedHeight(90); vb.addWidget(self.prompt)
        rn = QHBoxLayout()
        lbl_n = QLabel("Negative prompt"); lbl_n.setStyleSheet(TEXT_STYLE)
        btn_fill = QPushButton("填入常用"); btn_fill.setStyleSheet(BUTTON_STYLE)
        btn_fill.clicked.connect(lambda: self.neg_prompt.setPlainText(_COMMON_NEG))
        rn.addWidget(lbl_n); rn.addStretch(); rn.addWidget(btn_fill); vb.addLayout(rn)
        self.neg_prompt = QTextEdit(); self.neg_prompt.setStyleSheet(LINEEDIT_STYLE)
        self.neg_prompt.setPlaceholderText("worst quality, low quality, ...")
        self.neg_prompt.setFixedHeight(56); vb.addWidget(self.neg_prompt)
        left.addWidget(gb)

        # ── 参数
        gb = QGroupBox("参数"); gb.setProperty("titleVariant","accent")
        vb = QVBoxLayout(gb)

        r = QHBoxLayout()
        l = QLabel("采样器"); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(56)
        self.sampler_combo = QComboBox(); self.sampler_combo.setStyleSheet(LINEEDIT_STYLE)
        self.sampler_combo.addItems(_SAMPLER_LIST); self.sampler_combo.setCurrentText("Euler a")
        r.addWidget(l); r.addWidget(self.sampler_combo,1); vb.addLayout(r)

        def _srow(label, lo, hi, val):
            r = QHBoxLayout()
            l = QLabel(label); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(56)
            s = QSlider(Qt.Horizontal); s.setRange(lo,hi); s.setValue(val)
            lv = QLabel(str(val)); lv.setStyleSheet(TEXT_STYLE); lv.setFixedWidth(30)
            s.valueChanged.connect(lambda v: lv.setText(str(v)))
            r.addWidget(l); r.addWidget(s,1); r.addWidget(lv); vb.addLayout(r)
            return s
        self.slider_steps = _srow("步数",10,50,20)
        self.slider_cfg   = _srow("CFG",1,15,7)

        r = QHBoxLayout()
        l = QLabel("批量张数"); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(60)
        self.spin_batch = QSpinBox(); self.spin_batch.setRange(1,8); self.spin_batch.setValue(1)
        self.spin_batch.setStyleSheet(LINEEDIT_STYLE); self.spin_batch.setFixedWidth(60)
        r.addWidget(l); r.addWidget(self.spin_batch); r.addStretch(); vb.addLayout(r)

        l2 = QLabel("尺寸"); l2.setStyleSheet(TEXT_STYLE); vb.addWidget(l2)
        self._size_wrap = QWidget()
        self._size_container = QHBoxLayout(self._size_wrap)
        self._size_container.setSpacing(4); self._size_container.setContentsMargins(0,0,0,0)
        self.size_btn_group = QButtonGroup(self); self.size_btn_group.setExclusive(True)
        self.size_btns = []; vb.addWidget(self._size_wrap)
        self._build_size_buttons("sdxl")

        r = QHBoxLayout()
        l = QLabel("种子"); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(56)
        self.seed_input = QLineEdit("-1"); self.seed_input.setStyleSheet(LINEEDIT_STYLE)
        self.seed_input.setFixedWidth(120)
        br = QPushButton("随机"); br.setStyleSheet(BUTTON_STYLE)
        br.clicked.connect(lambda: self.seed_input.setText(str(random.randint(0,2**31))))
        lh = QLabel("-1 = 随机"); lh.setStyleSheet(HINT_LABEL_QSS)
        r.addWidget(l); r.addWidget(self.seed_input); r.addWidget(br); r.addWidget(lh); r.addStretch()
        vb.addLayout(r)

        r = QHBoxLayout()
        l = QLabel("保存至"); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(56)
        self.save_dir_input = QLineEdit(self._save_dir); self.save_dir_input.setStyleSheet(LINEEDIT_STYLE)
        bs = QPushButton("浏览"); bs.setStyleSheet(BUTTON_STYLE); bs.clicked.connect(self._choose_save_dir)
        r.addWidget(l); r.addWidget(self.save_dir_input,1); r.addWidget(bs); vb.addLayout(r)
        left.addWidget(gb)

        # ── 加速
        gb = QGroupBox("加速 / 显存"); gb.setProperty("titleVariant","accent")
        vb_ac = QHBoxLayout(gb)
        self.chk_cpu_offload = QCheckBox("CPU Offload（低显存必开）"); self.chk_cpu_offload.setStyleSheet(TEXT_STYLE)
        self.chk_xformers    = QCheckBox("xformers 加速"); self.chk_xformers.setStyleSheet(TEXT_STYLE)
        vb_ac.addWidget(self.chk_cpu_offload); vb_ac.addSpacing(20)
        vb_ac.addWidget(self.chk_xformers); vb_ac.addStretch()
        left.addWidget(gb)

        # ── 生成按钮 + 进度条
        self.btn_generate = QPushButton("▶  开始生成")
        self.btn_generate.setStyleSheet(BUTTON_STYLE); self.btn_generate.setFixedHeight(40)
        self.btn_generate.clicked.connect(self._start_generate)
        left.addWidget(self.btn_generate)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0,100); self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(PROGRESS_QSS)
        self.progress_bar.setFixedHeight(16)
        left.addWidget(self.progress_bar)
        left.addStretch()

        # ── 右列：预览
        gb = QGroupBox("预览"); gb.setProperty("titleVariant","accent")
        vb = QVBoxLayout(gb)
        self.preview_label = QLabel("生成后显示")
        self.preview_label.setAlignment(Qt.AlignCenter); self.preview_label.setFixedSize(300,300)
        self.preview_label.setStyleSheet(PREVIEW_PLACEHOLDER_QSS)
        vb.addWidget(self.preview_label,0,Qt.AlignHCenter)

        r_nav = QHBoxLayout()
        self.btn_prev_img = QPushButton("◀"); self.btn_prev_img.setStyleSheet(BUTTON_STYLE)
        self.btn_prev_img.setEnabled(False); self.btn_prev_img.clicked.connect(self._prev_img)
        self.lbl_img_idx = QLabel(""); self.lbl_img_idx.setStyleSheet(TEXT_STYLE)
        self.lbl_img_idx.setAlignment(Qt.AlignCenter)
        self.btn_next_img = QPushButton("▶"); self.btn_next_img.setStyleSheet(BUTTON_STYLE)
        self.btn_next_img.setEnabled(False); self.btn_next_img.clicked.connect(self._next_img)
        r_nav.addWidget(self.btn_prev_img); r_nav.addStretch()
        r_nav.addWidget(self.lbl_img_idx); r_nav.addStretch(); r_nav.addWidget(self.btn_next_img)
        vb.addLayout(r_nav)

        r_img = QHBoxLayout()
        self.btn_save_img = QPushButton("保存副本"); self.btn_save_img.setStyleSheet(BUTTON_STYLE)
        self.btn_save_img.setEnabled(False); self.btn_save_img.clicked.connect(self._save_copy)
        self.btn_open_dir = QPushButton("打开目录"); self.btn_open_dir.setStyleSheet(BUTTON_STYLE)
        self.btn_open_dir.setEnabled(False); self.btn_open_dir.clicked.connect(self._open_output_dir)
        r_img.addWidget(self.btn_save_img); r_img.addWidget(self.btn_open_dir)
        vb.addLayout(r_img); right.addWidget(gb)

        gb = QGroupBox("信息"); gb.setProperty("titleVariant","accent")
        vb_info = QVBoxLayout(gb)
        def _row(label):
            r = QHBoxLayout()
            l = QLabel(label); l.setStyleSheet(META_LABEL_QSS)
            v = QLabel("—"); v.setStyleSheet(META_VALUE_QSS)
            v.setAlignment(Qt.AlignRight)
            r.addWidget(l); r.addStretch(); r.addWidget(v); vb_info.addLayout(r); return v
        self.info_time = _row("耗时")
        self.info_seed = _row("种子")
        self.info_path = _row("文件名")
        right.addWidget(gb); right.addStretch()

    def set_python_exe(self, exe: str):
        """由主页调用，设置要使用的 Python 路径"""
        self._python_exe = exe
        self._log(f"✅ 已绑定 Python：{exe}")

    # ── 尺寸按钮
    _SN = TAB_BTN_NORMAL
    _SC = TAB_BTN_SELECTED

    def _build_size_buttons(self, arch):
        for b in self.size_btns:
            self.size_btn_group.removeButton(b)
            self._size_container.removeWidget(b); b.deleteLater()
        self.size_btns.clear()
        for i,(ratio,w,h) in enumerate(_SIZES.get(arch, _SIZES["sdxl"])):
            btn = QPushButton(f"{ratio}\n{w}×{h}"); btn.setCheckable(True); btn.setChecked(i==0)
            btn.setFixedHeight(44); btn.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            btn.setProperty("_w",w); btn.setProperty("_h",h)
            btn.setStyleSheet(self._SC if i==0 else self._SN)
            btn.toggled.connect(lambda c,b=btn: b.setStyleSheet(self._SC if c else self._SN))
            self.size_btn_group.addButton(btn); self._size_container.addWidget(btn); self.size_btns.append(btn)

    def _get_size(self):
        b = self.size_btn_group.checkedButton()
        return (b.property("_w"),b.property("_h")) if b else (512,512)

    def _browse_model_dir(self):
        d = QFileDialog.getExistingDirectory(self,"选择模型目录")
        if d: self.model_dir.setText(os.path.normpath(d))

    def _scan_models(self):
        d = self.model_dir.text().strip()
        if not os.path.isdir(d): self._log(f"❌ 目录不存在：{d}"); return
        found = []
        for ext in ["*.safetensors","*.ckpt","*.pt"]:
            found += glob.glob(os.path.join(d,ext))
            found += glob.glob(os.path.join(d,"**",ext),recursive=True)
        found = sorted(set(found))
        if not found: self._log("⚠️ 未找到模型文件"); return
        self.model_combo.blockSignals(True); self.model_combo.clear()
        for f in found: self.model_combo.addItem(os.path.basename(f),f)
        self.model_combo.blockSignals(False)
        self.model_combo.setCurrentIndex(0); self._on_model_changed(0)
        self._log(f"✅ 找到 {len(found)} 个模型")

    def _on_model_changed(self, idx):
        if idx < 0 or self.model_combo.count()==0: return
        name = self.model_combo.currentText()
        auto_arch = _guess_arch(name)
        override_map = {"SD 1.5": "sd15", "SDXL": "sdxl", "Flux": "flux"}
        override_text = self.arch_override.currentText()
        if override_text in override_map:
            # 用户手动选了架构，以手动为准
            arch = override_map[override_text]
            self.arch_tip.setText(f"自动识别为 {auto_arch.upper()}")
            self.arch_tip.setStyleSheet(ARCH_HINT_NORMAL_QSS)
        else:
            # "自动识别"选项，才用自动
            arch = auto_arch
            self.arch_tip.setText(f"自动识别：{arch.upper()}")
            self.arch_tip.setStyleSheet(ARCH_HINT_WARN_QSS)
        self._arch = arch
        is_flux = arch=="flux"
        self.slider_cfg.setEnabled(not is_flux)
        if is_flux:
            self.slider_cfg.setValue(1)
            self.sampler_combo.clear(); self.sampler_combo.addItems(_SAMPLERS_FLUX)
        else:
            self.sampler_combo.clear(); self.sampler_combo.addItems(_SAMPLER_LIST)
            self.sampler_combo.setCurrentText("Euler a")
        self._build_size_buttons(arch)
        self._log(f"📦 {name} → {arch.upper()}" + ("（手动）" if override_text in override_map else "（自动）"))

    def _on_arch_override(self, idx):
        """用户切换架构下拉时立即生效"""
        override_map = {"SD 1.5": "sd15", "SDXL": "sdxl", "Flux": "flux"}
        override_text = self.arch_override.currentText()
        if override_text in override_map:
            arch = override_map[override_text]
            self._arch = arch
            is_flux = arch=="flux"
            self.slider_cfg.setEnabled(not is_flux)
            if is_flux:
                self.slider_cfg.setValue(1)
                self.sampler_combo.clear(); self.sampler_combo.addItems(_SAMPLERS_FLUX)
            else:
                self.sampler_combo.clear(); self.sampler_combo.addItems(_SAMPLER_LIST)
                self.sampler_combo.setCurrentText("Euler a")
            self._build_size_buttons(arch)
            self._log(f"🔧 架构手动切换为 {arch.upper()}")
        elif self.model_combo.count() > 0:
            self._on_model_changed(self.model_combo.currentIndex())

    def _start_generate(self):
        if not self._python_exe:
            self._log("❌ 未设置 Python 路径，请回到「启动」分页确认环境"); return
        if self._worker and self._worker.isRunning():
            self._log("⚠️ 正在生成中，请稍候..."); return
        model_path = self.model_combo.currentData()
        if not model_path or not os.path.isfile(model_path):
            self._log("❌ 请先扫描并选择模型"); return
        if not self.prompt.toPlainText().strip():
            self._log("❌ Prompt 不能为空"); return
        try: seed = int(self.seed_input.text())
        except ValueError: seed = -1
        w,h = self._get_size()
        params = dict(
            model_path=model_path, arch=self._arch,
            prompt=self.prompt.toPlainText().strip(),
            negative_prompt=self.neg_prompt.toPlainText().strip(),
            sampler=self.sampler_combo.currentText(),
            steps=self.slider_steps.value(), cfg=self.slider_cfg.value(),
            width=w, height=h, seed=seed,
            save_dir=self.save_dir_input.text().strip() or self._save_dir,
            batch=self.spin_batch.value(),
            cpu_offload=self.chk_cpu_offload.isChecked(),
            use_xformers=self.chk_xformers.isChecked(),
        )
        self.progress_bar.setValue(0)
        self.btn_generate.setEnabled(False); self.btn_generate.setText("⏳ 生成中...")
        self.preview_label.setText("生成中，请稍候...")

        # ← 把 A1111 python 路径传给 Worker
        self._worker = GenerateWorker(self._python_exe, params)
        self._worker.sig_log.connect(self._log)
        self._worker.sig_progress.connect(self.progress_bar.setValue)
        self._worker.sig_finished.connect(self._on_finished)
        self._worker.sig_error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, paths, elapsed, seed):
        self._last_imgs=paths; self._last_img=paths[0] if paths else None; self._preview_idx=0
        self.btn_generate.setEnabled(True); self.btn_generate.setText("▶  开始生成")
        self.btn_save_img.setEnabled(True); self.btn_open_dir.setEnabled(True)
        has_many=len(paths)>1
        self.btn_prev_img.setEnabled(has_many); self.btn_next_img.setEnabled(has_many)
        self.info_time.setText(f"{elapsed:.1f} s"); self.info_seed.setText(str(seed))
        self.info_path.setText(os.path.basename(paths[0]) if paths else "—")
        self._show_preview(0)
        self._log(f"🎉 完成！{len(paths)} 张  {elapsed:.1f}s  seed={seed}")

    def _show_preview(self, idx):
        if not self._last_imgs: return
        idx=max(0,min(idx,len(self._last_imgs)-1))
        self._preview_idx=idx; self._last_img=self._last_imgs[idx]
        self.lbl_img_idx.setText(f"{idx+1}/{len(self._last_imgs)}")
        px=QPixmap(self._last_img)
        if not px.isNull():
            px=px.scaled(self.preview_label.width(),self.preview_label.height(),
                         Qt.KeepAspectRatio,Qt.SmoothTransformation)
            self.preview_label.setPixmap(px)

    def _prev_img(self): self._show_preview(self._preview_idx-1)
    def _next_img(self): self._show_preview(self._preview_idx+1)

    def _on_error(self, msg):
        self.btn_generate.setEnabled(True); self.btn_generate.setText("▶  开始生成")
        self.preview_label.setText("生成失败"); self.progress_bar.setValue(0)
        for line in msg.splitlines():
            if line.strip(): self._log(f"❌ {line}")

    def _choose_save_dir(self):
        d=QFileDialog.getExistingDirectory(self,"选择保存目录")
        if d: self.save_dir_input.setText(os.path.normpath(d))

    def _save_copy(self):
        if not self._last_img or not os.path.isfile(self._last_img): return
        dst,_=QFileDialog.getSaveFileName(self,"另存为",self._last_img,"PNG (*.png);;JPEG (*.jpg)")
        if dst: shutil.copy2(self._last_img,dst); self._log(f"📁 另存为：{dst}")

    def _open_output_dir(self):
        d=self.save_dir_input.text().strip() or self._save_dir
        if not os.path.isdir(d): self._log(f"❌ 目录不存在：{d}"); return
        try:
            s=platform.system()
            if s=="Windows": subprocess.Popen(["explorer",os.path.normpath(d)])
            elif s=="Darwin": subprocess.Popen(["open",d])
            else: subprocess.Popen(["xdg-open",d])
        except Exception as e: self._log(f"⚠️ 打开失败：{e}")

    def _log(self, msg): self._cmd.append(msg)


# ──────────────────────────────────────────────────────────────
# 主 Widget
# ──────────────────────────────────────────────────────────────
class PageSdMini(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TABS_QSS)
        lay.addWidget(self.tabs)

        self._cmd = CmdPanel()

        self._startup_tab = StartupTab(self._cmd)
        self._startup_tab.sig_python_ok.connect(self._on_python_confirmed)
        self.tabs.addTab(self._startup_tab, "🚀  启动")

        self._gen_tab = GenerateTab(self._cmd)
        self.tabs.addTab(self._gen_tab, "🎨  生成")
        self.tabs.addTab(self._cmd, "🖥️  CMD 输出")

        self.tabs.setTabEnabled(1, False)
        self._cmd.append("欢迎使用 SD Mini！请先在「启动」分页检测并确认环境。")

    def _on_python_confirmed(self, exe: str):
        # 把确认的 Python 路径传给生成 Tab
        self._gen_tab.set_python_exe(exe)
        self.tabs.setTabEnabled(1, True)
        self.tabs.setCurrentIndex(1)
        self._cmd.append(f"✅ Python 已绑定：{exe}")
        self._cmd.append("► 前往「生成」分页开始生图")
