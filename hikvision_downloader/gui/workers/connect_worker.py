# 后台连接线程
from typing import Dict, List
from PyQt5.QtCore import QThread, pyqtSignal


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
                sdk.logout_only()  # 只登出，不清理SDK
                self.result_ready.emit(False, f"登录失败: {msg}", {}, [])
                return

            channels = sdk.get_channels_with_names(
                total_ch=dev['total_ch'],
                start_chan=max(dev.get('start_dchan', 1), 1),
                nvr_ip=cfg['host'],
                nvr_port=cfg.get('http_port', 80),
                username=cfg.get('username', 'admin'),
                password=cfg.get('password', ''),
            )

            sdk.logout_only()  # 只登出，不清理SDK
            self.result_ready.emit(True, "连接成功", dev, channels)

        except Exception as e:
            self.result_ready.emit(False, f"异常: {e}", {}, [])
