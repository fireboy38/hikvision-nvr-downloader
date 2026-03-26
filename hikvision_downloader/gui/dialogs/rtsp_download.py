# RTSP实时流下载对话框
import os
from typing import List, Dict, Optional
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QGroupBox, QFormLayout, QComboBox, QSpinBox,
    QListWidget, QListWidgetItem, QPushButton, QLineEdit,
    QMessageBox, QAbstractItemView, QFileDialog,
)
from PyQt5.QtCore import Qt


class RTSPDownloadDialog(QDialog):
    """RTSP实时流下载对话框"""

    def __init__(self, parent=None, devices: List[Dict] = None, device_channels: Dict = None):
        super().__init__(parent)
        self.devices = devices or []
        self.device_channels = device_channels or {}
        self.setWindowTitle("RTSP实时流下载")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel("📹 通过RTSP协议下载实时视频流（非录像回放）")
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
        channel_layout.addWidget(self._channel_list)

        channel_group.setLayout(channel_layout)
        layout.addWidget(channel_group)

        # 下载设置
        settings_group = QGroupBox("下载设置")
        settings_layout = QFormLayout()

        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(10, 3600)
        self._duration_spin.setValue(60)
        self._duration_spin.setSuffix(" 秒")
        settings_layout.addRow("录制时长:", self._duration_spin)

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

        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("开始下载")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(self._on_start_download)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

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

        self.selected_device = device
        self.selected_channels = [item.data(Qt.UserRole) for item in selected_items]
        self.rtsp_port = self._rtsp_port.value()
        self.duration = self._duration_spin.value()
        self.stream_type = self._stream_combo.currentData()
        self.save_dir = self._dir_edit.text()

        self.accept()

    def get_download_params(self) -> Dict:
        return {
            'device': getattr(self, 'selected_device', None),
            'channels': getattr(self, 'selected_channels', []),
            'rtsp_port': getattr(self, 'rtsp_port', 554),
            'duration': getattr(self, 'duration', 60),
            'stream_type': getattr(self, 'stream_type', 'main'),
            'save_dir': getattr(self, 'save_dir', os.path.expanduser("~/Downloads")),
        }
