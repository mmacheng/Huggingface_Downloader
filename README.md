# Hugging Face 模型文件选择下载器

一个功能强大且用户友好的图形界面工具，用于从 Hugging Face Hub 下载模型文件。

## ✨ 功能特性

*   **图形化界面 (GUI)**：使用 PyQt6 构建，操作直观便捷。
*   **选择性下载**：加载模型仓库中的所有文件列表，可手动勾选需要下载的文件。
*   **自动创建模型文件夹**：下载时自动创建以模型名命名的子文件夹（如 `Qwen3-VL-8B-NSFW-Caption-V4.5`），方便管理。
*   **下载控制**：
    *   **暂停 / 继续**：支持暂停下载并在之后继续，利用 `aria2c` 的断点续传功能。
    *   **停止**：完全取消当前下载任务。
*   **限速下载**：通过集成 `aria2c` 支持设置下载速度上限（如 `500K`, `2M`）。
*   **实时进度显示**：清晰展示下载进度百分比和当前文件名。
*   **状态日志**：记录下载过程中的详细状态信息。

## 📋 依赖

*   Python 3.8+
*   `huggingface_hub`
*   `PyQt6`
*   `tqdm`
*   `requests`
*   `aria2c` (下载引擎)

## 🚀 快速开始

### 方法一：使用源代码运行

1.  **克隆仓库**：
    ```bash
    git clone https://github.com/YOUR_USERNAME/Huggingface_Downloader.git
    cd Huggingface_Downloader
    ```

2.  **安装依赖**：
    ```bash
    pip install -r requirements.txt
    ```
    *   **注意**：请确保你的 Python 环境中只安装了 `requirements.txt` 中列出的库，避免引入 `PyQt5`、`numpy`、`matplotlib` 等可能干扰 PyInstaller 打包的库。

3.  **下载 `aria2c.exe`**：
    *   从 [aria2 Releases](https://github.com/aria2/aria2/releases/latest) 下载 `aria2c.exe`。
    *   将 `aria2c.exe` 和 `hf_model_downloader_gui.py` 放在同一目录下。

4.  **运行脚本**：
    ```bash
    python hf_model_downloader_gui.py
    ```

### 方法二：使用预编译的 `.exe` 文件

*   从 [Releases](https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME/releases) 页面下载最新的 `HF_Model_Downloader.exe`。
*   将 `HF_Model_Downloader.exe` 和 `aria2c.exe` 放在同一目录下。
*   双击 `HF_Model_Downloader.exe` 即可运行。

## 📝 使用说明

1.  在 "模型仓库ID" 输入框中输入目标仓库 ID（例如 `thesby/Qwen3-VL-8B-NSFW-Caption-V4.5`）。
2.  点击 "浏览..." 选择本地保存路径。
3.  点击 "🔍 加载文件列表" 获取仓库中的所有文件。
4.  在文件列表中勾选你想要下载的文件。
5.  （可选）勾选 "启用限速" 并设置限速值。
6.  点击 "🚀 开始下载"。
7.  下载过程中可以点击 "⏸️ 暂停下载" 或 "⏹️ 停止下载"。

## 🛠️ 打包为 `.exe`

如果你需要自己打包 `.exe` 文件，请参考以下步骤：

1.  **确保虚拟环境纯净**：只安装 `requirements.txt` 中的库，**不要安装 `PyQt5`, `numpy`, `matplotlib` 等大型库**。
2.  **使用稳定版 PyInstaller**：建议使用 `PyInstaller==5.13.2`，避免使用 6.x 版本可能带来的打包问题。
    ```bash
    pip install pyinstaller==5.13.2
    ```
3.  **执行打包命令**：
    ```bash
    pyinstaller --onefile --windowed --add-data "aria2c.exe;." --icon icon.ico --name "HF_Model_Downloader" --exclude-module PyQt5 hf_model_downloader_gui.py
    ```
    *   `--exclude-module PyQt5` 参数可以进一步防止 PyInstaller 检测到系统中的 PyQt5。

## 🤝 贡献

欢迎提交 Issues 和 Pull Requests 来改进这个项目。

## 📄 许可证

请在此处添加你的项目许可证（例如 MIT, Apache 2.0 等）。
