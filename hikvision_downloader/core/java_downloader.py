"""
海康威视NVR录像下载器

核心逻辑：
1. 使用临时文件名下载（避免中文编码问题）
2. 自动检测录像时长：>40分钟则分段下载（规避 SDK 1GB 文件限制）
3. 分段下载完成后用 FFmpeg concat 合并为单个文件
4. 支持两种合并模式：
   - 快速模式：不转码，直接concat（最快，但需要所有段格式一致）
   - 标准模式：转码后合并（兼容性最好）
5. 分段文件存放在临时目录，合并完成后自动清理
6. 详细的调试日志：记录每段的信息、合并点位置等
7. 用户只看到最终的完整文件（干净、无中间文件）
"""

import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from typing import Tuple, Optional, Callable, List
import time
import math
import logging

# Java配置
JAVA_HOME     = r"C:\Program Files\Java\jdk-12.0.2"
HCNET_SDK_PATH = r"C:\Users\Administrator\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\CH-HCNetSDKV6.1.6.45_build20210302_win64\库文件"
JAVA_BIN_DIR  = r"C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_java\bin"
JAVA_LIB_DIR  = r"C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_java\src\main\resources\lib"
MAIN_CLASS    = "com.hikvision.HikvisionDownloaderCLI"
FFMPEG_PATH   = r"C:\tools\ffmpeg\bin\ffmpeg.exe"

# SDK 单文件大小限制阈值（秒）
# SDK V30 接口限制约 1GB；按 4Mbps 主码流估算约 34分钟 ≈ 2040秒；
# 为安全起见每段限制为 40分钟 = 2400秒
SEGMENT_MAX_SECONDS = 40 * 60   # 每段最大时长（秒）

# 合并模式
MERGE_MODE_FAST = "fast"     # 快速模式：不转码，直接concat
MERGE_MODE_STANDARD = "standard"  # 标准模式：转码后合并

# 配置日志
logger = logging.getLogger(__name__)

def setup_download_logger(log_dir: str, task_id: str):
    """
    设置下载调试日志

    记录内容包括：
    - 每个分段的时间范围
    - 每个分段的大小和时长
    - FFmpeg合并命令和输出
    - 合并点时间戳信息
    """
    log_file = os.path.join(log_dir, f"download_debug_{task_id}.log")
    
    # 配置日志格式
    logger.setLevel(logging.DEBUG)
    
    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # 格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    # 清除现有处理器，添加新处理器
    logger.handlers.clear()
    logger.addHandler(file_handler)
    
    return log_file


# ─────────────────────────────────────────────────────────────────────────────
#  内部：调用 Java 下载单段
# ─────────────────────────────────────────────────────────────────────────────

def _run_java_segment(
    ip: str, port: int, username: str, password: str,
    channel: int,
    start_time: datetime, end_time: datetime,
    save_path: str,
    channel_name: str = "",
    progress_callback: Optional[Callable[[int], None]] = None,
    gui_log_callback: Optional[Callable[[str], None]] = None,
    max_retries: int = 2,  # 最大重试次数（首次+重试）
) -> Tuple[bool, str]:
    """
    调用 Java CLI 下载一个时间段的录像。

    返回 (success, message)。
    """
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)

    # GUI日志辅助函数
    def gui_log(msg: str):
        """输出到GUI日志框"""
        if gui_log_callback:
            try:
                gui_log_callback(msg)
            except Exception as e:
                print(f"[JavaDownloader] 日志回调异常: {e}")
        print(f"[JavaDownloader] {msg}")
    
    # 调试：检查gui_log_callback是否为None
    if gui_log_callback is None:
        print(f"[JavaDownloader DEBUG] gui_log_callback is None!")

    # 重试循环
    for attempt in range(max_retries):
        if attempt > 0:
            gui_log(f"[RETRY] 第 {attempt + 1} 次重试下载...")
            time.sleep(2)  # 重试前等待2秒

        ok, msg = _run_java_segment_once(
            ip, port, username, password, channel,
            start_time, end_time, save_path, channel_name,
            progress_callback, gui_log, gui_log_callback
        )

        if ok:
            return True, msg

        # 检查是否需要重试
        if attempt < max_retries - 1:
            gui_log(f"[WARN] 下载失败，准备重试: {msg}")
        else:
            gui_log(f"[FAIL] 重试 {max_retries} 次后仍失败")

    return False, f"下载失败（重试{max_retries}次）: {msg}"


def _run_java_segment_once(
    ip: str, port: int, username: str, password: str,
    channel: int,
    start_time: datetime, end_time: datetime,
    save_path: str,
    channel_name: str = "",
    progress_callback: Optional[Callable[[int], None]] = None,
    gui_log = None,
    gui_log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """
    单次调用 Java CLI 下载一个时间段的录像（内部函数，被 _run_java_segment 调用）。

    返回 (success, message)。
    """


    java_exe = os.path.join(JAVA_HOME, "bin", "java.exe")

    duration_sec = (end_time - start_time).total_seconds()
    # 超时 = max(录像时长 × 3, 10分钟)，最长6小时
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

        start_ts   = time.time()
        last_prog  = -1

        while True:
            line = process.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line:
                # 只通过gui_log输出，避免重复
                # gui_log内部会处理print和callback
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


        process.wait(timeout=30)

        # 检查文件
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            size_mb = os.path.getsize(save_path) / 1024 / 1024
            return True, f"成功, {size_mb:.1f}MB"
        else:
            # 查找可能的临时文件
            dl = os.path.dirname(save_path)
            temps = [f for f in os.listdir(dl) if f.startswith("temp_") and f.endswith(".mp4")]
            if temps:
                tp = os.path.join(dl, sorted(temps)[-1])
                if os.path.getsize(tp) > 0:
                    os.rename(tp, save_path)
                    size_mb = os.path.getsize(save_path) / 1024 / 1024
                    return True, f"成功(临时文件), {size_mb:.1f}MB"
            return False, f"下载失败: 文件不存在 {save_path}"

    except subprocess.TimeoutExpired:
        process.kill()
        return False, "下载超时"
    except Exception as e:
        return False, f"下载异常: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  内部：FFmpeg 转换单个 MPEG/PS 文件为 MP4
# ─────────────────────────────────────────────────────────────────────────────

def _ffmpeg_to_mp4(src: str, dst: str) -> Tuple[bool, str]:
    """
    将 SDK 输出的 MPEG/PS 格式文件转为标准 MP4 容器。

    视频流直接复制（copy）。
    音频流优先转为 AAC（兼容 MP4）；若没有音频则忽略。
    """
    logger.debug(f"[转码] 开始转换: {os.path.basename(src)} -> {os.path.basename(dst)}")

    try:
        # 先探测文件信息（看有没有音频流）
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
#  内部：FFmpeg concat 合并多个 MP4 文件
# ─────────────────────────────────────────────────────────────────────────────

def _ffmpeg_concat_fast(segments: List[str], output: str, merge_points: List[Tuple[str, str]]) -> Tuple[bool, str]:
    """
    快速模式：不转码，直接concat合并（竞业达风格）。

    优点：
    - 速度最快（不重新编码）
    - 质量无损（直接copy流）

    要求：
    - 所有分段必须格式一致（编码、分辨率、帧率等）
    - 如果格式不一致会失败，需要回退到标准模式

    Args:
        segments: 分段文件列表
        output: 输出文件路径
        merge_points: 合并点信息列表 [(segment_path, time_range)]
    """
    logger.info(f"[合并] 快速模式: {len(segments)} 个分段，不转码直接合并")
    logger.info(f"[合并] 输出文件: {os.path.basename(output)}")

    concat_list = output + ".concat_list.txt"
    try:
        # 写入concat列表
        with open(concat_list, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                # 转为绝对路径，使用正斜杠（FFmpeg concat demuxer 要求）
                abs_path = os.path.abspath(seg).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")
                logger.debug(f"[合并列表] 分段{i}: {os.path.basename(seg)} ({merge_points[i-1][1]})")

        # 快速合并：直接copy流，不转码
        start_time = time.time()
        logger.info(f"[合并] 开始快速合并...")

        result = subprocess.run(
            [FFMPEG_PATH, "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
             "-c", "copy", "-movflags", "+faststart", output],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=3600
        )

        elapsed = time.time() - start_time

        if result.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 0:
            size_mb = os.path.getsize(output) / 1024 / 1024
            logger.info(f"[合并] 成功! 耗时: {elapsed:.1f}秒, 大小: {size_mb:.1f}MB")
            logger.info(f"[合并] 合并点信息:")
            for i, (seg, time_range) in enumerate(merge_points, 1):
                logger.info(f"  - 合并点{i}: {time_range}")

            # 清理临时列表文件
            if os.path.exists(concat_list):
                os.remove(concat_list)

            return True, ""
        else:
            error_msg = result.stderr[-500:] if result.stderr else "unknown error"
            logger.error(f"[合并] 快速合并失败")
            logger.error(f"[合并] 返回码: {result.returncode}")
            logger.error(f"[合并] 错误输出: {error_msg}")
            logger.error(f"[合并] 标准输出: {result.stdout[-500:] if result.stdout else ''}")
            # 打印concat列表内容，帮助诊断
            if os.path.exists(concat_list):
                with open(concat_list, "r", encoding="utf-8") as f:
                    logger.error(f"[合并] Concat列表内容:\n{f.read()}")
            logger.warning(f"[合并] 将回退到标准模式（转码后合并）")

            # 清理失败的输出文件
            if os.path.exists(output):
                os.remove(output)

            return False, error_msg

    except subprocess.TimeoutExpired:
        logger.error(f"[合并] 快速合并超时")
        return False, "合并超时"
    except Exception as e:
        logger.error(f"[合并] 快速合并异常: {e}")
        return False, str(e)


def _ffmpeg_concat_standard(segments: List[str], output: str, merge_points: List[Tuple[str, str]]) -> Tuple[bool, str]:
    """
    标准模式：转码后合并（兼容性最好）。

    策略：
    1. 使用 concat demuxer + 音频转 AAC
    2. 失败则用 concat filter 重新编码

    优点：
    - 兼容性最好（自动处理格式不一致）
    - 音频标准化为AAC

    缺点：
    - 速度较慢（需要转码）
    - 可能轻微画质损失（重新编码）
    """
    logger.info(f"[合并] 标准模式: {len(segments)} 个分段，转码后合并")
    logger.info(f"[合并] 输出文件: {os.path.basename(output)}")

    concat_list = output + ".concat_list.txt"
    try:
        with open(concat_list, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                # 转为绝对路径，使用正斜杠（FFmpeg concat demuxer 要求）
                abs_path = os.path.abspath(seg).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")
                logger.debug(f"[合并列表] 分段{i}: {os.path.basename(seg)} ({merge_points[i-1][1]})")

        # 方式1：concat demuxer，视频copy，音频转AAC
        logger.info(f"[合并] 尝试方式1: concat demuxer + 音频转AAC")
        start_time = time.time()

        cmd1 = [
            FFMPEG_PATH, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output,
        ]
        r1 = subprocess.run(cmd1, capture_output=True, text=True,
                          encoding='utf-8', errors='ignore', timeout=1800)
        elapsed = time.time() - start_time

        if r1.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 0:
            size_mb = os.path.getsize(output) / 1024 / 1024
            logger.info(f"[合并] 方式1成功! 耗时: {elapsed:.1f}秒, 大小: {size_mb:.1f}MB")
            logger.info(f"[合并] 合并点信息:")
            for i, (seg, time_range) in enumerate(merge_points, 1):
                logger.info(f"  - 合并点{i}: {time_range}")
            return True, ""

        logger.warning(f"[合并] 方式1失败，尝试方式2")

        # 方式2：concat demuxer，丢弃音频
        if os.path.exists(output):
            os.remove(output)

        logger.info(f"[合并] 尝试方式2: concat demuxer + 丢弃音频")
        start_time = time.time()

        cmd2 = [
            FFMPEG_PATH, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "copy", "-an",
            "-movflags", "+faststart",
            output,
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True,
                          encoding='utf-8', errors='ignore', timeout=1800)
        elapsed = time.time() - start_time

        if r2.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 0:
            size_mb = os.path.getsize(output) / 1024 / 1024
            logger.info(f"[合并] 方式2成功(无音频)! 耗时: {elapsed:.1f}秒, 大小: {size_mb:.1f}MB")
            logger.info(f"[合并] 合并点信息:")
            for i, (seg, time_range) in enumerate(merge_points, 1):
                logger.info(f"  - 合并点{i}: {time_range}")
            return True, ""

        error_msg = r2.stderr[-500:] if r2.stderr else "unknown concat error"
        logger.error(f"[合并] 所有方式均失败")
        logger.error(f"[合并] 方式2返回码: {r2.returncode}")
        logger.error(f"[合并] 错误输出: {error_msg}")
        logger.error(f"[合并] 标准输出: {r2.stdout[-500:] if r2.stdout else ''}")
        # 打印concat列表内容，帮助诊断
        if os.path.exists(concat_list):
            with open(concat_list, "r", encoding="utf-8") as f:
                logger.error(f"[合并] Concat列表内容:\n{f.read()}")
        return False, error_msg

    except Exception as e:
        logger.error(f"[合并] 异常: {e}")
        return False, str(e)
    finally:
        if os.path.exists(concat_list):
            os.remove(concat_list)


# ─────────────────────────────────────────────────────────────────────────────
#  公共接口
# ─────────────────────────────────────────────────────────────────────────────

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
    timeout: Optional[int] = None,   # 保留参数兼容旧调用，内部忽略
    merge_mode: str = MERGE_MODE_STANDARD,  # 合并模式：fast(快速) 或 standard(标准)
    enable_debug_log: bool = False,  # 是否启用调试日志
    gui_log_callback: Optional[Callable[[str], None]] = None,  # GUI日志回调
    skip_transcode: bool = True,  # 是否跳过转码（默认跳过，原始文件可直接播放）
) -> Tuple[bool, str]:
    """
    下载指定时间段的录像，自动处理1GB文件限制。

    参数：
        merge_mode: 合并模式
            - "fast": 快速模式，不转码直接合并（最快，但要求所有段格式一致）
            - "standard": 标准模式，转码后合并（兼容性最好，速度较慢）

        enable_debug_log: 是否启用调试日志
            - True: 生成详细的下载和合并日志（用于调试合并点问题）
            - False: 不生成日志

        skip_transcode: 是否跳过转码
            - True: 跳过转码，直接使用原始文件（默认，速度更快）
            - False: 转换为标准MP4格式（兼容性更好）

    返回 (success, message)
    """
    save_dir = os.path.dirname(os.path.abspath(save_path))
    os.makedirs(save_dir, exist_ok=True)

    # 创建临时目录存放分段文件（避免污染用户目录）
    # 使用通道名和随机数确保多线程并发时不会冲突
    import random
    random_suffix = random.randint(10000, 99999)
    temp_dir = os.path.join(save_dir, f"temp_{int(time.time())}_{channel}_{random_suffix}")
    os.makedirs(temp_dir, exist_ok=True)

    # GUI日志辅助函数
    def gui_log(msg: str):
        """输出到GUI日志框"""
        if gui_log_callback:
            gui_log_callback(msg)
        print(f"[JavaDownloader] {msg}")
    
    # 调试：检查gui_log_callback是否为None
    if gui_log_callback is None:
        print(f"[JavaDownloader DEBUG] download_with_java: gui_log_callback is None!")

    # 设置调试日志
    if enable_debug_log:
        log_file = setup_download_logger(save_dir, f"{int(time.time())}")
        logger.info("=" * 80)
        logger.info(f"[下载任务] 开始")
        logger.info(f"设备: {ip}:{port}")
        logger.info(f"通道: {channel} - {channel_name}")
        logger.info(f"时间: {start_time} ~ {end_time}")
        logger.info(f"合并模式: {merge_mode}")
        logger.info(f"输出: {save_path}")
        logger.info(f"临时目录: {temp_dir}")
        logger.info("=" * 80)

    # 计算时长（取整，避免微秒导致的浮点数精度问题）
    duration_sec = int((end_time - start_time).total_seconds())

    gui_log(f"开始下载 ch{channel} ({channel_name})  {start_time} ~ {end_time}")
    gui_log(f"时长: {duration_sec/60:.1f} 分钟  目标: {save_path}")
    gui_log(f"合并模式: {'快速(不转码)' if merge_mode == MERGE_MODE_FAST else '标准(转码)'}")
    if enable_debug_log:
        gui_log(f"调试日志: {log_file}")

    if enable_debug_log:
        logger.info(f"[下载] 录像时长: {duration_sec/60:.1f} 分钟 ({duration_sec:.0f} 秒)")

    # ── 短录像：直接下载 ──────────────────────────────────────────────────────
    if duration_sec <= SEGMENT_MAX_SECONDS:
        logger.info(f"[下载] 短录像（<=40分钟），直接下载")

        ok, msg = _run_java_segment(
            ip, port, username, password, channel,
            start_time, end_time, save_path, channel_name,
            progress_callback=progress_callback,
            gui_log_callback=gui_log_callback,
        )


        if not ok:
            logger.error(f"[下载] 失败: {msg}")
            return False, msg

        # 根据参数决定是否转码
        if skip_transcode:
            # 跳过转码，直接使用原始文件
            size_mb = os.path.getsize(save_path) / 1024 / 1024
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
                size_mb = os.path.getsize(save_path) / 1024 / 1024
                gui_log(f"[WARN] 转换失败，保留原始文件: {err}")
                return True, f"下载成功(MPEG格式): {size_mb:.1f}MB"


    # ── 长录像：分段下载 + 合并 ─────────────────────────────────────────────
    # 修复浮点数精度问题：先取整再计算段数
    duration_sec_int = int(duration_sec)
    num_segs = math.ceil(duration_sec_int / SEGMENT_MAX_SECONDS)
    
    # 调试日志：记录详细计算过程
    logger.info(f"[分段] 录像时长 {duration_sec_int}秒 ({duration_sec_int/60:.1f}分钟)，每段{SEGMENT_MAX_SECONDS//60}分钟，分{num_segs}段")
    logger.info(f"[分段] 计算: ceil({duration_sec_int}/{SEGMENT_MAX_SECONDS}) = {num_segs}")
    gui_log(f"[SEG] 分段下载: {duration_sec_int/60:.1f}分钟，分{num_segs}段下载后合并")

    seg_files: List[str] = []     # 每段转换后的 MP4 路径
    seg_raw:   List[str] = []     # 每段原始路径（用于清理）
    merge_points: List[Tuple[str, str]] = []  # 合并点信息 [(文件路径, 时间范围)]
    failed_segs: List[int] = []

    for i in range(num_segs):
        seg_start = start_time + timedelta(seconds=i * SEGMENT_MAX_SECONDS)
        seg_end   = min(start_time + timedelta(seconds=(i + 1) * SEGMENT_MAX_SECONDS), end_time)

        # 跳过空段或过短的段（避免时间计算溢出或产生极短段）
        seg_duration_sec = (seg_end - seg_start).total_seconds()
        if seg_end <= seg_start or seg_duration_sec < 5:  # 少于5秒的段跳过
            gui_log(f"[SKIP] 跳过第 {i+1} 段（时长{seg_duration_sec:.1f}秒过短）：{seg_start.strftime('%H:%M:%S')} ~ {seg_end.strftime('%H:%M:%S')}")
            failed_segs.append(i + 1)  # 记录缺失段
            continue

        # 分段文件存放在临时目录
        seg_raw_path = os.path.join(
            temp_dir,
            f"_seg_{i+1:03d}_raw_ch{channel}_{int(time.time()*1000)}.mp4"
        )
        seg_mp4_path = os.path.join(
            temp_dir,
            f"_seg_{i+1:03d}_ch{channel}_{int(time.time()*1000)}.mp4"
        )
        seg_raw.append(seg_raw_path)
        seg_files.append(seg_mp4_path)

        time_range = f"{seg_start.strftime('%H:%M:%S')} ~ {seg_end.strftime('%H:%M:%S')}"
        logger.info(f"[分段{i+1}] 开始下载: {time_range}")
        gui_log(f"[DOWN] 分段{i+1}/{num_segs}: {time_range}")

        # 分段进度回调（换算为整体进度）
        def make_cb(seg_idx, total):
            def cb(pct):
                if progress_callback:
                    overall = int((seg_idx * 100 + pct) / total)
                    progress_callback(overall)
            return cb

        ok, msg = _run_java_segment(
            ip, port, username, password, channel,
            seg_start, seg_end, seg_raw_path, channel_name,
            progress_callback=make_cb(i, num_segs),
            gui_log_callback=gui_log_callback,
        )


        if not ok:
            logger.error(f"[分段{i+1}] 下载失败: {msg}")
            gui_log(f"[FAIL] 第 {i+1} 段下载失败: {msg}")
            failed_segs.append(i + 1)
            seg_files.pop()   # 移除这段，不加入合并列表
            seg_raw.pop()
            continue

        # 记录合并点信息
        if skip_transcode:
            # 跳过转码，直接使用原始文件
            merge_points.append((seg_raw_path, time_range))
            # 将原始文件路径也加入 seg_files（跳过转码时，seg_files存原始文件）
            seg_files[-1] = seg_raw_path  # 替换为原始文件路径

            size_mb = os.path.getsize(seg_raw_path) / 1024 / 1024
            duration_sec = (seg_end - seg_start).total_seconds()
            logger.info(f"[分段{i+1}] 跳过转码: {size_mb:.1f}MB, 时长: {duration_sec/60:.1f}分钟, 时间: {time_range}")
            gui_log(f"[OK] 分段{i+1}: {size_mb:.1f}MB, {duration_sec/60:.1f}分钟, {time_range} (原始格式)")
        else:
            # 转换单段为 MP4
            merge_points.append((seg_mp4_path, time_range))

            logger.info(f"[分段{i+1}] 开始转换为MP4...")
            gui_log(f"[CONV] 转换第 {i+1} 段为MP4...")
            ok2, err = _ffmpeg_to_mp4(seg_raw_path, seg_mp4_path)

            if ok2:
                os.remove(seg_raw_path)
                size_mb = os.path.getsize(seg_mp4_path) / 1024 / 1024
                duration_sec = (seg_end - seg_start).total_seconds()
                logger.info(f"[分段{i+1}] 成功: {size_mb:.1f}MB, 时长: {duration_sec/60:.1f}分钟, 时间: {time_range}")
                gui_log(f"[OK] 分段{i+1}: {size_mb:.1f}MB, {duration_sec/60:.1f}分钟, {time_range}")
            else:
                # FFmpeg 转换失败，尝试直接用原始文件合并
                logger.warning(f"[分段{i+1}] 转换失败，使用原始文件: {err}")
                gui_log(f"[WARN] 分段{i+1} 转换失败，使用原始文件: {err}")
                # 把原始文件路径放到 seg_files 里
                seg_files[-1] = seg_raw_path
                seg_mp4_path  = seg_raw_path
                # 更新合并点信息
                merge_points[-1] = (seg_raw_path, time_range)


    if not seg_files:
        logger.error(f"[完成] 所有分段均下载失败")
        gui_log(f"[FAIL] 所有分段均下载失败")
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
            print(f"[JavaDownloader] 已清理临时目录: {temp_dir}")
        except Exception as e:
            print(f"[JavaDownloader] 清理临时目录失败: {e}")
        return False, f"所有分段均下载失败"

    if failed_segs:
        logger.warning(f"[完成] 部分分段失败: {failed_segs}，成功 {len(seg_files)} 段")
        gui_log(f"[WARN] 部分分段失败: {failed_segs}，成功 {len(seg_files)} 段，继续合并")

    # ── 合并 ──────────────────────────────────────────────────────────────────
    # 验证所有分段文件都存在
    missing_files = [f for f in seg_files if not os.path.exists(f)]
    if missing_files:
        logger.error(f"[合并] 分段文件缺失: {missing_files}")
        gui_log(f"[FAIL] 分段文件缺失: {len(missing_files)} 个文件不存在")
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
            print(f"[JavaDownloader] 已清理临时目录: {temp_dir}")
        except Exception as e:
            print(f"[JavaDownloader] 清理临时目录失败: {e}")
        return False, f"合并失败：{len(missing_files)} 个分段文件不存在"

    if len(seg_files) == 1:
        # 只有一段，直接移动
        logger.info(f"[合并] 只有1段，直接移动")
        gui_log(f"[MERGE] 只有1段，直接移动")
        os.replace(seg_files[0], save_path)
    else:
        logger.info(f"[合并] 开始合并 {len(seg_files)} 段")
        gui_log(f"[MERGE] 开始合并 {len(seg_files)} 段...")

        # 根据模式选择合并方式
        if merge_mode == MERGE_MODE_FAST:
            # 快速模式：不转码直接合并
            gui_log(f"[FAST] 快速合并模式（不转码）...")
            ok_merge, err_merge = _ffmpeg_concat_fast(seg_files, save_path, merge_points)

            # 如果快速模式失败，回退到标准模式
            if not ok_merge:
                logger.warning(f"[合并] 快速模式失败，回退到标准模式")
                gui_log(f"[WARN] 快速合并失败，改用标准模式（转码）...")
                ok_merge, err_merge = _ffmpeg_concat_standard(seg_files, save_path, merge_points)
        else:
            # 标准模式：转码后合并
            gui_log(f"[STD] 标准合并模式（转码）...")
            ok_merge, err_merge = _ffmpeg_concat_standard(seg_files, save_path, merge_points)
        if not ok_merge:
            gui_log(f"[FAIL] FFmpeg合并失败: {err_merge}")
            # 清理临时目录
            try:
                shutil.rmtree(temp_dir)
                print(f"[JavaDownloader] 已清理临时目录: {temp_dir}")
            except Exception as e:
                print(f"[JavaDownloader] 清理临时目录失败: {e}")
            return False, f"FFmpeg 合并失败: {err_merge}"

        # 清理分段文件
        for sf in seg_files:
            if os.path.exists(sf):
                try:
                    os.remove(sf)
                except Exception as e:
                    logger.warning(f"[清理] 删除分段文件失败: {sf}, 错误: {e}")
                    # 继续清理其他文件，不要因为一个文件失败就中断

    if not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
        return False, "合并后文件不存在或为空"

    total_mb = os.path.getsize(save_path) / 1024 / 1024
    warn_str = f" (缺失段: {failed_segs})" if failed_segs else ""
    gui_log(f"[OK] 完成: {total_mb:.1f}MB{warn_str}")

    # 清理临时目录（分段原始文件）
    # 增加短暂延迟，确保文件句柄已释放
    time.sleep(0.5)
    try:
        shutil.rmtree(temp_dir)
        print(f"[JavaDownloader] 已清理临时目录: {temp_dir}")
    except Exception as e:
        print(f"[JavaDownloader] 清理临时目录失败: {e}")
        logger.warning(f"[完成] 清理临时目录失败: {e}")
        # 不影响下载成功状态，临时文件会留到下次覆盖或手动清理

    return True, f"下载成功{warn_str}, 总大小: {total_mb:.1f}MB"


def quick_test():
    """快速测试下载功能（5分钟）"""
    now   = datetime.now().replace(second=0, microsecond=0)
    start = now - timedelta(minutes=65)   # 测试65分钟，触发分段逻辑
    end   = now - timedelta(minutes=5)

    print(f"测试分段下载: {start} ~ {end}  ({(end-start).seconds//60} 分钟)")

    ok, msg = download_with_java(
        ip="10.26.223.253",
        port=8000,
        username="admin",
        password="a1111111",
        channel=1,
        start_time=start,
        end_time=end,
        save_path=r"C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_downloader\downloads\test_segmented.mp4",
        channel_name="测试通道",
        progress_callback=lambda p: print(f"  总进度: {p}%"),
    )

    print(f"\n结果: ok={ok}  msg={msg}")


if __name__ == "__main__":
    quick_test()
