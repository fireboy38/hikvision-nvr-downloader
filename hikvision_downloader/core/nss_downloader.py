"""
NSS下载器 - 主进程端（x64）

通过启动x86代理进程加载竞业达NSS DLL，实现：
1. NSS登录/登出
2. 获取精确录像大小（bnclient_getstreamsize）
3. 搜索录像段
4. 流式下载录像

架构：
  x64主进程(Python) ← stdin/stdout JSON-RPC → x86代理进程(Python) → apiclient.dll → NVR(NSS)

关键认知：
- NSS服务直接运行在NVR设备上（端口8000）
- NSSDownLoadMgr.dll 是竞业达的中间层，实际由 apiclient.dll 与NVR通信
- apiclient.dll 通过 bnclient_* 系列函数操作NSS服务
- bnclient_getstreamsize() 可以获取精确的录像文件大小（服务端计算）

竞业达NSS DLL函数签名（通过逆向分析）：
- bnclient_login(ip, port, user, pass) -> handle
- bnclient_logout(handle)
- bnclient_getcameras(handle) -> camera_list
- bnclient_halogin(ip, port, user, pass) -> handle  (HA模式登录)
- bnclient_getstreamsize(handle, camera_id, start_time, end_time) -> size
- bnclient_getstream(handle, camera_id, start_time, end_time, callback) -> stream_handle
- bnclient_stopgetstream(stream_handle)
- bnclient_getLastError() -> error_code
"""

import json
import os
import subprocess
import sys
import time
import threading
import logging
import struct
from datetime import datetime
from typing import Tuple, Optional, Callable, List, Dict, Any

logger = logging.getLogger(__name__)

# 竞业达安装路径
JYD_INSTALL_PATH = r"C:\Program Files (x86)\竞业达视频下载器"

# x86 Python 解释器路径（需要安装32位Python）
# 常见位置：
# - C:\Python311-32\python.exe
# - C:\Users\Administrator\AppData\Local\Programs\Python\Python311-32\python.exe
# 环境变量 NSS_PYTHON_X86 可覆盖
X86_PYTHON_PATHS = [
    r"C:\Python311-32\python.exe",
    r"C:\Python310-32\python.exe",
    r"C:\Python39-32\python.exe",
    r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311-32\python.exe",
    r"C:\Users\Administrator\AppData\Local\Programs\Python\Python310-32\python.exe",
    r"C:\Users\Administrator\AppData\Local\Programs\Python\Python39-32\python.exe",
]


def find_x86_python() -> Optional[str]:
    """查找x86 Python解释器"""
    # 优先环境变量
    env_path = os.environ.get("NSS_PYTHON_X86", "")
    if env_path and os.path.isfile(env_path):
        return env_path

    # 搜索常见位置
    for path in X86_PYTHON_PATHS:
        if os.path.isfile(path):
            return path

    # 尝试通过 py -3-32 查找
    try:
        result = subprocess.run(
            ["py", "-3-32", "-c", "import sys; print(sys.executable)"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    return None


class NSSProxy:
    """
    NSS代理客户端（运行在x64主进程中）
    
    通过JSON-RPC over stdin/stdout 与x86代理进程通信。
    代理进程负责加载竞业达的 apiclient.dll 并调用其函数。
    """

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._connected = False
        self._jyd_path = JYD_INSTALL_PATH

    @property
    def is_connected(self) -> bool:
        return self._connected and self._process is not None and self._process.poll() is None

    def _send_request(self, method: str, params: dict = None, timeout: float = 30) -> dict:
        """发送JSON-RPC请求到代理进程"""
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("代理进程未启动或已退出")

        with self._lock:
            self._request_id += 1
            req = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params or {},
            }

            # 发送请求
            request_line = json.dumps(req, ensure_ascii=False) + "\n"
            self._process.stdin.write(request_line.encode("utf-8"))
            self._process.stdin.flush()

            # 等待响应
            deadline = time.time() + timeout
            response_lines = []
            while time.time() < deadline:
                try:
                    line = self._process.stdout.readline()
                    if not line:
                        if self._process.poll() is not None:
                            raise RuntimeError(f"代理进程已退出 (code={self._process.poll()})")
                        time.sleep(0.1)
                        continue
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue
                    response_lines.append(line)
                    try:
                        resp = json.loads(line)
                        if resp.get("id") == self._request_id:
                            if "error" in resp:
                                raise RuntimeError(f"代理错误: {resp['error']}")
                            return resp.get("result", {})
                    except json.JSONDecodeError:
                        pass
                except Exception:
                    time.sleep(0.1)
                    continue

            raise TimeoutError(f"代理进程响应超时 ({timeout}s), 已收到部分: {response_lines}")

    def start(self, jyd_path: str = None) -> Tuple[bool, str]:
        """
        启动x86代理进程
        
        Args:
            jyd_path: 竞业达安装路径（可选，默认使用内置路径）
            
        Returns:
            (success, message)
        """
        if self._connected:
            return True, "已连接"

        if jyd_path:
            self._jyd_path = jyd_path

        # 查找x86 Python
        python_exe = find_x86_python()
        if not python_exe:
            return False, (
                "未找到32位Python解释器。\n"
                "NSS下载需要32位Python来加载竞业达的x86 DLL。\n\n"
                "安装方法：\n"
                "1. 从 python.org 下载 Windows x86 installer (32-bit)\n"
                "2. 安装到默认路径（如 C:\\Python311-32\\）\n"
                "3. 或设置环境变量 NSS_PYTHON_X86 指向32位Python路径"
            )

        # 代理脚本路径
        proxy_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nss_proxy_x86.py")
        if not os.path.isfile(proxy_script):
            return False, f"代理脚本不存在: {proxy_script}"

        logger.info(f"启动NSS代理: python={python_exe}, jyd_path={self._jyd_path}")

        try:
            env = os.environ.copy()
            env["NSS_PROXY_JYD_PATH"] = self._jyd_path

            self._process = subprocess.Popen(
                [python_exe, "-u", proxy_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )

            # 等待代理就绪（代理启动后会发送 "NSS_PROXY_READY" 消息）
            ready_line = self._process.stdout.readline()
            if ready_line and "NSS_PROXY_READY" in ready_line:
                self._connected = True
                return True, f"NSS代理已启动 (PID={self._process.pid})"
            else:
                # 尝试读取错误信息
                stderr_output = ""
                try:
                    stderr_output = self._process.stderr.read(1000)
                except Exception:
                    pass
                self._process.terminate()
                self._process = None
                return False, f"代理启动失败: {ready_line} {stderr_output}"

        except Exception as e:
            return False, f"启动代理异常: {e}"

    def stop(self):
        """停止代理进程"""
        if self._process:
            try:
                self._send_request("shutdown", timeout=5)
            except Exception:
                pass
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        self._connected = False

    def login(self, ip: str, port: int, username: str, password: str) -> Tuple[bool, str, Optional[int]]:
        """
        NSS登录
        
        Returns:
            (success, message, handle)
        """
        try:
            result = self._send_request("login", {
                "ip": ip,
                "port": port,
                "username": username,
                "password": password,
            }, timeout=30)
            if result.get("success"):
                return True, "登录成功", result.get("handle")
            else:
                return False, result.get("error", "登录失败"), None
        except Exception as e:
            return False, f"登录异常: {e}", None

    def logout(self, handle: int) -> Tuple[bool, str]:
        """NSS登出"""
        try:
            result = self._send_request("logout", {"handle": handle}, timeout=10)
            return result.get("success", False), result.get("error", "")
        except Exception as e:
            return False, f"登出异常: {e}"

    def get_file_size(self, handle: int, camera_id: str,
                      start_time: datetime, end_time: datetime) -> Tuple[bool, int, str]:
        """
        获取录像文件大小（精确值，服务端计算）
        
        通过 bnclient_getstreamsize 获取精确字节数。
        
        Returns:
            (success, size_bytes, message)
        """
        try:
            result = self._send_request("get_file_size", {
                "handle": handle,
                "camera_id": camera_id,
                "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            }, timeout=30)
            if result.get("success"):
                return True, result.get("size", 0), "查询成功"
            else:
                return False, 0, result.get("error", "查询失败")
        except Exception as e:
            return False, 0, f"查询异常: {e}"

    def search_records(self, handle: int, camera_id: str,
                       start_time: datetime, end_time: datetime) -> Tuple[bool, List[Dict], str]:
        """
        搜索录像段列表
        
        Returns:
            (success, records, message)
            records: [{start_time, end_time, size}, ...]
        """
        try:
            result = self._send_request("search_records", {
                "handle": handle,
                "camera_id": camera_id,
                "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            }, timeout=60)
            if result.get("success"):
                return True, result.get("records", []), "搜索成功"
            else:
                return False, [], result.get("error", "搜索失败")
        except Exception as e:
            return False, [], f"搜索异常: {e}"

    def download_by_time(self, handle: int, camera_id: str,
                         start_time: datetime, end_time: datetime,
                         save_path: str,
                         progress_callback: Optional[Callable[[int], None]] = None,
                         gui_log_callback: Optional[Callable[[str], None]] = None,
                         timeout: int = 3600) -> Tuple[bool, str]:
        """
        按时间段下载录像
        
        通过流式下载方式获取录像数据，写入本地文件。
        
        Args:
            handle: 登录句柄
            camera_id: 摄像头/通道ID
            start_time: 开始时间
            end_time: 结束时间
            save_path: 保存路径
            progress_callback: 进度回调 (0-100)
            gui_log_callback: GUI日志回调
            timeout: 超时秒数
            
        Returns:
            (success, message)
        """
        try:
            # 创建保存目录
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)

            # 使用流式下载
            result = self._send_request("download_by_time", {
                "handle": handle,
                "camera_id": camera_id,
                "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "save_path": save_path,
            }, timeout=timeout)

            if result.get("success"):
                size_mb = result.get("file_size", 0) / 1024 / 1024
                return True, f"下载成功: {size_mb:.1f}MB"
            else:
                return False, result.get("error", "下载失败")
        except Exception as e:
            return False, f"下载异常: {e}"

    def get_cameras(self, handle: int) -> Tuple[bool, List[Dict], str]:
        """
        获取摄像头/通道列表
        
        Returns:
            (success, cameras, message)
            cameras: [{"id": "1", "name": "摄像头1"}, ...]
        """
        try:
            result = self._send_request("get_cameras", {"handle": handle}, timeout=30)
            if result.get("success"):
                return True, result.get("cameras", []), "获取成功"
            else:
                return False, [], result.get("error", "获取失败")
        except Exception as e:
            return False, [], f"获取异常: {e}"

    def get_last_error(self, handle: int = None) -> Tuple[bool, str]:
        """获取最后错误"""
        try:
            result = self._send_request("get_last_error", {"handle": handle}, timeout=10)
            return True, result.get("error", "无错误")
        except Exception as e:
            return False, str(e)

    def test_connection(self, ip: str, port: int, username: str, password: str) -> Tuple[bool, str]:
        """
        测试NSS连接（登录后立即登出）
        
        Returns:
            (success, message)
        """
        ok, msg, handle = self.login(ip, port, username, password)
        if ok and handle is not None:
            self.logout(handle)
            return True, f"NSS连接成功: {ip}:{port}"
        return False, f"NSS连接失败: {msg}"


# ─────────────────────────────────────────────────────────────────────────────
#  高级接口：集成到现有的下载管理器
# ─────────────────────────────────────────────────────────────────────────────

class NSSDownloader:
    """
    NSS下载器高级接口，提供与 java_downloader 类似的接口
    以便无缝集成到现有的 DownloadManager 中。
    """

    def __init__(self):
        self._proxy = NSSProxy()
        self._handles: Dict[str, int] = {}  # {device_key: handle}
        self._lock = threading.Lock()

    @property
    def is_available(self) -> bool:
        """NSS下载器是否可用"""
        return self._proxy.is_connected

    def ensure_connected(self, jyd_path: str = None) -> Tuple[bool, str]:
        """确保代理已启动"""
        if self._proxy.is_connected:
            return True, "已连接"
        return self._proxy.start(jyd_path)

    def login_device(self, device_key: str, ip: str, port: int,
                     username: str, password: str) -> Tuple[bool, str]:
        """登录NVR设备"""
        with self._lock:
            if device_key in self._handles:
                return True, "已登录"

            ok, msg, handle = self._proxy.login(ip, port, username, password)
            if ok and handle is not None:
                self._handles[device_key] = handle
                return True, f"登录成功: {ip}:{port}"
            return False, f"登录失败: {msg}"

    def logout_device(self, device_key: str):
        """登出设备"""
        with self._lock:
            handle = self._handles.pop(device_key, None)
            if handle is not None:
                self._proxy.logout(handle)

    def get_handle(self, device_key: str) -> Optional[int]:
        """获取设备登录句柄"""
        return self._handles.get(device_key)

    def query_file_size(self, device_key: str, camera_id: str,
                        start_time: datetime, end_time: datetime) -> Tuple[bool, int, str]:
        """
        查询录像精确大小
        
        Returns:
            (success, size_bytes, message)
        """
        handle = self.get_handle(device_key)
        if handle is None:
            return False, 0, "设备未登录"

        return self._proxy.get_file_size(handle, camera_id, start_time, end_time)

    def download(self, device_key: str, camera_id: str,
                 start_time: datetime, end_time: datetime,
                 save_path: str,
                 progress_callback: Optional[Callable[[int], None]] = None,
                 gui_log_callback: Optional[Callable[[str], None]] = None,
                 timeout: int = 3600) -> Tuple[bool, str]:
        """
        下载录像
        
        Returns:
            (success, message)
        """
        handle = self.get_handle(device_key)
        if handle is None:
            return False, "设备未登录"

        return self._proxy.download_by_time(
            handle, camera_id, start_time, end_time,
            save_path, progress_callback, gui_log_callback, timeout
        )

    def stop(self):
        """停止所有连接"""
        with self._lock:
            for device_key, handle in list(self._handles.items()):
                try:
                    self._proxy.logout(handle)
                except Exception:
                    pass
            self._handles.clear()
            self._proxy.stop()

    def test_connection(self, ip: str, port: int,
                        username: str, password: str) -> Tuple[bool, str]:
        """测试NSS连接"""
        return self._proxy.test_connection(ip, port, username, password)


def download_with_nss(
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
    gui_log_callback: Optional[Callable[[str], None]] = None,
    skip_transcode: bool = True,
) -> Tuple[bool, str]:
    """
    使用NSS协议下载录像（公共接口，与 java_downloader.download_with_java 签名兼容）
    
    注意：此函数会创建临时连接，下载完成后自动关闭。
    对于批量下载场景，建议使用 NSSDownloader 类管理连接。
    
    Returns:
        (success, message)
    """
    proxy = NSSProxy()
    device_key = f"{ip}:{port}"

    try:
        # 启动代理
        ok, msg = proxy.start()
        if not ok:
            if gui_log_callback:
                gui_log_callback(f"[NSS] 代理启动失败: {msg}")
            return False, f"NSS代理启动失败: {msg}"

        if gui_log_callback:
            gui_log_callback(f"[NSS] 代理已启动")

        # 登录
        ok, msg, handle = proxy.login(ip, port, username, password)
        if not ok:
            if gui_log_callback:
                gui_log_callback(f"[NSS] 登录失败: {msg}")
            return False, f"NSS登录失败: {msg}"

        if gui_log_callback:
            gui_log_callback(f"[NSS] 登录成功: {ip}:{port}")

        # 下载
        camera_id = str(channel)
        if gui_log_callback:
            channel_info = f"通道{channel}({channel_name})" if channel_name else f"通道{channel}"
            gui_log_callback(f"[NSS] 开始下载 {channel_info} {start_time} ~ {end_time}")

        ok, msg = proxy.download_by_time(
            handle=handle,
            camera_id=camera_id,
            start_time=start_time,
            end_time=end_time,
            save_path=save_path,
            progress_callback=progress_callback,
            gui_log_callback=gui_log_callback,
        )

        # 登出
        proxy.logout(handle)

        return ok, msg

    except Exception as e:
        return False, f"NSS下载异常: {e}"
    finally:
        proxy.stop()


def query_nss_file_size(
    ip: str,
    port: int,
    username: str,
    password: str,
    channel: int,
    start_time: datetime,
    end_time: datetime,
) -> Tuple[bool, int, str]:
    """
    通过NSS查询录像精确大小（公共接口）
    
    Returns:
        (success, size_bytes, message)
    """
    proxy = NSSProxy()

    try:
        ok, msg = proxy.start()
        if not ok:
            return False, 0, f"NSS代理启动失败: {msg}"

        ok, msg, handle = proxy.login(ip, port, username, password)
        if not ok:
            return False, 0, f"NSS登录失败: {msg}"

        ok, size, msg = proxy.get_file_size(handle, str(channel), start_time, end_time)
        proxy.logout(handle)
        return ok, size, msg

    except Exception as e:
        return False, 0, f"NSS查询异常: {e}"
    finally:
        proxy.stop()
