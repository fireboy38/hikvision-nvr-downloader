#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
运行打包后的程序并捕获输出
"""
import subprocess
import os
import sys
import time

print("运行打包后的程序测试")
print("=" * 60)

# 打包后的exe路径
exe_path = r"c:\Users\Administrator\WorkBuddy\20260323192840\dist\四川新数录像批量下载器_完整版_v2.4\四川新数录像批量下载器.exe"

if not os.path.exists(exe_path):
    print(f"[ERROR] 可执行文件不存在: {exe_path}")
    sys.exit(1)

print(f"可执行文件: {exe_path}")
print(f"文件大小: {os.path.getsize(exe_path):,} bytes")

# 运行程序并捕获输出
print("\n启动程序...")
try:
    # 设置环境变量以显示更多日志
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    
    # 运行程序，但只运行几秒钟就关闭
    process = subprocess.Popen(
        [exe_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='ignore',
        env=env
    )
    
    # 等待几秒钟，然后终止
    print("程序已启动，等待5秒...")
    time.sleep(5)
    
    # 终止程序
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
    
    # 获取输出
    stdout, stderr = process.communicate()
    
    print("\n程序输出:")
    print("-" * 40)
    if stdout:
        print("标准输出:")
        print(stdout[:2000])  # 只显示前2000字符
    else:
        print("无标准输出")
    
    print("\n" + "-" * 40)
    if stderr:
        print("标准错误:")
        print(stderr[:2000])  # 只显示前2000字符
    else:
        print("无标准错误")
        
except Exception as e:
    print(f"[ERROR] 运行程序时出错: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成")