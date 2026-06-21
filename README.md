# 桌面助手 v9.5 · 给 AI 人的口袋瑞士军刀 🔧🧠

> 把常用的小动作装进一个干净的窗口里：少切换两个软件，多一份心流。

---

## 🆕 v9.5 更新亮点

### 🎨 样式体系统一（`assets/app.qss`）
- **废弃 `common_styles.py`**：全部样式集中到 `app.qss`，消除各页面 `setStyleSheet(TEXT_STYLE/BUTTON_STYLE)` 冲突。
- **通用 GroupBox 标准**：`QGroupBox[titleVariant="accent"]` 统一深色底 `#0f1430`、边框 `#25345c`、圆角 10px、小字灰色标题，所有页面自动对齐"积分计算"风格。
- **结果指标卡修复**：`QFrame#MetricCard` 精准选择器，修复计算结果区文字后的深色背景框问题。
- **截图工具、比例计算、系统总览、反推提示词、批量打标**：全部自动继承通用 GroupBox 样式，无需逐页修改。

### 🖼️ 速存图文（`pages/page_fast_save.py`）
- **后台持续运行**：切换页面不再自动关闭速存/截图功能，保持后台工作。
- **侧边栏快捷开关**：速存图文、截图工具按钮右侧增加勾选开关（✓），无需切换页面即可直接开启/关闭，开启时变蓝。
- **提示文字修正**：快捷键说明由"Ctrl+Alt+7"更正为"Alt+1"；文本快捷键说明加入"可改为 F5～F8"提示。
- **界面对齐积分计算**：两个分组框深色背景、日志列表颜色与主题色板统一。

### 🔍 反推提示词（`pages/page_rev_prompt.py`）
- **修复崩溃**：补充 `QFileDialog` import，消除点击"选择图片"时的 `NameError`。
- **视觉模型识别升级**：新增 `/api/show` API 检测 modelfile；名字匹配新增 gemma3、phi4-vision、molmo、pixtral、cogvlm2、janus、idefics 等 15+ 近期模型。
- **强制发送图片**：新增"强制发送图片"复选框，绕过名字匹配，适配名字不规范的视觉模型。
- **流式实时输出**：生成过程逐字追加，不再等全部完成才显示。
- **新增按钮**："复制"一键复制结果到剪贴板；"刷新模型"重新拉取 Ollama 模型列表。
- **移除中文框**：界面简化，仅保留英文输出框，去掉始终为空的中文区域。

### 🏷️ 批量打标（`pages/page_batch_tag.py`）
- **真实打标**：接入 Ollama 视觉模型，从"生成占位文本"升级为真正调用模型。
- **5 种提示词模板**：Booru 标签 / SD 训练提示词 / 中文描述 / 英文描述 / 中英双语。
- **进度条 + 停止按钮**：实时显示当前处理进度，可随时中断。

### 📐 比例计算（`pages/page_ratio_calc.py`）
- **AI 生图像素预设**：比例按钮绑定常用像素值（长边 1536），点击自动填入 C 并立即计算 D。
- **Tooltip 提示**：悬停在比例按钮上显示具体像素尺寸（如 `1536 × 864 px`）。
- **预设比例更新**：`1:1 / 16:9 / 4:3 / 3:2 / 3:4 / 2:3 / 9:16 / 21:9`，覆盖主流 AI 生图场景。

### 🧩 Ollama 助理（`pages/page_ollama.py`）
- 移除旧样式 import，气泡颜色由 `app.qss` 统一管理，不再硬编码。

### 🗑️ 清理
- 删除无用文件：`app.py`（独立 Streamlit 工具）、`image_role_classifier_gui.py`（独立 tkinter 工具）、`v9.4/` 历史目录。
- 入口文件 `mainv92.py` 版本号更新为 v9.5。

---

## 🛠️ 安装与运行

> 建议 **Python 3.10+ / Windows 10+**（手动速存文本需 Windows）

```bash
# 核心依赖
pip install PyQt5 psutil pyperclip pywin32

# 可选（按需安装）
pip install keyboard pyautogui numpy flask flask-cors requests

# 运行
python mainv92.py
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

## 📁 代码结构

```
image_text_tool/
├─ mainv92.py                   # 入口（python mainv92.py 启动）
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
