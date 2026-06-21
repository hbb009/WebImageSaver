// content.js —— 幂等 + 监听 NumpadAdd
(() => {
    const KEY = "__hover_image_saver_injected_" + chrome.runtime.id;
    if (window[KEY]) return;
    window[KEY] = true;

    let lastXY = { x: 0, y: 0 };
    window.addEventListener("mousemove", (e) => {
        lastXY = { x: e.clientX, y: e.clientY };
    }, { passive: true });

    const isEditable = (el) => {
        return el && (
            el.tagName === "INPUT" ||
            el.tagName === "TEXTAREA" ||
            el.isContentEditable
        );
    };

    function dataUrlFromBlob(blob) {
        return new Promise((resolve) => {
            const r = new FileReader();
            r.onload = () => resolve(r.result);
            r.readAsDataURL(blob);
        });
    }

    // 替换整个 pickImageUnderCursor 函数
    async function pickImageUnderCursor() {
        const el = document.elementFromPoint(lastXY.x, lastXY.y);
        if (!el) return null;

        // ---------- 工具：解析 srcset，取最大 ----------
        function pickFromSrcset(img) {
            const set = (img.getAttribute("srcset") || "").split(",").map(s => s.trim()).filter(Boolean);
            if (!set.length) return null;
            // 支持 800w / 2x 两种写法，按“宽度/倍率”都能比较
            const items = set.map(s => {
                const m = s.match(/(\S+)\s+(\d+)(w|x)/i);
                return m ? { url: m[1], n: parseInt(m[2], 10), kind: m[3].toLowerCase() } : { url: s, n: 1, kind: "x" };
            });
            // 先按 kind=w 排序，w 优先；同类里取 n 最大
            items.sort((a, b) => (a.kind === "w" ? 0 : 1) - (b.kind === "w" ? 0 : 1) || b.n - a.n);
            return items[0]?.url || null;
        }

        // ---------- 工具：从常见属性/外层链接里找“原图” ----------
        function pickFromAttrs(img) {
            const cand = [];
            const looksImg = u => /\.(png|jpe?g|webp|gif|bmp|tiff|svg|avif)(?:$|\?)/i.test(String(u || ""));
            // 常见 data-* 原图字段
            const keys = [
                "data-src", "data-original", "data-origin", "data-large", "data-large-src", "data-zoom-image",
                "data-image", "data-full", "data-url", "data-preview", "data-hd", "data-big", "data-photo"
            ];
            for (const k of keys) {
                const v = img.getAttribute(k);
                if (looksImg(v)) cand.push(v);
            }
            // 外层 <a href="...大图...">
            const a = img.closest && img.closest("a[href]");
            if (a && looksImg(a.href)) cand.push(a.href);

            // 关键字加分：orig/full/master/large/2048 等
            const score = u => {
                const s = String(u).toLowerCase();
                let sc = 0;
                if (/orig|original|master|full|large|hd/.test(s)) sc += 10;
                const num = (s.match(/(\d{3,5})(?=\D|$)/g) || []).map(n => parseInt(n, 10)); // 提取像素数字
                if (num.length) sc += Math.max(...num) / 1000; // 越大越好
                return sc;
            };
            cand.sort((a, b) => score(b) - score(a));
            return cand[0] || null;
        }

        // ---------- IMG / PICTURE：尽力取最大 ----------
        if (el.tagName === "IMG") {
            const fromSrcset = pickFromSrcset(el);
            const fromAttr = pickFromAttrs(el);
            const best = fromAttr || fromSrcset || el.getAttribute("src") || el.currentSrc;
            return best ? { kind: "url", url: best, filename: el.alt || "image" } : null;
        }
        if (el.tagName === "PICTURE") {
            const img = el.querySelector("img");
            if (img) {
                const fromSrcset = pickFromSrcset(img);
                const fromAttr = pickFromAttrs(img);
                const best = fromAttr || fromSrcset || img.getAttribute("src") || img.currentSrc;
                return best ? { kind: "url", url: best, filename: img.alt || "image" } : null;
            }
        }

        // ---------- CSS 背景图 ----------
        const bg = getComputedStyle(el).backgroundImage;
        const m = bg && bg.match(/url\(["']?(.*?)["']?\)/);
        if (m && m[1]) return { kind: "url", url: m[1], filename: el.getAttribute("aria-label") || "image" };

        // ---------- CANVAS → dataURL（没有“原图”的概念） ----------
        if (el.tagName === "CANVAS") {
            try { return { kind: "data", dataUrl: el.toDataURL("image/png"), filename: "canvas" }; } catch { }
        }

        // ---------- blob: URL → 取真实二进制再转 dataURL ----------
        if (el && el.src && String(el.src).startsWith("blob:")) {
            try {
                const resp = await fetch(el.src);
                const blob = await resp.blob();
                const dataUrl = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(blob); });
                return { kind: "data", dataUrl, filename: el.alt || "image" };
            } catch { }
        }
        return null;
    }

    // 监听“数字键盘 +”且无修饰键；避免在可编辑控件里触发
    window.addEventListener("keydown", async (e) => {
        if (e.code === "NumpadAdd" && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey && !isEditable(e.target)) {
            e.preventDefault();
            e.stopPropagation();
            const info = await pickImageUnderCursor();
            if (info) await safeSendMessage({ type: "SAVE_INFO", info });
        }
    }, true);

    // 新增：F5 / F8 也作为保存触发键（无修饰键时），并阻止默认刷新/行为
    window.addEventListener("keydown", async (e) => {
        if ((e.code === "F5" || e.code === "F8") && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey && !isEditable(e.target)) {
            e.preventDefault();
            e.stopPropagation();
            const info = await pickImageUnderCursor();
            if (info) await safeSendMessage({ type: "SAVE_INFO", info });
        }
    }, true);

    // Alt+1 触发（无 Ctrl/Shift/Meta，且不在可编辑控件）
    window.addEventListener("keydown", async (e) => {
        if (e.code === "Digit1" && e.altKey && !e.ctrlKey && !e.shiftKey && !e.metaKey && !isEditable(e.target)) {
            e.preventDefault();
            e.stopPropagation();
            const info = await pickImageUnderCursor();
            if (info) await safeSendMessage({ type: "SAVE_INFO", info });
        }
    }, true);

    // 兼容 background 主动索取
    chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
        if (msg && msg.type === "GET_HOVER_IMAGE") {
            pickImageUnderCursor().then(sendResponse);
            return true;
        }
    });
})();

// —— 安全发送到后台，避免 "Extension context invalidated" 报错 ——
// 场景：扩展刚被重载/Service Worker 刚重启/页面刚跳转导致 runtime 暂不可用
async function safeSendMessage(payload) {
    try {
        // 扩展被卸载/重载时，runtime.id 可能不存在
        if (!chrome?.runtime?.id) throw new Error("RUNTIME_LOST");
        return await chrome.runtime.sendMessage(payload);
    } catch (err) {
        const msg = String(err && err.message || err);
        // 这两类是无害的瞬时错误，静默忽略（不打断使用）
        if (msg.includes("Extension context invalidated") || msg.includes("RUNTIME_LOST")) {
            console.debug("[WebImageSaver] sendMessage skipped:", msg);
            return;
        }
        console.error("[WebImageSaver] sendMessage failed:", err);
    }
}
