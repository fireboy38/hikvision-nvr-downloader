# 海康NVR批量录像下载工具
"""
Hikvision NVR Batch Video Downloader

基于海康威视NVR的ISAPI接口开发的批量录像下载工具
支持多通道录像批量下载和自动合并打包
"""

__version__ = "1.0.0"
__author__ = "Hikvision Downloader Team"

from .core.nvr_api import HikvisionISAPI
from .core.downloader import DownloadManager, DownloadTask, BatchDownloader
from .core.merger import VideoMerger, VideoSplitter
