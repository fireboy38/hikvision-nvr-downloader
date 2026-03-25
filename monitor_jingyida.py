"""
监控竞业达下载器是否使用了分段下载

思路：
1. 启动竞业达下载器，让它下载一个长录像（如2小时）
2. 监控下载过程中产生的文件
3. 如果看到多个分段文件，说明它也分段；如果只有一个最终文件，说明它有办法绕过1GB限制
"""

import os
import time
import glob
from datetime import datetime

def monitor_download_folder(folder_path, duration_minutes=2):
    """监控下载文件夹中的文件变化"""
    print(f"监控文件夹: {folder_path}")
    print(f"监控时长: {duration_minutes} 分钟")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    initial_files = set(os.listdir(folder_path)) if os.path.exists(folder_path) else set()
    file_changes = []

    for i in range(duration_minutes * 60):  # 每秒检查一次
        try:
            current_files = set(os.listdir(folder_path))

            # 新增的文件
            new_files = current_files - initial_files
            for f in new_files:
                if not f.startswith('.'):  # 忽略隐藏文件
                    file_path = os.path.join(folder_path, f)
                    size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    file_changes.append({
                        'time': timestamp,
                        'action': 'created',
                        'name': f,
                        'size': size
                    })
                    print(f"[{timestamp}] 新文件: {f} ({size:,} bytes)")

            # 大小变化的文件
            for f in current_files & initial_files:
                file_path = os.path.join(folder_path, f)
                if os.path.exists(file_path):
                    size = os.path.getsize(file_path)
                    # 只监控视频文件
                    if size > 1000000:  # >1MB
                        file_changes.append({
                            'time': datetime.now().strftime('%H:%M:%S'),
                            'action': 'growing',
                            'name': f,
                            'size': size
                        })
                        if i % 10 == 0:  # 每10秒打印一次
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] 文件增长: {f} ({size/1024/1024:.2f} MB)")

            initial_files = current_files
            time.sleep(1)

        except Exception as e:
            print(f"错误: {e}")
            time.sleep(1)

    print("\n" + "=" * 70)
    print("监控结束")
    print("=" * 70)

    # 分析结果
    print("\n文件变化总结:")
    print("-" * 70)

    created_files = [c for c in file_changes if c['action'] == 'created']
    growing_files = set(c['name'] for c in file_changes if c['action'] == 'growing')

    print(f"\n创建的文件数: {len(created_files)}")
    for f in created_files:
        print(f"  - {f['name']} ({f['size']/1024/1024:.2f} MB)")

    print(f"\n增长的文件数: {len(growing_files)}")
    for f in growing_files:
        print(f"  - {f}")

    # 判断是否分段
    if len(created_files) > 1:
        print("\n⚠️  结论: 检测到多个文件，竞业达可能也使用了分段下载！")
    elif len(growing_files) == 1:
        # 检查最终文件大小
        final_file = os.path.join(folder_path, list(growing_files)[0])
        if os.path.exists(final_file):
            final_size = os.path.getsize(final_file)
            if final_size > 1100 * 1024 * 1024:  # >1.1GB
                print(f"\n✅ 结论: 单个文件 {final_size/1024/1024:.2f} MB >1GB，竞业达成功绕过了1GB限制！")
            else:
                print(f"\n❓ 结论: 单个文件 {final_size/1024/1024:.2f} MB，无法确定是否绕过了限制（需要更长测试）")
    else:
        print("\n❓ 结论: 监控期间未检测到明显的下载行为")

if __name__ == "__main__":
    # 竞业达下载器配置的下载路径
    download_path = r"F:\test"  # 从 sys.ini 读取

    print("请先启动竞业达下载器并开始下载一个长录像（建议1小时以上）")
    print("然后按 Enter 键开始监控...")

    input()

    monitor_download_folder(download_path, duration_minutes=5)
