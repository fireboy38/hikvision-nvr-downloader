"""
海康威视NVR录像下载器

核心逻辑：
1. 使用V30接口直接下载完整录像
2. 下载完成后，检测生成了多少个分段文件
3. 如果有多个分段文件，执行合并（默认快速合并，失败则标准合并）
4. 合并完成后删除源文件
"""

import os
import subprocess
import threading
import shutil
import random
import re
from datetime import datetime
from typing import Tuple, Optional, Callable, Dict, List
import time
import logging

# 全局停止事件（用于跨线程控制Java子进程）
_stop_event = threading.Event()
_active_processes: Dict[str, subprocess.Popen] = {}
_process_lock = threading.Lock()

# Java配置
JAVA_HOME      = r"C:\Program Files\Java\jdk-12.0.2"
HCNET_SDK_PATH = r"C:\Users\Administrator\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\CH-HCNetSDKV6.1.6.45_build20210302_win64\库文件"
JAVA_BIN_DIR   = r"C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_java\bin"
JAVA_LIB_DIR   = r"C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_java\src\main\resources\lib"
MAIN_CLASS     = "com.hikvision.HikvisionDownloaderCLI"
FFMPEG_PATH    = r"C:\tools\ffmpeg\bin\ffmpeg.exe"

# 合并模式常量
MERGE_MODE_ULTRA = "ultra"      # 极速合并（faststart）
MERGE_MODE_FAST = "fast"        # 快速合并（不转码）
MERGE_MODE_STANDARD = "standard" # 标准合并（转码后合并）

# 配置日志
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  停止控制
# ─────────────────────────────────────────────────────────────────────────────

def stop_all_downloads():
    """停止所有正在运行的Java下载进程"""
    global _stop_event
    _stop_event.set()

    with _process_lock:
        for task_id, proc in list(_active_processes.items()):
            try:
                proc.terminate()
                time.sleep(0.5)
                if proc.poll() is None:
                    proc.kill()
                print(f"[JavaDownloader] 已终止进程: {task_id}")
            except Exception as e:
                print(f"[JavaDownloader] 终止进程失败: {task_id}, {e}")
        _active_processes.clear()

    print("[JavaDownloader] 所有下载已停止")


def reset_stop_event():
    """重置停止事件（用于开始新的下载任务前）"""
    global _stop_event
    _stop_event = threading.Event()
    print("[JavaDownloader] 停止事件已重置")


def is_stopped() -> bool:
    """检查是否收到停止信号"""
    return _stop_event.is_set()


# ─────────────────────────────────────────────────────────────────────────────
#  FFmpeg 合并函数
# ─────────────────────────────────────────────────────────────────────────────

def _ffmpeg_concat_ultra(segments: List[str], output: str, merge_points: List[Tuple[str, str]]) -> Tuple[bool, str]:
    """
    极速合并模式：直接concat复制，faststart（最快）。
    """
    logger.info(f"[合并] 极速模式: {len(segments)} 个分段直接合并")
    concat_list = output + ".concat_list.txt"
    temp_output = output.replace('.mp4', '_tmp.mp4')

    try:
        with open(concat_list, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                abs_path = os.path.abspath(seg).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")

        # 方式1：concat demuxer（最快）
        cmd1 = [
            FFMPEG_PATH, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            "-movflags", "+faststart",
            temp_output,
        ]
        r1 = subprocess.run(cmd1, capture_output=True, text=True,
                          encoding='utf-8', errors='ignore', timeout=1800)
        if r1.returncode == 0 and os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
            os.replace(temp_output, output)
            logger.info(f"[合并] 极速模式成功!")
            return True, ""

        logger.warning(f"[合并] 方式1失败，尝试方式2...")

        # 方式2：concat filter
        if os.path.exists(temp_output):
            os.remove(temp_output)

        cmd2 = [
            FFMPEG_PATH, "-y",
            "-i", f"concat:{'|'.join(segments)}",
            "-c", "copy",
            "-movflags", "+faststart",
            temp_output,
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True,
                          encoding='utf-8', errors='ignore', timeout=1800)
        if r2.returncode == 0 and os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
            os.replace(temp_output, output)
            logger.info(f"[合并] 方式2成功!")
            return True, ""

        logger.warning(f"[合并] 方式2也失败")
        return False, r2.stderr[-500:] if r2.stderr else "concat filter failed"

    except subprocess.TimeoutExpired:
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return False, "合并超时"
    except Exception as e:
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return False, str(e)
    finally:
        if os.path.exists(concat_list):
            os.remove(concat_list)


def _ffmpeg_concat_fast(segments: List[str], output: str, merge_points: List[Tuple[str, str]]) -> Tuple[bool, str]:
    """
    快速合并模式：使用 concat demuxer + files.txt，直接 copy 不转码。
    注意：MPEG/PS格式视频可能不支持此方式合并。
    """
    logger.info(f"[合并] 快速模式: {len(segments)} 个分段，使用 concat demuxer 直接合并")
    concat_list = output + ".files.txt"
    temp_output = output.replace('.mp4', '_tmp.mp4')

    try:
        # 创建 files.txt
        with open(concat_list, "w", encoding="utf-8") as f:
            for seg in segments:
                abs_path = os.path.abspath(seg).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")
        logger.info(f"[合并] 已创建文件列表: {concat_list}")

        # 显示files.txt内容
        with open(concat_list, "r", encoding="utf-8") as f:
            logger.info(f"[合并] files.txt内容:\n{f.read()}")

        # 执行合并: ffmpeg -f concat -i files.txt -c copy output.mp4
        cmd = [
            FFMPEG_PATH, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            temp_output,
        ]
        logger.info(f"[合并] 执行命令: {' '.join(cmd)}")
        r = subprocess.run(cmd, capture_output=True, text=True,
                          encoding='utf-8', errors='ignore', timeout=1800)

        logger.info(f"[合并] FFmpeg stdout: {r.stdout[:1000] if r.stdout else '(empty)'}")
        logger.info(f"[合并] FFmpeg stderr: {r.stderr[:1000] if r.stderr else '(empty)'}")

        if r.returncode == 0 and os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
            actual_size = os.path.getsize(temp_output)
            expected_size = sum(os.path.getsize(s) for s in segments)
            logger.info(f"[合并] 合并后文件大小: {actual_size/1024/1024:.1f}MB, 源文件总大小: {expected_size/1024/1024:.1f}MB")
            
            # 检查文件大小是否合理（误差在10%以内视为成功）
            if actual_size >= expected_size * 0.9:
                os.replace(temp_output, output)
                logger.info(f"[合并] 快速合并成功!")
                return True, ""
            else:
                logger.error(f"[合并] 文件大小异常: 期望 ~{expected_size/1024/1024:.1f}MB, 实际 {actual_size/1024/1024:.1f}MB")
                # 清理临时文件，让后续用标准合并处理
                os.remove(temp_output)
                return False, "文件大小异常"

        logger.error(f"[合并] 快速合并失败: {r.stderr[-500:] if r.stderr else 'unknown error'}")
        return False, r.stderr[-500:] if r.stderr else "快速合并失败"

    except subprocess.TimeoutExpired:
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return False, "合并超时"
    except Exception as e:
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return False, str(e)
    finally:
        if os.path.exists(concat_list):
            os.remove(concat_list)


def _ffmpeg_concat_standard(segments: List[str], output: str, merge_points: List[Tuple[str, str]]) -> Tuple[bool, str]:
    """
    标准模式：转码后合并（兼容性最好）。
    """
    logger.info(f"[合并] 标准模式: {len(segments)} 个分段，转码后合并")
    concat_list = output + ".concat_list.txt"
    temp_output = output.replace('.mp4', '_tmp.mp4')

    try:
        with open(concat_list, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                abs_path = os.path.abspath(seg).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")
                logger.debug(f"[合并列表] 分段{i}: {os.path.basename(seg)} ({merge_points[i-1][1]})")

        # 方式1：concat demuxer + 音频转AAC
        logger.info(f"[合并] 尝试方式1: concat demuxer + 音频转AAC")
        start_time = time.time()

        cmd1 = [
            FFMPEG_PATH, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            temp_output,
        ]
        r1 = subprocess.run(cmd1, capture_output=True, text=True,
                          encoding='utf-8', errors='ignore', timeout=1800)
        elapsed = time.time() - start_time

        if r1.returncode == 0 and os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
            size_mb = os.path.getsize(temp_output) / 1024 / 1024
            logger.info(f"[合并] 方式1成功! 耗时: {elapsed:.1f}秒 大小: {size_mb:.1f}MB")
            os.replace(temp_output, output)
            return True, ""

        logger.warning(f"[合并] 方式1失败，尝试方式2（无音频）...")

        # 方式2：丢弃音频
        if os.path.exists(temp_output):
            os.remove(temp_output)

        logger.info(f"[合并] 尝试方式2: concat demuxer + 丢弃音频")
        start_time = time.time()

        cmd2 = [
            FFMPEG_PATH, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "copy", "-an",
            "-movflags", "+faststart",
            temp_output,
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True,
                          encoding='utf-8', errors='ignore', timeout=1800)
        elapsed = time.time() - start_time

        if r2.returncode == 0 and os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
            size_mb = os.path.getsize(temp_output) / 1024 / 1024
            logger.info(f"[合并] 方式2成功! 耗时: {elapsed:.1f}秒 大小: {size_mb:.1f}MB")
            os.replace(temp_output, output)
            return True, ""

        logger.warning(f"[合并] 方式2也失败，尝试方式3...")
        if os.path.exists(temp_output):
            os.remove(temp_output)

        # 方式3：concat filter + 完全转码
        logger.info(f"[合并] 尝试方式3: concat filter + 完全转码")
        start_time = time.time()

        cmd3 = [
            FFMPEG_PATH, "-y",
            "-i", f"concat:{'|'.join(segments)}",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            temp_output,
        ]
        r3 = subprocess.run(cmd3, capture_output=True, text=True,
                          encoding='utf-8', errors='ignore', timeout=3600)
        elapsed = time.time() - start_time

        if r3.returncode == 0 and os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
            size_mb = os.path.getsize(temp_output) / 1024 / 1024
            logger.info(f"[合并] 方式3成功! 耗时: {elapsed:.1f}秒 大小: {size_mb:.1f}MB")
            os.replace(temp_output, output)
            return True, ""

        logger.error(f"[合并] 所有方式都失败")
        error_msg = r3.stderr[-500:] if r3.stderr else "标准合并失败"
        return False, error_msg

    except subprocess.TimeoutExpired:
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return False, "合并超时"
    except Exception as e:
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return False, str(e)
    finally:
        if os.path.exists(concat_list):
            os.remove(concat_list)


# ─────────────────────────────────────────────────────────────────────────────
#  检测分段文件
# ─────────────────────────────────────────────────────────────────────────────

def _find_segment_files(save_dir: str, channel: int, task_id: str) -> List[str]:
    """
    检测下载目录中的分段文件。

    SDK下载时会在临时目录中生成文件，可能的命名格式：
    - dl_ch{channel}_{timestamp}.mp4（新版下载文件）
    - dl_ch{channel}_{timestamp}_1.mp4 等（SDK分包）
    - temp_*{channel}*.mp4（旧版下载文件）

    返回按时间排序的分段文件列表。
    """
    if not os.path.exists(save_dir):
        return []

    files = []
    dl_pattern = f"dl_ch{channel}_"

    # 匹配新版 dl_ch{channel}_*.mp4 格式
    for f in os.listdir(save_dir):
        if not f.endswith('.mp4'):
            continue
        if f.startswith(dl_pattern):
            full_path = os.path.join(save_dir, f)
            if os.path.getsize(full_path) > 0:
                files.append(full_path)
                logger.debug(f"[分段检测] 发现dl文件: {f}")

    # 匹配旧版 temp_*_ch{channel}*.mp4 格式
    for f in os.listdir(save_dir):
        if not f.endswith('.mp4'):
            continue
        if f.startswith('temp_') and f"_ch{channel}" in f:
            full_path = os.path.join(save_dir, f)
            if os.path.getsize(full_path) > 0 and full_path not in files:
                files.append(full_path)
                logger.debug(f"[分段检测] 发现temp文件: {f}")

    # 按修改时间排序
    files.sort(key=lambda x: os.path.getmtime(x))
    logger.info(f"[分段检测] 共发现 {len(files)} 个文件")
    return files


# ─────────────────────────────────────────────────────────────────────────────
#  核心下载函数
# ─────────────────────────────────────────────────────────────────────────────

def download_and_merge(
    ip: str,
    port: int,
    username: str,
    password: str,
    channel: int,
    start_time: datetime,
    end_time: datetime,
    save_dir: str,
    channel_name: str = "",
    task_id: str = "",
    progress_callback: Optional[Callable[[int], None]] = None,
    gui_log_callback: Optional[Callable[[str], None]] = None,
    merge_mode: str = MERGE_MODE_FAST,
    skip_transcode: bool = True,
) -> Tuple[bool, str, str]:
    """
    下载完整录像，然后检测并合并分段文件。

    参数：
        merge_mode: 合并模式，默认快速合并（fast）
        skip_transcode: 是否跳过转码

    返回 (success, message, final_path)
    """
    os.makedirs(save_dir, exist_ok=True)

    # 生成目标文件路径（使用通道名称作为前缀，保持默认命名）
    safe_name = channel_name.replace("/", "_").replace("\\", "_")[:50] if channel_name else f"ch{channel}"
    save_path = os.path.join(save_dir, f"{safe_name}_{start_time.strftime('%Y%m%d_%H%M%S')}_{end_time.strftime('%H%M%S')}.mp4")

    # 生成唯一的下载批次号，用于隔离不同下载任务的临时文件
    download_batch = f"dl_{int(time.time() * 1000)}"

    # GUI日志辅助函数
    def gui_log(msg: str):
        if gui_log_callback:
            gui_log_callback(msg)
        print(f"[JavaDownloader] {msg}")

    duration_sec = int((end_time - start_time).total_seconds())
    gui_log(f"开始下载 ch{channel} ({channel_name})  {start_time} ~ {end_time}")
    gui_log(f"时长: {duration_sec/60:.1f} 分钟  目标: {save_path}")
    mode_text = {'ultra': '极速(faststart)', 'fast': '快速(不转码)', 'standard': '标准(转码)'}.get(merge_mode, '快速')
    gui_log(f"合并模式: {mode_text}")

    # 下载前记录本通道相关的已有文件
    # 新命名格式: dl_ch{channel}_{timestamp}.mp4 (timestamp确保唯一性)
    # SDK分包可能产生: dl_ch{channel}_{timestamp}_1.mp4, dl_ch{channel}_{timestamp}_2.mp4 等
    existing_channel_files = set()
    dl_pattern = f"dl_ch{channel}_"
    if os.path.exists(save_dir):
        for f in os.listdir(save_dir):
            if not f.endswith('.mp4'):
                continue
            # 匹配 dl_ch{channel}_*.mp4 格式（新命名）
            if f.startswith(dl_pattern) and f.endswith(".mp4"):
                existing_channel_files.add(f)
            # 也兼容旧版 temp_*_ch{channel}*.mp4 格式
            elif f.startswith('temp_') and f"_ch{channel}" in f:
                existing_channel_files.add(f)

    gui_log(f"[下载] 下载前本通道已有文件: {existing_channel_files}")

    # 调用Java下载
    ok, msg = _run_java_download(
        ip, port, username, password, channel,
        start_time, end_time, save_path, channel_name,
        progress_callback=progress_callback,
        gui_log_callback=gui_log_callback,
    )

    if not ok:
        logger.error(f"[下载] 失败: {msg}")
        return False, msg, ""

    # 检测本次下载产生的文件
    # 策略：检测所有 dl_ch{channel}_{timestamp}*.mp4 文件（新命名）或 temp_*{channel}*.mp4（旧命名）
    new_files = []
    if os.path.exists(save_dir):
        for f in os.listdir(save_dir):
            if not f.endswith('.mp4'):
                continue
            full_path = os.path.join(save_dir, f)
            if os.path.getsize(full_path) <= 0:
                continue
            # 检测 dl_ch{channel}_*.mp4 格式（新命名，包含timestamp）
            if f.startswith(dl_pattern) and f.endswith(".mp4"):
                if f not in existing_channel_files:
                    new_files.append(full_path)
                    gui_log(f"[分段检测] 发现新文件: {f}")
            # 也检测 temp_*_ch{channel}*.mp4 格式（旧版Java代码）
            elif f.startswith('temp_') and f"_ch{channel}" in f:
                if f not in existing_channel_files:
                    new_files.append(full_path)
                    gui_log(f"[分段检测] 发现新temp文件: {f}")

    # 按修改时间排序
    new_files.sort(key=lambda x: os.path.getmtime(x))
    logger.info(f"[下载] 检测到 {len(new_files)} 个本任务文件: {[os.path.basename(f) for f in new_files]}")

    # 如果只有1个文件，直接重命名为目标路径
    if len(new_files) == 1:
        src_file = new_files[0]
        if src_file != save_path:
            if os.path.exists(save_path):
                os.remove(save_path)
            os.rename(src_file, save_path)
        size_mb = os.path.getsize(save_path) / 1024 / 1024
        gui_log(f"[OK] 下载完成（单文件）: {size_mb:.1f}MB")
        return True, f"下载成功, 大小: {size_mb:.1f}MB", save_path

    # 多个文件，需要合并
    if len(new_files) >= 2:
        gui_log(f"[合并] 检测到 {len(new_files)} 个分段文件，开始合并...")
        for i, f in enumerate(new_files):
            gui_log(f"[合并] 分段{i+1}: {os.path.basename(f)} ({os.path.getsize(f)/1024/1024:.1f}MB)")

        # 合并点信息（简化处理，按文件顺序）
        merge_points = [(f, f"part_{i+1}") for i, f in enumerate(new_files)]

        # 临时输出文件（先写入临时文件）
        temp_output = save_path.replace('.mp4', '_merged.mp4')
        if os.path.exists(temp_output):
            os.remove(temp_output)

        # 计算源文件总大小
        total_size = sum(os.path.getsize(f) for f in new_files)
        gui_log(f"[合并] 源文件总大小: {total_size/1024/1024:.1f}MB")

        # 先尝试快速合并（不转码，直接concat）
        gui_log(f"[合并] 步骤1/3: 执行快速合并（concat demuxer）...")
        ok_merge, err_merge = _ffmpeg_concat_fast(new_files, temp_output, merge_points)

        if ok_merge:
            gui_log(f"[合并] 步骤2/3: 快速合并成功，将临时文件改名为最终文件...")
            # 合并成功，现在改名为最终文件名
            if os.path.exists(save_path):
                os.remove(save_path)
            os.rename(temp_output, save_path)
            gui_log(f"[合并] 步骤3/3: 删除源分段文件...")
            # 合并成功，删除源文件
            for sf in new_files:
                if os.path.exists(sf) and sf != save_path and sf != temp_output:
                    try:
                        os.remove(sf)
                        gui_log(f"[合并] 已删除: {os.path.basename(sf)}")
                    except Exception as e:
                        logger.warning(f"[清理] 删除源文件失败: {sf}, 错误: {e}")

            size_mb = os.path.getsize(save_path) / 1024 / 1024
            gui_log(f"[OK] 合并完成: {size_mb:.1f}MB")
            return True, f"下载并合并成功, 大小: {size_mb:.1f}MB", save_path

        # 快速合并失败，尝试标准合并（转码后合并）
        gui_log(f"[合并] 快速合并失败({err_merge})，尝试标准合并（转码合并）...")
        gui_log(f"[合并] 步骤1/3: 执行标准合并（转码后concat）...")
        ok_merge, err_merge = _ffmpeg_concat_standard(new_files, temp_output, merge_points)

        if ok_merge:
            gui_log(f"[合并] 步骤2/3: 标准合并成功，将临时文件改名为最终文件...")
            # 合并成功，现在改名为最终文件名
            if os.path.exists(save_path):
                os.remove(save_path)
            os.rename(temp_output, save_path)
            gui_log(f"[合并] 步骤3/3: 删除源分段文件...")
            # 合并成功，删除源文件
            for sf in new_files:
                if os.path.exists(sf) and sf != save_path and sf != temp_output:
                    try:
                        os.remove(sf)
                        gui_log(f"[合并] 已删除: {os.path.basename(sf)}")
                    except Exception as e:
                        logger.warning(f"[清理] 删除源文件失败: {sf}, 错误: {e}")

            size_mb = os.path.getsize(save_path) / 1024 / 1024
            gui_log(f"[OK] 合并完成: {size_mb:.1f}MB")
            return True, f"下载并合并成功, 大小: {size_mb:.1f}MB", save_path

        # 标准合并也失败
        gui_log(f"[FAIL] 合并失败: {err_merge}")
        logger.error(f"[合并] 合并失败: {err_merge}")
        return False, f"下载成功但合并失败: {err_merge}", save_path

    # 没有检测到新文件
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        size_mb = os.path.getsize(save_path) / 1024 / 1024
        gui_log(f"[OK] 下载完成: {size_mb:.1f}MB")
        return True, f"下载成功, 大小: {size_mb:.1f}MB", save_path

    return False, "下载失败: 未找到生成的文件", ""


def download_with_java(
    ip: str,
    port: int,
    username: str,
    password: str,
    channel: int,
    start_time: datetime,
    end_time: datetime,
    save_path: str,
    channel_name: str = "",
    progress_callback: Optional[Callable[[int], None]] = None,
    timeout: Optional[int] = None,
    skip_transcode: bool = True,
    gui_log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """
    直接下载录像，不进行分段检测和合并。

    参数：
        skip_transcode: 是否跳过转码（默认跳过，原始文件可直接播放）

    返回 (success, message)
    """
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)

    def gui_log(msg: str):
        if gui_log_callback:
            gui_log_callback(msg)
        print(f"[JavaDownloader] {msg}")

    duration_sec = int((end_time - start_time).total_seconds())
    gui_log(f"开始下载 ch{channel} ({channel_name})  {start_time} ~ {end_time}")
    gui_log(f"时长: {duration_sec/60:.1f} 分钟  目标: {save_path}")

    # 调用Java下载
    ok, msg = _run_java_download(
        ip, port, username, password, channel,
        start_time, end_time, save_path, channel_name,
        progress_callback=progress_callback,
        gui_log_callback=gui_log_callback,
    )

    if not ok:
        logger.error(f"[下载] 失败: {msg}")
        return False, msg

    # 检查文件
    if not os.path.exists(save_path) or os.path.getsize(save_path) <= 0:
        return False, f"下载失败: 文件不存在"

    size_mb = os.path.getsize(save_path) / 1024 / 1024

    if skip_transcode:
        logger.info(f"[完成] 跳过转码，使用原始文件: {size_mb:.1f}MB")
        gui_log(f"[OK] 完成: {size_mb:.1f}MB (原始格式)")
        return True, f"下载成功, 大小: {size_mb:.1f}MB"
    else:
        # FFmpeg 转换为标准 MP4
        logger.info(f"[转码] 开始转换为标准MP4...")
        gui_log(f"[CONV] 转换为标准MP4...")
        conv_path = save_path.replace(".mp4", "_conv.mp4")
        ok2, err = _ffmpeg_to_mp4(save_path, conv_path)

        if ok2:
            os.remove(save_path)
            os.rename(conv_path, save_path)
            size_mb = os.path.getsize(save_path) / 1024 / 1024
            logger.info(f"[完成] 成功: {size_mb:.1f}MB")
            gui_log(f"[OK] 完成: {size_mb:.1f}MB (标准MP4)")
            return True, f"下载成功, 大小: {size_mb:.1f}MB"
        else:
            logger.warning(f"[完成] 转换失败，保留原始文件: {err}")
            gui_log(f"[WARN] 转换失败，保留原始文件: {err}")
            return True, f"下载成功(MPEG格式): {size_mb:.1f}MB"


def _run_java_download(
    ip: str, port: int, username: str, password: str,
    channel: int,
    start_time: datetime, end_time: datetime,
    save_path: str,
    channel_name: str = "",
    progress_callback: Optional[Callable[[int], None]] = None,
    gui_log_callback: Optional[Callable[[str], None]] = None,
    max_retries: int = 2,
) -> Tuple[bool, str]:
    """调用 Java CLI 下载录像，支持重试。"""
    def gui_log(msg: str):
        if gui_log_callback:
            gui_log_callback(msg)
        print(f"[JavaDownloader] {msg}")

    for attempt in range(max_retries):
        if attempt > 0:
            gui_log(f"[RETRY] 第 {attempt + 1} 次重试下载...")
            time.sleep(2)

        ok, msg = _run_java_download_once(
            ip, port, username, password, channel,
            start_time, end_time, save_path, channel_name,
            progress_callback, gui_log
        )

        if ok:
            return True, msg

        if attempt < max_retries - 1:
            gui_log(f"[WARN] 下载失败，准备重试: {msg}")
        else:
            gui_log(f"[FAIL] 重试 {max_retries} 次后仍失败")

    return False, f"下载失败（重试{max_retries}次）: {msg}"


def _run_java_download_once(
    ip: str, port: int, username: str, password: str,
    channel: int,
    start_time: datetime, end_time: datetime,
    save_path: str,
    channel_name: str = "",
    progress_callback: Optional[Callable[[int], None]] = None,
    gui_log=None,
) -> Tuple[bool, str]:
    """单次调用 Java CLI 下载录像。"""
    java_exe = os.path.join(JAVA_HOME, "bin", "java.exe")

    duration_sec = (end_time - start_time).total_seconds()
    timeout = max(int(duration_sec * 3), 600)
    timeout = min(timeout, 6 * 3600)

    args = [
        java_exe,
        f"-Djava.library.path={HCNET_SDK_PATH}",
        "-Dfile.encoding=UTF-8",
        "-Dsun.jnu.encoding=UTF-8",
        "-cp",
        f"{JAVA_LIB_DIR}\\jna.jar;{JAVA_LIB_DIR}\\examples.jar;{JAVA_BIN_DIR}",
        MAIN_CLASS,
        ip,
        str(port),
        username,
        password,
        str(channel),
        start_time.strftime("%Y-%m-%d %H:%M:%S"),
        end_time.strftime("%Y-%m-%d %H:%M:%S"),
        save_path,
        channel_name,
    ]

    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        start_ts = time.time()
        last_prog = -1

        while True:
            if _stop_event.is_set():
                process.terminate()
                time.sleep(1)
                if process.poll() is None:
                    process.kill()
                return False, "下载已取消"

            line = process.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line:
                if gui_log:
                    gui_log(f"[Java] {line}")
                else:
                    print(f"[Java] {line}")

            if "Progress:" in line and "%" in line:
                try:
                    pct = int(line.split("Progress:")[1].split("%")[0].strip())
                    if 0 <= pct <= 100 and pct != last_prog:
                        if progress_callback:
                            progress_callback(pct)
                        last_prog = pct
                except Exception:
                    pass

            if "[OK] Download complete!" in line or "Download complete" in line:
                break
            if "[FAIL]" in line:
                break
            if process.poll() is not None:
                break
            if time.time() - start_ts > timeout:
                process.terminate()
                time.sleep(1)
                if process.poll() is None:
                    process.kill()
                return False, f"下载超时 ({timeout}s)"

        exit_code = process.wait(timeout=30)

        # Java现在不rename了，临时文件保留为 dl_ch{channel}_{timestamp}.mp4
        # Python的 download_and_merge 会统一处理检测、合并、改名
        # 所以这里只需要确认Java进程正常退出即可
        if exit_code == 0:
            return True, "Java下载完成"
        
        return False, f"Java进程异常退出, exit_code={exit_code}"

    except subprocess.TimeoutExpired:
        process.kill()
        return False, "下载超时"
    except Exception as e:
        return False, f"下载异常: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  FFmpeg 转码
# ─────────────────────────────────────────────────────────────────────────────

def _ffmpeg_to_mp4(src: str, dst: str) -> Tuple[bool, str]:
    """
    将 SDK 输出的 MPEG/PS 格式文件转为标准 MP4 容器。
    """
    logger.debug(f"[转码] 开始转换: {os.path.basename(src)} -> {os.path.basename(dst)}")

    try:
        # 先探测文件信息（看是否有音频流）
        probe = subprocess.run(
            [FFMPEG_PATH, "-y", "-i", src,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", dst],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=600
        )
        if probe.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
            logger.debug(f"[转码] 成功: {os.path.basename(dst)}")
            return True, ""

        # 如果上面失败，尝试丢弃音频（监控录像通常不需要音频）
        probe2 = subprocess.run(
            [FFMPEG_PATH, "-y", "-i", src,
             "-c:v", "copy", "-an",
             "-movflags", "+faststart", dst],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=600
        )
        if probe2.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
            logger.debug(f"[转码] 成功(无音频): {os.path.basename(dst)}")
            return True, ""

        error_msg = probe2.stderr[-500:] if probe2.stderr else "unknown ffmpeg error"
        logger.error(f"[转码] 失败: {error_msg}")
        return False, error_msg
    except Exception as e:
        logger.error(f"[转码] 异常: {e}")
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
#  测试入口
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 简单测试
    from datetime import timedelta
    now = datetime.now().replace(second=0, microsecond=0)
    start = now - timedelta(minutes=30)
    end = now - timedelta(minutes=5)

    print(f"测试下载: {start} ~ {end}")

    ok, msg = download_with_java(
        ip="10.26.223.253",
        port=8000,
        username="admin",
        password="a1111111",
        channel=1,
        start_time=start,
        end_time=end,
        save_path=r"C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_downloader\downloads\test_download.mp4",
        channel_name="测试通道",
        progress_callback=lambda p: print(f"  进度: {p}%"),
    )

    print(f"\n结果: ok={ok}  msg={msg}")