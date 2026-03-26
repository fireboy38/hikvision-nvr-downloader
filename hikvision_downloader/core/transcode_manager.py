"""
转码管理器 - 下载和转码分离架构

核心设计：
1. 下载线程池只负责下载原始文件到临时目录
2. 下载完成后立即释放下载槽位，开始下一个下载任务
3. 转码/合并任务放入独立的转码队列，由转码线程池异步处理
4. 支持查询转码进度和状态
"""

import os
import threading
import queue
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import shutil


class TranscodeStatus(Enum):
    """转码状态"""
    PENDING = "pending"         # 等待转码
    TRANSCODING = "transcoding" # 转码中
    COMPLETED = "completed"     # 完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 已取消


@dataclass
class TranscodeTask:
    """转码任务"""
    task_id: str
    channel: int
    channel_name: str
    device_id: str
    
    # 输入文件
    seg_files: List[str]              # 分段文件列表
    seg_raw_files: List[str]          # 原始文件列表（用于清理）
    temp_dir: str                     # 临时目录
    merge_points: List[Tuple[str, str]]  # 合并点信息
    
    # 输出文件
    save_path: str                    # 最终输出路径
    
    # 转码参数
    merge_mode: str = "standard"      # 合并模式
    skip_transcode: bool = True       # 是否跳过转码
    
    # 状态
    status: TranscodeStatus = TranscodeStatus.PENDING
    progress: int = 0
    error_message: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TranscodeManager:
    """
    转码管理器 - 异步处理转码/合并任务
    
    特点：
    - 独立的转码线程池，不占用下载槽位
    - 支持并发转码（默认2个并发）
    - 实时进度回调
    - 自动清理临时文件
    """
    
    def __init__(self, max_concurrent: int = 2):
        self.max_concurrent = max_concurrent
        self.tasks: Dict[str, TranscodeTask] = {}
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._running = False
        self._workers: List[threading.Thread] = []
        
        # 外部回调
        self.on_progress: Optional[Callable[[str, int], None]] = None
        self.on_status: Optional[Callable[[TranscodeTask], None]] = None
        self.on_completion: Optional[Callable[[TranscodeTask], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None
        
    def start(self):
        """启动转码管理器"""
        if self._running:
            return
        self._running = True
        print(f"[TranscodeManager] 启动 {self.max_concurrent} 个转码线程...")
        for i in range(self.max_concurrent):
            w = threading.Thread(target=self._worker, name=f"TranscodeWorker-{i}", daemon=True)
            w.start()
            self._workers.append(w)
            
    def stop(self):
        """停止转码管理器"""
        self._running = False
        # 清空队列
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break
        # 等待工作线程结束
        for w in self._workers:
            w.join(timeout=5)
        self._workers.clear()
        print("[TranscodeManager] 已停止")
        
    def add_task(self, task: TranscodeTask) -> str:
        """添加转码任务"""
        with self._lock:
            self.tasks[task.task_id] = task
            self._queue.put(task.task_id)
        self._log(f"[TranscodeQueue] 添加转码任务: {task.channel_name}, 队列长度: {self._queue.qsize()}")
        return task.task_id
        
    def get_task(self, task_id: str) -> Optional[TranscodeTask]:
        """获取任务状态"""
        return self.tasks.get(task_id)
        
    def get_all_tasks(self) -> List[TranscodeTask]:
        """获取所有任务"""
        return list(self.tasks.values())
        
    def get_pending_count(self) -> int:
        """获取等待中的任务数"""
        return self._queue.qsize()
        
    def get_transcoding_count(self) -> int:
        """获取正在转码的任务数"""
        with self._lock:
            return sum(1 for t in self.tasks.values() if t.status == TranscodeStatus.TRANSCODING)
            
    def _worker(self):
        """转码工作线程"""
        while self._running:
            try:
                task_id = self._queue.get(timeout=1)
            except queue.Empty:
                continue
                
            task = self.tasks.get(task_id)
            if not task or task.status == TranscodeStatus.CANCELLED:
                self._queue.task_done()
                continue
                
            self._run_transcode(task)
            self._queue.task_done()
            
    def _run_transcode(self, task: TranscodeTask):
        """执行转码任务"""
        from .java_downloader import (
            _ffmpeg_concat_ultra, _ffmpeg_concat_fast, _ffmpeg_concat_standard,
            MERGE_MODE_ULTRA, MERGE_MODE_FAST, MERGE_MODE_STANDARD,
            setup_download_logger, logger
        )
        
        task.status = TranscodeStatus.TRANSCODING
        task.started_at = datetime.now()
        self._fire_status(task)
        
        channel_info = f"通道{task.channel}" + (f"({task.channel_name})" if task.channel_name else "")
        self._log(f"[TRANSCODE] 开始转码 {channel_info}, 模式: {task.merge_mode}")
        
        try:
            # 设置调试日志
            save_dir = os.path.dirname(task.save_path)
            if task.merge_mode == MERGE_MODE_STANDARD:
                log_file = setup_download_logger(save_dir, f"transcode_{task.task_id}", task.channel_name)
                logger.info("=" * 80)
                logger.info(f"[转码任务] 开始 {channel_info}")
                logger.info(f"分段数: {len(task.seg_files)}")
                logger.info(f"输出: {task.save_path}")
                logger.info("=" * 80)
            
            # 验证所有分段文件都存在
            missing_files = [f for f in task.seg_files if not os.path.exists(f)]
            if missing_files:
                raise Exception(f"分段文件缺失: {len(missing_files)} 个文件不存在")
                
            # 执行合并
            if len(task.seg_files) == 1:
                # 只有一段，直接移动
                self._log(f"[TRANSCODE] {channel_info} 只有1段，直接移动")
                os.replace(task.seg_files[0], task.save_path)
                task.progress = 100
            else:
                # 多段合并
                self._log(f"[TRANSCODE] {channel_info} 开始合并 {len(task.seg_files)} 段...")
                task.progress = 30
                self._fire_status(task)
                
                # 根据模式选择合并方式
                ok_merge = False
                err_merge = ""
                
                if task.merge_mode == MERGE_MODE_ULTRA:
                    self._log(f"[ULTRA] {channel_info} 极速合并模式...")
                    ok_merge, err_merge = _ffmpeg_concat_ultra(
                        task.seg_files, task.save_path, task.merge_points
                    )
                    if not ok_merge:
                        self._log(f"[WARN] 极速模式失败，回退到快速模式...")
                        ok_merge, err_merge = _ffmpeg_concat_fast(
                            task.seg_files, task.save_path, task.merge_points
                        )
                    if not ok_merge:
                        self._log(f"[WARN] 快速模式失败，回退到标准模式...")
                        ok_merge, err_merge = _ffmpeg_concat_standard(
                            task.seg_files, task.save_path, task.merge_points
                        )
                            
                elif task.merge_mode == MERGE_MODE_FAST:
                    self._log(f"[FAST] {channel_info} 快速合并模式...")
                    ok_merge, err_merge = _ffmpeg_concat_fast(
                        task.seg_files, task.save_path, task.merge_points
                    )
                    if not ok_merge:
                        self._log(f"[WARN] 快速模式失败，回退到标准模式...")
                        ok_merge, err_merge = _ffmpeg_concat_standard(
                            task.seg_files, task.save_path, task.merge_points
                        )
                            
                else:  # MERGE_MODE_STANDARD
                    self._log(f"[STANDARD] {channel_info} 标准合并模式...")
                    ok_merge, err_merge = _ffmpeg_concat_standard(
                        task.seg_files, task.save_path, task.merge_points
                    )
                    
                if not ok_merge:
                    raise Exception(f"合并失败: {err_merge}")
                    
                task.progress = 90
                self._fire_status(task)
                
            # 清理临时文件
            self._cleanup_temp_files(task)
            task.progress = 100
            
            # 完成
            task.status = TranscodeStatus.COMPLETED
            task.completed_at = datetime.now()
            size_mb = os.path.getsize(task.save_path) / 1024 / 1024
            self._log(f"[TRANSCODE-OK] {channel_info} 转码完成: {size_mb:.1f}MB")
            
        except Exception as e:
            task.status = TranscodeStatus.FAILED
            task.error_message = str(e)
            self._log(f"[TRANSCODE-FAIL] {channel_info} 转码失败: {e}")
            
        self._fire_status(task)
        self._fire_completion(task)
        
    def _cleanup_temp_files(self, task: TranscodeTask):
        """清理临时文件"""
        try:
            if os.path.exists(task.temp_dir):
                shutil.rmtree(task.temp_dir)
                self._log(f"[CLEANUP] 已清理临时目录: {task.temp_dir}")
        except Exception as e:
            self._log(f"[WARN] 清理临时目录失败: {e}")
            
    def _log(self, msg: str):
        """输出日志"""
        print(f"[TranscodeManager] {msg}")
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass
                
    def _fire_status(self, task: TranscodeTask):
        """触发状态回调"""
        if self.on_status:
            try:
                self.on_status(task)
            except Exception:
                pass
                
    def _fire_completion(self, task: TranscodeTask):
        """触发完成回调"""
        if self.on_completion:
            try:
                self.on_completion(task)
            except Exception:
                pass


# 全局转码管理器实例（单例模式）
_transcode_manager: Optional[TranscodeManager] = None
_manager_lock = threading.Lock()


def get_transcode_manager(max_concurrent: int = 2) -> TranscodeManager:
    """获取全局转码管理器实例"""
    global _transcode_manager
    with _manager_lock:
        if _transcode_manager is None:
            _transcode_manager = TranscodeManager(max_concurrent=max_concurrent)
            _transcode_manager.start()
        return _transcode_manager


def stop_transcode_manager():
    """停止全局转码管理器"""
    global _transcode_manager
    with _manager_lock:
        if _transcode_manager:
            _transcode_manager.stop()
            _transcode_manager = None
