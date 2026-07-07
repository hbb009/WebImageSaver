# pages/page_douyin.py
# 抖音无水印下载器 —— 嵌入桌面助手 PyQt5 版
# 布局：第1排Cookie / 第2排链接 / 第3排媒体 / 第4排保存路径+下载 / 进度+日志
# 移除：解析步骤追踪面板
# v8 移植：五条解析线路 / 图文帖HTML解析 / 内部重试 / 并发下载 / 文件校验 / 文件名加日期

import warnings, urllib3
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

import os, re, sys, json, time, threading, uuid, gzip as gzip_mod
import http.cookiejar, ssl, datetime
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui  import QFont, QColor, QPixmap, QImage
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

from styles.page_douyin import PAGE_QSS, GB_STYLE as _GB_STYLE, DIVIDER_QSS

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
        # 此时无法预判，保守返回 video，等线路D/E 纠正
    return "video"


def refine_content_type(item: dict, current_type: str) -> str:
    """拿到 item 后，根据 aweme_type 纠正预判类型"""
    if item and item.get("aweme_type") == 68:
        return "note"
    return current_type


def load_cookies(path: str):
    cj = http.cookiejar.MozillaCookieJar()
    cj.load(path, ignore_discard=True, ignore_expires=True)
    d = {c.name: c.value for c in cj if "douyin.com" in (c.domain or "")}
    return "; ".join(f"{k}={v}" for k, v in d.items()), d


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


# ── 五条解析线路 ──────────────────────────────────────────────────────────────

def line_a_web_requests(aweme_id, cookie_str, s_v_web_id, page_type, log_cb=None):
    """线路A：Web API + requests（完整浏览器参数，多端点）"""
    hdrs = _web_headers(aweme_id, cookie_str, page_type)
    last_err = None
    for style in ("full", "slim", "legacy"):
        url = _web_api_url(aweme_id, s_v_web_id, style)
        try:
            final_url, body, status, length = _retry_get(_get, url, hdrs)
            if log_cb:
                log_cb(f"  A/{style} HTTP={status} len={length}B")
            data = _parse_json(body)
            if log_cb:
                log_cb(f"  A/{style} JSON keys={list(data.keys())}")
            return _extract_item(data)
        except ValueError as e:
            last_err = e
            if log_cb:
                log_cb(f"  A/{style} ValueError: {e}")
            if style == "legacy":
                raise
        except Exception as e:
            last_err = e
            if log_cb:
                log_cb(f"  A/{style} Error: {e}")
            if style == "legacy":
                raise
    raise last_err or ValueError("线路A 全部端点失败")


def line_b_web_urllib(aweme_id, cookie_str, s_v_web_id, page_type, log_cb=None):
    """线路B：Web API + urllib（系统 TLS，不同 JA3 指纹）"""
    hdrs = _web_headers(aweme_id, cookie_str, page_type)
    last_err = None
    for style in ("full", "slim"):
        url = _web_api_url(aweme_id, s_v_web_id, style)
        try:
            final_url, body, status, length = _retry_get(_get_urllib, url, hdrs)
            if log_cb:
                log_cb(f"  B/{style} HTTP={status} len={length}B")
            data = _parse_json(body)
            if log_cb:
                log_cb(f"  B/{style} JSON keys={list(data.keys())}")
            return _extract_item(data)
        except ValueError as e:
            last_err = e
            if log_cb:
                log_cb(f"  B/{style} ValueError: {e}")
            if style == "slim":
                raise
        except Exception as e:
            last_err = e
            if log_cb:
                log_cb(f"  B/{style} Error: {e}")
            if style == "slim":
                raise
    raise last_err or ValueError("线路B 全部端点失败")


def line_c_iesdouyin(aweme_id, cookie_str, s_v_web_id, page_type, log_cb=None):
    """线路C：iesdouyin API（完全不同的接口）"""
    api = (f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/"
           f"?item_ids={aweme_id}&reflow_source=reflow_page")
    ies_path = "note" if page_type == "note" else "video"
    hdrs = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Referer": f"https://www.iesdouyin.com/share/{ies_path}/{aweme_id}/",
        "Cookie": cookie_str,
    }
    final_url, body, status, length = _retry_get(_get, api, hdrs)
    if log_cb:
        log_cb(f"  C HTTP={status} len={length}B")
    data = _parse_json(body)
    if log_cb:
        log_cb(f"  C JSON keys={list(data.keys())} item_list_len={len(data.get('item_list',[]))}")
    items = data.get("item_list", [])
    if not items:
        raise ValueError(f"item_list 为空 (返回 keys={list(data.keys())})")
    return items[0]


def line_d_mobile(aweme_id, cookie_str, log_cb=None):
    """线路D：Mobile feed API，找不到时回退单条查询接口"""
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
            # （普通视频走线路E时也需要能解析）

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
                    for img_item in images_arr:
                        url_list = img_item.get('urlList', [])
                        video_obj = img_item.get('video') or {}
                        duration = video_obj.get('duration', 0) or 0
                        play_addr = video_obj.get('playAddr', []) or []
                        w = img_item.get('width', 0)
                        h = img_item.get('height', 0)
                        best_img = next(
                            (u for u in url_list if 'jpeg' in u.lower() and 'water' not in u),
                            url_list[0] if url_list else ""
                        )
                        if duration > 0 and play_addr:
                            first_src = play_addr[0].get('src', '') if isinstance(play_addr[0], dict) else str(play_addr[0])
                            video_items.append({
                                "url": first_src,
                                "duration": duration,
                                "thumb": best_img,
                                "width": w, "height": h,
                            })
                        elif url_list:
                            images_data.append({"url_list": url_list, "width": w, "height": h})
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


def line_e_note(aweme_id, cookie_str, s_v_web_id, log_cb=None):
    """
    线路E：图文帖专用线路。
    E1. /aweme/v1/web/note/item_list/?aweme_ids=[xxx]
    E2. /aweme/v2/web/note/aweme/?aweme_id=xxx
    E3. HTML页面解析 douyin.com/note/xxx
    E4. iesdouyin.com/share/note/xxx/
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

    # E1：图文专用 REST 接口
    e1_urls = [
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
    for api_url in e1_urls:
        for get_fn in (_get_urllib, _get):
            fn_name = "urllib" if get_fn == _get_urllib else "requests"
            try:
                final_url, body, status, length = get_fn(api_url, base_hdrs)
                errors.append(f"E1/{fn_name} HTTP={status} len={length}B url=...{api_url[-35:]}")
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
                errors.append(f"E1/{fn_name} ...{api_url[-30:]}: {str(e)[:60]}")

    # E2：HTML 页面解析
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
                errors.append(f"E2/{fn_name} HTML HTTP={status} len={length}B url={page_url[-30:]}")
                parse_debug = []
                item = _parse_note_from_html(html, debug_errors=parse_debug)
                for pd in parse_debug:
                    errors.append(pd)
                if item:
                    errors.append(f"  → HTML解析成功! aweme_type={item.get('aweme_type')} images={len(item.get('images') or [])}")
                    return item
            except Exception as e:
                errors.append(f"E2/{fn_name} {page_url[-30:]}: {str(e)[:60]}")

    if log_cb:
        for e_msg in errors:
            log_cb(e_msg)
    raise ValueError(
        "线路E（图文专用）全部失败。详细调试信息：\n  " +
        "\n  ".join(errors))


# ── 媒体提取 ──────────────────────────────────────────────────────────────────

class MediaItem:
    __slots__ = ("kind", "label", "url", "ext", "thumb_url", "index", "default_checked")

    def __init__(self, kind, label, url, ext, thumb_url="", index=0, default_checked=True):
        self.kind            = kind
        self.label           = label
        self.url             = url
        self.ext             = ext
        self.thumb_url       = thumb_url
        self.index           = index
        self.default_checked = default_checked


def parse_media(item: dict) -> list:
    results = []
    video        = item.get("video", {})
    music        = item.get("music", {})
    images       = item.get("images") or []
    aweme_type   = item.get("aweme_type", 0)
    video_frames = item.get("_video_frames") or []

    play_urls = (
        video.get("play_addr", {}).get("url_list", []) or
        video.get("download_addr", {}).get("url_list", []) or
        video.get("play_addr_h264", {}).get("url_list", [])
    )
    cover_urls = (
        video.get("origin_cover", {}).get("url_list", []) or
        video.get("cover", {}).get("url_list", [])
    )
    cover_url = cover_urls[0] if cover_urls else ""

    # 视频帧（图文帖中每张图附带的动态视频）
    if video_frames:
        for j, vf in enumerate(video_frames):
            results.append(MediaItem(
                "video",
                f"视频 {j+1}（无水印 MP4）",
                vf["url"],
                ".mp4",
                vf.get("thumb", ""),
                j, True
            ))
    elif play_urls:
        label = "幻灯片合成视频（MP4）" if aweme_type == 68 else "视频（无水印 MP4）"
        results.append(MediaItem("video", label, play_urls[0], ".mp4",
                                 cover_url, 0, True))

    # 图片
    for i, img in enumerate(images):
        url_list = img.get("url_list", [])
        if not url_list:
            continue
        results.append(MediaItem(
            "image", f"图片 {i+1}",
            url_list[0], ".jpg",
            url_list[-1] if len(url_list) > 1 else url_list[0],
            i, True
        ))
        # Live Photo 附带视频
        live_urls = img.get("video", {}).get("play_addr", {}).get("url_list", [])
        if live_urls:
            results.append(MediaItem("video", f"图片 {i+1} · Live",
                                     live_urls[0], ".mp4", url_list[0], i, True))

    # 音频（默认不选）
    music_urls = music.get("play_url", {}).get("url_list", [])
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

    return f"[桌面助手][{clean(author, 15)}]{date_str}{clean(desc, 35)}_{clean(suffix, 12)}{ext}"


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

            # 步骤6：五条线路依次尝试
            item = None
            errors = []

            def make_log_cb(name):
                def cb(msg):
                    self._log(f"[{name}] {msg}")
                return cb

            LINES = [
                ("线路A Web+requests", line_a_web_requests,
                 (aweme_id, cookie_str, s_v_web_id, page_type)),
                ("线路B Web+urllib",   line_b_web_urllib,
                 (aweme_id, cookie_str, s_v_web_id, page_type)),
                ("线路C iesdouyin",    line_c_iesdouyin,
                 (aweme_id, cookie_str, s_v_web_id, page_type)),
                ("线路D Mobile",       line_d_mobile,
                 (aweme_id, cookie_str)),
            ]

            for name, fn, args in LINES:
                try:
                    self._log(f"尝试 {name}…")
                    item = fn(*args, log_cb=make_log_cb(name))
                    self._log(f"{name} 成功 ✓", "ok")
                    break
                except Exception as e:
                    errors.append(f"{name}: {e}")
                    self._log(f"{name} 失败: {e}", "warn")

            # 步骤6e：线路E（图文专用）
            # 拿到 item 后用实际 aweme_type 纠正预判类型
            if item:
                page_type = refine_content_type(item, page_type)

            need_e = False
            if item is None:
                need_e = True
                reason = "全线路失败，补试图文专用线路E"
            elif item.get("aweme_type") == 68 and not (item.get("images") or []):
                need_e = True
                reason = "aweme_type=68 但 images 为空，用 /note/ Referer 重试"

            if need_e:
                self._log(f"线路E 图文专用：{reason}", "warn")
                try:
                    candidate = line_e_note(aweme_id, cookie_str, s_v_web_id,
                                            log_cb=make_log_cb("线路E"))
                    if candidate:
                        item = candidate
                        img_count = len(item.get("images") or [])
                        self._log(f"线路E ✓  图片数量: {img_count}", "ok")
                except Exception as e:
                    self._log(f"线路E 失败: {e}", "err")

            if not item:
                raise RuntimeError(
                    "所有解析线路均失败：\n" +
                    "\n".join(f"  · {e}" for e in errors) +
                    "\n\n可能原因：\n"
                    "  · Cookie 已过期（重新导出 cookies.txt）\n"
                    "  · 视频已删除或设为私密\n"
                    "  · 网络连接问题")

            # 步骤7：提取媒体资源
            media = parse_media(item)
            aweme_type = item.get("aweme_type", 0)
            type_name  = {0: "普通视频", 68: "图文帖子"}.get(aweme_type, f"类型{aweme_type}")
            img_n = len([m for m in media if m.kind == "image"])
            vid_n = len([m for m in media if m.kind == "video"])
            self._log(
                f"提取完成：{type_name}，共 {len(media)} 项"
                f"（{vid_n}视频/{img_n}图/{len(media)-vid_n-img_n}音频）", "ok")
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
        ref_path = "note" if aweme_type_for_ref == 68 else "video"
        ref_url = (f"https://www.douyin.com/{ref_path}/{aweme_id_for_ref}"
                   if aweme_id_for_ref else "https://www.douyin.com/")
        hdrs   = {"User-Agent": UA_MOBILE, "Referer": ref_url}
        total  = len(self._items)
        done_count = [0]
        lock   = threading.Lock()

        def download_one(item):
            if self._cancel[0]:
                return False, item, "已取消"

            filename = make_filename(
                self._author, self._desc, self._create_time,
                item.label, item.ext
            )
            path = os.path.join(self._save_dir, filename)
            base, ext = os.path.splitext(path)
            n = 1
            while os.path.exists(path):
                path = f"{base}_{n}{ext}"; n += 1

            try:
                if HAS_REQUESTS:
                    r = req_lib.get(item.url, headers=hdrs, stream=True,
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
                    actual_size = downloaded
                else:
                    import urllib.request
                    req = urllib.request.Request(item.url, headers=hdrs)
                    with urllib.request.urlopen(req, timeout=30, context=CTX) as resp:
                        data = resp.read()
                    with open(path, "wb") as f:
                        f.write(data)
                    actual_size = len(data)

                # 文件大小校验
                if actual_size < MIN_FILE_BYTES:
                    os.remove(path)
                    return False, item, f"文件过小（{actual_size}B），可能已损坏"

                with lock:
                    done_count[0] += 1
                    pct = int(done_count[0] / total * 100)
                    self.progress.emit(pct)

                return True, item, path

            except InterruptedError:
                if os.path.exists(path): os.remove(path)
                return False, item, "已取消"
            except Exception as e:
                if os.path.exists(path): os.remove(path)
                return False, item, str(e)

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

_KIND_COLOR = {
    "video": "#0f3460",
    "image": "#0d3b2e",
    "audio": "#2d1b4e",
}
_KIND_ICON  = {"video": "🎬", "image": "🖼", "audio": "🎵"}


class MediaCard(QFrame):
    THUMB_W = 110
    THUMB_H = 90

    def __init__(self, item: MediaItem, parent=None):
        super().__init__(parent)
        self.item = item
        self._checked = item.default_checked
        bg = _KIND_COLOR.get(item.kind, "#0f3460")
        self.setStyleSheet(f"""
            QFrame{{
                background:{bg};
                border:2px solid {'#1a4a7a' if self._checked else '#334155'};
                border-radius:6px;
            }}
        """)
        self.setFixedSize(self.THUMB_W + 16, self.THUMB_H + 56)
        self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # 缩略图占位
        self.thumb = QLabel(_KIND_ICON.get(item.kind, "?"))
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setFixedSize(self.THUMB_W, self.THUMB_H)
        self.thumb.setStyleSheet("font-size:28px; background:transparent;")
        lay.addWidget(self.thumb)

        # 标签行
        lbl = QLabel(item.label)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#f1f5f9; font-size:11px; background:transparent;")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)

        # 勾选框
        self.chk = QCheckBox("选择")
        self.chk.setChecked(self._checked)
        self.chk.setStyleSheet("color:#94a3b8; font-size:10px; background:transparent;")
        self.chk.stateChanged.connect(self._on_chk)
        lay.addWidget(self.chk, 0, Qt.AlignCenter)

        # 加载缩略图
        if item.thumb_url:
            self._load_thumb(item.thumb_url)

    def _on_chk(self, state):
        self._checked = bool(state)
        bg = _KIND_COLOR.get(self.item.kind, "#0f3460")
        border = "#1a4a7a" if self._checked else "#334155"
        self.setStyleSheet(f"QFrame{{background:{bg};border:2px solid {border};border-radius:6px;}}")

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

def _hline():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(DIVIDER_QSS)
    return f


class PageDouyin(QWidget):
    def __init__(self):
        super().__init__()
        self._video_info  = None
        self._media_items = []
        self._cards       = []
        self._cancel_flag = [False]
        self._parse_worker = None
        self._dl_worker    = None

        self.setStyleSheet(PAGE_QSS)

        GB_STYLE = _GB_STYLE

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # ══ 顶部：左侧卡片（解析配置 Cookie+链接）& 右侧卡片（下载设置 保存+下载） ══
        #    操作顺序从左到右：先在左侧解析，再到右侧设置保存并下载
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # ━━ 下载设置卡片（构建在前，显示在右侧）：保存位置 + 下载按钮/进度/状态 ━━
        gb_dl = QGroupBox("下载设置")
        gb_dl.setStyleSheet(GB_STYLE)
        vl = QVBoxLayout(gb_dl)
        vl.setSpacing(7)
        vl.setContentsMargins(6, 4, 6, 6)

        # 保存位置
        lbl_save = QLabel("保存位置")
        lbl_save.setObjectName("SecTitle")
        vl.addWidget(lbl_save)
        save_row = QHBoxLayout()
        save_row.setSpacing(6)
        self.save_edit = QLineEdit(os.path.expanduser("~/Downloads").replace("\\", "/"))
        save_row.addWidget(self.save_edit, 1)
        btn_browse = QPushButton("浏览")
        btn_browse.setObjectName("BtnSmall")
        btn_browse.clicked.connect(self._choose_dir)
        save_row.addWidget(btn_browse)
        btn_open = QPushButton("打开目录")
        btn_open.setObjectName("BtnSmall")
        btn_open.clicked.connect(lambda: self._open_dir(self.save_edit.text()))
        save_row.addWidget(btn_open)
        vl.addLayout(save_row)

        # 分隔
        vl.addSpacing(2)

        # 下载按钮行
        dl_btn_row = QHBoxLayout()
        dl_btn_row.setSpacing(6)
        self.btn_dl = QPushButton("⬇  开始下载")
        self.btn_dl.setObjectName("BtnDownload")
        self.btn_dl.setEnabled(False)
        self.btn_dl.clicked.connect(self._download)
        dl_btn_row.addWidget(self.btn_dl, 1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(lambda: self._cancel_flag.__setitem__(0, True))
        dl_btn_row.addWidget(self.btn_cancel)
        vl.addLayout(dl_btn_row)

        # 进度条（百分比文字）
        self.progress = QProgressBar()
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        vl.addWidget(self.progress)

        # 状态提示
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("StatusLbl")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        vl.addWidget(self.status_lbl)

        # ━━ 解析配置卡片（构建在后，显示在左侧）：Cookie + 链接输入 ━━━━━━━━━━━━
        gb_parse = QGroupBox("解析配置")
        gb_parse.setStyleSheet(GB_STYLE)
        vr = QVBoxLayout(gb_parse)
        vr.setSpacing(7)
        vr.setContentsMargins(6, 4, 6, 6)

        # Cookie
        lbl_ck = QLabel("Cookie 文件（必填，Netscape .txt 格式）")
        lbl_ck.setObjectName("SecTitle")
        vr.addWidget(lbl_ck)
        ck_row = QHBoxLayout()
        ck_row.setSpacing(6)
        self.ck_path = QLineEdit()
        self.ck_path.setPlaceholderText("cookies.txt 路径…")
        self.ck_path.setReadOnly(True)          # 防止误改，只能通过「选择文件」写入
        self.ck_path.textChanged.connect(self._on_cookie_change)
        ck_row.addWidget(self.ck_path, 1)
        btn_ck = QPushButton("选择文件")
        btn_ck.setObjectName("BtnSmall")
        btn_ck.clicked.connect(self._pick_cookie)
        ck_row.addWidget(btn_ck)
        btn_ck_help = QPushButton("？")
        btn_ck_help.setObjectName("BtnSmall")
        btn_ck_help.setFixedWidth(32)
        btn_ck_help.clicked.connect(self._cookie_help)
        btn_ck_help.setToolTip(
            "1. Chrome商店安装：Get cookies.txt LOCALLY\n"
            "2. 登录 douyin.com\n"
            "3. 点扩展 → Export → 保存 .txt\n"
            "4. 选择该文件")
        ck_row.addWidget(btn_ck_help)
        vr.addLayout(ck_row)
        self.ck_status = QLabel("")
        self.ck_status.setObjectName("StatusLbl")
        vr.addWidget(self.ck_status)

        # 分隔
        vr.addSpacing(2)

        # 链接输入
        lbl_url = QLabel("粘贴视频链接（支持短链 / 完整链接 / 含链接的分享文字）")
        lbl_url.setObjectName("SecTitle")
        vr.addWidget(lbl_url)
        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://v.douyin.com/xxx/  或  粘贴分享文字")
        self.url_edit.returnPressed.connect(self._parse)
        url_row.addWidget(self.url_edit, 1)
        self.btn_parse = QPushButton("解析")
        self.btn_parse.setObjectName("BtnParse")
        self.btn_parse.clicked.connect(self._parse)
        url_row.addWidget(self.btn_parse)
        vr.addLayout(url_row)

        # 左：解析配置 60%　右：下载设置 40%
        top_row.addWidget(gb_parse, 60)
        top_row.addWidget(gb_dl, 40)

        root.addLayout(top_row)

        # ══ 第3排：媒体卡片区 ═══════════════════════════════════════════════════
        media_head = QHBoxLayout()
        self._sec_label_widget(media_head, "媒体内容（解析后显示）")
        media_head.addStretch(1)
        self.btn_all   = QPushButton("全选")
        self.btn_none  = QPushButton("全不选")
        for b in (self.btn_all, self.btn_none):
            b.setObjectName("BtnSmall")
            b.setVisible(False)
            media_head.addWidget(b)
        self.btn_all.clicked.connect(self._select_all)
        self.btn_none.clicked.connect(self._deselect_all)
        root.addLayout(media_head)

        # 媒体卡片滚动区：始终可见并占用固定高度，
        # 解析前放一张占位空卡，避免解析前后布局高度变化导致下方日志区跳动
        self.card_scroll = QScrollArea()
        self.card_scroll.setWidgetResizable(True)
        self.card_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.card_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.card_scroll.setFixedHeight(MediaCard.THUMB_H + 70)
        card_inner = QWidget()
        self._card_layout = QHBoxLayout(card_inner)
        self._card_layout.setContentsMargins(4, 4, 4, 4)
        self._card_layout.setSpacing(8)
        self.card_scroll.setWidget(card_inner)
        root.addWidget(self.card_scroll)

        # 初始占位空卡
        self._empty_card = None
        self._show_empty_card()

        root.addWidget(_hline())

        # ══ 日志 ═══════════════════════════════════════════════════════════════
        log_head = QHBoxLayout()
        lbl_log = QLabel("运行日志")
        lbl_log.setObjectName("SecTitle")
        log_head.addWidget(lbl_log)
        log_head.addStretch(1)
        btn_clear_log = QPushButton("清屏")
        btn_clear_log.setObjectName("BtnSmall")
        btn_clear_log.setFixedWidth(52)
        btn_clear_log.clicked.connect(lambda: self.log_box.clear())
        log_head.addWidget(btn_clear_log)
        root.addLayout(log_head)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(100)
        root.addWidget(self.log_box, 1)

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
        colors = {"ok": "#22c55e", "err": "#ef4444", "warn": "#f59e0b", "info": "#94a3b8"}
        color  = colors.get(level, "#94a3b8")
        ts     = time.strftime("%H:%M:%S")
        self.log_box.append(
            f'<span style="color:#4a5a7a">[{ts}]</span> '
            f'<span style="color:{color}">{msg}</span>'
        )
        # 每次追加后强制滚到底部，避免悬停在中间位置
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum()
        )

    def _set_status(self, text, color="#94a3b8"):
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"QLabel#StatusLbl{{color:{color}; font-size:12px;}}")

    # ── Cookie ────────────────────────────────────────────────────────────────

    def _pick_cookie(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择 cookies.txt", "",
                                           "Cookie 文件 (*.txt);;所有文件 (*.*)")
        if p:
            # setReadOnly 不阻止程序调用 setText，只阻止用户键盘输入
            self.ck_path.setText(p)

    def _on_cookie_change(self, path):
        if not path or not os.path.isfile(path):
            self.ck_status.setText("")
            return
        try:
            _, d = load_cookies(path)
            has_sid  = "sid_tt" in d or "sessionid" in d
            has_svid = "s_v_web_id" in d
            count    = len(d)
            if has_sid and has_svid:
                msg = f"✅ Cookie 有效（{count} 个字段，含登录态）"
                self.ck_status.setStyleSheet("color:#22c55e;")
            else:
                miss = [k for k in ("sid_tt", "s_v_web_id") if k not in d]
                msg = f"⚠ 缺少字段: {', '.join(miss)}"
                self.ck_status.setStyleSheet("color:#f59e0b;")
            self.ck_status.setText(msg)
        except Exception as e:
            self.ck_status.setText(f"❌ 读取失败: {e}")
            self.ck_status.setStyleSheet("color:#ef4444;")

    def _cookie_help(self):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(self, "如何获取 cookies.txt",
            "1. Chrome 商店安装扩展：Get cookies.txt LOCALLY\n\n"
            "2. Chrome 打开并登录 www.douyin.com\n\n"
            "3. 点扩展图标 → Export → 保存为 .txt 文件\n\n"
            "4. 回到本程序点「选择文件」选中该文件")

    # ── 解析 ──────────────────────────────────────────────────────────────────

    def _parse(self):
        url_text = self.url_edit.text().strip()
        if not url_text:
            self._log("请先粘贴视频链接", "warn"); return
        self.btn_parse.setEnabled(False)
        self.btn_dl.setEnabled(False)
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
        self.btn_parse.setEnabled(True)
        self.btn_dl.setEnabled(True)
        self._set_status("解析成功 ✓", "#22c55e")
        self._fill_cards(media)

    def _on_parse_err(self, msg):
        self.btn_parse.setEnabled(True)
        self._set_status("解析失败 ✗", "#ef4444")
        self._log("━" * 40, "err")
        for line in msg.split("\n"):
            if line.strip(): self._log(f"  {line.strip()}", "err")
        self._log("━" * 40, "err")

    # ── 媒体卡片 ──────────────────────────────────────────────────────────────

    def _make_empty_card(self):
        """占位空卡：尺寸与真实媒体卡片完全一致，
        靠左摆放 + 尾部弹簧，保证解析前后媒体区布局像素级一致，日志区不位移"""
        card = QFrame()
        card.setObjectName("EmptyCard")
        card.setFixedSize(MediaCard.THUMB_W + 16, MediaCard.THUMB_H + 56)
        card.setStyleSheet(
            "QFrame#EmptyCard{background:#0e1a2e;"
            "border:1.5px dashed #334155;border-radius:6px;}"
        )
        v = QVBoxLayout(card)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)
        lbl = QLabel("解析后\n显示媒体")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color:#4a5a7a;font-size:12px;background:transparent;border:none;")
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
        for item in items:
            card = MediaCard(item)
            self._cards.append(card)
            self._card_layout.addWidget(card)
        self._card_layout.addStretch(1)
        self._log(f"显示 {len(items)} 个媒体项", "ok")

    def _clear_cards(self):
        self.btn_all.setVisible(False)
        self.btn_none.setVisible(False)
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

    def _open_dir(self, path):
        if not path: return
        try:
            if sys.platform == "win32": os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess; subprocess.Popen(["open", path])
            else:
                import subprocess; subprocess.Popen(["xdg-open", path])
        except Exception: pass

    # ── 下载 ──────────────────────────────────────────────────────────────────

    def _download(self):
        selected = [c.item for c in self._cards if c.is_checked()]
        if not selected:
            self._log("请至少勾选一项媒体后再下载", "warn"); return
        save_dir = self.save_edit.text().strip()
        if not save_dir:
            self._log("请先选择保存目录", "warn"); return
        os.makedirs(save_dir, exist_ok=True)
        self._cancel_flag[0] = False
        self.btn_dl.setEnabled(False)
        self.btn_parse.setEnabled(False)
        self.btn_cancel.setVisible(True)
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
        self._set_status("已取消", "#94a3b8")
        self._reset_btns()

    def _reset_btns(self):
        self.btn_dl.setEnabled(True)
        self.btn_parse.setEnabled(True)
        self.btn_cancel.setVisible(False)