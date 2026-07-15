# pages/page_overview.py

from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QColor, QDesktopServices
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QGroupBox, QSizePolicy, QTextBrowser, QFrame,
)
import html as html_lib
import platform, shutil, sys, subprocess
from styles.style_all import (
    install_card_title,
    make_card,
    make_grid_row,
    restyle_card_frame,
    restyle_card_title,
    content_primary_color,
    content_secondary_color,
    CARD_TOP_GAP,
    CARD_LEFT_GAP,
    CARD_RIGHT_GAP,
    CARD_BOTTOM_GAP,
    theme,
)

# 版本信息：优先 QWebEngine + Markdown→HTML（接近 MD 编辑器预览）；否则 QTextBrowser 兜底
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
    _WEBENGINE_OK = True
except Exception:
    QWebEngineView = None
    QWebEnginePage = None
    _WEBENGINE_OK = False

try:
    import markdown as _md_lib
    _MARKDOWN_OK = True
except Exception:
    _md_lib = None
    _MARKDOWN_OK = False

# 统一行高（像素）：环境信息 / 资源监控 两栏共用，逐行对齐。
# 相对旧值 26 加高 2px（行距加大）；字号比全局正文 14px 小一码。
ROW_H = 26
OVERVIEW_ROW_H = ROW_H + 2
OVERVIEW_FONT_PX = 13

# 资源监控进度条：已达段颜色 / 未达轨道（浅色）
_BAR_CHUNK = {
    "BarGpu": "#30c86b",
    "BarVram": "#3aa0ff",
    "BarMem": "#f0a542",
    "BarCpu": "#9aa0ac",
    "BarTemp": "#f07f3c",
    "BarPower": "#9b59b6",
    "BarDisk": "#ff6b6b",
}


def _meter_track_color() -> str:
    """进度条未达部分（浅色轨道）。"""
    return "#4a5575" if theme.is_dark else "#e8edf5"


def _apply_meter_bar_style(bar: QProgressBar, chunk: str) -> None:
    """内联刷进度条：半粗 4px + 浅色轨道 + 无外框 + 彩色已达段。

    不用只依赖全局 QSS：行容器若曾用无选择器透明背景，会冲掉轨道底色。
    """
    track = _meter_track_color()
    bar.setStyleSheet(
        f"QProgressBar{{"
        f"background:{track};border:none;border-radius:2px;"
        f"min-height:4px;max-height:4px;height:4px;"
        f"padding:0;text-align:center;color:transparent;}}"
        f"QProgressBar::chunk{{background:{chunk};border-radius:2px;}}"
    )


def _md_to_body_html(text: str) -> str:
    """Markdown 源文 → HTML 正文（尽量对齐编辑器 / GFM 能力）。"""
    if _MARKDOWN_OK:
        return _md_lib.markdown(
            text,
            extensions=[
                "fenced_code",
                "tables",
                "nl2br",
                "sane_lists",
                "smarty",
                "attr_list",
            ],
            output_format="html5",
        )
    # 无 markdown 库时：转义后按行简单处理，避免裸 HTML 注入
    esc = html_lib.escape(text)
    return "<pre style='white-space:pre-wrap;font-family:inherit;'>" + esc + "</pre>"


def _readme_preview_css(is_dark: bool) -> str:
    """类 VS Code / Cursor Markdown 预览的 CSS（对照 temp2.png 内容区观感）。"""
    if is_dark:
        # 深色预览：白标题 + 浅灰正文 + 左侧色条引用 + 略亮代码底
        return """
:root {
  --bg: transparent;
  --fg: #d4d4d4;
  --fg-strong: #ffffff;
  --fg-muted: #9ca3af;
  --heading: #f3f4f6;
  --link: #60a5fa;
  --border: #3a3f4b;
  --quote-bar: #7c8cff;
  --quote-fg: #b0b8c8;
  --code-bg: #2a2f3a;
  --code-fg: #e5e7eb;
  --pre-bg: #1a1f2b;
  --hr: #3a3f4b;
  --bullet: #9ca3af;
}
"""
    return """
:root {
  --bg: transparent;
  --fg: #334155;
  --fg-strong: #0f172a;
  --fg-muted: #64748b;
  --heading: #0f172a;
  --link: #2563eb;
  --border: #e2e8f0;
  --quote-bar: #6366f1;
  --quote-fg: #64748b;
  --code-bg: #f1f5f9;
  --code-fg: #0f172a;
  --pre-bg: #f8fafc;
  --hr: #e2e8f0;
  --bullet: #64748b;
}
"""


def _build_readme_document(md_text: str, is_dark: bool = None) -> str:
    """完整 HTML 文档：Markdown 正文 + 编辑器风格预览 CSS。"""
    if is_dark is None:
        is_dark = theme.is_dark
    body = _md_to_body_html(md_text)
    theme_vars = _readme_preview_css(is_dark)
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
{theme_vars}
html, body {{
  margin: 0; padding: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC",
               "Noto Sans CJK SC", sans-serif;
  font-size: 14.5px;
  line-height: 1.7;
  word-wrap: break-word;
  overflow-wrap: break-word;
}}
.markdown-body {{
  padding: 2px 6px 16px 2px;
  max-width: 100%;
  box-sizing: border-box;
}}
.markdown-body h1, .markdown-body h2, .markdown-body h3,
.markdown-body h4, .markdown-body h5, .markdown-body h6 {{
  color: var(--heading);
  font-weight: 700;
  line-height: 1.35;
  margin: 1.15em 0 0.55em;
}}
.markdown-body h1 {{
  font-size: 1.75em;
  margin-top: 0.2em;
  padding-bottom: 0.25em;
  border-bottom: none;
}}
.markdown-body h2 {{
  font-size: 1.35em;
  padding-bottom: 0.35em;
  border-bottom: 1px solid var(--border);
}}
.markdown-body h3 {{ font-size: 1.12em; margin-top: 1.25em; }}
.markdown-body h4 {{ font-size: 1.02em; }}
.markdown-body p {{ margin: 0.55em 0 0.75em; }}
.markdown-body a {{ color: var(--link); text-decoration: none; }}
.markdown-body a:hover {{ text-decoration: underline; }}
.markdown-body strong {{ color: var(--fg-strong); font-weight: 700; }}
.markdown-body em {{ font-style: italic; }}
/* 引用块：左侧色条（对照编辑器预览） */
.markdown-body blockquote {{
  margin: 0.75em 0 1em;
  padding: 0.15em 0 0.15em 0.9em;
  border-left: 3px solid var(--quote-bar);
  color: var(--quote-fg);
  background: transparent;
}}
.markdown-body blockquote p {{ margin: 0.25em 0; }}
.markdown-body ul, .markdown-body ol {{
  margin: 0.4em 0 0.9em;
  padding-left: 1.45em;
}}
.markdown-body li {{
  margin: 0.35em 0;
  color: var(--fg);
}}
.markdown-body li::marker {{ color: var(--bullet); }}
.markdown-body li > p {{ margin: 0.25em 0; }}
.markdown-body hr {{
  border: none;
  border-top: 1px solid var(--hr);
  margin: 1.1em 0;
}}
/* 行内代码 */
.markdown-body code {{
  font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
  font-size: 0.9em;
  background: var(--code-bg);
  color: var(--code-fg);
  padding: 0.12em 0.4em;
  border-radius: 4px;
}}
/* 代码块 */
.markdown-body pre {{
  background: var(--pre-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  overflow-x: auto;
  margin: 0.75em 0 1em;
  line-height: 1.5;
}}
.markdown-body pre code {{
  background: transparent;
  padding: 0;
  font-size: 0.88em;
  color: var(--code-fg);
}}
.markdown-body table {{
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0;
  font-size: 0.95em;
}}
.markdown-body th, .markdown-body td {{
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}}
.markdown-body th {{
  background: var(--code-bg);
  color: var(--fg-strong);
  font-weight: 600;
}}
.markdown-body img {{ max-width: 100%; height: auto; }}
/* 滚动条（贴近应用记录区） */
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{
  background: {"#3a4670" if is_dark else "#cbd5e1"};
  border-radius: 6px;
  border: 2px solid transparent;
  background-clip: content-box;
}}
::-webkit-scrollbar-thumb:hover {{
  background: {"#4b5a8a" if is_dark else "#94a3b8"};
  background-clip: content-box;
  border: 2px solid transparent;
}}
</style>
</head>
<body>
<div class="markdown-body">
{body}
</div>
</body></html>
"""


if _WEBENGINE_OK:
    class _ReadmeWebPage(QWebEnginePage):
        """链接在系统浏览器打开，避免在内嵌页里跳走。"""

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            if nav_type == QWebEnginePage.NavigationTypeLinkClicked:
                try:
                    QDesktopServices.openUrl(url)
                except Exception:
                    pass
                return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

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
        # 主内容区 ContentRoot 已有约 18px 内边距；这里若再套 12px，
        # 左右会叠出约「两个汉字」宽的空白。总览贴齐主区，只保留卡片之间的间距。
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # 顶部两列：左=环境信息，右=资源监控（更紧凑）
        head = QHBoxLayout()
        head.setSpacing(12)
        root.addLayout(head)

        def _apply_new_title(box: QGroupBox):
            box.setProperty("titleClass", "newTitle1")   # 让 QSS 命中“新标题1”
            box.style().unpolish(box); box.style().polish(box)  # 立即刷新样式

        # v9.9.2：这几张卡片改用内联样式画外观（见 style_common.make_card 的注释），
        # 不再吃全局 QSS 级联，所以主题切换时要自己收集控件引用、手动重刷。
        self._theme_frames = []          # 卡片外框（背景/边框）
        self._theme_titles = []          # 标题 QLabel
        self._theme_primary_labels = []  # 资源监控·第1列标签（常规字重）
        self._theme_primary_nums = []    # 资源监控·右侧数值
        self._theme_secondary_bold = []    # 环境信息·字段名
        self._theme_secondary_plain = []   # 环境信息·字段值

        # 左：环境信息
        # v9.9.2：改用 make_card() —— 无原生标题/无隐藏预留高度的 QFrame，
        # 避免 QGroupBox 原生标题机制在不同卡片上留白不一致的问题。
        card_env = make_card("CardEnv")
        self._theme_frames.append(card_env)

        _env_box = QVBoxLayout(card_env)
        _env_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        _env_box.setSpacing(0)
        self._theme_titles.append(install_card_title(card_env, _env_box, "环境信息"))

        # 环境信息正文：
        #  - 左列字段名去掉「：」
        #  - 右列从本区宽度 20% 处起左对齐（stretch 1:4）
        #  - 字号减一码；行高 = OVERVIEW_ROW_H（行距加大 2px）
        for label_text, value_text in self._env_fields():
            row_widget, row_lay = make_grid_row(OVERVIEW_ROW_H, spacing=0)
            lab = QLabel(label_text)
            lab.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            lab.setStyleSheet(
                f"background:transparent; color:{content_secondary_color()}; "
                f"font-weight:600; font-size:{OVERVIEW_FONT_PX}px;"
            )
            val = QLabel(value_text)
            val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            val.setStyleSheet(
                f"background:transparent; color:{content_secondary_color()}; "
                f"font-size:{OVERVIEW_FONT_PX}px;"
            )
            val.setWordWrap(False)
            # 1:4 → 右列起点落在当前区 20% 处
            row_lay.addWidget(lab, 1)
            row_lay.addWidget(val, 4)
            _env_box.addWidget(row_widget)
            self._theme_secondary_bold.append(lab)
            self._theme_secondary_plain.append(val)

        # 不再在卡片内部加 addStretch：让卡片高度贴合内容本身，
        # 多出来的窗口空间统一交给下方"版本信息"去撑（更符合它内容更多、
        # 更值得多给显示区域的实际需求）。
        head.addWidget(card_env, 1)

        # 右：资源监控 —— 卡片
        card_res = make_card("CardRes")
        self._theme_frames.append(card_res)

        res_layout = QVBoxLayout(card_res)
        res_layout.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        res_layout.setSpacing(0)
        self._theme_titles.append(install_card_title(card_res, res_layout, "资源监控"))

        head.addWidget(card_res, 1)

        # 资源监控：与环境信息同规格
        #  - 左列去掉「：」、常规字重（不加粗）；右列从 20% 处起（stretch 1:4）
        #  - 字号减一码；行高 OVERVIEW_ROW_H，与左侧逐行对齐
        def meter_row(label_text: str):
            row_widget, row = make_grid_row(OVERVIEW_ROW_H, spacing=0)

            lab = QLabel(label_text)
            lab.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            lab.setStyleSheet(
                f"background:transparent; color:{content_primary_color()}; "
                f"font-weight:400; font-size:{OVERVIEW_FONT_PX}px;"
            )

            # 进度条：半粗 4px / 浅色未达轨道 / 无外框（内联样式，避免被祖先 QSS 冲掉）
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setProperty("variant", "thin")
            bar.setTextVisible(False)
            bar.setFixedHeight(4)

            # 右侧数字：宽度预留防抖动（如 “13W / 320W”）
            num = QLabel("--")
            num.setStyleSheet(
                f"background:transparent; color:{content_primary_color()}; "
                f"font-weight:600; font-size:{OVERVIEW_FONT_PX}px;"
            )
            num.setMinimumWidth(76)
            num.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # 右区（80%）：进度条 + 数字，起点对齐本区 20%
            # 必须 #id 限定透明，否则 border/background 会级联到进度条
            right = QWidget()
            right.setObjectName("MeterRight")
            right.setStyleSheet("#MeterRight{background:transparent;}")
            right_l = QHBoxLayout(right)
            right_l.setContentsMargins(0, 0, 0, 0)
            right_l.setSpacing(8)
            right_l.addWidget(bar, 1)
            right_l.addWidget(num)

            row.addWidget(lab, 1)
            row.addWidget(right, 4)

            res_layout.addWidget(row_widget)
            self._theme_primary_labels.append(lab)
            self._theme_primary_nums.append(num)
            return bar, num

        # 7 个指标条（标签已去「：」）；objectName 后立即刷内联轨道样式
        self._meter_bars = []  # (bar, chunk_color) 供主题切换重刷

        def _bind_bar(bar: QProgressBar, name: str):
            bar.setObjectName(name)
            chunk = _BAR_CHUNK[name]
            _apply_meter_bar_style(bar, chunk)
            self._meter_bars.append((bar, chunk))
            return bar

        self.bar_gpu,   self.txt_gpu   = meter_row("GPU使用率"); _bind_bar(self.bar_gpu, "BarGpu")
        self.bar_vram,  self.txt_vram  = meter_row("显存使用");  _bind_bar(self.bar_vram, "BarVram")
        self.bar_mem,   self.txt_mem   = meter_row("内存使用");  _bind_bar(self.bar_mem, "BarMem")
        self.bar_cpu,   self.txt_cpu   = meter_row("CPU使用");   _bind_bar(self.bar_cpu, "BarCpu")
        self.bar_temp,  self.txt_temp  = meter_row("GPU温度");   _bind_bar(self.bar_temp, "BarTemp")
        self.bar_power, self.txt_power = meter_row("GPU功耗");   _bind_bar(self.bar_power, "BarPower")
        self.bar_disk,  self.txt_disk  = meter_row("硬盘使用");  _bind_bar(self.bar_disk, "BarDisk")

        # 同理：资源监控也不再内部撑高，贴合 7 行内容本身的高度即可。

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

        # 版本信息 —— 同样改用无原生装饰的 QFrame 卡片
        card_ver = make_card("CardVer")
        self._theme_frames.append(card_ver)

        _ver_box = QVBoxLayout(card_ver)
        _ver_box.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        self._theme_titles.append(install_card_title(card_ver, _ver_box, "版本信息"))

        # 拉伸系数 1：把窗口里除"环境信息/资源监控"两张卡片自身高度之外的
        # 剩余纵向空间，全部分给"版本信息"——它内容更多，理应获得更大的显示区域。
        root.addWidget(card_ver, 1)

        # 版本信息：QWebEngine 渲染 Markdown HTML（接近 MD 编辑器预览，见 temp2.png）
        # 无 WebEngine 时退回 QTextBrowser + 同一套 HTML
        self._readme_raw = ""
        self._ver_is_web = False
        if _WEBENGINE_OK:
            ver = QWebEngineView()
            ver.setObjectName("OverviewVerBrowser")
            ver.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            page = _ReadmeWebPage(ver)
            page.setBackgroundColor(QColor(0, 0, 0, 0))
            ver.setPage(page)
            ver.setStyleSheet(
                "QWebEngineView#OverviewVerBrowser{background:transparent;border:none;}"
            )
            self._ver_is_web = True
        else:
            ver = QTextBrowser()
            ver.setObjectName("OverviewVerBrowser")
            ver.setOpenExternalLinks(True)
            ver.setReadOnly(True)
            ver.setFrameShape(QFrame.NoFrame)
            ver.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
            ver.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            ver.document().setDocumentMargin(0)
            ver.setViewportMargins(0, 0, 0, 0)
            ver.setStyleSheet(
                "QTextBrowser#OverviewVerBrowser{background:transparent;border:none;}"
            )

        self._theme_ver_browser = ver
        self.ver = ver
        self._load_readme()
        _ver_box.addWidget(ver)

        # 定时刷新（每 1s）
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick)
        self.timer.start(1000)  # 每 1 秒刷新一次
        self._tick()

        # v9.9.2：这几张卡片改用内联样式画外观，不再随全局 QSS 自动换肤，
        # 所以要监听主题切换信号，手动重刷一遍配色（背景/边框/标题/正文）。
        theme.changed.connect(self._apply_theme)

    def _apply_theme(self, *_args):
        """主题切换（深色/浅色）时，重新刷新本页这几张"内联样式"卡片的配色。"""
        for frame in self._theme_frames:
            restyle_card_frame(frame)
        for title_lbl in self._theme_titles:
            restyle_card_title(title_lbl)
        primary = content_primary_color()
        secondary = content_secondary_color()
        for lbl in self._theme_primary_labels:
            lbl.setStyleSheet(
                f"background:transparent; color:{primary}; "
                f"font-weight:400; font-size:{OVERVIEW_FONT_PX}px;"
            )
        for lbl in self._theme_primary_nums:
            lbl.setStyleSheet(
                f"background:transparent; color:{primary}; "
                f"font-weight:600; font-size:{OVERVIEW_FONT_PX}px;"
            )
        for bar, chunk in getattr(self, "_meter_bars", []):
            _apply_meter_bar_style(bar, chunk)
        for lbl in self._theme_secondary_bold:
            lbl.setStyleSheet(
                f"background:transparent; color:{secondary}; "
                f"font-weight:600; font-size:{OVERVIEW_FONT_PX}px;"
            )
        for lbl in self._theme_secondary_plain:
            lbl.setStyleSheet(
                f"background:transparent; color:{secondary}; "
                f"font-size:{OVERVIEW_FONT_PX}px;"
            )
        # 版本信息：主题切换时按同一份 Markdown 重渲编辑器风格 HTML
        if getattr(self, "_readme_raw", None) is not None and self._readme_raw != "":
            self._render_readme(self._readme_raw)
        elif self._theme_ver_browser is not None and not getattr(self, "_ver_is_web", False):
            self._theme_ver_browser.setStyleSheet(
                "QTextBrowser#OverviewVerBrowser{background:transparent;border:none;}"
            )

    # ---------------- internal ----------------
    def _env_fields(self):
        """返回环境信息的 [(标签, 值), ...] 列表，供逐行固定高度布局使用
        （替代原来的单个富文本 QLabel，从根源上解决与"资源监控"逐行对不齐的问题）。"""
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

        return [
            ("设备名",     node),
            ("处理器",     cpu),
            ("机带 RAM",   f"{ram_gb} GB"),
            ("系统类型",   f"64 位操作系统，基于 {arch} 的处理器"),
            ("系统版本",   f"Windows {sys_release} {sys_version}"),
            ("Python",    py),
            ("磁盘空间",   disk_line),
        ]

    def _load_readme(self):
        """读取项目根目录 README.md，按 MD 编辑器预览风格渲染到「版本信息」。"""
        import os

        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(here)
        candidates = []
        meipass = getattr(sys, "_MEIPASS", None)
        for base in (meipass, root, here, os.getcwd()):
            if base:
                candidates.append(os.path.join(base, "README.md"))

        path = next((p for p in candidates if os.path.exists(p)), None)
        if not path:
            self._readme_raw = ""
            self._render_readme_message("⚠️ 未找到 README.md，请确认它在项目根目录。")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            self._readme_raw = ""
            self._render_readme_message(f"⚠️ 读取 README.md 失败：{e}")
            return

        self._readme_raw = text
        self._render_readme(text)

    def _render_readme_message(self, msg: str) -> None:
        """错误/提示：也走同一套 HTML 壳，避免 Web/Browser 两套 API 分叉难看。"""
        doc = _build_readme_document(msg, theme.is_dark)
        self._set_ver_html(doc)

    def _render_readme(self, md_text: str) -> None:
        """Markdown → 编辑器风格 HTML 文档并显示。"""
        doc = _build_readme_document(md_text, theme.is_dark)
        self._set_ver_html(doc)

    def _set_ver_html(self, document_html: str) -> None:
        """写入版本信息控件（WebEngine 或 QTextBrowser）。"""
        if getattr(self, "_ver_is_web", False):
            # baseUrl = 项目根，便于 README 里相对路径图片
            import os
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            base = QUrl.fromLocalFile(root.replace("\\", "/").rstrip("/") + "/")
            self.ver.setHtml(document_html, base)
            try:
                self.ver.page().setBackgroundColor(QColor(0, 0, 0, 0))
            except Exception:
                pass
        else:
            self.ver.setHtml(document_html)

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
