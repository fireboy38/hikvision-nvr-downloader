# 下载工作线程处理器
# 将MainWindow中的下载worker方法提取到此处，减少主窗口文件体积
import os
import threading
import time
import subprocess
import signal as _signal
import urllib.parse
from typing import Dict, Optional

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

from core.downloader import DownloadTask, DownloadStatus


def isapi_download_worker(task: DownloadTask, stop_event: threading.Event,
                          main_window) -> None:
    """ISAPI下载工作线程：下载单个任务并更新表格"""
    from core.nvr_api import create_isapi

    config = task.device_config or {}
    channel_no = int(task.channel_id) if task.channel_id.isdigit() else 1

    try:
        api = create_isapi(config)

        def _progress(pct):
            task.progress = pct
            main_window._progress_signal.emit(task.task_id, pct)

        def _log(msg):
            main_window._log_signal.emit(f"[{task.channel_name}] {msg}")

        t0 = time.time()

        success, msg = api.download_record_by_time(
            channel=channel_no,
            start_time=task.start_time,
            end_time=task.end_time,
            save_path=task.file_path,
            stream_type=1,
            rtsp_port=config.get('rtsp_port', 554),
            progress_callback=_progress,
            log_callback=_log,
            stop_event=stop_event,
        )

        elapsed = time.time() - t0

        if success:
            task.status = DownloadStatus.COMPLETED
            task.progress = 100
            if os.path.exists(task.file_path):
                actual_size = os.path.getsize(task.file_path)
                main_window._task_file_sizes[task.task_id] = actual_size
                # 更新表格中的录像大小列
                QTimer.singleShot(0, lambda sz=actual_size: main_window._update_size_in_table(task.task_id, sz))
            main_window._log_signal.emit(f"✓ ISAPI下载完成: {task.channel_name} - {msg}, 耗时:{elapsed:.1f}s")
        else:
            task.status = DownloadStatus.FAILED
            task.error_message = msg
            main_window._log_signal.emit(f"✗ ISAPI下载失败: {task.channel_name} - {msg}")

        main_window._status_signal.emit(task.task_id)
        main_window._dm.tasks[task.task_id] = task
        QTimer.singleShot(0, lambda: main_window._on_task_done_bg(task.task_id, success, task.file_path, msg))

    except Exception as e:
        task.status = DownloadStatus.FAILED
        task.error_message = str(e)
        main_window._status_signal.emit(task.task_id)
        main_window._log_signal.emit(f"✗ ISAPI下载异常: {task.channel_name} - {str(e)}")
        main_window._dm.tasks[task.task_id] = task
        QTimer.singleShot(0, lambda: main_window._on_task_done_bg(task.task_id, False, "", str(e)))


def rtsp_download_worker(task: DownloadTask, stop_event: threading.Event,
                         main_window) -> None:
    """RTSP FFmpeg下载工作线程"""
    config = task.device_config or {}
    channel_no = int(task.channel_id) if task.channel_id.isdigit() else 1

    try:
        safe_user = urllib.parse.quote(config.get('username', 'admin'), safe='')
        safe_pass = urllib.parse.quote(config.get('password', ''), safe='')
        host = config.get('host', '')
        rtsp_port = config.get('rtsp_port', 554)
        track_id = f"{channel_no}01"
        start_str = task.start_time.strftime("%Y%m%dT%H%M%S")
        end_str = task.end_time.strftime("%Y%m%dT%H%M%S")

        rtsp_url = (
            f"rtsp://{safe_user}:{safe_pass}@{host}:{rtsp_port}"
            f"/Streaming/tracks/{track_id}"
            f"?starttime={start_str}Z&endtime={end_str}Z"
        )

        main_window._log_signal.emit(f"[{task.channel_name}] RTSP下载开始...")

        ffmpeg_path = r"C:\tools\ffmpeg\bin\ffmpeg.exe"
        if not os.path.exists(ffmpeg_path):
            ffmpeg_path = "ffmpeg"

        cmd = [
            ffmpeg_path, "-y",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-c:v", "copy", "-an",
            "-f", "mp4",
            task.file_path,
        ]

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0

        duration_sec = (task.end_time - task.start_time).total_seconds()
        t0 = time.time()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            creationflags=creation_flags,
        )

        while proc.poll() is None:
            if stop_event.is_set():
                try:
                    if os.name == 'nt':
                        proc.send_signal(_signal.CTRL_BREAK_EVENT)
                    else:
                        proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
                task.status = DownloadStatus.CANCELLED
                main_window._status_signal.emit(task.task_id)
                return

            elapsed = time.time() - t0
            if duration_sec > 0:
                pct = min(int((elapsed / duration_sec) * 100), 99)
                task.progress = pct
                main_window._progress_signal.emit(task.task_id, pct)

            threading.Event().wait(0.5)

        stdout, stderr = proc.communicate(timeout=5)

        elapsed = time.time() - t0
        if proc.returncode == 0 and os.path.exists(task.file_path):
            file_size = os.path.getsize(task.file_path) / (1024 * 1024)
            task.status = DownloadStatus.COMPLETED
            task.progress = 100
            main_window._task_file_sizes[task.task_id] = os.path.getsize(task.file_path)
            # 更新表格中的录像大小列
            QTimer.singleShot(0, lambda sz=os.path.getsize(task.file_path): main_window._update_size_in_table(task.task_id, sz))
            main_window._log_signal.emit(f"✓ RTSP下载完成: {task.channel_name} - {file_size:.2f}MB, 耗时{elapsed:.0f}s")
        else:
            error_msg = (stderr.decode('utf-8', errors='ignore') if stderr else "")
            task.status = DownloadStatus.FAILED
            task.error_message = error_msg[-300:]
            main_window._log_signal.emit(f"✗ RTSP下载失败: {task.channel_name} - {error_msg[-200:]}")

        main_window._status_signal.emit(task.task_id)
        main_window._dm.tasks[task.task_id] = task
        QTimer.singleShot(0, lambda: main_window._on_task_done_bg(
            task.task_id, task.status == DownloadStatus.COMPLETED, task.file_path, task.error_message))

    except Exception as e:
        task.status = DownloadStatus.FAILED
        task.error_message = str(e)
        main_window._status_signal.emit(task.task_id)
        main_window._log_signal.emit(f"✗ RTSP下载异常: {task.channel_name} - {str(e)}")
        main_window._dm.tasks[task.task_id] = task
        QTimer.singleShot(0, lambda: main_window._on_task_done_bg(task.task_id, False, "", str(e)))
