# 视频合并模块
import os
import subprocess
import threading
from typing import List, Optional, Callable
from dataclasses import dataclass
from enum import Enum


class MergeStatus(Enum):
    """合并状态"""
    IDLE = "idle"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class MergeResult:
    """合并结果"""
    success: bool
    output_path: str = ""
    input_count: int = 0
    error_message: str = ""


class VideoMerger:
    """视频合并器 - 使用FFmpeg合并多个视频"""
    
    def __init__(self):
        self.status = MergeStatus.IDLE
        self.progress = 0
        self.current_result: Optional[MergeResult] = None
        
        # 检查FFmpeg是否可用
        self.ffmpeg_available = self._check_ffmpeg()
        
    def _check_ffmpeg(self) -> bool:
        """检查FFmpeg是否可用"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def merge_videos(self, input_files: List[str], output_path: str, 
                     progress_callback: Optional[Callable] = None) -> bool:
        """
        合并多个视频文件
        
        Args:
            input_files: 输入文件列表
            output_path: 输出文件路径
            progress_callback: 进度回调
            
        Returns:
            是否成功
        """
        if not input_files:
            self.current_result = MergeResult(
                success=False,
                error_message="没有输入文件"
            )
            return False
            
        # 检查输入文件是否存在
        for f in input_files:
            if not os.path.exists(f):
                self.current_result = MergeResult(
                    success=False,
                    error_message=f"文件不存在: {f}"
                )
                return False
        
        # 创建输出目录
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        self.status = MergeStatus.MERGING
        self.progress = 0
        
        try:
            if self.ffmpeg_available:
                # 使用FFmpeg合并
                success = self._merge_with_ffmpeg(input_files, output_path, progress_callback)
            else:
                # 使用OpenCV合并（仅当FFmpeg不可用时）
                success = self._merge_with_opencv(input_files, output_path, progress_callback)
            
            if success:
                self.status = MergeStatus.COMPLETED
                self.progress = 100
                self.current_result = MergeResult(
                    success=True,
                    output_path=output_path,
                    input_count=len(input_files)
                )
            else:
                self.status = MergeStatus.FAILED
                self.current_result = MergeResult(
                    success=False,
                    error_message="合并失败"
                )
                
            return success
            
        except Exception as e:
            self.status = MergeStatus.FAILED
            self.current_result = MergeResult(
                success=False,
                error_message=str(e)
            )
            return False
    
    def _merge_with_ffmpeg(self, input_files: List[str], output_path: str,
                          progress_callback: Optional[Callable] = None) -> bool:
        """使用FFmpeg合并视频"""
        try:
            # 创建临时文件列表
            list_file = output_path + ".txt"
            with open(list_file, 'w', encoding='utf-8') as f:
                for file in input_files:
                    # 转义特殊字符
                    escaped_path = file.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")
            
            # 使用FFmpeg concat合并
            cmd = [
                'ffmpeg',
                '-y',  # 覆盖输出文件
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c', 'copy',  # 直接复制流，不重新编码
                '-progress', 'pipe:1',  # 输出进度信息
                output_path
            ]
            
            # 执行命令
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # 读取进度
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                    
                if 'out_time_ms=' in line:
                    # 可以在这里计算进度
                    if progress_callback:
                        self.progress = min(self.progress + 1, 99)
                        progress_callback(self.progress)
            
            # 清理临时文件
            if os.path.exists(list_file):
                os.remove(list_file)
                
            return process.returncode == 0
            
        except Exception as e:
            print(f"FFmpeg合并失败: {e}")
            return False
    
    def _merge_with_opencv(self, input_files: List[str], output_path: str,
                          progress_callback: Optional[Callable] = None) -> bool:
        """使用OpenCV合并视频（需要重新编码）"""
        try:
            import cv2
            
            # 获取视频信息
            first_cap = cv2.VideoCapture(input_files[0])
            fps = first_cap.get(cv2.CAP_PROP_FPS)
            width = int(first_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(first_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            first_cap.release()
            
            # 创建输出视频
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            
            total_files = len(input_files)
            for i, file in enumerate(input_files):
                cap = cv2.VideoCapture(file)
                
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    out.write(frame)
                
                cap.release()
                
                # 更新进度
                if progress_callback:
                    progress = int((i + 1) / total_files * 100)
                    progress_callback(progress)
            
            out.release()
            return True
            
        except Exception as e:
            print(f"OpenCV合并失败: {e}")
            return False
    
    def get_video_info(self, video_path: str) -> Optional[dict]:
        """
        获取视频信息
        
        Args:
            video_path: 视频路径
            
        Returns:
            视频信息字典
        """
        if not os.path.exists(video_path):
            return None
            
        try:
            if self.ffmpeg_available:
                # 使用FFprobe获取信息
                cmd = [
                    'ffprobe',
                    '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_format',
                    '-show_streams',
                    video_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    import json
                    info = json.loads(result.stdout)
                    
                    # 提取关键信息
                    duration = float(info.get('format', {}).get('duration', 0))
                    size = int(info.get('format', {}).get('size', 0))
                    
                    video_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
                    if video_stream:
                        width = video_stream.get('width', 0)
                        height = video_stream.get('height', 0)
                        fps_str = video_stream.get('r_frame_rate', '0/1')
                        if '/' in fps_str:
                            num, den = fps_str.split('/')
                            fps = float(num) / float(den) if float(den) != 0 else 0
                        else:
                            fps = float(fps_str)
                    else:
                        width, height, fps = 0, 0, 0
                    
                    return {
                        'duration': duration,
                        'size': size,
                        'width': width,
                        'height': height,
                        'fps': fps
                    }
            else:
                # 使用OpenCV
                import cv2
                cap = cv2.VideoCapture(video_path)
                if cap.isOpened():
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    duration = frame_count / fps if fps > 0 else 0
                    cap.release()
                    
                    return {
                        'duration': duration,
                        'size': os.path.getsize(video_path),
                        'width': width,
                        'height': height,
                        'fps': fps
                    }
                    
        except Exception as e:
            print(f"获取视频信息失败: {e}")
            
        return None


class VideoSplitter:
    """视频分割器"""
    
    def __init__(self):
        self.ffmpeg_available = self._check_ffmpeg()
        
    def _check_ffmpeg(self) -> bool:
        """检查FFmpeg是否可用"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def split_video(self, input_path: str, output_dir: str, 
                   segment_duration: int = 600) -> List[str]:
        """
        分割视频
        
        Args:
            input_path: 输入路径
            output_dir: 输出目录
            segment_duration: 片段时长（秒）
            
        Returns:
            输出文件列表
        """
        if not self.ffmpeg_available:
            return []
            
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_pattern = os.path.join(output_dir, f"{base_name}_%03d.mp4")
            
            cmd = [
                'ffmpeg',
                '-y',
                '-i', input_path,
                '-c', 'copy',
                '-f', 'segment',
                '-segment_time', str(segment_duration),
                '-reset_timestamps', '1',
                output_pattern
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=3600)
            
            if result.returncode == 0:
                # 获取生成的文件
                import glob
                files = sorted(glob.glob(os.path.join(output_dir, f"{base_name}_*.mp4")))
                return files
                
        except Exception as e:
            print(f"分割视频失败: {e}")
            
        return []
