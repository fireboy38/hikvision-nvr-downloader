# RTSP回放流下载模块
# 使用FFmpeg通过RTSP协议下载历史录像回放
import os
import subprocess
import threading
import time
from datetime import datetime
from typing import Optional, Callable, Dict, Any, Tuple
import signal

# FFmpeg路径（与java_downloader.py保持一致）
FFMPEG_PATH = r"C:\tools\ffmpeg\bin\ffmpeg.exe"


class RTSPPlaybackDownloader:
    """RTSP回放流下载器 - 用于下载历史录像"""
    
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        
    def _build_rtsp_playback_url(self, 
                                 host: str, 
                                 port: int, 
                                 username: str, 
                                 password: str,
                                 channel: int, 
                                 start_time: datetime,
                                 end_time: datetime,
                                 stream_type: str = "main") -> str:
        """
        构建RTSP回放URL
        
        海康NVR RTSP回放格式:
        rtsp://username:password@ip:port/Streaming/tracks/<trackID>?starttime=<ISO8601>&endtime=<ISO8601>
        
        trackID格式: <channel>0<stream_type>0<track>
        - channel: 通道号 (1-128)
        - stream_type: 1=主码流, 2=子码流
        - track: 1=视频, 2=音频, 3=音视频
        
        时间格式: YYYYMMDDTHHMMSSZ (ISO 8601 UTC格式)
        """
        # trackID格式: <通道号><码流类型>
        # 码流类型: 01=主码流, 02=子码流
        # 例: 通道1主码流 → 101, 通道2子码流 → 202
        stream_code = "01" if stream_type == "main" else "02"
        track_id = f"{channel}{stream_code}"
        
        # 转换时间为ISO 8601 UTC格式
        # 注意：海康设备通常使用本地时间，不需要Z后缀，或者需要根据实际情况调整
        start_str = start_time.strftime("%Y%m%dT%H%M%S")
        end_str = end_time.strftime("%Y%m%dT%H%M%S")
        
        # URL编码密码中的特殊字符
        safe_password = password.replace('@', '%40').replace(':', '%3A').replace('/', '%2F')
        safe_username = username.replace('@', '%40').replace(':', '%3A')
        
        url = f"rtsp://{safe_username}:{safe_password}@{host}:{port}/Streaming/tracks/{track_id}?starttime={start_str}Z&endtime={end_str}Z"
        return url
    
    def download_playback(self,
                         host: str,
                         port: int,
                         username: str,
                         password: str,
                         channel: int,
                         start_time: datetime,
                         end_time: datetime,
                         save_path: str,
                         stream_type: str = "main",
                         progress_callback: Optional[Callable[[int], None]] = None,
                         log_callback: Optional[Callable[[str], None]] = None,
                         stop_event: Optional[threading.Event] = None) -> Tuple[bool, str]:
        """
        下载历史录像回放
        
        Args:
            host: NVR IP地址
            port: RTSP端口 (默认554)
            username: 用户名
            password: 密码
            channel: 通道号 (1-128)
            start_time: 开始时间
            end_time: 结束时间
            save_path: 保存路径
            stream_type: 码流类型 ("main"主码流 / "sub"子码流)
            progress_callback: 进度回调函数(progress: int)
            log_callback: 日志回调函数(msg: str)
            stop_event: 停止事件，用于中断下载
            
        Returns:
            (success, message)
        """
        rtsp_url = self._build_rtsp_playback_url(
            host, port, username, password, channel, 
            start_time, end_time, stream_type
        )
        
        duration = (end_time - start_time).total_seconds()
        
        if log_callback:
            log_callback(f"[RTSP回放] 开始下载通道{channel}历史录像...")
            log_callback(f"[RTSP回放] 时间范围: {start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            log_callback(f"[RTSP回放] 预计时长: {duration:.0f}秒")
            log_callback(f"[RTSP回放] URL: rtsp://{username}:****@{host}:{port}/Streaming/tracks/{channel}{'01' if stream_type=='main' else '02'}")
        
        # 确保保存目录存在
        save_dir = os.path.dirname(save_path)
        if save_dir and not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)

        # 两套命令：
        #   方案A：视频直复制 + 音频转AAC（保留音频）
        #   方案B：视频直复制 + 丢弃音频（回退，解决 pcm_alaw 不支持 MP4 的问题）
        cmd_with_audio = [
            FFMPEG_PATH,
            "-y",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "64k",
            "-f", "mp4",
            "-movflags", "+faststart",
            save_path,
        ]
        cmd_no_audio = [
            FFMPEG_PATH,
            "-y",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-c:v", "copy",
            "-an",
            "-f", "mp4",
            "-movflags", "+faststart",
            save_path,
        ]

        if log_callback:
            log_callback(f"[RTSP回放] FFmpeg命令: {' '.join(cmd_with_audio[:5])} ... {cmd_with_audio[-1]}")

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0

        for attempt, cmd in enumerate([cmd_with_audio, cmd_no_audio], start=1):
            if stop_event and stop_event.is_set():
                return False, "用户取消下载"

            if attempt == 2 and log_callback:
                log_callback("[RTSP回放] 音频转AAC失败，改为丢弃音频重试...")

            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    startupinfo=startupinfo,
                    creationflags=creation_flags,
                )

                # 监控进度
                start_timestamp = time.time()
                last_progress = 0

                while self._process.poll() is None:
                    if stop_event and stop_event.is_set():
                        self._stop_download()
                        return False, "用户取消下载"

                    elapsed = time.time() - start_timestamp
                    if duration > 0:
                        progress = min(int((elapsed / duration) * 100), 99)
                        if progress != last_progress and progress_callback:
                            progress_callback(progress)
                            last_progress = progress

                    time.sleep(0.5)

                stdout, stderr = self._process.communicate(timeout=5)
                return_code = self._process.returncode

                if return_code == 0:
                    file_size = os.path.getsize(save_path) / (1024 * 1024)
                    actual_duration = time.time() - start_timestamp
                    if progress_callback:
                        progress_callback(100)
                    audio_note = "（含音频）" if attempt == 1 else "（无音频）"
                    return True, f"下载完成{audio_note}，文件大小: {file_size:.2f}MB，实际耗时: {actual_duration:.0f}秒"

                # 失败：分析错误
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else ""
                if "404" in error_msg or "Not Found" in error_msg:
                    return False, "录像不存在或时间范围无效"
                elif "401" in error_msg or "Unauthorized" in error_msg:
                    return False, "认证失败，请检查用户名密码"
                elif "Connection refused" in error_msg:
                    return False, "连接被拒绝，请检查RTSP端口"
                # pcm_alaw / codec not supported → 继续尝试方案B
                elif attempt == 1 and ("codec not currently supported" in error_msg
                                       or "Could not find tag for codec" in error_msg
                                       or "Invalid argument" in error_msg):
                    continue  # 进入方案B
                else:
                    return False, f"FFmpeg错误: {error_msg[-500:]}"

            except subprocess.TimeoutExpired:
                self._stop_download()
                return False, "FFmpeg进程超时"
            except Exception as e:
                self._stop_download()
                return False, f"下载异常: {str(e)}"
            finally:
                self._process = None

        return False, "两种音频方案均失败，请检查设备连接或录像是否存在"
    
    def _stop_download(self):
        """停止下载进程"""
        if self._process and self._process.poll() is None:
            try:
                if os.name == 'nt':
                    self._process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    self._process.terminate()
                self._process.wait(timeout=3)
            except:
                try:
                    self._process.kill()
                except:
                    pass
    
    def stop(self):
        """停止下载"""
        self._stop_download()


class RTSPPlaybackBatchDownloader:
    """RTSP回放批量下载管理器"""
    
    def __init__(self, max_concurrent: int = 2):
        self.max_concurrent = max_concurrent
        self._active_downloads: Dict[str, RTSPPlaybackDownloader] = {}
        self._lock = threading.Lock()
        
    def download(self,
                 task_id: str,
                 host: str,
                 port: int,
                 username: str,
                 password: str,
                 channel: int,
                 start_time: datetime,
                 end_time: datetime,
                 save_path: str,
                 stream_type: str = "main",
                 progress_callback: Optional[Callable[[str, int], None]] = None,
                 log_callback: Optional[Callable[[str], None]] = None,
                 completion_callback: Optional[Callable[[str, bool, str], None]] = None) -> bool:
        """
        启动一个RTSP回放下载任务
        
        Args:
            task_id: 任务唯一标识
            host, port, username, password: 设备连接信息
            channel: 通道号
            start_time, end_time: 回放时间范围
            save_path: 保存路径
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
            
            downloader = RTSPPlaybackDownloader()
            self._active_downloads[task_id] = downloader
        
        def _progress(p: int):
            if progress_callback:
                progress_callback(task_id, p)
        
        def _log(msg: str):
            if log_callback:
                log_callback(msg)
        
        def _download_thread():
            try:
                success, message = downloader.download_playback(
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    channel=channel,
                    start_time=start_time,
                    end_time=end_time,
                    save_path=save_path,
                    stream_type=stream_type,
                    progress_callback=_progress,
                    log_callback=_log
                )
                
                if completion_callback:
                    completion_callback(task_id, success, message)
                    
            finally:
                with self._lock:
                    self._active_downloads.pop(task_id, None)
        
        thread = threading.Thread(target=_download_thread, name=f"RTSP-Playback-{task_id}", daemon=True)
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


def download_rtsp_playback(ip: str,
                          port: int,
                          username: str,
                          password: str,
                          channel: int,
                          start_time: datetime,
                          end_time: datetime,
                          save_path: str,
                          stream_type: str = "main",
                          progress_callback: Optional[Callable[[int], None]] = None,
                          log_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
    """
    便捷函数：下载RTSP回放流
    
    Args:
        ip: NVR IP地址
        port: RTSP端口 (默认554)
        username: 用户名
        password: 密码
        channel: 通道号
        start_time: 开始时间
        end_time: 结束时间
        save_path: 保存文件路径
        stream_type: 码流类型 ("main"/"sub")
        progress_callback: 进度回调
        log_callback: 日志回调
        
    Returns:
        (success, message)
    """
    downloader = RTSPPlaybackDownloader()
    return downloader.download_playback(
        host=ip,
        port=port,
        username=username,
        password=password,
        channel=channel,
        start_time=start_time,
        end_time=end_time,
        save_path=save_path,
        stream_type=stream_type,
        progress_callback=progress_callback,
        log_callback=log_callback
    )
