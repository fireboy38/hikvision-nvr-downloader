# ISAPI录像下载模块
# 职责：ISAPI HTTP录像下载、RTSP FFmpeg回退下载、录像大小探测
import os
import signal
import subprocess
import time
import urllib.parse
from typing import Optional, Tuple

import requests


class ISAPIDownloaderMixin:
    """
    提供ISAPI HTTP录像下载和RTSP FFmpeg回退下载能力。
    混入到 HikvisionISAPI 主类使用。
    """

    # ------------------------------------------------------------------ #
    #  录像大小探测
    # ------------------------------------------------------------------ #

    def probe_record_size(
        self,
        channel: int,
        start_time: 'datetime',
        end_time: 'datetime',
        stream_type: int = 1,
        rtsp_port: int = 554,
    ) -> int:
        """
        探测指定通道+时间段的录像文件大小（仅获取 Content-Length，不下载）。

        原理与 download_record_by_time 相同：POST /ISAPI/ContentMgmt/download，
        但收到响应后只读取 Content-Length 头就关闭连接，不消费响应体。

        Returns:
            文件大小（字节），如果探测失败返回 -1。
        """
        stream_code = f"0{stream_type}"
        track_id = f"{channel}{stream_code}"
        start_str = start_time.strftime("%Y%m%dT%H%M%S")
        end_str = end_time.strftime("%Y%m%dT%H%M%S")

        safe_user = urllib.parse.quote(self.username, safe='')
        safe_pass = urllib.parse.quote(self.password, safe='')

        rtsp_uri = (
            f"rtsp://{safe_user}:{safe_pass}@{self.host}:{rtsp_port}"
            f"/Streaming/tracks/{track_id}"
            f"?starttime={start_str}Z&endtime={end_str}Z"
        )

        xml_body = (
            '<?xml version="1.0" encoding="UTF-8"?>\r\n'
            '<downloadRequest version="1.0">\r\n'
            f'  <playbackURI><![CDATA[{rtsp_uri}]]></playbackURI>\r\n'
            '</downloadRequest>\r\n'
        )

        urls_to_try = [
            f"{self.base_url}/ISAPI/ContentMgmt/download",
            f"{self.base_url}/ISAPI/Streaming/channels/download",
        ]

        headers = {
            'Content-Type': 'application/xml',
            'Accept': '*/*',
        }

        for url in urls_to_try:
            try:
                print(f"[PROBE] 尝试: {url}")
                resp = self.session.post(
                    url,
                    data=xml_body.encode('utf-8'),
                    headers=headers,
                    timeout=30,
                    stream=True,
                )
                
                print(f"[PROBE] POST {url} -> HTTP {resp.status_code}")
                print(f"[PROBE] Response headers: {dict(resp.headers)}")

                if resp.status_code != 200:
                    print(f"[PROBE] 非200状态码，响应内容: {resp.text[:500] if resp.text else '(empty)'}")
                    resp.close()
                    continue

                content_length = resp.headers.get('Content-Length')
                if content_length:
                    size = int(content_length)
                    resp.close()
                    print(f"[PROBE] Content-Length = {size} bytes ({size/1024/1024:.2f} MB)")
                    return size if size > 0 else -1
                else:
                    print(f"[PROBE] 无 Content-Length 头，响应头: {list(resp.headers.keys())}")
                    resp.close()
                    # 不返回 -1，继续尝试下一个URL
                    continue

            except Exception as e:
                print(f"[PROBE] 异常: {e}")
                import traceback
                traceback.print_exc()
                continue

        print(f"[PROBE] 所有URL都失败，返回 -1")
        return -1

    # ------------------------------------------------------------------ #
    #  ISAPI HTTP 录像下载
    # ------------------------------------------------------------------ #

    def download_record_by_time(
        self,
        channel: int,
        start_time: 'datetime',
        end_time: 'datetime',
        save_path: str,
        stream_type: int = 1,
        rtsp_port: int = 554,
        progress_callback: Optional[callable] = None,
        log_callback: Optional[callable] = None,
        stop_event: 'threading.Event' = None,
        size_callback: Optional[callable] = None,
    ) -> Tuple[bool, str]:
        """
        通过 ISAPI HTTP 接口下载指定时间段的录像文件。

        原理：向 NVR 发送一个 POST /ISAPI/ContentMgmt/download 请求，
        请求体中包含一个 RTSP 回放 URI（playbackURI），NVR 在服务端
        将 RTSP 流转封装为 PS 流通过 HTTP 响应体流式返回，客户端边
        接收边写入文件。

        优势：
        - 比 RTSP 更稳定（HTTP 长连接，不受 NAT/firewall 影响）
        - 速度通常优于 RTSP（NVR 服务端直接处理，无需实时协商）
        - 不依赖 Java SDK，纯 Python 实现

        回退：如果 ISAPI download 接口不可用，自动回退到 RTSP FFmpeg 方式。

        Args:
            channel:       通道号（1-128）
            start_time:    开始时间
            end_time:      结束时间
            save_path:     保存文件路径
            stream_type:   码流类型 1=主码流, 2=子码流
            rtsp_port:     RTSP端口（默认554）
            progress_callback: 进度回调 (progress_percent: int)
            log_callback:  日志回调 (msg: str)
            stop_event:    停止事件（可选，用于中断下载）
            size_callback: 文件大小回调 (size_bytes: int)

        Returns:
            (success, message)
        """
        def _log(msg: str):
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass
            print(f"[ISAPI下载] {msg}")

        stream_code = f"0{stream_type}"
        track_id = f"{channel}{stream_code}"
        start_str = start_time.strftime("%Y%m%dT%H%M%S")
        end_str = end_time.strftime("%Y%m%dT%H%M%S")

        safe_user = urllib.parse.quote(self.username, safe='')
        safe_pass = urllib.parse.quote(self.password, safe='')

        rtsp_uri = (
            f"rtsp://{safe_user}:{safe_pass}@{self.host}:{rtsp_port}"
            f"/Streaming/tracks/{track_id}"
            f"?starttime={start_str}Z&endtime={end_str}Z"
        )

        duration_sec = (end_time - start_time).total_seconds()
        _log(f"通道{channel} | {start_time.strftime('%H:%M:%S')}~{end_time.strftime('%H:%M:%S')} | 时长{duration_sec:.0f}s")

        xml_body = (
            '<?xml version="1.0" encoding="UTF-8"?>\r\n'
            '<downloadRequest version="1.0">\r\n'
            f'  <playbackURI><![CDATA[{rtsp_uri}]]></playbackURI>\r\n'
            '</downloadRequest>\r\n'
        )

        urls_to_try = [
            f"{self.base_url}/ISAPI/ContentMgmt/download",
            f"{self.base_url}/ISAPI/Streaming/channels/download",
        ]

        headers = {
            'Content-Type': 'application/xml',
            'Accept': '*/*',
        }

        # 确保保存目录存在
        save_dir = os.path.dirname(save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)

        last_error = ""

        for attempt_idx, url in enumerate(urls_to_try):
            if stop_event and stop_event.is_set():
                return False, "用户取消下载"

            _log(f"尝试接口: POST {url.split(self.host)[-1]}")

            try:
                resp = self.session.post(
                    url,
                    data=xml_body.encode('utf-8'),
                    headers=headers,
                    timeout=30,
                    stream=True,
                )

                if resp.status_code == 401:
                    last_error = "认证失败（HTTP 401），请检查用户名密码"
                    _log(f"❌ {last_error}")
                    continue

                if resp.status_code == 404:
                    last_error = f"接口不存在（HTTP 404）: {url}"
                    _log(f"⚠️ {last_error}")
                    continue

                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    _log(f"❌ {last_error}")
                    continue

                # 成功连接，开始流式接收
                content_length = resp.headers.get('Content-Length')
                if content_length:
                    total_bytes = int(content_length)
                    if total_bytes > 0:
                        _log(f"✅ 连接成功，文件大小: {total_bytes / 1024 / 1024:.2f}MB")
                        if size_callback:
                            try:
                                size_callback(total_bytes)
                            except Exception:
                                pass
                    else:
                        total_bytes = None
                        _log(f"✅ 连接成功，流式接收（服务端返回Content-Length=0）")
                else:
                    total_bytes = None
                    _log(f"✅ 连接成功，流式接收（未知大小）")

                # 写入文件
                downloaded_bytes = 0
                chunk_size = 1024 * 256  # 256KB
                t_start = time.monotonic()

                with open(save_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if stop_event and stop_event.is_set():
                            try:
                                os.remove(save_path)
                            except OSError:
                                pass
                            return False, "用户取消下载"

                        if chunk:
                            f.write(chunk)
                            downloaded_bytes += len(chunk)

                            # 计算进度
                            if total_bytes and total_bytes > 0:
                                pct = min(int(downloaded_bytes * 100 / total_bytes), 99)
                            elif duration_sec > 0:
                                elapsed = time.monotonic() - t_start
                                if elapsed > 0:
                                    avg_speed = downloaded_bytes / elapsed
                                    estimated_total = avg_speed * duration_sec
                                    if estimated_total > 0:
                                        pct = min(int(downloaded_bytes * 100 / estimated_total), 99)
                                    else:
                                        pct = min(int(elapsed / duration_sec * 100), 99)
                                else:
                                    pct = 0
                            else:
                                pct = 0

                            if progress_callback:
                                try:
                                    progress_callback(pct)
                                except Exception:
                                    pass

                elapsed_sec = time.monotonic() - t_start
                file_size = os.path.getsize(save_path) if os.path.exists(save_path) else 0

                if file_size == 0:
                    last_error = "下载的文件为空（0字节），可能录像不存在或时间段无效"
                    _log(f"❌ {last_error}")
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                    continue

                if progress_callback:
                    try:
                        progress_callback(100)
                    except Exception:
                        pass

                speed_mb = downloaded_bytes / elapsed_sec / 1024 / 1024 if elapsed_sec > 0 else 0
                _log(f"✅ 下载完成: {file_size / 1024 / 1024:.2f}MB, 耗时{elapsed_sec:.1f}s, 速度{speed_mb:.2f}MB/s")
                return True, f"ISAPI下载完成, {file_size / 1024 / 1024:.2f}MB, 耗时{elapsed_sec:.1f}s"

            except requests.exceptions.Timeout:
                last_error = f"连接超时: {url}"
                _log(f"❌ {last_error}")
                continue
            except requests.exceptions.ConnectionError:
                last_error = f"连接被拒绝: {url}"
                _log(f"❌ {last_error}")
                continue
            except Exception as e:
                last_error = f"下载异常: {str(e)}"
                _log(f"❌ {last_error}")
                _log(f"   详情: {traceback.format_exc()[-300:]}")
                continue

        # 所有 ISAPI 接口都失败，自动回退到 RTSP FFmpeg
        _log(f"⚠️ ISAPI接口全部失败，自动回退到RTSP FFmpeg方式...")
        return self._download_record_by_rtsp_fallback(
            channel=channel,
            start_time=start_time,
            end_time=end_time,
            save_path=save_path,
            stream_type=stream_type,
            rtsp_port=rtsp_port,
            progress_callback=progress_callback,
            log_callback=log_callback,
            stop_event=stop_event,
        )

    # ------------------------------------------------------------------ #
    #  RTSP FFmpeg 回退下载
    # ------------------------------------------------------------------ #

    def _download_record_by_rtsp_fallback(
        self,
        channel: int,
        start_time: 'datetime',
        end_time: 'datetime',
        save_path: str,
        stream_type: int = 1,
        rtsp_port: int = 554,
        progress_callback: Optional[callable] = None,
        log_callback: Optional[callable] = None,
        stop_event: 'threading.Event' = None,
    ) -> Tuple[bool, str]:
        """
        RTSP FFmpeg 回退下载方式。
        当 ISAPI HTTP 接口不可用时，使用 FFmpeg 通过 RTSP 协议下载录像。
        """
        def _log(msg: str):
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass
            print(f"[RTSP回退] {msg}")

        stream_code = "01" if stream_type == 1 else "02"
        track_id = f"{channel}{stream_code}"
        start_str = start_time.strftime("%Y%m%dT%H%M%S")
        end_str = end_time.strftime("%Y%m%dT%H%M%S")

        safe_user = urllib.parse.quote(self.username, safe='')
        safe_pass = urllib.parse.quote(self.password, safe='')

        rtsp_url = (
            f"rtsp://{safe_user}:{safe_pass}@{self.host}:{rtsp_port}"
            f"/Streaming/tracks/{track_id}"
            f"?starttime={start_str}Z&endtime={end_str}Z"
        )

        duration_sec = (end_time - start_time).total_seconds()
        _log(f"RTSP URL: rtsp://{self.username}:****@{self.host}:{rtsp_port}/Streaming/tracks/{track_id}")

        # FFmpeg路径
        ffmpeg_path = r"C:\tools\ffmpeg\bin\ffmpeg.exe"
        if not os.path.exists(ffmpeg_path):
            ffmpeg_path = "ffmpeg"

        cmd_with_audio = [
            ffmpeg_path, "-y",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "64k",
            "-f", "mp4",
            save_path,
        ]
        cmd_no_audio = [
            ffmpeg_path, "-y",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-c:v", "copy",
            "-an",
            "-f", "mp4",
            save_path,
        ]

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0

        for attempt, cmd in enumerate([cmd_with_audio, cmd_no_audio], start=1):
            if stop_event and stop_event.is_set():
                return False, "用户取消下载"

            if attempt == 2:
                _log("音频转AAC失败，改为丢弃音频重试...")

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    startupinfo=startupinfo,
                    creationflags=creation_flags,
                )

                t_start = time.monotonic()
                last_progress = 0

                while proc.poll() is None:
                    if stop_event and stop_event.is_set():
                        try:
                            if os.name == 'nt':
                                proc.send_signal(signal.CTRL_BREAK_EVENT)
                            else:
                                proc.terminate()
                            proc.wait(timeout=3)
                        except Exception:
                            proc.kill()
                        return False, "用户取消下载"

                    elapsed = time.monotonic() - t_start
                    if duration_sec > 0:
                        pct = min(int((elapsed / duration_sec) * 100), 99)
                        if pct != last_progress and progress_callback:
                            progress_callback(pct)
                            last_progress = pct

                    time.sleep(0.5)

                stdout, stderr = proc.communicate(timeout=5)
                return_code = proc.returncode

                if return_code == 0 and os.path.exists(save_path):
                    file_size = os.path.getsize(save_path) / (1024 * 1024)
                    actual_duration = time.monotonic() - t_start
                    if progress_callback:
                        progress_callback(100)
                    audio_note = "（含音频）" if attempt == 1 else "（无音频）"
                    return True, f"RTSP下载完成{audio_note}，{file_size:.2f}MB，耗时{actual_duration:.0f}s"

                error_msg = (stderr.decode('utf-8', errors='ignore') if stderr else "")
                if "404" in error_msg or "Not Found" in error_msg:
                    return False, "录像不存在或时间范围无效"
                elif "401" in error_msg or "Unauthorized" in error_msg:
                    return False, "认证失败，请检查用户名密码"
                elif attempt == 1 and ("codec not currently supported" in error_msg
                                       or "Could not find tag for codec" in error_msg):
                    continue
                else:
                    return False, f"FFmpeg错误: {error_msg[-500:]}"

            except Exception as e:
                return False, f"RTSP下载异常: {str(e)}"

        return False, "所有下载方式均失败"
