// background.js — 响应 Alt+1 命令，找图片并下载
const SUBDIR = "WebImageSaver";

function sanitize(s) {
    return String(s || "image").replace(/[\\/:*?"<>|]/g, "_").trim();
}
function extFrom(url) {
    const m = String(url || "").match(/\.(png|jpe?g|webp|gif|bmp|tiff|avif|ico)(?:$|\?)/i);
    return m ? m[1].replace("jpeg","jpg") : "png";
}
function nameFrom(url, fallback) {
    const m = String(url || "").match(/\/([^/?#]+)(?:\?|#|$)/);
    const raw = m ? m[1] : (fallback || "image");
    const ext = extFrom(raw) || extFrom(url);
    const base = sanitize(raw.replace(/\.(png|jpe?g|webp|gif|bmp|tiff|avif|ico)$/i, ""));
    return `${base}.${ext}`;
}

async function saveInfo(info) {
    if (!info) return;
    if (info.kind === "url" && info.url) {
        await chrome.downloads.download({
            url: info.url,
            filename: `${SUBDIR}/${nameFrom(info.url, info.filename)}`,
            saveAs: false,
            conflictAction: "uniquify",
        });
    } else if (info.kind === "data" && info.dataUrl) {
        const name = sanitize(info.filename || "image").replace(/\.[^.]+$/, "") || "image";
        await chrome.downloads.download({
            url: info.dataUrl,
            filename: `${SUBDIR}/${name}.png`,
            saveAs: false,
            conflictAction: "uniquify",
        });
    }
}

// Alt+1 由 manifest commands 触发，background 负责找图并保存
chrome.commands.onCommand.addListener(async (cmd) => {
    if (cmd !== "save-hover-image") return;

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab?.url) return;
    if (/^(chrome|edge|about|chrome-extension|devtools):/i.test(tab.url)) return;

    // 注入 content.js（处理插件安装后未刷新的标签页）
    try {
        await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    } catch {}

    // 向 content.js 取光标下的图片
    try {
        const info = await chrome.tabs.sendMessage(tab.id, { type: "GET_HOVER_IMAGE" });
        await saveInfo(info);
    } catch {}
});

// WebSocket：接收 Python 侧键触发
// Python 的 img_saver.py 开一个 WS Server，插件连上来，
// 侧键按下时 Python 发 "TRIGGER"，background 收到后执行保存
const WS_URL = "ws://127.0.0.1:19876";
const PROBE_URL = "http://127.0.0.1:19876";
const RETRY_INTERVAL = 5000;

async function handleTrigger() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab?.url) return;
    if (/^(chrome|edge|about|chrome-extension|devtools):/i.test(tab.url)) return;
    try {
        await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    } catch {}
    try {
        const info = await chrome.tabs.sendMessage(tab.id, { type: "GET_HOVER_IMAGE" });
        await saveInfo(info);
    } catch {}
}

async function connectWS() {
    // 先用 fetch 探测端口是否开着，失败不会被 Chrome 记录为扩展错误
    try {
        await fetch(PROBE_URL, { signal: AbortSignal.timeout(1000) });
    } catch {
        // Python 程序未启动，静默等待重试
        setTimeout(connectWS, RETRY_INTERVAL);
        return;
    }

    // 探测到端口再建立 WS 连接
    try {
        const ws = new WebSocket(WS_URL);
        ws.onmessage = e => { if (e.data === "TRIGGER") handleTrigger(); };
        ws.onclose   = () => setTimeout(connectWS, RETRY_INTERVAL);
        ws.onerror   = () => ws.close();
    } catch {
        setTimeout(connectWS, RETRY_INTERVAL);
    }
}

connectWS();
