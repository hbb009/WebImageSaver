<img width="962" height="853" alt="1c27ccc2-960e-40fc-8d84-6a2e6126cc0a" src="https://github.com/user-attachments/assets/7688b0aa-aa81-43d6-b7e9-75574263a2ee" />

# 桌面助手 v9.15 · 给 AI 人的口袋瑞士军刀 🔧🧠

> 让每一个操作，都能为您省下宝贵的时间

---

## 🆕 v9.15 主要调整

1. **图集下载新增 Pixiv 支持**：在 e-hentai/ExHentai、hitomi.la 之外新增 Pixiv 作品解析下载（`pixiv.net/artworks/{id}`，优先走站内 AJAX 接口），需登录后导出 Cookie；「关于」页自动下载白名单新增 Pixiv 分组。
2. **新增「图片处理」页**（助手区，粘贴助手与积分计算之间）：拖放/选图后可缩小、切割、转格式，右侧操作与选项同行，下方「输出预览」纵向滚动展示处理结果，单击打开输出目录；JPG 固定最高品质导出。
3. **新增「提示词编辑器」页**（助手区）：面向文生视频的提示词编辑，左原稿 / 右新稿分栏，按「基础参数 / 镜头 / 人物 / 体型 / 服装 / 环境 / 动作 / 表演 / 台词」等字段一一对应填写，历史记录写入 `prompts/history.jsonl`。
4. **新增「电子钟」页**：顶栏新增时钟图标入口（替换原 B 站空间猫标），七段数码时分（24 小时制）+ 月历 + 天气卡（天气目前为界面示意，实况接口待接入），不占用侧栏位置。
5. **「预下载」体系重构**：原「侧栏自动下载开关 + 记录 + 批处理」链路，统一改为**预下载队列**——剪贴板命中白名单后按平台（抖音 / B站 / YouTube / e-hentai / Pixiv / hitomi.la）+「无法处理」共 7 个分类入队，空闲且冷却 3 秒后自动继续下一条；系统总览新增「预下载」卡片（自动处理开关 + 「预处理文件」按钮，可整表查看/编辑队列）；图集下载、视频下载子页页签右侧显示预下载条数角标；单条记录也可一键转出为粘贴助手的记录卡（`cards/` 目录）。
6. **截图 OCR 识字改为独立子进程运行**：新增 `--ocr-job` 启动参数，OCR 引擎在独立进程内加载，避免与主进程 Qt/OpenMP 抢占 DLL 导致"误报未安装"或识别失败；同时新增 `tools/fix_ocr.bat` 一键修复脚本（重装 numpy/onnxruntime/RapidOCR）。
7. **语音编辑同样迁移子进程模式**：新增 `--whisper-job` 启动参数，转写模型在独立子进程中加载，避免与主进程 Qt DLL 冲突导致崩溃。
8. **入口更新为 `mainv915.py`**，界面缩放启动前写入 `QT_SCALE_FACTOR` 的逻辑延续 v9.14 的修复。
9. **新增 `yt-dlp-ejs` 依赖**：配合 `yt-dlp` 处理 B站/YouTube 的 JS 签名反爬校验，建议与 `yt-dlp` 一同定期升级。

---

## 🗂️ 功能模块

侧边栏分三区：**置顶常用** → **助手 · 主手脚** → **工具 · 小偏门**（靠下），底部为「关于」；顶栏另有「电子钟」图标入口（不占侧栏位置）。
> 侧栏按钮可**按住拖拽排序**（可跨分区自由摆放），分区标题可自定义改名，顺序与命名自动保存到 `records/user.txt`。

### 置顶常用

- **🖥️ 系统总览**：显示环境信息（设备名 / 处理器 / 机带 RAM / 系统类型与版本 / Python 版本 / 磁盘空间）与资源监控（GPU 使用率、显存、内存、CPU、GPU 温度、GPU 功耗、硬盘使用，实时刷新百分比+进度条）；下方版本信息区读取项目根目录 `README.md` 展示更新日志。设置区（界面缩放、保存与 Cookie、数据管理）与「功能与说明」教程轮播卡均在本页；**v9.15 新增「预下载」卡片**：自动处理开关 + 「预处理文件」按钮，可整表查看/编辑六平台 + 无法处理队列。
- **📥 速存图文**：配套浏览器插件，图片悬停按快捷键静默保存、文本全局快捷键提取，自动分类建目录；开关一键启停「速存全功能」。
- **🎬 视频下载**：抖音 / B站 / YouTube 三个 Tab 子页，支持解析下载与统一跨平台批量下载；剪贴板命中白名单后进入**预下载队列**自动处理，页签角标显示排队条数；下载遇到同名文件会弹窗确认（中止/改名/覆盖），单条内容 180 秒无进度自动判定失败并跳过。
- **🖼️ 图集下载**：粘贴漫画/图站网址批量抓图，支持 e-hentai/ExHentai、hitomi.la，**v9.15 新增 Pixiv**；同样接入预下载队列（页签角标显示条数）与同名文件确认、下载防卡死保护。
- **✂️ 截图工具**：自定义热键框选截图，自动存图/转格式/复制剪贴板，内置本地 OCR 识字（RapidOCR 优先，可选 Tesseract）；**v9.15 起 OCR 在独立子进程中运行**，减少 DLL 冲突导致的误报；开关为「截图监听」一键开/关热键。
- **⏺ 区域录屏**：热键定位/调整选区后开录，热键停止保存；按钮旁圆点在录制中显示红点提示。

### 助手 · 主手脚

- **📝 粘贴助手**：主题 + 内容 + 七色标签存为卡片，流式布局可拖拽排序，点击复制并载入编辑区；预下载记录也可一键转出为本页记录卡。
- **🖌️ 图片处理**（v9.15 新增）：选图后缩小 / 切割 / 转格式，输出预览区可滚动查看历史处理结果，单击打开输出目录。
- **💰 积分计算**：按订阅金额、汇率、单次消耗积分，折算单图/单秒视频的真实成本，历史可保存。
- **🎙 语音编辑**：本地语音转文字（**v9.15 起在独立子进程中加载模型**，避免与 Qt 冲突崩溃），转写结果进主编辑区改字、分段、排版后一键复制；繁体输出自动转简体（`zhconv`）。
- **📋 提示词编辑器**（v9.15 新增）：文生视频提示词左右对照编辑，字段化管理（基础参数/镜头/人物/体型/服装/环境/动作/表演/台词等），历史记录自动保存。

### 工具 · 小偏门

- **比例计算**：常用画幅像素换算，附金额大小写转换。
- **时区汇率**：多城市模拟时钟（可增删/可模拟时间）+ 汇率转换器。
- **目录映射**：图形化软链接创建，附磁盘空间 Treemap 可视化。

### 顶栏入口（不占侧栏）

- **⏰ 电子钟**（v9.15 新增）：点击顶栏时钟图标进入，七段数码时分 + 月历 + 天气卡（天气界面先行，实况接口待接入）。

### 关于

自动下载白名单管理（**v9.15 白名单新增 Pixiv 分组**），及底部 GitHub/主题切换等链接。软件信息、界面缩放、保存与 Cookie、数据管理见「系统总览」页。

---

## 🛠️ 安装与运行

> 建议 **Python 3.10+ / Windows 10+**（部分能力仅限 Windows）

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python mainv915.py
```

**关于管理员权限**：默认普通用户启动，需要时可显式提权 `python mainv915.py --as-admin`；目录映射页的 `mklink` 也可单独勾选管理员执行。

**可选环境**
- **NVIDIA**：GPU 监控需 `nvidia-smi` 在 PATH。
- **yt-dlp + yt-dlp-ejs + ffmpeg + Deno/Node.js**：视频下载 B站/YouTube 子页 + 区域录屏需要；`yt-dlp-ejs`（v9.15 新增）用于处理 JS 签名反爬校验，建议随 `yt-dlp` 一同升级。
- **faster-whisper + sounddevice**：语音编辑转写需要，未装则提示安装；转写在独立子进程中加载模型，转写结果自动繁转简（`zhconv`）。
- **rapidocr-onnxruntime**（配 `numpy<2`）：截图工具 OCR 识字（可选），v9.15 起在独立子进程中运行；识别异常可用 `tools/fix_ocr.bat` 一键修复。
- **浏览器扩展（MV41）**：配合速存图文使用。
- **Get cookies.txt LOCALLY（浏览器扩展）**：导出 YouTube / e-hentai / hitomi.la / Pixiv 等站点 Cookie（Netscape 格式），图集下载与部分平台解析需要。
> 磁盘 Treemap、版本信息、「功能与说明」轮播、电子钟均已改用 Qt 原生渲染（QPainter / QTextBrowser / QLabel），不再依赖 PyQtWebEngine。

### 🧩 浏览器扩展（MV41）安装步骤

1. Chrome 地址栏输入 `chrome://extensions/`
2. 打开右上角「开发者模式」
3. 「加载已解压的扩展程序」→ 选择项目 `MV41` 文件夹

---

## 📁 代码结构

```
桌面助手/
├─ mainv915.py                  # 入口（默认普通用户；--as-admin 显式提权；启动前设 QT_SCALE_FACTOR）
│                                 #   --ocr-job / --whisper-job：OCR / 语音转写独立子进程模式
├─ ui_main.py                   # 主窗口 + 侧栏三分区 + 拖拽排序 + 分区改名 + 顶栏（含电子钟入口）
├─ requirements.txt
├─ pages/
│  ├─ page_overview.py          # 系统总览（含设置区 + 预下载卡片 + 功能与说明轮播）
│  ├─ settings_section.py       # 设置区可复用组件（缩放/保存与Cookie/数据管理/预下载）
│  ├─ pre_download_panel.py     # 预下载记录浏览/编辑弹窗（v9.15 新增）
│  ├─ page_fast_save.py         # 速存图文
│  ├─ page_video.py             # 视频下载（Tab 容器 + 统一批量下载 + 预下载角标）
│  ├─ page_douyin.py / page_bilibili.py / page_youtube.py   # 三平台子页
│  ├─ page_gallery.py           # 图集下载（e-hentai/ExHentai + hitomi.la + Pixiv）
│  ├─ page_screenshot.py        # 截图工具（含 OCR 识字，子进程运行）
│  ├─ page_region_record.py     # 区域录屏
│  ├─ page_paste.py             # 粘贴助手
│  ├─ page_image_proc.py        # 图片处理（v9.15 新增：缩小/切割/转格式）
│  ├─ page_voice_input.py       # 语音编辑（本地转写，子进程运行，繁转简）
│  ├─ page_prompt_editor.py     # 提示词编辑器（v9.15 新增：文生视频提示词字段化编辑）
│  ├─ page_points_calc.py       # 积分计算
│  ├─ page_ratio_calc.py / page_dir_link.py / page_timezone_fx.py  # 工具·小偏门
│  ├─ page_clock.py             # 电子钟（v9.15 新增：七段数码时钟+月历+天气卡，顶栏入口）
│  ├─ page_about.py             # 关于（自动下载白名单管理，含 Pixiv）
│  └─ disk_treemap_widget.py    # 磁盘空间 Treemap 可视化
├─ tools/
│  ├─ hitomi_zip_debug.py       # hitomi.la 下载逻辑核实/调试脚本
│  └─ fix_ocr.bat               # OCR 依赖一键修复脚本（v9.15 新增）
├─ utils/                       # 通用工具（文件/日志/布局/语音转写/OCR 等）
│  ├─ download_confirm.py       # 下载前同名文件三选一确认（中止/改名/覆盖）
│  ├─ download_watchdog.py      # 下载防卡死看门狗（180s 无进度即判失败）
│  ├─ pre_download.py           # 预下载队列：六平台 + 无法处理，持久化到 records/pre_download.json（v9.15 新增）
│  ├─ ocr_util.py / ocr_job.py  # 本地 OCR 识字（引擎探测 + 子进程执行）
│  ├─ voice_input.py / whisper_job.py  # 语音转写（本地录音 + 子进程执行）
│  ├─ region_recorder.py        # 区域录屏核心逻辑
│  ├─ qthread_util.py           # 统一安全停止 QThread（关窗清理）
│  ├─ app_paths.py              # 统一路径解析（含 cards_dir 等）
│  ├─ gallery_records.py        # 图集下载记录
│  └─ cursor_toast.py           # 全局鼠标旁轻提示气泡
├─ styles/                      # 主题样式（app.qss / app_light.qss / style_all.py）
├─ guides/                      # 「功能与说明」轮播教程图（最多 12 张）
├─ prompts/                     # 提示词编辑器数据（editor.json 当前稿 / history.jsonl 历史记录，v9.15 新增）
├─ cards/                       # 粘贴助手记录卡（含预下载转出的记录卡）
├─ gallery/                     # 图集下载分平台记录（gallery_eh.txt / gallery_hitomi.txt 等）
├─ records/                     # 运行数据（user.txt / paste_helper.txt / pre_download.json / app.log 等）
└─ MV41/                        # 配套浏览器扩展
```

> 主脑配置、导演台、Ollama 工具、反推生图等 AI 相关页面（`page_brain_config.py`、`page_api_config.py`、`page_model_service.py`、`page_director.py`、`page_ollama_tools.py`、`page_literary_writing.py`、`page_prompt_gen.py`、`utils/llm_client.py`、`utils/mini_brain_client.py`、`utils/ollama_client.py`）已从主程序拆出，将并入独立的「算力版」程序。

---

## ❗ 常见问题

- **`ModuleNotFoundError: No module named 'utils'`** → 从项目根目录运行 `python mainv915.py`。
- **资源监控无 GPU 数据** → 安装 `psutil`；无 NVIDIA 或 `nvidia-smi` 不在 PATH 时显示 0。
- **语音编辑转写无反应** → 需安装 `faster-whisper` + `sounddevice`，首次使用可能联网下载模型；转写在独立子进程中加载，若子进程启动失败请查看日志。
- **B站 / YouTube 无法解析** → 需安装 `yt-dlp`（建议同时装 `yt-dlp-ejs` 应对 JS 签名反爬）；合并/转 mp3 需 `ffmpeg`；JS 挑战需 `Deno`/Node.js。
- **图集下载访问 ExHentai / hitomi.la / Pixiv 失败** → 需导入有效 Netscape 格式 Cookie；hitomi.la 的分片直链逻辑可用 `tools/hitomi_zip_debug.py` 单独核实；Pixiv 需先在站内登录后导出 Cookie。
- **下载一直卡在某一条不动** → 已有防卡死看门狗，180 秒无新数据会自动判定失败并跳过；若仍长时间无响应，请检查网络或站点是否失效。
- **下载提示"已存在同名文件"** → 弹窗默认 10 秒后自动中止，也可手动选择改名或覆盖；此确认对视频下载与图集下载均生效。
- **预下载队列不自动继续 / 一直停着** → 确认系统总览「预下载」卡片开关是否已打开；本机若未加载对应平台 Cookie，启动时会警告并自动关闭该开关；也可点「预处理文件」手动查看/编辑队列。
- **调整界面缩放后重启没生效** → v9.13 曾有该 bug，已在入口文件中修复；仍异常可检查 `records/user.txt` 里 `ui.scale` 是否写入正确。
- **速存图片插件状态灯黄/红** → 黄=等待连接或心跳超时；红=端口占用或 Chrome 未运行，确认以管理员权限运行或放行安全软件白名单。
- **截图 OCR 无法识字** → 需安装 `rapidocr-onnxruntime`（与 `numpy<2` 搭配）；可运行 `tools/fix_ocr.bat` 一键修复，或到「截图工具」内点「检测/修复」。
- **找不到「图片处理」「提示词编辑器」「电子钟」** → 图片处理、提示词编辑器在侧栏「助手 · 主手脚」区；电子钟不在侧栏，点击顶栏时钟图标进入。

---

## ✅ 开发规范

- **样式与逻辑分离**：视觉样式写入 `assets/*.qss` 与 `styles/style_all.py`；布局与业务逻辑写在 Python。
- **优雅降级**：`psutil` / `nvidia-smi` / `yt-dlp` / `faster-whisper` 不可用时提示但不崩溃。
- **Windows 依赖隔离**：`pywin32`、WinAPI 相关代码均有 `try/except` 保护。
- **子进程隔离**：OCR、语音转写等易与主进程 Qt/OpenMP 抢占 DLL 的能力，统一放到独立子进程（`--ocr-job` / `--whisper-job`）执行。
- **后台线程与关窗清理**：涉及定时器/`QThread` 的页面需在 `ui_main.py` 的 `closeEvent` 统一停止，见 `utils/qthread_util.py`。
- **持久化原子写入**：用户配置「写 `.tmp` + `os.replace`」，见 `utils/user_prefs.py`。

---

## 📜 版本历史

| 版本 | 主要内容 |
| --- | --- |
| **v9.15 (当前)** | 图集下载新增 Pixiv 支持；新增「图片处理」「提示词编辑器」两个助手区页面；新增顶栏「电子钟」入口；「预下载」体系重构（剪贴板白名单→六平台+无法处理队列，系统总览新增预下载卡片，下载页签显示排队角标，记录可转出为粘贴助手卡片）；截图 OCR 与语音转写改为独立子进程运行，减少 DLL 冲突；新增 `yt-dlp-ejs` 依赖；入口改为 `mainv915.py`。 |
| **v9.14** | 设置区（软件信息/界面缩放/保存与Cookie/数据管理）从「关于」页迁移到「系统总览」页，并新增「功能与说明」图文轮播卡；图集下载新增 hitomi.la 支持；下载新增同名文件确认与防卡死看门狗；新增全局鼠标提示气泡；侧栏默认分区调整（截图/录屏入置顶）；修复界面缩放重启失效的 bug；语音编辑转写结果自动繁转简。 |
| **v9.13** | Ollama/API 相关的主脑配置、导演台、Ollama 工具、反推生图等 AI 页面从主程序拆分，后续独立为「算力版」程序；侧栏主按钮支持跨分区拖拽排序 + 分区改名；视频下载新增 B站子页与跨平台统一批量下载；新增「语音编辑」（本地转写）。 |
| **v9.12** | 版本号升级至 v9.12，入口改为 `mainv912.py`。 |
| **v9.11** | 主大脑配置改为顶栏「本地/API」开关 + ⚙ 弹窗；模型条与粘贴助手 UI 打磨；抖音解析软过滤兜底；关于页可点 GitHub、复制联系方式。 |
| **v9.10** | 抖音下载升级为多平台视频下载（+YouTube）；新增图集下载；新增模型选择全局主大脑；侧栏三分区重排；默认普通用户启动。 |
| **v9.9** | 新增粘贴助手、导演台、文学写作；反推提示词与批量打标合并为 Ollama 工具；抖音新增一键粘贴解析；速存图文改 WebSocket 心跳。 |
| **v9.8** | 新增抖音无水印解析、积分计算、图形化目录映射与磁盘分析；速存图文新增插件直连。 |
| **v9.5** | 样式体系统一；速存图文后台常驻；批量打标真实接入 Ollama。 |
| **v9.0** | 主题与字体统一；系统总览资源监控；反推提示词、比例计算、批量打标上线。 |
| **v8.1** | 速存图文自动/手动模式；截图工具热键框选；Ollama 助理流式聊天。 |
