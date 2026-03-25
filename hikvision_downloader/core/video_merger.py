# 录像合并模块
# 使用FFmpeg将多个录像文件合并为一个文件
import os
import subprocess
from pathlib import Path
from typing import List
import re

FFMPEG_PATH = r"C:\tools\ffmpeg\bin\ffmpeg.exe"


def get_video_duration(file_path: str) -> float:
    """获取视频时长（秒）"""
    try:
        cmd = [
            FFMPEG_PATH,
            '-i', file_path,
            '-f', 'null',
            '-'
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )

        # 从stderr中提取时长
        match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', result.stderr)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = float(match.group(3))
            return hours * 3600 + minutes * 60 + seconds

        return 0.0
    except Exception as e:
        print(f"[Merger] 获取视频时长失败: {e}")
        return 0.0


def get_video_info(file_path: str) -> dict:
    """获取视频信息"""
    try:
        cmd = [
            FFMPEG_PATH,
            '-i', file_path,
            '-f', 'null',
            '-'
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )

        info = {}

        # 提取分辨率
        match = re.search(r'(\d{3,4})x(\d{3,4})', result.stderr)
        if match:
            info['width'] = int(match.group(1))
            info['height'] = int(match.group(2))

        # 提取帧率
        match = re.search(r'(\d+(?:\.\d+)?) fps', result.stderr)
        if match:
            info['fps'] = float(match.group(1))

        # 提取编码
        match = re.search(r'Video: (\w+)', result.stderr)
        if match:
            info['codec'] = match.group(1)

        # 提取时长
        duration = get_video_duration(file_path)
        if duration > 0:
            info['duration'] = duration

        return info
    except Exception as e:
        print(f"[Merger] 获取视频信息失败: {e}")
        return {}


def merge_videos(
    input_files: List[str],
    output_file: str,
    progress_callback=None
) -> bool:
    """
    合并多个视频文件

    Args:
        input_files: 输入文件列表
        output_file: 输出文件
        progress_callback: 进度回调 (current, total)

    Returns:
        是否成功
    """
    if not input_files:
        print("[Merger] 没有输入文件")
        return False

    if len(input_files) == 1:
        # 只有一个文件，直接复制
        print(f"[Merger] 只有一个文件，直接复制: {input_files[0]} -> {output_file}")
        import shutil
        shutil.copy(input_files[0], output_file)
        return True

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    print(f"[Merger] 开始合并 {len(input_files)} 个文件")

    # 创建 concat 文件列表
    concat_file = os.path.join(
        os.path.dirname(output_file),
        f"concat_{os.path.basename(output_file)}.txt"
    )

    try:
        # 写入 concat 列表文件（使用绝对路径）
        with open(concat_file, 'w', encoding='utf-8') as f:
            for input_file in input_files:
                # 转换为绝对路径并转义特殊字符
                abs_path = os.path.abspath(input_file).replace('\\', '/')
                # 修复：Windows路径格式为 file:/c:/path/file.mp4
                f.write(f"file '{abs_path}'\n")

        # 使用 FFmpeg concat 协议合并
        cmd = [
            FFMPEG_PATH,
            '-y',  # 覆盖输出文件
            '-f', 'concat',
            '-safe', '0',  # 允许使用任意路径
            '-i', concat_file,
            '-c', 'copy',  # 直接复制流，不重新编码（快速）
            output_file
        ]

        print(f"[Merger] 命令: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=7200  # 2小时超时
        )

        # 删除临时文件
        try:
            os.remove(concat_file)
        except:
            pass

        if result.returncode == 0:
            file_size = os.path.getsize(output_file)
            print(f"[Merger] 合并成功: {output_file} ({file_size / 1024 / 1024:.2f}MB)")
            return True
        else:
            print(f"[Merger] 合并失败: {result.stderr}")
            return False

    except Exception as e:
        print(f"[Merger] 合并异常: {e}")
        # 清理临时文件
        try:
            os.remove(concat_file)
        except:
            pass
        return False


def group_videos_by_duration(
    files: List[str],
    max_duration: int  # 最大时长（分钟）
) -> List[List[str]]:
    """
    按时长分组视频文件

    Args:
        files: 视频文件列表
        max_duration: 每组最大时长（分钟）

    Returns:
        分组后的文件列表 [[file1, file2], [file3, ...]]
    """
    groups = []
    current_group = []
    current_duration = 0

    for file in files:
        duration = get_video_duration(file)

        # 如果当前组为空，或者加入后不超过最大时长
        if not current_group or (current_duration + duration) <= (max_duration * 60):
            current_group.append(file)
            current_duration += duration
        else:
            # 保存当前组，开始新组
            groups.append(current_group)
            current_group = [file]
            current_duration = duration

    # 添加最后一组
    if current_group:
        groups.append(current_group)

    print(f"[Merger] 分组结果: {len(groups)} 组")
    for i, group in enumerate(groups):
        total_min = sum(get_video_duration(f) for f in group) / 60
        print(f"  组 {i+1}: {len(group)} 个文件, 总时长 {total_min:.1f} 分钟")

    return groups


def merge_channel_videos(
    channel_dir: str,
    max_duration: int = 120,  # 默认120分钟
    delete_original: bool = False
) -> List[str]:
    """
    合并单个通道的视频文件

    Args:
        channel_dir: 通道目录（包含多个视频文件）
        max_duration: 每组最大时长（分钟）
        delete_original: 是否删除原始文件

    Returns:
        合并后的文件列表
    """
    # 获取所有mp4文件并按时间排序
    files = sorted(Path(channel_dir).glob('*.mp4'))

    if not files:
        print(f"[Merger] 目录中没有视频文件: {channel_dir}")
        return []

    # 转换为字符串
    file_list = [str(f) for f in files]

    # 按时长分组
    groups = group_videos_by_duration(file_list, max_duration)

    # 合并每组
    merged_files = []
    for i, group in enumerate(groups):
        # 生成输出文件名
        base_name = os.path.basename(channel_dir)
        date_str = groups[0][0].split('_')[-3] if groups else 'unknown'
        output_file = os.path.join(
            channel_dir,
            f"{base_name}_pack{i+1}_{date_str}.mp4"
        )

        print(f"\n[Merger] 合并组 {i+1}/{len(groups)}...")
        success = merge_videos(group, output_file)

        if success and delete_original:
            # 删除原始文件
            print(f"[Merger] 删除原始文件...")
            for f in group:
                try:
                    os.remove(f)
                    print(f"  已删除: {os.path.basename(f)}")
                except Exception as e:
                    print(f"  删除失败 {os.path.basename(f)}: {e}")

        merged_files.append(output_file)

    return merged_files
