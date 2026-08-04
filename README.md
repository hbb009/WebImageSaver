<img width="1521" height="1298" alt="0ecfc147bb2ea34b3d5652f10deeba5f" src="https://github.com/user-attachments/assets/7000e121-0b95-43d2-9daf-f157989806ff" />

# 桌面助手 v9.13 · 给 AI 人的口袋瑞士军刀 🔧🧠

> 让每一个操作，都能为您省下宝贵的时间

---

## 🆕 v9.13 主要调整

1. **Ollama / API 相关功能已拆分**：主脑配置、导演台、Ollama 工具（文学/反推/打标）、反推生图等 AI 大模型能力从主程序中拆出，后续将单独打包为「算力版」独立程序，本包不再收录。
2. **侧栏主按钮支持拖拽排序**：按住可跨分区拖动调整顺序，分区标题也可自行改名，改动即时生效并自动保存，重启保留。

---

## 🗂️ 功能模块

侧边栏分三区：**置顶常用** → **助手 · 主手脚** → **工具 · 小偏门**（靠下），底部为「关于」。
> 侧栏按钮可**按住拖拽排序**（可跨分区自由摆放），分区标题可自定义改名，顺序与命名自动保存到 `records/user.txt`。

### 置顶常用

- **🖥️ 系统总览**：显示环境信息（设备名 / 处理器 / 机带 RAM / 系统类型与版本 / Python 版本 / 磁盘空间）与资源监控（GPU 使用率、显存、内存、CPU、GPU 温度、GPU 功耗、硬盘使用，实时刷新百分比+进度条）；下方版本信息区读取项目根目录 `README.md` 展示更新日志。
- **📥 速存图文**：配套浏览器插件，图片悬停按快捷键静默保存、文本全局快捷键提取，自动分类建目录；开关一键启停「速存全功能」。
- **🎬 视频下载**：抖音 / B站 / YouTube 三个 Tab 子页，支持解析下载与统一跨平台批量下载；开关为「自动下载」——剪贴板复制到对应平台链接时后台静默解析下载。
- **🖼️ 图集下载**：粘贴漫画/图站网址批量抓图，优先支持 e-hentai/ExHentai；开关同样是「自动下载」，复制图集链接即后台触发。

### 助手 · 主手脚

- **✂️ 截图工具**：自定义热键框选截图，自动存图/转格式/复制剪贴板；开关为「截图监听」一键开/关热键。
- **⏺ 区域录屏**：热键定位/调整选区后开录，热键停止保存；按钮旁圆点在录制中显示红点提示。
- **📝 粘贴助手**：主题 + 内容 + 七色标签存为卡片，流式布局可拖拽排序，点击复制并载入编辑区。
- **🎙 语音编辑**：本地语音转文字，转写结果进主编辑区改字、分段、排版后一键复制。
- **💰 积分计算**：按订阅金额、汇率、单次消耗积分，折算单图/单秒视频的真实成本，历史可保存。

### 工具 · 小偏门

- **比例计算**：常用画幅像素换算，附金额大小写转换。
- **目录映射**：图形化软链接创建，附磁盘空间 Treemap 可视化。
- **时区汇率**：多城市模拟时钟（可增删/可模拟时间）+ 汇率转换器。

### 关于

软件信息、GitHub/联系方式、自动下载白名单管理，及主题切换（右下角）。

---

## 🛠️ 安装与运行

> 建议 **Python 3.10+ / Windows 10+**（部分能力仅限 Windows）

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python mainv913.py
```

**关于管理员权限**：默认普通用户启动，需要时可显式提权 `python mainv913.py --as-admin`；目录映射页的 `mklink` 也可单独勾选管理员执行。

**可选环境**
- **NVIDIA**：GPU 监控需 `nvidia-smi` 在 PATH。
- **PyQtWebEngine**：磁盘 Treemap 需要，未装则降级提示。
- **yt-dlp + ffmpeg + Deno/Node.js**：视频下载 B站/YouTube 子页 + 区域录屏需要。
- **faster-whisper + sounddevice**：语音编辑转写需要，未装则提示安装。
- **rapidocr-onnxruntime**：截图工具 OCR 识字（可选）。
- **浏览器扩展（MV4）**：配合速存图文使用。

### 🧩 浏览器扩展（MV4）安装步骤

1. Chrome 地址栏输入 `chrome://extensions/`
2. 打开右上角「开发者模式」
3. 「加载已解压的扩展程序」→ 选择项目 `MV4` 文件夹

---

## 📁 代码结构

```
桌面助手/
├─ mainv913.py                  # 入口（默认普通用户；--as-admin 显式提权）
├─ ui_main.py                   # 主窗口 + 侧栏三分区 + 拖拽排序 + 分区改名
├─ requirements.txt
├─ pages/
│  ├─ page_overview.py          # 系统总览
│  ├─ page_fast_save.py         # 速存图文
│  ├─ page_video.py             # 视频下载（Tab 容器 + 统一批量下载）
│  ├─ page_douyin.py / page_bilibili.py / page_youtube.py   # 三平台子页
│  ├─ page_gallery.py           # 图集下载
│  ├─ page_screenshot.py        # 截图工具
│  ├─ page_region_record.py     # 区域录屏
│  ├─ page_paste.py             # 粘贴助手
│  ├─ page_voice_input.py       # 语音编辑（本地转写）
│  ├─ page_points_calc.py       # 积分计算
│  ├─ page_ratio_calc.py / page_dir_link.py / page_timezone_fx.py  # 工具·小偏门
│  ├─ page_about.py             # 关于（含自动下载白名单管理）
│  └─ ollama_model_bar.py       # 模型下拉栏组件（供拆分模块复用）
├─ utils/                       # 通用工具（文件/日志/布局/语音转写等）
├─ styles/                      # 主题样式（app.qss / app_light.qss / style_all.py）
├─ records/                     # 运行数据（user.txt / paste_helper.txt / app.log 等）
└─ MV4/                         # 配套浏览器扩展
```

> 主脑配置、导演台、Ollama 工具、反推生图等 AI 相关页面（`page_brain_config.py`、`page_api_config.py`、`page_model_service.py`、`page_director.py`、`page_ollama_tools.py`、`page_literary_writing.py`、`page_prompt_gen.py`、`utils/llm_client.py`、`utils/mini_brain_client.py`、`utils/ollama_client.py`）已从主程序拆出，将并入独立的「算力版」程序。

---

## ❗ 常见问题

- **`ModuleNotFoundError: No module named 'utils'`** → 从项目根目录运行 `python mainv913.py`。
- **资源监控无 GPU 数据** → 安装 `psutil`；无 NVIDIA 或 `nvidia-smi` 不在 PATH 时显示 0。
- **语音编辑转写无反应** → 需安装 `faster-whisper` + `sounddevice`，首次使用可能联网下载模型。
- **B站 / YouTube 无法解析** → 需安装 `yt-dlp`；合并/转 mp3 需 `ffmpeg`；JS 挑战需 `Deno`/Node.js。
- **图集下载访问 ExHentai 失败** → 需导入有效 Netscape 格式 Cookie。
- **速存图片插件状态灯黄/红** → 黄=等待连接或心跳超时；红=端口占用或 Chrome 未运行，确认以管理员权限运行或放行安全软件白名单。
- **截图 OCR 无法识字** → 需安装 `rapidocr-onnxruntime`（与 `numpy<2` 搭配），或到「关于」页一键修复。

---

## ✅ 开发规范

- **样式与逻辑分离**：视觉样式写入 `assets/*.qss` 与 `styles/style_all.py`；布局与业务逻辑写在 Python。
- **优雅降级**：`psutil` / `nvidia-smi` / `PyQtWebEngine` / `yt-dlp` / `faster-whisper` 不可用时提示但不崩溃。
- **Windows 依赖隔离**：`pywin32`、WinAPI 相关代码均有 `try/except` 保护。
- **后台线程与关窗清理**：涉及定时器/`QThread` 的页面需在 `ui_main.py` 的 `closeEvent` 统一停止。
- **持久化原子写入**：用户配置「写 `.tmp` + `os.replace`」，见 `utils/user_prefs.py`。

---

## 📜 版本历史

| 版本 | 主要内容 |
| --- | --- |
| **v9.13 (当前)** | Ollama/API 相关的主脑配置、导演台、Ollama 工具、反推生图等 AI 页面从主程序拆分，后续独立为「算力版」程序；侧栏主按钮支持跨分区拖拽排序 + 分区改名；视频下载新增 B站子页与跨平台统一批量下载；新增「语音编辑」（本地转写）。 |
| **v9.12** | 版本号升级至 v9.12，入口改为 `mainv912.py`。 |
| **v9.11** | 主大脑配置改为顶栏「本地/API」开关 + ⚙ 弹窗；模型条与粘贴助手 UI 打磨；抖音解析软过滤兜底；关于页可点 GitHub、复制联系方式。 |
| **v9.10** | 抖音下载升级为多平台视频下载（+YouTube）；新增图集下载；新增模型选择全局主大脑；侧栏三分区重排；默认普通用户启动。 |
| **v9.9** | 新增粘贴助手、导演台、文学写作；反推提示词与批量打标合并为 Ollama 工具；抖音新增一键粘贴解析；速存图文改 WebSocket 心跳。 |
| **v9.8** | 新增抖音无水印解析、积分计算、图形化目录映射与磁盘分析；速存图文新增插件直连。 |
| **v9.5** | 样式体系统一；速存图文后台常驻；批量打标真实接入 Ollama。 |
| **v9.0** | 主题与字体统一；系统总览资源监控；反推提示词、比例计算、批量打标上线。 |
| **v8.1** | 速存图文自动/手动模式；截图工具热键框选；Ollama 助理流式聊天。 |
