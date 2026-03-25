# 录像下载管理器（SDK版）
# 使用海康HCNetSDK.dll进行回放下载，替代原ISAPI方案
import os
import threading
import time
import queue
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class DownloadStatus(Enum):
    """下载状态"""
    PENDING     = "pending"
    DOWNLOADING = "downloading"
    COMPLETED   = "completed"
    FAILED      = "failed"
    CANCELLED   = "cancelled"


@dataclass
class DownloadTask:
    """下载任务"""
    task_id:      str
    device_id:    str
    device_name:  str
    channel_id:   str        # 字符串通道号，如 "1"
    channel_name: str
    start_time:   datetime
    end_time:     datetime
    save_dir:     str
    status:       DownloadStatus = DownloadStatus.PENDING
    progress:     int = 0
    file_path:    str = ""
    error_message:str = ""
    created_at:   datetime = field(default_factory=datetime.now)
    device_config: Optional[Dict[str, Any]] = None  # 设备配置（支持多设备）
    merge_mode:   str = "standard"  # 合并模式：fast 或 standard
    enable_debug_log: bool = False  # 是否启用调试日志
    skip_transcode: bool = True  # 是否跳过转码（默认跳过）


    def __post_init__(self):
        # 生成文件名：通道名称_日期_时段.mp4
        date_str   = self.start_time.strftime("%Y%m%d")
        time_range = f"{self.start_time.strftime('%H%M%S')}_{self.end_time.strftime('%H%M%S')}"

        import re

        # 使用通道名称（包含中文）
        # Java会处理中文文件名，不经过Windows命令行
        safe_channel = self.channel_name.strip()

        # 移除文件名中不允许的字符
        safe_channel = re.sub(r'[\\/:*?"<>|]', '', safe_channel)  # Windows不允许的字符
        safe_channel = safe_channel or f"CH{self.channel_id}"  # 如果清理后为空，使用CHx

        filename   = f"{safe_channel}_{date_str}_{time_range}.mp4"
        self.file_path = os.path.join(self.save_dir, filename)
        print(f"[Downloader] 文件路径: {self.file_path}")


@dataclass
class DownloadResult:
    """下载结果"""
    task_id:       str
    success:       bool
    file_path:     str   = ""
    error_message: str   = ""
    download_time: float = 0.0


# ------------------------------------------------------------------ #
#  下载管理器
# ------------------------------------------------------------------ #

class DownloadManager:
    """
    SDK模式下载任务管理器
    - 每个设备连接独立管理
    - 支持多通道顺序/并发下载
    - 线程安全
    - 每台NVR最多 MAX_CONCURRENT_PER_DEVICE 个并发连接（避免超出设备限制）
    """

    # 每台NVR允许的最大并发下载数（海康NVR默认每用户最多4个SDK连接）
    MAX_CONCURRENT_PER_DEVICE = 3

    def __init__(self, max_concurrent: int = 2):
        self.max_concurrent = max_concurrent
        self.tasks:   Dict[str, DownloadTask]   = {}
        self.results: Dict[str, DownloadResult] = {}
        self._queue   = queue.Queue()
        self._lock    = threading.Lock()
        self._running = False
        self._workers: List[threading.Thread] = []

        # 外部回调
        self.on_progress:   Optional[Callable[[str, int], None]]           = None
        self.on_status:     Optional[Callable[[DownloadTask], None]]       = None
        self.on_completion: Optional[Callable[[DownloadTask], None]]       = None
        self.on_log:        Optional[Callable[[str], None]]                = None  # 日志回调

        # 设备连接配置（start()时注入）
        self._device_config: Optional[Dict[str, Any]] = None

        # 按设备的并发信号量 {device_id: Semaphore}
        # 每台NVR最多同时 MAX_CONCURRENT_PER_DEVICE 个下载
        self._device_semaphores: Dict[str, threading.Semaphore] = {}

    # -------- 任务管理 --------

    def add_task(self, task: DownloadTask) -> str:
        with self._lock:
            self.tasks[task.task_id] = task
            self._queue.put(task.task_id)
        return task.task_id

    def add_tasks_batch(self, tasks: List[DownloadTask]) -> List[str]:
        with self._lock:
            ids = []
            for t in tasks:
                self.tasks[t.task_id] = t
                self._queue.put(t.task_id)
                ids.append(t.task_id)
        return ids

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.status == DownloadStatus.PENDING:
                task.status = DownloadStatus.CANCELLED
                return True
        return False

    def cancel_all(self):
        with self._lock:
            for task in self.tasks.values():
                if task.status in (DownloadStatus.PENDING, DownloadStatus.DOWNLOADING):
                    task.status = DownloadStatus.CANCELLED

    def clear_completed(self):
        with self._lock:
            done = [tid for tid, t in self.tasks.items()
                    if t.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED)]
            for tid in done:
                del self.tasks[tid]

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[DownloadTask]:
        return list(self.tasks.values())

    # -------- 回调设置 --------

    def set_progress_callback(self, cb: Callable):
        self.on_progress = cb

    def set_status_callback(self, cb: Callable):
        self.on_status = cb

    def set_completion_callback(self, cb: Callable):
        self.on_completion = cb

    def set_log_callback(self, cb: Callable):
        """设置日志回调，用于输出到GUI日志框"""
        self.on_log = cb

    # -------- 启动 / 停止 --------

    def start(self, device_config: Optional[Dict[str, Any]] = None):
        """启动下载管理器

        Args:
            device_config: 设备配置（可选）。如果未提供，则从每个任务的 device_config 字段读取
        """
        if self._running:
            return
        self._device_config = device_config if device_config else {}
        self._running = True
        # 使用当前的max_concurrent值创建工作线程
        thread_count = self.max_concurrent
        print(f"[DownloadManager] 启动 {thread_count} 个下载线程...")
        for _ in range(thread_count):
            w = threading.Thread(target=self._worker, daemon=True)
            w.start()
            self._workers.append(w)

    def stop(self):
        self._running = False
        self.cancel_all()
        for w in self._workers:
            w.join(timeout=3)
        self._workers.clear()

    # -------- 工作线程 --------

    def _worker(self):
        """每个工作线程使用Python SDK下载器（原生SDK支持进度查询）"""

        while self._running:
            try:
                task_id = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            task = self.tasks.get(task_id)
            if not task or task.status == DownloadStatus.CANCELLED:
                self._queue.task_done()
                continue

            self._run_task_hiksdk(task)
            self._queue.task_done()

    def _get_device_semaphore(self, device_id: str) -> threading.Semaphore:
        """获取或创建设备的并发信号量（线程安全）"""
        with self._lock:
            if device_id not in self._device_semaphores:
                self._device_semaphores[device_id] = threading.Semaphore(
                    self.MAX_CONCURRENT_PER_DEVICE
                )
                print(f"[DownloadManager] 为设备 {device_id} 创建并发限制 (最多{self.MAX_CONCURRENT_PER_DEVICE}个并发)")
            return self._device_semaphores[device_id]

    def _run_task_hiksdk(self, task: DownloadTask):
        """使用Java下载器执行下载任务（避免中文编码问题）"""
        from .java_downloader import download_with_java

        # 更新状态
        task.status = DownloadStatus.DOWNLOADING
        task.progress = 0
        self._fire_status(task)

        t0 = time.time()

        def _progress(p: int):
            task.progress = p
            if self.on_progress:
                try:
                    self.on_progress(task.task_id, p)
                except Exception as e:
                    print(f"[JavaDownloader] 回调异常: {e}")

        def _gui_log(msg: str):
            """GUI日志回调"""
            print(f"[DownloadManager DEBUG] _gui_log called: {msg[:50]}..., on_log={'set' if self.on_log else 'None'}")
            if self.on_log:
                try:
                    self.on_log(msg)
                    print(f"[DownloadManager DEBUG] on_log callback executed")
                except Exception as e:
                    print(f"[JavaDownloader] 日志回调异常: {e}")
            else:
                print(f"[DownloadManager DEBUG] on_log is None, skipping callback")

        try:
            # 从任务中获取设备配置（支持多设备）
            cfg = task.device_config if task.device_config else self._device_config
            if not cfg:
                raise Exception("设备配置未设置")

            channel_no = int(task.channel_id) if task.channel_id.isdigit() else 1

            # 动态计算超时时间（更宽松的计算）
            duration_sec = (task.end_time - task.start_time).total_seconds()
            # 基础时间：每10分钟录像至少需要15分钟下载时间，最少30分钟
            timeout = int(max(1800, duration_sec * 1.5))  # 至少30分钟，或者录像时长的1.5倍
            timeout = min(timeout, 14400)  # 最多4小时

            # 获取该设备的并发信号量，避免同一台NVR并发连接超限
            device_id = task.device_id or f"{cfg.get('host', '')}:{cfg.get('port', 8000)}"
            sem = self._get_device_semaphore(device_id)

            # 重试参数
            max_retries = 3
            retry_delay = 5  # 每次重试前等待5秒

            for attempt in range(1, max_retries + 1):
                # 获取信号量（等待轮到自己）
                print(f"[DownloadManager] 等待设备 {device_id} 的下载槽位 (通道{channel_no}, 尝试{attempt}/{max_retries})...")
                acquired = sem.acquire(timeout=300)  # 最多等5分钟排队
                if not acquired:
                    raise Exception(f"等待设备下载槽位超时 (设备:{device_id})")

                try:
                    print(f"[DownloadManager] 获得下载槽位, 开始下载 {device_id} 通道{channel_no} (尝试{attempt}/{max_retries})")
                    # 使用Java下载器（支持中文文件名）
                    success, msg = download_with_java(
                        ip=cfg.get('host', ''),
                        port=cfg.get('port', 8000),
                        username=cfg.get('username', 'admin'),
                        password=cfg.get('password', ''),
                        channel=channel_no,
                        start_time=task.start_time,
                        end_time=task.end_time,
                        save_path=task.file_path,
                        channel_name=task.channel_name,
                        progress_callback=_progress,
                        timeout=timeout,
                        merge_mode=task.merge_mode,
                        enable_debug_log=task.enable_debug_log,
                        gui_log_callback=_gui_log,
                        skip_transcode=task.skip_transcode
                    )

                finally:
                    sem.release()
                    print(f"[DownloadManager] 释放设备 {device_id} 的下载槽位 (通道{channel_no})")

                # 判断是否需要重试（登录失败类错误才重试）
                if success:
                    break
                login_errors = ["登录失败", "连接数量超限", "Login failed", "连接超时", "error: 7", "error: 4"]
                should_retry = any(e in msg for e in login_errors)
                if should_retry and attempt < max_retries:
                    wait = retry_delay * attempt
                    print(f"[DownloadManager] 下载失败(可能是并发限制), {wait}秒后重试... 错误:{msg}")
                    time.sleep(wait)
                else:
                    break

            elapsed = time.time() - t0

            # Java下载器会返回最终文件路径（可能已经重命名）
            print(f"[JavaDownloader] 下载结果: success={success}")
            print(f"[JavaDownloader] 消息: {msg}")

            if success:
                task.status = DownloadStatus.COMPLETED
                task.progress = 100
                task.error_message = ""
                success_msg = f"✓ 下载完成: ch{channel_no} ({task.channel_name}) - {msg}, 耗时:{elapsed:.1f}秒"
                print(f"[JavaDownloader] {success_msg}")
                _gui_log(success_msg)
            else:
                task.status = DownloadStatus.FAILED
                task.error_message = msg
                fail_msg = f"✗ 下载失败: ch{channel_no} ({task.channel_name}) - {msg}"
                print(f"[JavaDownloader] {fail_msg}")
                _gui_log(fail_msg)

            self._fire_status(task)
            if self.on_completion:
                self.on_completion(task.task_id, success, task.file_path, msg)

        except Exception as e:
            task.status = DownloadStatus.FAILED
            task.error_message = str(e)
            print(f"[JavaDownloader] 异常: {e}")
            self._fire_status(task)

    def _run_task(self, sdk, task: DownloadTask):
        """执行单个下载任务"""
        # 更新状态
        task.status = DownloadStatus.DOWNLOADING
        task.progress = 0
        self._fire_status(task)

        t0 = time.time()

        def _progress(p: int):
            print(f"[Downloader] 进度回调: task_id={task.task_id}, progress={p}")
            task.progress = p
            if self.on_progress:
                try:
                    self.on_progress(task.task_id, p)
                    print(f"[Downloader] 回调已发出")
                except Exception as e:
                    print(f"[Downloader] 回调异常: {e}")

        try:
            channel_no = int(task.channel_id)
        except ValueError:
            channel_no = 1

        success, msg = sdk.download_by_time(
            channel=channel_no,
            start_time=task.start_time,
            end_time=task.end_time,
            save_path=task.file_path,
            progress_callback=_progress,
            timeout_sec=300,
        )

        elapsed = time.time() - t0

        if success:
            task.status   = DownloadStatus.COMPLETED
            task.progress = 100
            self.results[task.task_id] = DownloadResult(
                task_id=task.task_id, success=True,
                file_path=task.file_path, download_time=elapsed
            )
        else:
            task.status        = DownloadStatus.FAILED
            task.error_message = msg
            self.results[task.task_id] = DownloadResult(
                task_id=task.task_id, success=False, error_message=msg
            )

        self._fire_status(task)
        self._fire_completion(task)

    def _fire_status(self, task: DownloadTask):
        if self.on_status:
            try:
                self.on_status(task)
            except Exception:
                pass

    def _fire_completion(self, task: DownloadTask):
        if self.on_completion:
            try:
                self.on_completion(task)
            except Exception:
                pass


# ------------------------------------------------------------------ #
#  批量下载器（多通道封装）
# ------------------------------------------------------------------ #

class BatchDownloader:
    """多通道批量下载封装"""

    def __init__(self, download_manager: DownloadManager):
        self.dm = download_manager

    def create_tasks(
        self,
        device_config: Dict[str, Any],
        channels: List[Dict],
        start_time: datetime,
        end_time: datetime,
        save_dir: str,
    ) -> List[DownloadTask]:
        """
        为每个通道创建一个下载任务

        Args:
            device_config: {'host','port','username','password','name'}
            channels:      [{'id':'1','name':'...','no':1}, ...]
            start_time / end_time: 时间范围
            save_dir:      保存目录

        Returns:
            任务列表
        """
        import uuid
        device_id   = f"{device_config['host']}:{device_config.get('port',8000)}"
        device_name = device_config.get('name', device_config['host'])

        tasks = []
        for ch in channels:
            task = DownloadTask(
                task_id      = str(uuid.uuid4()),
                device_id    = device_id,
                device_name  = device_name,
                channel_id   = str(ch.get('no', ch.get('id', '1'))),
                channel_name = ch.get('name', f"通道{ch.get('id','?')}"),
                start_time   = start_time,
                end_time     = end_time,
                save_dir     = save_dir,
            )
            tasks.append(task)

        return tasks

    def submit(self, tasks: List[DownloadTask]) -> List[str]:
        """提交任务到下载队列"""
        return self.dm.add_tasks_batch(tasks)

    def get_completed_files(self) -> List[str]:
        """获取所有已完成的文件路径"""
        return [
            t.file_path
            for t in self.dm.get_all_tasks()
            if t.status == DownloadStatus.COMPLETED and os.path.exists(t.file_path)
        ]
