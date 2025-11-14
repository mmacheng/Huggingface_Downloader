import sys
import os
import subprocess
import threading
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QListWidget,
    QListWidgetItem, QCheckBox, QProgressBar, QTextEdit, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor
from huggingface_hub import HfApi

def resource_path(relative_path):
    """获取资源文件的绝对路径，适用于 PyInstaller 打包后的环境"""
    try:
        # PyInstaller 创建的临时文件夹
        base_path = sys._MEIPASS
    except Exception:
        # 普通运行环境
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class DownloadWorker(QThread):
    progress = pyqtSignal(int, str)  # 进度百分比, 当前文件名
    finished = pyqtSignal()          # 所有文件成功下载完成
    cancelled = pyqtSignal()         # 用户主动取消下载
    paused = pyqtSignal()            # 用户暂停下载
    resumed = pyqtSignal()           # 用户继续下载
    error = pyqtSignal(str)          # 下载过程中发生错误

    def __init__(self, repo_id, local_dir, selected_files, speed_limit=None):
        super().__init__()
        self.repo_id = repo_id
        self.local_dir = local_dir
        self.selected_files = selected_files
        self.speed_limit = speed_limit  # 如 "500K", "2M", None 表示不限速
        self.running = True  # 用于控制线程
        self.is_paused = False  # 新增：暂停状态
        self.pause_requested = threading.Event()  # 用于线程同步
        self.pause_requested.set()  # 初始为运行状态

        # 用于存储当前正在下载的进程
        self.current_process = None

    def run(self):
        total = len(self.selected_files)
        if total == 0:
            self.finished.emit()
            return

        # 从 repo_id 中提取模型名（去掉用户名部分）
        model_name = self.repo_id.split("/")[-1]
        # 创建最终的下载目录
        final_dir = os.path.join(self.local_dir, model_name)
        os.makedirs(final_dir, exist_ok=True)

        # 查找 aria2c.exe 的路径
        aria2c_path = resource_path("aria2c.exe")

        if not os.path.exists(aria2c_path):
            self.error.emit(f"未找到 aria2c.exe: {aria2c_path}")
            return

        for i, file_path in enumerate(self.selected_files):
            if not self.running:
                # 用户点击了“停止”，优雅退出，不视为错误或完成
                self.cancelled.emit()
                return

            try:
                # 构造下载 URL
                url = f"https://huggingface.co/{self.repo_id}/resolve/main/{file_path}"
                # 构造本地保存路径（在模型名子目录下）
                full_path = os.path.join(final_dir, file_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)

                # 构建 aria2c 命令
                cmd = [
                    aria2c_path,  # 使用找到的路径
                    "-x", "16",
                    "-s", "16",
                    "-j", "5",
                    "--continue=true",
                    "--dir", os.path.dirname(full_path),
                    "--out", os.path.basename(full_path),
                    url
                ]

                if self.speed_limit:
                    cmd.extend(["--max-download-limit", self.speed_limit])

                # 启动进程，并隐藏控制台窗口 👇
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW  # ✅ 关键：隐藏终端窗口
                )

                # 存储当前进程，以便在暂停时可以控制它
                self.current_process = process

                # 实时读取输出，用于检查进程是否仍在运行
                while True:
                    if not self.running:
                        process.terminate()
                        break

                    # 检查暂停状态
                    if self.is_paused and self.running:
                        # 不终止进程，只是暂停处理进度
                        # 让 aria2c 继续运行，Python 线程等待
                        self.pause_requested.wait()  # 等待恢复
                        if not self.running:
                            process.terminate()
                            self.cancelled.emit()
                            return
                        # 恢复后，继续读取输出
                        continue

                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        # 可选：打印调试信息
                        # print(output.strip())
                        pass

                # 等待进程结束
                return_code = process.wait()

                # 如果是用户主动停止，return_code 可能为 1，但不应视为错误
                if return_code != 0 and self.running:
                    # 只有在不是用户主动停止的情况下才视为错误
                    stderr_output = process.stderr.read()
                    raise Exception(f"aria2c 下载失败 (退出码 {return_code}): {stderr_output}")

                # 更新进度
                percent = int((i + 1) / total * 100)
                self.progress.emit(percent, file_path)

            except Exception as e:
                # 只有在不是用户主动停止的情况下才发送错误信号
                if self.running:
                    self.error.emit(f"下载失败: {file_path}\n错误: {str(e)}")
                    return

        # 所有文件都成功下载完毕
        self.finished.emit()

    def stop(self):
        self.running = False
        self.is_paused = False  # 确保暂停状态被清除
        self.pause_requested.set()  # 唤醒任何等待的线程
        if self.current_process:
            self.current_process.terminate()

    def pause(self):
        if self.running and not self.is_paused:
            self.is_paused = True
            self.pause_requested.clear()  # 清除事件，使 wait() 阻塞
            self.paused.emit()

    def resume(self):
        if self.running and self.is_paused:
            self.is_paused = False
            self.pause_requested.set()  # 设置事件，使 wait() 唤醒
            self.resumed.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hugging Face 模型文件选择下载器")
        self.setGeometry(300, 200, 1000, 750)
        self.setStyleSheet(self.get_stylesheet())

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 标题区域
        title_label = QLabel("📥 Hugging Face 模型文件选择下载器")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2c3e50; padding: 15px; background-color: #ecf0f1; border-radius: 8px;")
        main_layout.addWidget(title_label)

        # 配置区域
        config_group = QGroupBox("配置")
        config_layout = QGridLayout()
        config_layout.setSpacing(10)

        # Repo ID 输入
        repo_label = QLabel("模型仓库ID:")
        repo_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        repo_label.setStyleSheet("color: #2d3436;")
        self.repo_input = QLineEdit("请输入项目ID-例如：MiniMaxAI/MiniMax-M2")
        self.repo_input.setFont(QFont("Consolas", 10))
        self.repo_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                background-color: #ffffff;
                color: #2d3436;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
            }
        """)
        config_layout.addWidget(repo_label, 0, 0)
        config_layout.addWidget(self.repo_input, 0, 1, 1, 2)

        # 本地目录选择
        dir_label = QLabel("保存路径:")
        dir_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        dir_label.setStyleSheet("color: #2d3436;")
        self.dir_input = QLineEdit("./downloaded_model")
        self.dir_input.setFont(QFont("Consolas", 10))
        self.dir_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                background-color: #ffffff;
                color: #2d3436;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
            }
        """)
        browse_btn = QPushButton("📁 浏览...")
        browse_btn.clicked.connect(self.browse_directory)
        config_layout.addWidget(dir_label, 1, 0)
        config_layout.addWidget(self.dir_input, 1, 1)
        config_layout.addWidget(browse_btn, 1, 2)

        # 限速设置
        speed_label = QLabel("限速:")
        speed_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        speed_label.setStyleSheet("color: #2d3436;")
        self.speed_input = QLineEdit()
        self.speed_input.setPlaceholderText("如 500K, 2M (留空则不限速)")
        self.speed_input.setFont(QFont("Consolas", 10))
        self.speed_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                background-color: #ffffff;
                color: #2d3436;
            }
            QLineEdit:focus {
                border: 2px solid #3498db;
            }
            QLineEdit:disabled {
                background-color: #f8f9fa;
                color: #6c757d;
            }
        """)
        self.speed_checkbox = QCheckBox("启用限速")
        self.speed_checkbox.setStyleSheet("""
            QCheckBox {
                color: #2d3436;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #bdc3c7;
                border-radius: 3px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #27ae60;
                border-radius: 3px;
                background-color: #27ae60;
            }
        """)
        self.speed_checkbox.stateChanged.connect(self.on_speed_checkbox_changed)
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(self.speed_checkbox)
        speed_layout.addWidget(self.speed_input)
        config_layout.addWidget(speed_label, 2, 0)
        config_layout.addLayout(speed_layout, 2, 1, 1, 2)

        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)

        # 加载按钮
        load_btn = QPushButton("🔍 加载文件列表")
        load_btn.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        load_btn.setStyleSheet(self.get_button_style("#3498db"))
        load_btn.clicked.connect(self.load_file_list)
        main_layout.addWidget(load_btn)

        # 选择文件区域（恢复为原始样式）
        file_group = QGroupBox("选择文件")
        file_layout = QVBoxLayout()
        file_layout.addWidget(QLabel("✅ 请勾选要下载的文件："))

        # 文件列表（使用原始样式，确保所有文件可见）
        self.file_list_widget = QListWidget()
        self.file_list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        # 不设置自定义样式，保持系统默认，确保兼容性和可读性
        file_layout.addWidget(self.file_list_widget)

        # 添加统计标签（只显示总文件数量）
        self.file_count_label = QLabel("共 0 个文件")
        self.file_count_label.setFont(QFont("Arial", 9))
        self.file_count_label.setStyleSheet("color: #6c757d;")
        file_layout.addWidget(self.file_count_label)

        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        # 进度和状态区域
        progress_group = QGroupBox("下载状态")
        progress_layout = QVBoxLayout()

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                text-align: center;
                height: 20px;
                font-weight: bold;
                color: #2d3436;
            }
            QProgressBar::chunk {
                background-color: #27ae60;
                width: 20px;
            }
        """)
        progress_layout.addWidget(QLabel("进度:"))
        progress_layout.addWidget(self.progress_bar)

        # 状态文本框
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(150)
        self.status_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 9pt;
                color: #2d3436;
            }
        """)
        progress_layout.addWidget(QLabel("日志:"))
        progress_layout.addWidget(self.status_text)

        progress_group.setLayout(progress_layout)
        main_layout.addWidget(progress_group)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # 开始/暂停/继续下载按钮
        self.download_btn = QPushButton("🚀 开始下载")
        self.download_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.download_btn.setStyleSheet(self.get_button_style("#27ae60"))
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setEnabled(False)
        button_layout.addWidget(self.download_btn)

        # 停止下载按钮
        self.stop_btn = QPushButton("⏹️ 停止下载")
        self.stop_btn.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.stop_btn.setStyleSheet(self.get_button_style("#e74c3c"))
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)

        main_layout.addLayout(button_layout)

        # 初始化变量
        self.file_paths = []
        self.worker = None

    def get_stylesheet(self):
        """返回应用的整体样式表"""
        return """
            QMainWindow {
                background-color: #f8f9fa;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                background-color: #dfe6e9;
                color: #2d3436;
                border-radius: 4px;
            }
            QLabel {
                color: #2d3436;
                font-family: Arial, sans-serif;
            }
            /* 修复弹窗文字颜色 */
            QMessageBox {
                background-color: #ffffff;
                color: #2d3436;
            }
            QMessageBox QLabel {
                color: #2d3436;
            }
            QMessageBox QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
            }
            QMessageBox QPushButton:hover {
                background-color: #2980b9;
            }
        """

    def get_button_style(self, color):
        """返回按钮样式"""
        return f"""
            QPushButton {{
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                color: white;
                background-color: {color};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.darken_color(color)};
            }}
            QPushButton:pressed {{
                background-color: {self.darken_color(self.darken_color(color))};
            }}
            QPushButton:disabled {{
                background-color: #bdc3c7;
                color: #6c757d;
            }}
        """

    def darken_color(self, color):
        """辅助函数：将颜色变暗一点"""
        color = color.lstrip('#')
        rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        darkened_rgb = tuple(max(0, c - 30) for c in rgb)
        return f"#{darkened_rgb[0]:02x}{darkened_rgb[1]:02x}{darkened_rgb[2]:02x}"

    def on_speed_checkbox_changed(self, state):
        self.speed_input.setEnabled(state == Qt.CheckState.Checked.value)

    def browse_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if folder:
            self.dir_input.setText(folder)

    def load_file_list(self):
        repo_id = self.repo_input.text().strip()
        if not repo_id:
            QMessageBox.warning(self, "错误", "请输入模型仓库ID！")
            return

        self.status_text.clear()
        self.status_text.append("⏳ 正在加载文件列表...")

        try:
            api = HfApi()
            files = api.list_repo_files(repo_id=repo_id)
            self.file_paths = files

            self.file_list_widget.clear()
            for file_path in files:
                item = QListWidgetItem()
                checkbox = QCheckBox(file_path)
                checkbox.setChecked(True)
                # 不设置自定义样式，保持默认
                item.setSizeHint(checkbox.sizeHint())
                self.file_list_widget.addItem(item)
                self.file_list_widget.setItemWidget(item, checkbox)

            # 只显示总文件数量
            self.file_count_label.setText(f"共 {len(files)} 个文件")

            self.status_text.append(f"✅ 成功加载 {len(files)} 个文件")
            self.download_btn.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载文件列表失败:\n{str(e)}")
            self.status_text.append(f"❌ 错误: {str(e)}")

    def start_download(self):
        repo_id = self.repo_input.text().strip()
        local_dir = self.dir_input.text().strip()

        if not repo_id or not local_dir:
            QMessageBox.warning(self, "错误", "请填写仓库ID和本地路径！")
            return

        # 获取选中的文件
        selected_files = []
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            widget = self.file_list_widget.itemWidget(item)
            if isinstance(widget, QCheckBox) and widget.isChecked():
                selected_files.append(widget.text())

        if not selected_files:
            QMessageBox.information(self, "提示", "没有选择任何文件！")
            return

        # 获取限速值
        speed_limit = None
        if self.speed_checkbox.isChecked():
            speed_limit = self.speed_input.text().strip()
            if speed_limit and not any(c in speed_limit.upper() for c in ['K', 'M', 'G']):
                QMessageBox.warning(self, "警告", "限速格式错误！请使用如 500K, 2M")
                return

        # 创建下载线程
        self.worker = DownloadWorker(repo_id, local_dir, selected_files, speed_limit)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.download_finished)
        self.worker.cancelled.connect(self.download_cancelled)
        self.worker.paused.connect(self.download_paused)
        self.worker.resumed.connect(self.download_resumed)
        self.worker.error.connect(self.download_error)
        self.worker.start()

        # 更新按钮状态：开始下载 -> 暂停下载
        self.download_btn.setText("⏸️ 暂停下载")
        self.download_btn.clicked.disconnect()
        self.download_btn.clicked.connect(self.pause_download)
        self.stop_btn.setEnabled(True)
        # 显示即将创建的模型文件夹名
        model_name = repo_id.split("/")[-1]
        self.status_text.append(f"⏳ 开始下载 {len(selected_files)} 个文件到子目录: {model_name}")

    def update_progress(self, percent, current_file):
        self.progress_bar.setValue(percent)
        self.status_text.append(f"📦 正在下载: {current_file} ({percent}%)")

    def pause_download(self):
        if self.worker:
            self.worker.pause()
            self.status_text.append("⏸️ 用户请求暂停下载...")

    def resume_download(self):
        if self.worker:
            self.worker.resume()
            self.status_text.append("▶️ 用户请求继续下载...")

    def stop_download(self):
        if self.worker and self.worker.running:
            self.worker.stop()
            self.status_text.append("🛑 用户请求停止下载...")

    def download_paused(self):
        # 用户主动暂停下载
        self.status_text.append("⏸️ 下载已暂停。")
        # 更新按钮状态：暂停下载 -> 继续下载
        self.download_btn.setText("▶️ 继续下载")
        self.download_btn.clicked.disconnect()
        self.download_btn.clicked.connect(self.resume_download)

    def download_resumed(self):
        # 用户主动继续下载
        self.status_text.append("▶️ 下载已继续。")
        # 更新按钮状态：继续下载 -> 暂停下载
        self.download_btn.setText("⏸️ 暂停下载")
        self.download_btn.clicked.disconnect()
        self.download_btn.clicked.connect(self.pause_download)

    def download_finished(self):
        self.progress_bar.setValue(100)
        self.status_text.append("🎉 所有文件下载完成！")
        QMessageBox.information(self, "成功", "所有选中文件已下载完毕！")
        # 恢复初始按钮状态
        self.download_btn.setText("🚀 开始下载")
        self.download_btn.clicked.disconnect()
        self.download_btn.clicked.connect(self.start_download)
        self.stop_btn.setEnabled(False)

    def download_cancelled(self):
        # 用户主动取消下载
        self.status_text.append("⏸️ 下载已由用户取消。")
        # 恢复初始按钮状态
        self.download_btn.setText("🚀 开始下载")
        self.download_btn.clicked.disconnect()
        self.download_btn.clicked.connect(self.start_download)
        self.stop_btn.setEnabled(False)

    def download_error(self, error_msg):
        self.status_text.append(f"❌ 下载出错: {error_msg}")
        QMessageBox.critical(self, "错误", f"下载过程中发生错误:\n{error_msg}")
        # 恢复初始按钮状态
        self.download_btn.setText("🚀 开始下载")
        self.download_btn.clicked.disconnect()
        self.download_btn.clicked.connect(self.start_download)
        self.stop_btn.setEnabled(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 使用 Fusion 风格，看起来更现代

    # 应用全局样式（可选，如果上面的 stylesheet 已经包含，可省略）
    # app.setStyleSheet("""
    #     QMessageBox {
    #         background-color: #ffffff;
    #         color: #2d3436;
    #     }
    #     QMessageBox QLabel {
    #         color: #2d3436;
    #     }
    #     QMessageBox QPushButton {
    #         background-color: #3498db;
    #         color: white;
    #         padding: 8px 16px;
    #         border-radius: 5px;
    #         font-weight: bold;
    #     }
    #     QMessageBox QPushButton:hover {
    #         background-color: #2980b9;
    #     }
    # """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())