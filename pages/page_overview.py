# pages/page_overview.py

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QGroupBox, QSizePolicy, QTextBrowser, QFrame  # 🆕 新增 QFrame，用于 NoFrame
)
import platform, shutil, sys, subprocess

_IS_WIN = sys.platform.startswith("win")


# ══════════════ Windows 集成显卡利用率（PDH 性能计数器） ══════════════
# 说明：nvidia-smi 只适用于 NVIDIA 独显。笔记本常见的 Intel/AMD 集显读不到数据，
# 会导致“资源监控”里 GPU 相关几项全空。这里用 Windows 自带的性能计数器
# “\GPU Engine(*)\Utilization Percentage” 读取任意厂商 GPU 的利用率作为兜底。
# 全程 try/except 包裹，任何异常都安全退回 None，绝不影响主界面刷新。
if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    class _PDH_UNION(ctypes.Union):
        _fields_ = [
            ("longValue", ctypes.c_long),
            ("doubleValue", ctypes.c_double),
            ("largeValue", ctypes.c_longlong),
            ("AnsiStringValue", ctypes.c_char_p),
            ("WideStringValue", ctypes.c_wchar_p),
        ]

    class _PDH_FMT_COUNTERVALUE(ctypes.Structure):
        _fields_ = [("CStatus", wintypes.DWORD), ("value", _PDH_UNION)]

    class _PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
        _fields_ = [("szName", ctypes.c_wchar_p),
                    ("FmtValue", _PDH_FMT_COUNTERVALUE)]

    _PDH_FMT_DOUBLE = 0x00000200

    class _PdhGpu:
        """读取整机 GPU 利用率（取各引擎实例的最大值，近似任务管理器口径）。"""
        def __init__(self):
            self._ok = False
            self.hq = None
            try:
                self.pdh = ctypes.WinDLL("pdh")
                self.hq = wintypes.HANDLE()
                if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.hq)) != 0:
                    return
                self.counter = wintypes.HANDLE()
                path = r"\GPU Engine(*)\Utilization Percentage"
                if self.pdh.PdhAddEnglishCounterW(
                        self.hq, path, 0, ctypes.byref(self.counter)) != 0:
                    return
                # 首次采样（计数器需要两次采样才能计算）
                self.pdh.PdhCollectQueryData(self.hq)
                self._ok = True
            except Exception:
                self._ok = False

        def read(self):
            if not self._ok:
                return None
            try:
                if self.pdh.PdhCollectQueryData(self.hq) != 0:
                    return None
                size = wintypes.DWORD(0)
                count = wintypes.DWORD(0)
                # 第一次调用取所需缓冲区大小
                self.pdh.PdhGetFormattedCounterArrayW(
                    self.counter, _PDH_FMT_DOUBLE,
                    ctypes.byref(size), ctypes.byref(count), None)
                if size.value == 0 or count.value == 0:
                    return None
                buf = ctypes.create_string_buffer(size.value)
                if self.pdh.PdhGetFormattedCounterArrayW(
                        self.counter, _PDH_FMT_DOUBLE,
                        ctypes.byref(size), ctypes.byref(count), buf) != 0:
                    return None
                item_sz = ctypes.sizeof(_PDH_FMT_COUNTERVALUE_ITEM_W)
                # 防越界：以缓冲区实际容量为准
                safe_n = min(count.value, size.value // item_sz)
                best = 0.0
                for i in range(safe_n):
                    item = _PDH_FMT_COUNTERVALUE_ITEM_W.from_buffer(buf, i * item_sz)
                    v = item.FmtValue.value.doubleValue
                    if v == v and v > best:   # 过滤 NaN
                        best = v
                return max(0, min(100, int(round(best))))
            except Exception:
                return None


def _detect_gpu_name():
    """返回主显卡名称（用于占位提示），失败返回空串。仅 Windows。"""
    if not _IS_WIN:
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        class DISPLAY_DEVICEW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128),
                ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128),
                ("DeviceKey", wintypes.WCHAR * 128),
            ]
        i = 0
        names = []
        while True:
            dd = DISPLAY_DEVICEW()
            dd.cb = ctypes.sizeof(dd)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            s = dd.DeviceString.strip()
            if s and s not in names:
                names.append(s)
            i += 1
            if i > 16:
                break
        return names[0] if names else ""
    except Exception:
        return ""


def _detect_cpu_name():
    """从注册表读取友好的 CPU 名称（比 platform.processor() 更可读）。仅 Windows。"""
    if not _IS_WIN:
        return ""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        return (val or "").strip()
    except Exception:
        return ""

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

        # 集显利用率读取器（仅 Windows 且无 NVIDIA 时兜底使用）
        self._pdh_gpu = None
        if _IS_WIN:
            try:
                self._pdh_gpu = _PdhGpu()
            except Exception:
                self._pdh_gpu = None

        # 检测显卡名称，供占位提示更友好
        self._gpu_name = _detect_gpu_name()
        gpu_tip = self._gpu_name or "显卡"
        self.txt_gpu.setToolTip(gpu_tip)
        # 集显通常无法读取显存/温度/功耗，给出说明性提示，避免误以为是 Bug
        na_tip = f"{gpu_tip}：集成显卡或非 NVIDIA 设备通常无法读取该指标"
        for lab in (self.txt_vram, self.txt_temp, self.txt_power):
            lab.setToolTip(na_tip)

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

        # 🆕 版本信息内容改为读取项目根目录的 README.md（Markdown 原生渲染）
        self.ver = ver
        self._load_readme()

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
        cpu  = _detect_cpu_name() or platform.processor() or platform.uname().processor or "Unknown CPU"
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

    def _load_readme(self):
        """读取项目根目录下的 README.md，用 Markdown 原生渲染到“版本信息”面板。
        找不到文件或读取失败时给出友好提示，绝不抛异常中断界面。"""
        import os, sys

        # 兼容：源码运行（本文件在 pages/，README 在上一级）/ PyInstaller 打包 / 从根目录运行
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(here)
        candidates = []
        meipass = getattr(sys, "_MEIPASS", None)
        for base in (meipass, root, here, os.getcwd()):
            if base:
                candidates.append(os.path.join(base, "README.md"))

        path = next((p for p in candidates if os.path.exists(p)), None)
        if not path:
            self.ver.setPlainText("⚠️ 未找到 README.md，请确认它在项目根目录。")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            self.ver.setPlainText(f"⚠️ 读取 README.md 失败：{e}")
            return

        # Qt 5.14+ 的 QTextBrowser 原生支持 Markdown；旧版本兼底为纯文本
        if hasattr(self.ver, "setMarkdown"):
            self.ver.setMarkdown(text)
        else:
            self.ver.setPlainText(text)

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
            # 无 NVIDIA 独显（或查询失败）：尝试用 Windows 性能计数器读集显利用率
            util = self._pdh_gpu.read() if self._pdh_gpu else None
            self.bar_temp.setRange(0, 100)  # 复位刻度（NVIDIA 分支曾改成 110）
            if util is not None:
                self.bar_gpu.setValue(util)
                self.txt_gpu.setText(f"{util}%")
            else:
                self.bar_gpu.setValue(0)
                self.txt_gpu.setText("N/A")
            # 显存 / 温度 / 功耗：集显一般无法读取，用 N/A 明确占位（而非空白）
            for bar, lab in (
                (self.bar_vram, self.txt_vram),
                (self.bar_temp, self.txt_temp),
                (self.bar_power, self.txt_power),
            ):
                bar.setValue(0)
                lab.setText("N/A")

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
