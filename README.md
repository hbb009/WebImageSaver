# 桌面助手 v9.5 · 给 AI 人的口袋瑞士军刀 🔧🧠

> 小工具的一个操作，省下您的10秒时间

---

## 🆕 v9.5 核心功能模块

### 🖥️ **系统总览**
- 实时监控设备硬件状态，包括 CPU、内存、GPU（使用率/显存/温度/功耗）。
### 📥 **速存图文**
- 后台静默监听，通过全局快捷键（如 Alt+1、F7）一键将剪贴板文本或图片直存至预设本地目录。
### 🧮 **积分计算**
- AI 平台订阅成本核算器。输入平台费用及获取积分，自动折算单次生图或单秒视频的精确人民币成本，并支持历史记录保存。
### ✂️ **截图工具**
- 支持自定义组合热键（如 Ctrl+Shift+A），框选屏幕区域并自动保存到指定文件夹。
### 📐 比例计算
- 内置 1:1、16:9、21:9 等 8 种 AI 常用画幅预设；支持输入基准像素（如长边 1536），自动换算确切的宽/高数值。
### 🔍 **反推提示词**
- 单图拖拽反推。接入本地 Ollama 视觉模型（支持 gemma3、phi4-vision 等），内置 9 种英文 Prompt 输出模式（如 Booru、Midjourney 风格），流式生成结果。
### 🏷️ 批量打标
- 对指定本地文件夹的图片进行自动化批量分析，调用视觉模型生成 SD/Booru 格式的 `.txt` 标签文件，带实时进度监控。
### 🤖 **Ollama 助理**
- 简易的本地 LLM 对话窗口，支持流式文本交互。
### 🧩 **浏览器扩展 (MV3)**
- 配合“速存图文”使用，将 `MV3/` 目录加载至 Chrome 浏览器，可增强网页图片保存的兼容性（可选组件）。

---

## 🛠️ 安装与运行

> 建议 **Python 3.10+ / Windows 10+**（手动速存文本需 Windows）

```bash
# 核心依赖
pip install PyQt5 psutil pyperclip pywin32

# 可选（按需安装）
pip install keyboard pyautogui numpy flask flask-cors requests

# 运行
python mainv95.py
```

**可选环境**
- **NVIDIA**：用于 GPU 监控，需 `nvidia-smi` 在 PATH 中；否则 GPU/显存/温度/功耗显示 0。
- **Ollama**：用于反推提示词和批量打标；视觉模型需手动拉取，例如：
  ```bash
  ollama pull llava:latest
  ollama pull qwen2-vl:7b
  ```
- **浏览器扩展（MV3）**：配合速存图文使用，安装 `MV3/` 目录下的扩展可增强图片保存兼容性（可选）。

---
### 🧩 附：浏览器扩展（MV3）安装步骤（速存图文，必装）

如果需要使用“速存图文”功能并增强网页图片的保存兼容性，请手动将配套的浏览器插件安装到 Google Chrome 中：

1. **打开扩展管理页面**：打开 Chrome 浏览器，在地址栏输入 `chrome://extensions/` 并回车（或点击浏览器右上角“三点”图标 -> “扩展程序” -> “管理扩展程序”）。
    
2. **开启开发者模式**：在扩展程序页面右上角，找到并打开 **“开发者模式”** 开关。
    
3. **加载插件文件夹**：点击页面左上角出现的 **“加载已解压的扩展程序”** 按钮。
    
4. **选择项目目录**：在弹出的文件选择框中，找到你本地的 **`MV3` 文件夹**，点击“选择文件夹”即可完成安装。

---

## 📁 代码结构

```
image_text_tool/
├─ mainv95.py                   # 入口（python mainv92.py 启动）
├─ ui_main.py                   # 主窗口 + 主题栏 + 页面栈 + 侧栏 + LED 开关
├─ assets/
│  ├─ app.qss                   # 统一主题样式（v9.5 全面重构）
│  └─ star.ico                  # 窗口图标
├─ pages/
│  ├─ page_overview.py          # 系统总览（资源监控 / 环境信息 / 版本日志）
│  ├─ page_fast_save.py         # 速存图文（自动剪贴板 / 手动 F7 / 鼠标侧键）
│  ├─ page_screenshot.py        # 截图工具（热键框选保存）
│  ├─ page_ratio_calc.py        # 比例计算（AI 像素预设 / 简易计算器）
│  ├─ page_rev_prompt.py        # 反推提示词（Ollama 视觉模型 / 9 种模式）
│  ├─ page_batch_tag.py         # 批量打标（Ollama 视觉模型 / 5 种模板）
│  ├─ page_points_calc.py       # 积分计算（AI 订阅成本计算器）
│  └─ page_ollama.py            # Ollama 助理（流式聊天）
├─ utils/
│  ├─ ollama_client.py          # Ollama 封装（含视觉模型识别 / 流式输出）
│  ├─ file_utils.py             # 文件工具
│  └─ server.py                 # 本地 Flask 服务（配合浏览器扩展）
├─ styles/
│  └─ common_styles.py          # v9.5 已废弃，保留空变量兼容旧引用
├─ records/
│  └─ points_calc.txt           # 积分计算历史记录（JSON Lines）
└─ MV3/                         # 配套浏览器扩展（可选）
   ├─ manifest.json
   ├─ background.js
   └─ content.js
```

---

## ❗ 常见问题

- **`ModuleNotFoundError: No module named 'utils'`**
  → 确认从项目根目录运行 `python mainv92.py`，不要在子目录里启动。

- **资源监控无 GPU 数据**
  → 安装 `psutil`；若无 NVIDIA 或 `nvidia-smi` 不在 PATH，GPU/显存/温度/功耗显示 0，不影响其他功能。

- **反推提示词返回空 / 图片未发送**
  → 确认选择的模型是视觉模型（下拉绿色=视觉，红色=纯文本）；若模型名不被识别，勾选"强制发送图片"复选框。

- **批量打标无输出**
  → 确认 Ollama 已启动且已拉取视觉模型；点击"刷新"按钮重新获取模型列表。

- **手动速存文本（F7）不响应**
  → 依赖 `pywin32`（仅 Windows）；确认已在"速存图文"页面开启"速存图片"开关，F7 随之生效。

- **速存图片侧键无反应**
  → 鼠标侧键监听依赖 Windows 全局钩子；确认程序以**管理员权限**运行，或在安全软件白名单中放行。

---

## ✅ 开发规范

- **样式与逻辑分离**：所有视觉样式写入 `assets/app.qss`；布局、定时刷新、业务逻辑写在 Python。
- **样式钩子**：用 `setObjectName()`、`setProperty("titleVariant","accent")`、`setProperty("typo","...")` 精准命中 QSS，避免 `setStyleSheet()` 内联污染。
- **优雅降级**：`psutil` / `nvidia-smi` / Ollama 不可用时提示但不崩溃。
- **Windows 依赖隔离**：`pywin32`、`ctypes` WinAPI 相关代码均有 `try/except` 保护。

---

## 📜 版本历史

| 版本 | 主要内容 |
|------|----------|
| **v9.5（当前）** | 样式体系统一；速存图文后台持续运行 + 侧边栏 LED 开关；反推提示词修复崩溃 + 视觉模型升级；批量打标真实接入 Ollama；比例计算 AI 像素预设 |
| **v9.0** | 主题与字体系统一；主题栏；系统总览资源监控；反推提示词（预览+模型下拉+9 模式+双语）；比例计算（状态+预设比例+简易计算器）；批量打标；速存图文样式优化 |
| **v8.1** | 速存图文自动/手动模式；截图工具热键框选；比例计算基础版；Ollama 助理流式聊天 |
