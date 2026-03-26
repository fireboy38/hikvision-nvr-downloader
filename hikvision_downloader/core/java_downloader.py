"""
海康威视NVR录像下载器

核心逻辑：
1. V40接口探测：先探测设备是否支持V40接口（无1GB限制）
2. V40可用：直接下载整段，不分段，不合并
3. V30回退：>55分钟则分段下载（规避SDK 1GB文件限制），FFmpeg合并
4. 支持三种合并模式（仅V30分段时使用）：
   - 极速模式：不转码，无faststart（最快）
   - 快速模式：不转码，直接concat
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
from typing import Tuple, Optional, Callable, List, Dict, Any
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
# 为安全起见每段限制为 55分钟 = 3300秒（接近但不超过1GB）
SEGMENT_MAX_SECONDS = 55 * 60   # 每段最大时长（秒）

# 合并模式
MERGE_MODE_ULTRA = "ultra"   # 极速模式：不转码，无faststart（最快）
MERGE_MODE_FAST = "fast"     # 快速模式：不转码，直接concat
MERGE_MODE_STANDARD = "standard"  # 标准模式：转码后合并

# 配置日志
logger = logging.getLogger(__name__)

def setup_download_logger(log_dir: str, task_id: str, channel_name: str = ""):
    """
    设置下载调试日志

    记录内容包括：
    - 每个分段的时间范围
    - 每个分段的大小和时长
    - FFmpeg合并命令和输出
    - 合并点时间戳信息
    
    日志文件统一输出到 debug 子目录，文件名包含通道名便于识别
    """
    # 创建 debug 子目录
    debug_dir = os.path.join(log_dir, "debug")
    os.makedirs(debug_dir, exist_ok=True)
    
    # 构建文件名：包含通道名和时间戳
    if channel_name:
        # 清理通道名中的非法字符
        safe_channel = channel_name.strip().replace(' ', '_').replace('/', '_').replace('\\', '_')
        log_file = os.path.join(debug_dir, f"{safe_channel}_{task_id}.log")
    else:
        log_file = os.path.join(debug_dir, f"download_{task_id}.log")
    
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
#  内部：探测设备是否支持 V40 接口
# ─────────────────────────────────────────────────────────────────────────────

def _detect_v40_support(
    ip: str, port: int, username: str, password: str,
    channel: int,
    channel_name: str = "",
    gui_log_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    用一个30秒的小文件探测设备是否支持V40接口。
    返回 True 表示V40可用。
    """
    def gui_log(msg: str):
        if gui_log_callback:
            try:
                gui_log_callback(msg)
            except Exception:
                pass
        print(f"[V40探测] {msg}")

    # 取当前时间前2分钟的30秒作为探测段
    now = datetime.now()
    probe_start = now - timedelta(minutes=2)
    probe_end = probe_start + timedelta(seconds=30)

    # 临时文件路径
    import tempfile
    tmp_dir = tempfile.gettempdir()
    probe_file = os.path.join(tmp_dir, f"_v40_probe_{channel}_{int(time.time())}.mp4")

    try:
        gui_log(f"正在探测 V40 接口支持（通道{channel}）...")

        java_exe = os.path.join(JAVA_HOME, "bin", "java.exe")
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
            probe_start.strftime("%Y-%m-%d %H:%M:%S"),
            probe_end.strftime("%Y-%m-%d %H:%M:%S"),
            probe_file,
            f"V40探测",
        ]

        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        output_lines = []
        timeout_sec = 120  # 探测最多等2分钟
        start_ts = time.time()

        while True:
            if time.time() - start_ts > timeout_sec:
                process.terminate()
                gui_log("探测超时")
                return False

            line = process.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line:
                output_lines.append(line)
                gui_log(line)

            # 关键判断行
            if "[OK] V40 handle:" in line:
                # V40成功！等进程完成
                process.wait(timeout=60)
                # 清理探测文件
                try:
                    if os.path.exists(probe_file):
                        os.remove(probe_file)
                except Exception:
                    pass
                return True

            if "[OK] Using V30 handle:" in line:
                # V40失败，回退到V30
                process.wait(timeout=60)
                try:
                    if os.path.exists(probe_file):
                        os.remove(probe_file)
                except Exception:
                    pass
                return False

            if "[FAIL]" in line:
                process.wait(timeout=30)
                return False

            if process.poll() is not None:
                break

        process.wait(timeout=30)
        return False

    except Exception as e:
        gui_log(f"探测异常: {e}")
        return False
    finally:
        try:
            if os.path.exists(probe_file):
                os.remove(probe_file)
        except Exception:
            pass










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

def _ffmpeg_concat_ultra(segments: List[str], output: str, merge_points: List[Tuple[str, str]]) -> Tuple[bool, str]:
    """
    极速模式：不转码，无faststart（最快）。

    优点：
    - 速度最快（不重新编码，无faststart开销）
    - 质量无损（直接copy流）
    - 适合本地播放场景

    缺点：
    - 没有faststart，网络播放需要下载完才能播放

    要求：
    - 所有分段必须格式一致（编码、分辨率、帧率等）
    """
    logger.info(f"[合并] 极速模式: {len(segments)} 个分段，无faststart")
    logger.info(f"[合并] 输出文件: {os.path.basename(output)}")

    concat_list = output + ".concat_list.txt"
    try:
        with open(concat_list, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                abs_path = os.path.abspath(seg).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")
                logger.debug(f"[合并列表] 分段{i}: {os.path.basename(seg)} ({merge_points[i-1][1]})")

        start_time = time.time()
        logger.info(f"[合并] 开始极速合并...")

        # 极速模式：无faststart，最快
        result = subprocess.run(
            [FFMPEG_PATH, "-y", "-nostats", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", concat_list,
             "-c", "copy", "-threads", "4", output],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=3600
        )

        elapsed = time.time() - start_time

        if result.returncode == 0 and os.path.exists(output) and os.path.getsize(output) > 0:
            size_mb = os.path.getsize(output) / 1024 / 1024
            logger.info(f"[合并] 极速模式成功! 耗时: {elapsed:.1f}秒, 大小: {size_mb:.1f}MB")
            if os.path.exists(concat_list):
                os.remove(concat_list)
            return True, ""
        else:
            error_msg = result.stderr[-500:] if result.stderr else "unknown error"
            logger.error(f"[合并] 极速模式失败: {error_msg}")
            if os.path.exists(concat_list):
                with open(concat_list, "r", encoding="utf-8") as f:
                    logger.error(f"[合并] Concat列表:\n{f.read()}")
            if os.path.exists(output):
                os.remove(output)
            return False, error_msg

    except subprocess.TimeoutExpired:
        logger.error(f"[合并] 极速模式超时")
        return False, "合并超时"
    except Exception as e:
        logger.error(f"[合并] 极速模式异常: {e}")
        return False, str(e)


def _ffmpeg_concat_fast(segments: List[str], output: str, merge_points: List[Tuple[str, str]]) -> Tuple[bool, str]:
    """
    快速模式：不转码，直接concat合并（竞业达风格）。

    优点：
    - 速度最快（不重新编码）
    - 质量无损（直接copy流）
    - 有faststart，适合网络播放

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
        # 优化参数：
        # - -threads 4: 使用多线程（虽然copy模式线程收益不大，但某些操作可能受益）
        # - -nostats: 不输出统计信息，减少IO
        # - -loglevel error: 只输出错误，减少日志开销
        start_time = time.time()
        logger.info(f"[合并] 开始快速合并...")

        result = subprocess.run(
            [FFMPEG_PATH, "-y", "-nostats", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", concat_list,
             "-c", "copy", "-movflags", "+faststart", "-threads", "4", output],
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
        log_file = setup_download_logger(save_dir, f"{int(time.time())}", channel_name)
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

    if enable_debug_log:
        logger.info(f"[下载] 录像时长: {duration_sec/60:.1f} 分钟 ({duration_sec:.0f} 秒)")

    # ── 探测V40接口 ────────────────────────────────────────────────────────
    v40_supported = _detect_v40_support(
        ip, port, username, password, channel, channel_name, gui_log_callback
    )

    if v40_supported:
        gui_log(f"[V40] ✅ 设备支持V40接口，直接下载（无1GB限制，无需分段）")
        logger.info(f"[V40] 设备支持V40接口，直接下载整段")
    else:
        gui_log(f"[V30] ⚠️ 设备不支持V40，使用V30接口（有1GB限制，长录像需分段）")
        logger.info(f"[V30] 设备不支持V40，使用V30分段策略")
        mode_text = {'ultra': '极速(无faststart)', 'fast': '快速(不转码)', 'standard': '标准(转码)'}.get(merge_mode, '快速')
        gui_log(f"合并模式: {mode_text}")

    # ── V40: 直接下载整段，不分段 ───────────────────────────────────────────
    if v40_supported:
        ok, msg = _run_java_segment(
            ip, port, username, password, channel,
            start_time, end_time, save_path, channel_name,
            progress_callback=progress_callback,
            gui_log_callback=gui_log_callback,
        )

        if not ok:
            logger.error(f"[V40下载] 失败: {msg}")
            return False, msg

        # 根据参数决定是否转码
        if skip_transcode:
            size_mb = os.path.getsize(save_path) / 1024 / 1024
            logger.info(f"[V40完成] 跳过转码，使用原始文件: {size_mb:.1f}MB")
            gui_log(f"[OK] V40下载完成: {size_mb:.1f}MB (原始格式)")
            return True, f"下载成功(V40), 大小: {size_mb:.1f}MB"
        else:
            logger.info(f"[转码] 开始转换为标准MP4...")
            gui_log(f"[CONV] 转换为标准MP4...")
            conv_path = save_path.replace(".mp4", "_conv.mp4")
            ok2, err = _ffmpeg_to_mp4(save_path, conv_path)

            if ok2:
                os.remove(save_path)
                os.rename(conv_path, save_path)
                size_mb = os.path.getsize(save_path) / 1024 / 1024
                logger.info(f"[V40完成] 成功: {size_mb:.1f}MB")
                gui_log(f"[OK] V40下载完成: {size_mb:.1f}MB (标准MP4)")
                return True, f"下载成功(V40), 大小: {size_mb:.1f}MB"
            else:
                logger.warning(f"[V40完成] 转换失败，保留原始文件: {err}")
                size_mb = os.path.getsize(save_path) / 1024 / 1024
                gui_log(f"[WARN] 转换失败，保留原始文件: {err}")
                return True, f"下载成功(V40, MPEG格式): {size_mb:.1f}MB"

    # ── V30: 短录像直接下载 ────────────────────────────────────────────────
    if duration_sec <= SEGMENT_MAX_SECONDS:
        logger.info(f"[V30下载] 短录像（<={SEGMENT_MAX_SECONDS//60}分钟），直接下载")

        ok, msg = _run_java_segment(
            ip, port, username, password, channel,
            start_time, end_time, save_path, channel_name,
            progress_callback=progress_callback,
            gui_log_callback=gui_log_callback,
        )


        if not ok:
            logger.error(f"[V30下载] 失败: {msg}")
            return False, msg

        # 根据参数决定是否转码
        if skip_transcode:
            # 跳过转码，直接使用原始文件
            size_mb = os.path.getsize(save_path) / 1024 / 1024
            logger.info(f"[V30完成] 跳过转码，使用原始文件: {size_mb:.1f}MB")
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
                logger.info(f"[V30完成] 成功: {size_mb:.1f}MB")
                gui_log(f"[OK] 完成: {size_mb:.1f}MB (标准MP4)")
                return True, f"下载成功, 大小: {size_mb:.1f}MB"
            else:
                logger.warning(f"[V30完成] 转换失败，保留原始文件: {err}")
                size_mb = os.path.getsize(save_path) / 1024 / 1024
                gui_log(f"[WARN] 转换失败，保留原始文件: {err}")
                return True, f"下载成功(MPEG格式): {size_mb:.1f}MB"


    # ── V30: 长录像分段下载 + 合并 ─────────────────────────────────────────
    # 修复浮点数精度问题：先取整再计算段数
    duration_sec_int = int(duration_sec)
    num_segs = math.ceil(duration_sec_int / SEGMENT_MAX_SECONDS)
    
    # 调试日志：记录详细计算过程
    channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
    logger.info(f"[分段] {channel_info} 录像时长 {duration_sec_int}秒 ({duration_sec_int/60:.1f}分钟)，每段{SEGMENT_MAX_SECONDS//60}分钟，分{num_segs}段")
    logger.info(f"[分段] {channel_info} 计算: ceil({duration_sec_int}/{SEGMENT_MAX_SECONDS}) = {num_segs}")
    gui_log(f"[SEG] {channel_info} 分段下载: {duration_sec_int/60:.1f}分钟，分{num_segs}段下载后合并")

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
        channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
        logger.info(f"[分段{i+1}] {channel_info} 开始下载: {time_range}")
        gui_log(f"[DOWN] {channel_info} 分段{i+1}/{num_segs}: {time_range}")

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
            channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
            logger.error(f"[分段{i+1}] {channel_info} 下载失败: {msg}")
            gui_log(f"[FAIL] {channel_info} 第 {i+1} 段下载失败: {msg}")
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
            channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
            logger.info(f"[分段{i+1}] {channel_info} 跳过转码: {size_mb:.1f}MB, 时长: {duration_sec/60:.1f}分钟, 时间: {time_range}")
            gui_log(f"[OK] {channel_info} 分段{i+1}: {size_mb:.1f}MB, {duration_sec/60:.1f}分钟, {time_range} (原始格式)")
        else:
            # 转换单段为 MP4
            merge_points.append((seg_mp4_path, time_range))

            channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
            logger.info(f"[分段{i+1}] {channel_info} 开始转换为MP4...")
            gui_log(f"[CONV] {channel_info} 转换第 {i+1} 段为MP4...")
            ok2, err = _ffmpeg_to_mp4(seg_raw_path, seg_mp4_path)

            if ok2:
                os.remove(seg_raw_path)
                size_mb = os.path.getsize(seg_mp4_path) / 1024 / 1024
                duration_sec = (seg_end - seg_start).total_seconds()
                channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
                logger.info(f"[分段{i+1}] {channel_info} 成功: {size_mb:.1f}MB, 时长: {duration_sec/60:.1f}分钟, 时间: {time_range}")
                gui_log(f"[OK] {channel_info} 分段{i+1}: {size_mb:.1f}MB, {duration_sec/60:.1f}分钟, {time_range}")
            else:
                # FFmpeg 转换失败，尝试直接用原始文件合并
                channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
                logger.warning(f"[分段{i+1}] {channel_info} 转换失败，使用原始文件: {err}")
                gui_log(f"[WARN] {channel_info} 分段{i+1} 转换失败，使用原始文件: {err}")
                # 把原始文件路径放到 seg_files 里
                seg_files[-1] = seg_raw_path
                seg_mp4_path  = seg_raw_path
                # 更新合并点信息
                merge_points[-1] = (seg_raw_path, time_range)


    if not seg_files:
        channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
        logger.error(f"[完成] {channel_info} 所有分段均下载失败")
        gui_log(f"[FAIL] {channel_info} 所有分段均下载失败")
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
            print(f"[JavaDownloader] 已清理临时目录: {temp_dir}")
        except Exception as e:
            print(f"[JavaDownloader] 清理临时目录失败: {e}")
        return False, f"所有分段均下载失败"

    if failed_segs:
        channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
        logger.warning(f"[完成] {channel_info} 部分分段失败: {failed_segs}，成功 {len(seg_files)} 段")
        gui_log(f"[WARN] {channel_info} 部分分段失败: {failed_segs}，成功 {len(seg_files)} 段，继续合并")

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
        channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
        logger.info(f"[合并] {channel_info} 只有1段，直接移动")
        gui_log(f"[MERGE] {channel_info} 只有1段，直接移动")
        os.replace(seg_files[0], save_path)
    else:
        channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
        logger.info(f"[合并] {channel_info} 开始合并 {len(seg_files)} 段")
        gui_log(f"[MERGE] {channel_info} 开始合并 {len(seg_files)} 段...")
        
        # 记录合并开始时间
        merge_start_time = time.time()

        # 根据模式选择合并方式
        if merge_mode == MERGE_MODE_ULTRA:
            # 极速模式：无faststart，最快
            gui_log(f"[ULTRA] 极速合并模式（无faststart）...")
            ok_merge, err_merge = _ffmpeg_concat_ultra(seg_files, save_path, merge_points)
            # 极速模式失败，回退到快速模式
            if not ok_merge:
                logger.warning(f"[合并] 极速模式失败，回退到快速模式")
                gui_log(f"[WARN] 极速合并失败，改用快速模式...")
                ok_merge, err_merge = _ffmpeg_concat_fast(seg_files, save_path, merge_points)
            # 快速模式也失败，回退到标准模式
            if not ok_merge:
                logger.warning(f"[合并] 快速模式失败，回退到标准模式")
                gui_log(f"[WARN] 快速合并失败，改用标准模式（转码）...")
                ok_merge, err_merge = _ffmpeg_concat_standard(seg_files, save_path, merge_points)
        elif merge_mode == MERGE_MODE_FAST:
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
        
        # 计算合并用时
        merge_elapsed = time.time() - merge_start_time
        
        if ok_merge:
            gui_log(f"[MERGE] 合并完成，用时: {merge_elapsed:.1f}秒")
        else:
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


# ─────────────────────────────────────────────────────────────────────────────
#  下载和转码分离架构 - 新接口
# ─────────────────────────────────────────────────────────────────────────────

def download_only(
    ip: str,
    port: int,
    username: str,
    password: str,
    channel: int,
    start_time: datetime,
    end_time: datetime,
    save_dir: str,
    channel_name: str = "",
    progress_callback: Optional[Callable[[int], None]] = None,
    gui_log_callback: Optional[Callable[[str], None]] = None,
    enable_debug_log: bool = False,
) -> Tuple[bool, str, Optional[Dict]]:
    """
    只下载原始文件，不转码/合并，返回分段信息供后续异步转码
    
    返回: (success, message, transcode_info)
        transcode_info: 包含转码所需信息的字典，如果下载成功
            {
                'channel': int,
                'channel_name': str,
                'device_id': str,
                'seg_files': List[str],       # 下载的分段文件
                'seg_raw_files': List[str],   # 原始文件列表
                'temp_dir': str,              # 临时目录
                'merge_points': List[Tuple[str, str]],
                'save_path': str,             # 最终输出路径
            }
    """
    import random
    import uuid
    
    os.makedirs(save_dir, exist_ok=True)
    
    # 创建临时目录
    random_suffix = random.randint(10000, 99999)
    temp_dir = os.path.join(save_dir, f"temp_{int(time.time())}_{channel}_{random_suffix}")
    os.makedirs(temp_dir, exist_ok=True)
    
    def gui_log(msg: str):
        if gui_log_callback:
            gui_log_callback(msg)
        print(f"[JavaDownloader] {msg}")
    
    # 生成最终输出路径
    date_str = start_time.strftime("%Y%m%d")
    time_range = f"{start_time.strftime('%H%M%S')}_{end_time.strftime('%H%M%S')}"
    safe_channel = channel_name.strip() if channel_name else f"CH{channel}"
    import re
    safe_channel = re.sub(r'[\\/:*?"<>|]', '', safe_channel)
    safe_channel = safe_channel or f"CH{channel}"
    filename = f"{safe_channel}_{date_str}_{time_range}.mp4"
    save_path = os.path.join(save_dir, filename)
    
    device_id = f"{ip}:{port}"
    channel_info = f"通道{channel}" + (f"({channel_name})" if channel_name else "")
    
    # 设置调试日志
    if enable_debug_log:
        log_file = setup_download_logger(save_dir, f"{int(time.time())}", channel_name)
        logger.info("=" * 80)
        logger.info(f"[下载任务-仅下载] 开始 {channel_info}")
        logger.info(f"设备: {ip}:{port}")
        logger.info(f"时间: {start_time} ~ {end_time}")
        logger.info(f"临时目录: {temp_dir}")
        logger.info("=" * 80)
    
    duration_sec = int((end_time - start_time).total_seconds())
    gui_log(f"[DOWNLOAD-ONLY] {channel_info} 开始下载 {duration_sec/60:.1f}分钟")
    
    # ── 探测V40接口 ──
    v40_supported = _detect_v40_support(ip, port, username, password, channel, channel_name, gui_log_callback)
    
    if v40_supported:
        gui_log(f"[V40] ✅ 设备支持V40，直接下载（不分段）")
        logger.info(f"[download_only] V40可用，直接下载整段")
    
    # ── V40: 直接下载，不分段 ──
    if v40_supported:
        seg_raw_path = os.path.join(temp_dir, f"_seg_001_raw_ch{channel}_{int(time.time()*1000)}.mp4")
        
        ok, msg = _run_java_segment(
            ip, port, username, password, channel,
            start_time, end_time, seg_raw_path, channel_name,
            progress_callback=progress_callback,
            gui_log_callback=gui_log_callback,
        )
        
        if not ok:
            logger.error(f"[download_only V40] 失败: {msg}")
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
            return False, msg, None
        
        size_mb = os.path.getsize(seg_raw_path) / 1024 / 1024
        gui_log(f"[DOWNLOAD-OK] {channel_info} V40下载完成: {size_mb:.1f}MB")
        
        transcode_info = {
            'task_id': str(uuid.uuid4()),
            'channel': channel,
            'channel_name': channel_name,
            'device_id': device_id,
            'seg_files': [seg_raw_path],
            'seg_raw_files': [seg_raw_path],
            'temp_dir': temp_dir,
            'merge_points': [(seg_raw_path, f"{start_time.strftime('%H:%M:%S')} ~ {end_time.strftime('%H:%M:%S')}")],
            'save_path': save_path,
            'v40': True,  # 标记为V40下载
        }
        return True, f"V40下载完成: {size_mb:.1f}MB", transcode_info
    
    # ── V30: 短录像直接下载 ──
    if duration_sec <= SEGMENT_MAX_SECONDS:
        seg_raw_path = os.path.join(temp_dir, f"_seg_001_raw_ch{channel}_{int(time.time()*1000)}.mp4")
        
        ok, msg = _run_java_segment(
            ip, port, username, password, channel,
            start_time, end_time, seg_raw_path, channel_name,
            progress_callback=progress_callback,
            gui_log_callback=gui_log_callback,
        )
        
        if not ok:
            logger.error(f"[下载失败] {channel_info}: {msg}")
            # 清理临时目录
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
            return False, msg, None
        
        size_mb = os.path.getsize(seg_raw_path) / 1024 / 1024
        gui_log(f"[DOWNLOAD-OK] {channel_info} 下载完成: {size_mb:.1f}MB")
        
        transcode_info = {
            'task_id': str(uuid.uuid4()),
            'channel': channel,
            'channel_name': channel_name,
            'device_id': device_id,
            'seg_files': [seg_raw_path],
            'seg_raw_files': [seg_raw_path],
            'temp_dir': temp_dir,
            'merge_points': [(seg_raw_path, f"{start_time.strftime('%H:%M:%S')} ~ {end_time.strftime('%H:%M:%S')}")],
            'save_path': save_path,
        }
        return True, f"下载完成: {size_mb:.1f}MB", transcode_info
    
    # ── V30: 长录像分段下载 ──
    gui_log(f"[V30] 设备不支持V40，分段下载")
    
    duration_sec_int = int(duration_sec)
    num_segs = math.ceil(duration_sec_int / SEGMENT_MAX_SECONDS)
    gui_log(f"[SEG] {channel_info} 分段下载: {num_segs}段")
    
    seg_files = []
    seg_raw_files = []
    merge_points = []
    failed_segs = []
    
    for i in range(num_segs):
        seg_start = start_time + timedelta(seconds=i * SEGMENT_MAX_SECONDS)
        seg_end = min(start_time + timedelta(seconds=(i + 1) * SEGMENT_MAX_SECONDS), end_time)
        
        seg_duration_sec = (seg_end - seg_start).total_seconds()
        if seg_end <= seg_start or seg_duration_sec < 5:
            gui_log(f"[SKIP] {channel_info} 跳过第{i+1}段（时长过短）")
            failed_segs.append(i + 1)
            continue
        
        seg_raw_path = os.path.join(temp_dir, f"_seg_{i+1:03d}_raw_ch{channel}_{int(time.time()*1000)}.mp4")
        seg_raw_files.append(seg_raw_path)
        
        time_range = f"{seg_start.strftime('%H:%M:%S')} ~ {seg_end.strftime('%H:%M:%S')}"
        gui_log(f"[DOWN] {channel_info} 分段{i+1}/{num_segs}: {time_range}")
        
        # 分段进度回调
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
            logger.error(f"[分段失败] {channel_info} 第{i+1}段: {msg}")
            gui_log(f"[FAIL] {channel_info} 第{i+1}段下载失败")
            failed_segs.append(i + 1)
            seg_raw_files.pop()
            continue
        
        seg_files.append(seg_raw_path)
        merge_points.append((seg_raw_path, time_range))
        
        size_mb = os.path.getsize(seg_raw_path) / 1024 / 1024
        gui_log(f"[OK] {channel_info} 分段{i+1}: {size_mb:.1f}MB")
    
    if not seg_files:
        gui_log(f"[FAIL] {channel_info} 所有分段下载失败")
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
        return False, "所有分段下载失败", None
    
    if failed_segs:
        gui_log(f"[WARN] {channel_info} 部分分段失败: {failed_segs}")
    
    total_mb = sum(os.path.getsize(f) for f in seg_files) / 1024 / 1024
    gui_log(f"[DOWNLOAD-OK] {channel_info} 下载完成: {len(seg_files)}段, {total_mb:.1f}MB")
    
    transcode_info = {
        'task_id': str(uuid.uuid4()),
        'channel': channel,
        'channel_name': channel_name,
        'device_id': device_id,
        'seg_files': seg_files,
        'seg_raw_files': seg_raw_files,
        'temp_dir': temp_dir,
        'merge_points': merge_points,
        'save_path': save_path,
    }
    
    warn_str = f" (缺失段: {failed_segs})" if failed_segs else ""
    return True, f"下载完成{warn_str}: {len(seg_files)}段, {total_mb:.1f}MB", transcode_info


if __name__ == "__main__":
    quick_test()
