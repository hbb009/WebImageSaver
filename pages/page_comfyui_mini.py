"""
page_comfyui_mini.py  —  ComfyUI Mini（图生图）
界面三分页：启动 / 改图 / CMD输出

核心架构：
  启动页  → 一键启动 / 停止本地 ComfyUI 进程，检测 API 可用性
  改图页  → 上传参考图 + Prompt + 参数 → 调用 ComfyUI HTTP API
  CMD页   → 所有日志、错误、进度实时显示
"""

from styles.common_styles import TEXT_STYLE, BUTTON_STYLE, LINEEDIT_STYLE

import os, sys, json, glob, random, shutil, platform, subprocess, time, urllib.request, urllib.error
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QComboBox, QSlider,
    QGroupBox, QFileDialog, QSizePolicy, QButtonGroup,
    QScrollArea, QSpinBox, QDoubleSpinBox, QCheckBox, QProgressBar,
    QTabWidget, QPlainTextEdit, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap, QFont, QTextCursor

# ──────────────────────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────────────────────
_COMFYUI_DIR    = r"D:\ComfyUI\ComfyUI"
_VENV_PYTHON    = os.path.join(_COMFYUI_DIR, "venv", "Scripts", "python.exe")
_COMFYUI_MAIN   = os.path.join(_COMFYUI_DIR, "main.py")
_API_BASE        = "http://127.0.0.1:8188"

_MODEL_DIR_DIFF = os.path.join(_COMFYUI_DIR, "models", "diffusion_models", "flux2")
_MODEL_DIR_CLIP = os.path.join(_COMFYUI_DIR, "models", "clip")
_MODEL_DIR_VAE  = os.path.join(_COMFYUI_DIR, "models", "vae")

# Flux img2img 推荐采样器
_FLUX_SAMPLERS  = ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_sde"]
_FLUX_SCHEDULERS = ["simple", "normal", "karras", "sgm_uniform"]

# 输出尺寸预设（Flux 推荐 1024 起步）
_SIZES = [
    ("1:1",  1024, 1024),
    ("4:3",  1152, 896),
    ("3:2",  1216, 832),
    ("2:3",  832,  1216),
    ("9:16", 768,  1344),
    ("16:9", 1344, 768),
]

# 默认模型文件名（与实际文件名对齐）
_DEFAULT_DIFF = "flux-2-klein-9b-fp8.safetensors"
_DEFAULT_CLIP1 = "t5xxl_fp8_e4m3fn.safetensors"
_DEFAULT_CLIP2 = "clip_l.safetensors"
_DEFAULT_VAE   = "flux2-vae.safetensors"


# ──────────────────────────────────────────────────────────────
# CMD 面板（黑底绿字）—— 与 SD Mini 相同风格
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
# API 检测 Worker
# ──────────────────────────────────────────────────────────────
class ApiCheckWorker(QThread):
    sig_result = pyqtSignal(bool, str)   # (ok, message)

    def run(self):
        try:
            req = urllib.request.urlopen(f"{_API_BASE}/system_stats", timeout=4)
            data = json.loads(req.read())
            gpu = data.get("devices", [{}])[0].get("name", "未知 GPU")
            vram = data.get("devices", [{}])[0].get("vram_total", 0)
            vram_gb = round(vram / 1024 / 1024 / 1024, 1) if vram else "?"
            self.sig_result.emit(True, f"{gpu}  {vram_gb} GB")
        except Exception as e:
            self.sig_result.emit(False, str(e))


# ──────────────────────────────────────────────────────────────
# ComfyUI 进程启动 Worker（读取 stdout 转发到 CMD）
# ──────────────────────────────────────────────────────────────
class ComfyLaunchWorker(QThread):
    sig_line   = pyqtSignal(str)
    sig_ready  = pyqtSignal()    # 检测到 "To see the GUI go to:" 时发射

    def __init__(self, python_exe: str, comfyui_dir: str):
        super().__init__()
        self.python_exe  = python_exe
        self.comfyui_dir = comfyui_dir
        self._proc       = None

    def run(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        # 禁用 tqdm 的终端彩色输出，防止 colorama 写 stdout 时因管道报 [Errno 22]
        env["NO_COLOR"]    = "1"
        env["TERM"]        = "dumb"
        env["FORCE_COLOR"] = "0"
        try:
            self._proc = subprocess.Popen(
                [self.python_exe, _COMFYUI_MAIN, "--disable-metadata"],
                cwd=self.comfyui_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env,
            )
            for line in self._proc.stdout:
                line = line.rstrip()
                if line:
                    self.sig_line.emit(line)
                if "To see the GUI go to:" in line or "Starting server" in line:
                    self.sig_ready.emit()
            self._proc.wait()
        except Exception as e:
            self.sig_line.emit(f"❌ 启动失败：{e}")

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


# ──────────────────────────────────────────────────────────────
# 生图 Worker —— 调用 ComfyUI HTTP API
# ──────────────────────────────────────────────────────────────
class ComfyGenWorker(QThread):
    sig_log      = pyqtSignal(str)
    sig_progress = pyqtSignal(int)
    sig_finished = pyqtSignal(list, float)   # (image_paths, elapsed)
    sig_error    = pyqtSignal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.p = params
        self._stop_flag = False   # 用独立名字，避免和任何属性冲突

    # ── 工具方法 ──────────────────────
    def _post_json(self, path: str, data: dict) -> dict:
        body = json.dumps(data).encode("utf-8")
        req  = urllib.request.Request(
            f"{_API_BASE}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def _upload_image(self, filepath: str) -> str:
        """上传参考图，返回 ComfyUI 内部文件名"""
        import uuid, mimetypes
        boundary = uuid.uuid4().hex
        filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            file_data = f.read()
        mime = mimetypes.guess_type(filepath)[0] or "image/png"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            f"{_API_BASE}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["name"]

    def _build_workflow(self, uploaded_name: str) -> dict:
        """
        构建 Flux2 Klein img2img workflow
        严格对齐从 ComfyUI 导出的真实 API Format JSON，节点编号与原文件一致。

        节点链路：
          LoadImage(76) → ImageScaleToTotalPixels(143) → GetImageSize(144)
                                                        ↓
          UNETLoader(137)                        VAEEncode(146) → ReferenceLatent(145/147)
          CLIPLoader(138) → CLIPTextEncode(139/140)              ↓
          VAELoader(141)                         EmptyFlux2LatentImage(142)
                  ↓                                              ↓
          CFGGuider(133) ← model(137) + positive(147) + negative(145)
          KSamplerSelect(131) + Flux2Scheduler(132) + RandomNoise(136)
                  ↓
          SamplerCustomAdvanced(134) → VAEDecode(135) → SaveImage(9)
        """
        p   = self.p
        seed = p["seed"] if p["seed"] != -1 else random.randint(0, 2**31)
        self._actual_seed = seed

        wf = {
            # ── 加载参考图
            "76": {
                "class_type": "LoadImage",
                "inputs": {"image": uploaded_name},
                "_meta": {"title": "加载图像"}
            },
            # ── 缩放到 1MP，自动保持比例
            "143": {
                "class_type": "ImageScaleToTotalPixels",
                "inputs": {
                    "upscale_method":   "lanczos",
                    "megapixels":       1,
                    "resolution_steps": 1,
                    "image":            ["76", 0],
                },
                "_meta": {"title": "缩放图像（像素）"}
            },
            # ── 读取缩放后的尺寸（供 Scheduler 和 EmptyLatent 使用）
            "144": {
                "class_type": "GetImageSize",
                "inputs": {"image": ["143", 0]},
                "_meta": {"title": "获取图像尺寸"}
            },
            # ── 加载 UNet 扩散模型
            "137": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name":    p["diff_model"],   # flux2\flux-2-klein-9b-fp8.safetensors
                    "weight_dtype": "default",
                },
                "_meta": {"title": "UNet加载器"}
            },
            # ── 加载单 CLIP（Flux2 用 qwen，不是双CLIP）
            "138": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": p["clip1"],            # qwen_3_8b_fp8mixed.safetensors
                    "type":      "flux2",
                    "device":    "default",
                },
                "_meta": {"title": "加载CLIP"}
            },
            # ── 正向 Prompt
            "139": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": p["prompt"],
                    "clip": ["138", 0],
                },
                "_meta": {"title": "CLIP Text Encode (Positive Prompt)"}
            },
            # ── 负向 Prompt（Flux2 通常留空）
            "140": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": p.get("negative_prompt", ""),
                    "clip": ["138", 0],
                },
                "_meta": {"title": "CLIP Text Encode (Negative Prompt)"}
            },
            # ── 加载 VAE
            "141": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": p["vae"]},
                "_meta": {"title": "加载VAE"}
            },
            # ── VAE 编码参考图 → 潜空间
            "146": {
                "class_type": "VAEEncode",
                "inputs": {
                    "pixels": ["143", 0],
                    "vae":    ["141", 0],
                },
                "_meta": {"title": "VAE编码"}
            },
            # ── 空 Flux2 Latent（尺寸来自参考图）
            "142": {
                "class_type": "EmptyFlux2LatentImage",
                "inputs": {
                    "width":      ["144", 0],
                    "height":     ["144", 1],
                    "batch_size": 1,
                },
                "_meta": {"title": "空Latent图像（Flux2）"}
            },
            # ── 正向参考Latent（把参考图编码注入正向条件）
            "147": {
                "class_type": "ReferenceLatent",
                "inputs": {
                    "conditioning": ["139", 0],
                    "latent":       ["146", 0],
                },
                "_meta": {"title": "参考Latent（正向）"}
            },
            # ── 负向参考Latent
            "145": {
                "class_type": "ReferenceLatent",
                "inputs": {
                    "conditioning": ["140", 0],
                    "latent":       ["146", 0],
                },
                "_meta": {"title": "参考Latent（负向）"}
            },
            # ── 随机噪波（种子）
            "136": {
                "class_type": "RandomNoise",
                "inputs": {"noise_seed": seed},
                "_meta": {"title": "随机噪波"}
            },
            # ── 采样器选择
            "131": {
                "class_type": "KSamplerSelect",
                "inputs": {"sampler_name": p["sampler"]},
                "_meta": {"title": "K采样器选择"}
            },
            # ── Flux2 调度器（步数 + 尺寸）
            "132": {
                "class_type": "Flux2Scheduler",
                "inputs": {
                    "steps":  p["steps"],
                    "width":  ["144", 0],
                    "height": ["144", 1],
                },
                "_meta": {"title": "Flux2调度器"}
            },
            # ── CFG 引导器
            "133": {
                "class_type": "CFGGuider",
                "inputs": {
                    "cfg":      p.get("cfg", 5),
                    "model":    ["137", 0],
                    "positive": ["147", 0],
                    "negative": ["145", 0],
                },
                "_meta": {"title": "CFG引导器"}
            },
            # ── 高级自定义采样器（主采样节点）
            "134": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise":        ["136", 0],
                    "guider":       ["133", 0],
                    "sampler":      ["131", 0],
                    "sigmas":       ["132", 0],
                    "latent_image": ["142", 0],
                },
                "_meta": {"title": "自定义采样器（高级）"}
            },
            # ── VAE 解码
            "135": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["134", 0],
                    "vae":     ["141", 0],
                },
                "_meta": {"title": "VAE解码"}
            },
            # ── 保存图片
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "ComfyMini",
                    "images":          ["135", 0],
                },
                "_meta": {"title": "保存图像"}
            },
        }
        return wf

    def _poll_until_done(self, prompt_id: str) -> list:
        """
        轮询 ComfyUI 直到生成完成，返回输出图片信息列表。
        策略：先查队列确认任务存在，再反复查 history，错误全部打日志不吞掉。
        """
        self.sig_log.emit(f"⏳ 等待生成完成（prompt_id={prompt_id[:8]}…）")

        # 先确认任务进入队列
        try:
            with urllib.request.urlopen(f"{_API_BASE}/queue", timeout=10) as r:
                q = json.loads(r.read())
            running  = [t for t in q.get("queue_running", []) if len(t) > 1 and t[1] == prompt_id]
            pending  = [t for t in q.get("queue_pending", []) if len(t) > 1 and t[1] == prompt_id]
            self.sig_log.emit(f"   队列状态：running={len(running)}  pending={len(pending)}")
        except Exception as e:
            self.sig_log.emit(f"   ⚠️ 查询队列失败（不影响生成）：{e}")

        # 轮询 history，最多等 20 分钟
        for i in range(1200):
            if getattr(self, "_stop_flag", False):
                self.sig_log.emit("   已手动停止")
                return []

            time.sleep(1)

            try:
                with urllib.request.urlopen(
                    f"{_API_BASE}/history/{prompt_id}", timeout=15
                ) as r:
                    hist = json.loads(r.read())
            except Exception as e:
                # 打日志但继续等，不要吃掉错误
                if i % 10 == 0:
                    self.sig_log.emit(f"   ⚠️ 第{i}s 查询失败：{e}")
                continue

            if prompt_id not in hist:
                # 任务还在队列里跑，继续等
                if i % 15 == 0 and i > 0:
                    self.sig_log.emit(f"   ⏳ 第{i}s 仍在生成中…")
                self.sig_progress.emit(min(20 + i // 6, 88))
                continue

            # ── 任务完成，解析输出 ──
            entry   = hist[prompt_id]
            status  = entry.get("status", {})
            err     = status.get("messages", [])

            # 检查是否有错误消息
            for msg_type, msg_data in err:
                if msg_type == "execution_error":
                    self.sig_log.emit(f"   ❌ ComfyUI 执行错误：{msg_data}")

            outputs = entry.get("outputs", {})
            self.sig_log.emit(f"   输出节点数：{len(outputs)}  节点ID：{list(outputs.keys())}")

            images = []
            for node_id, node_out in outputs.items():
                imgs = node_out.get("images", [])
                self.sig_log.emit(f"   节点{node_id} 图片数：{len(imgs)}")
                for img in imgs:
                    images.append(img)

            if images:
                self.sig_log.emit(f"   ✅ 获取到 {len(images)} 张图片")
                return images
            else:
                self.sig_log.emit(f"   ⚠️ 任务完成但输出为空，完整输出：{json.dumps(outputs)[:300]}")
                return []

        self.sig_log.emit(f"   ❌ 超过20分钟未完成，放弃等待")
        return []

    def _download_images(self, images: list, save_dir: str) -> list:
        """从 ComfyUI 下载生成图片到 save_dir，返回本地路径列表"""
        os.makedirs(save_dir, exist_ok=True)
        paths = []
        for img in images:
            fname    = img["filename"]
            subfolder = img.get("subfolder", "")
            url_params = f"filename={fname}&type=output"
            if subfolder:
                url_params += f"&subfolder={subfolder}"
            url = f"{_API_BASE}/view?{url_params}"
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = os.path.join(save_dir, f"ComfyMini_{ts}_{fname}")
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    with open(dest, "wb") as f:
                        f.write(r.read())
                paths.append(dest)
                self.sig_log.emit(f"✅ 已保存：{os.path.basename(dest)}")
            except Exception as e:
                self.sig_log.emit(f"⚠️ 下载图片失败：{e}")
        return paths

    # ── 主流程 ───────────────────────
    def stop(self):
        self._stop_flag = True

    def run(self):
        self._stop_flag = False
        t0 = time.time()
        try:
            p = self.p

            # ① 上传参考图
            self.sig_log.emit(f"📤 上传参考图：{os.path.basename(p['input_image'])}")
            uploaded_name = self._upload_image(p["input_image"])
            self.sig_log.emit(f"   → ComfyUI 文件名：{uploaded_name}")
            self.sig_progress.emit(10)

            # ② 构建并提交 workflow
            self.sig_log.emit("📋 提交 workflow…")
            wf = self._build_workflow(uploaded_name)
            resp = self._post_json("/prompt", {"prompt": wf})
            prompt_id = resp.get("prompt_id")
            if not prompt_id:
                self.sig_error.emit(f"提交 workflow 失败：{resp}")
                return
            self.sig_log.emit(f"   → prompt_id={prompt_id}")
            self.sig_progress.emit(20)

            # ③ 轮询完成
            images = self._poll_until_done(prompt_id)
            if not images:
                self.sig_error.emit("超时或未获得输出图片")
                return
            self.sig_progress.emit(92)

            # ④ 下载图片
            paths = self._download_images(images, p["save_dir"])
            if not paths:
                self.sig_error.emit("图片下载失败")
                return

            elapsed = time.time() - t0
            self.sig_progress.emit(100)
            self.sig_finished.emit(paths, elapsed)

        except Exception as e:
            import traceback
            self.sig_error.emit(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ──────────────────────────────────────────────────────────────
# 启动 Tab
# ──────────────────────────────────────────────────────────────
class StartupTab(QWidget):
    sig_api_ok = pyqtSignal()   # ComfyUI API 可用时发射

    def __init__(self, cmd_panel: CmdPanel):
        super().__init__()
        self._cmd            = cmd_panel
        self._launch_worker  = None
        self._check_worker   = None
        self._api_ok         = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        title = QLabel("ComfyUI Mini — 启动控制")
        title.setStyleSheet("color:#9fb0d7;font-size:18px;font-weight:bold;")
        lay.addWidget(title)
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#2d3d5a;"); lay.addWidget(sep)

        # ── ComfyUI 目录
        gb = QGroupBox("ComfyUI 路径"); gb.setProperty("titleVariant", "accent")
        vb = QVBoxLayout(gb)

        r = QHBoxLayout()
        lbl = QLabel("目录："); lbl.setStyleSheet(TEXT_STYLE); lbl.setFixedWidth(80)
        self.dir_input = QLineEdit(_COMFYUI_DIR); self.dir_input.setStyleSheet(LINEEDIT_STYLE)
        btn_browse = QPushButton("浏览"); btn_browse.setStyleSheet(BUTTON_STYLE)
        btn_browse.clicked.connect(self._browse_dir)
        r.addWidget(lbl); r.addWidget(self.dir_input, 1); r.addWidget(btn_browse)
        vb.addLayout(r)

        r2 = QHBoxLayout()
        lbl2 = QLabel("Python："); lbl2.setStyleSheet(TEXT_STYLE); lbl2.setFixedWidth(80)
        self.py_input = QLineEdit(_VENV_PYTHON); self.py_input.setStyleSheet(LINEEDIT_STYLE)
        btn_py = QPushButton("浏览"); btn_py.setStyleSheet(BUTTON_STYLE)
        btn_py.clicked.connect(self._browse_python)
        r2.addWidget(lbl2); r2.addWidget(self.py_input, 1); r2.addWidget(btn_py)
        vb.addLayout(r2)
        lay.addWidget(gb)

        # ── 启动 / 停止按钮
        btn_row = QHBoxLayout(); btn_row.setSpacing(10)

        self.btn_launch = QPushButton("▶  启动 ComfyUI")
        self.btn_launch.setStyleSheet(BUTTON_STYLE); self.btn_launch.setFixedHeight(42)
        self.btn_launch.clicked.connect(self._launch)
        btn_row.addWidget(self.btn_launch)

        self.btn_comfy_stop = QPushButton("■  停止 ComfyUI")
        self.btn_comfy_stop.setStyleSheet(BUTTON_STYLE); self.btn_comfy_stop.setFixedHeight(42)
        self.btn_comfy_stop.setEnabled(False)
        self.btn_comfy_stop.clicked.connect(self._stop_comfy)
        btn_row.addWidget(self.btn_comfy_stop)

        self.btn_check = QPushButton("🔍  检测 API")
        self.btn_check.setStyleSheet(BUTTON_STYLE); self.btn_check.setFixedHeight(42)
        self.btn_check.clicked.connect(self._check_api)
        btn_row.addWidget(self.btn_check)

        lay.addLayout(btn_row)

        # ── 状态
        self.lbl_status = QLabel("尚未检测  |  请先启动 ComfyUI 或检测已运行的实例")
        self.lbl_status.setStyleSheet("color:#4a6080;font-size:13px;")
        lay.addWidget(self.lbl_status)

        # ── 确认按钮
        self.btn_confirm = QPushButton("✅  API 正常，前往改图")
        self.btn_confirm.setStyleSheet(BUTTON_STYLE); self.btn_confirm.setFixedHeight(40)
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.clicked.connect(self._confirm)
        lay.addWidget(self.btn_confirm)

        # ── 提示
        gb_tip = QGroupBox("说明"); gb_tip.setProperty("titleVariant", "accent")
        vb2 = QVBoxLayout(gb_tip)
        tips = QLabel(
            "① <b>启动</b>：先关闭手动开的 ComfyUI，再点此按钮，程序会自动启动并传入正确参数。<br>"
            "② <b>检测</b>：如果你已用本按钮启动了 ComfyUI，等待自动检测即可，无需手动点。<br>"
            "③ <b>停止</b>：关闭 ComfyUI 进程，显存立即释放。<br>"
            "④ ⚠️ 请勿手动启动 ComfyUI 后直接使用，会导致生图时进度条写入错误。"
        )
        tips.setStyleSheet("color:#4a6080;font-size:12px;"); tips.setWordWrap(True)
        vb2.addWidget(tips); lay.addWidget(gb_tip)
        lay.addStretch()

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择 ComfyUI 目录")
        if d: self.dir_input.setText(os.path.normpath(d))

    def _browse_python(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择 python.exe", "", "python.exe (python.exe);;所有文件 (*)")
        if f: self.py_input.setText(os.path.normpath(f))

    def _launch(self):
        py  = self.py_input.text().strip()
        cwd = self.dir_input.text().strip()
        if not os.path.isfile(py):
            self._set_status(False, f"找不到 Python：{py}")
            return
        if not os.path.isfile(_COMFYUI_MAIN):
            self._set_status(False, f"找不到 main.py：{_COMFYUI_MAIN}")
            return
        self.btn_launch.setEnabled(False)
        self.btn_comfy_stop.setEnabled(True)
        self._set_status(None, "⏳ 启动中，请稍候…")
        self._cmd.append(f"► 启动 ComfyUI：{py} {_COMFYUI_MAIN}")

        self._launch_worker = ComfyLaunchWorker(py, cwd)
        self._launch_worker.sig_line.connect(self._cmd.append_raw)
        self._launch_worker.sig_ready.connect(self._on_comfy_ready)
        self._launch_worker.start()

    def _on_comfy_ready(self):
        """ComfyUI 输出了"To see the GUI go to:"，延迟 1.5 秒再检测 API"""
        self._cmd.append("✅ ComfyUI 进程就绪，正在检测 API…")
        QTimer.singleShot(1500, self._check_api)

    def _stop_comfy(self):
        if self._launch_worker and self._launch_worker.isRunning():
            self._cmd.append("■ 正在停止 ComfyUI…")
            self._launch_worker.stop()
            self._launch_worker.wait(3000)
        self.btn_launch.setEnabled(True)
        self.btn_comfy_stop.setEnabled(False)
        self.btn_confirm.setEnabled(False)
        self._api_ok = False
        self._set_status(False, "ComfyUI 已停止，显存已释放")
        self._cmd.append("■ ComfyUI 已停止")

    def _check_api(self):
        self.btn_check.setEnabled(False)
        self._set_status(None, "⏳ 检测 API…")
        self._check_worker = ApiCheckWorker()
        self._check_worker.sig_result.connect(self._on_check_result)
        self._check_worker.start()

    def _on_check_result(self, ok: bool, msg: str):
        self.btn_check.setEnabled(True)
        if ok:
            self._api_ok = True
            self._set_status(True, f"✅ ComfyUI API 正常  |  {msg}")
            self.btn_confirm.setEnabled(True)
            self._cmd.append(f"✅ API 检测通过：{msg}")
        else:
            self._api_ok = False
            self._set_status(False, f"❌ API 无响应  |  {msg}")
            self.btn_confirm.setEnabled(False)
            self._cmd.append(f"❌ API 检测失败：{msg}")

    def _confirm(self):
        self.sig_api_ok.emit()

    def cleanup(self):
        """主窗口关闭时调用，确保子线程全部退出"""
        if self._launch_worker and self._launch_worker.isRunning():
            self._launch_worker.stop()
            self._launch_worker.wait(4000)
        if self._check_worker and self._check_worker.isRunning():
            self._check_worker.wait(2000)

    def _set_status(self, ok, msg):
        self.lbl_status.setText(msg)
        if ok is True:
            self.lbl_status.setStyleSheet("color:#4ac880;font-size:13px;")
        elif ok is False:
            self.lbl_status.setStyleSheet("color:#c04040;font-size:13px;")
        else:
            self.lbl_status.setStyleSheet("color:#9fb0d7;font-size:13px;")


# ──────────────────────────────────────────────────────────────
# 改图 Tab
# ──────────────────────────────────────────────────────────────
class GenerateTab(QWidget):
    def __init__(self, cmd_panel: CmdPanel):
        super().__init__()
        self._cmd         = cmd_panel
        self._worker      = None
        self._last_imgs   = []
        self._last_img    = None
        self._preview_idx = 0
        self._save_dir    = os.path.join(os.path.expanduser("~"), "Pictures", "ComfyUI_Mini")
        self._input_image = ""

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8); outer.setSpacing(10)

        # ── 左列（可滚动）
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QScrollBar:vertical{width:6px;background:#0f1826;}"
            "QScrollBar::handle:vertical{background:#2d3d5a;border-radius:3px;}")
        lw = QWidget(); lw.setAttribute(Qt.WA_StyledBackground, True)
        left = QVBoxLayout(lw); left.setContentsMargins(0, 0, 6, 0); left.setSpacing(8)
        scroll.setWidget(lw); outer.addWidget(scroll, 1)

        right = QVBoxLayout(); right.setSpacing(8); outer.addLayout(right)

        # ── 参考图上传
        gb = QGroupBox("参考图"); gb.setProperty("titleVariant", "accent")
        vb = QVBoxLayout(gb)

        self.input_preview = QLabel("点击选择参考图")
        self.input_preview.setAlignment(Qt.AlignCenter)
        self.input_preview.setFixedHeight(120)
        self.input_preview.setStyleSheet(
            "background:#0a1220;border:1px dashed #2d4a6a;border-radius:4px;"
            "color:#3a5070;font-size:13px;")
        self.input_preview.setCursor(Qt.PointingHandCursor)
        self.input_preview.mousePressEvent = lambda e: self._choose_input_image()
        vb.addWidget(self.input_preview)

        r = QHBoxLayout()
        self.input_path_label = QLabel("未选择"); self.input_path_label.setStyleSheet("color:#4a6080;font-size:11px;")
        btn_choose = QPushButton("选择图片"); btn_choose.setStyleSheet(BUTTON_STYLE)
        btn_choose.clicked.connect(self._choose_input_image)
        r.addWidget(self.input_path_label, 1); r.addWidget(btn_choose)
        vb.addLayout(r)
        left.addWidget(gb)

        # ── 模型选择
        gb = QGroupBox("模型"); gb.setProperty("titleVariant", "accent")
        vb = QVBoxLayout(gb)

        def _model_row(label, directory, default_name):
            r = QHBoxLayout()
            lbl = QLabel(label); lbl.setStyleSheet(TEXT_STYLE); lbl.setFixedWidth(52)
            combo = QComboBox(); combo.setStyleSheet(LINEEDIT_STYLE)
            self._scan_combo(combo, directory, default_name)
            btn = QPushButton("扫描"); btn.setStyleSheet(BUTTON_STYLE); btn.setFixedWidth(48)
            btn.clicked.connect(lambda _, c=combo, d=directory, n=default_name: self._scan_combo(c, d, n))
            r.addWidget(lbl); r.addWidget(combo, 1); r.addWidget(btn)
            vb.addLayout(r)
            return combo

        self.combo_diff  = _model_row("扩散：", _MODEL_DIR_DIFF, _DEFAULT_DIFF)
        self.combo_clip1 = _model_row("CLIP：",  _MODEL_DIR_CLIP, _DEFAULT_CLIP1)
        self.combo_vae   = _model_row("VAE：",   _MODEL_DIR_VAE,  _DEFAULT_VAE)
        left.addWidget(gb)

        # ── Prompt
        gb = QGroupBox("Prompt"); gb.setProperty("titleVariant", "accent")
        vb = QVBoxLayout(gb)
        self.prompt = QTextEdit(); self.prompt.setStyleSheet(LINEEDIT_STYLE)
        self.prompt.setPlaceholderText("描述你想要的效果，Flux 对中文也有一定理解…")
        self.prompt.setFixedHeight(90); vb.addWidget(self.prompt)
        left.addWidget(gb)

        # ── 参数
        gb = QGroupBox("参数"); gb.setProperty("titleVariant", "accent")
        vb = QVBoxLayout(gb)

        # 采样器
        r = QHBoxLayout()
        l = QLabel("采样器"); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(68)
        self.sampler_combo = QComboBox(); self.sampler_combo.setStyleSheet(LINEEDIT_STYLE)
        self.sampler_combo.addItems(_FLUX_SAMPLERS); self.sampler_combo.setCurrentText("euler")
        r.addWidget(l); r.addWidget(self.sampler_combo, 1); vb.addLayout(r)

        # CFG
        r = QHBoxLayout()
        l = QLabel("CFG"); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(68)
        self.spin_cfg = QDoubleSpinBox()
        self.spin_cfg.setRange(1.0, 20.0); self.spin_cfg.setSingleStep(0.5)
        self.spin_cfg.setValue(5.0); self.spin_cfg.setDecimals(1)
        self.spin_cfg.setStyleSheet(LINEEDIT_STYLE); self.spin_cfg.setFixedWidth(72)
        cfg_hint = QLabel("默认 5，越高越贴近 Prompt"); cfg_hint.setStyleSheet("color:#4a6080;font-size:11px;")
        r.addWidget(l); r.addWidget(self.spin_cfg); r.addWidget(cfg_hint); r.addStretch()
        vb.addLayout(r)

        # 步数
        def _srow(label, lo, hi, val):
            r = QHBoxLayout()
            l = QLabel(label); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(68)
            s = QSlider(Qt.Horizontal); s.setRange(lo, hi); s.setValue(val)
            lv = QLabel(str(val)); lv.setStyleSheet(TEXT_STYLE); lv.setFixedWidth(30)
            s.valueChanged.connect(lambda v: lv.setText(str(v)))
            r.addWidget(l); r.addWidget(s, 1); r.addWidget(lv); vb.addLayout(r)
            return s
        self.slider_steps = _srow("步数", 10, 50, 20)

        # 去噪强度（img2img 核心参数）
        r = QHBoxLayout()
        l = QLabel("去噪强度"); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(68)
        self.spin_denoise = QDoubleSpinBox()
        self.spin_denoise.setRange(0.1, 1.0); self.spin_denoise.setSingleStep(0.05)
        self.spin_denoise.setValue(0.65); self.spin_denoise.setDecimals(2)
        self.spin_denoise.setStyleSheet(LINEEDIT_STYLE); self.spin_denoise.setFixedWidth(72)
        hint = QLabel("0.4=微调  0.65=改图  0.9=重绘"); hint.setStyleSheet("color:#4a6080;font-size:11px;")
        r.addWidget(l); r.addWidget(self.spin_denoise); r.addWidget(hint); r.addStretch()
        vb.addLayout(r)

        # 尺寸（自动从参考图获取，无需手动选择）
        size_hint = QLabel("📐 输出尺寸自动跟随参考图（缩放至约 1MP）")
        size_hint.setStyleSheet("color:#4a6080;font-size:11px;"); vb.addWidget(size_hint)

        # 种子
        r = QHBoxLayout()
        l = QLabel("种子"); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(68)
        self.seed_input = QLineEdit("-1"); self.seed_input.setStyleSheet(LINEEDIT_STYLE)
        self.seed_input.setFixedWidth(120)
        br = QPushButton("随机"); br.setStyleSheet(BUTTON_STYLE)
        br.clicked.connect(lambda: self.seed_input.setText(str(random.randint(0, 2**31))))
        lh = QLabel("-1 = 随机"); lh.setStyleSheet("color:#4a6080;font-size:12px;")
        r.addWidget(l); r.addWidget(self.seed_input); r.addWidget(br); r.addWidget(lh); r.addStretch()
        vb.addLayout(r)

        # 保存目录
        r = QHBoxLayout()
        l = QLabel("保存至"); l.setStyleSheet(TEXT_STYLE); l.setFixedWidth(68)
        self.save_dir_input = QLineEdit(self._save_dir); self.save_dir_input.setStyleSheet(LINEEDIT_STYLE)
        bs = QPushButton("浏览"); bs.setStyleSheet(BUTTON_STYLE)
        bs.clicked.connect(self._choose_save_dir)
        r.addWidget(l); r.addWidget(self.save_dir_input, 1); r.addWidget(bs); vb.addLayout(r)
        left.addWidget(gb)

        # ── 生成按钮 + 进度条
        self.btn_generate = QPushButton("▶  开始改图")
        self.btn_generate.setStyleSheet(BUTTON_STYLE); self.btn_generate.setFixedHeight(40)
        self.btn_generate.clicked.connect(self._start_generate)
        left.addWidget(self.btn_generate)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(
            "QProgressBar{background:#0a1220;border:1px solid #2d3d5a;border-radius:3px;"
            "color:#9fb0d7;font-size:11px;}"
            "QProgressBar::chunk{background:#1e5fa8;border-radius:3px;}")
        self.progress_bar.setFixedHeight(16)
        left.addWidget(self.progress_bar)
        left.addStretch()

        # ── 右列：预览
        gb = QGroupBox("预览"); gb.setProperty("titleVariant", "accent")
        vb = QVBoxLayout(gb)
        self.preview_label = QLabel("改图后显示")
        self.preview_label.setAlignment(Qt.AlignCenter); self.preview_label.setFixedSize(300, 300)
        self.preview_label.setStyleSheet(
            "background:#0a1220;border:1px solid #2d3d5a;border-radius:4px;"
            "color:#3a5070;font-size:13px;")
        vb.addWidget(self.preview_label, 0, Qt.AlignHCenter)

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

        gb = QGroupBox("信息"); gb.setProperty("titleVariant", "accent")
        vb_info = QVBoxLayout(gb)
        def _row(label):
            r = QHBoxLayout()
            l = QLabel(label); l.setStyleSheet("color:#4a6080;font-size:12px;")
            v = QLabel("—"); v.setStyleSheet("color:#7a9ac0;font-size:12px;")
            v.setAlignment(Qt.AlignRight)
            r.addWidget(l); r.addStretch(); r.addWidget(v); vb_info.addLayout(r); return v
        self.info_time  = _row("耗时")
        self.info_cfg   = _row("CFG / 去噪")
        self.info_path  = _row("文件名")
        right.addWidget(gb); right.addStretch()

    # ── 模型扫描 ────────────────────────────
    def _scan_combo(self, combo: QComboBox, directory: str, default_name: str):
        found = []
        for ext in ["*.safetensors", "*.ckpt", "*.pt"]:
            found += glob.glob(os.path.join(directory, ext))
        found = sorted(set(found))
        combo.blockSignals(True); combo.clear()
        select_idx = 0
        for i, f in enumerate(found):
            name = os.path.basename(f)
            combo.addItem(name, name)
            if name == default_name:
                select_idx = i
        combo.blockSignals(False)
        if found:
            combo.setCurrentIndex(select_idx)
        else:
            combo.addItem(f"(未找到，目录：{directory})", "")

    # ── 参考图选择 ──────────────────────────
    def _choose_input_image(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择参考图", "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)"
        )
        if not f: return
        self._input_image = f
        self.input_path_label.setText(os.path.basename(f))
        px = QPixmap(f)
        if not px.isNull():
            px = px.scaled(self.input_preview.width(), self.input_preview.height(),
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.input_preview.setPixmap(px)

    # ── 生成 ────────────────────────────────
    def _start_generate(self):
        if self._worker and self._worker.isRunning():
            self._log("⚠️ 正在生成中，请稍候…"); return
        if not self._input_image or not os.path.isfile(self._input_image):
            self._log("❌ 请先选择参考图"); return
        if not self.prompt.toPlainText().strip():
            self._log("❌ Prompt 不能为空"); return
        if not self.combo_diff.currentData():
            self._log("❌ 未找到扩散模型，请检查模型目录"); return

        try: seed = int(self.seed_input.text())
        except ValueError: seed = -1

        params = dict(
            input_image     = self._input_image,
            diff_model      = f"flux2\\{self.combo_diff.currentData()}",
            clip1           = self.combo_clip1.currentData(),
            vae             = self.combo_vae.currentData(),
            prompt          = self.prompt.toPlainText().strip(),
            negative_prompt = "",
            sampler         = self.sampler_combo.currentText(),
            steps           = self.slider_steps.value(),
            cfg             = self.spin_cfg.value(),
            denoise         = self.spin_denoise.value(),
            seed            = seed,
            save_dir        = self.save_dir_input.text().strip() or self._save_dir,
        )

        self.progress_bar.setValue(0)
        self.btn_generate.setEnabled(False); self.btn_generate.setText("⏳ 改图中…")
        self.preview_label.setText("生成中，请稍候…")
        self._log(f"▶ 开始改图  denoise={params['denoise']}  steps={params['steps']}")

        self._worker = ComfyGenWorker(params)
        self._worker.sig_log.connect(self._log)
        self._worker.sig_progress.connect(self.progress_bar.setValue)
        self._worker.sig_finished.connect(self._on_finished)
        self._worker.sig_error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, paths, elapsed):
        self._last_imgs = paths
        self._last_img  = paths[0] if paths else None
        self._preview_idx = 0
        self.btn_generate.setEnabled(True); self.btn_generate.setText("▶  开始改图")
        self.btn_save_img.setEnabled(True); self.btn_open_dir.setEnabled(True)
        has_many = len(paths) > 1
        self.btn_prev_img.setEnabled(has_many); self.btn_next_img.setEnabled(has_many)
        self.info_time.setText(f"{elapsed:.1f} s")
        self.info_cfg.setText(f"cfg={self._worker.p.get('cfg','—')}  denoise={self._worker.p.get('denoise','—')}")
        self.info_path.setText(os.path.basename(paths[0]) if paths else "—")
        self._show_preview(0)
        self._log(f"🎉 完成！{len(paths)} 张  {elapsed:.1f}s")

    def _show_preview(self, idx):
        if not self._last_imgs: return
        idx = max(0, min(idx, len(self._last_imgs) - 1))
        self._preview_idx = idx; self._last_img = self._last_imgs[idx]
        self.lbl_img_idx.setText(f"{idx+1}/{len(self._last_imgs)}")
        px = QPixmap(self._last_img)
        if not px.isNull():
            px = px.scaled(self.preview_label.width(), self.preview_label.height(),
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_label.setPixmap(px)

    def _prev_img(self): self._show_preview(self._preview_idx - 1)
    def _next_img(self): self._show_preview(self._preview_idx + 1)

    def _on_error(self, msg):
        self.btn_generate.setEnabled(True); self.btn_generate.setText("▶  开始改图")
        self.preview_label.setText("生成失败"); self.progress_bar.setValue(0)
        for line in msg.splitlines():
            if line.strip(): self._log(f"❌ {line}")

    def _choose_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if d: self.save_dir_input.setText(os.path.normpath(d))

    def _save_copy(self):
        if not self._last_img or not os.path.isfile(self._last_img): return
        dst, _ = QFileDialog.getSaveFileName(self, "另存为", self._last_img, "PNG (*.png);;JPEG (*.jpg)")
        if dst: shutil.copy2(self._last_img, dst); self._log(f"📁 另存为：{dst}")

    def _open_output_dir(self):
        d = self.save_dir_input.text().strip() or self._save_dir
        if not os.path.isdir(d): self._log(f"❌ 目录不存在：{d}"); return
        try:
            s = platform.system()
            if s == "Windows": subprocess.Popen(["explorer", os.path.normpath(d)])
            elif s == "Darwin": subprocess.Popen(["open", d])
            else: subprocess.Popen(["xdg-open", d])
        except Exception as e: self._log(f"⚠️ 打开失败：{e}")

    def cleanup(self):
        """主窗口关闭时调用"""
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)

    def _log(self, msg): self._cmd.append(msg)


# ──────────────────────────────────────────────────────────────
# 主 Widget
# ──────────────────────────────────────────────────────────────
class PageComfyUiMini(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane{border:none;}"
            "QTabBar::tab{background:#0f1826;color:#5a7098;padding:8px 20px;"
            "  border-bottom:2px solid transparent;font-size:13px;}"
            "QTabBar::tab:selected{color:#9fb0d7;border-bottom:2px solid #4a7fc1;}"
            "QTabBar::tab:hover{color:#7a9ac0;}")
        lay.addWidget(self.tabs)

        self._cmd = CmdPanel()

        self._startup_tab = StartupTab(self._cmd)
        self._startup_tab.sig_api_ok.connect(self._on_api_ok)
        self.tabs.addTab(self._startup_tab, "🚀  启动")

        self._gen_tab = GenerateTab(self._cmd)
        self.tabs.addTab(self._gen_tab, "🖼️  改图")
        self.tabs.addTab(self._cmd, "🖥️  CMD 输出")

        self.tabs.setTabEnabled(1, False)
        self._cmd.append("欢迎使用 ComfyUI Mini！")
        self._cmd.append("请在「启动」分页启动 ComfyUI，或检测已运行的实例。")

    def _on_api_ok(self):
        self.tabs.setTabEnabled(1, True)
        self.tabs.setCurrentIndex(1)
        self._cmd.append("✅ ComfyUI API 已确认，前往「改图」分页开始使用")

    def closeEvent(self, event):
        """程序关闭时，确保所有子线程安全退出"""
        self._startup_tab.cleanup()
        self._gen_tab.cleanup()
        super().closeEvent(event)
