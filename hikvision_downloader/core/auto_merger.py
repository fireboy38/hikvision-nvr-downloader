# 录像自动合并模块
# 用于合并SDK自动分割的录像片段文件
import os
import re
import glob
from pathlib import Path
from typing import List, Tuple
import subprocess

FFMPEG_PATH = r"C:\tools\ffmpeg\bin\ffmpeg.exe"


def detect_split_files(directory: str, pattern: str = "*.mp4") -> List[List[str]]:
    """
    检测并分组同一录像的分割文件

    SDK分割文件命名规律：
    - 基础文件名：ch1_20260323_232819.mp4
    - 分割文件：ch1_20260323_232819_1.mp4, ch1_20260323_232819_2.mp4, ...
                    或：ch1_20260323_232819.mp4.1, ch1_20260323_232819.mp4.2, ...

    Args:
        directory: 目录路径
        pattern: 文件匹配模式

    Returns:
        分组后的文件列表 [[file1, file2, ...], [file3, ...], ...]
    """
    # 获取所有匹配的文件
    files = sorted(Path(directory).glob(pattern))

    # 按基础文件名分组
    groups = {}

    for file in files:
        filename = file.name

        # 尝试两种分割命名模式
        # 模式1: ch1_20260323_232819_1.mp4 (下划线+数字+扩展名)
        match1 = re.match(r'^(.+?)_(\d+)\.(mp4|avi|mov)$', filename)
        # 模式2: ch1_20260323_232819.mp4.1 (扩展名+点+数字)
        match2 = re.match(r'^(.+?)\.(mp4|avi|mov)\.(\d+)$', filename)

        if match1:
            base_name = match1.group(1)
            segment_num = int(match1.group(2))
            ext = match1.group(3)
            # 重建基础文件名
            base_filename = f"{base_name}.{ext}"
        elif match2:
            base_filename = match2.group(0)
            segment_num = int(match2.group(3))
        else:
            # 不是分割文件，跳过
            continue

        # 添加到分组
        if base_filename not in groups:
            groups[base_filename] = []
        groups[base_filename].append((segment_num, str(file)))

    # 对每组文件按段号排序
    result = []
    for base_filename, segment_files in groups.items():
        # 按段号排序
        sorted_files = sorted(segment_files, key=lambda x: x[0])
        # 提取文件路径
        file_list = [f[1] for f in sorted_files]

        if len(file_list) > 1:  # 只处理有多个片段的情况
            result.append(file_list)

    return result


def merge_videos(input_files: List[str], output_file: str) -> Tuple[bool, str]:
    """
    使用FFmpeg合并多个视频文件

    Args:
        input_files: 输入文件列表（按顺序）
        output_file: 输出文件路径

    Returns:
        (success, message)
    """
    if not input_files:
        return False, "没有输入文件"

    if len(input_files) == 1:
        # 只有一个文件，直接复制
        import shutil
        try:
            shutil.copy(input_files[0], output_file)
            size = os.path.getsize(output_file)
            return True, f"单个文件已复制 ({size/1024/1024:.2f}MB)"
        except Exception as e:
            return False, f"复制失败: {e}"

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    print(f"[AutoMerge] 开始合并 {len(input_files)} 个文件...")

    # 创建 concat 文件列表
    concat_file = os.path.join(
        os.path.dirname(output_file),
        f"concat_{os.path.basename(output_file)}.txt"
    )

    try:
        # 写入 concat 列表文件
        with open(concat_file, 'w', encoding='utf-8') as f:
            for input_file in input_files:
                # 转换为绝对路径并转义特殊字符
                abs_path = os.path.abspath(input_file).replace('\\', '/')
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

        print(f"[AutoMerge] 执行命令: {' '.join(cmd)}")

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
            print(f"[AutoMerge] 合并成功: {output_file} ({file_size/1024/1024:.2f}MB)")
            return True, f"合并成功 ({file_size/1024/1024:.2f}MB)"
        else:
            print(f"[AutoMerge] 合并失败: {result.stderr}")
            return False, f"合并失败: {result.stderr[:100]}"

    except Exception as e:
        print(f"[AutoMerge] 合并异常: {e}")
        # 清理临时文件
        try:
            os.remove(concat_file)
        except:
            pass
        return False, f"合并异常: {e}"


def auto_merge_directory(
    directory: str,
    delete_original: bool = False,
    pattern: str = "*.mp4"
) -> Tuple[int, int, List[str]]:
    """
    自动检测并合并目录中的分割文件

    Args:
        directory: 目录路径
        delete_original: 是否删除原始分割文件
        pattern: 文件匹配模式

    Returns:
        (成功组数, 失败组数, 合并文件列表)
    """
    print(f"[AutoMerge] 扫描目录: {directory}")

    # 检测分割文件组
    file_groups = detect_split_files(directory, pattern)

    if not file_groups:
        print(f"[AutoMerge] 未检测到分割文件")
        return 0, 0, []

    print(f"[AutoMerge] 检测到 {len(file_groups)} 组分割文件")

    success_count = 0
    failed_count = 0
    merged_files = []

    for i, file_group in enumerate(file_groups):
        print(f"\n[AutoMerge] 处理组 {i+1}/{len(file_groups)}: {len(file_group)} 个片段")

        # 确定输出文件名（使用基础文件名）
        # 从第一个文件提取基础名称
        first_file = Path(file_group[0])

        # 移除分割后缀 (_1, _2, ... 或 .mp4.1, .mp4.2, ...)
        base_filename = re.sub(r'(_\d+)\.(mp4|avi|mov)$', r'.\2', first_file.name)
        base_filename = re.sub(r'\.(mp4|avi|mov)\.\d+$', r'.\1', base_filename)

        output_file = os.path.join(directory, base_filename)

        print(f"[AutoMerge] 合并为: {base_filename}")

        # 合并文件
        success, message = merge_videos(file_group, output_file)

        if success:
            success_count += 1
            merged_files.append(output_file)

            # 删除原始分割文件
            if delete_original:
                print(f"[AutoMerge] 删除原始分割文件...")
                for f in file_group:
                    try:
                        os.remove(f)
                        print(f"  已删除: {Path(f).name}")
                    except Exception as e:
                        print(f"  删除失败 {Path(f).name}: {e}")
        else:
            failed_count += 1
            print(f"[AutoMerge] 合并失败: {message}")

    print(f"\n[AutoMerge] 完成: 成功 {success_count} 组, 失败 {failed_count} 组")

    return success_count, failed_count, merged_files


def merge_single_recording(
    base_filename: str,
    directory: str,
    delete_original: bool = False
) -> Tuple[bool, str]:
    """
    合并单个录像的所有分割片段

    Args:
        base_filename: 基础文件名（如 ch1_20260323_232819.mp4）
        directory: 目录路径
        delete_original: 是否删除原始分割文件

    Returns:
        (success, message)
    """
    # 查找所有分割文件
    base_path = Path(directory)
    base_name = Path(base_filename).stem
    base_ext = Path(base_filename).suffix

    # 匹配两种分割命名模式
    pattern1 = f"{base_name}_*{base_ext}"  # ch1_20260323_232819_1.mp4
    pattern2 = f"{base_filename}.*"  # ch1_20260323_232819.mp4.1

    files1 = sorted(base_path.glob(pattern1))
    files2 = sorted(base_path.glob(pattern2))

    segment_files = []

    # 处理模式1: 基础名_数字.扩展名
    if files1:
        for f in files1:
            match = re.match(rf'^{re.escape(base_name)}_(\d+){re.escape(base_ext)}$', f.name)
            if match:
                segment_num = int(match.group(1))
                segment_files.append((segment_num, str(f)))

    # 处理模式2: 基础名.扩展名.数字
    if files2:
        for f in files2:
            match = re.match(rf'^{re.escape(base_name)}{re.escape(base_ext)}\.(\d+)$', f.name)
            if match:
                segment_num = int(match.group(1))
                segment_files.append((segment_num, str(f)))

    if not segment_files:
        return False, "未检测到分割文件"

    # 按段号排序
    sorted_files = sorted(segment_files, key=lambda x: x[0])
    file_list = [f[1] for f in sorted_files]

    # 合并文件
    success, message = merge_videos(file_list, os.path.join(directory, base_filename))

    if success and delete_original:
        # 删除原始分割文件
        print(f"[AutoMerge] 删除原始分割文件...")
        for f in file_list:
            try:
                os.remove(f)
                print(f"  已删除: {Path(f).name}")
            except Exception as e:
                print(f"  删除失败 {Path(f).name}: {e}")

    return success, message


if __name__ == "__main__":
    # 测试自动合并
    test_dir = r"c:\Users\Administrator\WorkBuddy\20260323192840\hikvision_downloader\downloads"
    success, failed, merged = auto_merge_directory(test_dir, delete_original=True)
    print(f"\n测试结果: 成功 {success}, 失败 {failed}")
    print(f"合并文件: {merged}")
