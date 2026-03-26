# ISAPI HTTP 录像截取对话框
import os
import re
import threading
from typing import List, Dict
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QSpinBox, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QMessageBox, QAbstractItemView,
    QFileDialog, QTextEdit, QProgressBar, QLabel,
)
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime, QTime
from PyQt5.QtGui import QFont


class ISAPIClippingDialog(QDialog):
    """ISAPI HTTP 录像截取对话框 - 通过ISAPI接口下载指定时间段录像"""

    progress_signal = pyqtSignal(str, int)    # task_id, progress
    log_signal = pyqtSignal(str)              # log message
    completion_signal = pyqtSignal(str, bool, str)  # task_id, success, message

    def __init__(self, parent=None, devices: List[Dict] = None, device_channels: Dict = None):
        super().__init__(parent)
        self.devices = devices or []
        self.device_channels = device_channels or {}
        self.setWindowTitle("ISAPI HTTP 录像截取")
        self.setMinimumWidth(650)
        self.setMinimumHeight(580)
        self._build_ui()
        self._active_tasks: Dict[str, Dict] = {}

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel("📥 通过 ISAPI HTTP 接口直接下载指定时间段录像（比RTSP更快更稳定）")
        hint.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(hint)

        # 设备选择
        device_group = QGroupBox("选择设备")
        device_layout = QFormLayout()

        self._device_combo = QComboBox()
        self._device_combo.addItem("请选择设备...", None)
        for device in self.devices:
            device_key = f"{device['host']}:{device.get('port', 8000)}"
            self._device_combo.addItem(f"{device.get('name', device['host'])} ({device_key})", device)
        self._device_combo.currentIndexChanged.connect(self._on_device_changed)
        device_layout.addRow("设备:", self._device_combo)

        self._http_port_spin = QSpinBox()
        self._http_port_spin.setRange(1, 65535)
        self._http_port_spin.setValue(80)
        device_layout.addRow("HTTP端口:", self._http_port_spin)

        self._rtsp_port_spin = QSpinBox()
        self._rtsp_port_spin.setRange(1, 65535)
        self._rtsp_port_spin.setValue(554)
        device_layout.addRow("RTSP端口:", self._rtsp_port_spin)

        device_group.setLayout(device_layout)
        layout.addWidget(device_group)

        # 通道选择
        channel_group = QGroupBox("选择通道")
        channel_layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        self._btn_select_all = QPushButton("全选")
        self._btn_select_all.clicked.connect(self._select_all_channels)
        btn_layout.addWidget(self._btn_select_all)

        self._btn_deselect_all = QPushButton("取消全选")
        self._btn_deselect_all.clicked.connect(self._deselect_all_channels)
        btn_layout.addWidget(self._btn_deselect_all)
        btn_layout.addStretch()
        channel_layout.addLayout(btn_layout)

        self._channel_list = QListWidget()
        self._channel_list.setSelectionMode(QAbstractItemView.MultiSelection)
        channel_layout.addWidget(self._channel_list)

        channel_group.setLayout(channel_layout)
        layout.addWidget(channel_group)

        # 时间和设置
        settings_group = QGroupBox("时间范围与设置")
        settings_layout = QFormLayout()

        self._start_edit = QDateTimeEdit()
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._start_edit.setDateTime(QDateTime.currentDateTime().addSecs(-3600))
        settings_layout.addRow("开始时间:", self._start_edit)

        self._end_edit = QDateTimeEdit()
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._end_edit.setDateTime(QDateTime.currentDateTime())
        settings_layout.addRow("结束时间:", self._end_edit)

        # 快捷时间按钮
        quick_layout = QHBoxLayout()
        for label, seconds in [("最近30分钟", 1800), ("最近1小时", 3600), ("最近2小时", 7200)]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, s=seconds: self._set_duration(s))
            quick_layout.addWidget(btn)
        btn_today = QPushButton("今天")
        btn_today.clicked.connect(lambda: self._set_today())
        quick_layout.addWidget(btn_today)
        settings_layout.addRow("快捷:", quick_layout)

        self._stream_combo = QComboBox()
        self._stream_combo.addItem("主码流 (高清)", 1)
        self._stream_combo.addItem("子码流 (标清)", 2)
        settings_layout.addRow("码流类型:", self._stream_combo)

        dir_layout = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setText(os.path.expanduser("~/Downloads"))
        dir_layout.addWidget(self._dir_edit)
        self._btn_browse = QPushButton("浏览...")
        self._btn_browse.clicked.connect(self._browse_dir)
        dir_layout.addWidget(self._btn_browse)
        settings_layout.addRow("保存目录:", dir_layout)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # 进度面板
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout()

        self._progress_text = QTextEdit()
        self._progress_text.setReadOnly(True)
        self._progress_text.setMaximumHeight(150)
        self._progress_text.setFont(QFont("Consolas", 9))
        progress_layout.addWidget(self._progress_text)

        self._overall_bar = QProgressBar()
        self._overall_bar.setValue(0)
        self._overall_bar.setTextVisible(True)
        self._overall_bar.setFormat("总进度: %v/%m (%p%)")
        progress_layout.addWidget(self._overall_bar)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # 按钮区域
        btn_row = QHBoxLayout()

        self._btn_start = QPushButton("▶ 开始截取")
        self._btn_start.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 6px 16px; }")
        self._btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(self._btn_start)

        self._btn_stop = QPushButton("■ 停止")
        self._btn_stop.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 6px 16px; }")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop)
        btn_row.addWidget(self._btn_stop)

        btn_row.addStretch()

        self._btn_close = QPushButton("关闭")
        self._btn_close.clicked.connect(self.close)
        btn_row.addWidget(self._btn_close)

        layout.addLayout(btn_row)

        # 连接信号
        self.progress_signal.connect(self._on_progress_update)
        self.log_signal.connect(self._on_log_update)
        self.completion_signal.connect(self._on_task_completion)

    def _on_device_changed(self, index):
        self._channel_list.clear()
        if index <= 0:
            return
        device = self._device_combo.currentData()
        if not device:
            return
        device_key = f"{device['host']}:{device.get('port', 8000)}"
        channels = self.device_channels.get(device_key, [])
        for ch in channels:
            ch_no = ch.get('no', ch.get('id', '?'))
            ch_name = ch.get('name', f"通道{ch_no}")
            item = QListWidgetItem(f"{ch_no}. {ch_name}")
            item.setData(Qt.UserRole, ch)
            self._channel_list.addItem(item)
        self._http_port_spin.setValue(device.get('http_port', 80))

    def _select_all_channels(self):
        for i in range(self._channel_list.count()):
            self._channel_list.item(i).setSelected(True)

    def _deselect_all_channels(self):
        for i in range(self._channel_list.count()):
            self._channel_list.item(i).setSelected(False)

    def _set_duration(self, seconds: int):
        end = QDateTime.currentDateTime()
        self._end_edit.setDateTime(end)
        self._start_edit.setDateTime(end.addSecs(-seconds))

    def _set_today(self):
        now = QDateTime.currentDateTime()
        self._start_edit.setDateTime(QDateTime(now.date(), QTime(0, 0, 0)))
        self._end_edit.setDateTime(QDateTime(now.date(), QTime(23, 59, 59)))

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录", self._dir_edit.text())
        if d:
            self._dir_edit.setText(d)

    def _on_start(self):
        device = self._device_combo.currentData()
        if not device:
            QMessageBox.warning(self, "提示", "请先选择设备")
            return

        selected = self._channel_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "提示", "请先选择至少一个通道")
            return

        start_dt = self._start_edit.dateTime().toPyDateTime()
        end_dt = self._end_edit.dateTime().toPyDateTime()
        if start_dt >= end_dt:
            QMessageBox.warning(self, "提示", "开始时间必须早于结束时间")
            return

        save_dir = self._dir_edit.text().strip()
        if not save_dir:
            QMessageBox.warning(self, "提示", "请选择保存目录")
            return

        channels = []
        for item in selected:
            ch = item.data(Qt.UserRole)
            if ch:
                channels.append(ch)

        stream_type = self._stream_combo.currentData()
        http_port = self._http_port_spin.value()
        rtsp_port = self._rtsp_port_spin.value()

        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._overall_bar.setMaximum(len(channels))
        self._overall_bar.setValue(0)
        self._progress_text.clear()

        self._total_tasks = len(channels)
        self._completed_tasks = 0
        self._active_tasks.clear()

        for idx, ch in enumerate(channels):
            ch_no = int(ch.get('no', ch.get('id', 1)))
            ch_name = ch.get('name', f"通道{ch_no}")

            safe_name = re.sub(r'[\\/:*?"<>|]', '', ch_name.strip()) or f"CH{ch_no}"
            date_str = start_dt.strftime("%Y%m%d")
            time_range = f"{start_dt.strftime('%H%M%S')}_{end_dt.strftime('%H%M%S')}"
            filename = f"{safe_name}_{date_str}_{time_range}.mp4"
            save_path = os.path.join(save_dir, filename)

            task_id = f"isapi_{ch_no}_{idx}"
            stop_event = threading.Event()
            self._active_tasks[task_id] = {
                'channel': ch_no,
                'channel_name': ch_name,
                'stop_event': stop_event,
                'save_path': save_path,
            }

            t = threading.Thread(
                target=self._download_thread,
                args=(task_id, device, ch_no, ch_name, start_dt, end_dt,
                      save_path, stream_type, http_port, rtsp_port, stop_event),
                name=f"ISAPI-Clip-{task_id}",
                daemon=True,
            )
            t.start()

        self._log_append(f"▶ 已启动 {len(channels)} 个ISAPI截取任务")

    def _download_thread(self, task_id, device, channel, channel_name,
                         start_time, end_time, save_path,
                         stream_type, http_port, rtsp_port, stop_event):
        """下载线程"""
        try:
            from core.nvr_api import HikvisionISAPI

            api = HikvisionISAPI(
                host=device['host'],
                port=http_port,
                username=device.get('username', 'admin'),
                password=device.get('password', ''),
            )

            def _progress(pct):
                self.progress_signal.emit(task_id, pct)

            def _log(msg):
                self.log_signal.emit(f"[{channel_name}] {msg}")

            success, msg = api.download_record_by_time(
                channel=channel,
                start_time=start_time,
                end_time=end_time,
                save_path=save_path,
                stream_type=stream_type,
                rtsp_port=rtsp_port,
                progress_callback=_progress,
                log_callback=_log,
                stop_event=stop_event,
            )

            self.completion_signal.emit(task_id, success, msg)

        except Exception as e:
            self.completion_signal.emit(task_id, False, f"异常: {str(e)}")

    def _on_progress_update(self, task_id: str, progress: int):
        task_info = self._active_tasks.get(task_id)
        if not task_info:
            return
        ch_name = task_info['channel_name']
        self._log_append(f"  {ch_name}: {progress}%")

    def _on_log_update(self, msg: str):
        self._log_append(msg)

    def _on_task_completion(self, task_id: str, success: bool, message: str):
        task_info = self._active_tasks.get(task_id)
        ch_name = task_info['channel_name'] if task_info else task_id

        if success:
            self._log_append(f"✅ {ch_name}: {message}")
        else:
            self._log_append(f"❌ {ch_name}: {message}")

        self._completed_tasks += 1
        self._overall_bar.setValue(self._completed_tasks)

        if self._completed_tasks >= self._total_tasks:
            self._btn_start.setEnabled(True)
            self._btn_stop.setEnabled(False)
            self._active_tasks.clear()
            self._log_append(f"\n🏁 全部任务完成 ({self._completed_tasks}/{self._total_tasks})")

    def _on_stop(self):
        for task_id, info in self._active_tasks.items():
            info['stop_event'].set()
        self._log_append("⏹ 正在停止所有下载任务...")

    def _log_append(self, msg: str):
        cursor = self._progress_text.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(msg + "\n")
        self._progress_text.setTextCursor(cursor)
        self._progress_text.ensureCursorVisible()

    def closeEvent(self, event):
        if self._active_tasks:
            reply = QMessageBox.question(
                self, "确认关闭",
                f"还有 {len(self._active_tasks)} 个下载任务进行中，确定关闭吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            self._on_stop()
        event.accept()
