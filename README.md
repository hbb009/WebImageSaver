# 网页图片 + 文本笔记保存器 WebImageSaver

> 一个用于快速保存网页图片和相关文字说明的小工具，适用于写作、收图、资料整理等日常任务。

> A handy tool for quickly saving web images and their related textual notes, perfect for writing, collecting, and research.

---

## 🌟 功能特色 Features

- 🖱️ 【Alt + 左键】快速保存网页图片（非截图，直接下载原图）
- 📋 【右键复制图片】自动保存剪贴板中的图片
- 📝 【复制文字】自动生成与图片同名的 `.txt` 说明文档
- 🗂️ 可视化界面 + 自定义保存路径
- 📋 支持浏览器扩展（Chrome 插件），增强网页交互体验

---

## 📦 使用方式 How to Use

### ✅ 方法一：直接运行 Python 源码（需安装 Python 3.10+）

1. 安装依赖：
    ```bash
    pip install flask pillow pyqt5
    ```

2. 运行主程序：
    ```bash
    python main.py
    ```

3. 浏览器中加载扩展：
    - 打开 Chrome 的扩展程序页面 `chrome://extensions/`
    - 打开“开发者模式”
    - 点击“加载已解压的扩展程序”
    - 选择 `chrome_image_saver_configurable` 目录

4. 使用方法：
    - 将鼠标放在网页图片上 → 按下【Alt + 左键】
    - 或者在图片上右键 → 选择“复制图片”
    - 再复制任意文字（图片保存后）→ 自动写入文本

---

### ✅ 方法二：打包成可执行文件（.exe）

1. 安装 pyinstaller：
    ```bash
    pip install pyinstaller
    ```

2. 打包程序：
    ```bash
    pyinstaller --onefile --noconsole main.py
    ```

3. 打包完成后，会生成 `dist/main.exe`，双击即可运行。

---

## 🧩 项目结构 Project Structure

