// background.js — 图片速存（自包含）
// 【关键原则】下载动作绝不依赖与桌面程序的连接。
//   - 连不上程序：照常下载（fail-open），只是无法被程序的开关关掉；
//   - 连上程序且程序说“停用”：才跳过。
// 触发：manifest 里的命令（Alt+1，固定）。
// 保存：下载到「下载目录/WebImageSaver」，由桌面程序按其设置处理。

const STAGING_SUBDIR = "WebImageSaver";
const WS_URL   = "ws://127.0.0.1:19876";
const PING_MS  = 20000;

// 指数退避重连：连不上程序时不再每 4 秒狂重试刷错误，改为 2s→4s→…→最长 60s。
const BACKOFF_MIN = 2000;
const BACKOFF_MAX = 60000;

// ── 与桌面程序的连接状态（只影响“开关”，不影响能否下载） ──
let appConnected = false;
let appEnabled   = true;      // 默认开：即使程序没连上也能存
let ws = null, pingTimer = null;
let reconnectTimer = null, backoff = BACKOFF_MIN;

// 闹钟只用来兜底：Service Worker 被浏览器回收后，定时器会丢失，
// 靠它在下次唤醒时确保“还安排着一次重连”，而不是每 30 秒强制连一次。
chrome.alarms.create("keepAlive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => { if (!appConnected) scheduleReconnect(); });

function scheduleReconnect() {
  if (reconnectTimer) return;                 // 已经安排过，别重复
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWS();
  }, backoff);
  backoff = Math.min(backoff * 2, BACKOFF_MAX);
}

function connectWS() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  if (reconnectTimer) return;                 // 有待执行的重连，交给它，避免多开一次连接=多一条错误

  try { ws = new WebSocket(WS_URL); }
  catch { ws = null; scheduleReconnect(); return; }

  ws.onopen = () => {
    appConnected = true;
    backoff = BACKOFF_MIN;                     // 连上了，退避归零
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    console.log("[ImgSaver] 已连接桌面程序");
    try { ws.send("PING"); } catch {}
    clearInterval(pingTimer);
    pingTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) { try { ws.send("PING"); } catch {} }
    }, PING_MS);
  };
  ws.onmessage = e => {
    if (e.data === "ENABLE")  { appEnabled = true;  console.log("[ImgSaver] 程序：启用"); }
    else if (e.data === "DISABLE") { appEnabled = false; console.log("[ImgSaver] 程序：停用"); }
  };
  ws.onclose = () => {
    appConnected = false; clearInterval(pingTimer); ws = null;
    scheduleReconnect();
  };
  // 静默处理：连不上时不额外抛错，交给 onclose 去安排退避重连
  ws.onerror = () => { try { ws.close(); } catch {} };
}
connectWS();

// ── Alt+1：找图并下载 ──
let _lastFire = 0;
chrome.commands.onCommand.addListener(async (cmd) => {
  if (cmd !== "save-hover-image") return;
  const now = Date.now();
  if (now - _lastFire < 500) return;   // 防长按/连击重复
  _lastFire = now;

  console.log("[ImgSaver] 收到 Alt+1");

  // 只有“确实连上程序且程序明确停用”才跳过；其余一律尝试
  if (appConnected && !appEnabled) { console.log("[ImgSaver] 跳过：程序里为停用状态"); return; }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab?.url) { console.log("[ImgSaver] 跳过：没有活动标签页"); return; }
  if (/^(chrome|edge|about|chrome-extension|devtools|view-source):/i.test(tab.url)) {
    console.log("[ImgSaver] 跳过：受限页面（无法在此注入）", tab.url); return;
  }

  let info = null;
  try {
    const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: findHoverImage });
    info = res?.result || null;
  } catch (e) { console.warn("[ImgSaver] 注入失败：", e); return; }

  if (!info || !info.url) { console.log("[ImgSaver] 未找到光标下的图片（把鼠标停在图片上再按）"); return; }

  console.log("[ImgSaver] 找到图片，准备下载：", String(info.url).slice(0, 140));
  try {
    const id = await saveImage(info);
    console.log("[ImgSaver] 已发起下载，downloadId =", id);
  } catch (e) {
    console.warn("[ImgSaver] 下载失败：", e && e.message ? e.message : e);
  }
});

// ── 注入到页面：用 :hover 找光标下的图，取“原图”URL ──
async function findHoverImage() {
  const abs = u => { try { return u ? new URL(u, location.href).href : null; } catch { return u; } };
  const looksImg = u => /\.(png|jpe?g|webp|gif|bmp|tiff|avif)(?=$|[?#])/i.test(String(u || ""));

  const fromSrcset = img => {
    const ss = img.getAttribute("srcset");
    if (!ss) return null;
    const items = ss.split(",").map(s => s.trim()).filter(Boolean).map(s => {
      const m = s.match(/(\S+)\s+(\d+)(?:w|x)/i);
      return m ? { u: m[1], n: parseInt(m[2], 10) } : { u: s.split(/\s+/)[0], n: 1 };
    });
    items.sort((a, b) => b.n - a.n);
    return items.length ? items[0].u : null;
  };
  const fromData = img => {
    const keys = ["data-original","data-actualsrc","data-src","data-large","data-large-src",
                  "data-hd","data-big","data-zoom-image","data-image","data-full"];
    for (const k of keys) { const v = img.getAttribute(k); if (looksImg(v)) return v; }
    const a = img.closest && img.closest("a[href]");
    if (a && looksImg(a.href)) return a.href;
    return null;
  };
  const finalize = async (url, alt) => {
    if (!url) return null;
    if (url.startsWith("blob:")) {
      try {
        const b = await fetch(url).then(r => r.blob());
        const dataUrl = await new Promise((res, rej) => {
          const fr = new FileReader(); fr.onload = () => res(fr.result); fr.onerror = rej; fr.readAsDataURL(b);
        });
        return { url: dataUrl, filename: alt || "" };
      } catch { return null; }
    }
    return { url, filename: alt || "" };
  };

  const hov = document.querySelectorAll(":hover");
  const el = hov[hov.length - 1];
  if (!el) return null;

  let img = null;
  if (el.tagName === "IMG") img = el;
  else if (el.tagName === "PICTURE") img = el.querySelector("img");
  else if (el.closest) img = el.closest("img");
  if (img) {
    // 与右键“图片另存为”一致：优先取页面上正显示的这张（currentSrc / src）；
    // 只有取不到时才退回 srcset / data-* 等原图候选。
    const url = abs(img.currentSrc || img.getAttribute("src") || fromSrcset(img) || fromData(img));
    return await finalize(url, img.getAttribute("alt"));
  }

  const bg = getComputedStyle(el).backgroundImage;
  const m = bg && bg.match(/url\(["']?(.*?)["']?\)/);
  if (m && m[1]) return await finalize(abs(m[1]), el.getAttribute("aria-label"));

  return null;
}

// ── 文件名 / 下载 ──
function sanitize(s) { return String(s || "").replace(/[\\/:*?"<>|]+/g, "_").replace(/\s+/g, " ").trim(); }
// 只对“我们发起的下载”命名/加子目录，不干扰用户自己的下载。
// 注意：一旦注册了 onDeterminingFilename，download() 里传的 filename 会被忽略，
// 一律以本监听器 suggest 的为准，所以命名逻辑全部收敛到这里。
const pendingNames = new Map();   // url -> 期望文件名（null 表示交给 Chrome，与右键一致）
const ourIds = new Set();
let _armed = false;               // 兜底：刚发起、还没拿到 id 时用它认领本次下载

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  let key = pendingNames.has(item.url) ? item.url
          : pendingNames.has(item.finalUrl) ? item.finalUrl : null;
  const mine = key !== null || ourIds.has(item.id) || _armed;
  if (!mine) { suggest(); return; }          // 不是我们的下载，放行不干预
  _armed = false;
  const desired = key !== null ? pendingNames.get(key) : null;
  if (key !== null) pendingNames.delete(key);
  ourIds.add(item.id);
  // desired 为 null 时用 item.filename —— 那是 Chrome 综合网址/Content-Disposition/类型定的名，与右键一致
  const chosen = desired || String(item.filename || "image").split(/[\\/]/).pop() || "image";
  suggest({ filename: `${STAGING_SUBDIR}/${chosen}`, conflictAction: "uniquify" });
});

async function saveImage(info) {
  const url = info.url;
  let desired = null;                          // http(s)：交给 Chrome 命名（右键同款）
  if (/^data:/i.test(url)) {                   // data:（含 blob 转来的）没有真实文件名，自己起
    const mime = ((url.match(/^data:([^;,]+)/i) || [])[1] || "").toLowerCase();
    const ext = { "image/png":"png","image/jpeg":"jpg","image/webp":"webp","image/gif":"gif","image/bmp":"bmp" }[mime] || "png";
    desired = `${sanitize(info.filename) || "image"}.${ext}`;
  }
  pendingNames.set(url, desired);
  _armed = true;
  const id = await chrome.downloads.download({ url, saveAs: false });
  ourIds.add(id);
  eraseWhenDone(id);
  return id;
}

function eraseWhenDone(id) {
  const onChanged = d => {
    if (d.id === id && d.state && d.state.current === "complete") {
      chrome.downloads.onChanged.removeListener(onChanged);
      ourIds.delete(id);
      chrome.downloads.erase({ id }).catch(() => {});
    }
  };
  chrome.downloads.onChanged.addListener(onChanged);
}
