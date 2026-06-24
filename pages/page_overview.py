# pages/page_overview.py

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QGroupBox, QSizePolicy, QTextBrowser, QFrame  # 🆕 新增 QFrame，用于 NoFrame
)
import platform, shutil, sys, subprocess

def make_card(title: str):
    box = QGroupBox(title)
    box.setProperty("variant", "card")            # 用属性做“卡片”样式钩子
    lay = QVBoxLayout(box)
    lay.setContentsMargins(12, 10, 12, 12)        # 这些是布局，QSS管不了
    lay.setSpacing(8)
    return box, lay

try:
    import psutil  # 可选
except Exception:
    psutil = None

class _Card(QGroupBox):
    def __init__(self, title):
        super().__init__(title)
        self.setProperty("card", "1")         # 与 app.qss 对齐
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        self.v = lay

class PageOverview(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # 顶部两列：左=环境信息，右=资源监控（更紧凑）
        head = QHBoxLayout()
        head.setSpacing(12)
        root.addLayout(head)

        def _apply_new_title(box: QGroupBox):
            box.setProperty("titleClass", "newTitle1")   # 让 QSS 命中“新标题1”
            box.style().unpolish(box); box.style().polish(box)  # 立即刷新样式

        # 左：环境信息
        card_env = QGroupBox("环境信息")
        card_env.setObjectName("CardEnv")
        card_env.setProperty("titleVariant", "accent")
        card_env.setProperty("variant", "card") 

        _env_box = QVBoxLayout(card_env)
        _env_box.setContentsMargins(12, 12, 12, 12)

        # 环境信息正文（使用 QLabel 渲染 HTML）
        self.env = QLabel(self._env_text())
        self.env.setTextFormat(Qt.RichText)          # 使用 HTML 渲染
        self.env.setWordWrap(True)                   # 自动换行

        # ✅ 关键点1：统一使用“卡片正文”样式钩子，QSS 中已定义为透明背景、无边框、合适的文字色
        self.env.setProperty("role", "card-body")

        # ✅ 关键点2：再显式补一刀，强制透明背景，彻底消除任何默认底色导致的色差
        self.env.setStyleSheet("background: transparent;")

        _env_box.addWidget(self.env)

        head.addWidget(card_env, 1)

        # 右：资源监控 —— 卡片
        card_res = QGroupBox("资源监控")
        card_res.setObjectName("CardRes")
        card_res.setProperty("titleVariant", "accent")  # 保留浅蓝标题 + 18px（不会引入背景/圆角）

        # 刷新样式，确保运行期立即生效
        card_res.style().unpolish(card_res)             # 先撤销旧样式
        card_res.style().polish(card_res)               # 再应用新样式

        res_layout = QVBoxLayout(card_res)
        res_layout.setContentsMargins(12, 12, 12, 12)

        head.addWidget(card_res, 1)

        # 中文注释：创建一行“左侧标签 + 细进度条 + 右侧数字文本”
        def meter_row(label_text: str):
            row = QHBoxLayout()
            row.setSpacing(8)

            # 左侧标签：固定最小宽度，便于对齐
            lab = QLabel(label_text)
            lab.setMinimumWidth(90)
            lab.setProperty("role", "stat-label")  # 供 QSS 定制“左侧标签”样式

            # 进度条：范围 0-100，使用 QSS 的细进度条外观；条内关闭文字显示
            bar = QProgressBar()                      # 创建进度条
            bar.setRange(0, 100)
            bar.setProperty("variant", "thin")        # 命中细条样式
            bar.setTextVisible(False)                 # ★ 关键：条内不显示任何文字，只用右侧 QLabel

            # 右侧数字：默认 "--"，右对齐，宽度预留防抖动
            num = QLabel("--")
            num.setProperty("role", "stat-number") # 供 QSS 定制“右侧数字”样式
            num.setMinimumWidth(76)                # 例如 “13W / 320W” 也够用
            num.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # 组装
            row.addWidget(lab)
            row.addWidget(bar, 1)
            row.addWidget(num)

            res_layout.addLayout(row)
            return bar, num

        # 中文注释：7 个指标条（进度条 + 右侧数字标签）
        self.bar_gpu,   self.txt_gpu   = meter_row("GPU使用率："); self.bar_gpu.setObjectName("BarGpu")
        self.bar_vram,  self.txt_vram  = meter_row("显存使用：");   self.bar_vram.setObjectName("BarVram")
        self.bar_mem,   self.txt_mem   = meter_row("内存使用：");   self.bar_mem.setObjectName("BarMem")
        self.bar_cpu,   self.txt_cpu   = meter_row("CPU使用：");    self.bar_cpu.setObjectName("BarCpu")
        self.bar_temp,  self.txt_temp  = meter_row("GPU温度：");    self.bar_temp.setObjectName("BarTemp")
        self.bar_power, self.txt_power = meter_row("GPU功耗：");    self.bar_power.setObjectName("BarPower")
        self.bar_disk,  self.txt_disk  = meter_row("硬盘使用：");   self.bar_disk.setObjectName("BarDisk")

        # 版本信息 —— 裸 QGroupBox + TEXT_STYLE（与“速存图文”一致）
        card_ver = QGroupBox("版本信息")
        card_ver.setObjectName("CardVer")
        card_ver.setProperty("titleVariant", "accent")

        _ver_box = QVBoxLayout(card_ver)
        _ver_box.setContentsMargins(12, 12, 12, 12)

        root.addWidget(card_ver)

        ver = QTextBrowser()
        ver.setOpenExternalLinks(True)
        ver.setReadOnly(True)

        # ✅ 去掉 QTextBrowser 自带的内框，避免出现“卡片边框 + 浏览器边框”的双层外框
        ver.setFrameShape(QFrame.NoFrame)

        # ✅ 与环境信息一致，使用“卡片正文”钩子，走同一套透明背景/文字色
        ver.setProperty("role", "card-body")

        ver.setHtml('''
        <h3>🆕 v9.5 核心功能模块</h3>

        <h4>🖥️ 系统总览</h4>
        <ul>
          <li>实时监控设备硬件状态，包括 CPU、内存、GPU（使用率/显存/温度/功耗）。</li>
        </ul>

        <h4>📥 速存图文</h4>
        <ul>
          <li>后台静默监听，通过全局快捷键（如 Alt+1、F7）一键将剪贴板文本或图片直存至预设本地目录。</li>
        </ul>

        <h4>🧮 积分计算</h4>
        <ul>
          <li>AI 平台订阅成本核算器。输入平台费用及获取积分，自动折算单次生图或单秒视频的精确人民币成本，并支持历史记录保存。</li>
        </ul>

        <h4>✂️ 截图工具</h4>
        <ul>
          <li>支持自定义组合热键（如 Ctrl+Shift+A），框选屏幕区域并自动保存到指定文件夹。</li>
        </ul>

        <h4>📐 比例计算</h4>
        <ul>
          <li>内置 1:1、16:9、21:9 等 8 种 AI 常用画幅预设；支持输入基准像素（如长边 1536），自动换算确切的宽/高数值。</li>
        </ul>

        <h4>🔍 反推提示词</h4>
        <ul>
          <li>单图拖拽反推。接入本地 Ollama 视觉模型（支持 gemma3、phi4-vision 等），内置 9 种英文 Prompt 输出模式（如 Booru、Midjourney 风格），流式生成结果。</li>
        </ul>

        <h4>🏷️ 批量打标</h4>
        <ul>
          <li>对指定本地文件夹的图片进行自动化批量分析，调用视觉模型生成 SD/Booru 格式的 <code>.txt</code> 标签文件，带实时进度监控。</li>
        </ul>

        <h4>🤖 Ollama 助理</h4>
        <ul>
          <li>简易的本地 LLM 对话窗口，支持流式文本交互。</li>
        </ul>

        <h4>🧩 浏览器扩展 (MV3)</h4>
        <ul>
          <li>配合“速存图文”使用，将 <code>MV3/</code> 目录加载至 Chrome 浏览器，可增强网页图片保存的兼容性（可选组件）。</li>
        </ul>
        ''')
        _ver_box.addWidget(ver)

        # 定时刷新（每 1s）
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick)
        self.timer.start(1000)  # 每 1 秒刷新一次
        self._tick()

    # ---------------- internal ----------------
    def _env_text(self):
        import platform, psutil, shutil
        from pathlib import Path

        node = platform.node() or "Unknown"
        cpu  = platform.processor() or platform.uname().processor or "Unknown CPU"
        ram_gb = round(psutil.virtual_memory().total / (1024**3))
        arch = platform.machine() or "x64"
        sys_release = platform.win32_ver()[1] or platform.release()
        sys_version = platform.win32_ver()[2] or platform.version()

        try:
            home = Path.home()
            root_drive = home.drive + "\\" if home.drive else "/"
            du = shutil.disk_usage(root_drive)
            disk_total = round(du.total / (1024**3))
            disk_free  = round(du.free  / (1024**3))
            disk_used  = disk_total - disk_free
            disk_line  = f"{disk_free} GB 可用 / 共 {disk_total} GB（已用 {disk_used} GB）"
        except Exception:
            disk_line = "未知"

        py = platform.python_version()

        # 用 HTML 设置 1.8 倍行距
        return f"""
    <div style="line-height:1.6;">
      <b>设备名：</b>{node}<br/>
      <b>处理器：</b>{cpu}<br/>
      <b>机带 RAM：</b>{ram_gb} GB<br/>
      <b>系统类型：</b>64 位操作系统，基于 {arch} 的处理器<br/>
      <b>系统版本：</b>Windows {sys_release} {sys_version}<br/>
      <b>Python：</b>{py}<br/>
      <b>磁盘空间：</b>{disk_line}
    </div>
    """.strip()

    def _query_nvidia(self):
        """
        返回：dict 或 None
        keys: util(%)、vram_used(MiB)、vram_total(MiB)、temp(°C)、pwr_draw(W)、pwr_limit(W)
        说明：在 Windows 下调用 nvidia-smi 时，显式隐藏控制台窗口，避免打包 exe 时闪窗。
        """
        try:
            # —— Windows 下隐藏子进程控制台窗口（关键）——————————————
            si = None
            cf = 0
            if sys.platform.startswith("win"):                     # 仅在 Windows 使用
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW      # 使用隐藏窗口
                si.wShowWindow = 0                                  # SW_HIDE
                cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)     # 避免出现新控制台窗口

            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,power.limit",
                "--format=csv,noheader,nounits",
                ],
                stderr=subprocess.DEVNULL,          # 屏蔽错误输出
                universal_newlines=True,            # Python 3.10：文本模式
                timeout=1.2,                        # 略放宽一点，降低偶发超时
                startupinfo=si,                     # ★ 隐藏窗口（Windows）
                creationflags=cf                    # ★ 隐藏窗口（Windows）
            )

            line = out.strip().splitlines()[0]
            util, mu, mt, temp, pwr, lim = [s.strip() for s in line.split(",")]
            return {
                "util": int(float(util)),
                "vram_used": float(mu),
                "vram_total": max(1.0, float(mt)),
                "temp": int(float(temp)),
                "pwr_draw": float(pwr),
                "pwr_limit": max(1.0, float(lim)),
            }
        except Exception:
            return None

    def _tick(self):
        """每 1s 刷新资源数据：GPU(优先 nvidia-smi) + CPU/内存/磁盘(psutil)"""
        # ========= GPU（来自 nvidia-smi）=========
        info = self._query_nvidia()
        if info:
            # GPU 使用率（0~100）
            util = max(0, min(100, int(info["util"])))
            self.bar_gpu.setValue(util)
            self.txt_gpu.setText(f"{util}%")

            # 显存使用率（由已用/总量计算）
            vram_pct = int(info["vram_used"] / info["vram_total"] * 100)
            self.bar_vram.setValue(vram_pct)
            self.txt_vram.setText(f"{vram_pct}%")

            # 温度（刻度给到 110℃）
            self.bar_temp.setRange(0, 110)
            temp = int(info["temp"])
            self.bar_temp.setValue(temp)
            self.txt_temp.setText(f"{temp}℃")

            # 功耗（按功耗占比画条；右侧显示 “xW / yW”）
            p_pct = int(info["pwr_draw"] / info["pwr_limit"] * 100)
            p_pct = max(0, min(100, p_pct))
            self.bar_power.setValue(p_pct)
            self.txt_power.setText(f"{info['pwr_draw']:.0f}W / {info['pwr_limit']:.0f}W")
        else:
            # 无 NVIDIA 或查询失败：置零并显示占位
            for bar, lab in (
                (self.bar_gpu, self.txt_gpu),
                (self.bar_vram, self.txt_vram),
                (self.bar_temp, self.txt_temp),
                (self.bar_power, self.txt_power),
            ):
                bar.setValue(0)
                lab.setText("--")

        # ========= 系统资源（CPU / 内存 / 磁盘，来自 psutil）=========
        if psutil:
            try:
                # CPU：瞬时百分比（非阻塞）
                cpu = int(psutil.cpu_percent(interval=0))
                self.bar_cpu.setValue(cpu)
                self.txt_cpu.setText(f"{cpu}%")

                # 内存：百分比
                mem = int(psutil.virtual_memory().percent)
                self.bar_mem.setValue(mem)
                self.txt_mem.setText(f"{mem}%")

                # 磁盘：系统盘百分比（Windows 取用户主目录所在盘；其它平台取“/”）
                from pathlib import Path
                home = Path.home()
                root_drive = home.drive + "\\" if getattr(home, "drive", "") else "/"
                du = psutil.disk_usage(root_drive)
                disk_pct = int(du.percent)
                self.bar_disk.setValue(disk_pct)
                self.txt_disk.setText(f"{disk_pct}%")
            except Exception:
                # 即使 psutil 异常，也不中断 UI
                pass
        else:
            # 未安装 psutil：显示占位
            self.txt_cpu.setText("--")
            self.txt_mem.setText("--")
            self.txt_disk.setText("--")
