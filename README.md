<img width="962" height="765" alt="354390c9-9bbe-4c23-9563-f7406a1f15e8" src="https://github.com/user-attachments/assets/8e8a690a-9217-4b98-8bff-1a55af8c3786" />

# 桌面助手 v9.14 · 给 AI 人的口袋瑞士军刀 🔧🧠

> 让每一个操作，都能为您省下宝贵的时间

---

## 🆕 v9.14 主要调整

1. **设置区迁移到「系统总览」**：原「关于」页里的软件信息、界面缩放、保存与 Cookie、数据管理，整体搬到「系统总览」页，抽成可复用的 `settings_section.py`；「关于」页现在只保留自动下载白名单管理与底部链接（YT 入口改为 GitHub）。
2. **新增「功能与说明」图文轮播**：系统总览新卡片，最多 12 张 `guides/` 目录图片自动轮播（15 秒一张，可点底部圆点切换），作为随包更新的操作教程。
3. **图集下载新增 hitomi.la**：在 e-hentai/ExHentai 之外新增 hitomi.la 图库解析下载（含 gg.js 分片算法、Referer 直链等），随附独立调试脚本 `tools/hitomi_zip_debug.py` 核对官网下载逻辑。
4. **下载防同名 + 防卡死**：新增 `utils/download_confirm.py`，下载前遇到同名文件弹窗三选一（中止/改名/覆盖，默认 10 秒后自动中止）；新增 `utils/download_watchdog.py`，单条视频/图片 180 秒无新数据流入即判定失败并主动断开，避免整批任务被卡住。
5. **全局光标提示气泡**：新增 `utils/cursor_toast.py`，任意页面可在鼠标旁弹出短暂提示（最多 8 个汉字），用于各类操作的轻量反馈。
6. **侧栏默认分区调整**：置顶常用新增「截图工具」「区域录屏」；助手区调整为「粘贴助手 / 积分计算 / 语音编辑」；工具区调整为「比例计算 / 时区汇率 / 目录映射」（拖拽排序与改名功能不变，仍写入 `records/user.txt`）。
7. **修复界面缩放重启失效**：v9.13 重构时遗漏了启动前写入 `QT_SCALE_FACTOR` 的逻辑，导致选择 1.5× 等倍数重启后仍停在 1×；已在新入口 `mainv914.py` 中修复。
8. **语音编辑繁转简**：新增 `zhconv` 依赖，Whisper 转写常见的繁体输出会自动转换为简体。

---

## 🗂️ 功能模块

侧边栏分三区：**置顶常用** → **助手 · 主手脚** → **工具 · 小偏门**（靠下），底部为「关于」。
> 侧栏按钮可**按住拖拽排序**（可跨分区自由摆放），分区标题可自定义改名，顺序与命名自动保存到 `records/user.txt`。

### 置顶常用

- **🖥️ 系统总览**：显示环境信息（设备名 / 处理器 / 机带 RAM / 系统类型与版本 / Python 版本 / 磁盘空间）与资源监控（GPU 使用率、显存、内存、CPU、GPU 温度、GPU 功耗、硬盘使用，实时刷新百分比+进度条）；下方版本信息区读取项目根目录 `README.md` 展示更新日志。**新增设置区**：界面缩放、保存与 Cookie、数据管理（导出/导入/重置）三张卡片，及展示 `guides/` 教程图的「功能与说明」轮播卡（原本这些内容在「关于」页，v9.14 起统一迁到本页）。
- **📥 速存图文**：配套浏览器插件，图片悬停按快捷键静默保存、文本全局快捷键提取，自动分类建目录；开关一键启停「速存全功能」。
- **🎬 视频下载**：抖音 / B站 / YouTube 三个 Tab 子页，支持解析下载与统一跨平台批量下载；开关为「自动下载」——剪贴板复制到对应平台链接时后台静默解析下载；下载遇到同名文件会弹窗确认（中止/改名/覆盖），单条内容 180 秒无进度自动判定失败并跳过。
- **🖼️ 图集下载**：粘贴漫画/图站网址批量抓图，优先支持 e-hentai/ExHentai，**新增 hitomi.la** 图库解析下载；开关同样是「自动下载」，复制图集链接即后台触发；同样具备同名文件确认与下载防卡死保护。
- **✂️ 截图工具**（v9.14 起置顶）：自定义热键框选截图，自动存图/转格式/复制剪贴板；开关为「截图监听」一键开/关热键。
- **⏺ 区域录屏**（v9.14 起置顶）：热键定位/调整选区后开录，热键停止保存；按钮旁圆点在录制中显示红点提示。

> v9.14 起「截图工具」「区域录屏」移入置顶常用区，见上；「助手」「工具」两区的默认成员随之调整为下列内容（分区仍可拖拽/改名）。

### 助手 · 主手脚

- **📝 粘贴助手**：主题 + 内容 + 七色标签存为卡片，流式布局可拖拽排序，点击复制并载入编辑区。
- **💰 积分计算**：按订阅金额、汇率、单次消耗积分，折算单图/单秒视频的真实成本，历史可保存。
- **🎙 语音编辑**：本地语音转文字，转写结果进主编辑区改字、分段、排版后一键复制；繁体输出自动转简体（`zhconv`）。

### 工具 · 小偏门

- **比例计算**：常用画幅像素换算，附金额大小写转换。
- **时区汇率**：多城市模拟时钟（可增删/可模拟时间）+ 汇率转换器。
- **目录映射**：图形化软链接创建，附磁盘空间 Treemap 可视化。

### 关于

自动下载白名单管理，及底部 GitHub/主题切换等链接。**软件信息、界面缩放、保存与 Cookie、数据管理已移至「系统总览」页**，详见上文。

---

## 🛠️ 安装与运行

> 建议 **Python 3.10+ / Windows 10+**（部分能力仅限 Windows）

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python mainv914.py
```

**关于管理员权限**：默认普通用户启动，需要时可显式提权 `python mainv914.py --as-admin`；目录映射页的 `mklink` 也可单独勾选管理员执行。

**可选环境**
- **NVIDIA**：GPU 监控需 `nvidia-smi` 在 PATH。
- **yt-dlp + ffmpeg + Deno/Node.js**：视频下载 B站/YouTube 子页 + 区域录屏需要。
- **faster-whisper + sounddevice**：语音编辑转写需要，未装则提示安装；转写结果自动繁转简（`zhconv`）。
- **rapidocr-onnxruntime**：截图工具 OCR 识字（可选）。
- **浏览器扩展（MV4）**：配合速存图文使用。
- **Get cookies.txt LOCALLY（浏览器扩展）**：导出 YouTube / e-hentai / hitomi.la 等站点 Cookie（Netscape 格式），图集下载与部分平台解析需要。
> 磁盘 Treemap、版本信息与「功能与说明」轮播均已改用 Qt 原生渲染（QPainter / QTextBrowser / QLabel），不再依赖 PyQtWebEngine。

### 🧩 浏览器扩展（MV4）安装步骤

1. Chrome 地址栏输入 `chrome://extensions/`
2. 打开右上角「开发者模式」
3. 「加载已解压的扩展程序」→ 选择项目 `MV4` 文件夹

---

## 📁 代码结构

```
桌面助手/
├─ mainv914.py                  # 入口（默认普通用户；--as-admin 显式提权；启动前设 QT_SCALE_FACTOR）
├─ ui_main.py                   # 主窗口 + 侧栏三分区 + 拖拽排序 + 分区改名
├─ requirements.txt
├─ pages/
│  ├─ page_overview.py          # 系统总览（含设置区：界面缩放/保存与Cookie/数据管理/功能与说明）
│  ├─ settings_section.py       # 设置区可复用组件（原属「关于」页）
│  ├─ page_fast_save.py         # 速存图文
│  ├─ page_video.py             # 视频下载（Tab 容器 + 统一批量下载）
│  ├─ page_douyin.py / page_bilibili.py / page_youtube.py   # 三平台子页
│  ├─ page_gallery.py           # 图集下载（e-hentai/ExHentai + hitomi.la）
│  ├─ page_screenshot.py        # 截图工具
│  ├─ page_region_record.py     # 区域录屏
│  ├─ page_paste.py             # 粘贴助手
│  ├─ page_voice_input.py       # 语音编辑（本地转写，繁转简）
│  ├─ page_points_calc.py       # 积分计算
│  ├─ page_ratio_calc.py / page_dir_link.py / page_timezone_fx.py  # 工具·小偏门
│  ├─ page_about.py             # 关于（自动下载白名单管理）
│  └─ disk_treemap_widget.py    # 磁盘空间 Treemap 可视化
├─ tools/
│  └─ hitomi_zip_debug.py       # hitomi.la 下载逻辑核实/调试脚本
├─ utils/                       # 通用工具（文件/日志/布局/语音转写等）
│  ├─ download_confirm.py       # 下载前同名文件三选一确认（中止/改名/覆盖）
│  ├─ download_watchdog.py      # 下载防卡死看门狗（180s 无进度即判失败）
│  └─ cursor_toast.py           # 全局鼠标旁轻提示气泡
├─ styles/                      # 主题样式（app.qss / app_light.qss / style_all.py）
├─ guides/                      # 「功能与说明」轮播教程图（最多 12 张）
├─ records/                     # 运行数据（user.txt / paste_helper.txt / app.log 等）
└─ MV4/                         # 配套浏览器扩展
```

> 主脑配置、导演台、Ollama 工具、反推生图等 AI 相关页面（`page_brain_config.py`、`page_api_config.py`、`page_model_service.py`、`page_director.py`、`page_ollama_tools.py`、`page_literary_writing.py`、`page_prompt_gen.py`、`utils/llm_client.py`、`utils/mini_brain_client.py`、`utils/ollama_client.py`）已从主程序拆出，将并入独立的「算力版」程序。

---

## ❗ 常见问题

- **`ModuleNotFoundError: No module named 'utils'`** → 从项目根目录运行 `python mainv914.py`。
- **资源监控无 GPU 数据** → 安装 `psutil`；无 NVIDIA 或 `nvidia-smi` 不在 PATH 时显示 0。
- **语音编辑转写无反应** → 需安装 `faster-whisper` + `sounddevice`，首次使用可能联网下载模型。
- **B站 / YouTube 无法解析** → 需安装 `yt-dlp`；合并/转 mp3 需 `ffmpeg`；JS 挑战需 `Deno`/Node.js。
- **图集下载访问 ExHentai / hitomi.la 失败** → 需导入有效 Netscape 格式 Cookie；hitomi.la 的分片直链逻辑可用 `tools/hitomi_zip_debug.py` 单独核实。
- **下载一直卡在某一条不动** → v9.14 已有防卡死看门狗，180 秒无新数据会自动判定失败并跳过；若仍长时间无响应，请检查网络或站点是否失效。
- **下载提示"已存在同名文件"** → 弹窗默认 10 秒后自动中止，也可手动选择改名或覆盖；此确认对视频下载与图集下载均生效。
- **调整界面缩放后重启没生效** → v9.13 曾有该 bug，v9.14 已在 `mainv914.py` 中修复；仍异常可检查 `records/user.txt` 里 `ui.scale` 是否写入正确。
- **找不到「软件信息 / 界面缩放 / 保存与 Cookie」** → v9.14 起已从「关于」页移至「系统总览」页。
- **速存图片插件状态灯黄/红** → 黄=等待连接或心跳超时；红=端口占用或 Chrome 未运行，确认以管理员权限运行或放行安全软件白名单。
- **截图 OCR 无法识字** → 需安装 `rapidocr-onnxruntime`（与 `numpy<2` 搭配），或到「关于」页一键修复。

---

## ✅ 开发规范

- **样式与逻辑分离**：视觉样式写入 `assets/*.qss` 与 `styles/style_all.py`；布局与业务逻辑写在 Python。
- **优雅降级**：`psutil` / `nvidia-smi` / `yt-dlp` / `faster-whisper` 不可用时提示但不崩溃。
- **Windows 依赖隔离**：`pywin32`、WinAPI 相关代码均有 `try/except` 保护。
- **后台线程与关窗清理**：涉及定时器/`QThread` 的页面需在 `ui_main.py` 的 `closeEvent` 统一停止。
- **持久化原子写入**：用户配置「写 `.tmp` + `os.replace`」，见 `utils/user_prefs.py`。

---

## 📜 版本历史

| 版本 | 主要内容 |
| --- | --- |
| **v9.14 (当前)** | 设置区（软件信息/界面缩放/保存与Cookie/数据管理）从「关于」页迁移到「系统总览」页，并新增「功能与说明」图文轮播卡；图集下载新增 hitomi.la 支持；下载新增同名文件确认与防卡死看门狗；新增全局鼠标提示气泡；侧栏默认分区调整（截图/录屏入置顶）；修复界面缩放重启失效的 bug；语音编辑转写结果自动繁转简。 |
| **v9.13** | Ollama/API 相关的主脑配置、导演台、Ollama 工具、反推生图等 AI 页面从主程序拆分，后续独立为「算力版」程序；侧栏主按钮支持跨分区拖拽排序 + 分区改名；视频下载新增 B站子页与跨平台统一批量下载；新增「语音编辑」（本地转写）。 |
| **v9.12** | 版本号升级至 v9.12，入口改为 `mainv912.py`。 |
| **v9.11** | 主大脑配置改为顶栏「本地/API」开关 + ⚙ 弹窗；模型条与粘贴助手 UI 打磨；抖音解析软过滤兜底；关于页可点 GitHub、复制联系方式。 |
| **v9.10** | 抖音下载升级为多平台视频下载（+YouTube）；新增图集下载；新增模型选择全局主大脑；侧栏三分区重排；默认普通用户启动。 |
| **v9.9** | 新增粘贴助手、导演台、文学写作；反推提示词与批量打标合并为 Ollama 工具；抖音新增一键粘贴解析；速存图文改 WebSocket 心跳。 |
| **v9.8** | 新增抖音无水印解析、积分计算、图形化目录映射与磁盘分析；速存图文新增插件直连。 |
| **v9.5** | 样式体系统一；速存图文后台常驻；批量打标真实接入 Ollama。 |
| **v9.0** | 主题与字体统一；系统总览资源监控；反推提示词、比例计算、批量打标上线。 |
| **v8.1** | 速存图文自动/手动模式；截图工具热键框选；Ollama 助理流式聊天。 |
