// background.js — MV3 service worker
const SUBDIR = "WebImageSaver";   // 下载目录下的子文件夹
let LAST_FILENAME = null;          // 中文注释：缓存本次期望文件名（含子目录），用于强制覆盖浏览器默认名

// [强制放入子目录] —— 只对“本扩展发起”的下载生效
function _basename(p) { return (p || "").split(/[\/\\]/).pop(); }
function _sanitize(n) { return String(n || "image").replace(/[\\/:*?"<>|]/g, "_").trim(); }

// 中文注释：统一把下载文件放进子目录；若已设置期望文件名，则以我们为准
chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
    // 只处理本扩展发起的下载
    if (item.byExtensionId !== chrome.runtime.id) return;

    // ✅ 优先使用我们预先缓存的“期望文件名”（含子目录），避免被浏览器改成“下载.jpg”
    if (LAST_FILENAME) {
        const want = LAST_FILENAME;
        LAST_FILENAME = null; // 只生效一次，避免串场
        return suggest({ filename: want, conflictAction: "uniquify" });
    }

    // 否则：强制进子目录，并清洗名字
    const raw = _basename(item.filename || item.finalUrl || "image");
    const name = _sanitize(raw);
    suggest({ filename: `${SUBDIR}/${name}`, conflictAction: "uniquify" });
});

// 生成安全文件名（去非法字符/去扩展名）
function makeSafeBase(name) {
    return String(name || "image").replace(/[\\/:*?"<>|]/g, "_").replace(/\s+/g, " ").trim();
}

// 从 URL 或候选名里提取【基础名+扩展名】
function deriveNameAndExt(info) {
    const url = info?.url || "";
    // 1) 先取 URL 最后一段作为候选
    const m = url.match(/\/([^\/?#]+)(?:\?|#|$)/);
    let base = m ? m[1] : (info?.filename || "image");
    // 2) 拆出扩展名（不区分大小写）
    const extMatch = base.match(/\.(png|jpe?g|webp|gif|bmp|tiff|svg|avif|ico)$/i);
    const ext = (extMatch ? extMatch[1] : null) || extFromUrl(url, info?.filename);
    // 3) 清理基础名（移除扩展）
    base = base.replace(/\.(png|jpe?g|webp|gif|bmp|tiff|svg|avif|ico)$/i, "");
    return { base: makeSafeBase(base), ext };
}

function extFromUrl(u, fallback) {
  const pick = (s) => {
    if (!s) return null;
    const m = String(s).toLowerCase().match(/\.(png|jpe?g|webp|gif|bmp|tiff|svg|avif|ico)(?:$|\?)/i);
    return m ? m[1] : null;
  };
  return pick(u) || pick(fallback) || "png";
}

async function downloadInfo(info) {
  if (!info) return;
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  // 修复：原来写成 w.getHours() 导致 ReferenceError，直接把 w 改成 now
  const ts = `${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;

    if (info.kind === "url" && info.url) {
        const { base, ext } = deriveNameAndExt(info);
        const want = `${SUBDIR}/${base}.${ext}`;    // 中文：原名+扩展，带子目录
        LAST_FILENAME = want;                       // ✅ 缓存期望名
        await chrome.downloads.download({
            url: info.url,
            filename: want,                           // 仍然传，双保险
            saveAs: false,
            conflictAction: "uniquify",
        });
        return;
    }

    if (info.kind === "data" && info.dataUrl) {
        const { base, ext } = deriveNameAndExt({ filename: info.filename || "image.png" });
        const want = `${SUBDIR}/${base}.${ext || "png"}`;  // 中文：按传入文件名还原扩展
        LAST_FILENAME = want;                               // ✅ 缓存期望名
        await chrome.downloads.download({
            url: info.dataUrl,
            filename: want,                                   // 仍然传，双保险
            saveAs: false,
            conflictAction: "uniquify",
        });
        return;
    }

}

// content.js 主动发送保存请求（数字区+ / F5 / F8 会触发）
chrome.runtime.onMessage.addListener((msg, _sender, _resp) => {
  if (msg && msg.type === "SAVE_INFO" && msg.info) downloadInfo(msg.info);
});

// Ctrl+Shift+7：manifest 的 commands
async function saveHoverImageViaCommand() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !tab.id) return;
  const url = tab.url || "";
  if (/^(chrome|edge|about|chrome-extension|chrome-search|devtools|view-source):/i.test(url)) return;

  // 确保 content.js 已注入
  try { await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] }); } catch {}

  try {
    const info = await chrome.tabs.sendMessage(tab.id, { type: "GET_HOVER_IMAGE" });
    await downloadInfo(info);
  } catch {}
}

chrome.commands?.onCommand?.addListener((cmd) => {
  if (cmd === "save-hover-image") saveHoverImageViaCommand();
});

// ===== [兜底] Alt+1 在“整页图片(image document)”时，直接下载当前标签页 URL =====

// 判断当前标签页是否是 image document（整页只显示图片）
async function __isImageDocument(tabId) {
    try {
        const [{ result }] = await chrome.scripting.executeScript({
            target: { tabId },
            world: "MAIN",
            func: () => {
                try {
                    const ct = (document.contentType || "").toLowerCase();
                    if (ct.startsWith("image/")) return true;
                } catch (e) { }
                try {
                    const b = document.body;
                    return !!(b && b.childElementCount === 1 && b.firstElementChild.tagName === "IMG");
                } catch (e) { return false; }
            },
        });
        return !!result;
    } catch (e) {
        return false;
    }
}

// ===== [兜底] Alt+1 在“整页图片(image document)”时，直接从页面拿像素再下载 =====

// 判断当前标签页是否是 image document（整页只显示图片）
async function __isImageDocument(tabId) {
    try {
        const [{ result }] = await chrome.scripting.executeScript({
            target: { tabId },
            world: "MAIN",
            func: () => {
                try {
                    const ct = (document.contentType || "").toLowerCase();
                    if (ct.startsWith("image/")) return true;
                } catch (e) { }
                try {
                    const b = document.body;
                    return !!(b && b.childElementCount === 1 && b.firstElementChild.tagName === "IMG");
                } catch (e) { return false; }
            },
        });
        return !!result;
    } catch (e) {
        return false;
    }
}

// 在图片页中把当前 IMG 画到 canvas，返回 {dataUrl, name, mime}
async function __grabImageDocAsDataURL(tabId) {
    const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId },
        world: "MAIN",
        func: () => {
            return new Promise((resolve) => {
                try {
                    // 1) 优先从页面已有 <img> 取像素；否则临时创建 Image 再绘制到 canvas
                    const imgEl = document.body?.firstElementChild?.tagName === "IMG"
                        ? document.body.firstElementChild
                        : null;
                    const src = imgEl ? (imgEl.currentSrc || imgEl.src) : location.href;

                    const onload = (img) => {
                        const w = img.naturalWidth || img.width || 0;
                        const h = img.naturalHeight || img.height || 0;
                        if (!w || !h) return resolve(null);

                        const canvas = document.createElement("canvas");
                        canvas.width = w;
                        canvas.height = h;
                        const ctx = canvas.getContext("2d");
                        ctx.drawImage(img, 0, 0);

                        // 2) 根据地址栏 location.href 推断“原文件名”（保证还原站点给的名字）
                        //    a) 先取路径最后一段；b) URL 解码；c) 去非法字符；d) 若没扩展名则按 MIME 补一个
                        let finalName = "image";
                        let mime = "image/png";
                        try {
                            // 尽量按原扩展名推测 MIME
                            const srcExt = String(src).toLowerCase().match(/\.(jpe?g|png|webp|gif|bmp|tiff|avif|ico|svg)$/i);
                            if (srcExt) {
                                const map = {
                                    "jpg": "image/jpeg", "jpeg": "image/jpeg",
                                    "png": "image/png", "webp": "image/webp",
                                    "gif": "image/gif", "bmp": "image/bmp",
                                    "tiff": "image/tiff", "avif": "image/avif",
                                    "ico": "image/x-icon", "svg": "image/svg+xml"
                                };
                                mime = map[srcExt[1]] || mime;
                            }
                            // —— 用地址栏来复原原名（关键点）——
                            const u = new URL(location.href);
                            let base = decodeURIComponent(u.pathname.split("/").pop() || "image");
                            base = base.replace(/[\\/:*?"<>|]/g, "_").trim();
                            if (!/\.(jpe?g|png|webp|gif|bmp|tiff|avif|ico|svg)$/i.test(base)) {
                                // 若没有扩展名，按 mime 补一个（jpeg 统一用 jpg）
                                const extFromMime = (mime.split("/")[1] || "png").replace("jpeg", "jpg");
                                base += "." + extFromMime;
                            }
                            finalName = base;
                        } catch (e) { }

                        const dataUrl = canvas.toDataURL(mime);
                        resolve({ dataUrl, name: finalName, mime });
                    };

                    if (imgEl) {
                        if (imgEl.complete && imgEl.naturalWidth) return onload(imgEl);
                        imgEl.addEventListener("load", () => onload(imgEl), { once: true });
                        imgEl.addEventListener("error", () => resolve(null), { once: true });
                    } else {
                        const tmp = new Image();
                        tmp.src = src;                  // 同源图片页允许绘制到 canvas
                        tmp.onload = () => onload(tmp);
                        tmp.onerror = () => resolve(null);
                        document.body?.appendChild(tmp);
                    }
                } catch (e) {
                    resolve(null);
                }
            });
        },
    });
    return result || null;
}

// Alt+1 命令的兜底：先判断是否图片页；是则用 dataURL 下载；否则走原有 content.js 流程
chrome.commands.onCommand.addListener(async (cmd) => {
    if (cmd !== "save-hover-image") return;

    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || !tab.id || !tab.url) return;

    if (await __isImageDocument(tab.id)) {
        const grabbed = await __grabImageDocAsDataURL(tab.id);
        if (!grabbed || !grabbed.dataUrl) return;

        const ts = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
        // 交给 downloads.download；onDeterminingFilename 会强制进 WebImageSaver 子目录
        await chrome.downloads.download({
            url: grabbed.dataUrl,                                  // 用 dataURL，避免 Referer/防盗链
            filename: grabbed.name,               // 使用原始文件名；子目录由 onDeterminingFilename 统一加
            conflictAction: "uniquify",
            saveAs: false,
        });
        return; // 已处理
    }
    // 非图片页：保持现有流程（content.js GET_HOVER_IMAGE）
});
