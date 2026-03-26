# RTSP回放流下载对话框
import os
from typing import List, Dict
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QGroupBox, QFormLayout, QComboBox, QSpinBox,
    QListWidget, QListWidgetItem, QPushButton, QLineEdit,
    QMessageBox, QAbstractItemView, QFileDialog, QLabel,
)
from PyQt5.QtCore import Qt, QTime, QDateTime


class RTSPPlaybackDownloadDialog(QDialog):
    """RTSP回放流下载对话框 - 用于下载历史录像"""

    def __init__(self, parent=None, devices: List[Dict] = None, device_channels: Dict = None):
        super().__init__(parent)
        self.devices = devices or []
        self.device_channels = device_channels or {}
        self.setWindowTitle("RTSP回放流下载（历史录像）")
        self.setMinimumWidth(650)
        self.setMinimumHeight(550)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel("📹 通过RTSP协议下载历史录像回放（需要设备支持RTSP回放）")
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

        self._rtsp_port = QSpinBox()
        self._rtsp_port.setRange(1, 65535)
        self._rtsp_port.setValue(554)
        device_layout.addRow("RTSP端口:", self._rtsp_port)

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
        self._channel_list.itemSelectionChanged.connect(self._update_channel_count)
        channel_layout.addWidget(self._channel_list)

        self._channel_count_label = QLabel("共 0 个通道，已选择 0 个")
        self._channel_count_label.setStyleSheet("color: #666; font-size: 11px;")
        channel_layout.addWidget(self._channel_count_label)

        channel_group.setLayout(channel_layout)
        layout.addWidget(channel_group)

        # 时间范围设置
        time_group = QGroupBox("回放时间范围")
        time_layout = QFormLayout()

        self._start_time = QDateTimeEdit()
        self._start_time.setCalendarPopup(True)
        self._start_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._start_time.setDateTime(QDateTime.currentDateTime().addSecs(-3600))
        time_layout.addRow("开始时间:", self._start_time)

        self._end_time = QDateTimeEdit()
        self._end_time.setCalendarPopup(True)
        self._end_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._end_time.setDateTime(QDateTime.currentDateTime())
        time_layout.addRow("结束时间:", self._end_time)

        quick_layout = QHBoxLayout()
        btn_1h = QPushButton("最近1小时")
        btn_1h.clicked.connect(lambda: self._set_time_range(1))
        quick_layout.addWidget(btn_1h)

        btn_2h = QPushButton("最近2小时")
        btn_2h.clicked.connect(lambda: self._set_time_range(2))
        quick_layout.addWidget(btn_2h)

        btn_1d = QPushButton("今天")
        btn_1d.clicked.connect(lambda: self._set_time_range(0, "today"))
        quick_layout.addWidget(btn_1d)

        quick_layout.addStretch()
        time_layout.addRow("快捷设置:", quick_layout)

        time_group.setLayout(time_layout)
        layout.addWidget(time_group)

        # 下载设置
        settings_group = QGroupBox("下载设置")
        settings_layout = QFormLayout()

        self._stream_combo = QComboBox()
        self._stream_combo.addItem("主码流 (高清)", "main")
        self._stream_combo.addItem("子码流 (标清)", "sub")
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

        tip_label = QLabel("<small>提示：RTSP回放需要设备支持，部分旧型号NVR可能不支持此功能。<br>"
                          "如果下载失败，建议使用SDK方式下载录像。</small>")
        tip_label.setStyleSheet("color: #999;")
        tip_label.setWordWrap(True)
        layout.addWidget(tip_label)

        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("开始下载")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self._on_start_download)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _set_time_range(self, hours: int, preset: str = None):
        now = QDateTime.currentDateTime()
        if preset == "today":
            self._start_time.setDateTime(QDateTime(now.date(), QTime(0, 0, 0)))
            self._end_time.setDateTime(now)
        else:
            self._start_time.setDateTime(now.addSecs(-hours * 3600))
            self._end_time.setDateTime(now)

    def _on_device_changed(self, index):
        self._channel_list.clear()
        if index <= 0:
            self._update_channel_count()
            return

        device = self._device_combo.currentData()
        if not device:
            self._update_channel_count()
            return

        device_key = f"{device['host']}:{device.get('port', 8000)}"
        channels = self.device_channels.get(device_key, [])

        for ch in channels:
            ch_no = ch.get('no', ch.get('id', '?'))
            ch_name = ch.get('name', f"通道{ch_no}")
            item = QListWidgetItem(f"{ch_no}. {ch_name}")
            item.setData(Qt.UserRole, ch)
            self._channel_list.addItem(item)

        self._update_channel_count()

    def _update_channel_count(self):
        total = self._channel_list.count()
        selected = len(self._channel_list.selectedItems())
        self._channel_count_label.setText(f"共 {total} 个通道，已选择 {selected} 个")

    def _select_all_channels(self):
        for i in range(self._channel_list.count()):
            self._channel_list.item(i).setSelected(True)

    def _deselect_all_channels(self):
        for i in range(self._channel_list.count()):
            self._channel_list.item(i).setSelected(False)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录", self._dir_edit.text())
        if d:
            self._dir_edit.setText(d)

    def _on_start_download(self):
        device = self._device_combo.currentData()
        if not device:
            QMessageBox.warning(self, "提示", "请先选择设备")
            return

        selected_items = self._channel_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请至少选择一个通道")
            return

        start_dt = self._start_time.dateTime().toPyDateTime()
        end_dt = self._end_time.dateTime().toPyDateTime()

        if start_dt >= end_dt:
            QMessageBox.warning(self, "提示", "开始时间必须早于结束时间")
            return

        self.selected_device = device
        self.selected_channels = [item.data(Qt.UserRole) for item in selected_items]
        self.rtsp_port = self._rtsp_port.value()
        self.start_time = start_dt
        self.end_time = end_dt
        self.stream_type = self._stream_combo.currentData()
        self.save_dir = self._dir_edit.text()

        self.accept()

    def get_download_params(self) -> Dict:
        return {
            'device': getattr(self, 'selected_device', None),
            'channels': getattr(self, 'selected_channels', []),
            'rtsp_port': getattr(self, 'rtsp_port', 554),
            'start_time': getattr(self, 'start_time', None),
            'end_time': getattr(self, 'end_time', None),
            'stream_type': getattr(self, 'stream_type', 'main'),
            'save_dir': getattr(self, 'save_dir', os.path.expanduser("~/Downloads")),
        }
