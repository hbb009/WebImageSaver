# pages/page_director.py
# 导演台 —— 故事 → A 电影制作板 / B 角色提示词 / C 镜头提示词
# v9.9    新增：核心交互/生成逻辑来自 director-agent.html（独立网页版），这里
#         原样保留其 JS 逻辑，只做两件事：
#           1) 用 QWebEngineView 把它内嵌进桌面助手，去掉网页自带的主题切换按钮；
#           2) 配色改用桌面助手当前主题的色板（theme.changed 时用 window.applyTheme()
#              直接覆盖 CSS 自定义属性，不刷新整页，避免丢失已填的故事/元素/镜头大纲）。
# v9.9.1  修复：网页原先用浏览器 fetch() 直连 http://localhost:11434，在 QWebEngineView
#         里页面 origin 是 null，会被 Chromium 的 CORS 拦掉（浏览器控制台报
#         "Access to fetch ... has been blocked by CORS policy"）。
#         改为 JS 通过 QWebChannel 把请求转交给 Python，Python 用 requests 库
#         （和 utils/ollama_client.py 同款方式）去连 Ollama，天然不受浏览器跨域
#         限制约束。下面 _HTML_TEMPLATE 里做了双模式：检测到宿主提供了
#         QWebChannel 就走桥接；没有（比如把 _HTML_TEMPLATE 另存成 .html 文件
#         直接用浏览器打开）就照旧退回原来的 fetch()，两种运行方式都能用。
# v9.9.2  单文件化：原来是 page_director.py + assets/director_agent.html 两个
#         文件，现在把网页内容整段内嵌进本文件末尾的 _HTML_TEMPLATE 常量里，
#         以后改动这个页面只需要发这一个 .py 文件。assets/director_agent.html
#         不再被读取，可以删除。
# 依赖 PyQtWebEngine（含 QtWebChannel）；未安装时优雅降级为提示文案（与
# disk_treemap_widget.py 里 Treemap 组件的处理方式一致）。

import json
import os
import re
from datetime import datetime

import requests

from PyQt5.QtCore import Qt, QUrl, QObject, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy, QApplication

from styles.style_all import theme, fmt, WEB_VIEW_QSS, FALLBACK_LABEL_QSS

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE_OK = True
except Exception:
    QWebEngineView = None
    _WEBENGINE_OK = False

try:
    from PyQt5.QtWebChannel import QWebChannel
    _WEBCHANNEL_OK = True
except Exception:
    QWebChannel = None
    _WEBCHANNEL_OK = False

OLLAMA_BASE = "http://localhost:11434"

# 产出根目录：每次“确认元素”会在这里新建一个 日期+项目名+序号 的项目目录。
# 想改到别处，改这一行即可（例如指向某个固定的作品库路径）。
OUTPUT_BASE = os.path.join(os.getcwd(), "导演台产出")


def _sanitize_name(name: str) -> str:
    """把项目名清洗成合法目录名（去掉 \\ / : * ? " < > | 及换行等）。"""
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    name = name.strip(" ._") or "未命名项目"
    return name[:40]


def _make_project_dir(project_name: str) -> str:
    """创建“日期+项目名+序号”目录（如 20260713_警察与事故_001）。
    若当天同名目录已存在则序号自增，返回新建目录的绝对路径。"""
    os.makedirs(OUTPUT_BASE, exist_ok=True)
    date = datetime.now().strftime("%Y%m%d")
    safe = _sanitize_name(project_name)
    seq = 1
    while True:
        full = os.path.join(OUTPUT_BASE, f"{date}_{safe}_{seq:03d}")
        if not os.path.exists(full):
            os.makedirs(full)
            return full
        seq += 1


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """'#3a8ee0' -> 'rgba(58,142,224,0.14)'，用于生成柔和的强调色底/边框。"""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return hex_color
    return f"rgba({r},{g},{b},{alpha})"


def _theme_vars() -> dict:
    """把桌面助手当前主题的色板，映射成网页里用到的那套
    --token（--bg / --ink / --accent ... ）。"""
    t = theme.tokens
    accent = t["accent"]
    warn = t["warn"]
    danger = t["err"]
    return {
        "bg":            t["bg"],
        "ink":           t["text"],
        "ink-soft":      t["text_mut"],
        "card":          t["panel"],
        "border":        t["border"],
        "accent":        accent,
        "accent-soft":   _hex_to_rgba(accent, 0.14),
        "accent-border": _hex_to_rgba(accent, 0.4),
        "warn":          warn,
        "warn-soft":     _hex_to_rgba(warn, 0.14),
        "warn-border":   _hex_to_rgba(warn, 0.4),
        "danger":        danger,
        "danger-soft":   _hex_to_rgba(danger, 0.14),
        "danger-border": _hex_to_rgba(danger, 0.4),
        "btn-bg":        accent,
        "btn-text":      "#FFFFFF",
        "logo-color":    accent,
    }


# 首屏兜底占位符 → :root 变量名（与下面 _HTML_TEMPLATE 里的 __XXX__ 一一对应）
_PLACEHOLDER_MAP = {
    "__BG__": "bg", "__INK__": "ink", "__INK_SOFT__": "ink-soft",
    "__CARD__": "card", "__BORDER__": "border",
    "__ACCENT__": "accent", "__ACCENT_SOFT__": "accent-soft", "__ACCENT_BORDER__": "accent-border",
    "__WARN__": "warn", "__WARN_SOFT__": "warn-soft", "__WARN_BORDER__": "warn-border",
    "__DANGER__": "danger", "__DANGER_SOFT__": "danger-soft", "__DANGER_BORDER__": "danger-border",
    "__BTN_BG__": "btn-bg", "__BTN_TEXT__": "btn-text", "__LOGO_COLOR__": "logo-color",
}


def _build_html() -> str:
    html = _HTML_TEMPLATE
    v = _theme_vars()
    for placeholder, key in _PLACEHOLDER_MAP.items():
        html = html.replace(placeholder, v[key])
    return html


class _OllamaRequestThread(QThread):
    """在后台线程真正发起 requests 请求，避免阻塞 GUI 主线程。"""
    done = pyqtSignal(str, str)   # request_id, result_json（{"ok":bool,"data"/"error":...}）

    def __init__(self, request_id: str, kind: str, payload: dict, parent=None):
        super().__init__(parent)
        self.request_id = request_id
        self.kind = kind        # "tags" | "chat"
        self.payload = payload

    def run(self):
        try:
            if self.kind == "tags":
                r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
                if not r.ok:
                    raise RuntimeError(f"HTTP {r.status_code}")
                result = {"ok": True, "data": r.json()}
            else:
                model = self.payload.get("model", "")
                body = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": self.payload.get("system", "")},
                        {"role": "user",   "content": self.payload.get("user", "")},
                    ],
                    "stream": False,
                }
                if self.payload.get("expectJSON"):
                    body["format"] = "json"
                    body["options"] = {"temperature": 0.3}
                r = requests.post(
                    f"{OLLAMA_BASE}/api/chat", json=body,
                    timeout=(15, 600),
                )
                if not r.ok:
                    raise RuntimeError(
                        f'Ollama 返回错误状态码 {r.status_code}，请检查模型名称 '
                        f'"{model}" 是否已通过 ollama pull 下载。'
                    )
                result = {"ok": True, "data": r.json()}
        except requests.RequestException:
            result = {"ok": False, "error": f"无法连接到 Ollama（{OLLAMA_BASE}）。请确认 Ollama 已启动（ollama serve）。"}
        except Exception as e:
            result = {"ok": False, "error": str(e)}
        self.done.emit(self.request_id, json.dumps(result, ensure_ascii=False))


class _OllamaBridge(QObject):
    """暴露给网页 JS 的桥接对象（通过 QWebChannel），JS 调用它而不是直接 fetch，
    从根源上绕开 QWebEngineView 里 origin=null 触发的浏览器 CORS 拦截。"""
    tagsReady = pyqtSignal(str, str)   # request_id, result_json
    chatReady = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._threads = {}   # request_id -> QThread，防止提前被 GC

    @pyqtSlot(str)
    def listModels(self, request_id):
        self._spawn(request_id, "tags", {}, self.tagsReady)

    @pyqtSlot(str, str)
    def chat(self, request_id, payload_json):
        try:
            payload = json.loads(payload_json)
        except Exception:
            payload = {}
        self._spawn(request_id, "chat", payload, self.chatReady)

    # ── 文件产出（同步返回，本地磁盘 IO 很快，无需开线程）────────────────
    @pyqtSlot(str, result=str)
    def saveElements(self, payload_json):
        """第一步“确认元素”：新建 日期+项目名+序号 目录，并写入第一步元素文本。
        入参 JSON：{projectName, elementsText}
        返回 JSON：{ok, dir, path} 或 {ok:false, error}"""
        try:
            p = json.loads(payload_json)
            proj_dir = _make_project_dir(p.get("projectName", "") or "未命名项目")
            path = os.path.join(proj_dir, "01_元素.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(p.get("elementsText", "") or "")
            return json.dumps({"ok": True, "dir": proj_dir, "path": path}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def saveDesign(self, payload_json):
        """第二步“确认设计面板”：把设计面板文本写进同一个项目目录。
        入参 JSON：{dir, projectName, designText}
        返回 JSON：{ok, dir, path} 或 {ok:false, error}"""
        try:
            p = json.loads(payload_json)
            proj_dir = p.get("dir", "") or ""
            if not proj_dir or not os.path.isdir(proj_dir):
                # 没有第一步目录时兜底：按项目名新建
                proj_dir = _make_project_dir(p.get("projectName", "") or "未命名项目")
            path = os.path.join(proj_dir, "02_设计面板.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(p.get("designText", "") or "")
            return json.dumps({"ok": True, "dir": proj_dir, "path": path}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, result=bool)
    def copyToClipboard(self, text):
        """第三步各处“复制”按钮：在桌面宿主里，网页 origin 是 null，
        navigator.clipboard 常被拦；直接用 Qt 系统剪贴板最稳。"""
        try:
            cb = QApplication.clipboard()
            cb.setText(text or "")
            return True
        except Exception:
            return False

    @pyqtSlot(str, result=str)
    def saveOutputs(self, payload_json):
        """第三步 A/B/C 生成完成后：把三份纯文本各存一个文件到项目目录。
        入参 JSON：{dir, projectName, a, b, c}
        返回 JSON：{ok, dir, paths:[...]} 或 {ok:false, error}"""
        try:
            p = json.loads(payload_json)
            proj_dir = p.get("dir", "") or ""
            if not proj_dir or not os.path.isdir(proj_dir):
                proj_dir = _make_project_dir(p.get("projectName", "") or "未命名项目")
            files = [
                ("03_A_故事简讯与镜头提示词.txt", p.get("a", "") or ""),
                ("04_B_角色提示词.txt",           p.get("b", "") or ""),
                ("05_C_电影制作板.txt",           p.get("c", "") or ""),
            ]
            paths = []
            for name, text in files:
                fp = os.path.join(proj_dir, name)
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(text)
                paths.append(fp)
            return json.dumps({"ok": True, "dir": proj_dir, "paths": paths}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def saveOneOutput(self, payload_json):
        """第三步单区重新生成后：只写对应的一份文件。
        入参 JSON：{dir, projectName, which: 'a'|'b'|'c', text}
        返回 JSON：{ok, dir, path} 或 {ok:false, error}"""
        try:
            p = json.loads(payload_json)
            proj_dir = p.get("dir", "") or ""
            if not proj_dir or not os.path.isdir(proj_dir):
                proj_dir = _make_project_dir(p.get("projectName", "") or "未命名项目")
            name_map = {
                "a": "03_A_故事简讯与镜头提示词.txt",
                "b": "04_B_角色提示词.txt",
                "c": "05_C_电影制作板.txt",
            }
            which = (p.get("which", "") or "").lower()
            if which not in name_map:
                return json.dumps({"ok": False, "error": "which 必须是 a/b/c"}, ensure_ascii=False)
            fp = os.path.join(proj_dir, name_map[which])
            with open(fp, "w", encoding="utf-8") as f:
                f.write(p.get("text", "") or "")
            return json.dumps({"ok": True, "dir": proj_dir, "path": fp}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    def _spawn(self, request_id, kind, payload, signal):
        t = _OllamaRequestThread(request_id, kind, payload, self)

        def _on_done(rid, result_json, _sig=signal):
            _sig.emit(rid, result_json)
            self._threads.pop(rid, None)

        t.done.connect(_on_done)
        self._threads[request_id] = t
        t.start()


class PageDirector(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.fallback = None
        self.bridge = None
        self.channel = None
        if _WEBENGINE_OK:
            self.web = QWebEngineView()
            self.web.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            if _WEBCHANNEL_OK:
                self.bridge = _OllamaBridge(self)
                self.channel = QWebChannel(self)
                self.channel.registerObject("bridge", self.bridge)
                self.web.page().setWebChannel(self.channel)
            # 没装 QtWebChannel 时不致命：网页检测不到桥接会自动退回原来的
            # fetch() 直连，只是会撞上文首说的 CORS 拦截。

            self.web.setHtml(_build_html(), QUrl("about:blank"))
            root.addWidget(self.web, 1)
        else:
            self.web = None
            fallback = QLabel(
                "未检测到 PyQtWebEngine，无法加载导演台。\n"
                "请先执行：pip install PyQtWebEngine"
            )
            fallback.setAlignment(Qt.AlignCenter)
            self.fallback = fallback
            root.addWidget(fallback, 1)

        self._apply_static_style()
        theme.changed.connect(self._on_theme_changed)

    def _apply_static_style(self):
        if self.web is not None:
            self.web.setStyleSheet(fmt(WEB_VIEW_QSS))
        if self.fallback is not None:
            self.fallback.setStyleSheet(fmt(FALLBACK_LABEL_QSS))

    def _on_theme_changed(self, *_args):
        """主题切换：不重载整页，只用 JS 覆盖 CSS 变量，保留用户已填写/已生成的内容。"""
        self._apply_static_style()
        if self.web is None:
            return
        payload = json.dumps(_theme_vars(), ensure_ascii=False)
        self.web.page().runJavaScript(
            f"window.applyTheme && window.applyTheme({payload});"
        )


# ── 网页内容（原 assets/director_agent.html，现内嵌于此，单文件维护）───────
_HTML_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>导演 Agent · 故事转 Seedance 2.0 提示词</title>
<style>
  /* 配色不再写死：由宿主程序（page_director.py）在加载完成后通过
     window.applyTheme({...}) 用 --token 覆盖，随桌面助手深/浅主题联动。
     这里的 __TOKEN__ 占位符只是首屏兜底值（对应桌面助手默认的深色主题），
     真实值以 Python 传入的为准。*/
  :root{
    --bg:__BG__;
    --ink:__INK__;
    --ink-soft:__INK_SOFT__;
    --card:__CARD__;
    --border:__BORDER__;
    --accent:__ACCENT__;
    --accent-soft:__ACCENT_SOFT__;
    --accent-border:__ACCENT_BORDER__;
    --warn:__WARN__;
    --warn-soft:__WARN_SOFT__;
    --warn-border:__WARN_BORDER__;
    --danger:__DANGER__;
    --danger-soft:__DANGER_SOFT__;
    --danger-border:__DANGER_BORDER__;
    --btn-bg:__BTN_BG__;
    --btn-text:__BTN_TEXT__;
    --logo-color:__LOGO_COLOR__;
    --font-display: ui-serif, Georgia, "Songti SC", "Times New Roman", serif;
    --font-body: "微软雅黑", ui-sans-serif, -apple-system, "PingFang SC", "Segoe UI", system-ui, sans-serif;
    --font-mono: ui-monospace, "SFMono-Regular", Consolas, "Courier New", monospace;
  }
  body{transition:background 0.2s ease, color 0.2s ease;}
  *{box-sizing:border-box;}
  body{
    margin:0; background:var(--bg); color:var(--ink);
    font-family:var(--font-body); line-height:1.6; padding-bottom:80px;
  }
  header{border-bottom:1px solid var(--border);}
  .header-inner{
    max-width:860px; margin:0 auto; padding:28px 24px 20px;
    display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap; gap:16px;
  }
  .brand{display:flex; align-items:center; gap:12px;}
  .slate{width:44px; height:34px; position:relative; flex-shrink:0; margin-right:12px;}
  .slate .top{position:absolute; top:0; left:0; width:100%; height:10px; background:repeating-linear-gradient(115deg, var(--logo-color) 0 5px, #fff 5px 10px); border-radius:3px 3px 0 0;}
  .slate .body{position:absolute; top:10px; left:0; width:100%; height:24px; background:var(--logo-color); border-radius:0 0 3px 3px;}
  .brand h1{font-family:var(--font-display); font-size:20px; font-weight:500; margin:0; letter-spacing:0.2px;}
  .brand .sub{font-size:12px; color:var(--ink-soft); margin-top:2px;}
  .config{display:flex; gap:8px; align-items:center; font-size:12px; color:var(--ink-soft); flex-wrap:wrap;}
  .config select{font-family:var(--font-mono); font-size:12px; padding:6px 8px; border:1px solid var(--border); border-radius:4px; background:var(--card); width:240px;}
  .config input[type=text]{font-family:var(--font-mono); font-size:12px; padding:6px 8px; border:1px solid var(--border); border-radius:4px; background:var(--card); width:200px;}
  .status-dot{width:8px; height:8px; border-radius:50%; background:var(--border); flex-shrink:0;}
  .status-dot.ok{background:var(--accent);}
  .status-dot.bad{background:var(--danger);}
  .icon-btn{width:30px; height:30px; padding:0; display:inline-flex; align-items:center; justify-content:center; font-size:15px; line-height:1;}

  main{max-width:860px; margin:0 auto; padding:32px 24px;}
  .progress{display:flex; gap:0; margin-bottom:28px; font-family:var(--font-mono); font-size:12px;}
  .progress .p{flex:1; padding:10px 4px; text-align:center; color:var(--ink-soft); border-bottom:2px solid var(--border);}
  .progress .p.active{color:var(--ink); border-bottom-color:var(--accent); font-weight:600;}
  .progress .p.done{color:var(--accent);}

  section{display:none;}
  section.show{display:block;}

  h2{font-family:var(--font-display); font-size:22px; font-weight:500; margin:0 0 6px;}
  h3{font-family:var(--font-display); font-size:18px; font-weight:500; margin:28px 0 12px;}
  .hint{color:var(--ink-soft); font-size:13px; margin:0 0 20px;}

  textarea, input[type=text], input[type=number], select{
    width:100%; font-family:var(--font-body); font-size:14px; padding:10px 12px;
    border:1px solid var(--border); border-radius:6px; background:var(--card); color:var(--ink);
  }
  textarea{min-height:120px; resize:vertical; font-family:var(--font-mono); font-size:13px;}
  label{display:block; font-size:12px; color:var(--ink-soft); margin:0 0 6px; font-weight:600;}
  .field{margin-bottom:18px;}

  button{
    font-family:var(--font-body); font-size:14px; font-weight:600; padding:10px 18px;
    border-radius:6px; border:1px solid var(--btn-bg); background:var(--btn-bg); color:var(--btn-text); cursor:pointer;
  }
  button.secondary{background:var(--card); color:var(--ink); border-color:var(--border);}
  button.small{padding:6px 12px; font-size:12px; font-weight:500;}
  /* 第三步 A/B/C 区域「复制X内容」：相对 .small 加宽约 1 倍、高度 +6px */
  button.copy-pane-btn{padding:9px 24px; font-size:12px; font-weight:500;}
  button:disabled{opacity:0.45; cursor:not-allowed;}
  button:hover:not(:disabled){opacity:0.88;}

  .card{background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px; margin-bottom:14px;}
  .card-head{display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;}
  .card-head .tag{font-family:var(--font-mono); font-size:11px; color:var(--accent); background:var(--accent-soft); padding:2px 8px; border-radius:10px;}
  .grid2{display:grid; grid-template-columns:1fr 1fr; gap:12px;}
  .grid3{display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px;}
  @media(max-width:640px){.grid2,.grid3{grid-template-columns:1fr;}}

  .actions{display:flex; gap:10px; margin-top:24px; align-items:center;}
  .msg{font-size:13px; padding:10px 14px; border-radius:6px; margin:14px 0;}
  /* 操作行内状态（如「正在识别元素」）贴行最右侧，与按钮分行对齐 */
  .actions > .msg,
  .actions > #step1Msg{
    margin-left:auto;
    margin-top:0;
    margin-bottom:0;
    flex-shrink:0;
    display:inline-flex;
    align-items:center;
  }
  .msg.err{background:var(--danger-soft); color:var(--danger); border:1px solid var(--danger-border);}
  .msg.warn{background:var(--warn-soft); color:var(--warn); border:1px solid var(--warn-border);}
  .msg.info{background:var(--accent-soft); color:var(--accent); border:1px solid var(--accent-border);}
  .spinner{display:inline-block; width:14px; height:14px; border:2px solid var(--border); border-top-color:var(--accent); border-radius:50%; animation:spin 0.7s linear infinite; margin-right:8px; vertical-align:-2px;}
  @keyframes spin{to{transform:rotate(360deg);}}

  table{width:100%; border-collapse:collapse; font-size:13px;}
  th{text-align:left; font-family:var(--font-mono); font-size:11px; color:var(--ink-soft); font-weight:500; padding:6px 8px; border-bottom:1px solid var(--border);}
  td{padding:6px 8px; border-bottom:1px solid var(--border); vertical-align:top;}
  .shot-no{font-family:var(--font-mono); color:var(--accent); font-weight:600;}
  .prompt-block{white-space:pre-wrap; font-family:var(--font-mono); font-size:12.5px; background:var(--accent-soft); padding:10px; border-radius:6px;}
  .ref-chip{display:inline-block; font-size:11px; font-family:var(--font-mono); background:var(--border); color:var(--ink-soft); padding:2px 8px; border-radius:10px; margin:2px 4px 0 0;}

  .remove-btn{background:none; border:none; color:var(--danger); font-size:12px; padding:2px 6px; font-weight:600;}
  .remove-btn:hover{opacity:0.7;}
  hr{border:none; border-top:1px solid var(--border); margin:28px 0;}

  .outline-row{display:flex; gap:8px; align-items:center; margin-bottom:8px; background:var(--card); border-radius:6px;}
  .outline-row.dragging{opacity:0.4;}
  .drag-handle{cursor:grab; color:var(--ink-soft); font-size:14px; padding:2px 2px; flex-shrink:0; user-select:none;}
  .drag-handle:active{cursor:grabbing;}
  .outline-row .shot-no{width:30px; flex-shrink:0;}
  .outline-row input[type=number]{width:64px; flex-shrink:0;}
  .outline-row input[type=text]{flex:1;}
  .outline-total{font-size:12px; color:var(--ink-soft); margin:10px 0 16px;}
</style>
</head>
<body>

<header>
  <div class="header-inner">
    <div class="brand">
      <div class="slate"><div class="top"></div><div class="body"></div></div>
      <div>
        <h1>导演台Agent v0.1</h1>
        <div class="sub">故事 → A 电影制作板 / B 角色提示词 / C 镜头提示词</div>
      </div>
    </div>
    <div class="config">
      <span class="status-dot" id="statusDot"></span>
      <span title="固定连接 http://localhost:11434">Ollama</span>
      <button class="secondary icon-btn" id="refreshModels" title="刷新模型列表" aria-label="刷新模型列表">⟳</button>
      <select id="ollamaModelSelect">
        <option value="qwen2.5:14b">qwen2.5:14b</option>
        <option value="__custom__">自定义模型名…</option>
      </select>
      <input type="text" id="ollamaModelCustom" placeholder="输入模型名" style="display:none;">
    </div>
  </div>
</header>

<main>
  <div class="progress">
    <div class="p active" id="prog1">① 上传故事 · 元素</div>
    <div class="p" id="prog2">② 设计面板</div>
    <div class="p" id="prog3">③ 三份产出</div>
  </div>

  <!-- STEP 1 -->
  <section id="step1" class="show">
    <h2>第一步 · 上传故事</h2>
    <p class="hint">粘贴故事文本，AI 会整理并弹出元素面板——包括人物、动物、关键道具、关键场景，你可以增删改每一项。</p>
    <div class="field">
      <label>故事文本</label>
      <textarea id="storyInput" placeholder="在这里粘贴你的故事……"></textarea>
    </div>
    <div class="actions">
      <button id="extractBtn">AI 整理元素</button>
      <span id="step1Msg"></span>
    </div>

    <div class="field" id="projectNameField" style="display:none; margin-top:16px;">
      <label>项目名称（点“AI 整理元素”后由 AI 自动拟定，可修改；用于生成产出目录 日期+项目名+序号）</label>
      <input type="text" id="projectNameInput" placeholder="项目名称">
    </div>

    <div id="characterList" style="margin-top:22px;"></div>
    <div class="actions" id="step1Confirm" style="display:none;">
      <button class="secondary small" id="addCharBtn">+ 添加元素</button>
      <button class="secondary small" id="exportProgressBtn1">⬇ 导出元素</button>
      <button class="secondary small" id="importProgressBtn1">⬆ 导入元素</button>
      <button id="confirmCharsBtn" style="margin-left:auto;">确认元素 → 进入设计面板</button>
    </div>
  </section>

  <!-- STEP 2 -->
  <section id="step2">
    <h2>第二步 · 设计面板</h2>
    <p class="hint">以下字段由 AI 根据故事和已确认的元素自动草拟，你可以直接修改后确认。</p>
    <div id="step2Msg" class="msg"></div>

    <div class="field">
      <label>Audience 受众定位</label>
      <input type="text" id="designAudience" placeholder="例：喜欢黑色幽默、反转短剧的短视频观众">
    </div>
    <div class="field">
      <label>Must include 必须出现的关键画面（每行一条）</label>
      <textarea id="designMustInclude" placeholder="每行填写一个必须出现的画面"></textarea>
    </div>
    <div class="grid3">
      <div class="field">
        <label>Language</label>
        <select id="designLanguage"><option>中文</option><option>English</option></select>
      </div>
      <div class="field">
        <label>Aspect Ratio</label>
        <select id="designAspectRatio"><option>16:9</option><option>1:1</option><option>9:16</option></select>
      </div>
      <div class="field">
        <label>Art Style</label>
        <select id="designArtStyle">
          <option>电影感</option><option>商业</option><option>未来感</option><option>复古</option>
          <option>动漫</option><option>3D</option><option>插画</option><option>写实</option><option>实验性</option>
        </select>
      </div>
    </div>
    <!-- 与上一行 grid3 同宽同列：Duration↔Language、镜头数↔Aspect Ratio、生成按钮↔Art Style -->
    <div class="grid3" style="align-items:end;">
      <div class="field">
        <label>Video Duration（秒）</label>
        <input type="number" id="designDuration" value="30" min="4" max="600">
      </div>
      <div class="field">
        <label>镜头数（大致）</label>
        <input type="number" id="designShotCount" value="4" min="1" max="60">
      </div>
      <div class="field">
        <label style="visibility:hidden;">生成</label>
        <button id="regenOutlineBtn" style="width:100%; background:var(--accent); border-color:var(--accent);">↻ 生成镜头大纲</button>
      </div>
    </div>
    <div id="outlineMsg" class="msg" style="margin-top:-8px;"></div>

    <h3>镜头大纲</h3>
    <p class="hint" style="margin-top:-8px;">AI 根据镜头数草拟的简化大纲，先在这里把最重要的镜头内容和顺序定下来，第三步会据此细化成完整镜头。</p>
    <div id="shotOutlineList"></div>
    <div class="outline-total" id="outlineTotal"></div>
    <div class="actions">
      <button class="secondary small" id="addOutlineBtn">+ 添加镜头</button>
      <button class="secondary small" id="exportProgressBtn">⬇ 导出进度</button>
      <button class="secondary small" id="importProgressBtn">⬆ 导入进度</button>
      <input type="file" id="importFileInput" accept="application/json" style="display:none;">
      <button id="confirmDesignBtn" style="margin-left:auto;">确认设计面板</button>
    </div>
  </section>

  <!-- STEP 3 -->
  <section id="step3">
    <h2>第三步 · 三份产出</h2>
    <p class="hint">按 A → B → C 依次生成：A/B 生成完成后倒计时 20 秒自动进入下一步（也可手动提前点确认）；全部完成后自动保存为文本文件。各区可「复制X内容」；「重新生成 A/B/C」会重跑本区并自动写回对应 txt。</p>

    <div id="blockA">
      <h3>A 故事简讯 + 镜头提示词</h3>
      <div id="msgA" class="msg"></div>
      <div id="paneA"></div>
    </div>

    <div id="blockB" style="display:none;">
      <hr>
      <h3>B 角色提示词（多角度模型参考）</h3>
      <div id="msgB" class="msg"></div>
      <div id="paneB"></div>
    </div>

    <div id="blockC" style="display:none;">
      <hr>
      <h3>C 电影制作板</h3>
      <div id="msgC" class="msg"></div>
      <div id="paneC"></div>
    </div>

    <!-- 三份产出保存完成后的提示固定放在第三步页面最下方 -->
    <div id="finishMsg" class="msg" style="display:none; margin-top:24px;"></div>
  </section>
</main>

<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
const OLLAMA_BASE_URL = 'http://localhost:11434';

// ── 宿主桥接（QWebChannel）─────────────────────────────────────────────
// 桌面助手里这个页面是内嵌网页，origin 是 null，浏览器会把直连 Ollama 的
// fetch() 当跨域请求拦掉（CORS）。所以优先走 Python 桥接转发；如果不在
// 桌面助手里（比如你直接双击这个 html 文件用浏览器打开），bridge 会是
// null，自动退回下面的原生 fetch() 路径，两种方式都能正常用。
let _bridge = null;
const _pending = {};
function _genReqId(){ return 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2,8); }

if (typeof qt !== 'undefined' && qt.webChannelTransport) {
  new QWebChannel(qt.webChannelTransport, function(channel){
    _bridge = channel.objects.bridge;
    _bridge.tagsReady.connect(function(reqId, json){
      const cb = _pending[reqId]; delete _pending[reqId];
      if (cb) cb(JSON.parse(json));
    });
    _bridge.chatReady.connect(function(reqId, json){
      const cb = _pending[reqId]; delete _pending[reqId];
      if (cb) cb(JSON.parse(json));
    });
    loadModelList();
  });
} else {
  window.addEventListener('load', loadModelList);
}

function bridgeTags(){
  return new Promise((resolve) => {
    const id = _genReqId();
    _pending[id] = resolve;
    _bridge.listModels(id);
  });
}
function bridgeChat(model, system, user, expectJSON){
  return new Promise((resolve) => {
    const id = _genReqId();
    _pending[id] = resolve;
    _bridge.chat(id, JSON.stringify({model, system, user, expectJSON: !!expectJSON}));
  });
}

// 调用宿主 Python 侧的同步文件写入槽（saveElements / saveDesign）。
// 未在桌面宿主内（浏览器直开）时 _bridge 为 null，返回 null，调用方走浏览器下载兜底。
function bridgeCall(method, payloadObj){
  return new Promise((resolve) => {
    if (!_bridge || typeof _bridge[method] !== 'function'){ resolve(null); return; }
    try {
      _bridge[method](JSON.stringify(payloadObj), function(resJson){
        try { resolve(JSON.parse(resJson)); } catch(e){ resolve(null); }
      });
    } catch(e){ resolve(null); }
  });
}

function downloadPlain(text, filename){
  const blob = new Blob([text], {type:'text/plain;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

// 第一步“确认元素”写盘的文本内容
function buildElementsText(){
  let t = '=== 第一步 · 已确认元素 ===\n';
  t += `项目名称：${state.projectName || '未命名项目'}\n`;
  t += `确认时间：${new Date().toLocaleString()}\n\n`;
  t += `故事文本：\n${state.storyText || ''}\n\n`;
  t += `共 ${state.characters.length} 个元素\n\n`;
  state.characters.forEach((c, i) => {
    t += `【${i+1}】${c.name||''}（${c.type||''}）\n`;
    t += `  视觉细节：${c.visual||''}\n`;
    t += `  性格/习性/氛围：${c.vibe||'—'}\n`;
    t += `  一致性方案：${c.consistencyPlan||'B'}\n\n`;
  });
  return t;
}

// 第二步“确认设计面板”写盘的文本内容（以用户最终镜头大纲为准）
function buildDesignText(){
  const d = state.design;
  const total = (d.shotOutline||[]).reduce((a,s)=>a+(+s.duration||0),0);
  let t = '=== 第二步 · 已确认设计面板 ===\n';
  t += `项目名称：${state.projectName || '未命名项目'}\n`;
  t += `确认时间：${new Date().toLocaleString()}\n\n`;
  t += `受众定位：${d.audience||''}\n`;
  t += `必含关键画面：\n${(d.mustInclude||[]).map(m=>'  · '+m).join('\n') || '  （无）'}\n\n`;
  t += `语言：${d.language}\n画幅：${d.aspectRatio}\n艺术风格：${d.artStyle}\n\n`;
  t += `最终镜头数：${(d.shotOutline||[]).length}\n`;
  t += `最终总时长：${total} 秒（以下方镜头大纲各条 duration 之和为准）\n\n`;
  t += `镜头大纲（最终版，第三步据此逐条细化，数量与时长均不得改动）：\n`;
  (d.shotOutline||[]).forEach((s, i) => {
    t += `  #${i+1} [${s.duration}s] ${s.summary||''}\n`;
  });
  return t;
}

// ── 通用“复制”能力（第三步一切产出都要能全部复制 + 分段复制）─────────────
// 桌面宿主里页面 origin 是 null，navigator.clipboard 常被拦，优先走 Python
// 系统剪贴板槽 copyToClipboard；浏览器直开时退回 navigator.clipboard / execCommand。
function copyRaw(text){
  return new Promise((resolve) => {
    if (_bridge && typeof _bridge.copyToClipboard === 'function'){
      try {
        _bridge.copyToClipboard(String(text||''), function(ok){
          if (ok){ resolve(true); return; }
          _fallbackCopy(String(text||'')).then(resolve);
        });
        return;
      } catch(e){}
    }
    _fallbackCopy(String(text||'')).then(resolve);
  });
}
async function _fallbackCopy(text){
  try { await navigator.clipboard.writeText(text); return true; } catch(e){}
  try {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position='fixed'; ta.style.top='-1000px'; ta.style.opacity='0';
    document.body.appendChild(ta); ta.focus(); ta.select();
    const ok = document.execCommand('copy'); document.body.removeChild(ta);
    return ok;
  } catch(e){ return false; }
}
function flashBtn(btn, ok){
  if (!btn.dataset.label) btn.dataset.label = btn.textContent;
  btn.textContent = ok ? '✓ 已复制' : '复制失败';
  setTimeout(() => { btn.textContent = btn.dataset.label; }, 1200);
}
// 复制按钮的文本存这里，按钮只带一个短 id，避免把长文本塞进 HTML 属性里出转义问题
const _copyStore = {};
function copyBtnHtml(text, label){
  const id = 'cp' + Date.now().toString(36) + Math.random().toString(36).slice(2,7);
  _copyStore[id] = String(text||'');
  return `<button class="secondary small copy-btn" data-copyid="${id}">${escapeHtml(label||'复制')}</button>`;
}
function wireCopyButtons(container){
  container.querySelectorAll('.copy-btn').forEach(btn => {
    if (btn._wired) return; btn._wired = true;
    btn.dataset.label = btn.textContent;
    btn.addEventListener('click', async () => {
      const ok = await copyRaw(_copyStore[btn.dataset.copyid] || '');
      flashBtn(btn, ok);
    });
  });
}

// ── 三份产出的纯文本格式化（都以纯文本为准，方便整理复制/保存）───────────
function _boardShotCount(){
  if (state.storyboard && Array.isArray(state.storyboard.shots)) return state.storyboard.shots.length;
  return (state.design.shotOutline||[]).length;
}
function _boardTotal(){
  const t = (state.design.shotOutline||[]).reduce((a,s)=>a+(+s.duration||0),0);
  return t || state.design.duration || 0;
}

// A：故事简讯 + 镜头提示词（纯文本，参考“1、内容”式的分段清单）
function formatA(a){
  a = a || {};
  const shots = a.shots || [];
  let t = `故事简讯：${a.brief||''}\n\n`;
  shots.forEach((s, i) => {
    let line = `${i+1}、[${s.duration||0}秒] ${s.content||''}`;
    if (s.dialogue && String(s.dialogue).trim()) line += `　台词：“${s.dialogue}”`;
    t += line + '\n';
  });
  return t.trim();
}

// B：角色提示词（纯文本，一个可整体复制的段落，不做成一块块卡片）
function formatB(arr){
  arr = arr || [];
  return arr.map(c => {
    let t = `【${c.name||''}｜${c.type||''}】\n`;
    t += `多角度模型：${c.modelSheet||''}\n`;
    t += `服装配饰：${c.wardrobe||''}\n`;
    t += `身份一致性：${c.consistency||''}`;
    return t;
  }).join('\n\n');
}

// C：电影制作板（纯文本，简洁，整份≤1000汉字，按用户定的镜头数）
function formatC(b){
  b = b || {};
  const n = _boardShotCount();
  const total = _boardTotal();
  const cd = b.creativeDirection || {};
  const e = b.environmentDesign || {};
  const au = b.audioTone || {};
  const cn = b.cinematographyNotes || {};
  let t = '';
  if (b.concept) t += `概念：${b.concept}\n`;
  t += `【共享创意指导】镜头数：${n}；总时长：${total}秒；画幅：${state.design.aspectRatio}；调色板：${cd.palette||''}；环境背景：${cd.environmentBackground||''}；整体限制：${cd.overallConstraints||''}\n`;
  t += `【环境与场景设计】地点：${e.location||''}；戏剧特征：${e.dramaticFeatures||''}；俯视路径与机位：${e.topDownMap||''}` + ((e.cameraPositions||[]).length?('（'+(e.cameraPositions||[]).map(c=>`${c.tag||''}:${c.shotType||''}`).join('、')+'）'):'') + `\n`;
  t += `【故事板】` + (b.storyboardFrames||[]).map(f=>`#${f.frame} ${f.shotSize||''}·${f.movement||''} ${f.action||''}(${f.moodProgression||''})`).join('；') + `\n`;
  t += `【灯光/情绪/风格】` + (b.lightingMood||[]).map(l=>`${l.timeOfDay||''}·${l.lightQuality||''}·${l.atmosphere||''}·${l.texture||''}`).join('；') + `\n`;
  t += `【情绪与关键词】` + (b.moodKeywords||[]).join('、') + `\n`;
  t += `【音频/音调】环境声：${au.ambient||''}；音乐：${au.musicStyle||''}；氛围：${au.soundscape||''}\n`;
  t += `【电影摄影笔记】镜头：${cn.lensCharacter||''}；运动：${cn.motionStyle||''}；后期：${cn.postProcessing||''}；哲学：${cn.visualPhilosophy||''}`;
  return t.trim();
}

// 主题由宿主程序（page_director.py）在深浅色切换时统一驱动，见下方 window.applyTheme。
// 供宿主程序调用：用 CSS 自定义属性直接覆盖，不刷新页面，
// 保证故事文本 / 已生成的元素卡 / 镜头大纲等状态不丢失。
window.applyTheme = function(vars){
  const root = document.documentElement.style;
  Object.keys(vars).forEach(k => root.setProperty('--' + k, vars[k]));
};

const state = {
  storyText: '',
  projectName: '',
  projectDir: '',              // 第一步“确认元素”后由 Python 返回的项目目录
  confirmedElementsText: '',   // 第一步写入磁盘的元素文本，第二步据此设计
  confirmedDesignText: '',     // 第二步写入磁盘的设计文本，第三步据此生成
  characters: [],
  design: { audience:'', mustInclude:[], language:'中文', aspectRatio:'16:9', artStyle:'写实', duration:30, shotCount:4, shotOutline:[] },
  storyboard: null,
  shotScript: null,            // A：{brief, shots:[{duration,content,dialogue}]}
  characterSheets: null,       // B：[{name,type,modelSheet,wardrobe,consistency}]
  board: null,                 // C：电影制作板结构化内容
  textA: '', textB: '', textC: '',   // 三份产出的纯文本（可编辑，复制/保存以此为准）
  abcStage: 0,                 // 第三步进度：1=A完成 2=B完成 3=C完成（≥2 时 A 区显示「重新生成A」等）
  genToken: 0,                 // 生成令牌：点“重试”会+1，旧的在途请求返回后据此丢弃
  characterCards: null,
  prompts: null
};

function baseUrl(){ return OLLAMA_BASE_URL; }
function modelName(){
  const sel = document.getElementById('ollamaModelSelect');
  if (sel.value === '__custom__'){
    return document.getElementById('ollamaModelCustom').value.trim();
  }
  return sel.value;
}
document.getElementById('ollamaModelSelect').addEventListener('change', (e) => {
  document.getElementById('ollamaModelCustom').style.display = (e.target.value === '__custom__') ? 'block' : 'none';
});

async function loadModelList(){
  const sel = document.getElementById('ollamaModelSelect');
  const dot = document.getElementById('statusDot');
  try {
    let data;
    if (_bridge){
      const res = await bridgeTags();
      if (!res.ok) throw new Error(res.error || '获取模型列表失败');
      data = res.data;
    } else {
      const res = await fetch(baseUrl() + '/api/tags');
      if (!res.ok) throw new Error();
      data = await res.json();
    }
    const models = (data.models || []).map(m => m.name || m.model).filter(Boolean);
    dot.className = 'status-dot ok';
    if (!models.length) return;
    const current = sel.value === '__custom__' ? null : sel.value;
    sel.innerHTML = '';
    models.forEach(name => {
      const opt = document.createElement('option');
      opt.value = name; opt.textContent = name;
      sel.appendChild(opt);
    });
    const customOpt = document.createElement('option');
    customOpt.value = '__custom__'; customOpt.textContent = '自定义模型名…';
    sel.appendChild(customOpt);
    if (current && models.includes(current)) sel.value = current;
  } catch(e){
    dot.className = 'status-dot bad';
  }
}
document.getElementById('refreshModels').addEventListener('click', loadModelList);

function parseJSONLoose(text){
  let cleaned = text.trim();
  cleaned = cleaned.replace(/^```json\s*/i,'').replace(/^```\s*/,'').replace(/```\s*$/,'');
  try { return JSON.parse(cleaned); } catch(e){}
  const starts = ['{','['].map(c=>cleaned.indexOf(c)).filter(i=>i>=0);
  const start = starts.length ? Math.min(...starts) : -1;
  const end = Math.max(cleaned.lastIndexOf('}'), cleaned.lastIndexOf(']'));
  if (start >= 0 && end > start){
    try { return JSON.parse(cleaned.slice(start, end+1)); } catch(e){}
  }
  throw new Error('模型未返回合法 JSON，原始内容：\n' + text.slice(0,400));
}

async function callOllama(system, user, expectJSON, attempt){
  attempt = attempt || 1;
  let content;
  if (_bridge){
    const res = await bridgeChat(modelName(), system, user, expectJSON);
    if (!res.ok) throw new Error(res.error || 'Ollama 请求失败');
    content = (res.data.message && res.data.message.content) || '';
  } else {
    const url = baseUrl() + '/api/chat';
    const body = {
      model: modelName(),
      messages: [ {role:'system', content:system}, {role:'user', content:user} ],
      stream: false
    };
    if (expectJSON){ body.format = 'json'; body.options = { temperature: 0.3 }; }
    let res;
    try {
      res = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    } catch(e){
      throw new Error('无法连接到 Ollama（' + url + '）。请确认：① Ollama 已启动（ollama serve）② 如仍失败，尝试设置环境变量 OLLAMA_ORIGINS=* 后重启 Ollama。');
    }
    if (!res.ok) throw new Error('Ollama 返回错误状态码 ' + res.status + '，请检查模型名称 "' + modelName() + '" 是否已通过 ollama pull 下载。');
    const data = await res.json();
    content = (data.message && data.message.content) || '';
  }
  if (!expectJSON) return content;
  try {
    return parseJSONLoose(content);
  } catch(e){
    if (attempt < 3){
      return callOllama(system, user, expectJSON, attempt + 1);
    }
    throw new Error('模型连续 ' + attempt + ' 次都没有返回合法 JSON，可能是当前模型结构化输出能力偏弱，建议换一个模型（顶部下拉框可选），或者简化故事文本后重试。原始内容片段：\n' + content.slice(0,300));
  }
}

function setMsg(id, text, type){
  const el = document.getElementById(id);
  el.className = type ? 'msg ' + type : '';
  el.textContent = text || '';
  if (!text) el.className = '';
}
// 在消息区右侧追加一个“🔄 重试”按钮（用于卡住/失败时手动重跑当前步骤）
function _appendRetry(el, retryFn){
  if (!retryFn) return;
  const btn = document.createElement('button');
  btn.className = 'secondary small';
  btn.textContent = '🔄 重试';
  btn.style.marginLeft = '8px';
  btn.onclick = retryFn;
  el.appendChild(btn);
}
function setBusy(id, text, retryFn){
  const el = document.getElementById(id);
  el.className = 'msg info';
  el.innerHTML = '<span class="spinner"></span>' + text;
  _appendRetry(el, retryFn);   // 生成过程中也带重试，卡住时可直接重跑
}
function setError(id, text, retryFn){
  const el = document.getElementById(id);
  el.className = 'msg err';
  el.textContent = text || '';
  _appendRetry(el, retryFn);
}
// 修改某个按钮的文字/禁用/点击行为（用于生成中把触发按钮变成“X 内容生成中”）
function setBtn(id, text, disabled, onclick){
  const b = document.getElementById(id);
  if (!b) return;
  if (text != null) b.textContent = text;
  b.disabled = !!disabled;
  if (onclick) b.onclick = onclick;
}
function escapeHtml(s){ return String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }

// ---------- STEP 1: elements (人物/动物/道具/场景) ----------
function renderCharacters(){
  const container = document.getElementById('characterList');
  container.innerHTML = '';
  state.characters.forEach((c, idx) => {
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `
      <div class="card-head">
        <span class="tag">${c.type || '元素'}</span>
        <button class="remove-btn" data-idx="${idx}">删除</button>
      </div>
      <div class="grid2">
        <div class="field"><label>名称</label><input type="text" data-f="name" data-idx="${idx}" value="${escapeHtml(c.name||'')}"></div>
        <div class="field"><label>类型</label>
          <select data-f="type" data-idx="${idx}">
            <option ${c.type==='人类'?'selected':''}>人类</option>
            <option ${c.type==='动物'?'selected':''}>动物</option>
            <option ${c.type==='道具'?'selected':''}>道具</option>
            <option ${c.type==='场景'?'selected':''}>场景</option>
          </select>
        </div>
      </div>
      <div class="field"><label>视觉细节（外貌 / 材质 / 环境等）</label><input type="text" data-f="visual" data-idx="${idx}" value="${escapeHtml(c.visual||'')}"></div>
      <div class="grid2">
        <div class="field"><label>性格 / 习性 / 氛围（人物动物填性格，道具场景可填氛围）</label><input type="text" data-f="vibe" data-idx="${idx}" value="${escapeHtml(c.vibe||'')}"></div>
        <div class="field"><label>一致性方案</label>
          <select data-f="consistencyPlan" data-idx="${idx}">
            <option value="A" ${c.consistencyPlan==='A'?'selected':''}>A 文字锁定</option>
            <option value="B" ${(!c.consistencyPlan||c.consistencyPlan==='B')?'selected':''}>B 定妆/参考图 @引用（推荐）</option>
            <option value="C" ${c.consistencyPlan==='C'?'selected':''}>C 预置素材</option>
          </select>
        </div>
      </div>
    `;
    container.appendChild(div);
  });
  container.querySelectorAll('[data-f]').forEach(el => {
    el.addEventListener('input', e => {
      const idx = +e.target.dataset.idx, f = e.target.dataset.f;
      state.characters[idx][f] = e.target.value;
      if (f === 'type') renderCharacters();
    });
  });
  container.querySelectorAll('.remove-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      state.characters.splice(+e.target.dataset.idx, 1);
      renderCharacters();
    });
  });
  document.getElementById('step1Confirm').style.display = state.characters.length ? 'flex' : 'none';
  if (state.characters.length){
    setMsg('step1Msg', `当前 ${state.characters.length} 个元素，可在下方编辑`, 'info');
  }
}

document.getElementById('addCharBtn').onclick = () => {
  state.characters.push({name:'新元素', type:'人类', visual:'', vibe:'', consistencyPlan:'B'});
  renderCharacters();
};

async function extractElements(){
  const tok = ++state.genToken;
  state.storyText = document.getElementById('storyInput').value.trim();
  if (!state.storyText){ setMsg('step1Msg','请先粘贴故事文本','warn'); return; }
  setBusy('step1Msg', '正在识别元素…', extractElements);
  try {
    const sys = `你是短视频元素识别助手。根据用户提供的故事文本，提取里面所有需要在视频里被稳定呈现的关键元素：人类角色、动物角色、关键道具、关键场景/地点都算元素。
严格只输出一个JSON数组，不要任何解释文字、不要代码块标记。每个元素格式：
{"name":"元素名称","type":"人类|动物|道具|场景","visual":"外貌/材质/环境等视觉细节，逗号分隔","vibe":"性格、习性或氛围关键词，非必需"}`;
    const result = await callOllama(sys, state.storyText, true);
    if (tok !== state.genToken) return;   // 已被“重试”取代，丢弃旧结果
    state.characters = (Array.isArray(result) ? result : []).map(c => ({...c, consistencyPlan: c.consistencyPlan || 'B'}));
    renderCharacters();
    document.getElementById('projectNameField').style.display = 'block';   // 元素出来后显示项目名字段
    if (!state.characters.length) setMsg('step1Msg', '没有识别到元素，可以手动添加，或检查故事文本', 'warn');
    autoNameProject();   // 后台顺便让 AI 拟个项目名（失败/超时都不影响主流程）
  } catch(e){
    if (tok !== state.genToken) return;
    setError('step1Msg', 'AI 整理元素失败：' + e.message, extractElements);
  }
}
document.getElementById('extractBtn').onclick = extractElements;

// 让 AI 根据故事拟一个项目名，填进“项目名称”框（用户没填时才写入，可再改）
async function autoNameProject(){
  const input = document.getElementById('projectNameInput');
  if (!input || input.value.trim()) return;
  try {
    const sys = `根据故事内容起一个简短的中文项目名，用作文件夹名：不超过12个汉字，不含标点、书名号、引号、空格。严格只输出JSON：{"projectName":"名字"}`;
    const res = await callOllama(sys, state.storyText, true);
    let pn = (res && res.projectName) ? String(res.projectName) : '';
    pn = pn.replace(/[《》"'\\/:*?<>|\s]/g, '').slice(0, 12);
    if (pn && !input.value.trim()){ input.value = pn; state.projectName = pn; }
  } catch(e){ /* 拟名失败不影响主流程，用户可自己填 */ }
}

document.getElementById('confirmCharsBtn').onclick = async () => {
  if (!state.characters.length){ setMsg('step1Msg','请先至少保留一个元素再确认','warn'); return; }
  const pnEl = document.getElementById('projectNameInput');
  state.projectName = (pnEl && pnEl.value.trim()) || '未命名项目';
  state.storyText = document.getElementById('storyInput').value.trim() || state.storyText;

  // 冻结“已确认元素”文本，第二步 AI 设计将据此进行
  state.confirmedElementsText = buildElementsText();

  // 新建 日期+项目名+序号 目录，并写入 01_元素.txt
  const res = await bridgeCall('saveElements', {
    projectName: state.projectName,
    elementsText: state.confirmedElementsText
  });
  if (res && res.ok){
    state.projectDir = res.dir;
    setMsg('step1Msg', `已确认元素，元素文件已保存：${res.path}`, 'info');
  } else {
    state.projectDir = '';   // 浏览器直开模式：无宿主，退回下载
    downloadPlain(state.confirmedElementsText, `${state.projectName}-元素.txt`);
    setMsg('step1Msg', '已确认元素（未连接桌面宿主，已改为浏览器下载元素文件）', 'info');
  }

  goToStep(2);
  runDesignDraft();
};

// ---------- STEP 2: design panel + shot outline (auto-generated on entry) ----------
async function runDesignDraft(){
  const tok = ++state.genToken;
  setBusy('step2Msg', '正在根据故事和元素生成设计面板默认值与镜头大纲…', runDesignDraft);
  try {
    const sys = `你是短视频创意顾问兼分镜师。根据故事内容和已确认的元素列表（人物/动物/道具/场景），为一个即将制作的短视频草拟创作简报默认值，并给出一个简化的镜头大纲预览。
严格只输出一个JSON对象，不要解释文字、不要代码块标记，格式：
{"audience":"目标受众描述，一句话","mustInclude":["必须出现的关键画面1","必须出现的关键画面2"],"language":"中文","aspectRatio":"16:9","artStyle":"写实","duration":30,"shotCount":4,
"shotOutline":[{"duration":8,"summary":"一句话描述这个镜头大致要拍什么，不超过30字"}]}
shotOutline 数组长度要等于 shotCount，各镜头 duration 总和要接近 duration 字段，每个镜头 duration 在 2-15 秒之间。
aspectRatio 必须是 16:9、1:1、9:16 之一。artStyle 从：电影感、商业、未来感、复古、动漫、3D、插画、写实、实验性 中选一个。`;
    const user = `故事：\n${state.storyText}\n\n已确认元素（来自第一步确认后保存的元素文件，务必据此设计）：\n${state.confirmedElementsText || JSON.stringify(state.characters)}`;
    const d = await callOllama(sys, user, true);
    if (tok !== state.genToken) return;
    document.getElementById('designAudience').value = d.audience || '';
    document.getElementById('designMustInclude').value = (d.mustInclude||[]).join('\n');
    document.getElementById('designLanguage').value = d.language || '中文';
    document.getElementById('designAspectRatio').value = d.aspectRatio || '16:9';
    document.getElementById('designArtStyle').value = d.artStyle || '写实';
    document.getElementById('designDuration').value = d.duration || 30;
    document.getElementById('designShotCount').value = d.shotCount || Math.max(1, Math.round((d.duration||30)/8));
    state.design.shotOutline = (Array.isArray(d.shotOutline) && d.shotOutline.length)
      ? d.shotOutline.map(s => ({duration: s.duration || 8, summary: s.summary || ''}))
      : [];
    renderShotOutline();
    setMsg('step2Msg', '已生成默认值与镜头大纲，可直接修改', 'info');
  } catch(e){
    if (tok !== state.genToken) return;
    setError('step2Msg', '设计面板生成失败：' + e.message, runDesignDraft);
  }
}

function genId(){ return 'o' + Date.now().toString(36) + Math.random().toString(36).slice(2,8); }

function renderShotOutline(){
  const container = document.getElementById('shotOutlineList');
  container.innerHTML = '';
  state.design.shotOutline.forEach((s, idx) => {
    if (!s.id) s.id = genId();
    const row = document.createElement('div');
    row.className = 'outline-row';
    row.draggable = true;
    row.dataset.id = s.id;
    row.innerHTML = `
      <span class="drag-handle" title="拖拽调整顺序">⠿</span>
      <span class="shot-no">#${idx+1}</span>
      <input type="number" min="2" max="15" data-of="duration" data-oidx="${idx}" value="${s.duration}">
      <input type="text" data-of="summary" data-oidx="${idx}" value="${escapeHtml(s.summary||'')}" placeholder="这个镜头大致要拍什么">
      <button class="remove-btn" data-oidx="${idx}">删除</button>
    `;
    row.addEventListener('mousedown', e => {
      row.draggable = !(e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON');
    });
    row.addEventListener('dragstart', () => row.classList.add('dragging'));
    row.addEventListener('dragend', () => { row.classList.remove('dragging'); syncOutlineOrderFromDOM(); });
    container.appendChild(row);
  });
  container.querySelectorAll('[data-of]').forEach(el => {
    el.addEventListener('input', e => {
      const idx = +e.target.dataset.oidx, f = e.target.dataset.of;
      state.design.shotOutline[idx][f] = f === 'duration' ? (+e.target.value || 8) : e.target.value;
      updateOutlineTotal();
    });
  });
  container.querySelectorAll('.remove-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      state.design.shotOutline.splice(+e.target.dataset.oidx, 1);
      renderShotOutline();
    });
  });
  updateOutlineTotal();
}

function getDragAfterElement(container, y){
  const rows = [...container.querySelectorAll('.outline-row:not(.dragging)')];
  return rows.reduce((closest, row) => {
    const box = row.getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0 && offset > closest.offset) return {offset, element: row};
    return closest;
  }, {offset: -Infinity}).element;
}

function syncOutlineOrderFromDOM(){
  const container = document.getElementById('shotOutlineList');
  const ids = [...container.querySelectorAll('.outline-row')].map(r => r.dataset.id);
  const byId = {};
  state.design.shotOutline.forEach(s => { byId[s.id] = s; });
  state.design.shotOutline = ids.map(id => byId[id]).filter(Boolean);
  renderShotOutline();
}

(function setupOutlineDragDrop(){
  const container = document.getElementById('shotOutlineList');
  container.addEventListener('dragover', e => {
    e.preventDefault();
    const dragging = container.querySelector('.dragging');
    if (!dragging) return;
    const afterEl = getDragAfterElement(container, e.clientY);
    if (afterEl == null) container.appendChild(dragging);
    else container.insertBefore(dragging, afterEl);
  });
})();
function updateOutlineTotal(){
  const total = state.design.shotOutline.reduce((a,s)=>a+(+s.duration||0),0);
  const target = +document.getElementById('designDuration').value || 0;
  document.getElementById('outlineTotal').textContent = `共 ${state.design.shotOutline.length} 个镜头，合计 ${total} 秒（目标时长 ${target} 秒）`;
}
document.getElementById('designDuration').addEventListener('input', updateOutlineTotal);
document.getElementById('addOutlineBtn').onclick = () => {
  state.design.shotOutline.push({duration:8, summary:''});
  renderShotOutline();
};

function exportProgress(filename){
  readDesignFromForm();
  state.storyText = document.getElementById('storyInput').value.trim() || state.storyText;
  const data = { version:1, storyText: state.storyText, characters: state.characters, design: state.design };
  const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename || '导演Agent进度.json';
  a.click();
}

function importProgress(file){
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      state.storyText = data.storyText || '';
      state.characters = Array.isArray(data.characters) ? data.characters : [];
      state.design = Object.assign(
        {audience:'', mustInclude:[], language:'中文', aspectRatio:'16:9', artStyle:'写实', duration:30, shotCount:4, shotOutline:[]},
        data.design || {}
      );
      document.getElementById('storyInput').value = state.storyText;
      renderCharacters();
      document.getElementById('designAudience').value = state.design.audience || '';
      document.getElementById('designMustInclude').value = (state.design.mustInclude||[]).join('\n');
      document.getElementById('designLanguage').value = state.design.language || '中文';
      document.getElementById('designAspectRatio').value = state.design.aspectRatio || '16:9';
      document.getElementById('designArtStyle').value = state.design.artStyle || '写实';
      document.getElementById('designDuration').value = state.design.duration || 30;
      document.getElementById('designShotCount').value = state.design.shotCount || 4;
      renderShotOutline();
      setMsg('outlineMsg', '已导入进度', 'info');
    } catch(e){
      setMsg('outlineMsg', '导入失败，文件不是有效的进度文件', 'err');
    }
  };
  reader.readAsText(file, 'utf-8');
}
document.getElementById('exportProgressBtn').onclick = () => exportProgress('导演Agent设计001.json');
document.getElementById('importProgressBtn').onclick = () => document.getElementById('importFileInput').click();
document.getElementById('exportProgressBtn1').onclick = () => exportProgress('导演Agent元素001.json');
document.getElementById('importProgressBtn1').onclick = () => document.getElementById('importFileInput').click();
document.getElementById('importFileInput').addEventListener('change', e => {
  if (e.target.files[0]) importProgress(e.target.files[0]);
  e.target.value = '';
});

async function regenerateOutline(){
  const tok = ++state.genToken;
  state.design.duration = +document.getElementById('designDuration').value || 30;
  state.design.shotCount = +document.getElementById('designShotCount').value || 4;
  setBusy('outlineMsg', '正在按当前时长和镜头数重新生成镜头大纲…', regenerateOutline);
  try {
    const sys = `你是短视频分镜师。根据故事、已确认元素列表，以及给定的总时长和镜头数，草拟一个简化镜头大纲预览。
严格只输出一个JSON数组，不要解释文字、不要代码块标记，数组长度必须正好等于给定的镜头数，格式：
[{"duration":8,"summary":"一句话描述这个镜头大致要拍什么，不超过30字"}]
各镜头 duration 总和要接近给定总时长，每个镜头 duration 在 2-15 秒之间。`;
    const user = `故事：\n${state.storyText}\n\n元素列表：\n${JSON.stringify(state.characters)}\n\n总时长：${state.design.duration}秒\n\n镜头数：${state.design.shotCount}`;
    const outline = await callOllama(sys, user, true);
    if (tok !== state.genToken) return;
    state.design.shotOutline = (Array.isArray(outline) ? outline : []).map(s => ({duration: s.duration || 8, summary: s.summary || ''}));
    renderShotOutline();
    setMsg('outlineMsg', '镜头大纲已按新设置重新生成，可直接修改', 'info');
  } catch(e){
    if (tok !== state.genToken) return;
    setError('outlineMsg', '镜头大纲生成失败：' + e.message, regenerateOutline);
  }
}
document.getElementById('regenOutlineBtn').onclick = regenerateOutline;

function readDesignFromForm(){
  state.design.audience = document.getElementById('designAudience').value.trim();
  state.design.mustInclude = document.getElementById('designMustInclude').value.split('\n').map(s=>s.trim()).filter(Boolean);
  state.design.language = document.getElementById('designLanguage').value;
  state.design.aspectRatio = document.getElementById('designAspectRatio').value;
  state.design.artStyle = document.getElementById('designArtStyle').value;
  // 关键修正：一旦有镜头大纲，最终镜头数与最终总时长都以“用户实际编辑好的镜头大纲”为准，
  // 而不是上方那个可能没同步的 designDuration 输入框（这正是第三步会变回 30 秒的根因）。
  const outline = state.design.shotOutline || [];
  if (outline.length){
    const outlineTotal = outline.reduce((a,s)=>a+(+s.duration||0),0);
    state.design.shotCount = outline.length;
    state.design.duration  = outlineTotal;
    // 把上方两个框也同步成最终值，避免界面显示与最终版不一致
    document.getElementById('designShotCount').value = outline.length;
    document.getElementById('designDuration').value  = outlineTotal;
  } else {
    state.design.duration  = +document.getElementById('designDuration').value || 30;
    state.design.shotCount = +document.getElementById('designShotCount').value || 4;
  }
}

document.getElementById('confirmDesignBtn').onclick = async () => {
  readDesignFromForm();

  // 冻结“已确认设计面板”文本，第三步生成将据此进行
  state.confirmedDesignText = buildDesignText();

  const res = await bridgeCall('saveDesign', {
    dir: state.projectDir || '',
    projectName: state.projectName || '未命名项目',
    designText: state.confirmedDesignText
  });
  if (res && res.ok){
    if (res.dir) state.projectDir = res.dir;
    setMsg('step2Msg', `已确认设计面板，设计文件已保存：${res.path}`, 'info');
  } else {
    downloadPlain(state.confirmedDesignText, `${state.projectName||'项目'}-设计面板.txt`);
    setMsg('step2Msg', '已确认设计面板（未连接桌面宿主，已改为浏览器下载设计文件）', 'info');
  }

  enterStep3();
};

// ---------- STEP 3: A → B → C 依次生成；A/B 完成后 20s 自动进入下一步 ----------
// 倒计时句柄：切步 / 重试 / 手动确认时都要清掉，避免重复触发
let _countdownTimer = null;
let _countdownInterval = null;

function clearCountdown(){
  if (_countdownTimer){ clearTimeout(_countdownTimer); _countdownTimer = null; }
  if (_countdownInterval){ clearInterval(_countdownInterval); _countdownInterval = null; }
}

/** 页面滚到最底部（新内容生成后调用，方便看到最新块） */
function scrollPageBottom(){
  requestAnimationFrame(() => {
    const se = document.scrollingElement || document.documentElement;
    const top = Math.max(
      se ? se.scrollHeight : 0,
      document.body ? document.body.scrollHeight : 0,
      document.documentElement ? document.documentElement.scrollHeight : 0
    );
    window.scrollTo({ top: top, behavior: 'smooth' });
  });
}

/**
 * 按钮 20 秒倒计时后自动执行 onDone；期间也可手动点按钮立即执行。
 * 防重入：onDone 只会真正跑一次（手动点或倒计时到点，先到先得）。
 */
function startCountdown(btnId, baseLabel, seconds, onDone){
  clearCountdown();
  const btn = document.getElementById(btnId);
  if (!btn){ onDone(); return; }
  let left = seconds;
  let fired = false;
  const fire = () => {
    if (fired) return;
    fired = true;
    clearCountdown();
    onDone();
  };
  const paint = () => {
    const b = document.getElementById(btnId);
    if (b && !b.disabled) b.textContent = baseLabel + '（' + left + 's 后自动）';
  };
  paint();
  _countdownInterval = setInterval(() => {
    left -= 1;
    if (left <= 0){
      clearInterval(_countdownInterval);
      _countdownInterval = null;
      return;
    }
    paint();
  }, 1000);
  _countdownTimer = setTimeout(fire, seconds * 1000);
  btn.onclick = fire;
  btn.disabled = false;
}

function setFinishMsg(text, type){
  const el = document.getElementById('finishMsg');
  if (!el) return;
  if (!text){
    el.style.display = 'none';
    el.className = 'msg';
    el.textContent = '';
    return;
  }
  el.style.display = 'block';
  el.className = type ? 'msg ' + type : 'msg';
  el.textContent = text;
}

function enterStep3(){
  clearCountdown();
  goToStep(3);
  document.getElementById('blockB').style.display = 'none';
  document.getElementById('blockC').style.display = 'none';
  setMsg('msgA',''); setMsg('msgB',''); setMsg('msgC','');
  setFinishMsg('');
  state.textA = ''; state.textB = ''; state.textC = '';
  state._confirmingA = false;
  state._confirmingB = false;
  generateA();
}

// 读取某个 pane 里文本框的当前内容（用户可能编辑过）
function readPaneText(id){
  const ta = document.querySelector('#' + id + ' textarea');
  return ta ? ta.value : '';
}

// 通用：把一份纯文本产出渲染成“可编辑文本框 + 复制 + 下一步/重新生成按钮”
// opts.height：固定高度（px）；opts.minHeight：最小高度（默认 240）
// opts.copyLabel：左侧复制按钮文案（如「复制A内容」）
function renderTextPane(paneId, text, opts){
  opts = opts || {};
  const pane = document.getElementById(paneId);
  const copyId = paneId + 'CopyBtn';
  let html = '';
  if (opts.hint) html += `<p class="hint" style="margin:0 0 8px;">${escapeHtml(opts.hint)}</p>`;
  const hStyle = opts.height
    ? `height:${opts.height}px; min-height:${opts.height}px;`
    : `min-height:${opts.minHeight||240}px;`;
  html += `<textarea style="width:100%; ${hStyle}">${escapeHtml(text)}</textarea>`;
  const copyLabel = opts.copyLabel || '复制';
  html += `<div class="actions"><button class="secondary copy-pane-btn" id="${copyId}">${escapeHtml(copyLabel)}</button>`;
  if (opts.nextLabel) html += `<button id="${opts.nextId}" style="margin-left:auto;">${escapeHtml(opts.nextLabel)}</button>`;
  html += `</div>`;
  pane.innerHTML = html;
  const ta = pane.querySelector('textarea');
  const copyBtn = document.getElementById(copyId);
  copyBtn.dataset.label = copyBtn.textContent;
  copyBtn.onclick = async () => { const ok = await copyRaw(ta.value); flashBtn(copyBtn, ok); };  // 复制文本框实时内容
  if (opts.nextId && opts.onNext){
    const nb = document.getElementById(opts.nextId);
    if (nb) nb.onclick = opts.onNext;
  }
}

// ===== A：故事简讯 + 镜头提示词 =====
async function generateA(){
  clearCountdown();
  const tok = ++state.genToken;
  if (state.abcStage >= 2) setBtn('confirmABtn', 'A 内容生成中…', true);
  try {
    setBusy('msgA', '正在生成 A · 故事简讯 + 镜头提示词…', state.abcStage >= 2 ? regenerateA : generateA);
    scrollPageBottom();
    const outline = state.design.shotOutline || [];
    const n = outline.length;
    const total = outline.reduce((a,s)=>a+(+s.duration||0),0);
    const durList = outline.map((s,i)=>`第${i+1}镜头=${s.duration}秒`).join('，');
    const sys = `你是分镜脚本师。根据故事、已确认元素、已确认设计面板和已确认镜头大纲，输出“故事简讯 + 镜头清单”。
硬性要求：
1. 故事简讯 brief 不超过100个汉字；
2. 镜头数量必须正好等于 ${n}；每个镜头 duration 必须与给定时长完全一致（${durList}）；
3. 每个镜头 content 是这一镜头“要拍什么”的客观描述，不超过100个汉字，只写画面内容与动作，不要写风格、运镜、光影、美化或形容词堆砌；
4. dialogue 只在故事中该镜头确有台词时填原文，没有就留空。
严格只输出一个JSON对象，不要解释、不要代码块标记，格式：
{"brief":"...","shots":[{"duration":3,"content":"...","dialogue":""}]}`;
    const user = `故事：\n${state.storyText}\n\n已确认元素：\n${state.confirmedElementsText||JSON.stringify(state.characters)}\n\n已确认设计面板：\n${state.confirmedDesignText||''}\n\n镜头大纲（权威，数量=${n}，总时长=${total}秒）：\n${JSON.stringify(outline)}`;
    const a = await callOllama(sys, user, true);
    if (tok !== state.genToken) return;
    const raw = Array.isArray(a.shots) ? a.shots : [];
    // 兜底：数量与时长一律以镜头大纲为准
    const shots = outline.map((o, i) => ({
      duration: o.duration || (raw[i] && raw[i].duration) || 0,
      content: (raw[i] && raw[i].content) || o.summary || '',
      dialogue: (raw[i] && raw[i].dialogue) || ''
    }));
    state.shotScript = { brief: a.brief || '', shots };
    // 留一份 storyboard.shots，供 C 的故事板与镜头数计算参考
    state.storyboard = { shots: shots.map((s,i)=>({shotNumber:i+1, duration:s.duration, content:s.content, dialogue:s.dialogue})) };
    state.textA = formatA(state.shotScript);
    state._confirmingA = false;
    const isRegen = state.abcStage >= 2;   // B 已走过 → 本次是「重新生成 A」
    state.abcStage = Math.max(state.abcStage || 0, 1);
    renderOutputA();
    if (isRegen){
      await saveOneOutput('a');
      setMsg('msgA', 'A 已重新生成并已自动保存', 'info');
      // 若打断了 B→C 倒计时，把 B 区右侧按钮文案复位
      if (state.abcStage < 3 && document.getElementById('confirmBBtn')){
        setBtn('confirmBBtn', '确认 B，生成 C →', false, confirmB);
      }
      scrollPageBottom();
    } else {
      setMsg('msgA', 'A 已生成，可直接在文本框里编辑；20 秒后自动生成 B（也可手动确认）', 'info');
      scrollPageBottom();
      startCountdown('confirmABtn', '确认 A，生成 B →', 20, confirmA);
    }
  } catch(e){
    if (tok !== state.genToken) return;
    setError('msgA', 'A 生成失败：' + e.message, state.abcStage >= 2 ? regenerateA : generateA);
    if (state.abcStage >= 2) setBtn('confirmABtn', '↻ 重新生成 A', false, regenerateA);
    scrollPageBottom();
  }
}
function renderOutputA(){
  const regen = state.abcStage >= 2;
  renderTextPane('paneA', state.textA, {
    hint: '故事简讯（≤100字）+ 逐镜头（时长/内容/台词）。纯文本，可整理后复制。',
    minHeight: 260,
    copyLabel: '复制A内容',
    nextId: 'confirmABtn',
    nextLabel: regen ? '↻ 重新生成 A' : '确认 A，生成 B →',
    onNext: regen ? regenerateA : confirmA
  });
}
function confirmA(){
  clearCountdown();
  if (state._confirmingA) return;   // 防倒计时与手动点击重复触发
  state._confirmingA = true;
  state.textA = readPaneText('paneA');       // 采用用户编辑后的文本，B/C 会据此生成
  const blockB = document.getElementById('blockB');
  blockB.style.display = 'block';
  scrollPageBottom();
  generateB();
}
// 重新生成本区 A（不推进到 B），完成后自动保存 03_A_….txt
function regenerateA(){
  clearCountdown();
  generateA();
}

// ===== B：角色提示词（多角度模型参考，纯文本一整段）=====
async function generateB(){
  clearCountdown();
  const tok = ++state.genToken;
  // 首次从 A 确认过来时，A 右侧按钮显示“生成中”；重新生成 B 时 B 区按钮显示“生成中”
  if (state.abcStage >= 2){
    setBtn('confirmBBtn', 'B 内容生成中…', true);
  } else {
    setBtn('confirmABtn', 'B 内容生成中…', true);
  }
  try {
    setBusy('msgB', '正在生成 B · 角色提示词（多角度模型）…', generateB);
    scrollPageBottom();
    const sys = `你是角色设定师。为每个需要保持一致性的角色/关键道具，写一段“多角度模型参考”提示词。
每个对象包含：
- modelSheet：同一对象从多角度描述——正面、背面、侧面、特写、放松姿态各自要点，串成一段；
- wardrobe：服装与配饰参考；
- consistency：强调身份一致性的锁定描述，并说明允许在特定场景中的细微变化。
文字客观、可直接用于文生图定妆参考，不要空洞形容词堆砌。
严格只输出一个JSON数组，不要解释、不要代码块标记，格式：
[{"name":"","type":"人类|动物|道具|场景","modelSheet":"正面…；背面…；侧面…；特写…；放松姿态…","wardrobe":"","consistency":""}]`;
    const user = `已确认元素：\n${state.confirmedElementsText||JSON.stringify(state.characters)}\n\n已确认镜头脚本（A，供参考出场情况）：\n${state.textA||''}`;
    const arr = await callOllama(sys, user, true);
    if (tok !== state.genToken) return;
    state.characterSheets = Array.isArray(arr) ? arr : [];
    state.textB = formatB(state.characterSheets);
    state._confirmingA = false;
    state._confirmingB = false;
    const isRegen = state.abcStage >= 3;   // C 已走过 → 本次是「重新生成 B」
    state.abcStage = Math.max(state.abcStage || 0, 2);
    renderOutputB();
    // A 区右侧固定为「重新生成 A」（不再误标成重新生成 B）
    setBtn('confirmABtn', '↻ 重新生成 A', false, regenerateA);
    if (isRegen){
      await saveOneOutput('b');
      setMsg('msgB', 'B 已重新生成并已自动保存', 'info');
      scrollPageBottom();
    } else {
      setMsg('msgB', 'B 已生成，可直接编辑；20 秒后自动生成 C（也可手动确认）', 'info');
      scrollPageBottom();
      startCountdown('confirmBBtn', '确认 B，生成 C →', 20, confirmB);
    }
  } catch(e){
    if (tok !== state.genToken) return;
    state._confirmingA = false;   // 失败后允许重新点
    setError('msgB', 'B 生成失败：' + e.message, state.abcStage >= 3 ? regenerateB : generateB);
    if (state.abcStage >= 2){
      setBtn('confirmABtn', '↻ 重新生成 A', false, regenerateA);
    } else {
      setBtn('confirmABtn', '确认 A，生成 B →', false, confirmA);
    }
    if (state.abcStage >= 3){
      setBtn('confirmBBtn', '↻ 重新生成 B', false, regenerateB);
    } else if (document.getElementById('confirmBBtn')){
      setBtn('confirmBBtn', '确认 B，生成 C →', false, confirmB);
    }
    scrollPageBottom();
  }
}
function renderOutputB(){
  // B 内容较长：文本框固定 800px 高度，内部滚动查看
  const regen = state.abcStage >= 3;
  renderTextPane('paneB', state.textB, {
    hint: '每个角色一段：多角度模型（正/背/侧/特写/放松）+ 服装配饰 + 身份一致性。纯文本，可整体复制。',
    height: 800,
    copyLabel: '复制B内容',
    nextId: 'confirmBBtn',
    nextLabel: regen ? '↻ 重新生成 B' : '确认 B，生成 C →',
    onNext: regen ? regenerateB : confirmB
  });
}
function confirmB(){
  clearCountdown();
  if (state._confirmingB) return;
  state._confirmingB = true;
  state.textB = readPaneText('paneB');
  const blockC = document.getElementById('blockC');
  blockC.style.display = 'block';
  scrollPageBottom();
  generateC();
}
// 重新生成本区 B（不推进到 C），完成后自动保存 04_B_….txt
function regenerateB(){
  clearCountdown();
  generateB();
}

// ===== C：电影制作板（简洁纯文本，整份≤1000汉字，按用户镜头数）=====
async function generateC(){
  clearCountdown();
  const tok = ++state.genToken;
  const isRegen = state.abcStage >= 3;
  if (isRegen){
    setBtn('regenCBtn', 'C 内容生成中…', true);
  } else {
    setBtn('confirmBBtn', 'C 内容生成中…', true);   // 刚点过的按钮变成“生成中”
  }
  try {
    setBusy('msgC', '正在生成 C · 电影制作板…', generateC);
    scrollPageBottom();
    const n = _boardShotCount();
    const sys = `你是导演预制作总监。产出一份简洁的“电影制作板/视觉规划表”，比例${state.design.aspectRatio}。
硬性要求：整份中文控制在1000个汉字以内，各节从简、一两句话即可；故事板帧数必须正好等于 ${n}；各场景要有差异、避免雷同；不要输出角色卡（角色在 B 里）。
严格只输出一个JSON对象，不要解释、不要代码块标记，所有取值用中文，格式：
{"concept":"一句话概念",
"creativeDirection":{"palette":"统一调色板","environmentBackground":"环境背景基调","overallConstraints":"整体限制"},
"environmentDesign":{"location":"户外地点","dramaticFeatures":"戏剧性特征","topDownMap":"俯视路径+机位与拍摄类型（简述）","cameraPositions":[{"tag":"C1","shotType":"广角/中景/特写等"}]},
"storyboardFrames":[{"frame":1,"shotSize":"广角/中景/特写/微距","movement":"静态/跟踪/手持等","action":"动作简述","moodProgression":"情绪"}],
"lightingMood":[{"timeOfDay":"时段","lightQuality":"光质","atmosphere":"氛围","texture":"纹理"}],
"moodKeywords":["关键词"],
"audioTone":{"ambient":"环境声","musicStyle":"音乐风格","soundscape":"声音氛围"},
"cinematographyNotes":{"lensCharacter":"镜头特性","motionStyle":"运动风格","postProcessing":"后期","visualPhilosophy":"视觉哲学"}}`;
    const user = `故事：\n${state.storyText}\n\n已确认设计面板：\n${state.confirmedDesignText||''}\n\n已确认镜头脚本（A）：\n${state.textA||''}\n\n镜头数量：${n}\n画幅：${state.design.aspectRatio}\n艺术风格：${state.design.artStyle}`;
    state.board = await callOllama(sys, user, true);
    if (tok !== state.genToken) return;
    state.textC = formatC(state.board);
    state._confirmingB = false;
    state.abcStage = 3;
    renderOutputC();
    // B 区右侧固定为「重新生成 B」（不再误标成重新生成 C）
    setBtn('confirmBBtn', '↻ 重新生成 B', false, regenerateB);
    scrollPageBottom();
    if (isRegen){
      await saveOneOutput('c');
      setMsg('msgC', 'C 已重新生成并已自动保存', 'info');
    } else {
      setMsg('msgC', 'C 已生成，正在保存三份产出到文本文件…', 'info');
      await saveOutputs();
    }
  } catch(e){
    if (tok !== state.genToken) return;
    state._confirmingB = false;
    setError('msgC', 'C 生成失败：' + e.message, state.abcStage >= 3 ? regenerateC : generateC);
    if (state.abcStage >= 3){
      setBtn('confirmBBtn', '↻ 重新生成 B', false, regenerateB);
      setBtn('regenCBtn', '↻ 重新生成 C', false, regenerateC);
    } else {
      setBtn('confirmBBtn', '确认 B，生成 C →', false, confirmB);
    }
    scrollPageBottom();
  }
}
function renderOutputC(){
  renderTextPane('paneC', state.textC, {
    hint: '简洁版电影制作板，纯文本（整份≤1000字）。可点「重新生成 C」重跑并自动保存。',
    minHeight: 260,
    copyLabel: '复制C内容',
    nextId: 'regenCBtn', nextLabel: '↻ 重新生成 C', onNext: regenerateC
  });
}
// 重新生成本区 C，完成后自动保存 05_C_….txt
function regenerateC(){
  clearCountdown();
  generateC();
}

// ===== 保存单份产出（重新生成 A/B/C 后调用）=====
async function saveOneOutput(which){
  const key = String(which || '').toLowerCase();
  const paneMap = { a: 'paneA', b: 'paneB', c: 'paneC' };
  const fileMap = {
    a: '03_A_故事简讯与镜头提示词.txt',
    b: '04_B_角色提示词.txt',
    c: '05_C_电影制作板.txt'
  };
  if (!paneMap[key]) return;
  const text = readPaneText(paneMap[key]) || state['text' + key.toUpperCase()] || '';
  if (key === 'a') state.textA = text;
  if (key === 'b') state.textB = text;
  if (key === 'c') state.textC = text;
  const res = await bridgeCall('saveOneOutput', {
    dir: state.projectDir || '',
    projectName: state.projectName || '未命名项目',
    which: key,
    text: text
  });
  const label = key.toUpperCase();
  if (res && res.ok){
    if (res.dir) state.projectDir = res.dir;
    setFinishMsg(label + ' 已保存到：' + (res.path || ''), 'info');
  } else {
    downloadPlain(text, `${state.projectName||'项目'}-${fileMap[key]}`);
    setFinishMsg(label + ' 已保存（未连接桌面宿主，改为浏览器下载）', 'info');
  }
}

// ===== 保存三份产出到项目目录 =====
async function saveOutputs(){
  state.textA = readPaneText('paneA') || state.textA;
  state.textB = readPaneText('paneB') || state.textB;
  state.textC = readPaneText('paneC') || state.textC;
  const res = await bridgeCall('saveOutputs', {
    dir: state.projectDir || '',
    projectName: state.projectName || '未命名项目',
    a: state.textA, b: state.textB, c: state.textC
  });
  // 完成提示固定写到第三步页面最下方的 finishMsg，不再挤在 C 标题下面
  if (res && res.ok){
    if (res.dir) state.projectDir = res.dir;
    setMsg('msgC', 'C 已生成并已自动保存', 'info');
    setFinishMsg('三份产出已保存到：' + (res.paths || []).join('  |  '), 'info');
  } else {
    downloadPlain(state.textA, `${state.projectName||'项目'}-A_故事简讯与镜头提示词.txt`);
    downloadPlain(state.textB, `${state.projectName||'项目'}-B_角色提示词.txt`);
    downloadPlain(state.textC, `${state.projectName||'项目'}-C_电影制作板.txt`);
    setMsg('msgC', 'C 已生成并已自动保存', 'info');
    setFinishMsg('三份产出已保存（未连接桌面宿主，改为浏览器下载 3 个文件）', 'info');
  }
  scrollPageBottom();
}

// ---------- step navigation ----------
function goToStep(n){
  [1,2,3].forEach(i => {
    document.getElementById('step'+i).classList.toggle('show', i===n);
    const p = document.getElementById('prog'+i);
    p.classList.toggle('active', i===n);
    p.classList.toggle('done', i<n);
  });
  window.scrollTo({top:0, behavior:'smooth'});
}
</script>
</body>
</html>

'''
