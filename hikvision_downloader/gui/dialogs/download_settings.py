# 下载设置对话框
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QSpinBox,
    QCheckBox, QComboBox, QLabel,
)


class DownloadSettingsDialog(QDialog):
    """下载设置对话框"""

    def __init__(self, parent=None,
                 total_thread_count=9, per_device_thread_count=3,
                 pack_duration=120, delete_original=False,
                 merge_mode='standard', enable_debug_log=True, skip_transcode=True):
        super().__init__(parent)
        self.setWindowTitle("下载设置")
        self.setMinimumWidth(450)
        self._build_ui()

        self._total_thread_spin.setValue(total_thread_count)
        self._per_device_thread_spin.setValue(per_device_thread_count)
        self._pack_spin.setValue(pack_duration)
        self._delete_chk.setChecked(delete_original)
        merge_mode_index = {'ultra': 0, 'fast': 1, 'standard': 2}.get(merge_mode, 0)
        self._merge_mode_combo.setCurrentIndex(merge_mode_index)
        self._debug_log_chk.setChecked(enable_debug_log)
        self._skip_transcode_chk.setChecked(skip_transcode)

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(12)

        # ===== 线程设置 =====
        thread_group = QLabel("<b>线程设置</b>")
        layout.addRow(thread_group)

        self._total_thread_spin = QSpinBox()
        self._total_thread_spin.setRange(1, 20)
        self._total_thread_spin.setValue(9)
        self._total_thread_spin.setSuffix(" 线程")
        layout.addRow("总下载线程数:", self._total_thread_spin)

        total_thread_hint = QLabel("<small>全局下载线程池大小，建议：9线程（1-20）<br/>多台NVR时可提高此值</small>")
        total_thread_hint.setWordWrap(True)
        total_thread_hint.setStyleSheet("color: #666;")
        layout.addRow("", total_thread_hint)

        self._per_device_thread_spin = QSpinBox()
        self._per_device_thread_spin.setRange(1, 6)
        self._per_device_thread_spin.setValue(3)
        self._per_device_thread_spin.setSuffix(" 线程")
        layout.addRow("每台NVR并发数:", self._per_device_thread_spin)

        per_device_hint = QLabel("<small>单台NVR最大并发连接数，建议：3线程（1-6）<br/>海康NVR每用户最多4个SDK连接</small>")
        per_device_hint.setWordWrap(True)
        per_device_hint.setStyleSheet("color: #666;")
        layout.addRow("", per_device_hint)

        layout.addRow(QLabel(""))  # 分隔

        # 合并模式设置
        self._merge_mode_combo = QComboBox()
        self._merge_mode_combo.addItem("极速模式（不转码，无faststart）", "ultra")
        self._merge_mode_combo.addItem("快速模式（不转码，有faststart）", "fast")
        self._merge_mode_combo.addItem("标准模式（转码合并，兼容性好）", "standard")
        self._merge_mode_combo.setCurrentIndex(0)
        layout.addRow("合并模式:", self._merge_mode_combo)

        merge_hint = QLabel("<small>极速模式：最快，适合本地播放<br/>快速模式：较快，适合网络播放<br/>标准模式：较慢，兼容性最好</small>")
        merge_hint.setWordWrap(True)
        merge_hint.setStyleSheet("color: #666;")
        layout.addRow("", merge_hint)

        layout.addRow(QLabel(""))  # 分隔

        # 调试日志设置
        self._debug_log_chk = QCheckBox("启用调试日志")
        self._debug_log_chk.setChecked(True)
        self._debug_log_chk.setToolTip("生成详细的下载和合并日志，用于排查合并点问题")
        layout.addRow("", self._debug_log_chk)

        debug_hint = QLabel("<small>启用后会在下载目录生成详细日志文件<br/>包含分段信息、合并点时间戳等</small>")
        debug_hint.setWordWrap(True)
        debug_hint.setStyleSheet("color: #666;")
        layout.addRow("", debug_hint)

        layout.addRow(QLabel(""))  # 分隔

        # 转码设置
        self._skip_transcode_chk = QCheckBox("跳过转码（原始格式）")
        self._skip_transcode_chk.setChecked(True)
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
            'total_thread_count': self._total_thread_spin.value(),
            'per_device_thread_count': self._per_device_thread_spin.value(),
            'pack_duration': self._pack_spin.value(),
            'delete_original': self._delete_chk.isChecked(),
            'merge_mode': self._merge_mode_combo.currentData(),
            'enable_debug_log': self._debug_log_chk.isChecked(),
            'skip_transcode': self._skip_transcode_chk.isChecked()
        }
