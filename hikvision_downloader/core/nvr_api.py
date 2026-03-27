# 海康NVR ISAPI接口模块
# 职责：通过ISAPI HTTP接口获取设备/通道信息，录像下载
# ------------------------------------------------------------------ #
#  模块架构（2026-03-27 重构）：
#    HikvisionISAPI = HikvisionISAPIBase
#                          + DeviceInfoMixin        → core/device_info.py
#                          + ChannelManagerMixin     → core/channel_manager.py
#                          + OSDManagerMixin        → core/osd_manager.py
#                          + ISAPIDownloaderMixin    → core/isapi_downloader.py
#
#  基础类（HikvisionISAPIBase）只负责会话管理、连接测试、工具函数。
# ------------------------------------------------------------------ #
import base64
import json
import os
import re
import traceback
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPDigestAuth, HTTPBasicAuth

# 混入模块（功能分类）
from .device_info import DeviceInfoMixin
from .channel_manager import ChannelManagerMixin
from .osd_manager import OSDManagerMixin
from .isapi_downloader import ISAPIDownloaderMixin


# ------------------------------------------------------------------ #
#  基类：会话管理 + 连接测试 + 工具函数
# ------------------------------------------------------------------ #

class HikvisionISAPIBase:
    """海康ISAPI基类：仅包含会话管理和通用工具"""

    def __init__(self, host: str, port: int = 80,
                 username: str = "admin", password: str = "admin"):
        self.host     = host
        self.port     = port
        self.username = username
        self.password = password
        self.base_url = f"http://{host}:{port}"

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'HikvisionClient/1.0',
            'Accept': '*/*',
        })
        self.session.auth = HTTPDigestAuth(username, password)

    def test_connection(self) -> Tuple[bool, str]:
        """测试ISAPI连接，返回 (success, device_model)"""
        try:
            url = f"{self.base_url}/ISAPI/System/deviceInfo"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                model = self._parse_xml_text(resp.text, 'model')
                return True, model or "NVR设备"
            elif resp.status_code == 401:
                return False, "认证失败，请检查用户名/密码"
            else:
                return False, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return False, "连接超时"
        except requests.exceptions.ConnectionError:
            return False, "无法连接设备"
        except Exception as e:
            return False, str(e)

    def _parse_xml_text(self, xml_str: str, tag: str) -> Optional[str]:
        """从XML字符串提取指定标签的文本"""
        try:
            root = ET.fromstring(xml_str)
            ns = 'http://www.hikvision.com/ver20/XMLSchema'
            el = root.find(f'.//{{{ns}}}{tag}')
            if el is None:
                el = root.find(f'.//{tag}')
            return el.text if el is not None else None
        except Exception:
            return None


# ------------------------------------------------------------------ #
#  统一门面类：继承所有Mixin
# ------------------------------------------------------------------ #

class HikvisionISAPI(
    HikvisionISAPIBase,
    DeviceInfoMixin,
    ChannelManagerMixin,
    OSDManagerMixin,
    ISAPIDownloaderMixin,
):
    """
    海康ISAPI统一接口。
    通过Mixin机制组合以下功能：
      - DeviceInfoMixin:       设备信息/硬盘/系统状态/网络接口
      - ChannelManagerMixin:    通道名称/状态/流信息
      - OSDManagerMixin:       OSD名称设置
      - ISAPIDownloaderMixin:  ISAPI HTTP下载 + RTSP FFmpeg回退
    """
    pass


# ------------------------------------------------------------------ #
#  便利工厂
# ------------------------------------------------------------------ #

def create_isapi(config: Dict) -> HikvisionISAPI:
    """根据设备配置创建ISAPI连接"""
    return HikvisionISAPI(
        host     = config['host'],
        port     = config.get('http_port', 80),
        username = config.get('username', 'admin'),
        password = config.get('password', ''),
    )
