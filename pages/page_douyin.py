# pages/page_douyin.py
# 抖音无水印下载器 —— 嵌入桌面助手 PyQt5 版
# 布局：合并卡片「解析与下载」(Cookie+保存位置 / 链接 / 一键按钮+进度+状态)
#       → 媒体卡片区(全选/全不选/选中下载) → 运行日志
# v9.9：一键「粘贴并解析」= 读剪贴板 → 解析 → 自动下载到保存位置
#       移除「解析」「开始下载」「打开目录」三个按钮；「？」→「安装」
# v8 移植：五条解析线路 / 图文帖HTML解析 / 内部重试 / 并发下载 / 文件校验 / 文件名加日期
# v9.10 修复：图文帖(aweme_type=2/68) 的 video 节点只是 cover 容器，其中的
#       playwm 占位地址并无真实视频流（请求返回 200 + 空 body）。旧版无条件把它
#       当成「视频（无水印 MP4）」产出，导致：① 媒体项比网页多一条；② 该项下载
#       必然 0B 失败。现按 aweme_type / images / duration 判定图集，占位项不再产出；
#       同时修正 aweme_type=2 的类型识别、Referer 拼接与 0B 错误文案。

import warnings, urllib3
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

import os, re, sys, json, time, threading, uuid, gzip as gzip_mod
import http.cookiejar, ssl, datetime
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui  import QFont, QColor, QPixmap, QImage, QTextCursor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QFileDialog, QCheckBox, QFrame,
    QScrollArea, QGridLayout, QProgressBar, QSizePolicy, QApplication,
    QGroupBox,
)

try:
    import requests as req_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from styles.style_all import (
    theme,
    fmt,
    tk,
    PAGE_QSS,
    GB_STYLE as _GB_STYLE,
    DIVIDER_QSS,
    install_card_title,
    restyle_card_title,
    restyle_card_frame,
    make_card,
    apply_folder_path_edit,
    restyle_folder_path_edit,
    CARD_TOP_GAP,
    CARD_LEFT_GAP,
    CARD_RIGHT_GAP,
    CARD_BOTTOM_GAP,
)


class _ElideLabel(QLabel):
    """按可用宽度自动省略的标签（右端加省略号，保留开头）。

    用于 Cookie 状态提示：状态文字过长时旧写法会把它所在的列（Cookie 列，占 60%）
    最小宽度顶爆，整列越过与「保存位置」列之间的分界、连同下方路径行一起溢出。
    这里让标签 sizeHint 宽度不再强撑父布局（横向 Ignored），拿到多少宽度就显示多少、
    放不下就省略，从而彻底不越界；完整文字保留在 tooltip 里。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._full = text or ""
        # 横向 Ignored：不把自身文字宽度当成布局最小宽度上报，杜绝撑爆列宽
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setFullText(self, text: str):
        self._full = text or ""
        self.setToolTip(self._full)
        self._apply_elide()

    def _apply_elide(self):
        fm = self.fontMetrics()
        avail = max(0, self.width() - 2)
        super().setText(fm.elidedText(self._full, Qt.ElideRight, avail))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_elide()


# ── 网络层 ────────────────────────────────────────────────────────────────────
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/17.0 Mobile/15E148 Safari/604.1")
UA_ANDROID = ("com.ss.android.ugc.aweme/210202 "
              "(Linux; U; Android 10; zh_CN; Pixel 4; "
              "Build/QQ3A.200805.001; Cronet/TTNetVersion:b4d74d15)")

RETRY_WAIT = 0.35       # 同线路重试等待秒数
MIN_FILE_BYTES = 10 * 1024   # 文件最小有效大小 10 KB
DEBUG_DUMP_ITEM = True  # 解析成功后把原始 item JSON 落盘，便于排查字段变动


def dump_item_debug(item: dict, aweme_id: str = "") -> str:
    """把解析到的原始 item 存成 JSON，返回文件路径（失败返回 ""）。
    抖音字段名时常变动，出问题时先看这个文件比猜键名快得多。"""
    if not DEBUG_DUMP_ITEM:
        return ""
    try:
        import tempfile
        d = os.path.join(tempfile.gettempdir(), "douyin_debug")
        os.makedirs(d, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        p = os.path.join(d, f"item_{aweme_id or 'unknown'}_{ts}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        return p
    except Exception:
        return ""


def _get(url, headers, timeout=15):
    """返回 (final_url, body, status_code, content_length)"""
    import urllib.request
    if HAS_REQUESTS:
        r = req_lib.get(url, headers=headers, timeout=timeout,
                        verify=False, allow_redirects=True)
        r.raise_for_status()
        return r.url, r.content, r.status_code, len(r.content)
    else:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip_mod.decompress(body)
            return resp.geturl(), body, resp.status, len(body)


def _get_urllib(url, headers, timeout=12):
    """使用系统 urllib，TLS 指纹不同于 requests"""
    import urllib.request
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
        body = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            body = gzip_mod.decompress(body)
        return resp.geturl(), body, resp.status, len(body)


def _head(url, headers, timeout=10):
    import urllib.request
    if HAS_REQUESTS:
        r = req_lib.head(url, headers=headers, timeout=timeout,
                         verify=False, allow_redirects=True)
        return r.url
    else:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            return resp.geturl()


def _parse_json(body: bytes):
    if not body or not body.strip():
        raise ValueError("API 返回了空响应（可能是 Referer/Cookie 问题或 IP 限制）")
    text = body.decode("utf-8", errors="replace").strip()
    if text.startswith("<"):
        raise ValueError("API 返回 HTML（被重定向到登录页，Cookie 可能过期）")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(f"API 响应不是 JSON: {text[:80]}")


def _ms_token():
    raw = uuid.uuid4().hex * 4
    return raw[:128]


def _retry_get(get_fn, url, headers, retries=2):
    """同线路内部重试，区分网络抖动（重试）和真实拒绝（立即放弃）"""
    import random
    last_err = None
    for attempt in range(retries + 1):
        try:
            return get_fn(url, headers)
        except Exception as e:
            last_err = e
            err_str = str(e)
            if any(x in err_str for x in ["403", "404", "HTML", "JSON"]):
                raise
            # 空响应可能是瞬时风控，加抖动延迟后重试
            if attempt < retries:
                wait = RETRY_WAIT + random.uniform(0.1, 0.5) * (attempt + 1)
                time.sleep(wait)
    raise last_err


# ── 链接 & ID 处理 ────────────────────────────────────────────────────────────

def extract_url(text: str) -> str:
    """从纯链接或任意分享文字中提取第一个有效抖音/TikTok 链接"""
    pat = re.compile(
        r'https?://(?:v\.douyin\.com|vm\.tiktok\.com|www\.douyin\.com'
        r'|m\.douyin\.com|www\.tiktok\.com)/[^\s\u4e00-\u9fff，。！？、；：'
        r'""\'\'【】《》（）\[\]{}]*'
    )
    m = pat.search(text.strip())
    if m:
        return m.group(0).rstrip("/.,;!?）》】")
    raise ValueError(
        "未找到有效的抖音/TikTok 链接\n\n支持：\n"
        "• https://v.douyin.com/xxx/\n"
        "• https://www.douyin.com/video/xxx\n"
        "• https://www.douyin.com/note/xxx（图文帖）\n"
        "• 包含上述链接的分享文字"
    )


def resolve_short(url: str, cookie_str: str) -> str:
    return _head(url, {"User-Agent": UA_MOBILE,
                       "Referer": "https://www.douyin.com/",
                       "Cookie": cookie_str})


def get_aweme_id(url: str):
    for p in [r"/video/(\d+)", r"/note/(\d+)",
              r"item_ids=(\d+)", r"/(\d{15,20})"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def guess_content_type(original_url: str, resolved_url: str) -> str:
    for url in (original_url, resolved_url):
        if "/note/" in url:
            return "note"
        # iesdouyin 分享页也可能是图文帖，但 URL 带 /video/；
        # 此时无法预判，保守返回 video，等线路A/E 纠正
    return "video"


def refine_content_type(item: dict, current_type: str) -> str:
    """拿到 item 后，根据 aweme_type 纠正预判类型

    aweme_type：2 = 图集/图文帖（分享页常见），68 = 图文帖（Web/note 接口常见），
    其余按普通视频处理。两者都应归为 note，否则日志会把图文帖打成「普通视频」，
    Referer 也会拼成 /video/<id>。
    """
    if item and item.get("aweme_type") in (2, 68):
        return "note"
    return current_type


def load_cookies(path: str):
    cj = http.cookiejar.MozillaCookieJar()
    cj.load(path, ignore_discard=True, ignore_expires=True)
    d = {c.name: c.value for c in cj if "douyin.com" in (c.domain or "")}
    return "; ".join(f"{k}={v}" for k, v in d.items()), d


def _default_download_dirs() -> list:
    """常见「下载」目录（英文 Downloads / 中文「下载」+ 保存位置默认路径）。"""
    dirs, seen = [], set()

    def _add(p):
        if not p:
            return
        p = os.path.normpath(os.path.expanduser(p))
        key = os.path.normcase(p)
        if key in seen:
            return
        if os.path.isdir(p):
            seen.add(key)
            dirs.append(p)

    home = os.path.expanduser("~")
    for name in ("Downloads", "下载"):
        _add(os.path.join(home, name))
    # Windows：USERPROFILE\Downloads（与 ~ 有时不一致）
    up = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    if up:
        for name in ("Downloads", "下载"):
            _add(os.path.join(up, name))
    return dirs


def find_best_cookie_file(search_dirs) -> str:
    """
    在给定目录（仅顶层 *.txt）中找最合适的抖音 Netscape Cookie 文件。
    评分：含登录态(sid_tt/sessionid) > 含 s_v_web_id > 字段多 > 修改时间新。
    找不到返回 ""。
    """
    candidates = []
    for d in search_dirs or []:
        if not d or not os.path.isdir(d):
            continue
        try:
            names = os.listdir(d)
        except Exception:
            continue
        for name in names:
            if not name.lower().endswith(".txt"):
                continue
            # 跳过明显不是 cookie 的常见文本
            low = name.lower()
            if low in ("readme.txt", "license.txt", "changelog.txt"):
                continue
            path = os.path.join(d, name)
            if not os.path.isfile(path):
                continue
            try:
                if os.path.getsize(path) > 2 * 1024 * 1024:  # >2MB 基本不是 cookie
                    continue
            except Exception:
                continue
            try:
                _, ck = load_cookies(path)
            except Exception:
                continue
            if not ck:
                continue
            score = len(ck)
            if "sid_tt" in ck or "sessionid" in ck:
                score += 1000
            if "s_v_web_id" in ck:
                score += 500
            try:
                mtime = os.path.getmtime(path)
            except Exception:
                mtime = 0
            candidates.append((score, mtime, path))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


# ── API 请求头 ────────────────────────────────────────────────────────────────

def _web_headers(aweme_id, cookie_str, page_type):
    referer = f"https://www.douyin.com/{page_type}/{aweme_id}"
    return {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Origin": "https://www.douyin.com",
        "Connection": "keep-alive",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "Cookie": cookie_str,
    }


def _web_api_url(aweme_id, s_v_web_id, style="full"):
    ms = _ms_token()
    base = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}"
    if style == "full":
        return (base + f"&device_platform=webapp&aid=6383"
                f"&channel=channel_pc_web&pc_client_type=1"
                f"&version_code=190500&version_name=19.5.0"
                f"&cookie_enabled=true&screen_width=1920&screen_height=1080"
                f"&browser_language=zh-CN&browser_platform=Win32"
                f"&browser_name=Chrome&browser_version=124.0.0.0"
                f"&browser_online=true&os_name=Windows&os_version=10"
                f"&cpu_core_num=8&device_memory=8&platform=PC"
                f"&downlink=10&effective_type=4g&round_trip_time=50"
                f"&webid={s_v_web_id}&verifyFp={s_v_web_id}&fp={s_v_web_id}"
                f"&msToken={ms}")
    elif style == "slim":
        return base + f"&device_platform=webapp&aid=6383&msToken={ms}"
    else:  # legacy
        return (base + f"&aid=1128&version_name=23.5.0"
                f"&device_platform=webapp&cookie_enabled=true&msToken={ms}")


def _extract_item(data: dict):
    item = data.get("aweme_detail")
    if not item:
        sc = data.get("status_code", "?")
        msg = data.get("status_msg", "")
        raise ValueError(f"aweme_detail 为空 (status_code={sc} '{msg}')")
    return item


# ── 解析线路 ─────────────────────────────────────────────────────────────────
# 说明：更早的 Web+requests / Web+urllib / iesdouyin 三条线路在实际下载中命中率
# 几乎为 0（抖音 Web 接口普遍返回空响应），已移除以节省逐条重试的等待时间。现有
# 有效线路为：A（Mobile feed）→ B（分享页）→ C（图文/实况专用）。
# 移除三条线路后，_web_headers / _web_api_url / _get_urllib 等仅供那三条老线路使用的
# 底层 helper 便成为未调用代码，保留不影响运行（如需彻底瘦身可另行清理）。


def line_a_mobile(aweme_id, cookie_str, log_cb=None):
    """线路A：Mobile feed API，找不到时回退单条查询接口"""
    hdrs = {"User-Agent": UA_ANDROID,
            "Cookie": cookie_str, "Accept-Encoding": "gzip"}

    # D1：原有 feed 接口
    api_feed = (f"https://api3-normal-c-hl.amemv.com/aweme/v1/feed/"
                f"?aweme_id={aweme_id}&version_code=210202&app_name=aweme")
    try:
        final_url, body, status, length = _retry_get(_get, api_feed, hdrs)
        if log_cb:
            log_cb(f"  D HTTP={status} len={length}B")
        data = _parse_json(body)
        items = data.get("aweme_list", [])
        if log_cb:
            log_cb(f"  D aweme_list 返回 {len(items)} 条")
        for item in items:
            if str(item.get("aweme_id", "")) == str(aweme_id):
                return item
        if log_cb:
            log_cb(f"  D feed 未命中，切换单条查询…")
    except Exception as e:
        if log_cb:
            log_cb(f"  D feed 异常: {e}，切换单条查询…")

    # D2：单条精准查询（图文帖不会被 feed 过滤）
    api_single = (f"https://api3-normal-c-hl.amemv.com/aweme/v1/aweme/detail/"
                  f"?aweme_id={aweme_id}&version_code=210202&app_name=aweme")
    final_url, body, status, length = _retry_get(_get, api_single, hdrs)
    if log_cb:
        log_cb(f"  D2 HTTP={status} len={length}B")
    data = _parse_json(body)
    item = data.get("aweme_detail")
    if item:
        return item
    raise ValueError(
        f"aweme_list 中未找到 aweme_id={aweme_id}"
        f"，单条查询也未返回 aweme_detail")


def _parse_note_from_html(html: str, debug_errors: list = None) -> dict:
    """
    从抖音图文帖页面 HTML 提取数据。
    数据在 self.__pace_f.push([1,"..."]) 这个 React 服务端流式数据块里。
    """
    def dbg(msg):
        if debug_errors is not None:
            debug_errors.append(msg)

    # ── 方法1：从 __pace_f.push 提取（主要方法）
    pace_blocks = re.findall(
        r'self\.__pace_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)',
        html, re.DOTALL
    )
    dbg(f"找到 __pace_f.push 块: {len(pace_blocks)} 个")

    for i, raw_block in enumerate(pace_blocks):
        if 'awemeId' not in raw_block and 'awemeType' not in raw_block:
            continue
        try:
            decoded = json.loads(f'"{raw_block}"')
            has68 = ('awemeType":68' in decoded or 'awemeType\\":68' in decoded)
            dbg(f"  块 解码后 len={len(decoded):,} awemeType68={has68}")

            # 放宽：只要块里有 awemeId 就值得解析，不再强制要求 type=68
            # （普通视频走线路C时也需要能解析）

            images_data = []
            video_items = []

            img_arr_start = decoded.find('"images":[{')
            if img_arr_start >= 0:
                arr_pos = decoded.find('[{', img_arr_start)
                depth2, in_str2, esc2 = 0, False, False
                k = arr_pos
                while k < len(decoded):
                    c2 = decoded[k]
                    if esc2: esc2 = False
                    elif c2 == '\\': esc2 = True
                    elif c2 == '"' and not esc2: in_str2 = not in_str2
                    elif not in_str2:
                        if c2 in '[{': depth2 += 1
                        elif c2 in ']}':
                            depth2 -= 1
                            if depth2 == 0: break
                    k += 1
                try:
                    images_arr = json.loads(decoded[arr_pos:k+1])
                    dbg(f"  images 数组解析成功: {len(images_arr)} 条")
                    for img_idx, img_item in enumerate(images_arr):
                        url_list = img_item.get('urlList', [])
                        video_obj = img_item.get('video') or {}
                        duration = video_obj.get('duration', 0) or 0
                        w = img_item.get('width', 0)
                        h = img_item.get('height', 0)
                        best_img = next(
                            (u for u in url_list if 'jpeg' in u.lower() and 'water' not in u),
                            url_list[0] if url_list else ""
                        )
                        # 静图始终保留（旧版把带 Live 的图整张丢进 video_items，
                        # 结果实况图的静态版本永远下不到）
                        if url_list:
                            images_data.append({"url_list": url_list,
                                                "width": w, "height": h})
                        live_urls = _find_live_video_urls(img_item)
                        if live_urls:
                            video_items.append({
                                "url": live_urls[0],
                                "duration": duration,
                                "thumb": best_img,
                                "width": w, "height": h,
                                "img_index": img_idx,
                            })
                except (json.JSONDecodeError, Exception) as e:
                    dbg(f"  images JSON 解析失败: {e}，回退到正则")
                    fallback_section = decoded[arr_pos:k+1]
                    for mm in re.finditer(r'"urlList":\[([^\]]+)\]', fallback_section):
                        urls = re.findall(r'"(https://p[^"]+)"', mm.group(1))
                        urls = [u for u in urls if 'aweme-avatar' not in u]
                        if urls:
                            images_data.append({"url_list": urls, "width": 0, "height": 0})

            dbg(f"  提取结果: {len(images_data)} 张图片 + {len(video_items)} 个视频帧")

            desc_m  = re.search(r'"desc":"([^"]*?)"', decoded)
            nick_m  = re.search(r'"nickname":"([^"]*?)"', decoded)
            music_title_m = re.search(r'"title":"([^"]*?)","coverThumb"', decoded)
            music_url_m   = re.search(r'"playUrl":"([^"]+)"', decoded)
            aweme_id_val  = re.search(r'"awemeId":"(\d+)"', decoded)

            if not images_data and not video_items:
                dbg(f"  块 无图片也无视频帧，跳过")
                continue

            item = {
                "aweme_id":     aweme_id_val.group(1) if aweme_id_val else "",
                "aweme_type":   68,
                "desc":         desc_m.group(1) if desc_m else "",
                "author":       {"nickname": nick_m.group(1) if nick_m else "未知"},
                "statistics":   {},
                "images": [
                    {"url_list": img["url_list"],
                     "width": img["width"], "height": img["height"]}
                    for img in images_data
                ],
                "_video_frames": video_items,
                "video":  {},
                "music":  {
                    "title":    music_title_m.group(1) if music_title_m else "",
                    "play_url": {"url_list": [music_url_m.group(1)] if music_url_m else []},
                },
            }
            dbg(f"  ✓ item: aweme_id={item['aweme_id']} "
                f"图片={len(item['images'])}张 视频帧={len(item['_video_frames'])}个")
            return item

        except Exception as e:
            dbg(f"  块[{i}] 处理异常: {e}")
            continue

    # ── 方法2：备用 RENDER_DATA 解析
    import urllib.parse as _up
    for pat, url_encoded in [
        (r'<script id="RENDER_DATA"[^>]*>([^<]+)</script>', True),
        (r'<script id="__NEXT_DATA__"[^>]*>(\{[\s\S]+?\})</script>', False),
    ]:
        m = re.search(pat, html, re.DOTALL)
        if not m:
            continue
        raw = m.group(1).strip()
        try:
            if url_encoded:
                raw = _up.unquote(raw)
            data = json.loads(raw)

            def _find(obj, depth=0):
                if depth > 12 or not isinstance(obj, dict):
                    return None
                if "aweme_id" in obj and "images" in obj:
                    return obj
                if "awemeId" in obj and "images" in obj:
                    return obj
                for v in obj.values():
                    r = (_find(v[0], depth+1) if isinstance(v, list) and v and isinstance(v[0], dict)
                         else _find(v, depth+1) if isinstance(v, dict) else None)
                    if r:
                        return r
            item = _find(data)
            if item:
                dbg(f"  备用RENDER_DATA解析成功")
                return item
        except Exception as e:
            dbg(f"  备用解析失败: {e}")

    raise ValueError("HTML 页面中未找到图文数据（已尝试 pace_f 和 RENDER_DATA）")


def line_c_note(aweme_id, cookie_str, s_v_web_id, log_cb=None, prefer_html=False):
    """
    线路C：图文帖专用线路。
    prefer_html=True 时先跑 C2(note 页 SSR)——补实况地址只有它管用，
    C1 那三个接口缺 a_bogus 签名基本必空，白等 6 次请求约 20 秒。
    C1. /aweme/v1/web/note/item_list/?aweme_ids=[xxx]
    C2. /aweme/v2/web/note/aweme/?aweme_id=xxx
    C3. HTML页面解析 douyin.com/note/xxx
    C4. iesdouyin.com/share/note/xxx/
    """
    note_referer = f"https://www.douyin.com/note/{aweme_id}"
    ms = _ms_token()
    errors = []

    base_hdrs = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": note_referer,
        "Origin": "https://www.douyin.com",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "Cookie": cookie_str,
    }

    def _try_c1():
        # C1：图文专用 REST 接口
        c1_urls = [
            (f"https://www.douyin.com/aweme/v1/web/note/item_list/"
             f"?aweme_ids=[{aweme_id}]&aid=6383&version_name=19.5.0"
             f"&device_platform=webapp&cookie_enabled=true"
             f"&msToken={ms}&webid={s_v_web_id}"),
            (f"https://www.douyin.com/aweme/v2/web/note/aweme/"
             f"?aweme_id={aweme_id}&aid=6383&device_platform=webapp"
             f"&msToken={ms}"),
            (f"https://www.douyin.com/aweme/v1/web/aweme/detail/"
             f"?aweme_id={aweme_id}&aid=6383&device_platform=webapp"
             f"&note_type=1&aweme_type=68&msToken={ms}"),
        ]
        for api_url in c1_urls:
            for get_fn in (_get_urllib, _get):
                fn_name = "urllib" if get_fn == _get_urllib else "requests"
                try:
                    final_url, body, status, length = get_fn(api_url, base_hdrs)
                    errors.append(f"C1/{fn_name} HTTP={status} len={length}B url=...{api_url[-35:]}")
                    data = _parse_json(body)
                    errors.append(f"  → JSON keys={list(data.keys())}")
                    candidates = [
                        data.get("aweme_detail"),
                        (data.get("aweme_list") or [None])[0],
                        (data.get("item_list") or [None])[0],
                    ]
                    for item in candidates:
                        if item:
                            at = item.get("aweme_type")
                            img_n = len(item.get("images") or [])
                            errors.append(f"  → item aweme_type={at} images={img_n}")
                            return item
                    errors.append(f"  → 所有字段为空")
                except Exception as e:
                    errors.append(f"C1/{fn_name} ...{api_url[-30:]}: {str(e)[:60]}")
        return None

    def _try_c2():
        # C2：HTML 页面解析（note 页 SSR，实况地址只在这里）
        html_hdrs = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.douyin.com/",
            "Cookie": cookie_str,
        }
        for page_url in [
            f"https://www.douyin.com/note/{aweme_id}",
            f"https://www.iesdouyin.com/share/note/{aweme_id}/",
        ]:
            for get_fn in (_get_urllib, _get):
                fn_name = "urllib" if get_fn == _get_urllib else "requests"
                try:
                    final_url, body, status, length = get_fn(page_url, html_hdrs)
                    html = body.decode("utf-8", errors="ignore")
                    errors.append(f"C2/{fn_name} HTML HTTP={status} len={length}B url={page_url[-30:]}")
                    parse_debug = []
                    item = _parse_note_from_html(html, debug_errors=parse_debug)
                    for pd in parse_debug:
                        errors.append(pd)
                    if item:
                        errors.append(f"  → HTML解析成功! aweme_type={item.get('aweme_type')} images={len(item.get('images') or [])}")
                        return item
                except Exception as e:
                    errors.append(f"C2/{fn_name} {page_url[-30:]}: {str(e)[:60]}")
        return None

    for stage in ((_try_c2, _try_c1) if prefer_html else (_try_c1, _try_c2)):
        got = stage()
        if got:
            return got

    if log_cb:
        for e_msg in errors:
            log_cb(e_msg)
    raise ValueError(
        "线路C（图文专用）全部失败。详细调试信息：\n  " +
        "\n  ".join(errors))


def _brace_match(text, start):
    """从 text[start] 处的 '{' 起做括号配对，返回完整 JSON 子串；失败返回 None"""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


def _extract_from_router_data(html):
    """
    从移动分享页 HTML 的 window._ROUTER_DATA 中提取 item_list[0]。
    结构：loaderData → "<type>_(id)/page" → videoInfoRes → item_list[0]
    找不到返回 None。
    """
    m = re.search(r"window\._ROUTER_DATA\s*=\s*", html)
    if not m:
        return None
    brace = html.find("{", m.end())
    if brace < 0:
        return None
    raw = _brace_match(html, brace)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    loader = data.get("loaderData") or {}
    for _key, node in loader.items():
        if not isinstance(node, dict):
            continue
        info = (node.get("videoInfoRes") or node.get("itemInfoRes")
                or node.get("noteInfoRes") or node.get("videoInfo"))
        if isinstance(info, dict):
            lst = info.get("item_list") or info.get("aweme_list") or []
            if lst and isinstance(lst[0], dict):
                return lst[0]
    return None


def _to_nowm(u: str) -> str:
    """playwm(带水印) → play(无水印)；顺带补协议"""
    if u.startswith("//"):
        u = "https:" + u
    return u.replace("/playwm/", "/play/").replace("/playwm?", "/play?")


# 只匹配像视频流的地址：抖音图片是 .jpeg/.heic，不会命中
_VIDEO_URL_RE = re.compile(
    r"https?:(?://|\\/\\/)[^\s\"']+?(?:/play/|/playwm/|video_id=|\.mp4)[^\s\"'\\]*",
    re.I,
)


def _find_live_video_urls(img: dict) -> list:
    """从单张图片节点里尽力挖出 Live（实况/动图）的视频地址。

    抖音在不同接口/不同版本里键名不统一，已知至少这几种形状：
      snake（移动 feed / 分享页 item_list）：video.play_addr.url_list = [...]
      camel（Web SSR _ROUTER_DATA）：        video.playAddr = [{"src": ...}]
      偶尔还有 videoPlayAddr / playApi / download_addr
    先按已知键名取，全都取不到时对整个子树做正则兜底，避免键名一改就瞎。
    """
    urls = []
    v = img.get("video")
    if isinstance(v, dict):
        for key in ("play_addr", "download_addr", "play_addr_h264",
                    "playAddr", "downloadAddr", "playApi", "videoPlayAddr"):
            node = v.get(key)
            if isinstance(node, dict):
                uri = node.get("uri") or ""
                if isinstance(uri, str) and uri.startswith("http"):
                    urls.append(uri)          # 可直连的 CDN 地址优先
                urls += [u for u in (node.get("url_list") or node.get("urlList") or [])
                         if isinstance(u, str)]
            elif isinstance(node, list):
                for e in node:
                    if isinstance(e, dict) and isinstance(e.get("src"), str):
                        urls.append(e["src"])
                    elif isinstance(e, str):
                        urls.append(e)
            elif isinstance(node, str):
                urls.append(node)

    if not urls:                       # 正则兜底：整个图片节点里捞视频地址
        try:
            blob = json.dumps(img, ensure_ascii=False)
        except Exception:
            blob = str(img)
        urls = _VIDEO_URL_RE.findall(blob)

    out, seen = [], set()
    for u in urls:
        u = _to_nowm(u.replace("\\/", "/"))
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _all_play_urls(video: dict) -> list:
    """列出一个视频**所有**可用地址，按优先级排序、去重。

    抖音一条视频通常给 4 个 CDN 域名 × 5 组地址（play_addr / h264 / download_addr /
    lowbr / 265）＝ 约 20 个候选。任何单个 CDN 都可能被墙、超时、或连接中断
    （如 requests 的 ConnectionError: Connection aborted），所以下载要逐个试，
    不能只认第一个。

    另：反流(reflow)数据里 play_addr.uri 是可直连的 CDN 对象地址，而 url_list 是
    aweme.snssdk.com 的 App 接口包装壳（PC UA 直连回 200 + 空 body），故 uri 优先。
    """
    out, seen = [], set()

    def add(u):
        if isinstance(u, str) and u.startswith("http"):
            u = _to_nowm(u)
            if u not in seen:
                seen.add(u)
                out.append(u)

    add(((video or {}).get("play_addr") or {}).get("uri"))
    # h265 兼容性差，排最后
    for key in ("play_addr", "play_addr_h264", "download_addr",
                "play_addr_lowbr", "play_addr_265"):
        node = (video or {}).get(key)
        if isinstance(node, dict):
            for u in (node.get("url_list") or []):
                add(u)
    return out


def _best_play_url(video: dict) -> str:
    urls = _all_play_urls(video)
    return urls[0] if urls else ""


def _collect_live_frames(item: dict) -> list:
    """汇总图文帖里所有实况(Live)视频，统一成 {url, thumb, duration, img_index}。

    两个来源合并：
      · _video_frames —— 线路C 的 HTML 解析器产出
      · images[i].video —— 线路A/F 的 item 直接携带
    注意：反流分享页(PackSourceEnum_DOUYIN_REFLOW)对实况图是阉割下发的，
    images[i] 只有 uri/url_list/width/height，这里自然会返回空。
    """
    frames = [dict(f) for f in (item.get("_video_frames") or [])]
    have = {f.get("img_index") for f in frames if isinstance(f.get("img_index"), int)}
    for idx, img in enumerate(item.get("images") or []):
        if idx in have:
            continue
        urls = _find_live_video_urls(img)
        if not urls:
            continue
        ul = img.get("url_list") or img.get("urlList") or []
        frames.append({
            "url":       urls[0],
            "thumb":     ul[0] if ul else "",
            "duration":  ((img.get("video") or {}).get("duration") or 0),
            "img_index": idx,
        })
    return frames


def _playwm_to_play(item):
    """把 video.play_addr 里的 playwm(带水印) 换成 play(无水印)，原地修改并返回"""
    v = item.get("video") or {}
    pa = v.get("play_addr") or {}
    ul = pa.get("url_list") or []
    if ul:
        pa["url_list"] = [
            u.replace("/playwm/", "/play/").replace("/playwm?", "/play?")
            for u in ul
        ]
        v["play_addr"] = pa
        item["video"] = v
    return item


def line_b_share_page(aweme_id, real_url, cookie_str, log_cb=None):
    """
    线路B：视频分享页 _ROUTER_DATA（普通视频的确定性兜底）。
    移动分享页 SSR HTML 内嵌 window._ROUTER_DATA，其中
    loaderData[*/page].videoInfoRes.item_list[0] 即完整视频/图文详情。
    不依赖推荐 feed 命中，也不需要 a_bogus 签名。
    play_addr 为 playwm(带水印)，返回前转成 play(无水印)。
    """
    hdrs = {
        "User-Agent": UA_MOBILE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Referer": "https://www.iesdouyin.com/",
        "Cookie": cookie_str,
    }

    # 候选页面：优先用还原出的真实分享页，再兜底标准 share/video 页
    cand, seen = [], set()
    for u in (real_url, f"https://www.iesdouyin.com/share/video/{aweme_id}/"):
        if u and "/share/" in u and u not in seen:
            seen.add(u)
            cand.append(u)

    errors = []
    for page_url in cand:
        for get_fn in (_get_urllib, _get):
            fn_name = "urllib" if get_fn == _get_urllib else "requests"
            try:
                final_url, body, status, length = get_fn(page_url, hdrs)
                html = body.decode("utf-8", errors="ignore")
                if log_cb:
                    log_cb(f"B/{fn_name} HTTP={status} len={length}B "
                           f"url=...{page_url[-32:]}")
                item = _extract_from_router_data(html)
                if item:
                    _playwm_to_play(item)
                    if log_cb:
                        log_cb(f"B/{fn_name} 命中 "
                               f"aweme_type={item.get('aweme_type')} "
                               f"images={len(item.get('images') or [])}")
                    return item
                errors.append(f"B/{fn_name} 页面无 _ROUTER_DATA 视频数据")
            except Exception as e:
                errors.append(f"B/{fn_name} ...{page_url[-28:]}: {str(e)[:60]}")

    if log_cb:
        for e_msg in errors:
            log_cb(e_msg)
    raise ValueError("线路B（视频分享页）未提取到数据：" + " | ".join(errors[:4]))


# ── 媒体提取 ──────────────────────────────────────────────────────────────────

class MediaItem:
    """一个媒体项 = 网页上的一格内容（保持与浏览器一一对应）。

    实况图在网页上就是一格，只是它同时含静图和一段 mp4，因此不再拆成两张卡，
    而是由 live_url 挂在同一项上；下载时该项落两个文件。
    """
    __slots__ = ("kind", "label", "url", "ext", "thumb_url", "index",
                 "default_checked", "live_url", "url_alts")

    def __init__(self, kind, label, url, ext, thumb_url="", index=0,
                 default_checked=True, live_url="", url_alts=None):
        self.kind            = kind
        self.label           = label
        self.url             = url
        self.ext             = ext
        self.thumb_url       = thumb_url
        self.index           = index
        self.default_checked = default_checked
        self.live_url        = live_url          # 实况图附带的 mp4，空则无
        # 备选地址（同一内容的其它 CDN / 码率），首选失败时逐个回退
        self.url_alts        = [u for u in (url_alts or []) if u and u != url]


def parse_media(item: dict) -> list:
    results = []
    video        = item.get("video") or {}
    music        = item.get("music") or {}
    images       = item.get("images") or []
    aweme_type   = item.get("aweme_type", 0)
    video_frames = item.get("_video_frames") or []

    def _ulist(d, key):
        """安全取 d[key].url_list：任何一层为 None / 非 dict 都返回 []"""
        sub = (d or {}).get(key)
        return (sub.get("url_list") or []) if isinstance(sub, dict) else []

    play_urls = (
        _ulist(video, "play_addr") or
        _ulist(video, "download_addr") or
        _ulist(video, "play_addr_h264")
    )
    cover_urls = (
        _ulist(video, "origin_cover") or
        _ulist(video, "cover")
    )
    cover_url = cover_urls[0] if cover_urls else ""

    # 图集判定：图文帖的 item 里同样带 video 节点，但它只是 cover/dynamic_cover
    # 的容器，play_addr 里是没有真实视频流的占位地址（请求回 200 + 空 body）。
    # 仅当 duration > 0 时才认为存在真正的幻灯片合成视频。
    duration   = video.get("duration") or 0          # 毫秒
    is_gallery = bool(images) or aweme_type in (2, 68)

    # 实况(Live)视频：按图片下标归位，没有下标的当独立视频帧处理
    frames     = _collect_live_frames(item)
    live_by_ix = {f["img_index"]: f for f in frames
                  if isinstance(f.get("img_index"), int)}
    orphans    = [f for f in frames if not isinstance(f.get("img_index"), int)]

    if orphans:
        for j, vf in enumerate(orphans):
            results.append(MediaItem(
                "video", f"视频 {j+1}（无水印 MP4）", vf["url"], ".mp4",
                vf.get("thumb", ""), j, True
            ))
    elif play_urls and not (is_gallery and duration <= 0):
        label = "幻灯片合成视频（MP4）" if aweme_type in (2, 68) else "视频（无水印 MP4）"
        all_urls = _all_play_urls(video)
        results.append(MediaItem("video", label, all_urls[0], ".mp4",
                                 cover_url, 0, True, url_alts=all_urls[1:]))

    # 图片（实况图的静图与动图各自独立成项，紧挨着排）
    for i, img in enumerate(images):
        url_list = img.get("url_list") or []
        if not url_list:
            continue
        vf = live_by_ix.get(i)
        results.append(MediaItem(
            "image",
            f"图片 {i+1} · 实况" if vf else f"图片 {i+1}",
            url_list[0], ".jpg",
            url_list[-1] if len(url_list) > 1 else url_list[0],
            i, True,
            live_url=(vf or {}).get("url", ""),
            url_alts=url_list[1:]          # 图片 url_list 就是多 CDN 镜像
        ))

    # 音频（默认不选）
    music_urls = _ulist(music, "play_url")
    if music_urls:
        results.append(MediaItem(
            "audio",
            f"音频：{music.get('title', '背景音乐')[:20]}",
            music_urls[0], ".mp3", "", 0, False
        ))

    if not results:
        raise ValueError(
            "未找到任何可下载媒体\n可能原因：视频已删除、设为私密，或 API 格式变更")
    return results


def make_filename(author: str, desc: str, create_time: int, suffix: str, ext: str) -> str:
    """文件命名：[桌面助手][作者]YYYYMMDD_文案_后缀.ext"""
    def clean(s, n=30):
        return re.sub(r'[\\/:*?"<>|\r\n\t]', "_", str(s)).strip("_ ")[:n]

    date_str = ""
    if create_time:
        try:
            date_str = datetime.datetime.fromtimestamp(create_time).strftime("%Y%m%d") + "_"
        except Exception:
            pass

    # 后缀给 16 字（原为 12）：「图片 1 · Live」这类标签会被 12 字砍成
    # 「图片 1 · Live（」，尾巴丢一半很难看
    return f"[桌面助手][{clean(author, 15)}]{date_str}{clean(desc, 35)}_{clean(suffix, 16)}{ext}"


# ── 解析线程 ──────────────────────────────────────────────────────────────────

class ParseWorker(QThread):
    ok  = pyqtSignal(object, list)
    err = pyqtSignal(str)
    log = pyqtSignal(str, str)   # msg, level(ok/warn/err/info)

    def __init__(self, url_text, cookie_path):
        super().__init__()
        self.url_text    = url_text
        self.cookie_path = cookie_path

    def _log(self, msg, level="info"):
        self.log.emit(msg, level)

    def run(self):
        try:
            # 步骤1：提取 URL
            url = extract_url(self.url_text)
            is_short = any(h in url for h in ("v.douyin.com", "vm.tiktok.com"))
            self._log(f"识别链接：{url}")

            # 步骤2：加载 Cookie
            cookie_str = ""; s_v_web_id = ""; cookie_dict = {}
            if self.cookie_path and os.path.isfile(self.cookie_path):
                cookie_str, cookie_dict = load_cookies(self.cookie_path)
                s_v_web_id = cookie_dict.get("s_v_web_id", "")
                self._log(f"已加载 Cookie（{len(cookie_dict)} 个字段）")

            # 步骤3：还原短链
            original_url = url
            if is_short:
                self._log("还原短链…")
                url = resolve_short(url, cookie_str)
                self._log(f"真实 URL：{url}")

            # 步骤4：提取 aweme_id
            aweme_id = get_aweme_id(url)
            if not aweme_id:
                raise ValueError(f"无法提取 aweme_id: {url}")
            self._log(f"aweme_id：{aweme_id}")

            # 步骤5：预判内容类型
            page_type = guess_content_type(original_url, url)
            type_hint = "图文帖（note）" if page_type == "note" else "视频（video）"
            self._log(f"预判类型: {type_hint}")

            # 分享链接里的 is_slides=1 / share/slides/ 就是图集/实况的确定标记
            is_slides = ("is_slides=1" in url or "/share/slides/" in url
                         or page_type == "note")

            # 步骤6：解析线路（旧命名 D/F/E 已按执行顺序改为 A/B/C）
            item = None
            errors = []
            c_done = False          # 线路C 是否已跑过，避免重复跑

            def make_log_cb(name):
                def cb(msg):
                    self._log(f"[{name}] {msg}")
                return cb

            if is_slides:
                # 图集/实况：线路A 是推荐流，对图集基本必空，跳过不等它。
                # B（分享页，元数据齐全但实况被阉割）与 C（note 页 SSR，唯一有实况
                # 地址）互不依赖 —— 并发跑，总耗时取两者最大值而不是相加。
                self._log("识别为图集/实况（is_slides），线路B、C 并发解析…")
                c_done = True
                item_b = item_c = None
                with ThreadPoolExecutor(max_workers=2) as pool:
                    fb = pool.submit(line_b_share_page, aweme_id, url, cookie_str,
                                     make_log_cb("线路B"))
                    fc = pool.submit(line_c_note, aweme_id, cookie_str, s_v_web_id,
                                     make_log_cb("线路C"), True)
                    try:
                        item_b = fb.result()
                        self._log("线路B 分享页 成功 ✓", "ok")
                    except Exception as e:
                        errors.append(f"线路B 分享页: {e}")
                        self._log(f"线路B 分享页 失败: {e}", "warn")
                    try:
                        item_c = fc.result()
                        self._log("线路C note页 成功 ✓", "ok")
                    except Exception as e:
                        errors.append(f"线路C 图文专用: {e}")
                        self._log(f"线路C 图文专用 失败: {e}", "warn")

                # B 的元数据更全（作者/时间/静图），C 只用来补实况地址
                item = item_b if item_b is not None else item_c
                if item_b is not None and item_c is not None:
                    frames = _collect_live_frames(item_c)
                    if frames and not _collect_live_frames(item_b):
                        item_b["_video_frames"] = frames
                        self._log(f"线路C ✓  补到 {len(frames)} 个实况视频", "ok")
            else:
                try:
                    self._log("尝试 线路A Mobile…")
                    item = line_a_mobile(aweme_id, cookie_str,
                                         log_cb=make_log_cb("线路A Mobile"))
                    self._log("线路A Mobile 成功 ✓", "ok")
                except Exception as e:
                    errors.append(f"线路A Mobile: {e}")
                    self._log(f"线路A Mobile 失败: {e}", "warn")

                # 线路B：分享页 _ROUTER_DATA，A 未命中时的确定性兜底
                if item is None:
                    try:
                        self._log("尝试 线路B 分享页…")
                        item = line_b_share_page(aweme_id, url, cookie_str,
                                                 log_cb=make_log_cb("线路B"))
                        self._log("线路B 分享页 成功 ✓", "ok")
                    except Exception as e:
                        errors.append(f"线路B 分享页: {e}")
                        self._log(f"线路B 分享页 失败: {e}", "warn")

            # 拿到 item 后用实际 aweme_type 纠正预判类型
            if item:
                page_type = refine_content_type(item, page_type)

            need_c, enrich = False, False
            if item is None and not c_done:
                need_c = True
                reason = "全线路失败，补试图文专用线路C"
            elif item is not None and item.get("aweme_type") in (2, 68) \
                    and not (item.get("images") or []):
                need_c = True
                reason = (f"aweme_type={item.get('aweme_type')} 但 images 为空，"
                          "用 /note/ Referer 重试")
            elif item is not None and item.get("aweme_type") in (2, 68) \
                    and not _collect_live_frames(item) and not c_done:
                # 线路B 的反流(reflow)数据源对实况图只下发静态首帧，不给那段 mp4
                need_c = True
                enrich = True
                reason = "图文帖未见实况(Live)数据，补试线路C 取 note 页 SSR"

            if need_c:
                self._log(f"线路C 图文专用：{reason}", "warn")
                try:
                    candidate = line_c_note(aweme_id, cookie_str, s_v_web_id,
                                            log_cb=make_log_cb("线路C"),
                                            prefer_html=enrich)
                    if candidate and enrich:
                        frames = _collect_live_frames(candidate)
                        if frames:
                            item["_video_frames"] = frames
                            self._log(f"线路C ✓  补到 {len(frames)} 个实况视频", "ok")
                        else:
                            self._log("线路C 也未提供实况数据，只能下静图", "warn")
                    elif candidate:
                        item = candidate
                        img_count = len(item.get("images") or [])
                        self._log(f"线路C ✓  图片数量: {img_count}", "ok")
                except Exception as e:
                    self._log(f"线路C 失败: {e}", "err")

            if not item:
                raise RuntimeError(
                    "所有解析线路均失败：\n" +
                    "\n".join(f"  · {e}" for e in errors) +
                    "\n\n可能原因：\n"
                    "  · Cookie 已过期（重新导出 cookies.txt）\n"
                    "  · 视频已删除或设为私密\n"
                    "  · 网络连接问题")

            # 步骤7：提取媒体资源
            dbg_path = dump_item_debug(item, item.get("aweme_id", "") or aweme_id)
            if dbg_path:
                self._log(f"原始 item 已转储：{dbg_path}")

            media = parse_media(item)
            aweme_type = item.get("aweme_type", 0)
            type_name  = "图文帖子" if aweme_type in (2, 68) else "普通视频"
            img_n  = len([m for m in media if m.kind == "image"])
            vid_n  = len([m for m in media if m.kind == "video"])
            live_n = len([m for m in media if m.live_url])
            files_n = len(media) + live_n          # 实况项落 2 个文件
            self._log(
                f"提取完成：{type_name}，共 {len(media)} 项"
                f"（{vid_n}视频/{img_n}图/{len(media)-vid_n-img_n}音频"
                f"，其中 {live_n} 张实况）→ {files_n} 个文件", "ok")
            if aweme_type in (2, 68) and live_n == 0:
                self._log(
                    "未取到实况(Live)视频，只有静图。若网页上确实是动图，"
                    "多半是数据源被阉割（反流分享页只给首帧）——请把日志里"
                    "线路C 的报错发来。", "warn")
            self.ok.emit(item, media)

        except Exception as e:
            self.err.emit(str(e))


# ── 下载线程 ──────────────────────────────────────────────────────────────────

class DownloadWorker(QThread):
    progress  = pyqtSignal(int)
    log       = pyqtSignal(str, str)
    done      = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, items, author, desc, create_time, save_dir, cancel_flag, video_info=None):
        super().__init__()
        self._items           = items          # list of MediaItem (已勾选)
        self._author          = author
        self._desc            = desc
        self._create_time     = create_time
        self._save_dir        = save_dir
        self._cancel          = cancel_flag
        self._video_info_ref  = video_info or {}

    def run(self):
        vi = self._video_info_ref  # 由 __init__ 传入
        aweme_id_for_ref = (vi or {}).get("aweme_id", "")
        aweme_type_for_ref = (vi or {}).get("aweme_type", 0)
        ref_path = "note" if aweme_type_for_ref in (2, 68) else "video"
        ref_url = (f"https://www.douyin.com/{ref_path}/{aweme_id_for_ref}"
                   if aweme_id_for_ref else "https://www.douyin.com/")
        hdrs   = {"User-Agent": UA_MOBILE, "Referer": ref_url}
        total  = sum(1 + (1 if it.live_url else 0) for it in self._items)
        done_count = [0]
        lock   = threading.Lock()

        def _fetch(url, path):
            """单地址单次尝试，返回 (ok, size_or_err)"""
            if HAS_REQUESTS:
                r = req_lib.get(url, headers=hdrs, stream=True,
                                timeout=30, verify=False)
                r.raise_for_status()
                downloaded = 0
                with open(path, "wb") as f:
                    for chunk in r.iter_content(32768):
                        if self._cancel[0]:
                            raise InterruptedError()
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                return downloaded
            else:
                import urllib.request
                req = urllib.request.Request(url, headers=hdrs)
                with urllib.request.urlopen(req, timeout=30, context=CTX) as resp:
                    data = resp.read()
                with open(path, "wb") as f:
                    f.write(data)
                return len(data)

        def _save(urls, label, ext):
            """按候选地址依次尝试下载，返回 (ok, path_or_err)。

            抖音一条视频会给多个 CDN 域名（365yg / amemv…）和多组码率地址，
            单个域名被墙、超时或连接中断都很常见，只试第一个就放弃太脆。
            """
            cands = [u for u in urls if u]
            if not cands:
                return False, "没有可用地址"

            filename = make_filename(
                self._author, self._desc, self._create_time, label, ext
            )
            path = os.path.join(self._save_dir, filename)
            base, ext_ = os.path.splitext(path)
            n = 1
            while os.path.exists(path):
                path = f"{base}_{n}{ext_}"; n += 1

            last = ""
            for k, url in enumerate(cands):
                if self._cancel[0]:
                    return False, "已取消"
                try:
                    size = _fetch(url, path)
                    if size == 0:
                        last = "服务端返回空内容"
                    elif size < MIN_FILE_BYTES:
                        last = f"文件过小（{size}B）"
                    else:
                        if k > 0:
                            self.log.emit(
                                f"↻ {label}：前 {k} 个地址失败，改用 "
                                f"{url.split('/')[2]} 成功", "warn")
                        return True, path
                except InterruptedError:
                    if os.path.exists(path): os.remove(path)
                    return False, "已取消"
                except Exception as e:
                    last = f"{type(e).__name__}: {str(e)[:70]}"
                if os.path.exists(path):
                    os.remove(path)          # 清掉半截文件再换下一个地址

            return False, f"{len(cands)} 个地址全部失败，最后一个：{last}"

        def _bump():
            with lock:
                done_count[0] += 1
                self.progress.emit(int(done_count[0] / total * 100))

        def download_one(item):
            if self._cancel[0]:
                return False, item, "已取消"

            ok, info = _save([item.url] + item.url_alts, item.label, item.ext)

            # 实况图：静图之外再落一个 mp4，两者同属一项
            if ok and item.live_url:
                live_label = item.label.replace(" · 实况", "") + " · Live"
                ok2, info2 = _save([item.live_url], live_label, ".mp4")
                if ok2:
                    _bump()
                    self.log.emit(f"✓ {os.path.basename(info2)}", "ok")
                elif info2 != "已取消":
                    self.log.emit(f"✗ 失败 {item.label} 的实况视频: {info2}", "err")

            if ok:
                _bump()
            return ok, item, info

        # 并发下载，最多4线程
        max_workers = min(4, total)
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(download_one, item): item for item in self._items}
            for fut in as_completed(futures):
                ok, item, info = fut.result()
                results.append((ok, item, info))
                if ok:
                    self.log.emit(f"✓ {os.path.basename(info)}", "ok")
                elif info == "已取消":
                    self.log.emit(f"✗ 已取消: {item.label}", "warn")
                else:
                    self.log.emit(f"✗ 失败 {item.label}: {info}", "err")

        if self._cancel[0]:
            self.cancelled.emit()
        else:
            self.progress.emit(100)
            self.done.emit(self._save_dir)


# ── 媒体卡片 ──────────────────────────────────────────────────────────────────

_KIND_ICON  = {"video": "🎬", "image": "🖼", "audio": "🎵"}


class MediaCard(QFrame):
    """媒体内容卡：无外框，缩略图 + 单行标题 +「选择」勾选。"""
    THUMB_W = 110
    THUMB_H = 90
    LABEL_H = 18
    # 缩略图 + 间距 + 单行字 + 间距 + 勾选区
    CARD_H = THUMB_H + 4 + LABEL_H + 2 + 22

    def __init__(self, item: MediaItem, parent=None):
        super().__init__(parent)
        self.item = item
        self._checked = item.default_checked
        self.setFixedSize(self.THUMB_W, self.CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # 缩略图：无边框、无底色块
        self.thumb = QLabel(_KIND_ICON.get(item.kind, "?"))
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        lay.addWidget(self.thumb)

        # 标签：单行，放不下右侧裁切（省略号）
        self.lbl = _ElideLabel(item.label or "")
        self.lbl.setFullText(item.label or "")
        self.lbl.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.lbl.setFixedHeight(self.LABEL_H)
        self.lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        lay.addWidget(self.lbl)

        # 勾选框（保持不变）
        self.chk = QCheckBox("选择")
        self.chk.setChecked(self._checked)
        self.chk.stateChanged.connect(self._on_chk)
        lay.addWidget(self.chk, 0, Qt.AlignCenter)

        self.refresh_theme()

        if item.thumb_url:
            self._load_thumb(item.thumb_url)

    def refresh_theme(self, *_):
        """无卡片外框；文字/勾选跟随主题。"""
        self.setStyleSheet(
            "QFrame{background:transparent;border:none;}")
        self.thumb.setStyleSheet(
            f"font-size:28px; background:transparent; border:none;"
            f" color:{tk('text_mut')};")
        self.lbl.setStyleSheet(
            f"color:{tk('text')}; font-size:11px;"
            f" background:transparent; border:none;")
        # 「选择」勾选样式保持简洁可读
        self.chk.setStyleSheet(
            f"color:{tk('text_mut')}; font-size:10px;"
            f" background:transparent; border:none;")

    def _on_chk(self, state):
        self._checked = bool(state)

    def mousePressEvent(self, e):
        self.chk.setChecked(not self.chk.isChecked())

    def _load_thumb(self, url):
        class ThumbFetch(QThread):
            done = pyqtSignal(bytes)
            def __init__(self, u): super().__init__(); self.u = u
            def run(self):
                try:
                    if HAS_REQUESTS:
                        r = req_lib.get(self.u, timeout=8, verify=False,
                                        headers={"User-Agent": UA_MOBILE})
                        self.done.emit(r.content)
                    else:
                        import urllib.request
                        with urllib.request.urlopen(self.u, timeout=8, context=CTX) as resp:
                            self.done.emit(resp.read())
                except Exception:
                    pass

        def _apply(data):
            pm = QPixmap()
            pm.loadFromData(data)
            if not pm.isNull():
                pm = pm.scaled(MediaCard.THUMB_W, MediaCard.THUMB_H,
                               Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                x = (pm.width()  - MediaCard.THUMB_W) // 2
                y = (pm.height() - MediaCard.THUMB_H) // 2
                pm = pm.copy(x, y, MediaCard.THUMB_W, MediaCard.THUMB_H)
                self.thumb.setPixmap(pm)
                self.thumb.setText("")

        t = ThumbFetch(url)
        t.setParent(self)
        t.done.connect(_apply)
        t.start()
        self._thumb_thread = t

    def is_checked(self):
        return self.chk.isChecked()


# ── 主页面 ────────────────────────────────────────────────────────────────────

def _tk_try(*keys, fallback=""):
    """按顺序尝试若干主题色键，取到第一个非空值；全都取不到就用 fallback。
    （不同版本的 style_theme 键名不一致，这里做个软兜底，避免 KeyError）"""
    for k in keys:
        try:
            v = tk(k)
        except Exception:
            continue
        # 只接受看起来像颜色的值，避免某些实现对未知键返回 None/占位串
        if isinstance(v, str) and (v.startswith("#") or v.startswith("rgb")):
            return v
    return fallback


def tooltip_qss() -> str:
    """暗色主题下 Qt 默认 QToolTip 是「白底 + 继承的浅色字」，会看不清。
    这里显式给出底色/字色/边框，两套主题都走主题色。"""
    bg = _tk_try("bg_card", "card", "panel", "surface", "bg_2", "bg", fallback="#1f2937")
    fg = _tk_try("text", "text_main", "text_pri", "text_mut", fallback="#e5e7eb")
    bd = _tk_try("border_3", "border", "text_dim", fallback="#475569")
    return (f"QToolTip{{background-color:{bg}; color:{fg};"
            f"border:1px solid {bd}; border-radius:4px;"
            f"padding:6px 8px; font-size:12px; opacity:255;}}")


class PageDouyin(QWidget):
    def __init__(self):
        super().__init__()
        self._video_info  = None
        self._media_items = []
        self._cards       = []
        self._cancel_flag = [False]
        self._parse_worker = None
        self._dl_worker    = None
        self._auto_dl      = False   # 解析成功后是否自动开始下载
        self._cookie_auto_tried = False  # 本会话是否已尝试过自动加载 Cookie

        # 注意：PAGE_QSS 从 v9.x 起就被注释掉了（橙色按钮样式实际未生效，
        # 走的是 app.qss 的通用按钮规则）。这里保持原状，不改变现有观感。
        # 想启用抖音页的橙色主题，取消下面一行的注释即可：
        # self.setStyleSheet(fmt(PAGE_QSS))
        #
        # 但 QToolTip 必须显式着色：Qt 默认给 tooltip 白底，而字色继承自
        # app.qss 的浅色文字 → 暗色主题下「白底白字」。在本页 widget 上设
        # 样式表即可作用于其所有子控件的 tooltip。
        self.setStyleSheet(tooltip_qss())
        theme.changed.connect(self.refresh_theme)

        root = QVBoxLayout(self)
        # 与系统总览一致：ContentRoot 已有左右内边距，页面不再叠第二层
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # ══ 顶部：单卡片「解析与下载」════════════════════════════════════════
        #    第1行：Cookie（左） + 保存位置（右）
        #    第2行：视频链接
        #    第3行：粘贴并解析（一键） + 取消 + 进度 + 状态
        # 功能区标准卡 #1：解析与下载
        gb_main = make_card("CardDouyinParse")
        gv = QVBoxLayout(gb_main)
        gv.setSpacing(0)  # 标题间距走全局 CARD_TITLE_BODY_GAP
        gv.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        self._card_title = install_card_title(gb_main, gv, "解析与下载")
        self._theme_titles = [self._card_title]
        self._func_cards = [gb_main]

        # 正文区自管间距，避免与标题空隙叠加
        # 必须带 #id 选择器：无选择器的 border:none 会级联到子 QLineEdit，冲掉路径框外框
        body_main = QWidget()
        body_main.setObjectName("DouyinParseBody")
        body_main.setStyleSheet(
            "#DouyinParseBody{background:transparent;border:none;}"
        )
        gv_body = QVBoxLayout(body_main)
        gv_body.setContentsMargins(0, 0, 0, 0)
        gv_body.setSpacing(7)
        gv.addWidget(body_main, 1)

        conf_row = QHBoxLayout()
        conf_row.setSpacing(14)

        # ── Cookie 列（「安装」「选择文件」在行首；状态提示上移到标题行右端）──
        ck_col = QVBoxLayout()
        ck_col.setSpacing(5)

        ck_head = QHBoxLayout()
        ck_head.setSpacing(8)
        lbl_ck = QLabel("Cookie 文件（必填，Netscape .txt 格式）")
        lbl_ck.setObjectName("SecTitle")
        ck_head.addWidget(lbl_ck, 0)
        # 状态提示用自动省略标签，占据标题右侧剩余宽度、右对齐；文字再长也只省略、
        # 不会把 Cookie 列顶宽越过与「保存位置」列的分界（完整文字见 tooltip）。
        self.ck_status = _ElideLabel("")
        self.ck_status.setObjectName("StatusLbl")
        self.ck_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ck_head.addWidget(self.ck_status, 1)
        ck_col.addLayout(ck_head)

        ck_row = QHBoxLayout()
        ck_row.setSpacing(6)
        self.btn_ck = QPushButton("选择文件")
        self.btn_ck.setObjectName("BtnSmall")
        self.btn_ck.setMinimumWidth(72)
        self.btn_ck.setToolTip("选择 Netscape 格式的 cookies.txt")
        self.btn_ck.clicked.connect(self._pick_cookie)
        ck_row.addWidget(self.btn_ck)
        self.ck_path = QLineEdit()
        self.ck_path.setPlaceholderText("首次进入将自动扫描下载目录…")
        self.ck_path.setReadOnly(True)          # 防止误改，只能通过「选择文件」写入
        self._ck_path_icon_action = apply_folder_path_edit(self.ck_path)
        self.ck_path.textChanged.connect(self._on_cookie_change)
        ck_row.addWidget(self.ck_path, 1)
        ck_col.addLayout(ck_row)
        self._cookie_loaded_via = None   # 'auto' | 'manual' | None
        conf_row.addLayout(ck_col, 60)

        # ── 保存位置 列（浏览 + 地址；提示上移到标题行右端）────────────────────
        sv_col = QVBoxLayout()
        sv_col.setSpacing(5)

        sv_head = QHBoxLayout()
        sv_head.setSpacing(8)
        lbl_save = QLabel("保存位置")
        lbl_save.setObjectName("SecTitle")
        sv_head.addWidget(lbl_save)
        sv_head.addStretch(1)
        self.dir_hint = QLabel("解析完成后自动下载到此目录")
        self.dir_hint.setObjectName("StatusLbl")
        self.dir_hint.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.dir_hint.setStyleSheet(f"color:{tk('text_faint')}; font-size:12px;")
        sv_head.addWidget(self.dir_hint)
        sv_col.addLayout(sv_head)

        save_row = QHBoxLayout()
        save_row.setSpacing(6)
        btn_browse = QPushButton("浏览")
        btn_browse.setObjectName("BtnSmall")
        btn_browse.clicked.connect(self._choose_dir)
        save_row.addWidget(btn_browse)
        self.save_edit = QLineEdit(os.path.expanduser("~/Downloads").replace("\\", "/"))
        self._save_edit_icon_action = apply_folder_path_edit(self.save_edit)
        save_row.addWidget(self.save_edit, 1)
        sv_col.addLayout(save_row)
        conf_row.addLayout(sv_col, 40)

        gv_body.addLayout(conf_row)
        gv_body.addSpacing(2)

        # ── 链接标题行：左边是说明文字，右边（红框位置）挪进来进度条 + 完成状态 ──
        #    跟上面「保存位置」列同宽对齐（60/40 + 16px 硬隔断，与下面链接行一致）
        lbl_url = QLabel("粘贴视频链接（支持短链 / 完整链接 / 含链接的分享文字）")
        lbl_url.setObjectName("SecTitle")

        url_head_row = QHBoxLayout()
        url_head_row.setSpacing(16)
        url_head_row.addWidget(lbl_url, 60)

        self.progress = QProgressBar()
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        self.progress.setMinimumWidth(70)
        # 进度条颜色跟着数值走（红→黄→绿连续渐变），不用状态色画外边线
        # （见 _on_progress_value / _progress_gradient_color）
        self.progress.valueChanged.connect(self._on_progress_value)
        self._on_progress_value(self.progress.value())   # 初始上色（0% → 红）

        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)
        progress_row.addWidget(self.progress, 1)

        # 「取消」挪到下载提示（进度条）这一行，常驻占位、用 enabled 切换可用性，
        # 不再用 setVisible(False)——之前挂在「粘贴并解析」按钮旁边，下载开始/
        # 结束时 setVisible 切换会让那个按钮的宽度跟着回流，一会儿变长一会儿变短，
        # 观感很差；改成一直占着位置只是灰掉，就不会有任何控件跟着抖动了。
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.setFixedWidth(56)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setToolTip("下载进行中可点击取消")
        self.btn_cancel.clicked.connect(lambda: self._cancel_flag.__setitem__(0, True))
        progress_row.addWidget(self.btn_cancel)

        url_head_row.addLayout(progress_row, 40)

        gv_body.addLayout(url_head_row)

        # ── 链接输入 + 一键操作：合并成一行，省掉原来单独一整行的按钮区 ──────────
        #    左（60%，与上面 Cookie 列同宽对齐）：链接输入框
        #    16px 硬隔断（用户截图里画的绿线位置）
        #    右（40%，与上面「保存位置」列同宽对齐）：安装 / 粘贴并解析
        #    （「取消」已经挪到上面进度条那一行，这里的宽度分配固定不再变化）
        link_row = QHBoxLayout()
        link_row.setSpacing(16)          # 硬隔断：用户画绿线要求的 16px

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("粘贴链接后回车，或点右侧按钮自动读取剪贴板解析")
        self._url_edit_icon_action = apply_folder_path_edit(self.url_edit)
        self.url_edit.returnPressed.connect(lambda: self._start_flow(False))
        link_row.addWidget(self.url_edit, 60)

        act_cluster = QHBoxLayout()
        act_cluster.setSpacing(8)

        self.btn_ck_help = QPushButton("安装")
        self.btn_ck_help.setObjectName("BtnSmall")
        self.btn_ck_help.setFixedWidth(56)
        self.btn_ck_help.clicked.connect(self._cookie_help)
        self.btn_ck_help.setToolTip(
            "如何安装并导出 cookies.txt：\n"
            "1. Chrome商店安装：Get cookies.txt LOCALLY\n"
            "2. 登录 douyin.com\n"
            "3. 点扩展 → Export → 保存 .txt\n"
            "4. 回到本程序点「选择文件」")
        act_cluster.addWidget(self.btn_ck_help)

        self.btn_go = QPushButton("粘贴并解析")     # 图标已去掉，窄空间下更省地方
        self.btn_go.setObjectName("BtnDownload")
        self.btn_go.setMinimumWidth(96)
        self.btn_go.setToolTip("复制抖音链接后点这里：自动读取剪贴板 → 解析 → 下载到保存位置")
        self.btn_go.clicked.connect(lambda: self._start_flow(True))
        act_cluster.addWidget(self.btn_go, 1)

        link_row.addLayout(act_cluster, 40)
        gv_body.addLayout(link_row)

        root.addWidget(gb_main)

        # ══ 第3排：媒体卡片区 ═══════════════════════════════════════════════════
        media_head = QHBoxLayout()
        self._sec_label_widget(media_head, "媒体内容（解析后显示）")
        media_head.addStretch(1)
        self.btn_all    = QPushButton("全选")
        self.btn_none   = QPushButton("全不选")
        self.btn_dl_sel = QPushButton("选中下载")
        for b in (self.btn_all, self.btn_none, self.btn_dl_sel):
            b.setObjectName("BtnSmall")
            b.setVisible(False)
            media_head.addWidget(b)
        self.btn_dl_sel.setMinimumWidth(84)
        self.btn_dl_sel.setToolTip("只下载当前勾选的媒体项")
        self.btn_all.clicked.connect(self._select_all)
        self.btn_none.clicked.connect(self._deselect_all)
        self.btn_dl_sel.clicked.connect(self._download_selected)
        root.addLayout(media_head)

        # 媒体卡片滚动区：始终可见并占用固定高度，
        # 解析前放一张占位空卡，避免解析前后布局高度变化导致下方日志区跳动
        self.card_scroll = QScrollArea()
        self.card_scroll.setWidgetResizable(True)
        self.card_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.card_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.card_scroll.setFixedHeight(MediaCard.CARD_H + 16)
        # 去掉 QScrollArea 的默认边框 + 白色 viewport 底：
        # 默认 frameShape=StyledPanel，会画出那圈白色矩形；viewport 又
        # autoFillBackground 用调色板的 Base 色（白），所以要一起关掉。
        self.card_scroll.setFrameShape(QFrame.NoFrame)
        self.card_scroll.setObjectName("CardScroll")
        self.card_scroll.viewport().setAutoFillBackground(False)
        self.card_scroll.setStyleSheet(
            "QScrollArea#CardScroll{background:transparent;border:none;}"
            "QScrollArea#CardScroll > QWidget > QWidget{background:transparent;}"
        )
        card_inner = QWidget()
        card_inner.setAutoFillBackground(False)
        self._card_layout = QHBoxLayout(card_inner)
        self._card_layout.setContentsMargins(4, 4, 4, 4)
        self._card_layout.setSpacing(8)
        self.card_scroll.setWidget(card_inner)
        root.addWidget(self.card_scroll)

        # 初始占位空卡
        self._empty_card = None
        self._show_empty_card()

        # ══ 功能区标准卡 #2：运行日志 ═══════════════════════════════════════════
        card_log = make_card("CardDouyinLog")
        log_lay = QVBoxLayout(card_log)
        log_lay.setContentsMargins(CARD_LEFT_GAP, CARD_TOP_GAP, CARD_RIGHT_GAP, CARD_BOTTOM_GAP)
        log_lay.setSpacing(0)  # 标题间距走全局 CARD_TITLE_BODY_GAP
        self._theme_titles.append(install_card_title(card_log, log_lay, "运行日志"))
        self._func_cards.append(card_log)

        log_body = QWidget()
        log_body.setObjectName("DouyinLogBody")
        log_body.setStyleSheet(
            "#DouyinLogBody{background:transparent;border:none;}"
        )
        log_body_l = QVBoxLayout(log_body)
        log_body_l.setContentsMargins(0, 0, 0, 0)
        log_body_l.setSpacing(6)
        log_lay.addWidget(log_body, 1)

        log_head = QHBoxLayout()
        log_head.addStretch(1)
        btn_clear_log = QPushButton("清屏")
        btn_clear_log.setObjectName("BtnSmall")
        btn_clear_log.setFixedWidth(76)   # 加宽，避免「清屏」二字被截断
        # 必须用 lambda 延迟求值：此处 self.log_box 尚未创建，
        # 直接写 self.log_box.clear 会在 connect 时就取属性 → AttributeError
        btn_clear_log.clicked.connect(lambda: self.log_box.clear())
        log_head.addWidget(btn_clear_log)
        log_body_l.addLayout(log_head)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("DouyinLogBox")  # 滚动条：记录区标准（同截图工具）
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(100)
        self.log_box.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.log_box.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        log_body_l.addWidget(self.log_box, 1)
        root.addWidget(card_log, 1)

    # ── 辅助 UI ───────────────────────────────────────────────────────────────

    def _sec_label(self, parent_layout, text):
        lbl = QLabel(text)
        lbl.setObjectName("SecTitle")
        parent_layout.addWidget(lbl)

    def _sec_label_widget(self, parent_layout, text):
        lbl = QLabel(text)
        lbl.setObjectName("SecTitle")
        parent_layout.addWidget(lbl)

    def _log(self, msg, level="info"):
        colors = {"ok": tk("ok"), "err": tk("err"), "warn": tk("warn"), "info": tk("text_mut")}
        color  = colors.get(level, tk("text_mut"))
        ts     = time.strftime("%H:%M:%S")

        # 追加「之前」先判断用户是不是正停在底部。
        # 原因：append() 之后 maximum() 还没被文档布局更新（富文本 + 自动换行
        # 时尤其明显），此时直接 setValue(maximum()) 设的是「上一次」的最大值，
        # 于是日志就卡在中间不动了。
        sb = self.log_box.verticalScrollBar()
        follow = sb.value() >= sb.maximum() - 8   # 用户手动往上翻时不强拉

        self.log_box.append(
            f'<span style="color:{tk("text_faint")}">[{ts}]</span> '
            f'<span style="color:{color}">{msg}</span>'
        )
        if follow:
            self._scroll_log_bottom()

    def _scroll_log_bottom(self):
        """把日志滚到最新一行。
        moveCursor+ensureCursorVisible 走的是文档坐标，不依赖滚动条最大值；
        再补一次 singleShot(0)，等事件循环把布局跑完后修正最终位置。"""
        self.log_box.moveCursor(QTextCursor.End)
        self.log_box.ensureCursorVisible()
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())
        QTimer.singleShot(0, lambda: sb.setValue(sb.maximum()))

    def refresh_theme(self, *_):
        """重刷本页控件级样式（媒体卡片、状态文字、日志已写入的 HTML 不重绘）。"""
        # self.setStyleSheet(fmt(PAGE_QSS))   # 与上面的开关保持一致
        self.setStyleSheet(tooltip_qss())     # tooltip 跟随主题
        # theme.changed 在 __init__ 开头就已连接，控件可能还没建完 → 先探测
        if hasattr(self, "dir_hint"):
            self.dir_hint.setStyleSheet(f"color:{tk('text_faint')}; font-size:12px;")
        if hasattr(self, "ck_path"):
            restyle_folder_path_edit(self.ck_path, getattr(self, "_ck_path_icon_action", None))
            self._on_cookie_change(self.ck_path.text())   # Cookie 状态色 / 按钮样式跟随主题
        if hasattr(self, "save_edit"):
            restyle_folder_path_edit(self.save_edit, getattr(self, "_save_edit_icon_action", None))
        if hasattr(self, "url_edit"):
            restyle_folder_path_edit(self.url_edit, getattr(self, "_url_edit_icon_action", None))
        for c in self._cards:
            if hasattr(c, "refresh_theme"):
                c.refresh_theme()
        for lbl in self._theme_titles:
            restyle_card_title(lbl)
        for frame in getattr(self, "_func_cards", []):
            restyle_card_frame(frame)
        for f in self.findChildren(QFrame):
            if f.frameShape() == QFrame.HLine:
                f.setStyleSheet(fmt(DIVIDER_QSS))
        txt, col = getattr(self, "_status_cache", ("", None))
        if txt:
            self._set_status(txt, col)

    def _set_status(self, text, color=None):
        # 缓存的是「原始参数」：color 目前只用于缓存/兼容旧调用签名，
        # 进度条颜色改成只跟百分比走（见 _on_progress_value），不再用
        # 边框色传达语义状态——避免出现"蓝色内容 + 绿色外边线"两套颜色
        # 逻辑同时生效、看着混乱的问题。
        self._status_cache = (text, color)
        self.progress.setFormat(f"%p%  {text}" if text else "%p%")

    @staticmethod
    def _progress_gradient_color(pct: int) -> str:
        """0~100 的百分比映射成 红→黄→绿 的连续渐变色（而不是硬切三段，
        硬切在 30%/65% 分界点会有肉眼可见的"跳色"）。
        两段线性插值：0~50% 红→黄，50~100% 黄→绿。"""
        pct = max(0, min(100, pct))
        red, yellow, green = (239, 68, 68), (234, 179, 8), (34, 197, 94)
        if pct <= 50:
            c0, c1, t = red, yellow, pct / 50
        else:
            c0, c1, t = yellow, green, (pct - 50) / 50
        r = round(c0[0] + (c1[0] - c0[0]) * t)
        g = round(c0[1] + (c1[1] - c0[1]) * t)
        b = round(c0[2] + (c1[2] - c0[2]) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _on_progress_value(self, value):
        """进度条数值一变就重新上色，覆盖全局 QSS 里固定的蓝色 chunk；
        只画 ::chunk（进度填充部分），外层轨道边框/背景保持全局默认样式，
        不再额外画状态色的外边线。"""
        color = self._progress_gradient_color(value)
        self.progress.setStyleSheet(
            f"QProgressBar::chunk{{background:{color}; border-radius:5px;}}"
        )

    # ── Cookie ────────────────────────────────────────────────────────────────

    def showEvent(self, event):
        """本会话第一次显示本页时：自动在下载目录扫描并加载 Cookie。"""
        super().showEvent(event)
        if self._cookie_auto_tried:
            return
        self._cookie_auto_tried = True
        # 等布局/日志框就绪后再扫，避免构造期写日志
        QTimer.singleShot(0, self._auto_load_cookie)

    def _set_cookie_btn_loaded(self, loaded: bool):
        """加载成功 → 绿色「已加载」；否则恢复「选择文件」。仍可点击重新选择。"""
        btn = getattr(self, "btn_ck", None)
        if btn is None:
            return
        if loaded:
            btn.setText("已加载")
            btn.setStyleSheet(
                f"QPushButton{{background:{tk('ok')}; color:#ffffff;"
                f"border:1px solid {tk('ok')}; border-radius:6px;"
                f"padding:4px 12px; font-weight:600;}}"
                f"QPushButton:hover{{background:{tk('ok')}; color:#ffffff; opacity:0.9;}}"
            )
            btn.setToolTip("Cookie 已加载成功，仍可点击重新选择文件")
        else:
            btn.setText("选择文件")
            btn.setStyleSheet("")  # 交回 BtnSmall / 主题样式
            btn.setToolTip("选择 Netscape 格式的 cookies.txt")
            # 强制刷新 objectName 样式
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

    def _auto_load_cookie(self):
        """扫描下载目录，选中最合适的抖音 Cookie 文件并填入路径。"""
        cur = (self.ck_path.text() or "").strip()
        if cur and os.path.isfile(cur):
            return  # 用户已手动选过，不覆盖

        dirs = []
        # 优先：当前「保存位置」（默认就是 ~/Downloads）
        if hasattr(self, "save_edit"):
            save_dir = (self.save_edit.text() or "").strip()
            if save_dir:
                dirs.append(save_dir)
        # 再扫常见下载目录
        for d in _default_download_dirs():
            dirs.append(d)

        path = find_best_cookie_file(dirs)
        if path:
            self._cookie_loaded_via = "auto"
            # setReadOnly 不阻止程序 setText → 会触发 _on_cookie_change
            self.ck_path.setText(path.replace("\\", "/"))
            name = os.path.basename(path)
            self._log(
                f"✓ 已自动从下载目录加载 Cookie「{name}」，"
                f"无需再点「选择文件」（路径：{path}）",
                "ok",
            )
            self._set_status("Cookie 已自动加载 ✓", "#22c55e")
        else:
            self._cookie_loaded_via = None
            self._set_cookie_btn_loaded(False)
            self._log(
                "下载目录未找到可用 Cookie（Netscape .txt，含 douyin.com），"
                "请点「选择文件」手动指定",
                "warn",
            )

    def _pick_cookie(self):
        # 对话框默认打开当前路径或下载目录，少翻几层
        start = (self.ck_path.text() or "").strip()
        if start and os.path.isfile(start):
            start = os.path.dirname(start)
        elif hasattr(self, "save_edit") and self.save_edit.text().strip():
            start = self.save_edit.text().strip()
        else:
            dd = _default_download_dirs()
            start = dd[0] if dd else ""
        p, _ = QFileDialog.getOpenFileName(
            self, "选择 cookies.txt", start,
            "Cookie 文件 (*.txt);;所有文件 (*.*)",
        )
        if p:
            self._cookie_loaded_via = "manual"
            # setReadOnly 不阻止程序调用 setText，只阻止用户键盘输入
            self.ck_path.setText(p)
            self._log(f"✓ 已手动加载 Cookie：{p}", "ok")

    def _on_cookie_change(self, path):
        if not path or not os.path.isfile(path):
            self.ck_status.setFullText("")
            self._set_cookie_btn_loaded(False)
            return
        try:
            _, d = load_cookies(path)
            has_sid  = "sid_tt" in d or "sessionid" in d
            has_svid = "s_v_web_id" in d
            count    = len(d)
            via_auto = getattr(self, "_cookie_loaded_via", None) == "auto"
            if has_sid and has_svid:
                if via_auto:
                    msg = (f"✅ 已自动加载（{count} 字段，含登录态）"
                           f"· 无需再点「选择文件」")
                else:
                    msg = f"✅ Cookie 有效（{count} 个字段，含登录态）"
                self.ck_status.setStyleSheet(f"color:{tk('ok')};")
                self._set_cookie_btn_loaded(True)
            elif count > 0:
                need = []
                if not has_sid:
                    need.append("sid_tt/sessionid")
                if not has_svid:
                    need.append("s_v_web_id")
                prefix = "已自动加载但" if via_auto else ""
                msg = f"⚠ {prefix}缺少字段: {', '.join(need) or '关键登录字段'}"
                self.ck_status.setStyleSheet(f"color:{tk('warn')};")
                # 文件已读到仍算加载成功，按钮变绿；缺字段在状态里提示
                self._set_cookie_btn_loaded(True)
            else:
                msg = "⚠ 文件中无 douyin.com Cookie"
                self.ck_status.setStyleSheet(f"color:{tk('warn')};")
                self._set_cookie_btn_loaded(False)
            self.ck_status.setFullText(msg)
        except Exception as e:
            self.ck_status.setFullText(f"❌ 读取失败: {e}")
            self.ck_status.setStyleSheet(f"color:{tk('err')};")
            self._set_cookie_btn_loaded(False)

    def _cookie_help(self):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(self, "安装扩展 / 获取 cookies.txt",
            "1. Chrome 商店安装扩展：Get cookies.txt LOCALLY\n\n"
            "2. Chrome 打开并登录 www.douyin.com\n\n"
            "3. 点扩展图标 → Export → 保存为 .txt 到「下载」文件夹\n\n"
            "4. 本程序首次进入「抖音下载」页会自动扫描下载目录并加载；\n"
            "   成功后按钮会变成绿色「已加载」，一般无需再点「选择文件」\n"
            "   也可随时点该按钮重新选择")

    # ── 解析 ──────────────────────────────────────────────────────────────────

    def _clipboard_url(self) -> str:
        """从系统剪贴板取出一条有效的抖音/TikTok 链接；取不到返回空串"""
        cb = QApplication.clipboard()
        if cb is None:
            return ""
        text = (cb.text() or "").strip()
        if not text:
            return ""
        try:
            extract_url(text)      # 只做校验，真正的提取在 ParseWorker 里
            return text
        except Exception:
            return ""

    def _start_flow(self, use_clipboard=True):
        """一键主流程：读剪贴板 → 解析 → 解析成功后自动下载到保存位置。

        use_clipboard=True  ：点「粘贴并解析」按钮（剪贴板优先，其次输入框）
        use_clipboard=False ：在链接输入框里按回车（只用输入框内容）
        """
        text = ""
        if use_clipboard:
            text = self._clipboard_url()
            if text:
                self.url_edit.setText(text)
                self._log("已从剪贴板读取链接", "ok")
        if not text:
            text = self.url_edit.text().strip()
        if not text:
            self._log("剪贴板里没有抖音链接，输入框也是空的", "warn")
            self._set_status("没有链接", "#f97316")
            return
        if not self.ck_path.text().strip():
            self._log("未选择 Cookie 文件，解析可能失败（点「安装」查看获取方法）", "warn")

        self._auto_dl = True          # 解析成功即自动下载
        self._parse(text)

    def _parse(self, url_text=None):
        if not isinstance(url_text, str) or not url_text.strip():
            url_text = self.url_edit.text()
        url_text = url_text.strip()
        if not url_text:
            self._log("请先粘贴视频链接", "warn"); return

        self.btn_go.setEnabled(False)
        self.btn_dl_sel.setEnabled(False)
        self._clear_cards()
        self.progress.setValue(0)
        self._set_status("解析中…", "#f97316")
        self._log("开始解析…")

        self._parse_worker = ParseWorker(url_text, self.ck_path.text().strip())
        self._parse_worker.ok.connect(self._on_parse_ok)
        self._parse_worker.err.connect(self._on_parse_err)
        self._parse_worker.log.connect(self._log)
        self._parse_worker.start()

    def _on_parse_ok(self, item, media):
        self._video_info = item
        self.btn_go.setEnabled(True)
        self.btn_dl_sel.setEnabled(True)
        self._set_status("解析成功 ✓", "#22c55e")
        self._fill_cards(media)

        if self._auto_dl:
            self._auto_dl = False
            items = [c.item for c in self._cards if c.is_checked()]
            if not items and self._cards:      # 默认没勾中时，兜底下载第一项
                items = [self._cards[0].item]
            self._log("自动开始下载…", "ok")
            self._start_download(items)

    def _on_parse_err(self, msg):
        self._auto_dl = False
        self.btn_go.setEnabled(True)
        self.btn_dl_sel.setEnabled(True)
        self._set_status("解析失败 ✗", "#ef4444")
        self._log("━" * 40, "err")
        for line in msg.split("\n"):
            if line.strip(): self._log(f"  {line.strip()}", "err")
        self._log("━" * 40, "err")

    # ── 媒体卡片 ──────────────────────────────────────────────────────────────

    def _make_empty_card(self):
        """占位空卡：尺寸与真实媒体卡片一致，无外框，仅提示文字。"""
        card = QFrame()
        card.setObjectName("EmptyCard")
        card.setFixedSize(MediaCard.THUMB_W, MediaCard.CARD_H)
        card.setStyleSheet(
            "QFrame#EmptyCard{background:transparent;border:none;}")
        v = QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        lbl = QLabel("解析后显示媒体")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(False)
        lbl.setStyleSheet(
            f"color:{tk('text_faint')};font-size:12px;"
            f"background:transparent;border:none;")
        v.addWidget(lbl)
        return card

    def _clear_card_layout(self):
        """移除卡片布局内所有子项（含 stretch）"""
        while self._card_layout.count():
            it = self._card_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _show_empty_card(self):
        """媒体区放一张占位空卡（布局结构与 _fill_cards 完全相同：卡片 + 弹簧）"""
        for c in self._cards:
            c.deleteLater()
        self._cards.clear()
        self._clear_card_layout()
        self._empty_card = self._make_empty_card()
        self._card_layout.addWidget(self._empty_card)
        self._card_layout.addStretch(1)

    def _fill_cards(self, items):
        # 清掉占位空卡与旧卡片
        for c in self._cards:
            c.deleteLater()
        self._cards.clear()
        self._clear_card_layout()
        self._empty_card = None

        self.btn_all.setVisible(True)
        self.btn_none.setVisible(True)
        self.btn_dl_sel.setVisible(True)
        for item in items:
            card = MediaCard(item)
            self._cards.append(card)
            self._card_layout.addWidget(card)
        self._card_layout.addStretch(1)
        self._log(f"显示 {len(items)} 个媒体项", "ok")

    def _clear_cards(self):
        self.btn_all.setVisible(False)
        self.btn_none.setVisible(False)
        self.btn_dl_sel.setVisible(False)
        self._show_empty_card()

    def _select_all(self):
        for c in self._cards: c.chk.setChecked(True)

    def _deselect_all(self):
        for c in self._cards: c.chk.setChecked(False)

    # ── 保存目录 ──────────────────────────────────────────────────────────────

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录",
                                             self.save_edit.text())
        if d: self.save_edit.setText(d)

    # ── 下载 ──────────────────────────────────────────────────────────────────

    def _download_selected(self):
        """「选中下载」：只下载当前勾选的媒体卡"""
        self._start_download([c.item for c in self._cards if c.is_checked()])

    def _start_download(self, selected):
        if not selected:
            self._log("请至少勾选一项媒体后再下载", "warn")
            self._set_status("未选中媒体", "#f97316"); return
        save_dir = self.save_edit.text().strip()
        if not save_dir:
            self._log("请先设置保存位置", "warn"); return
        try:
            os.makedirs(save_dir, exist_ok=True)
        except Exception as e:
            self._log(f"保存目录不可用: {e}", "err")
            self._set_status("目录不可用 ✗", "#ef4444"); return
        self._cancel_flag[0] = False
        self.btn_go.setEnabled(False)
        self.btn_dl_sel.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self._set_status("下载中…", "#f97316")

        vi          = self._video_info or {}
        author      = vi.get("author", {}).get("nickname", "未知作者") if isinstance(vi.get("author"), dict) else "未知作者"
        desc        = vi.get("desc", "无标题")
        create_time = vi.get("create_time", 0)

        self._dl_worker = DownloadWorker(
            selected, author, desc, create_time, save_dir, self._cancel_flag,
            video_info=self._video_info
        )
        self._dl_worker.progress.connect(self.progress.setValue)
        self._dl_worker.log.connect(self._log)
        self._dl_worker.done.connect(self._on_dl_done)
        self._dl_worker.cancelled.connect(self._on_dl_cancel)
        self._dl_worker.start()

    def _on_dl_done(self, save_dir):
        self._set_status("下载完成 ✓", "#22c55e")
        self._log(f"所有文件已保存至: {save_dir}", "ok")
        self._reset_btns()

    def _on_dl_cancel(self):
        self._set_status("已取消")
        self._reset_btns()

    def _reset_btns(self):
        self.btn_go.setEnabled(True)
        self.btn_dl_sel.setEnabled(True)
        self.btn_cancel.setEnabled(False)
