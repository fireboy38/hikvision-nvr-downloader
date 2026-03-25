# -*- coding: utf-8 -*-
"""
监控竞业达下载器 - 检测是否使用分段下载

使用说明：
1. 确认竞业达的下载路径（从 sys.ini 读取）
2. 启动竞业达下载器
3. 开始下载一个长录像（建议至少1小时以上）
4. 运行此脚本
5. 观察输出，判断是否使用了分段下载
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
from collections import defaultdict

# 竞业达下载路径（从 sys.ini 读取）
DOWNLOAD_PATH = r"F:\test"

# 监控配置
MONITOR_DURATION_MINUTES = 5
CHECK_INTERVAL_SECONDS = 1

class FileMonitor:
    def __init__(self, download_path):
        self.download_path = download_path
        self.file_history = defaultdict(list)
        self.created_files = set()
        self.start_time = datetime.now()

    def get_files(self):
        if not os.path.exists(self.download_path):
            print(f"[警告] 下载目录不存在: {self.download_path}")
            return []

        files = []
        for f in os.listdir(self.download_path):
            file_path = os.path.join(self.download_path, f)
            if not f.startswith('.') and os.path.isfile(file_path):
                if f.lower().endswith(('.mp4', '.dav', '.264', '.h264', '.avi')):
                    size = os.path.getsize(file_path)
                    mtime = os.path.getmtime(file_path)
                    files.append({
                        'name': f,
                        'path': file_path,
                        'size': size,
                        'mtime': mtime
                    })
        return files

    def monitor(self):
        print("=" * 70)
        print("竞业达下载器 - 分段下载检测")
        print("=" * 70)
        print(f"监控路径: {self.download_path}")
        print(f"监控时长: {MONITOR_DURATION_MINUTES} 分钟")
        print(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        print()

        initial_files = {f['name'] for f in self.get_files()}

        total_seconds = MONITOR_DURATION_MINUTES * 60
        for i in range(total_seconds):
            current_files = self.get_files()

            current_names = {f['name'] for f in current_files}
            new_files = current_names - initial_files

            if new_files:
                timestamp = datetime.now().strftime('%H:%M:%S')
                print(f"\n[{timestamp}] [新文件] 检测到新文件创建:")
                for name in new_files:
                    file_info = next((f for f in current_files if f['name'] == name), None)
                    if file_info:
                        self.created_files.add(name)
                        print(f"  -> {name}")
                        print(f"     大小: {file_info['size']:,} bytes ({file_info['size']/1024/1024:.2f} MB)")

            for file_info in current_files:
                name = file_info['name']
                size = file_info['size']
                timestamp = datetime.now()

                if timestamp.timestamp() - file_info['mtime'] < 60:
                    self.file_history[name].append({
                        'time': timestamp,
                        'size': size
                    })

                    if len(self.file_history[name]) % 10 == 0 and len(self.file_history[name]) > 0:
                        elapsed = (datetime.now() - self.start_time).total_seconds()
                        growth_rate = 0
                        if len(self.file_history[name]) >= 2:
                            prev_size = self.file_history[name][-2]['size']
                            prev_time = self.file_history[name][-2]['time']
                            time_diff = (timestamp - prev_time).total_seconds()
                            if time_diff > 0:
                                growth_rate = (size - prev_size) / time_diff / 1024

                        print(f"[{timestamp.strftime('%H:%M:%S')}] [下载] {name[:30]} "
                              f"-> {size/1024/1024:8.2f} MB  ({growth_rate:.1f} KB/s)")

            if i > 0 and i % 60 == 0:
                elapsed_min = i // 60
                print(f"\n--- 已监控 {elapsed_min} 分钟 ---")
                print(f"当前活跃文件数: {len(current_files)}")
                print(f"创建的总文件数: {len(self.created_files)}")
                for name in self.created_files:
                    file_info = next((f for f in current_files if f['name'] == name), None)
                    if file_info:
                        print(f"  * {name[:40]}: {file_info['size']/1024/1024:.2f} MB")
                print()

            time.sleep(CHECK_INTERVAL_SECONDS)

        print("\n" + "=" * 70)
        print("监控结束")
        print("=" * 70)
        self.analyze()

    def analyze(self):
        print("\n分析报告")
        print("=" * 70)

        final_files = self.get_files()

        print("\n1. 文件数量统计:")
        print(f"   创建的总文件数: {len(self.created_files)}")
        print(f"   最终存在的文件数: {len(final_files)}")

        print("\n2. 文件大小统计:")
        large_files = [f for f in final_files if f['size'] > 100 * 1024 * 1024]
        print(f"   大文件数 (>100MB): {len(large_files)}")

        for f in large_files:
            size_mb = f['size'] / 1024 / 1024
            size_gb = f['size'] / 1024 / 1024 / 1024
            print(f"   * {f['name'][:40]}: {size_mb:.2f} MB ({size_gb:.3f} GB)")

        print("\n3. 分段下载判断:")
        print("-" * 70)

        if len(self.created_files) > 1:
            print("[分段] 检测到多个文件创建")
            print("   结论: 竞业达使用了分段下载策略")
            print()
            print("   详细信息:")
            for i, name in enumerate(sorted(self.created_files), 1):
                file_info = next((f for f in final_files if f['name'] == name), None)
                if file_info:
                    print(f"   文件 {i}: {name}")
                    print(f"           大小: {file_info['size']/1024/1024:.2f} MB")

        elif len(final_files) == 1 and final_files[0]['size'] > 0:
            final_file = final_files[0]
            size_mb = final_file['size'] / 1024 / 1024
            size_gb = final_file['size'] / 1024 / 1024 / 1024

            print(f"[单文件] 只有一个文件: {final_file['name']}")
            print(f"   大小: {size_mb:.2f} MB ({size_gb:.3f} GB)")
            print()

            if size_mb > 1100:
                print("[成功] 文件大小 >1.1GB，竞业达成功绕过了1GB限制！")
            elif size_mb > 900 and size_mb < 1100:
                print("[警告] 文件大小约1GB，可能被V30接口截断")
                print("   建议: 需要更长的监控时间来确认")
            else:
                print("[未知] 文件大小 <1GB，无法判断是否绕过了限制")
                print("   建议: 需要下载更长的录像（至少1小时）才能确认")

        else:
            print("[未知] 监控期间未检测到明显的下载行为")

        print("\n" + "=" * 70)
        self.save_history()

    def save_history(self):
        history = {
            'start_time': self.start_time.isoformat(),
            'end_time': datetime.now().isoformat(),
            'download_path': self.download_path,
            'created_files': list(self.created_files),
            'file_history': {}
        }

        for name, records in self.file_history.items():
            history['file_history'][name] = [
                {'time': r['time'].isoformat(), 'size': r['size']}
                for r in records
            ]

        output_file = f"jingyida_monitor_{self.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            print(f"\n[保存] 监控数据已保存到: {output_file}")
        except Exception as e:
            print(f"\n[错误] 保存监控数据失败: {e}")

def main():
    print("\n竞业达下载器监控工具")
    print("=" * 70)
    print(f"下载路径: {DOWNLOAD_PATH}")
    print()

    if not os.path.exists(DOWNLOAD_PATH):
        print(f"[警告] 下载目录不存在: {DOWNLOAD_PATH}")
        print(f"   请确认竞业达的配置文件中的下载路径是否正确")
        return

    print(f"当前目录中的文件:")
    if os.path.exists(DOWNLOAD_PATH):
        files = [f for f in os.listdir(DOWNLOAD_PATH)
                 if os.path.isfile(os.path.join(DOWNLOAD_PATH, f))]
        if files:
            for f in files[:10]:
                file_path = os.path.join(DOWNLOAD_PATH, f)
                size = os.path.getsize(file_path)
                print(f"  * {f}: {size/1024/1024:.2f} MB")
            if len(files) > 10:
                print(f"  ... 还有 {len(files)-10} 个文件")
        else:
            print("  (空目录)")

    print()
    print("=" * 70)
    print("使用说明:")
    print("1. 启动竞业达下载器")
    print("2. 开始下载一个长录像（建议至少1小时）")
    print("3. 确认竞业达正在下载（文件大小在增长）")
    print("4. 按 Enter 键开始监控")
    print("=" * 70)

    input("\n准备好后按 Enter 键开始...")

    monitor = FileMonitor(DOWNLOAD_PATH)
    monitor.monitor()

if __name__ == "__main__":
    main()
