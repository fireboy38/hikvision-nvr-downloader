# 设备配置对话框
from typing import Dict, Optional
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QSpinBox,
)


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
