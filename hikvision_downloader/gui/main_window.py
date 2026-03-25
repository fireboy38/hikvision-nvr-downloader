# 海康NVR批量录像下载工具 - 主窗口（SDK版）
import sys
import os
import json
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QSpinBox, QDateTimeEdit, QProgressBar, QTextEdit,
    QGroupBox, QFormLayout, QDialog, QDialogButtonBox, QMessageBox,
    QFileDialog, QStatusBar, QMenuBar, QMenu, QAction, QToolBar,
    QHeaderView, QAbstractItemView, QSplitter,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QApplication, QCheckBox, QComboBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QDateTime, QThread, QTime, QDate
from PyQt5.QtGui import QFont, QColor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.nvr_api import HikvisionISAPI, create_isapi
from core.downloader import DownloadManager, DownloadTask, DownloadStatus, BatchDownloader


# ================================================================= #
#  颜色 / 状态工具
# ================================================================= #

STATUS_COLORS = {
    DownloadStatus.PENDING:     QColor(128, 128, 128),
    DownloadStatus.DOWNLOADING: QColor(0, 120, 215),
    DownloadStatus.COMPLETED:   QColor(0, 153, 76),
    DownloadStatus.FAILED:      QColor(232, 17, 35),
    DownloadStatus.CANCELLED:   QColor(160, 160, 160),
}
STATUS_TEXT = {
    DownloadStatus.PENDING:     "等待中",
    DownloadStatus.DOWNLOADING: "下载中",
    DownloadStatus.COMPLETED:   "已完成",
    DownloadStatus.FAILED:      "失败",
    DownloadStatus.CANCELLED:   "已取消",
}


# ================================================================= #
#  设备配置对话框
# ================================================================= #

class DeviceConfigDialog(QDialog):
    def __init__(self, parent=None, device: Dict = None):
        super().__init__(parent)
        self.device = device or {}
        self.setWindowTitle("设备配置")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.name_edit = QLineEdit(self.device.get('name', ''))
        self.name_edit.setPlaceholderText("例：主楼NVR")
        layout.addRow("设备名称:", self.name_edit)

        self.host_edit = QLineEdit(self.device.get('host', ''))
        self.host_edit.setPlaceholderText("NVR IP地址")
        layout.addRow("IP地址:", self.host_edit)

        self.sdk_port = QSpinBox()
        self.sdk_port.setRange(1, 65535)
        self.sdk_port.setValue(self.device.get('port', 8000))
        layout.addRow("SDK端口:", self.sdk_port)

        self.http_port = QSpinBox()
        self.http_port.setRange(1, 65535)
        self.http_port.setValue(self.device.get('http_port', 80))
        layout.addRow("HTTP端口:", self.http_port)

        self.username_edit = QLineEdit(self.device.get('username', 'admin'))
        layout.addRow("用户名:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        if self.device.get('password'):
            self.password_edit.setText(self.device['password'])
        layout.addRow("密码:", self.password_edit)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_config(self) -> Dict:
        host = self.host_edit.text().strip()
        return {
            'name':      self.name_edit.text().strip() or host,
            'host':      host,
            'port':      self.sdk_port.value(),
            'http_port': self.http_port.value(),
            'username':  self.username_edit.text().strip(),
            'password':  self.password_edit.text(),
        }


# ================================================================= #
#  设置对话框
# ================================================================= #

class DownloadSettingsDialog(QDialog):
    """下载设置对话框"""
    def __init__(self, parent=None, thread_count=4, pack_duration=120, delete_original=False,
                 merge_mode='fast', enable_debug_log=True, skip_transcode=True):
        super().__init__(parent)
        self.setWindowTitle("下载设置")
        self.setMinimumWidth(420)
        self._build_ui()

        self._thread_spin.setValue(thread_count)
        self._pack_spin.setValue(pack_duration)
        self._delete_chk.setChecked(delete_original)
        self._merge_mode_combo.setCurrentIndex(0 if merge_mode == 'fast' else 1)
        self._debug_log_chk.setChecked(enable_debug_log)
        self._skip_transcode_chk.setChecked(skip_transcode)


    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(15)

        # 线程数设置
        self._thread_spin = QSpinBox()
        self._thread_spin.setRange(1, 10)
        self._thread_spin.setValue(4)  # 默认4线程
        self._thread_spin.setSuffix(" 线程")
        layout.addRow("并发线程数:", self._thread_spin)

        thread_hint = QLabel("<small>建议：4线程（最多10线程）<br/>过多线程可能导致NVR响应变慢</small>")
        thread_hint.setWordWrap(True)
        thread_hint.setStyleSheet("color: #666;")
        layout.addRow("", thread_hint)

        layout.addRow(QLabel(""))  # 分隔

        # 合并模式设置
        self._merge_mode_combo = QComboBox()
        self._merge_mode_combo.addItem("快速模式（不转码，最快）", "fast")
        self._merge_mode_combo.addItem("标准模式（转码合并，兼容性好）", "standard")
        self._merge_mode_combo.setCurrentIndex(0)  # 默认快速模式
        layout.addRow("合并模式:", self._merge_mode_combo)

        merge_hint = QLabel("<small>快速模式：不转码直接合并，速度最快<br/>标准模式：转码后合并，兼容性最好</small>")
        merge_hint.setWordWrap(True)
        merge_hint.setStyleSheet("color: #666;")
        layout.addRow("", merge_hint)

        layout.addRow(QLabel(""))  # 分隔

        # 调试日志设置
        self._debug_log_chk = QCheckBox("启用调试日志")
        self._debug_log_chk.setChecked(True)  # 默认开启
        self._debug_log_chk.setToolTip("生成详细的下载和合并日志，用于排查合并点问题")
        layout.addRow("", self._debug_log_chk)

        debug_hint = QLabel("<small>启用后会在下载目录生成详细日志文件<br/>包含分段信息、合并点时间戳等</small>")
        debug_hint.setWordWrap(True)
        debug_hint.setStyleSheet("color: #666;")
        layout.addRow("", debug_hint)

        layout.addRow(QLabel(""))  # 分隔

        # 转码设置
        self._skip_transcode_chk = QCheckBox("跳过转码（原始格式）")
        self._skip_transcode_chk.setChecked(True)  # 默认跳过
        self._skip_transcode_chk.setToolTip("跳过FFmpeg转码，直接使用NVR原始下载的文件。速度更快，原始文件通常可正常播放。")
        layout.addRow("", self._skip_transcode_chk)

        transcode_hint = QLabel("<small>推荐：勾选跳过转码（速度更快）<br/>如果播放问题可取消勾选，转换为标准MP4</small>")
        transcode_hint.setWordWrap(True)
        transcode_hint.setStyleSheet("color: #666;")
        layout.addRow("", transcode_hint)

        layout.addRow(QLabel(""))  # 分隔

        # 打包设置
        self._pack_spin = QSpinBox()
        self._pack_spin.setRange(0, 720)
        self._pack_spin.setValue(120)
        self._pack_spin.setSuffix(" 分钟")
        self._pack_spin.setSpecialValueText("不打包")
        layout.addRow("打包时长:", self._pack_spin)

        self._delete_chk = QCheckBox("删除原始文件")
        layout.addRow("", self._delete_chk)


        pack_hint = QLabel("<small>提示：设置为0表示不打包<br/>打包后将多个录像合并为一个文件</small>")
        pack_hint.setWordWrap(True)
        pack_hint.setStyleSheet("color: #666;")
        layout.addRow("", pack_hint)

        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_settings(self):
        return {
            'thread_count': self._thread_spin.value(),
            'pack_duration': self._pack_spin.value(),
            'delete_original': self._delete_chk.isChecked(),
            'merge_mode': self._merge_mode_combo.currentData(),
            'enable_debug_log': self._debug_log_chk.isChecked(),
            'skip_transcode': self._skip_transcode_chk.isChecked()
        }



# ================================================================= #
#  后台连接线程
# ================================================================= #

class ConnectWorker(QThread):
    """后台连接设备、获取通道的线程"""
    result_ready = pyqtSignal(bool, str, dict, list)   # ok, msg, dev_info, channels

    def __init__(self, config: Dict):
        super().__init__()
        self.config = config

    def run(self):
        try:
            from core.hcnetsdk import HCNetSDK
            cfg = self.config

            sdk = HCNetSDK()
            if not sdk.init():
                self.result_ready.emit(False, "SDK初始化失败", {}, [])
                return

            ok, msg, dev = sdk.login(
                cfg['host'], cfg.get('port', 8000),
                cfg.get('username', 'admin'), cfg.get('password', '')
            )
            if not ok:
                sdk.cleanup()
                self.result_ready.emit(False, f"登录失败: {msg}", {}, [])
                return

            # 用ISAPI补充通道名称
            channels = sdk.get_channels_with_names(
                total_ch   = dev['total_ch'],
                start_chan = max(dev.get('start_dchan', 1), 1),
                nvr_ip     = cfg['host'],
                nvr_port   = cfg.get('http_port', 80),
                username   = cfg.get('username', 'admin'),
                password   = cfg.get('password', ''),
            )

            sdk.cleanup()
            self.result_ready.emit(True, "连接成功", dev, channels)

        except Exception as e:
            self.result_ready.emit(False, f"异常: {e}", {}, [])


# ================================================================= #
#  主窗口
# ================================================================= #

class MainWindow(QMainWindow):
    _progress_signal = pyqtSignal(str, int)   # task_id, progress
    _status_signal   = pyqtSignal(str)         # task_id
    _log_signal = pyqtSignal(str)              # log message
    _multi_connect_result_signal = pyqtSignal(dict, bool, str, dict, list)  # cfg, ok, msg, dev, channels

    def __init__(self):
        super().__init__()
        self.setWindowTitle("海康NVR批量录像下载工具 (SDK版)")
        self.setMinimumSize(1280, 820)

        self.devices:      List[Dict] = []
        self._device_channels: Dict[str, List[Dict]] = {}  # {device_key: [channels]}
        self.download_dir: str = os.path.expanduser("~/Downloads")

        self._current_config: Optional[Dict] = None
        self._connect_worker: Optional[ConnectWorker] = None
        self._thread_count = 4  # 默认4线程
        self._pack_duration = 120  # 默认120分钟
        self._delete_original = False  # 默认不删除原始文件
        self._merge_mode = "fast"  # 默认快速合并模式
        self._enable_debug_log = True  # 默认开启调试日志
        self._skip_transcode = True  # 默认跳过转码
        self._dm = DownloadManager(max_concurrent=self._thread_count)
        self._batch: Optional[BatchDownloader] = None
        
        # 日志缓冲区
        self._run_log_buffer: List[str] = []
        self._download_log_buffer: List[str] = []
        self._log_view_mode = "run"  # 默认显示运行日志

        self._load_config()
        self._build_ui()
        self._wire_signals()

    # ------------------------------------------------------------------ #
    #  UI构建
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        self._make_menu()
        self._make_toolbar()

        central = QWidget()
        self.setCentralWidget(central)
        hbox = QHBoxLayout(central)
        hbox.setSpacing(6)

        hbox.addWidget(self._make_left_panel(), 1)
        hbox.addWidget(self._make_right_panel(), 3)

        self.statusBar().showMessage("就绪")

    def _make_menu(self):
        mb = self.menuBar()

        fm = mb.addMenu("文件")
        for label, slot in [
            ("添加设备", self._add_device),
            ("导入配置", self._import_config),
            ("导出配置", self._export_config),
        ]:
            a = QAction(label, self)
            a.triggered.connect(slot)
            fm.addAction(a)
        fm.addSeparator()
        
        # 设备列表导入导出
        a = QAction("📥 导入设备列表 (CSV)", self)
        a.triggered.connect(self._import_device_list)
        fm.addAction(a)
        a = QAction("📤 导出设备列表 (CSV)", self)
        a.triggered.connect(self._export_device_list)
        fm.addAction(a)
        fm.addSeparator()
        
        ex = QAction("退出", self)
        ex.triggered.connect(self.close)
        fm.addAction(ex)

        # 设置菜单
        sm = mb.addMenu("设置")
        a = QAction("⚙️ 下载设置", self)
        a.triggered.connect(self._show_download_settings)
        sm.addAction(a)

    def _make_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)

        btns = [
            ("➕ 添加设备",  self._add_device),
            ("🔌 连接设备",  self._connect_device),
            ("🔄 刷新通道",  self._refresh_channels),
        ]
        for label, slot in btns:
            b = QPushButton(label)
            b.clicked.connect(slot)
            tb.addWidget(b)

        tb.addSeparator()

        self._btn_start = QPushButton("▶ 开始下载")
        self._btn_start.clicked.connect(self._start_download)
        self._btn_start.setEnabled(False)
        tb.addWidget(self._btn_start)

        self._btn_stop = QPushButton("■ 停止")
        self._btn_stop.clicked.connect(self._stop_download)
        self._btn_stop.setEnabled(False)
        tb.addWidget(self._btn_stop)

        tb.addSeparator()

        self._btn_settings = QPushButton("⚙️ 设置")
        self._btn_settings.clicked.connect(self._show_download_settings)
        tb.addWidget(self._btn_settings)

        tb.addSeparator()

        self._btn_dir = QPushButton("📁 保存目录")
        self._btn_dir.clicked.connect(self._pick_dir)
        tb.addWidget(self._btn_dir)

        self._dir_label = QLabel(f"  {self.download_dir}")
        self._dir_label.setStyleSheet("color: #555;")
        tb.addWidget(self._dir_label)

    def _make_left_panel(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setSpacing(6)

        # 设备管理
        dg = QGroupBox("设备管理")
        dl = QVBoxLayout()

        self._device_list = QListWidget()
        self._device_list.setSelectionMode(QAbstractItemView.ExtendedSelection)  # 支持多选
        self._device_list.itemDoubleClicked.connect(self._on_device_double_clicked)  # 双击连接设备
        self._device_list.currentRowChanged.connect(self._on_device_row_changed)
        dl.addWidget(self._device_list)

        hb = QHBoxLayout()
        for label, slot in [("添加", self._add_device), ("编辑", self._edit_device),
                             ("删除", self._del_device), ("查询", self._query_device)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            hb.addWidget(b)
        dl.addLayout(hb)
        dg.setLayout(dl)
        vbox.addWidget(dg)

        # 通道选择
        cg = QGroupBox("通道选择")
        cl = QVBoxLayout()

        self._channel_tree = QTreeWidget()
        self._channel_tree.setHeaderLabels(["设备/通道", ""])
        self._channel_tree.setColumnWidth(0, 200)
        self._channel_tree.setColumnHidden(1, True)  # 隐藏第2列
        cl.addWidget(self._channel_tree)

        hb2 = QHBoxLayout()
        sel_all = QPushButton("全选")
        sel_all.clicked.connect(self._select_all)
        hb2.addWidget(sel_all)
        desel = QPushButton("取消全选")
        desel.clicked.connect(self._deselect_all)
        hb2.addWidget(desel)
        cl.addLayout(hb2)

        self._channel_count_label = QLabel("共 0 个通道")
        self._channel_count_label.setStyleSheet("color:#666;font-size:11px;")
        cl.addWidget(self._channel_count_label)

        cg.setLayout(cl)
        vbox.addWidget(cg)

        # 时间选择
        tg = QGroupBox("录像时间范围")
        tl = QFormLayout()

        self._dt_start = QDateTimeEdit()
        self._dt_start.setCalendarPopup(True)
        self._dt_start.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        # 默认开始时间：当前时间提前5小时
        self._dt_start.setDateTime(QDateTime.currentDateTime().addSecs(-5 * 3600))
        tl.addRow("开始时间:", self._dt_start)

        self._dt_end = QDateTimeEdit()
        self._dt_end.setCalendarPopup(True)
        self._dt_end.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        # 默认结束时间：当前时间提前2.5小时（与开始时间相差2.5小时）
        self._dt_end.setDateTime(QDateTime.currentDateTime().addSecs(-2 * 3600 - 30 * 60))
        tl.addRow("结束时间:", self._dt_end)

        hb3 = QHBoxLayout()
        for label, preset in [("今天","today"),("昨天","yesterday"),
                               ("最近1h","last_1h"),("最近24h","last_24h")]:
            b = QPushButton(label)
            b.clicked.connect(lambda _, p=preset: self._set_time_range(p))
            hb3.addWidget(b)
        tl.addRow(hb3)

        tg.setLayout(tl)
        vbox.addWidget(tg)

        return w

    def _make_right_panel(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)

        # 任务表格
        task_g = QGroupBox("下载任务")
        task_l = QVBoxLayout()

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["设备", "通道", "开始时间", "结束时间", "状态", "进度", "文件路径"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self._table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
        task_l.addWidget(self._table)

        hb = QHBoxLayout()
        btn_clear = QPushButton("清除已完成")
        btn_clear.clicked.connect(self._clear_completed)
        hb.addWidget(btn_clear)

        btn_merge = QPushButton("📦 打包录像")
        btn_merge.clicked.connect(self._merge_videos)
        hb.addWidget(btn_merge)

        hb.addStretch()
        self._stats_label = QLabel("任务: 0 | 完成: 0 | 失败: 0")
        hb.addWidget(self._stats_label)
        task_l.addLayout(hb)
        task_g.setLayout(task_l)
        vbox.addWidget(task_g)

        # 日志区域（运行日志 + 下载日志 共用一个文本框）
        log_g = QGroupBox("日志")
        log_l = QVBoxLayout()
        
        # 互斥菜单切换
        chk_layout = QHBoxLayout()
        self._log_view_mode = "run"  # 默认显示运行日志
        self._radio_run_log = QPushButton("📋 运行日志")
        self._radio_run_log.setCheckable(True)
        self._radio_run_log.setChecked(True)
        self._radio_run_log.setStyleSheet("QPushButton:checked { background-color: #4CAF50; color: white; }")
        self._radio_run_log.clicked.connect(lambda: self._switch_log_view("run"))
        
        self._radio_download_log = QPushButton("⬇️ 下载日志")
        self._radio_download_log.setCheckable(True)
        self._radio_download_log.setChecked(False)
        self._radio_download_log.setStyleSheet("QPushButton:checked { background-color: #2196F3; color: white; }")
        self._radio_download_log.clicked.connect(lambda: self._switch_log_view("download"))
        
        chk_layout.addWidget(self._radio_run_log)
        chk_layout.addWidget(self._radio_download_log)
        chk_layout.addStretch()
        log_l.addLayout(chk_layout)
        
        # 日志标签
        self._log_label = QLabel("运行日志:")
        log_l.addWidget(self._log_label)
        
        # 共用的日志文本框（更大的显示区域）
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMinimumHeight(200)
        self._log_text.setMaximumHeight(300)
        self._log_text.setFont(QFont("Consolas", 9))
        log_l.addWidget(self._log_text)
        
        # 日志按钮行
        btn_layout = QHBoxLayout()
        btn_cl = QPushButton("清除日志")
        btn_cl.clicked.connect(self._clear_all_logs)
        btn_export = QPushButton("导出日志")
        btn_export.clicked.connect(self._export_log)
        btn_layout.addWidget(btn_cl)
        btn_layout.addWidget(btn_export)
        log_l.addLayout(btn_layout)
        
        log_g.setLayout(log_l)
        vbox.addWidget(log_g)

        return w

    # ------------------------------------------------------------------ #
    #  信号连接
    # ------------------------------------------------------------------ #

    def _wire_signals(self):
        print("[GUI] 连接信号...")
        self._progress_signal.connect(self._on_progress_ui)
        self._status_signal.connect(self._on_status_ui)
        self._log_signal.connect(self._on_log_signal)
        self._multi_connect_result_signal.connect(self._on_multi_connect_result)
        
        # 使用显式方法而不是lambda，避免闭包问题
        def on_progress(tid, p):
            print(f"[GUI] 信号发射: tid={tid}, p={p}")
            self._progress_signal.emit(tid, p)
        
        def on_status(task):
            self._status_signal.emit(task.task_id)

        def on_log(msg: str):
            """日志回调（从下载器转发到GUI）"""
            print(f"[GUI on_log] 收到: {msg[:60]}...")
            # 通过信号发送到主线程
            self._log_signal.emit(msg)

        self._dm.set_progress_callback(on_progress)
        self._dm.set_status_callback(on_status)
        self._dm.set_completion_callback(self._on_task_done_bg)
        self._dm.set_log_callback(on_log)
        print("[GUI] 信号连接完成")
    
    def _on_log_signal(self, msg: str):
        """处理日志信号（在主线程执行）"""
        # 判断是否是下载相关日志（包含具体下载过程信息）
        download_keywords = [
            "开始下载", "下载完成", "下载失败", "下载取消",
            "开始合并", "合并完成", "合并失败", "合并取消",
            "分段", "转码", "清理", "临时", "时长", "目标", "调试日志",
            "Progress", "[Java]", "SDK", "录像", "ch", "通道", "合并模式",
            "[OK]", "[SEG]", "[SKIP]", "[WARN]", "[FAIL]", "[CONV]",
            "✓ 下载完成", "✗ 下载失败"
        ]
        
        # 运行日志关键词（这些应该显示在运行日志，而不是下载日志）
        run_keywords = [
            "▶ 开始下载", "■ 已停止", "正在连接", "连接成功", "连接失败",
            "已添加设备", "已删除设备", "保存目录", "设置已更新",
            "📦 开始打包",
            # 设备查询相关
            "💾 获取到", "硬盘信息", "系统状态", "网络绑定", "物理网卡",
            "查询完成", "查询失败", "查询异常", "盘位", "真实IP",
            "运行时间", "工作模式", "主网卡", "从网卡", "ISAPI"
        ]
        
        # 如果匹配运行日志关键词，显示在运行日志
        is_run_log = any(kw in msg for kw in run_keywords)
        if is_run_log:
            self._log_msg(msg)
            return
        
        # 如果匹配下载关键词，显示在下载日志
        is_download_log = any(kw in msg for kw in download_keywords)
        if is_download_log:
            self._log_download(msg)
        else:
            # 其他日志显示在运行日志面板
            self._log_msg(msg)

    # ------------------------------------------------------------------ #
    #  设备管理
    # ------------------------------------------------------------------ #

    def _add_device(self):
        dlg = DeviceConfigDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            cfg = dlg.get_config()
            if not cfg['host']:
                QMessageBox.warning(self, "错误", "IP地址不能为空")
                return
            self.devices.append(cfg)
            self._save_config()
            self._refresh_device_list()
            self._log_msg(f"已添加设备: {cfg['name']} ({cfg['host']})")

    def _edit_device(self):
        row = self._device_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择一个设备")
            return
        dlg = DeviceConfigDialog(self, self.devices[row])
        if dlg.exec_() == QDialog.Accepted:
            self.devices[row] = dlg.get_config()
            self._save_config()
            self._refresh_device_list()

    def _del_device(self):
        row = self._device_list.currentRow()
        if row < 0:
            return
        if QMessageBox.question(self, "确认", "确定删除该设备?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            name = self.devices.pop(row)['name']
            self._save_config()
            self._refresh_device_list()
            self._log_msg(f"已删除设备: {name}")

    def _refresh_device_list(self):
        self._device_list.clear()
        for d in self.devices:
            self._device_list.addItem(f"{d['name']}  ({d['host']}:{d.get('port',8000)})")

    def _on_device_row_changed(self, row: int):
        if row >= 0:
            self._current_config = self.devices[row]

    def _on_device_double_clicked(self, item):
        """双击设备列表项 - 连接该设备并获取通道"""
        row = self._device_list.row(item)
        if row < 0:
            return
        self._current_config = self.devices[row]
        self._device_list.setCurrentRow(row)
        self._log_msg(f"双击连接设备: {self._current_config['name']} ({self._current_config['host']})...")
        self._connect_device_by_config(self._current_config)

    def _connect_device_by_config(self, cfg: Dict):
        """根据配置连接单个设备"""
        self.statusBar().showMessage(f"连接 {cfg['host']}...")

        self._connect_worker = ConnectWorker(cfg)
        self._connect_worker.result_ready.connect(
            lambda ok, msg, dev_info, channels: self._on_connect_result_multi(ok, msg, dev_info, channels, cfg)
        )
        self._connect_worker.start()

    def _on_connect_result_multi(self, ok: bool, msg: str, dev_info: Dict, channels: List[Dict], cfg: Dict):
        """多设备连接结果处理"""
        device_key = f"{cfg['host']}:{cfg.get('port', 8000)}"

        if not ok:
            self._log_msg(f"❌ {cfg['name']} 连接失败: {msg}")
            self.statusBar().showMessage(f"{cfg['name']} 连接失败")
            return

        # 保存设备通道信息
        self._device_channels[device_key] = channels

        # 更新通道树显示
        self._populate_channels()

        # 启用开始下载按钮
        self._btn_start.setEnabled(True)

        sn = dev_info.get('serial', 'Unknown')
        actual_ch = len(channels)
        online_ch = sum(1 for ch in channels if ch.get('online', True))
        offline_ch = actual_ch - online_ch

        if offline_ch > 0:
            status_str = f"通道:{actual_ch}个 (在线:{online_ch} 离线:{offline_ch})"
        else:
            status_str = f"通道:{actual_ch}个"

        self._log_msg(f"✅ {cfg['name']} 连接成功  序列号:{sn}  {status_str}")
        self.statusBar().showMessage(f"已连接 {cfg['name']} — {status_str}")

    def _query_device(self):
        """查询设备详细信息（支持多选）"""
        selected_rows = [i.row() for i in self._device_list.selectionModel().selectedRows()]

        if not selected_rows:
            QMessageBox.information(self, "提示", "请先在设备列表中选择至少一个设备（可按住Ctrl多选）")
            return

        # 支持多选查询
        for row in selected_rows:
            cfg = self.devices[row]
            self._log_msg(f"🔍 正在查询设备: {cfg['name']} ({cfg['host']})...")
            threading.Thread(target=self._do_query_device, args=(cfg,), daemon=True).start()

    def _do_query_device(self, cfg: Dict):
        """执行设备查询（在后台线程）"""
        # 辅助函数：安全地发送日志到主线程
        def log(msg: str):
            self._log_signal.emit(msg)
        
        try:
            from core.hcnetsdk import HCNetSDK
            from core.nvr_api import create_isapi

            # 使用SDK获取设备基本信息
            sdk = HCNetSDK()
            if not sdk.init():
                QTimer.singleShot(0, lambda: QMessageBox.warning(
                    self, "查询失败", f"{cfg['name']}: SDK初始化失败"
                ))
                log(f"❌ {cfg['name']}: SDK初始化失败")
                return

            # 登录获取设备信息
            ok, msg, dev = sdk.login(
                cfg['host'], cfg.get('port', 8000),
                cfg.get('username', 'admin'), cfg.get('password', '')
            )

            if not ok:
                sdk.cleanup()
                QTimer.singleShot(0, lambda: QMessageBox.warning(
                    self, "查询失败", f"{cfg['name']}: {msg}"
                ))
                log(f"❌ {cfg['name']} 查询失败: {msg}")
                return

            # 使用ISAPI获取设备信息
            hdd_info = []
            system_status = {}
            network_interfaces = []
            bond_info = {}
            try:
                api = create_isapi(cfg)
                
                # 获取硬盘信息
                hdd_info = api.get_hdd_info()
                if hdd_info:
                    log(f"  💾 获取到 {len(hdd_info)} 块硬盘信息")
                    for hdd in hdd_info:
                        hdd_id = hdd.get('id', 'N/A')
                        hdd_name = hdd.get('name', 'Unknown')
                        capacity = hdd.get('capacity', 0)
                        free = hdd.get('free', 0)
                        status = hdd.get('status', '未知')
                        log(f"     盘位{hdd_id}: {hdd_name} | {capacity}GB | 可用{free}GB | {status}")
                else:
                    log(f"  ⚠️ 未获取到硬盘信息")
                
                # 获取系统运行状态
                system_status = api.get_system_status()
                if system_status:
                    cpu = system_status.get('cpu_percent')
                    mem = system_status.get('memory_percent', 'N/A')
                    mem_usage = system_status.get('memory_usage_mb')
                    mem_total = system_status.get('memory_total_mb')
                    users = system_status.get('online_users')
                    uptime = system_status.get('uptime', 'N/A')
                    
                    # 构建CPU信息字符串（某些设备不返回CPU信息）
                    cpu_str = f"{cpu}%" if cpu is not None else "不支持"
                    
                    # 构建内存信息字符串
                    mem_str = f"{mem}%" if mem != 'N/A' else "N/A"
                    if mem_usage is not None and mem_total is not None:
                        mem_str = f"{mem}% ({mem_usage:.0f}/{mem_total:.0f}MB)"
                    
                    # 构建在线用户字符串（某些设备不返回此信息）
                    users_str = f"{users}人" if users is not None else "不支持"
                    
                    log(f"  📊 系统状态: CPU {cpu_str}, 内存 {mem_str}, 在线用户 {users_str}")
                    if uptime != 'N/A':
                        log(f"     运行时间: {uptime}")
                
                # 获取网络绑定信息（工作模式、真实IP等）
                bond_info = api.get_network_bond_info()
                if bond_info and bond_info.get('enabled'):
                    work_mode = bond_info.get('work_mode', 'N/A')
                    primary_if = bond_info.get('primary_interface', 'N/A')
                    bond_ip = bond_info.get('ip', 'N/A')
                    bond_gateway = bond_info.get('gateway', 'N/A')
                    bond_mac = bond_info.get('mac', 'N/A')
                    slaves = bond_info.get('slave_interfaces', [])
                    
                    log(f"  🔗 网络绑定: 工作模式={work_mode}")
                    log(f"     真实IP: {bond_ip} | 网关: {bond_gateway}")
                    log(f"     主网卡: Lan{primary_if} | 从网卡: {[f'Lan{s}' for s in slaves]}")
                
                # 获取网络接口信息（物理网卡）
                network_interfaces = api.get_network_interfaces()
                if network_interfaces:
                    log(f"  🌐 物理网卡: {len(network_interfaces)} 个")
                    for iface in network_interfaces:
                        iface_id = iface.get('id', 'N/A')
                        ip = iface.get('ip', 'N/A')
                        mac = iface.get('mac', 'N/A')
                        log(f"     Lan{iface_id}: {ip} | MAC:{mac}")
                
            except Exception as e:
                log(f"  ❌ 获取设备信息失败: {e}")

            sdk.cleanup()

            # 构建查询结果
            result_text = f"""📋 设备查询结果: {cfg['name']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 基本信息
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  设备名称: {cfg['name']}
  IP地址:   {cfg['host']}:{cfg.get('port', 8000)}
  序列号:   {dev.get('serial', 'Unknown')}
  设备类型: {dev.get('type', 'Unknown')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 通道信息
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  模拟通道: {dev.get('analog_ch', 0)} 个
  IP通道:   {dev.get('ip_ch', 0)} 个
  总通道:   {dev.get('total_ch', 0)} 个
  起始通道: {dev.get('start_chan', 1)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💾 硬盘信息
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

            if hdd_info:
                for hdd in hdd_info:
                    hdd_id = hdd.get('id', 'N/A')
                    hdd_name = hdd.get('name', '')
                    status = hdd.get('status', '未知')
                    capacity = hdd.get('capacity', 0)
                    free = hdd.get('free', 0)
                    used = capacity - free
                    name_str = f" ({hdd_name})" if hdd_name else ""
                    result_text += f"\n  盘位{hdd_id}{name_str}: {status} | 总容量: {capacity}GB | 已用: {used}GB | 可用: {free}GB"
            else:
                result_text += "\n  (未获取到硬盘信息)"

            result_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

            # 运行状态信息
            result_text += """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 运行状态
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            if system_status:
                cpu = system_status.get('cpu_percent')
                mem = system_status.get('memory_percent', 'N/A')
                mem_usage = system_status.get('memory_usage_mb')
                mem_total = system_status.get('memory_total_mb')
                users = system_status.get('online_users')
                uptime = system_status.get('uptime', 'N/A')
                
                # 构建内存信息字符串
                mem_str = f"{mem}%"
                if mem_usage is not None and mem_total is not None:
                    mem_str = f"{mem}% ({mem_usage:.0f}/{mem_total:.0f}MB)"
                
                # CPU使用率（某些设备不返回）
                if cpu is not None:
                    result_text += f"\n  CPU使用率: {cpu}%"
                
                result_text += f"\n  内存使用率: {mem_str}"
                
                # 在线用户（某些设备不返回）
                if users is not None:
                    result_text += f"\n  在线用户: {users} 人"
                
                if uptime != 'N/A':
                    result_text += f"\n  运行时间: {uptime}"
            else:
                result_text += "\n  (未获取到运行状态)"

            # 网络绑定信息（Bond）
            result_text += """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗 网络配置
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            if bond_info and bond_info.get('enabled'):
                work_mode = bond_info.get('work_mode', 'N/A')
                primary_if = bond_info.get('primary_interface', 'N/A')
                bond_ip = bond_info.get('ip', 'N/A')
                bond_mask = bond_info.get('mask', 'N/A')
                bond_gateway = bond_info.get('gateway', 'N/A')
                bond_mac = bond_info.get('mac', 'N/A')
                slaves = bond_info.get('slave_interfaces', [])
                
                result_text += f"\n  工作模式: {work_mode}"
                result_text += f"\n  真实IP地址: {bond_ip}"
                result_text += f"\n  子网掩码: {bond_mask}"
                if bond_gateway != 'N/A':
                    result_text += f"\n  网关: {bond_gateway}"
                if bond_mac != 'N/A':
                    result_text += f"\n  MAC地址: {bond_mac}"
                result_text += f"\n  主网卡: Lan{primary_if}"
                if slaves:
                    result_text += f"\n  从网卡: {', '.join([f'Lan{s}' for s in slaves])}"
            else:
                result_text += "\n  (未启用网络绑定)"

            # 物理网卡信息
            result_text += """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 物理网卡
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            if network_interfaces:
                for iface in network_interfaces:
                    iface_id = iface.get('id', 'N/A')
                    ip = iface.get('ip', 'N/A')
                    mask = iface.get('mask', 'N/A')
                    mac = iface.get('mac', 'N/A')
                    mtu = iface.get('mtu', 'N/A')
                    
                    result_text += f"\n  Lan{iface_id}:"
                    result_text += f"\n    IP地址: {ip}"
                    result_text += f"\n    子网掩码: {mask}"
                    if mac != 'N/A':
                        result_text += f"\n    MAC地址: {mac}"
                    if mtu != 'N/A':
                        result_text += f"\n    MTU: {mtu}"
            else:
                result_text += "\n  (未获取到物理网卡信息)"

            result_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

            # 显示结果对话框
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self, f"设备查询 - {cfg['name']}", result_text
            ))

            log(f"✅ {cfg['name']} 查询完成: 序列号:{dev.get('serial', 'Unknown')}, 通道:{dev.get('total_ch', 0)}个")

        except Exception as e:
            QTimer.singleShot(0, lambda: QMessageBox.warning(
                self, "查询异常", f"{cfg['name']}: {str(e)}"
            ))
            log(f"❌ {cfg['name']} 查询异常: {e}")

    # ------------------------------------------------------------------ #
    #  连接 / 刷新通道
    # ------------------------------------------------------------------ #

    def _connect_device(self):
        row = self._device_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在列表中选择设备")
            return
        self._current_config = self.devices[row]
        self._log_msg(f"正在连接 {self._current_config['host']}...")
        self.statusBar().showMessage("连接中...")
        self._channel_tree.clear()
        self._channel_count_label.setText("获取中...")

        self._connect_worker = ConnectWorker(self._current_config)
        self._connect_worker.result_ready.connect(self._on_connect_result)
        self._connect_worker.start()

    def _refresh_channels(self):
        """刷新通道 - 支持多选设备同时刷新"""
        selected_rows = [i.row() for i in self._device_list.selectionModel().selectedRows()]

        if not selected_rows:
            QMessageBox.information(self, "提示", "请先在设备列表中选择至少一个设备（可按住Ctrl多选）")
            return

        if len(selected_rows) == 1:
            # 单选，使用原有逻辑
            self._current_config = self.devices[selected_rows[0]]
            self._connect_device()
        else:
            # 多选，使用线程池同时连接多个设备
            self._log_msg(f"▶ 开始批量连接 {len(selected_rows)} 台设备...")
            self._connect_multiple_devices([self.devices[row] for row in selected_rows])

    def _connect_multiple_devices(self, configs: List[Dict]):
        """使用线程池同时连接多个设备"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        def connect_single(cfg: Dict) -> tuple:
            """连接单个设备并返回结果"""
            try:
                from core.hcnetsdk import HCNetSDK
                sdk = HCNetSDK()
                if not sdk.init():
                    return cfg, False, "SDK初始化失败", {}, []

                ok, msg, dev = sdk.login(
                    cfg['host'], cfg.get('port', 8000),
                    cfg.get('username', 'admin'), cfg.get('password', '')
                )
                if not ok:
                    sdk.cleanup()
                    return cfg, False, f"登录失败: {msg}", {}, []

                channels = sdk.get_channels_with_names(
                    total_ch=dev['total_ch'],
                    start_chan=max(dev.get('start_dchan', 1), 1),
                    nvr_ip=cfg['host'],
                    nvr_port=cfg.get('http_port', 80),
                    username=cfg.get('username', 'admin'),
                    password=cfg.get('password', ''),
                )
                sdk.cleanup()
                return cfg, True, "连接成功", dev, channels
            except Exception as e:
                return cfg, False, f"异常: {e}", {}, []

        def run_connections():
            with ThreadPoolExecutor(max_workers=min(len(configs), 5)) as executor:
                futures = {executor.submit(connect_single, cfg): cfg for cfg in configs}
                for future in as_completed(futures):
                    cfg, ok, msg, dev, channels = future.result()
                    # 使用信号发送到主线程更新UI
                    self._multi_connect_result_signal.emit(cfg, ok, msg, dev, channels)

        threading.Thread(target=run_connections, daemon=True).start()

    def _on_multi_connect_result(self, cfg: Dict, ok: bool, msg: str, dev: Dict, channels: List[Dict]):
        """批量连接结果处理（在主线程执行）"""
        device_key = f"{cfg['host']}:{cfg.get('port', 8000)}"

        if not ok:
            self._log_msg(f"❌ {cfg['name']} 连接失败: {msg}")
        else:
            self._device_channels[device_key] = channels
            self._populate_channels()

            # 启用开始下载按钮
            self._btn_start.setEnabled(True)

            sn = dev.get('serial', 'Unknown')
            actual_ch = len(channels)
            online_ch = sum(1 for ch in channels if ch.get('online', True))
            offline_ch = actual_ch - online_ch

            if offline_ch > 0:
                status_str = f"通道:{actual_ch}个 (在线:{online_ch} 离线:{offline_ch})"
            else:
                status_str = f"通道:{actual_ch}个"

            self._log_msg(f"✅ {cfg['name']} 连接成功  序列号:{sn}  {status_str}")
            self.statusBar().showMessage(f"已连接 {cfg['name']} — {status_str}")

    def _on_connect_result(self, ok: bool, msg: str, dev_info: Dict, channels: List[Dict]):
        if not ok:
            self._log_msg(f"❌ 连接失败: {msg}")
            self.statusBar().showMessage(f"连接失败: {msg}")
            QMessageBox.warning(self, "连接失败", msg)
            return

        # 保存设备通道信息
        device_key = f"{self._current_config['host']}:{self._current_config.get('port', 8000)}"
        self._device_channels[device_key] = channels

        # 更新通道树显示（支持多设备）
        self._populate_channels()
        self._btn_start.setEnabled(True)

        sn = dev_info.get('serial', '')
        # 优先显示ISAPI实际通道数，而非SDK返回的通道数（SDK可能返回设备最大容量128而非实际接入数）
        actual_ch = len(channels)
        online_ch = sum(1 for ch in channels if ch.get('online', True))
        offline_ch = actual_ch - online_ch

        if offline_ch > 0:
            status_str = f"通道:{actual_ch}个 (在线:{online_ch} 离线:{offline_ch})"
        else:
            status_str = f"通道:{actual_ch}个"

        self._log_msg(f"✅ 连接成功  序列号:{sn}  {status_str}")
        self.statusBar().showMessage(f"已连接 {self._current_config['host']} — {status_str}")

    def _populate_channels(self):
        """填充通道树（支持多设备分组，离线通道标注）"""
        self._channel_tree.clear()

        total_channels = 0
        for device in self.devices:
            device_key = f"{device['host']}:{device.get('port', 8000)}"
            channels = self._device_channels.get(device_key, [])

            if not channels:
                continue

            # 统计在线/离线数
            online_count  = sum(1 for ch in channels if ch.get('online', True))
            offline_count = len(channels) - online_count

            # 创建设备节点
            device_item = QTreeWidgetItem(self._channel_tree)
            device_name = device.get('name', device['host'])
            if offline_count > 0:
                device_item.setText(0, f"📹 {device_name} ({len(channels)}通道, {offline_count}个离线)")
            else:
                device_item.setText(0, f"📹 {device_name} ({len(channels)}通道, 全部在线)")
            device_item.setExpanded(True)  # 默认展开

            # 添加通道子节点
            for ch in channels:
                ch_item = QTreeWidgetItem(device_item)
                ch_name = ch.get('name', f"通道{ch['id']}")
                is_online = ch.get('online', True)

                if is_online:
                    # 在线通道：正常显示
                    ch_item.setText(0, ch_name)
                    ch_item.setCheckState(0, Qt.Unchecked)
                    ch_item.setForeground(0, ch_item.foreground(0))  # 默认颜色
                else:
                    # 离线通道：灰色显示，名称后加 [离线] 标注
                    ch_item.setText(0, f"{ch_name}  [离线]")
                    ch_item.setCheckState(0, Qt.Unchecked)
                    from PyQt5.QtGui import QColor
                    ch_item.setForeground(0, QColor(150, 150, 150))  # 灰色
                    ch_item.setToolTip(0, f"通道离线 (status: {ch.get('status', 'unknown')})")

                ch_item.setData(0, Qt.UserRole, {**ch, 'device': device})

            total_channels += len(channels)

        self._channel_count_label.setText(f"共 {total_channels} 个通道")

    def _select_all(self):
        """全选所有通道"""
        for i in range(self._channel_tree.topLevelItemCount()):
            device_item = self._channel_tree.topLevelItem(i)
            for j in range(device_item.childCount()):
                device_item.child(j).setCheckState(0, Qt.Checked)

    def _deselect_all(self):
        """取消全选所有通道"""
        for i in range(self._channel_tree.topLevelItemCount()):
            device_item = self._channel_tree.topLevelItem(i)
            for j in range(device_item.childCount()):
                device_item.child(j).setCheckState(0, Qt.Unchecked)

    def _get_selected_channels(self) -> List[Dict]:
        """获取所有选中的通道（支持多设备）"""
        result = []
        for i in range(self._channel_tree.topLevelItemCount()):
            device_item = self._channel_tree.topLevelItem(i)
            for j in range(device_item.childCount()):
                ch_item = device_item.child(j)
                if ch_item.checkState(0) == Qt.Checked:
                    ch = ch_item.data(0, Qt.UserRole)
                    if ch:
                        result.append(ch)
        return result

    # ------------------------------------------------------------------ #
    #  时间选择
    # ------------------------------------------------------------------ #

    def _set_time_range(self, preset: str):
        now = QDateTime.currentDateTime()
        if preset == "today":
            s = QDateTime(now.date(), QTime(0, 0, 0))
            e = now
        elif preset == "yesterday":
            yd = now.date().addDays(-1)
            s  = QDateTime(yd, QTime(0, 0, 0))
            e  = QDateTime(yd, QTime(23, 59, 59))
        elif preset == "last_1h":
            s = now.addSecs(-3600)
            e = now
        elif preset == "last_24h":
            s = now.addDays(-1)
            e = now
        else:
            return
        self._dt_start.setDateTime(s)
        self._dt_end.setDateTime(e)

    # ------------------------------------------------------------------ #
    #  下载操作
    # ------------------------------------------------------------------ #

    def _show_download_settings(self):
        """显示下载设置对话框"""
        dlg = DownloadSettingsDialog(
            self,
            thread_count=self._thread_count,
            pack_duration=self._pack_duration,
            delete_original=self._delete_original,
            merge_mode=self._merge_mode,
            enable_debug_log=self._enable_debug_log,
            skip_transcode=self._skip_transcode
        )
        if dlg.exec_() == QDialog.Accepted:
            settings = dlg.get_settings()
            self._thread_count = settings['thread_count']
            self._pack_duration = settings['pack_duration']
            self._delete_original = settings['delete_original']
            self._merge_mode = settings['merge_mode']
            self._enable_debug_log = settings['enable_debug_log']
            self._skip_transcode = settings['skip_transcode']

            # 如果下载管理器未运行，更新并发数
            if not self._dm._running:
                self._dm.max_concurrent = self._thread_count
                print(f"[GUI] 线程数已更新为: {self._thread_count}")

            merge_mode_text = "快速" if self._merge_mode == 'fast' else "标准"
            debug_text = "开启" if self._enable_debug_log else "关闭"
            transcode_text = "跳过" if self._skip_transcode else "开启"
            self._log_msg(f"设置已更新: {self._thread_count}线程, 打包{self._pack_duration}分钟, "
                         f"合并模式:{merge_mode_text}, 调试日志:{debug_text}, 转码:{transcode_text}")


    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录", self.download_dir)
        if d:
            self.download_dir = d
            self._dir_label.setText(f"  {d}")
            self._save_config()
            self._log_msg(f"保存目录: {d}")

    def _start_download(self):
        """开始下载（支持多设备）"""
        selected = self._get_selected_channels()
        if not selected:
            QMessageBox.warning(self, "提示", "请先勾选至少一个通道")
            return

        # 检查是否有未连接的设备
        devices_to_connect = set()
        for ch in selected:
            if 'device' in ch:
                device_key = f"{ch['device']['host']}:{ch['device'].get('port', 8000)}"
                if device_key not in self._device_channels:
                    devices_to_connect.add(ch['device']['name'])

        if devices_to_connect:
            msg = f"以下设备未连接，请先连接：\n" + "\n".join(f"  - {name}" for name in devices_to_connect)
            QMessageBox.warning(self, "提示", msg)
            return

        start_dt = self._dt_start.dateTime().toPyDateTime()
        end_dt   = self._dt_end.dateTime().toPyDateTime()
        if start_dt >= end_dt:
            QMessageBox.warning(self, "提示", "开始时间必须早于结束时间")
            return

        os.makedirs(self.download_dir, exist_ok=True)

        # 按设备分组创建任务
        import uuid
        all_tasks = []
        device_groups = {}

        for ch in selected:
            device = ch['device']
            device_key = f"{device['host']}:{device.get('port', 8000)}"

            if device_key not in device_groups:
                device_groups[device_key] = {
                    'config': device,
                    'channels': []
                }
            device_groups[device_key]['channels'].append(ch)

        # 为每个设备创建任务
        for device_key, group in device_groups.items():
            device_config = group['config']
            channels = group['channels']

            for ch in channels:
                task = DownloadTask(
                    task_id      = str(uuid.uuid4()),
                    device_id    = f"{device_config['host']}:{device_config.get('port',8000)}",
                    device_name  = device_config.get('name', device_config['host']),
                    device_config = device_config,  # 传递设备配置
                    channel_id   = str(ch.get('no', ch.get('id', '1'))),
                    channel_name = ch.get('name', f"通道{ch.get('id','?')}"),
                    start_time   = start_dt,
                    end_time     = end_dt,
                    save_dir     = self.download_dir,
                    merge_mode   = getattr(self, '_merge_mode', 'standard'),
                    enable_debug_log = getattr(self, '_enable_debug_log', False),
                    skip_transcode = getattr(self, '_skip_transcode', True),
                )

                all_tasks.append(task)
                self._add_row(task)

        # 提交所有任务
        self._dm.add_tasks_batch(all_tasks)

        # 启动下载（使用第一个已连接设备的配置作为示例）
        # 注意：由于每个任务都包含设备配置，下载管理器会自动使用对应的设备配置
        self._dm.max_concurrent = self._thread_count
        self._dm.start()  # 设备配置从任务中读取，无需传入

        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)

        # 统计设备数和通道数
        device_count = len(device_groups)
        channel_count = len(selected)
        self._log_msg(f"▶ 开始下载 {device_count}台设备, {channel_count}个通道, {self._thread_count}线程")

    def _stop_download(self):
        self._dm.stop()
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._log_msg("■ 已停止下载")

    def _clear_completed(self):
        self._dm.clear_completed()
        self._table.setRowCount(0)
        for t in self._dm.get_all_tasks():
            self._add_row(t)
        self._update_stats()

    def _merge_videos(self):
        """合并已下载的录像文件"""
        pack_duration = self._pack_duration
        delete_original = self._delete_original

        if pack_duration == 0:
            QMessageBox.information(self, "提示", "请先设置打包时长（设置为0表示不打包）")
            return

        # 获取下载目录
        download_dir = self.download_dir
        if not os.path.exists(download_dir):
            QMessageBox.warning(self, "错误", f"下载目录不存在: {download_dir}")
            return

        # 确认操作
        reply = QMessageBox.question(
            self,
            "确认打包",
            f"即将合并目录中的所有录像文件\n\n"
            f"打包时长: {pack_duration} 分钟\n"
            f"删除原始文件: {'是' if delete_original else '否'}\n\n"
            f"是否继续？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.No:
            return

        self._log_msg(f"📦 开始打包录像 (时长: {pack_duration}分钟)...")

        try:
            from core.video_merger import merge_channel_videos

            # 按通道分组文件
            from pathlib import Path
            files_by_channel = {}
            for f in Path(download_dir).glob('*.mp4'):
                # 从文件名提取通道信息
                # 文件名格式: 设备_通道_日期_时段.mp4
                parts = f.stem.split('_')
                if len(parts) >= 2:
                    channel_name = parts[1]
                    if channel_name not in files_by_channel:
                        files_by_channel[channel_name] = []
                    files_by_channel[channel_name].append(str(f))

            if not files_by_channel:
                QMessageBox.warning(self, "提示", "下载目录中没有找到视频文件")
                return

            # 合并每个通道的文件
            merged_files = []
            for channel_name, files in files_by_channel.items():
                self._log_msg(f"  处理通道: {channel_name} ({len(files)} 个文件)")

                # 按文件名排序
                files.sort()

                # 使用video_merger的分组合并功能
                from core.video_merger import group_videos_by_duration, merge_videos
                groups = group_videos_by_duration(files, pack_duration)

                for i, group in enumerate(groups):
                    output_file = os.path.join(
                        download_dir,
                        f"{channel_name}_pack{i+1}.mp4"
                    )
                    self._log_msg(f"    合并组 {i+1}: {len(group)} 个文件")

                    success = merge_videos(group, output_file)
                    if success:
                        merged_files.append(output_file)
                        self._log_msg(f"    ✅ 合并成功: {os.path.basename(output_file)}")

                        if delete_original:
                            # 删除原始文件
                            for f in group:
                                try:
                                    os.remove(f)
                                except Exception as e:
                                    self._log_msg(f"    ⚠ 删除失败: {os.path.basename(f)}")
                    else:
                        self._log_msg(f"    ❌ 合并失败")

            QMessageBox.information(
                self,
                "打包完成",
                f"成功合并 {len(merged_files)} 个文件\n\n"
                f"文件保存在: {download_dir}"
            )
            self._log_msg(f"✅ 打包完成: {len(merged_files)} 个文件")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"打包失败: {str(e)}")
            self._log_msg(f"❌ 打包失败: {e}")

    # ------------------------------------------------------------------ #
    #  任务表格
    # ------------------------------------------------------------------ #

    def _add_row(self, task: DownloadTask):
        row = self._table.rowCount()
        self._table.insertRow(row)

        def item(text):
            i = QTableWidgetItem(text)
            i.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            return i

        self._table.setItem(row, 0, item(task.device_name))
        self._table.setItem(row, 1, item(task.channel_name))
        self._table.setItem(row, 2, item(task.start_time.strftime("%m-%d %H:%M")))
        self._table.setItem(row, 3, item(task.end_time.strftime("%m-%d %H:%M")))

        status_item = QTableWidgetItem(STATUS_TEXT[task.status])
        status_item.setForeground(STATUS_COLORS[task.status])
        self._table.setItem(row, 4, status_item)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(task.progress)
        bar.setTextVisible(True)
        self._table.setCellWidget(row, 5, bar)

        file_item = item(task.file_path)
        file_item.setData(Qt.UserRole, task.task_id)
        self._table.setItem(row, 6, file_item)

        # 在第0列存task_id
        self._table.item(row, 0).setData(Qt.UserRole, task.task_id)

    def _find_row(self, task_id: str) -> int:
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item and item.data(Qt.UserRole) == task_id:
                return r
        return -1

    # ------------------------------------------------------------------ #
    #  回调槽（主线程）
    # ------------------------------------------------------------------ #

    def _on_progress_ui(self, task_id: str, progress: int):
        print(f"[GUI] 收到进度更新: task_id={task_id}, progress={progress}")
        row = self._find_row(task_id)
        print(f"[GUI] 查找行: row={row}")
        if row >= 0:
            bar = self._table.cellWidget(row, 5)
            if bar:
                bar.setValue(progress)
                bar.setFormat(f"{progress}%")
                print(f"[GUI] 进度条已更新: {progress}%")
            else:
                print("[GUI] 进度条widget不存在")

    def _on_status_ui(self, task_id: str):
        task = self._dm.get_task(task_id)
        if not task:
            return
        row = self._find_row(task_id)
        if row >= 0:
            si = self._table.item(row, 4)
            if si:
                si.setText(STATUS_TEXT[task.status])
                si.setForeground(STATUS_COLORS[task.status])
        self._update_stats()

    def _on_task_done_bg(self, task_id: str, success: bool, file_path: str, error_message: str):
        """后台线程回调 → 转发到主线程日志"""
        task = self._dm.get_task(task_id)
        if not task:
            return
        icon = "✅" if success else "❌"
        msg  = f"{icon} {task.channel_name}: {STATUS_TEXT[task.status]}"
        if error_message:
            msg += f"  ({error_message})"
        QTimer.singleShot(0, lambda: self._log_msg(msg))
        QTimer.singleShot(0, self._update_stats)

    def _update_stats(self):
        tasks     = self._dm.get_all_tasks()
        total     = len(tasks)
        completed = sum(1 for t in tasks if t.status == DownloadStatus.COMPLETED)
        failed    = sum(1 for t in tasks if t.status == DownloadStatus.FAILED)
        self._stats_label.setText(f"任务: {total} | 完成: {completed} | 失败: {failed}")

    # ------------------------------------------------------------------ #
    #  日志
    # ------------------------------------------------------------------ #

    def _switch_log_view(self, mode: str):
        """切换日志视图模式（互斥）"""
        self._log_view_mode = mode
        if mode == "run":
            self._radio_run_log.setChecked(True)
            self._radio_download_log.setChecked(False)
            self._log_label.setText("运行日志:")
            # 显示运行日志内容
            self._log_text.clear()
            for line in self._run_log_buffer:
                self._log_text.append(line)
        else:
            self._radio_run_log.setChecked(False)
            self._radio_download_log.setChecked(True)
            self._log_label.setText("下载日志:")
            # 显示下载日志内容
            self._log_text.clear()
            for line in self._download_log_buffer:
                self._log_text.append(line)
    
    def _clear_all_logs(self):
        """清除所有日志"""
        self._run_log_buffer.clear()
        self._download_log_buffer.clear()
        self._log_text.clear()
    
    def _log_msg(self, msg: str):
        """添加运行日志（过滤进度信息）"""
        # 过滤掉进度信息，只显示重要信息
        if "Progress:" in msg and "%" in msg:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{ts}] {msg}"
        self._run_log_buffer.append(log_line)
        # 如果当前显示的是运行日志，则实时更新
        if self._log_view_mode == "run":
            self._log_text.append(log_line)
    
    def _log_download(self, msg: str):
        """添加下载日志（只显示关键信息）"""
        # 只保留关键日志关键词
        key_keywords = [
            "开始下载", "下载完成", "下载失败", "下载取消",
            "开始合并", "合并完成", "合并失败",
            "分段", "转码", "清理", "临时",
            "✓", "✗", "→", "▼"
        ]
        
        # 过滤掉纯进度信息和Java详细输出
        skip_keywords = [
            "Progress:", "[Java]", "[DownloadManager DEBUG]",
            "收到日志:", "_gui_log 被调用", "回调类型"
        ]
        
        # 如果包含跳过关键词，不显示
        for skip in skip_keywords:
            if skip in msg:
                return
        
        # 只显示关键信息
        has_key = any(kw in msg for kw in key_keywords)
        if not has_key:
            return
        
        ts = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{ts}] {msg}"
        self._download_log_buffer.append(log_line)
        # 如果当前显示的是下载日志，则实时更新
        if self._log_view_mode == "download":
            self._log_text.append(log_line)

    def _export_log(self):
        """导出日志到文件"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"hikvision_download_log_{ts}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", default_name, "文本文件 (*.txt);;所有文件 (*)"
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write("=" * 60 + "\n")
                    f.write("运行日志\n")
                    f.write("=" * 60 + "\n\n")
                    f.write("\n".join(self._run_log_buffer))
                    f.write("\n\n" + "=" * 60 + "\n")
                    f.write("下载日志\n")
                    f.write("=" * 60 + "\n\n")
                    f.write("\n".join(self._download_log_buffer))
                self._log_msg(f"✅ 日志已导出到: {path}")
                QMessageBox.information(self, "导出成功", f"日志已导出到:\n{path}")
            except Exception as e:
                self._log_msg(f"❌ 导出日志失败: {e}")
                QMessageBox.critical(self, "导出失败", f"导出日志失败:\n{e}")

    # ------------------------------------------------------------------ #
    #  配置存取
    # ------------------------------------------------------------------ #

    def _load_config(self):
        path = os.path.join(os.path.expanduser("~"), ".hikvision_downloader", "config.json")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    self.devices      = cfg.get('devices', [])
                    self.download_dir = cfg.get('download_dir', self.download_dir)
            except Exception as e:
                print(f"加载配置失败: {e}")

    def _save_config(self):
        d = os.path.join(os.path.expanduser("~"), ".hikvision_downloader")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "config.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({
                    'devices':      self.devices,
                    'download_dir': self.download_dir,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            self.devices      = cfg.get('devices', self.devices)
            self.download_dir = cfg.get('download_dir', self.download_dir)
            self._save_config()
            self._refresh_device_list()
            self._log_msg("配置导入成功")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _export_config(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出配置", "hikvision_config.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'devices': self.devices, 'download_dir': self.download_dir},
                          f, ensure_ascii=False, indent=2)
            self._log_msg("配置导出成功")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _import_device_list(self):
        """从CSV文件导入设备列表"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入设备列表", "", 
            "CSV文件 (*.csv);;文本文件 (*.txt);;所有文件 (*)"
        )
        if not path:
            return
        
        try:
            imported_devices = []
            errors = []
            
            with open(path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig 处理BOM
                # 尝试检测是否是CSV格式
                first_line = f.readline().strip()
                f.seek(0)
                
                # 检查是否是CSV头
                is_csv = ',' in first_line or '，' in first_line
                
                if is_csv and ('名称' in first_line or 'name' in first_line.lower() or 'IP' in first_line):
                    # 有表头的CSV
                    import csv
                    reader = csv.DictReader(f)
                    for row_num, row in enumerate(reader, start=2):
                        try:
                            device = self._parse_device_row(row, row_num)
                            if device:
                                imported_devices.append(device)
                        except Exception as e:
                            errors.append(f"第{row_num}行: {e}")
                else:
                    # 无表头的简单格式：每行一个设备，格式为 name,host,port,username,password
                    for row_num, line in enumerate(f, start=1):
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        parts = line.replace('，', ',').split(',')
                        if len(parts) >= 2:
                            device = {
                                'name': parts[0].strip() or parts[1].strip(),
                                'host': parts[1].strip(),
                                'port': int(parts[2].strip()) if len(parts) > 2 and parts[2].strip() else 8000,
                                'http_port': int(parts[3].strip()) if len(parts) > 3 and parts[3].strip() else 80,
                                'username': parts[4].strip() if len(parts) > 4 else 'admin',
                                'password': parts[5].strip() if len(parts) > 5 else ''
                            }
                            imported_devices.append(device)
                        else:
                            errors.append(f"第{row_num}行: 格式错误")
            
            if imported_devices:
                # 询问是追加还是替换
                reply = QMessageBox.question(
                    self, "导入设备",
                    f"成功解析 {len(imported_devices)} 个设备\n{len(errors)} 个错误\n\n是追加到现有列表还是替换？",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Cancel:
                    return
                elif reply == QMessageBox.No:
                    # 替换
                    self.devices = imported_devices
                else:
                    # 追加
                    self.devices.extend(imported_devices)
                
                self._save_config()
                self._refresh_device_list()
                self._log_msg(f"✅ 成功导入 {len(imported_devices)} 个设备")
            
            if errors:
                error_msg = "\n".join(errors[:10])
                if len(errors) > 10:
                    error_msg += f"\n...还有 {len(errors) - 10} 个错误"
                QMessageBox.warning(self, "导入警告", f"部分行导入失败:\n{error_msg}")
                
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"导入设备列表失败:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def _parse_device_row(self, row: dict, row_num: int) -> dict:
        """解析CSV行数据为设备配置"""
        # 支持多种列名变体
        name = row.get('名称') or row.get('name') or row.get('设备名称') or row.get('Name')
        host = row.get('IP地址') or row.get('host') or row.get('IP') or row.get('ip')
        
        if not host:
            raise ValueError("缺少IP地址")
        
        # 端口
        port_str = row.get('SDK端口') or row.get('port') or row.get('端口') or '8000'
        try:
            port = int(port_str)
        except:
            port = 8000
        
        # HTTP端口
        http_port_str = row.get('HTTP端口') or row.get('http_port') or '80'
        try:
            http_port = int(http_port_str)
        except:
            http_port = 80
        
        # 用户名密码
        username = row.get('用户名') or row.get('username') or row.get('Username') or 'admin'
        password = row.get('密码') or row.get('password') or row.get('Password') or ''
        
        return {
            'name': name or host,
            'host': host,
            'port': port,
            'http_port': http_port,
            'username': username,
            'password': password
        }

    def _export_device_list(self):
        """导出设备列表到CSV文件"""
        if not self.devices:
            QMessageBox.information(self, "提示", "当前没有设备可导出")
            return
        
        path, _ = QFileDialog.getSaveFileName(
            self, "导出设备列表", "hikvision_devices.csv", 
            "CSV文件 (*.csv);;文本文件 (*.txt)"
        )
        if not path:
            return
        
        try:
            import csv
            
            with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                # 写入UTF-8 BOM，让Excel正确识别中文
                fieldnames = ['名称', 'IP地址', 'SDK端口', 'HTTP端口', '用户名', '密码']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                
                writer.writeheader()
                for device in self.devices:
                    writer.writerow({
                        '名称': device.get('name', ''),
                        'IP地址': device.get('host', ''),
                        'SDK端口': device.get('port', 8000),
                        'HTTP端口': device.get('http_port', 80),
                        '用户名': device.get('username', 'admin'),
                        '密码': device.get('password', '')
                    })
            
            self._log_msg(f"✅ 设备列表已导出到: {path}")
            QMessageBox.information(self, "导出成功", f"成功导出 {len(self.devices)} 个设备到:\n{path}")
            
        except Exception as e:
            QMessageBox.warning(self, "导出失败", f"导出设备列表失败:\n{str(e)}")

    # ------------------------------------------------------------------ #
    #  初始化设备列表
    # ------------------------------------------------------------------ #

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_device_list()
        if self.devices:
            self._device_list.setCurrentRow(0)

    def closeEvent(self, event):
        self._dm.stop()
        self._save_config()
        event.accept()
