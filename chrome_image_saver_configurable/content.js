chrome.storage.sync.get(["serverUrl", "useAltKey"], function (config) {
    const serverUrl = config.serverUrl || "http://127.0.0.1:8787";
    const useAltKey = config.useAltKey ?? true;

    document.addEventListener("click", function (e) {
        if (e.target.tagName === "IMG" && (!useAltKey || e.altKey)) {
            const imgUrl = e.target.src;
            fetch(`${serverUrl}/save`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: imgUrl })
            }).then(() => {
                console.log("✅ 图片URL发送成功：", imgUrl);
            }).catch((err) => {
                console.error("❌ 发送失败：", err);
            });
        }
    });
});
