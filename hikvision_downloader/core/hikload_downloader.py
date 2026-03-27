"""
HikLoad 兼容下载器

基于 HikLoad 的设计理念，使用 ISAPI + RTSP + FFmpeg 实现批量录像下载
参考: https://pypi.org/project/hikload/
"""

import os
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Callable
from threading import Thread
import time

from .nvr_api import HikvisionISAPI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HikLoadDownloader:
    """HikLoad 兼容下载器 - 模拟 HikLoad 功能"""
    
    def __init__(self, nvr_ip: str, username: str, password: str, 
                 download_path: str = "Downloads",
                 video_format: str = "mkv",
                 use_ffmpeg: bool = True,
                 folder_structure: str = "onepercamera",  # onepercamera, oneperday, onepermonth
                 use_localtime: bool = True):
        """
        初始化 HikLoad 下载器
        
        Args:
            nvr_ip: NVR IP地址
            username: 用户名
            password: 密码
            download_path: 下载目录
            video_format: 视频格式 (mkv, mp4, avi)
            use_ffmpeg: 是否使用 FFmpeg 转码
            folder_structure: 文件夹组织方式
            use_localtime: 是否使用本地时间命名
        """
        self.nvr_ip = nvr_ip
        self.username = username
        self.password = password
        self.download_path = Path(download_path)
        self.video_format = video_format
        self.use_ffmpeg = use_ffmpeg
        self.folder_structure = folder_structure
        self.use_localtime = use_localtime
        
        # 初始化 NVR API
        self.nvr_api = HikvisionISAPI(nvr_ip, username, password)
        
        # 进度回调
        self.progress_callback: Optional[Callable[[int, str], None]] = None
        self.log_callback: Optional[Callable[[str], None]] = None
        
        # 停止标志
        self._stop_event = None
        
        logger.info(f"HikLoadDownloader initialized for {nvr_ip}")
    
    def set_progress_callback(self, callback: Callable[[int, str], None]):
        """设置进度回调: callback(progress_percent, status_text)"""
        self.progress_callback = callback
    
    def set_log_callback(self, callback: Callable[[str], None]):
        """设置日志回调: callback(log_message)"""
        self.log_callback = callback
    
    def _log(self, message: str):
        """内部日志方法"""
        logger.info(message)
        if self.log_callback:
            self.log_callback(message)
    
    def _update_progress(self, percent: int, status: str):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(percent, status)
    
    def stop(self):
        """停止下载"""
        if self._stop_event:
            self._stop_event.set()
            self._log("停止信号已发送")
    
    def download_videos(self, camera_ids: List[str], 
                       start_time: datetime, 
                       end_time: datetime,
                       concat_videos: bool = True) -> Dict[str, any]:
        """
        批量下载录像（HikLoad 风格）
        
        Args:
            camera_ids: 摄像头ID列表
            start_time: 开始时间
            end_time: 结束时间
            concat_videos: 是否自动合并视频片段
            
        Returns:
            下载结果统计
        """
        self._stop_event = None
        results = {
            'success': 0,
            'failed': 0,
            'total_size': 0,
            'videos': []
        }
        
        try:
            # 登录 NVR
            self._log(f"连接到 NVR: {self.nvr_ip}")
            self._update_progress(5, "正在登录NVR...")
            
            if not self.nvr_api.test_connection():
                raise Exception("无法连接到NVR，请检查网络和设备配置")
            
            # 下载每个摄像头的录像
            total_cameras = len(camera_ids)
            for idx, camera_id in enumerate(camera_ids):
                if self._stop_event and self._stop_event.is_set():
                    self._log("下载已停止")
                    break
                
                self._log(f"开始下载摄像头 {camera_id} 的录像...")
                self._update_progress(
                    10 + (idx * 80 // total_cameras),
                    f"正在下载摄像头 {camera_id}..."
                )
                
                try:
                    video_info = self._download_single_camera(
                        camera_id, start_time, end_time, concat_videos
                    )
                    
                    if video_info:
                        results['success'] += 1
                        results['total_size'] += video_info.get('size', 0)
                        results['videos'].append(video_info)
                        self._log(f"✓ 摄像头 {camera_id} 下载成功: {video_info['filepath']}")
                    else:
                        results['failed'] += 1
                        self._log(f"✗ 摄像头 {camera_id} 下载失败")
                        
                except Exception as e:
                    results['failed'] += 1
                    self._log(f"✗ 摄像头 {camera_id} 下载出错: {str(e)}")
                    logger.error(f"下载摄像头 {camera_id} 失败", exc_info=True)
            
            self._update_progress(100, f"下载完成: 成功 {results['success']}, 失败 {results['failed']}")
            self._log(f"下载任务完成，总计: {results['success']} 成功, {results['failed']} 失败")
            
        except Exception as e:
            self._log(f"下载任务失败: {str(e)}")
            logger.error("下载任务异常", exc_info=True)
            raise
        
        return results
    
    def _download_single_camera(self, camera_id: str, 
                               start_time: datetime, 
                               end_time: datetime,
                               concat_videos: bool) -> Optional[Dict[str, any]]:
        """
        下载单个摄像头的录像
        
        Returns:
            视频信息字典，失败返回 None
        """
        try:
            # 获取通道的 RTSP URL
            self._log(f"获取摄像头 {camera_id} 的流信息...")
            
            # 查询通道的码流信息
            stream_info = self.nvr_api.get_channel_stream_info(int(camera_id))
            if not stream_info:
                self._log(f"无法获取摄像头 {camera_id} 的流信息")
                return None
            
            self._log(f"摄像头 {camera_id} 分辨率: {stream_info.get('resolution', '未知')}, "
                     f"码率: {stream_info.get('bitrate', '未知')}")
            
            # 构建 RTSP URL
            # 格式: rtsp://username:password@ip:554/Streaming/tracks/101?starttime=20230101T120000Z&endtime=20230101T130000Z
            start_str = start_time.strftime('%Y%m%dT%H%M%SZ')
            end_str = end_time.strftime('%Y%m%dT%H%M%SZ')
            
            rtsp_url = (f"rtsp://{self.username}:{self.password}@{self.nvr_ip}:554/"
                       f"Streaming/tracks/{camera_id}01?starttime={start_str}&endtime={end_str}")
            
            # 确定输出路径
            output_dir = self._get_output_dir(camera_id, start_time)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 文件名格式: CameraID_YYYYMMDD_HHMMSS_YYYYMMDD_HHMMSS.format
            time_format = "%Y%m%d_%H%M%S"
            start_time_str = start_time.strftime(time_format)
            end_time_str = end_time.strftime(time_format)
            filename = f"{camera_id}_{start_time_str}_{end_time_str}.{self.video_format}"
            filepath = output_dir / filename
            
            self._log(f"RTSP URL: {rtsp_url}")
            self._log(f"输出文件: {filepath}")
            
            # 使用 FFmpeg 下载 RTSP 流
            success = self._download_with_ffmpeg(rtsp_url, str(filepath))
            
            if success and filepath.exists():
                file_size = filepath.stat().st_size
                self._log(f"下载完成，文件大小: {file_size / (1024*1024):.2f} MB")
                
                return {
                    'camera_id': camera_id,
                    'filepath': str(filepath),
                    'size': file_size,
                    'start_time': start_time,
                    'end_time': end_time
                }
            else:
                self._log("FFmpeg 下载失败")
                return None
                
        except Exception as e:
            self._log(f"下载摄像头 {camera_id} 失败: {str(e)}")
            logger.error(f"下载失败", exc_info=True)
            return None
    
    def _get_output_dir(self, camera_id: str, start_time: datetime) -> Path:
        """根据文件夹结构设置确定输出目录"""
        base_dir = self.download_path
        
        if self.folder_structure == "onepercamera":
            # 每个摄像头一个文件夹
            return base_dir / f"Camera_{camera_id}"
        elif self.folder_structure == "oneperday":
            # 每天一个文件夹
            date_str = start_time.strftime("%Y-%m-%d")
            return base_dir / date_str / f"Camera_{camera_id}"
        elif self.folder_structure == "onepermonth":
            # 每月一个文件夹
            month_str = start_time.strftime("%Y-%m")
            return base_dir / month_str / f"Camera_{camera_id}"
        else:
            return base_dir
    
    def _download_with_ffmpeg(self, rtsp_url: str, output_path: str) -> bool:
        """
        使用 FFmpeg 下载 RTSP 流（Windows 兼容版本）
        
        Args:
            rtsp_url: RTSP URL
            output_path: 输出文件路径
            
        Returns:
            是否成功
        """
        try:
            # 检查 FFmpeg 是否可用
            try:
                subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                self._log("错误: 未找到 FFmpeg，请确保 FFmpeg 已安装并添加到系统 PATH")
                return False

            # 构建 FFmpeg 命令（Windows 兼容）
            # -stimeout 在某些 FFmpeg 版本中不支持，改用 -rw_timeout（微秒）
            cmd = [
                "ffmpeg",
                "-rw_timeout", "10000000",  # 10秒超时（微秒）
                "-i", rtsp_url,
                "-c", "copy",  # 不重新编码，直接复制流
                "-y",  # 覆盖输出文件
                output_path
            ]
            
            self._log(f"执行 FFmpeg 命令: {' '.join(cmd)}")
            
            # 执行 FFmpeg 命令
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1小时超时
            )
            
            if process.returncode == 0:
                # 检查输出文件是否存在且非空
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                    self._log(f"FFmpeg 执行成功，文件大小: {file_size_mb:.2f} MB")
                    return True
                else:
                    self._log("FFmpeg 执行完成，但输出文件不存在或为空")
                    return False
            else:
                error_msg = process.stderr.strip() if process.stderr else "未知错误"
                self._log(f"FFmpeg 执行失败 (返回码: {process.returncode}): {error_msg}")
                
                # 提供常见错误提示
                if "404" in error_msg:
                    self._log("提示: RTSP 流未找到，请检查通道ID和时间段是否正确")
                elif "401" in error_msg or "Unauthorized" in error_msg:
                    self._log("提示: 认证失败，请检查用户名和密码")
                elif "timeout" in error_msg.lower():
                    self._log("提示: 连接超时，请检查网络连接和NVR配置")
                
                return False
                
        except subprocess.TimeoutExpired:
            self._log("FFmpeg 执行超时（超过1小时）")
            return False
        except Exception as e:
            self._log(f"FFmpeg 异常: {str(e)}")
            logger.error("FFmpeg 下载异常", exc_info=True)
            return False
    
    def download_async(self, camera_ids: List[str], 
                      start_time: datetime, 
                      end_time: datetime,
                      concat_videos: bool = True) -> Thread:
        """
        异步下载录像
        
        Returns:
            下载线程
        """
        def download_task():
            try:
                self.download_videos(camera_ids, start_time, end_time, concat_videos)
            except Exception as e:
                self._log(f"异步下载失败: {str(e)}")
                logger.error("异步下载异常", exc_info=True)
        
        thread = Thread(target=download_task, daemon=True)
        thread.start()
        return thread


# 兼容 HikLoad 命令行接口
def run_hikload_compatible(server: str, username: str, password: str,
                          cameras: str = None,
                          starttime: str = None,
                          endtime: str = None,
                          days: int = None,
                          downloads: str = "Downloads",
                          videoformat: str = "mkv",
                          ffmpeg: bool = True,
                          concat: bool = True,
                          debug: bool = False):
    """
    兼容 HikLoad 命令行接口的函数
    
    示例:
        run_hikload_compatible(
            server="192.168.1.100",
            username="admin",
            password="password",
            cameras="101,102",
            starttime="2023-10-01T08:00:00",
            endtime="2023-10-01T12:00:00",
            concat=True
        )
    """
    from datetime import datetime
    
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    
    # 解析时间
    if days:
        # 最近 N 天
        end_time = datetime.now()
        start_time = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
        start_time = start_time.timestamp() - (days * 86400)
        start_time = datetime.fromtimestamp(start_time)
    elif starttime and endtime:
        # ISO 格式时间
        start_time = datetime.fromisoformat(starttime.replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(endtime.replace('Z', '+00:00'))
    else:
        # 当天
        end_time = datetime.now()
        start_time = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 解析摄像头列表
    camera_ids = []
    if cameras:
        camera_ids = [cam.strip() for cam in cameras.split(',')]
    
    if not camera_ids:
        print("错误: 未指定摄像头ID")
        return
    
    # 创建下载器
    downloader = HikLoadDownloader(
        nvr_ip=server,
        username=username,
        password=password,
        download_path=downloads,
        video_format=videoformat,
        use_ffmpeg=ffmpeg
    )
    
    # 设置日志回调
    def log_callback(msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    
    downloader.set_log_callback(log_callback)
    
    # 执行下载
    print(f"开始下载 {len(camera_ids)} 个摄像头的录像...")
    print(f"时间范围: {start_time} 至 {end_time}")
    print(f"输出目录: {downloads}")
    print(f"视频格式: {videoformat}")
    print("-" * 60)
    
    results = downloader.download_videos(
        camera_ids=camera_ids,
        start_time=start_time,
        end_time=end_time,
        concat_videos=concat
    )
    
    print("-" * 60)
    print(f"下载完成!")
    print(f"成功: {results['success']} 个摄像头")
    print(f"失败: {results['failed']} 个摄像头")
    print(f"总大小: {results['total_size'] / (1024*1024):.2f} MB")


if __name__ == "__main__":
    # 测试示例
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("HikLoad 兼容下载器测试")
        print("=" * 60)
        
        # 测试参数
        test_params = {
            'server': '192.168.1.100',
            'username': 'admin',
            'password': 'password123',
            'cameras': '101,102',
            'starttime': '2023-10-01T08:00:00',
            'endtime': '2023-10-01T12:00:00',
            'downloads': 'HikLoad_Downloads',
            'concat': True,
            'debug': True
        }
        
        print("测试参数:")
        for k, v in test_params.items():
            print(f"  {k}: {v}")
        print("\n注意: 这只是一个接口测试，实际下载需要真实的 NVR 连接信息")
        print("=" * 60)
