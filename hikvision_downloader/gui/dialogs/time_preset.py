# 时间预设管理对话框
from typing import Dict, Optional
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QGroupBox, QFormLayout, QLineEdit, QDateTimeEdit,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QMessageBox, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QTime, QDateTime


class TimePresetDialog(QDialog):
    """时间预设管理对话框"""

    def __init__(self, parent=None, presets: Dict = None):
        super().__init__(parent)
        self.setWindowTitle("管理时间预设")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.presets = presets or {}
        self._build_ui()
        self._load_presets()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hint = QLabel("自定义常用时间段，如：语文考试、早自习、课间操等")
        hint.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(hint)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.itemClicked.connect(self._on_item_selected)
        layout.addWidget(self._list)

        edit_group = QGroupBox("编辑预设")
        edit_layout = QFormLayout()

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("例如：语文考试")
        edit_layout.addRow("预设名称:", self._name_edit)

        self._start_edit = QDateTimeEdit()
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._start_edit.setDateTime(QDateTime.currentDateTime().addSecs(-3600))
        edit_layout.addRow("开始时间:", self._start_edit)

        self._end_edit = QDateTimeEdit()
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._end_edit.setDateTime(QDateTime.currentDateTime())
        edit_layout.addRow("结束时间:", self._end_edit)

        quick_layout = QHBoxLayout()
        btn_today = QPushButton("设为今天")
        btn_today.clicked.connect(lambda: self._set_date_range("today"))
        quick_layout.addWidget(btn_today)

        btn_yesterday = QPushButton("设为昨天")
        btn_yesterday.clicked.connect(lambda: self._set_date_range("yesterday"))
        quick_layout.addWidget(btn_yesterday)

        btn_1h = QPushButton("1小时")
        btn_1h.clicked.connect(lambda: self._set_duration(3600))
        quick_layout.addWidget(btn_1h)

        btn_2h = QPushButton("2小时")
        btn_2h.clicked.connect(lambda: self._set_duration(7200))
        quick_layout.addWidget(btn_2h)

        edit_layout.addRow("快捷设置:", quick_layout)

        edit_group.setLayout(edit_layout)
        layout.addWidget(edit_group)

        btn_layout = QHBoxLayout()

        self._btn_add = QPushButton("➕ 添加")
        self._btn_add.clicked.connect(self._add_preset)
        btn_layout.addWidget(self._btn_add)

        self._btn_update = QPushButton("💾 保存修改")
        self._btn_update.clicked.connect(self._update_preset)
        btn_layout.addWidget(self._btn_update)

        self._btn_delete = QPushButton("🗑️ 删除")
        self._btn_delete.clicked.connect(self._delete_preset)
        btn_layout.addWidget(self._btn_delete)

        btn_layout.addStretch()

        self._btn_clear = QPushButton("清空")
        self._btn_clear.clicked.connect(self._clear_form)
        btn_layout.addWidget(self._btn_clear)

        layout.addLayout(btn_layout)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _set_date_range(self, preset: str):
        now = QDateTime.currentDateTime()
        if preset == "today":
            self._start_edit.setDateTime(QDateTime(now.date(), QTime(0, 0, 0)))
            self._end_edit.setDateTime(QDateTime(now.date(), QTime(23, 59, 59)))
        elif preset == "yesterday":
            yd = now.date().addDays(-1)
            self._start_edit.setDateTime(QDateTime(yd, QTime(0, 0, 0)))
            self._end_edit.setDateTime(QDateTime(yd, QTime(23, 59, 59)))

    def _set_duration(self, seconds: int):
        start = self._start_edit.dateTime()
        self._end_edit.setDateTime(start.addSecs(seconds))

    def _load_presets(self):
        self._list.clear()
        for name, data in self.presets.items():
            item = QListWidgetItem(f"{name} ({data['start']} ~ {data['end']})")
            item.setData(Qt.UserRole, name)
            self._list.addItem(item)

    def _on_item_selected(self, item):
        name = item.data(Qt.UserRole)
        if name in self.presets:
            data = self.presets[name]
            self._name_edit.setText(name)
            self._start_edit.setDateTime(QDateTime.fromString(data['start'], "yyyy-MM-dd HH:mm:ss"))
            self._end_edit.setDateTime(QDateTime.fromString(data['end'], "yyyy-MM-dd HH:mm:ss"))

    def _add_preset(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入预设名称")
            return

        if name in self.presets:
            QMessageBox.warning(self, "提示", f"预设 '{name}' 已存在，请使用保存修改")
            return

        self.presets[name] = {
            'start': self._start_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            'end': self._end_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        }
        self._load_presets()
        QMessageBox.information(self, "成功", f"已添加预设 '{name}'")

    def _update_preset(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入预设名称")
            return

        if name not in self.presets:
            QMessageBox.warning(self, "提示", f"预设 '{name}' 不存在，请使用添加")
            return

        self.presets[name] = {
            'start': self._start_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            'end': self._end_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        }
        self._load_presets()
        QMessageBox.information(self, "成功", f"已更新预设 '{name}'")

    def _delete_preset(self):
        name = self._name_edit.text().strip()
        if not name or name not in self.presets:
            QMessageBox.warning(self, "提示", "请先选择要删除的预设")
            return

        reply = QMessageBox.question(self, "确认", f"确定要删除预设 '{name}' 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.presets[name]
            self._load_presets()
            self._clear_form()

    def _clear_form(self):
        self._name_edit.clear()
        self._start_edit.setDateTime(QDateTime.currentDateTime().addSecs(-3600))
        self._end_edit.setDateTime(QDateTime.currentDateTime())
        self._list.clearSelection()

    def get_presets(self) -> Dict:
        return self.presets
