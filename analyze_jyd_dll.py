"""
分析竞业达的HCNetSDK.dll，看看它导出了哪些函数
"""
import ctypes
from ctypes import wintypes
import sys

def analyze_dll(dll_path):
    """分析DLL的导出函数"""
    try:
        # 加载DLL
        dll = ctypes.CDLL(dll_path)
        print(f"[成功] 加载DLL: {dll_path}")
        print(f"[版本] {sys.getsizeof(dll)} bytes\n")

        # 尝试获取一些关键函数
        key_functions = [
            'NET_DVR_Init',
            'NET_DVR_Login_V30',
            'NET_DVR_GetFileByTime',
            'NET_DVR_GetFileByTime_V40',
            'NET_DVR_GetFileByTime_V50',
            'NET_DVR_StopGetFile',
            'NET_DVR_GetDownloadPos',
            'NET_DVR_FindFile_V30',
            'NET_DVR_FindNextFile_V30',
            'NET_DVR_FindClose_V30',
        ]

        print("[检查] 关键函数导出情况:")
        print("=" * 60)

        for func_name in key_functions:
            try:
                func = getattr(dll, func_name, None)
                if func:
                    print(f"  [存在] {func_name}")
                else:
                    print(f"  [缺失] {func_name}")
            except Exception as e:
                print(f"  [错误] {func_name}: {e}")

        print("\n" + "=" * 60)

        # 尝试检查SDK版本
        try:
            # 调用NET_DVR_GetSDKVersion (如果存在)
            pass
        except:
            pass

        return dll

    except Exception as e:
        print(f"[错误] 加载DLL失败: {e}")
        return None

if __name__ == '__main__':
    dll_path = r"C:\Program Files (x86)\竞业达视频下载器\HCNetSDK.dll"
    analyze_dll(dll_path)
