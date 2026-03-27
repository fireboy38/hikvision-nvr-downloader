# 海康SDK Python封装模块
# 使用ctypes调用海康官方HCNetSDK.dll
# 基于Java版验证成功的下载逻辑移植

import os
import sys
import ctypes
import time
import threading
from ctypes import *
from typing import List, Dict, Any, Optional, Tuple, Callable
from datetime import datetime

# SDK路径配置
SDK_PATH = r"C:\Users\Administrator\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\CH-HCNetSDKV6.1.6.45_build20210302_win64\库文件"
SDK_COM_PATH = os.path.join(SDK_PATH, "HCNetSDKCom")

# ==================== 常量定义 ====================

# 回放控制命令
NET_DVR_PLAYSTART   = 1   # 开始
NET_DVR_PLAYSTOP    = 2   # 停止
NET_DVR_PLAYGETPOS  = 3   # 获取进度(0~100)

# 流类型
STREAM_MAIN = 0   # 主码流
STREAM_SUB  = 1   # 子码流

# 下载完成标志（进度返回200时表示没有录像）
DOWNLOAD_NO_RECORD = 200


# ==================== 结构体定义 ====================

class NET_DVR_TIME(Structure):
    """时间结构体"""
    _fields_ = [
        ("dwYear",   c_uint32),
        ("dwMonth",  c_uint32),
        ("dwDay",    c_uint32),
        ("dwHour",   c_uint32),
        ("dwMinute", c_uint32),
        ("dwSecond", c_uint32),
    ]

    @classmethod
    def from_datetime(cls, dt: datetime) -> 'NET_DVR_TIME':
        t = cls()
        t.dwYear   = dt.year
        t.dwMonth  = dt.month
        t.dwDay    = dt.day
        t.dwHour   = dt.hour
        t.dwMinute = dt.minute
        t.dwSecond = dt.second
        return t

    def to_datetime(self) -> datetime:
        try:
            return datetime(self.dwYear, self.dwMonth, self.dwDay,
                            self.dwHour, self.dwMinute, self.dwSecond)
        except:
            return datetime.now()


class NET_DVR_DEVICEINFO_V30(Structure):
    """设备信息结构体"""
    _fields_ = [
        ("sSerialNumber",      c_char * 48),
        ("byAlarmInPortNum",   c_byte),
        ("byAlarmOutPortNum",  c_byte),
        ("byDiskNum",          c_byte),
        ("byDVRType",          c_byte),
        ("byChanNum",          c_byte),
        ("byStartChan",        c_byte),
        ("byAudioChanNum",     c_byte),
        ("byIPChanNum",        c_byte),
        ("byZeroChanNum",      c_byte),
        ("byMainProto",        c_byte),
        ("bySubProto",         c_byte),
        ("bySupport",          c_byte),
        ("bySupport1",         c_byte),
        ("bySupport2",         c_byte),
        ("byHighDChanNum",     c_byte),
        ("bySupport3",         c_byte),
        ("byMultiStreamProto", c_byte),
        ("byStartDChan",       c_byte),
        ("byStartDTalkChan",   c_byte),
        ("byHighDChanNum2",    c_byte),
        ("bySupport4",         c_byte),
        ("byLanguageType",     c_byte),
        ("byVoiceInChanNum",   c_byte),
        ("byStartVoiceInChanNo", c_byte),
        ("bySupport5",         c_byte),
        ("bySupport6",         c_byte),
        ("byMirrorChanNum",    c_byte),
        ("wStartMirrorChanNo", c_uint16),
        ("bySupport7",         c_byte),
        ("byRes",              c_byte * 174),
    ]


class NET_DVR_PLAYCOND(Structure):
    """按时间下载条件（V40接口用）"""
    _fields_ = [
        ("dwChannel",            c_uint32),
        ("struStartTime",        NET_DVR_TIME),
        ("struStopTime",         NET_DVR_TIME),
        ("byStreamType",         c_byte),
        ("byDownloadType",       c_byte),
        ("byPlayBackFileType",   c_byte),
        ("byRes",                c_byte * 61),
    ]


# ==================== SDK错误码 ====================

ERROR_CODES = {
    0:  "无错误",
    1:  "用户名或密码错误",
    2:  "权限不足",
    3:  "SDK未初始化",
    4:  "通道号错误",
    5:  "连接数超限",
    6:  "版本不匹配",
    7:  "网络连接失败",
    8:  "网络发送失败",
    9:  "网络接收失败",
    10: "网络接收超时",
    11: "命令顺序错误",
    17: "设备不支持该功能",
    23: "没有录像文件",
    53: "没有找到文件",
}


# ==================== SDK封装类 ====================

class HCNetSDK:
    """海康SDK封装类（线程安全）"""

    def __init__(self):
        self.sdk = None
        self.user_id = -1
        self._lock = threading.Lock()
        self._active_downloads: Dict[int, bool] = {}   # handle -> should_stop
        self._load_sdk()

    # ------------------------------------------------------------------ #
    #  加载与初始化
    # ------------------------------------------------------------------ #

    def _load_sdk(self):
        """加载SDK DLL，自动切换工作目录确保依赖可找到"""
        sdk_dll = os.path.join(SDK_PATH, "HCNetSDK.dll")
        if not os.path.exists(sdk_dll):
            raise FileNotFoundError(f"SDK DLL不存在: {sdk_dll}")

        # 必须先切换工作目录
        os.chdir(SDK_PATH)
        self.sdk = ctypes.CDLL(sdk_dll)
        print(f"[SDK] 已加载: {sdk_dll}")
        self._setup_functions()

    def _setup_functions(self):
        """声明所有SDK函数原型（避免ctypes默认int返回值截断）"""
        sdk = self.sdk

        sdk.NET_DVR_Init.restype = c_bool
        sdk.NET_DVR_Init.argtypes = []

        sdk.NET_DVR_Cleanup.restype = c_bool
        sdk.NET_DVR_Cleanup.argtypes = []

        sdk.NET_DVR_SetConnectTime.restype = c_bool
        sdk.NET_DVR_SetConnectTime.argtypes = [c_uint32, c_uint32]

        sdk.NET_DVR_SetReconnect.restype = c_bool
        sdk.NET_DVR_SetReconnect.argtypes = [c_uint32, c_bool]

        sdk.NET_DVR_GetLastError.restype = c_uint32
        sdk.NET_DVR_GetLastError.argtypes = []

        sdk.NET_DVR_Login_V30.restype = c_long
        sdk.NET_DVR_Login_V30.argtypes = [
            c_char_p, c_uint16, c_char_p, c_char_p,
            POINTER(NET_DVR_DEVICEINFO_V30)
        ]

        sdk.NET_DVR_Logout.restype = c_bool
        sdk.NET_DVR_Logout.argtypes = [c_long]

        # NET_DVR_GetFileByTime — 经Java版验证可用
        sdk.NET_DVR_GetFileByTime.restype = c_long
        sdk.NET_DVR_GetFileByTime.argtypes = [
            c_long,                  # lUserID
            c_long,                  # lChannel
            POINTER(NET_DVR_TIME),   # lpStartTime
            POINTER(NET_DVR_TIME),   # lpStopTime
            c_char_p,                # sSavedFileName
        ]

        # NET_DVR_GetFileByTime_V40 — 备用
        sdk.NET_DVR_GetFileByTime_V40.restype = c_long
        sdk.NET_DVR_GetFileByTime_V40.argtypes = [
            c_long,
            c_char_p,
            POINTER(NET_DVR_PLAYCOND),
        ]

        sdk.NET_DVR_PlayBackControl.restype = c_long
        sdk.NET_DVR_PlayBackControl.argtypes = [
            c_long, c_uint32, c_long, POINTER(c_long)
        ]

        sdk.NET_DVR_StopGetFile.restype = c_bool
        sdk.NET_DVR_StopGetFile.argtypes = [c_long]

        # NET_DVR_GetDownloadState - 获取下载进度状态
        # 返回: 0=成功, -1=失败
        # 通过参数返回: 状态值(1=下载中,2=完成,3=失败), 文件总大小, 已下载大小
        sdk.NET_DVR_GetDownloadState.restype = c_long
        sdk.NET_DVR_GetDownloadState.argtypes = [
            c_long, POINTER(c_long), POINTER(c_long), POINTER(c_long)
        ]

        # NET_DVR_GetDVRConfig - 获取设备配置（硬盘信息等）
        sdk.NET_DVR_GetDVRConfig.restype = c_bool
        sdk.NET_DVR_GetDVRConfig.argtypes = [
            c_long,      # lUserID
            c_uint32,    # dwCommand
            c_long,      # lChannel
            c_void_p,    # lpOutBuffer
            c_uint32,    # dwOutBufferSize
            POINTER(c_uint32)  # lpReturned
        ]

        print("[SDK] 函数原型设置完成")

    def init(self) -> bool:
        """初始化SDK"""
        self.sdk.NET_DVR_SetConnectTime(3000, 3)
        self.sdk.NET_DVR_SetReconnect(10000, True)
        ok = self.sdk.NET_DVR_Init()
        print(f"[SDK] 初始化: {'成功' if ok else '失败'}")
        return ok

    def cleanup(self):
        """清理SDK"""
        try:
            if self.user_id >= 0:
                self.logout()
            self.sdk.NET_DVR_Cleanup()
            print("[SDK] 已清理")
        except Exception as e:
            print(f"[SDK] 清理异常: {e}")

    # ------------------------------------------------------------------ #
    #  登录 / 登出
    # ------------------------------------------------------------------ #

    def login(self, ip: str, port: int, username: str, password: str) -> Tuple[bool, str, Dict]:
        """登录设备，返回 (success, message, device_info)"""
        device_info = NET_DVR_DEVICEINFO_V30()
        user_id = self.sdk.NET_DVR_Login_V30(
            ip.encode('utf-8'), port,
            username.encode('utf-8'), password.encode('utf-8'),
            ctypes.byref(device_info)
        )
        if user_id < 0:
            code = self.sdk.NET_DVR_GetLastError()
            msg = ERROR_CODES.get(code, f"错误码{code}")
            print(f"[SDK] 登录失败: {msg}")
            return False, msg, {}

        self.user_id = user_id

        # 计算总通道数
        analog = device_info.byChanNum
        high   = device_info.byHighDChanNum & 0xFF
        ip_ch  = (high << 8) | (device_info.byIPChanNum & 0xFF)
        total  = analog + ip_ch
        
        # 调试信息：记录原始值
        print(f"[SDK DEBUG] byChanNum={analog}, byHighDChanNum={device_info.byHighDChanNum}, byIPChanNum={device_info.byIPChanNum}")
        print(f"[SDK DEBUG] high={high}, ip_ch={ip_ch}, total={total}")
        
        if total <= 0 or total > 1000:
            print(f"[SDK DEBUG] total={total} out of range, using default 128")
            total = 128

        dev = {
            'serial':       device_info.sSerialNumber.decode('utf-8', errors='ignore').rstrip('\x00'),
            'type':         device_info.byDVRType,
            'analog_ch':    analog,
            'ip_ch':        ip_ch,
            'total_ch':     total,
            'disk_num':     device_info.byDiskNum,
            'start_chan':   device_info.byStartChan,
            'start_dchan':  device_info.byStartDChan,
        }
        print(f"[SDK] 登录成功: {ip}:{port}  序列号:{dev['serial']}  通道:{total}")
        return True, "登录成功", dev

    def get_hdd_info(self) -> List[Dict]:
        """获取硬盘信息 - 使用ISAPI接口"""
        hdd_list = []
        try:
            import requests
            from requests.auth import HTTPDigestAuth
            
            # 使用ISAPI获取硬盘信息
            # 需要通过设备IP和HTTP端口访问
            # 这里返回空列表，让上层使用ISAPI接口获取
            print(f"[SDK] 硬盘信息请通过ISAPI接口获取")
            
        except Exception as e:
            print(f"[SDK] 获取硬盘信息异常: {e}")

        return hdd_list

    def logout(self) -> bool:
        """登出"""
        if self.user_id < 0:
            return True
        ok = self.sdk.NET_DVR_Logout(self.user_id)
        self.user_id = -1
        print("[SDK] 已登出")
        return ok

    # ------------------------------------------------------------------ #
    #  错误信息
    # ------------------------------------------------------------------ #

    def get_last_error(self) -> Tuple[int, str]:
        code = self.sdk.NET_DVR_GetLastError()
        return code, ERROR_CODES.get(code, f"错误码{code}")

    # ------------------------------------------------------------------ #
    #  录像下载
    # ------------------------------------------------------------------ #

    def download_by_time(
        self,
        channel:           int,
        start_time:        datetime,
        end_time:          datetime,
        save_path:         str,
        progress_callback: Optional[Callable[[int], None]] = None,
        timeout_sec:       int = 300,
    ) -> Tuple[bool, str]:
        """
        按时间段下载录像（与Java版逻辑一致）

        Args:
            channel:           通道号（从1开始）
            start_time:        开始时间
            end_time:          结束时间
            save_path:         本地保存路径
            progress_callback: 进度回调 callback(progress: int)，0~100
            timeout_sec:       超时秒数，默认300秒

        Returns:
            (success, message)
        """
        if self.user_id < 0:
            return False, "未登录设备"

        # 确保保存目录存在
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        t_start = NET_DVR_TIME.from_datetime(start_time)
        t_end   = NET_DVR_TIME.from_datetime(end_time)

        print(f"[SDK] 开始下载 通道{channel}: "
              f"{start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ "
              f"{end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[SDK] 保存路径: {save_path}")

        # 优先用 NET_DVR_GetFileByTime（Java版验证可用）
        dl_handle = self.sdk.NET_DVR_GetFileByTime(
            self.user_id,
            channel,
            ctypes.byref(t_start),
            ctypes.byref(t_end),
            save_path.encode('gbk'),   # 中文路径用GBK
        )

        if dl_handle < 0:
            code, msg = self.get_last_error()
            print(f"[SDK] GetFileByTime失败({code}): {msg}，尝试V40...")

            # 回退到 V40
            play_cond = NET_DVR_PLAYCOND()
            play_cond.dwChannel   = channel
            play_cond.struStartTime = t_start
            play_cond.struStopTime  = t_end
            play_cond.byStreamType  = STREAM_MAIN
            play_cond.byDownloadType = 1

            dl_handle = self.sdk.NET_DVR_GetFileByTime_V40(
                self.user_id,
                save_path.encode('gbk'),
                ctypes.byref(play_cond),
            )

            if dl_handle < 0:
                code, msg = self.get_last_error()
                print(f"[SDK] GetFileByTime_V40也失败({code}): {msg}")
                return False, msg

        print(f"[SDK] 下载句柄: {dl_handle}")

        # 注册活跃下载
        with self._lock:
            self._active_downloads[dl_handle] = False

        try:
            # 发送 PLAYSTART 命令
            pos_ref = c_long(0)
            start_result = self.sdk.NET_DVR_PlayBackControl(
                dl_handle, NET_DVR_PLAYSTART, 0, ctypes.byref(pos_ref)
            )
            if start_result < 0:
                code, msg = self.get_last_error()
                print(f"[SDK] 发送PLAYSTART失败({code}): {msg}")
                self.sdk.NET_DVR_StopGetFile(dl_handle)
                return False, msg

            print("[SDK] 已发送PLAYSTART，开始等待进度...")

            # 轮询进度
            deadline = time.time() + timeout_sec
            last_progress = -1
            stable_file_size = 0  # 稳定的文件大小
            file_size_count = 0   # 文件大小保持一致的次数
            download_done = False  # 下载完成标志

            # 用于NET_DVR_GetDownloadState的输出参数
            state_ref    = c_long(0)   # 1=下载中, 2=完成, 3=失败
            size_total   = c_long(0)   # 文件总大小
            size_current = c_long(0)   # 已下载大小
            pos_ref      = c_long(0)   # 进度百分比

            while True:
                time.sleep(1)

                # 检查是否被外部取消
                with self._lock:
                    if self._active_downloads.get(dl_handle, False):
                        print("[SDK] 下载被取消")
                        break

                if download_done:
                    print("[SDK] 下载已完成，退出循环")
                    break

                progress = -1

                # 方法1: 尝试NET_DVR_GetDownloadState
                result = self.sdk.NET_DVR_GetDownloadState(
                    dl_handle,
                    ctypes.byref(state_ref),
                    ctypes.byref(size_total),
                    ctypes.byref(size_current)
                )

                if result >= 0:
                    state = state_ref.value
                    if state == 2:  # SDK报告下载完成
                        print("[SDK] SDK报告下载完成，等待文件写入...")
                        time.sleep(3)
                        if os.path.exists(save_path):
                            final_size = os.path.getsize(save_path)
                            print(f"[SDK] 最终文件大小: {final_size} 字节")
                        progress = 100
                        download_done = True
                    elif state == 3:  # 下载失败
                        code, msg = self.get_last_error()
                        print(f"[SDK] 下载失败({code}): {msg}")
                        self.sdk.NET_DVR_StopGetFile(dl_handle)
                        return False, f"下载失败: {msg}"
                    elif state == 1:  # 下载中
                        if size_total.value > 0:
                            progress = int(size_current.value * 100 / size_total.value)

                # 方法2: 尝试PLAYGETPOS
                if progress < 0:
                    play_result = self.sdk.NET_DVR_PlayBackControl(
                        dl_handle, NET_DVR_PLAYGETPOS, 0, ctypes.byref(pos_ref)
                    )
                    if play_result >= 0:
                        pos_val = pos_ref.value
                        # 过滤掉状态码50（正在下载），只接受0-100的真实百分比
                        if 0 <= pos_val <= 100:
                            progress = pos_val

                # 方法3: 用文件大小估算
                if progress < 0:
                    if os.path.exists(save_path):
                        current_size = os.path.getsize(save_path)
                        if current_size > 0:
                            # 如果文件大小跟上一次一样，说明可能下载完成或暂停
                            if current_size == stable_file_size:
                                file_size_count += 1
                            else:
                                stable_file_size = current_size
                                file_size_count = 0
                            
                            # 如果连续3次文件大小不变，认为下载完成
                            if file_size_count >= 3:
                                print(f"[SDK] 文件大小稳定({stable_file_size}字节)超过3次，认为下载完成")
                                progress = 100
                                download_done = True
                            else:
                                # 估算进度：假设最大为当前大小的2倍
                                progress = min(int(current_size * 100 / (stable_file_size * 2)), 99)

                # 回调进度
                if progress != last_progress and progress >= 0:
                    print(f"[SDK] >>> 进度更新: {progress}%")
                    last_progress = progress
                    if progress_callback and 0 <= progress <= 100:
                        try:
                            progress_callback(progress)
                        except Exception:
                            pass

                if progress >= 100:
                    print("[SDK] 下载完成!")
                    break

                if time.time() > deadline:
                    print(f"[SDK] 下载超时")
                    return False, "下载超时"

            # 验证文件
            if os.path.exists(save_path):
                size = os.path.getsize(save_path)
                print(f"[SDK] 文件大小: {size / 1024 / 1024:.2f} MB")
                if size > 0:
                    return True, "下载成功"
                else:
                    return False, "文件为空（可能该时段无录像）"
            else:
                return False, "文件未生成"

        finally:
            self.sdk.NET_DVR_StopGetFile(dl_handle)
            with self._lock:
                self._active_downloads.pop(dl_handle, None)

    def cancel_download(self, dl_handle: int):
        """取消指定下载句柄"""
        with self._lock:
            if dl_handle in self._active_downloads:
                self._active_downloads[dl_handle] = True

    def stop_all_downloads(self):
        """取消所有下载"""
        with self._lock:
            for handle in self._active_downloads:
                self._active_downloads[handle] = True

    # ------------------------------------------------------------------ #
    #  通道信息（通过ISAPI补名称）
    # ------------------------------------------------------------------ #

    def get_channels_with_names(
        self,
        total_ch:   int,
        start_chan: int = 1,
        nvr_ip:     str = "",
        nvr_port:   int = 80,
        username:   str = "admin",
        password:   str = "admin",
    ) -> List[Dict[str, Any]]:
        """
        获取通道列表：用ISAPI补充名称和在线状态，失败则用默认名称

        Args:
            total_ch:   总通道数（SDK返回值，可能不准确；ISAPI优先）
            start_chan: 起始通道号（SDK返回）
            nvr_ip:     NVR IP（用于ISAPI请求）
            nvr_port:   HTTP端口
            username / password: 认证信息

        Returns:
            通道列表 [{'id': '1', 'name': '...', 'no': 1, 'online': True/False}, ...]
        """
        # 先尝试从ISAPI获取通道（含名称+在线状态）
        # channel_info: {ch_no: {'name': str, 'online': bool, 'status': str}}
        channel_info: Dict[int, Dict] = {}
        if nvr_ip:
            try:
                channel_info = _fetch_channel_info_isapi(nvr_ip, nvr_port, username, password)
                print(f"[ISAPI] 获取到 {len(channel_info)} 个通道（含在线状态）")
                online_count = sum(1 for c in channel_info.values() if c.get('online', False))
                print(f"[ISAPI] 在线: {online_count}, 离线/未知: {len(channel_info)-online_count}")
            except Exception as e:
                print(f"[ISAPI] 获取通道信息失败: {e}")

        # 如果ISAPI返回了通道，以ISAPI的通道范围为准（比SDK的total_ch更准确）
        if channel_info:
            ch_start = min(channel_info.keys())
            ch_end   = max(channel_info.keys())
            print(f"[ISAPI] 通道范围: {ch_start} - {ch_end} (共{len(channel_info)}个)")
            channels = []
            for ch_no in sorted(channel_info.keys()):
                info = channel_info[ch_no]
                channels.append({
                    'id':     str(ch_no),
                    'name':   info['name'],
                    'no':     ch_no,
                    'online': info.get('online', True),   # 默认True兼容旧逻辑
                    'status': info.get('status', 'unknown'),
                })
            return channels

        # ISAPI不可用时，退回 SDK 信息（无在线状态）
        channels = []
        for i in range(total_ch):
            ch_no = start_chan + i
            channels.append({
                'id':     str(ch_no),
                'name':   f"通道{ch_no}",
                'no':     ch_no,
                'online': True,    # 无法判断，默认在线
                'status': 'unknown',
            })
        return channels


# ==================== ISAPI辅助：获取通道信息（含在线状态） ====================

def _fetch_channel_info_isapi(
    host: str, port: int, username: str, password: str
) -> Dict[int, Dict]:
    """
    通过ISAPI获取通道完整信息（名称 + 在线状态）
    返回 {channel_no: {'name': str, 'online': bool, 'status': str}} 映射

    兼容两种固件：
    - 老固件：InputProxyChannel 内含 <connectionStatus>online/offline</connectionStatus>
    - 新固件：无此字段，需调用 /channels/status 接口（含 <online>true/false</online>）
    备用：Streaming/channels（无在线状态）
    """
    import requests
    import xml.etree.ElementTree as ET
    from requests.auth import HTTPDigestAuth

    session = requests.Session()
    session.headers.update({'Accept': '*/*'})
    # 使用 Digest Auth（新固件强制要求；老固件也兼容）
    session.auth = HTTPDigestAuth(username, password)

    channel_info: Dict[int, Dict] = {}

    # ── 方式1: InputProxy channels（名称 + 可能含 connectionStatus）──────
    url = f"http://{host}:{port}/ISAPI/ContentMgmt/InputProxy/channels"
    has_conn_status = False
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)

            ns = None
            for ns_opt in [
                'http://www.isapi.org/ver20/XMLSchema',
                'http://www.hikvision.com/ver20/XMLSchema',
            ]:
                if root.find(f'.//{{{ns_opt}}}InputProxyChannel') is not None:
                    ns = ns_opt
                    print(f"[ISAPI] 检测到命名空间: {ns}")
                    break

            def _parse_proxy_ch(ch_elem, pfx=''):
                nonlocal has_conn_status

                def f(tag): return ch_elem.find(f'{pfx}{tag}')
                id_el   = f('id')
                name_el = f('name')
                stat_el = f('connectionStatus')
                if id_el is None:
                    return
                try:
                    no   = int(id_el.text)
                    name = (name_el.text or f"通道{no}").strip() if name_el is not None else f"通道{no}"
                    if stat_el is not None:
                        # 老固件：直接包含状态
                        has_conn_status = True
                        status = (stat_el.text or 'unknown').strip().lower()
                        online = (status == 'online')
                    else:
                        # 新固件：暂时占位，后续用 /channels/status 覆盖
                        status = 'unknown'
                        online = True
                    channel_info[no] = {'name': name, 'online': online, 'status': status}
                except Exception:
                    pass

            if ns is None:
                print("[ISAPI] 未检测到标准命名空间，尝试无命名空间解析")
                for ch in root.findall('.//InputProxyChannel'):
                    _parse_proxy_ch(ch, '')
            else:
                for ch in root.findall(f'.//{{{ns}}}InputProxyChannel'):
                    _parse_proxy_ch(ch, f'{{{ns}}}')

            print(f"[ISAPI] InputProxy获取到 {len(channel_info)} 个通道")

            # 如果通道配置里没有 connectionStatus，调用专用 status 接口补充在线状态
            if channel_info and not has_conn_status:
                _enrich_channel_status(session, host, port, channel_info)

    except Exception as e:
        print(f"[ISAPI] InputProxy请求失败: {e}")

    # ── 方式2: Streaming/channels（备用，无在线状态）───────────────────────
    if not channel_info:
        url2 = f"http://{host}:{port}/ISAPI/Streaming/channels"
        try:
            resp2 = session.get(url2, timeout=10)
            if resp2.status_code == 200:
                root2 = ET.fromstring(resp2.text)

                ns2 = None
                for ns_opt in [
                    'http://www.isapi.org/ver20/XMLSchema',
                    'http://www.hikvision.com/ver20/XMLSchema',
                ]:
                    if root2.find(f'.//{{{ns_opt}}}StreamingChannel') is not None:
                        ns2 = ns_opt
                        print(f"[ISAPI] Streaming检测到命名空间: {ns2}")
                        break

                seen: set = set()

                def _parse_streaming_ch(ch_elem, pfx=''):
                    def f(tag): return ch_elem.find(f'{pfx}{tag}')
                    id_el   = f('id')
                    name_el = f('channelName')
                    if id_el is None:
                        return
                    try:
                        raw_id = int(id_el.text)
                        ch_no  = raw_id // 100   # 101->1, 201->2
                        if ch_no > 0 and ch_no not in seen:
                            seen.add(ch_no)
                            name = (name_el.text or f"通道{ch_no}").strip() if name_el is not None else f"通道{ch_no}"
                            channel_info[ch_no] = {'name': name, 'online': True, 'status': 'unknown'}
                    except Exception:
                        pass

                if ns2 is None:
                    print("[ISAPI] Streaming未检测到标准命名空间，尝试无命名空间解析")
                    for ch in root2.findall('.//StreamingChannel'):
                        _parse_streaming_ch(ch, '')
                else:
                    for ch in root2.findall(f'.//{{{ns2}}}StreamingChannel'):
                        _parse_streaming_ch(ch, f'{{{ns2}}}')

                print(f"[ISAPI] Streaming获取到 {len(channel_info)} 个通道")
        except Exception as e:
            print(f"[ISAPI] Streaming/channels请求失败: {e}")

    return channel_info


def _enrich_channel_status(
    session, host: str, port: int, channels: Dict[int, Dict]
) -> None:
    """
    从 /ISAPI/ContentMgmt/InputProxy/channels/status 补充在线状态
    新固件使用 <online>true/false</online> 字段
    直接修改传入的 channels 字典
    """
    import xml.etree.ElementTree as ET
    try:
        url  = f"http://{host}:{port}/ISAPI/ContentMgmt/InputProxy/channels/status"
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return

        root = ET.fromstring(resp.text)
        ns = None
        for ns_opt in [
            'http://www.isapi.org/ver20/XMLSchema',
            'http://www.hikvision.com/ver20/XMLSchema',
        ]:
            if root.find(f'.//{{{ns_opt}}}InputProxyChannelStatus') is not None:
                ns = ns_opt
                break

        def _parse_status(ch_elem, pfx=''):
            def f(tag): return ch_elem.find(f'{pfx}{tag}')
            id_el     = f('id')
            online_el = f('online')
            detect_el = f('chanDetectResult')
            if id_el is None:
                return
            try:
                no = int(id_el.text)
                if no not in channels:
                    return
                if online_el is not None:
                    online = (online_el.text or '').strip().lower() == 'true'
                    channels[no]['online'] = online
                    channels[no]['status'] = 'online' if online else 'offline'
                elif detect_el is not None:
                    detect = (detect_el.text or '').strip().lower()
                    online = (detect == 'connect')
                    channels[no]['online'] = online
                    channels[no]['status'] = detect
            except Exception:
                pass

        tag = 'InputProxyChannelStatus'
        if ns is None:
            for ch in root.findall(f'.//{tag}'):
                _parse_status(ch, '')
        else:
            for ch in root.findall(f'.//{{{ns}}}{tag}'):
                _parse_status(ch, f'{{{ns}}}')

        online_cnt = sum(1 for c in channels.values() if c['online'])
        print(f"[ISAPI] 通道状态（status接口）: {online_cnt}在线 / {len(channels)-online_cnt}离线")

    except Exception as e:
        print(f"[ISAPI] channels/status 接口异常: {e}")




def _fetch_channel_names_isapi(
    host: str, port: int, username: str, password: str
) -> Dict[int, str]:
    """
    向下兼容旧接口，只返回名称映射
    """
    info = _fetch_channel_info_isapi(host, port, username, password)
    return {no: d['name'] for no, d in info.items()}


# ==================== 单例 ====================

_sdk_instance: Optional[HCNetSDK] = None

def get_sdk() -> HCNetSDK:
    """获取全局SDK单例（懒加载）"""
    global _sdk_instance
    if _sdk_instance is None:
        _sdk_instance = HCNetSDK()
    return _sdk_instance


# ==================== 快速测试 ====================

if __name__ == "__main__":
    from datetime import timedelta

    sdk = HCNetSDK()
    if not sdk.init():
        print("SDK初始化失败")
        sys.exit(1)

    ok, msg, dev = sdk.login("10.4.130.245", 8000, "admin", "a1111111")
    if not ok:
        print(f"登录失败: {msg}")
        sdk.cleanup()
        sys.exit(1)

    print(f"设备信息: {dev}")

    # 获取通道（带ISAPI名称）
    channels = sdk.get_channels_with_names(
        total_ch=dev['total_ch'],
        start_chan=1,
        nvr_ip="10.4.130.245",
        nvr_port=80,
        username="admin",
        password="a1111111",
    )
    print(f"通道总数: {len(channels)}")
    for ch in channels[:5]:
        print(f"  {ch}")

    # 下载测试：下载最近1分钟
    now = datetime.now()
    start = now - timedelta(minutes=1)
    save = os.path.join(
        r"C:\Users\Administrator\WorkBuddy\20260323192840\hikvision_downloader\downloads",
        f"test_ch1_{now.strftime('%Y%m%d_%H%M%S')}.mp4"
    )

    success, msg = sdk.download_by_time(
        channel=1,
        start_time=start,
        end_time=now,
        save_path=save,
        progress_callback=lambda p: print(f"  进度: {p}%"),
        timeout_sec=120,
    )
    print(f"下载结果: {'成功' if success else '失败'} - {msg}")
    if success:
        print(f"文件: {save}")

    sdk.cleanup()
