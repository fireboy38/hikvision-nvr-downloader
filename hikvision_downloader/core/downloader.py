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

# 导入转码管理器
from .transcode_manager import TranscodeManager, TranscodeTask, TranscodeStatus, get_transcode_manager


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
    
    # 下载和转码分离架构
    transcode_async: bool = True  # 是否异步转码（下载完成后立即释放槽位）
    transcode_task_id: Optional[str] = None  # 关联的转码任务ID


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
    SDK模式下载任务管理器（下载和转码分离架构）
    - 每个设备连接独立管理
    - 支持多通道顺序/并发下载
    - 线程安全
    - 每台NVR最多 max_concurrent_per_device 个并发连接（避免超出设备限制）
    - 下载和转码分离：下载完成后立即释放槽位，转码由独立线程池处理
    
    线程架构：
    - 总下载线程池：max_concurrent（默认9）
    - 每台NVR并发限制：max_concurrent_per_device（默认3）
    - 转码线程池：transcode_workers（默认2）
    """

    def __init__(self, max_concurrent: int = 9, max_concurrent_per_device: int = 3, transcode_workers: int = 2):
        """
        初始化下载管理器
        
        Args:
            max_concurrent: 总下载线程数（全局线程池大小），默认9
            max_concurrent_per_device: 每台NVR最大并发数，默认3
            transcode_workers: 转码线程数，默认2
        """
        self.max_concurrent = max_concurrent
        self.max_concurrent_per_device = max_concurrent_per_device
        
        self.tasks:   Dict[str, DownloadTask]   = {}
        self.results: Dict[str, DownloadResult] = {}
        self._queue   = queue.Queue()
        self._lock    = threading.Lock()
        self._running = False
        self._workers: List[threading.Thread] = []

        # 外部回调
        self.on_progress:   Optional[Callable[[str, int], None]]           = None
        self.on_transcode_progress: Optional[Callable[[str, int], None]]   = None  # 转码进度回调
        self.on_status:     Optional[Callable[[DownloadTask], None]]       = None
        self.on_completion: Optional[Callable[[DownloadTask], None]]       = None
        self.on_log:        Optional[Callable[[str], None]]                = None  # 日志回调

        # 设备连接配置（start()时注入）
        self._device_config: Optional[Dict[str, Any]] = None

        # 按设备的并发信号量 {device_id: Semaphore}
        # 每台NVR最多同时 max_concurrent_per_device 个下载
        self._device_semaphores: Dict[str, threading.Semaphore] = {}
        
        # 转码管理器（下载和转码分离）
        self._transcode_manager: Optional[TranscodeManager] = None
        self._transcode_workers = transcode_workers

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
        """取消单个任务（仅限等待中状态）"""
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.status == DownloadStatus.PENDING:
                task.status = DownloadStatus.CANCELLED
                return True
        return False

    def cancel_task_downloading(self, task_id: str) -> bool:
        """取消正在下载的任务（仅标记状态，实际停止由信号量/事件控制）"""
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.status == DownloadStatus.DOWNLOADING:
                task.status = DownloadStatus.CANCELLED
                return True
        return False

    def remove_task(self, task_id: str) -> bool:
        """从任务列表中删除单个任务（仅限非下载中状态）"""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            if task.status == DownloadStatus.DOWNLOADING:
                return False  # 正在下载的任务不允许直接删除，需先停止
            del self.tasks[task_id]
            return True

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

    def set_transcode_progress_callback(self, cb: Callable):
        """设置转码进度回调"""
        self.on_transcode_progress = cb

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
        self._device_config = device_config if device_config else {}
        
        if self._running:
            # 已经在运行，只需更新配置
            print(f"[DownloadManager] 下载管理器已在运行，更新配置: 总线程={self.max_concurrent}, 每设备={self.max_concurrent_per_device}")
            return
            
        self._running = True
        # 使用当前的max_concurrent值创建工作线程
        thread_count = self.max_concurrent
        print(f"[DownloadManager] 启动 {thread_count} 个下载线程...")
        for i in range(thread_count):
            w = threading.Thread(target=self._worker, name=f"DownloadWorker-{i}", daemon=True)
            w.start()
            self._workers.append(w)
        
        # 启动转码管理器（下载和转码分离）
        if self._transcode_manager is None:
            self._transcode_manager = get_transcode_manager(max_concurrent=self._transcode_workers)
            # 设置转码回调
            self._transcode_manager.on_log = self._on_transcode_log
            self._transcode_manager.on_status = self._on_transcode_status
            self._transcode_manager.on_completion = self._on_transcode_completion
            print(f"[DownloadManager] 转码管理器已启动 ({self._transcode_workers} 个转码线程)")

    def stop(self):
        self._running = False
        self.cancel_all()
        for w in self._workers:
            w.join(timeout=3)
        self._workers.clear()
        # 停止转码管理器
        if self._transcode_manager:
            # 注意：不停止全局转码管理器，让它继续处理已提交的转码任务
            # 如果需要强制停止，可以调用 stop_transcode_manager()
            pass

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
        """获取或创建设备的并发信号量（线程安全）
        
        注意：如果max_concurrent_per_device设置发生变化，会重新创建信号量
        """
        with self._lock:
            # 检查是否需要重新创建信号量（配置可能已更改）
            if device_id in self._device_semaphores:
                existing_sem = self._device_semaphores[device_id]
                # 检查信号量的初始值（通过自定义属性存储）
                initial_value = getattr(existing_sem, '_initial_value', None)
                if initial_value is not None and initial_value != self.max_concurrent_per_device:
                    print(f"[DownloadManager] 设备 {device_id} 并发限制变更: {initial_value} -> {self.max_concurrent_per_device}，重新创建信号量")
                    del self._device_semaphores[device_id]
            
            if device_id not in self._device_semaphores:
                sem = threading.Semaphore(self.max_concurrent_per_device)
                # 存储初始值以便后续检查配置变更
                sem._initial_value = self.max_concurrent_per_device
                self._device_semaphores[device_id] = sem
                print(f"[DownloadManager] 为设备 {device_id} 创建并发限制 (最多{self.max_concurrent_per_device}个并发)")
            return self._device_semaphores[device_id]

    def _run_task_hiksdk(self, task: DownloadTask):
        """使用Java下载器执行下载任务（下载和转码分离架构）"""
        from .java_downloader import download_with_java, download_only, MERGE_MODE_STANDARD

        # 先获取设备配置和信号量，再更新状态
        cfg = task.device_config if task.device_config else self._device_config
        if not cfg:
            task.status = DownloadStatus.FAILED
            self._fire_status(task)
            raise Exception("设备配置未设置")

        channel_no = int(task.channel_id) if task.channel_id.isdigit() else 1

        # 获取该设备的并发信号量，避免同一台NVR并发连接超限
        device_id = task.device_id or f"{cfg.get('host', '')}:{cfg.get('port', 8000)}"
        sem = self._get_device_semaphore(device_id)

        # 获取信号量（等待轮到自己）- 在设置DOWNLOADING状态之前
        print(f"[DownloadManager] 等待设备 {device_id} 的下载槽位 (通道{channel_no})...")
        acquired = sem.acquire(timeout=300)  # 最多等5分钟排队
        if not acquired:
            task.status = DownloadStatus.FAILED
            self._fire_status(task)
            raise Exception(f"等待设备下载槽位超时 (设备:{device_id})")

        # 获得槽位后才设置DOWNLOADING状态
        print(f"[DownloadManager] 获得下载槽位, 开始下载 {device_id} 通道{channel_no}")
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
            if self.on_log:
                try:
                    self.on_log(msg)
                except Exception as e:
                    print(f"[JavaDownloader] 日志回调异常: {e}")

        try:
            # 重试参数
            max_retries = 3
            retry_delay = 5  # 每次重试前等待5秒
            
            success = False
            msg = ""
            transcode_info = None

            for attempt in range(1, max_retries + 1):
                try:
                    
                    # 根据是否异步转码选择下载方式
                    if task.transcode_async and task.merge_mode == MERGE_MODE_STANDARD:
                        # 下载和转码分离：只下载原始文件，转码由独立线程池处理
                        print(f"[DownloadManager] 使用下载和转码分离模式 (通道{channel_no})")
                        success, msg, transcode_info = download_only(
                            ip=cfg.get('host', ''),
                            port=cfg.get('port', 8000),
                            username=cfg.get('username', 'admin'),
                            password=cfg.get('password', ''),
                            channel=channel_no,
                            start_time=task.start_time,
                            end_time=task.end_time,
                            save_dir=task.save_dir,
                            channel_name=task.channel_name,
                            progress_callback=_progress,
                            gui_log_callback=_gui_log,
                            enable_debug_log=task.enable_debug_log,
                        )
                    else:
                        # 传统模式：下载并立即转码/合并（占用槽位直到完成）
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
                            merge_mode=task.merge_mode,
                            enable_debug_log=task.enable_debug_log,
                            gui_log_callback=_gui_log,
                            skip_transcode=task.skip_transcode
                        )

                finally:
                    # 下载完成后立即释放槽位！
                    sem.release()
                    print(f"[DownloadManager] 释放设备 {device_id} 的下载槽位 (通道{channel_no})")
                    
                    # 如果是异步转码模式且下载成功，立即提交转码任务
                    if task.transcode_async and transcode_info and success:
                        self._submit_transcode_task(task, transcode_info)

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

            if success:
                if task.transcode_async and task.merge_mode == MERGE_MODE_STANDARD:
                    # 异步转码模式：下载完成，转码在后台进行
                    task.status = DownloadStatus.COMPLETED
                    task.progress = 100
                    task.error_message = ""
                    success_msg = f"✓ 下载完成(转码中): ch{channel_no} ({task.channel_name}) - {msg}, 耗时:{elapsed:.1f}秒"
                    print(f"[JavaDownloader] {success_msg}")
                    _gui_log(success_msg)
                else:
                    # 传统模式：下载和转码都已完成
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
            
    def _submit_transcode_task(self, download_task: DownloadTask, transcode_info: Dict):
        """提交转码任务到转码管理器"""
        if not self._transcode_manager:
            return
            
        # 创建转码任务
        tc_task = TranscodeTask(
            task_id=transcode_info['task_id'],
            channel=transcode_info['channel'],
            channel_name=transcode_info['channel_name'],
            device_id=transcode_info['device_id'],
            seg_files=transcode_info['seg_files'],
            seg_raw_files=transcode_info['seg_raw_files'],
            temp_dir=transcode_info['temp_dir'],
            merge_points=transcode_info['merge_points'],
            save_path=transcode_info['save_path'],
            merge_mode=download_task.merge_mode,
            skip_transcode=download_task.skip_transcode,
        )
        
        # 关联转码任务ID
        download_task.transcode_task_id = tc_task.task_id
        download_task.file_path = transcode_info['save_path']
        
        # 提交到转码队列
        self._transcode_manager.add_task(tc_task)
        print(f"[DownloadManager] 已提交转码任务: {tc_task.task_id} ({tc_task.channel_name})")
        
    def _on_transcode_log(self, msg: str):
        """转码日志回调"""
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass
                
    def _on_transcode_status(self, task: TranscodeTask):
        """转码状态回调"""
        # 转发转码进度到GUI
        if self.on_transcode_progress:
            try:
                self.on_transcode_progress(task.task_id, task.progress)
            except Exception:
                pass
        
    def _on_transcode_completion(self, task: TranscodeTask):
        """转码完成回调"""
        status_str = "完成" if task.status == TranscodeStatus.COMPLETED else "失败"
        print(f"[DownloadManager] 转码任务 {status_str}: {task.channel_name}")
        if self.on_log:
            try:
                if task.status == TranscodeStatus.COMPLETED:
                    size_mb = os.path.getsize(task.save_path) / 1024 / 1024
                    self.on_log(f"[TRANSCODE-OK] {task.channel_name} 转码完成: {size_mb:.1f}MB")
                else:
                    self.on_log(f"[TRANSCODE-FAIL] {task.channel_name} 转码失败: {task.error_message}")
            except Exception:
                pass

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
