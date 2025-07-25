document.addEventListener("DOMContentLoaded", function () {
    const serverInput = document.getElementById("serverUrl");
    const useAltKeyCheckbox = document.getElementById("useAltKey");
    const status = document.getElementById("status");

    // 加载现有配置
    chrome.storage.sync.get(["serverUrl", "useAltKey"], function (config) {
        if (config.serverUrl) serverInput.value = config.serverUrl;
        useAltKeyCheckbox.checked = config.useAltKey ?? true;
    });

    // 保存按钮
    document.getElementById("saveBtn").addEventListener("click", function () {
        chrome.storage.sync.set({
            serverUrl: serverInput.value || "http://127.0.0.1:8787",
            useAltKey: useAltKeyCheckbox.checked
        }, function () {
            status.textContent = "✅ 设置已保存！";
            setTimeout(() => status.textContent = "", 2000);
        });
    });
});
