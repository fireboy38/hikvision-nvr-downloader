# RTSP实时流下载模块
# 使用FFmpeg通过RTSP协议下载实时视频流
import os
import subprocess
import threading
import time
from datetime import datetime
from typing import Optional, Callable, Dict, Any, Tuple
import signal

# FFmpeg路径（与java_downloader.py保持一致）
FFMPEG_PATH = r"C:\tools\ffmpeg\bin\ffmpeg.exe"


class RTSPDownloader:
    """RTSP实时流下载器"""
    
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        self._download_thread: Optional[threading.Thread] = None
        
    def _build_rtsp_url(self, host: str, port: int, username: str, password: str, 
                        channel: int, stream_type: str = "main") -> str:
        """
        构建RTSP URL
        
        海康NVR RTSP格式:
        - 主码流: rtsp://username:password@ip:port/Streaming/Channels/101
        - 子码流: rtsp://username:password@ip:port/Streaming/Channels/102
        - 通道N主码流: rtsp://username:password@ip:port/Streaming/Channels/N01
        """
        stream_suffix = "01" if stream_type == "main" else "02"
        channel_code = f"{channel}{stream_suffix}"
        
        # URL编码密码中的特殊字符
        safe_password = password.replace('@', '%40').replace(':', '%3A').replace('/', '%2F')
        safe_username = username.replace('@', '%40').replace(':', '%3A')
        
        return f"rtsp://{safe_username}:{safe_password}@{host}:{port}/Streaming/Channels/{channel_code}"
    
    def download_live_stream(self,
                           host: str,
                           port: int,
                           username: str,
                           password: str,
                           channel: int,
                           save_path: str,
                           duration: int = 60,
                           stream_type: str = "main",
                           progress_callback: Optional[Callable[[int], None]] = None,
                           log_callback: Optional[Callable[[str], None]] = None,
                           stop_event: Optional[threading.Event] = None) -> Tuple[bool, str]:
        """
        下载实时视频流
        
        Args:
            host: NVR IP地址
            port: RTSP端口 (默认554)
            username: 用户名
            password: 密码
            channel: 通道号 (1-128)
            save_path: 保存路径
            duration: 录制时长(秒)，0表示持续录制直到手动停止
            stream_type: 码流类型 ("main"主码流 / "sub"子码流)
            progress_callback: 进度回调函数(progress: int)
            log_callback: 日志回调函数(msg: str)
            stop_event: 停止事件，用于中断下载
            
        Returns:
            (success, message)
        """
        rtsp_url = self._build_rtsp_url(host, port, username, password, channel, stream_type)
        
        if log_callback:
            log_callback(f"[RTSP] 开始下载通道{channel}实时流...")
            log_callback(f"[RTSP] URL: rtsp://{username}:****@{host}:{port}/Streaming/Channels/{channel}01")
        
        # 确保保存目录存在
        save_dir = os.path.dirname(save_path)
        if save_dir and not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
        
        # 构建FFmpeg命令
        cmd = [
            FFMPEG_PATH,
            "-y",  # 覆盖已存在文件
            "-rtsp_transport", "tcp",  # 使用TCP传输，更稳定
            "-i", rtsp_url,  # 输入RTSP流
            "-c", "copy",  # 直接复制，不重新编码
            "-f", "mp4",  # 输出格式
            "-movflags", "+faststart",  # 优化网络播放
        ]
        
        # 如果指定了时长，添加-t参数
        if duration > 0:
            cmd.extend(["-t", str(duration)])
        
        cmd.append(save_path)
        
        if log_callback:
            log_callback(f"[RTSP] FFmpeg命令: {' '.join(cmd[:5])} ... {cmd[-1]}")
        
        try:
            # 启动FFmpeg进程
            startupinfo = None
            if os.name == 'nt':  # Windows
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            
            # 使用线程监控进度
            start_time = time.time()
            last_progress = 0
            
            # 如果指定了时长，显示进度
            if duration > 0 and progress_callback:
                while self._process.poll() is None:
                    # 检查停止事件
                    if stop_event and stop_event.is_set():
                        self._stop_download()
                        return False, "用户取消下载"
                    
                    elapsed = time.time() - start_time
                    progress = min(int((elapsed / duration) * 100), 99)
                    
                    if progress != last_progress:
                        progress_callback(progress)
                        last_progress = progress
                    
                    time.sleep(0.5)
            else:
                # 持续录制模式，等待停止信号
                while self._process.poll() is None:
                    if stop_event and stop_event.is_set():
                        self._stop_download()
                        return False, "用户取消下载"
                    time.sleep(0.5)
            
            # 等待进程结束
            stdout, stderr = self._process.communicate(timeout=5)
            return_code = self._process.returncode
            
            if return_code == 0:
                file_size = os.path.getsize(save_path) / (1024 * 1024)  # MB
                if progress_callback:
                    progress_callback(100)
                return True, f"下载完成，文件大小: {file_size:.2f}MB"
            else:
                error_msg = stderr.decode('utf-8', errors='ignore')[-500:] if stderr else "未知错误"
                return False, f"FFmpeg错误 (code {return_code}): {error_msg}"
                
        except subprocess.TimeoutExpired:
            self._stop_download()
            return False, "FFmpeg进程超时"
        except Exception as e:
            self._stop_download()
            return False, f"下载异常: {str(e)}"
        finally:
            self._process = None
    
    def _stop_download(self):
        """停止下载进程"""
        if self._process and self._process.poll() is None:
            try:
                if os.name == 'nt':
                    # Windows: 发送CTRL_BREAK_EVENT
                    self._process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    self._process.terminate()
                
                # 等待进程结束
                self._process.wait(timeout=3)
            except:
                # 强制结束
                try:
                    self._process.kill()
                except:
                    pass
    
    def stop(self):
        """停止下载"""
        self._stop_download()


class RTSPBatchDownloader:
    """RTSP批量下载管理器"""
    
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self._active_downloads: Dict[str, RTSPDownloader] = {}
        self._lock = threading.Lock()
        
    def download(self,
                 task_id: str,
                 host: str,
                 port: int,
                 username: str,
                 password: str,
                 channel: int,
                 save_path: str,
                 duration: int = 60,
                 stream_type: str = "main",
                 progress_callback: Optional[Callable[[str, int], None]] = None,
                 log_callback: Optional[Callable[[str], None]] = None,
                 completion_callback: Optional[Callable[[str, bool, str], None]] = None) -> bool:
        """
        启动一个RTSP下载任务
        
        Args:
            task_id: 任务唯一标识
            host, port, username, password: 设备连接信息
            channel: 通道号
            save_path: 保存路径
            duration: 录制时长(秒)
            stream_type: 码流类型
            progress_callback: 进度回调(task_id, progress)
            log_callback: 日志回调(msg)
            completion_callback: 完成回调(task_id, success, message)
            
        Returns:
            是否成功启动
        """
        with self._lock:
            if task_id in self._active_downloads:
                return False
            
            downloader = RTSPDownloader()
            self._active_downloads[task_id] = downloader
        
        def _progress(p: int):
            if progress_callback:
                progress_callback(task_id, p)
        
        def _log(msg: str):
            if log_callback:
                log_callback(msg)
        
        def _download_thread():
            try:
                success, message = downloader.download_live_stream(
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    channel=channel,
                    save_path=save_path,
                    duration=duration,
                    stream_type=stream_type,
                    progress_callback=_progress,
                    log_callback=_log
                )
                
                if completion_callback:
                    completion_callback(task_id, success, message)
                    
            finally:
                with self._lock:
                    self._active_downloads.pop(task_id, None)
        
        thread = threading.Thread(target=_download_thread, name=f"RTSP-{task_id}", daemon=True)
        thread.start()
        return True
    
    def stop_task(self, task_id: str) -> bool:
        """停止指定任务"""
        with self._lock:
            downloader = self._active_downloads.get(task_id)
            if downloader:
                downloader.stop()
                return True
            return False
    
    def stop_all(self):
        """停止所有任务"""
        with self._lock:
            for downloader in self._active_downloads.values():
                downloader.stop()
            self._active_downloads.clear()


def download_rtsp_live(ip: str,
                      port: int,
                      username: str,
                      password: str,
                      channel: int,
                      save_path: str,
                      duration: int = 60,
                      stream_type: str = "main",
                      progress_callback: Optional[Callable[[int], None]] = None,
                      log_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
    """
    便捷函数：下载RTSP实时流
    
    Args:
        ip: NVR IP地址
        port: RTSP端口 (默认554)
        username: 用户名
        password: 密码
        channel: 通道号
        save_path: 保存文件路径
        duration: 录制时长(秒)
        stream_type: 码流类型 ("main"/"sub")
        progress_callback: 进度回调
        log_callback: 日志回调
        
    Returns:
        (success, message)
    """
    downloader = RTSPDownloader()
    return downloader.download_live_stream(
        host=ip,
        port=port,
        username=username,
        password=password,
        channel=channel,
        save_path=save_path,
        duration=duration,
        stream_type=stream_type,
        progress_callback=progress_callback,
        log_callback=log_callback
    )
