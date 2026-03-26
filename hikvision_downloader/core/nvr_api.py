# 海康NVR辅助接口模块
# 职责：通过ISAPI HTTP接口获取设备/通道信息
# 录像下载由 hcnetsdk.py 负责
import base64
import json
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPDigestAuth, HTTPBasicAuth


class HikvisionISAPI:
    """海康ISAPI接口（仅用于获取设备/通道信息）"""

    def __init__(self, host: str, port: int = 80,
                 username: str = "admin", password: str = "admin"):
        self.host     = host
        self.port     = port
        self.username = username
        self.password = password
        self.base_url = f"http://{host}:{port}"

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'HikvisionClient/1.0',
            'Accept': '*/*',
        })
        # 优先尝试 Digest Auth（新固件强制要求），会自动协商
        # 若设备仍支持 Basic，requests.auth.HTTPDigestAuth 也能正常工作
        self.session.auth = HTTPDigestAuth(username, password)

    # ------------------------------------------------------------------ #
    #  连接测试
    # ------------------------------------------------------------------ #

    def test_connection(self) -> Tuple[bool, str]:
        """测试ISAPI连接，返回 (success, device_model)"""
        try:
            url  = f"{self.base_url}/ISAPI/System/deviceInfo"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                model = self._parse_xml_text(resp.text, 'model')
                return True, model or "NVR设备"
            elif resp.status_code == 401:
                return False, "认证失败，请检查用户名/密码"
            else:
                return False, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return False, "连接超时"
        except requests.exceptions.ConnectionError:
            return False, "无法连接设备"
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------ #
    #  通道名称
    # ------------------------------------------------------------------ #

    def get_channel_names(self) -> Dict[int, str]:
        """
        获取所有通道名称映射 {channel_no: name}
        优先用 InputProxy，失败用 Streaming/channels
        """
        # 方式1：InputProxy（数字通道）
        names = self._get_names_from_input_proxy()
        if names:
            return names

        # 方式2：Streaming/channels
        names = self._get_names_from_streaming()
        return names

    def _get_names_from_input_proxy(self) -> Dict[int, str]:
        """从 /ISAPI/ContentMgmt/InputProxy/channels 获取名称（仅名称）"""
        result = self._get_channels_from_input_proxy()
        return {no: info['name'] for no, info in result.items()}

    def _get_channels_from_input_proxy(self) -> Dict[int, Dict]:
        """
        从 /ISAPI/ContentMgmt/InputProxy/channels 获取通道完整信息
        返回 {channel_no: {'name': str, 'online': bool, 'status': str}} 映射

        在线状态兼容两种固件：
        - 老固件: InputProxyChannel 内含 <connectionStatus>online/offline</connectionStatus>
        - 新固件: 无此字段，需另调 /channels/status 接口（含 <online>true/false</online>）
        """
        channels: Dict[int, Dict] = {}
        try:
            url  = f"{self.base_url}/ISAPI/ContentMgmt/InputProxy/channels"
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return channels

            root = ET.fromstring(resp.text)
            # 自动检测命名空间
            ns = None
            for ns_opt in [
                'http://www.isapi.org/ver20/XMLSchema',
                'http://www.hikvision.com/ver20/XMLSchema',
            ]:
                if root.find(f'.//{{{ns_opt}}}InputProxyChannel') is not None:
                    ns = ns_opt
                    break

            has_connection_status = False  # 记录是否包含 connectionStatus 字段

            def _parse_ch(ch_elem, ns_prefix=''):
                nonlocal has_connection_status

                def _find(tag):
                    return ch_elem.find(f'{ns_prefix}{tag}') if ns_prefix else ch_elem.find(tag)

                def _find_in_parent(elem, tag):
                    """在父元素中查找，支持嵌套"""
                    if ns_prefix:
                        return elem.find(f'{ns_prefix}{tag}')
                    else:
                        return elem.find(tag)

                id_el     = _find('id')
                name_el   = _find('name')
                status_el = _find('connectionStatus')
                if id_el is None:
                    return
                try:
                    no   = int(id_el.text)
                    name = (name_el.text or f"通道{no}").strip() if name_el is not None else f"通道{no}"

                    if status_el is not None:
                        # 老固件：connectionStatus 在通道配置中直接包含
                        has_connection_status = True
                        status = (status_el.text or 'unknown').strip().lower()
                        online = (status == 'online')
                    else:
                        # 新固件：暂时标为 unknown，稍后通过 /channels/status 补充
                        status = 'unknown'
                        online = True   # 占位，会被后续覆盖

                    # 初始化通道信息
                    ch_info = {'name': name, 'online': online, 'status': status}
                    
                    # 获取源输入端口信息（IP地址等）
                    source_input = _find('sourceInputPortDescriptor')
                    if source_input is not None:
                        # IP地址
                        ip_el = source_input.find(f'{ns_prefix}ipAddress') if ns_prefix else source_input.find('ipAddress')
                        if ip_el is not None and ip_el.text:
                            ch_info['ip'] = ip_el.text
                        
                        # 管理端口
                        mgmt_port_el = source_input.find(f'{ns_prefix}managePortNo') if ns_prefix else source_input.find('managePortNo')
                        if mgmt_port_el is not None and mgmt_port_el.text:
                            ch_info['mgmt_port'] = mgmt_port_el.text
                        
                        # 协议
                        protocol_el = source_input.find(f'{ns_prefix}srcInputPortProtocol') if ns_prefix else source_input.find('srcInputPortProtocol')
                        if protocol_el is not None and protocol_el.text:
                            ch_info['protocol'] = protocol_el.text
                        
                        # 用户名
                        user_el = source_input.find(f'{ns_prefix}userName') if ns_prefix else source_input.find('userName')
                        if user_el is not None and user_el.text:
                            ch_info['username'] = user_el.text
                    
                    # 获取OSD信息
                    osd = _find('OSD')
                    if osd is not None:
                        osd_info = {}
                        
                        # OSD名称
                        osd_name_el = osd.find(f'{ns_prefix}name') if ns_prefix else osd.find('name')
                        if osd_name_el is not None and osd_name_el.text:
                            osd_info['name'] = osd_name_el.text
                        
                        # OSD是否启用
                        osd_enabled_el = osd.find(f'{ns_prefix}enabled') if ns_prefix else osd.find('enabled')
                        if osd_enabled_el is not None and osd_enabled_el.text:
                            osd_info['enabled'] = osd_enabled_el.text == 'true'
                        
                        # OSD位置
                        osd_pos_el = osd.find(f'{ns_prefix}position') if ns_prefix else osd.find('position')
                        if osd_pos_el is not None:
                            pos_type_el = osd_pos_el.find(f'{ns_prefix}positionType') if ns_prefix else osd_pos_el.find('positionType')
                            if pos_type_el is not None and pos_type_el.text:
                                osd_info['position_type'] = pos_type_el.text
                        
                        if osd_info:
                            ch_info['osd'] = osd_info
                    
                    channels[no] = ch_info
                except Exception:
                    pass

            if ns is None:
                for ch in root.findall('.//InputProxyChannel'):
                    _parse_ch(ch, '')
            else:
                for ch in root.findall(f'.//{{{ns}}}InputProxyChannel'):
                    _parse_ch(ch, f'{{{ns}}}')

            # 如果通道配置里没有 connectionStatus，尝试专用 status 接口
            if channels and not has_connection_status:
                self._enrich_status_from_status_api(channels)

        except Exception as e:
            print(f"[ISAPI] InputProxy异常: {e}")
        return channels

    def _enrich_status_from_status_api(self, channels: Dict[int, Dict]) -> None:
        """
        从 /ISAPI/ContentMgmt/InputProxy/channels/status 补充在线状态
        新固件使用 <online>true/false</online> 字段
        结果直接写回传入的 channels 字典
        """
        try:
            url  = f"{self.base_url}/ISAPI/ContentMgmt/InputProxy/channels/status"
            resp = self.session.get(url, timeout=15)
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

            def _parse_status(ch_elem, ns_prefix=''):
                def _find(tag):
                    return ch_elem.find(f'{ns_prefix}{tag}') if ns_prefix else ch_elem.find(tag)

                id_el     = _find('id')
                online_el = _find('online')
                detect_el = _find('chanDetectResult')  # 'connect' | 'disconnect' | ...
                if id_el is None:
                    return
                try:
                    no = int(id_el.text)
                    if no not in channels:
                        return

                    # 优先用 <online> 字段
                    if online_el is not None:
                        online = (online_el.text or '').strip().lower() == 'true'
                        channels[no]['online'] = online
                        channels[no]['status'] = 'online' if online else 'offline'
                    elif detect_el is not None:
                        # 备用：chanDetectResult = 'connect' 表示在线
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

            online_count = sum(1 for c in channels.values() if c['online'])
            print(f"[ISAPI] 通道状态（status接口）: {online_count}在线 / {len(channels)-online_count}离线")

        except Exception as e:
            print(f"[ISAPI] channels/status 接口异常: {e}")

    def get_channels_with_status(self) -> Dict[int, Dict]:
        """
        获取所有通道信息（含在线状态）
        返回 {channel_no: {'name': str, 'online': bool, 'status': str}}
        """
        channels = self._get_channels_from_input_proxy()
        if channels:
            online_count  = sum(1 for c in channels.values() if c['online'])
            offline_count = len(channels) - online_count
            print(f"[ISAPI] 通道在线状态: {online_count}在线, {offline_count}离线/未知")
        return channels

    def set_channel_osd(self, channel_no: int, osd_name: str, enabled: bool = True) -> Tuple[bool, str]:
        """
        设置通道OSD名称（实际上是修改通道名称）
        
        注意：对于此NVR，OSD显示的就是通道名称（InputProxy接口中的<name>标签），
        没有独立的OSD配置。因此此方法修改的是通道名称。
        
        Args:
            channel_no: 通道号
            osd_name: OSD名称（通道名称）
            enabled: 是否启用（此参数在此NVR上无效，保留用于兼容性）
            
        Returns:
            (success, message)
        """
        try:
            # 首先获取当前通道配置
            url = f"{self.base_url}/ISAPI/ContentMgmt/InputProxy/channels/{channel_no}"
            print(f"[OSD] GET {url}")
            resp = self.session.get(url, timeout=10)
            print(f"[OSD] GET响应: HTTP {resp.status_code}")
            
            if resp.status_code != 200:
                return False, f"获取通道配置失败: HTTP {resp.status_code}"
            
            # 获取原始XML文本
            original_xml = resp.text
            print(f"[OSD] 原始XML长度: {len(original_xml)}")
            
            # 使用正则表达式替换 <name> 标签内容
            # 匹配 <name>xxx</name> 或 <name xmlns="...">xxx</name>
            import re
            
            # 先检查是否存在 name 标签
            name_pattern = r'(<name[^>]*>)[^<]*(</name>)'
            match = re.search(name_pattern, original_xml)
            
            if match:
                # 替换现有的 name 标签内容
                new_xml = re.sub(name_pattern, rf'\g<1>{osd_name}\g<2>', original_xml)
                print(f"[OSD] 替换名称: '{match.group(0)}' -> '<name...>{osd_name}</name>'")
            else:
                # 如果没有 name 标签，在根元素内添加
                # 找到第一个 > 后面插入 name 标签
                insert_pattern = r'(<InputProxyChannel[^>]*>)'
                new_xml = re.sub(insert_pattern, rf'\g<1>\n<name>{osd_name}</name>', original_xml, count=1)
                print(f"[OSD] 添加新name标签: <name>{osd_name}</name>")
            
            print(f"[OSD] PUT请求XML前500字符:\n{new_xml[:500]}...")
            
            # 发送PUT请求更新配置
            headers = {'Content-Type': 'application/xml'}
            resp = self.session.put(url, data=new_xml.encode('utf-8'), headers=headers, timeout=10)
            print(f"[OSD] PUT响应: HTTP {resp.status_code}")
            
            if resp.status_code == 200:
                return True, f"通道{channel_no} 名称/OSD更新成功"
            else:
                error_detail = resp.text[:300] if resp.text else "无响应内容"
                print(f"[OSD] PUT失败详情: {error_detail}")
                return False, f"更新通道名称失败: HTTP {resp.status_code} - {error_detail}"
                
        except Exception as e:
            import traceback
            print(f"[OSD] 异常: {e}")
            print(f"[OSD] 异常详情: {traceback.format_exc()}")
            return False, f"设置OSD异常: {str(e)}"

    def _get_names_from_streaming(self) -> Dict[int, str]:
        """从 /ISAPI/Streaming/channels 获取名称"""
        names: Dict[int, str] = {}
        try:
            url  = f"{self.base_url}/ISAPI/Streaming/channels"
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return names

            root = ET.fromstring(resp.text)
            # 尝试多个可能的命名空间
            ns_options = [
                'http://www.isapi.org/ver20/XMLSchema',
                'http://www.hikvision.com/ver20/XMLSchema',
            ]
            ns = None
            for ns_opt in ns_options:
                if root.find(f'.//{{{ns_opt}}}StreamingChannel') is not None:
                    ns = ns_opt
                    break
            
            if ns is None:
                # 没有找到任何命名空间，尝试不使用命名空间
                seen: set = set()
                for ch in root.findall('.//StreamingChannel'):
                    id_el   = ch.find('id')
                    name_el = ch.find('channelName')
                    if id_el is None or name_el is None:
                        continue
                    try:
                        raw_id = int(id_el.text)
                        ch_no = raw_id // 100
                        if ch_no > 0 and ch_no not in seen:
                            seen.add(ch_no)
                            name = (name_el.text or f"通道{ch_no}").strip()
                            names[ch_no] = name
                    except Exception:
                        pass
                return names

            seen: set = set()
            for ch in root.findall(f'.//{{{ns}}}StreamingChannel'):
                id_el   = ch.find(f'{{{ns}}}id')
                name_el = ch.find(f'{{{ns}}}channelName')
                if id_el is None or name_el is None:
                    continue
                try:
                    raw_id = int(id_el.text)
                    # 101 -> 1, 201 -> 2  （主码流ID格式）
                    ch_no = raw_id // 100
                    if ch_no > 0 and ch_no not in seen:
                        seen.add(ch_no)
                        name = (name_el.text or f"通道{ch_no}").strip()
                        names[ch_no] = name
                except Exception:
                    pass
        except Exception as e:
            print(f"[ISAPI] Streaming/channels异常: {e}")
        return names

    # ------------------------------------------------------------------ #
    #  设备信息
    # ------------------------------------------------------------------ #

    def get_device_info(self) -> Dict:
        """获取设备基本信息"""
        info: Dict = {}
        try:
            url  = f"{self.base_url}/ISAPI/System/deviceInfo"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                ns   = 'http://www.hikvision.com/ver20/XMLSchema'
                for tag in ('deviceName', 'model', 'serialNumber', 'firmwareVersion'):
                    el = root.find(f'.//{{{ns}}}{tag}')
                    if el is not None:
                        info[tag] = el.text
        except Exception as e:
            print(f"[ISAPI] 获取设备信息失败: {e}")
        return info

    def get_hdd_info(self) -> List[Dict]:
        """获取硬盘信息"""
        hdd_list = []
        try:
            url = f"{self.base_url}/ISAPI/ContentMgmt/Storage"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                
                # 尝试不同的命名空间
                namespaces = [
                    'http://www.isapi.org/ver20/XMLSchema',  # ISAPI标准命名空间
                    'http://www.hikvision.com/ver20/XMLSchema',  # 海康命名空间
                ]
                
                # 查找所有硬盘
                for ns in namespaces:
                    hdd_elements = root.findall(f'.//{{{ns}}}hdd')
                    if hdd_elements:
                        for hdd in hdd_elements:
                            hdd_info = {}
                            
                            # 硬盘号
                            id_el = hdd.find(f'{{{ns}}}id')
                            if id_el is not None:
                                hdd_info['id'] = id_el.text
                            
                            # 硬盘名称
                            name_el = hdd.find(f'{{{ns}}}hddName')
                            if name_el is not None:
                                hdd_info['name'] = name_el.text
                            
                            # 总容量 (MB)
                            capacity_el = hdd.find(f'{{{ns}}}capacity')
                            if capacity_el is not None:
                                capacity_mb = int(capacity_el.text)
                                hdd_info['capacity'] = round(capacity_mb / 1024, 2)  # 转为GB
                            
                            # 剩余空间 (MB)
                            free_el = hdd.find(f'{{{ns}}}freeSpace')
                            if free_el is not None:
                                free_mb = int(free_el.text)
                                hdd_info['free'] = round(free_mb / 1024, 2)  # 转为GB
                            
                            # 状态
                            status_el = hdd.find(f'{{{ns}}}status')
                            if status_el is not None:
                                status_map = {
                                    'ok': '正常',
                                    'error': '异常',
                                    'sleep': '休眠',
                                    'active': '活动'
                                }
                                hdd_info['status'] = status_map.get(status_el.text, status_el.text)
                            
                            # 类型
                            type_el = hdd.find(f'{{{ns}}}hddType')
                            if type_el is not None:
                                hdd_info['type'] = type_el.text
                            
                            if hdd_info:
                                hdd_list.append(hdd_info)
                        break  # 找到匹配的命名空间后退出
                        
                print(f"[ISAPI] 获取到 {len(hdd_list)} 块硬盘信息")
            else:
                print(f"[ISAPI] 获取硬盘信息失败: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[ISAPI] 获取硬盘信息异常: {e}")
        return hdd_list

    # ------------------------------------------------------------------ #
    #  系统运行状态
    # ------------------------------------------------------------------ #

    def get_system_status(self) -> Dict:
        """获取系统运行状态（CPU、内存等）"""
        status: Dict = {}
        try:
            url = f"{self.base_url}/ISAPI/System/status"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                
                # 尝试不同的命名空间
                namespaces = [
                    'http://www.isapi.org/ver20/XMLSchema',
                    'http://www.hikvision.com/ver20/XMLSchema',
                ]
                
                for ns in namespaces:
                    # CPU信息 - 尝试多种可能的字段名
                    # 注意：某些设备（如DS-8664N）可能不返回CPU信息
                    for cpu_tag in ['cpuUtilization', 'CPUUtilization', 'cpuPercent', 'CPUPercent']:
                        cpu_el = root.find(f'.//{{{ns}}}{cpu_tag}')
                        if cpu_el is not None:
                            try:
                                status['cpu_percent'] = int(float(cpu_el.text))
                                break
                            except:
                                pass
                    
                    # 内存信息 - 尝试多种可能的字段名
                    # 有些设备返回的是MemoryList/Memory子结构
                    memory_usage_mb = None
                    memory_available_mb = None
                    
                    # 先尝试直接从根元素查找
                    for mem_usage_tag in ['memoryUsage', 'MemoryUsage']:
                        mem_usage_el = root.find(f'.//{{{ns}}}{mem_usage_tag}')
                        if mem_usage_el is not None:
                            try:
                                memory_usage_mb = float(mem_usage_el.text)
                                status['memory_usage_mb'] = memory_usage_mb
                                break
                            except:
                                pass
                    
                    for mem_avail_tag in ['memoryAvailable', 'MemoryAvailable']:
                        mem_avail_el = root.find(f'.//{{{ns}}}{mem_avail_tag}')
                        if mem_avail_el is not None:
                            try:
                                memory_available_mb = float(mem_avail_el.text)
                                status['memory_available_mb'] = memory_available_mb
                                break
                            except:
                                pass
                    
                    # 计算内存使用率
                    if memory_usage_mb is not None and memory_available_mb is not None:
                        total_mb = memory_usage_mb + memory_available_mb
                        if total_mb > 0:
                            status['memory_percent'] = int((memory_usage_mb / total_mb) * 100)
                            status['memory_total_mb'] = int(total_mb)
                    
                    # 在线用户 - 尝试多种可能的字段名
                    # 注意：某些设备可能不返回在线用户数量
                    for users_tag in ['onlineUserNumber', 'OnlineUserNumber', 'onlineUsers', 'OnlineUsers']:
                        users_el = root.find(f'.//{{{ns}}}{users_tag}')
                        if users_el is not None:
                            try:
                                status['online_users'] = int(users_el.text)
                                break
                            except:
                                pass
                    
                    # 运行时间 - 尝试多种可能的字段名
                    for uptime_tag in ['deviceUpTime', 'DeviceUpTime', 'upTime', 'UpTime']:
                        uptime_el = root.find(f'.//{{{ns}}}{uptime_tag}')
                        if uptime_el is not None:
                            uptime_val = uptime_el.text.strip() if uptime_el.text else ""
                            # 如果是纯数字，转换为可读格式
                            if uptime_val and uptime_val.isdigit():
                                seconds = int(uptime_val)
                                days = seconds // 86400
                                hours = (seconds % 86400) // 3600
                                minutes = (seconds % 3600) // 60
                                status['uptime'] = f"{days}天{hours}小时{minutes}分钟"
                                status['uptime_seconds'] = seconds
                            else:
                                status['uptime'] = uptime_val
                            break
                    
                    # 如果已经获取到基本信息，就退出命名空间循环
                    if status:
                        break
                
                # 也尝试不带命名空间
                if 'cpu_percent' not in status:
                    for cpu_tag in ['cpuUtilization', 'CPUUtilization']:
                        cpu_el = root.find(f'.//{cpu_tag}')
                        if cpu_el is not None:
                            try:
                                status['cpu_percent'] = int(float(cpu_el.text))
                            except:
                                pass
                            break
                
                # 如果内存信息还没获取到，尝试不带命名空间
                if 'memory_percent' not in status:
                    for mem_tag in ['memoryUsage', 'MemoryUsage']:
                        mem_el = root.find(f'.//{mem_tag}')
                        if mem_el is not None:
                            try:
                                memory_usage_mb = float(mem_el.text)
                                status['memory_usage_mb'] = memory_usage_mb
                                break
                            except:
                                pass
                    
                    for mem_tag in ['memoryAvailable', 'MemoryAvailable']:
                        mem_el = root.find(f'.//{mem_tag}')
                        if mem_el is not None:
                            try:
                                memory_available_mb = float(mem_el.text)
                                status['memory_available_mb'] = memory_available_mb
                                break
                            except:
                                pass
                    
                    if memory_usage_mb is not None and memory_available_mb is not None:
                        total_mb = memory_usage_mb + memory_available_mb
                        if total_mb > 0:
                            status['memory_percent'] = int((memory_usage_mb / total_mb) * 100)
                            status['memory_total_mb'] = int(total_mb)
                        
                cpu_str = f"{status.get('cpu_percent', 'N/A')}%"
                mem_str = f"{status.get('memory_percent', 'N/A')}%"
                users_str = f"{status.get('online_users', 'N/A')}人"
                print(f"[ISAPI] 获取到系统状态: CPU {cpu_str}, 内存 {mem_str}, 在线用户 {users_str}")
            else:
                print(f"[ISAPI] 获取系统状态失败: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[ISAPI] 获取系统状态异常: {e}")
            import traceback
            traceback.print_exc()
        return status

    # ------------------------------------------------------------------ #
    #  网络绑定信息（Bond/工作模式）
    # ------------------------------------------------------------------ #

    def get_network_bond_info(self) -> Dict:
        """获取网络绑定信息（工作模式、主网卡、真实IP等）"""
        bond_info: Dict = {}
        try:
            url = f"{self.base_url}/ISAPI/System/Network/Bond"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                
                # 尝试不同的命名空间
                namespaces = [
                    'http://www.isapi.org/ver20/XMLSchema',
                    'http://www.hikvision.com/ver20/XMLSchema',
                ]
                
                for ns in namespaces:
                    # 查找Bond配置
                    bond_el = root.find(f'.//{{{ns}}}Bond')
                    if bond_el is not None:
                        # 是否启用
                        enabled_el = bond_el.find(f'{{{ns}}}enabled')
                        if enabled_el is not None:
                            bond_info['enabled'] = enabled_el.text.lower() == 'true'
                        
                        # 工作模式
                        work_mode_el = bond_el.find(f'{{{ns}}}workMode')
                        if work_mode_el is not None:
                            mode = work_mode_el.text
                            # 转换工作模式为中文
                            mode_map = {
                                'active-backup': '网络容错（主备）',
                                'balance-rr': '负载均衡（轮询）',
                                'balance-xor': '负载均衡（XOR）',
                                'broadcast': '广播',
                                '802.3ad': '链路聚合',
                                'balance-tlb': '负载均衡（TLB）',
                                'balance-alb': '负载均衡（ALB）'
                            }
                            bond_info['work_mode'] = mode_map.get(mode, mode)
                            bond_info['work_mode_raw'] = mode
                        
                        # 主网卡
                        primary_el = bond_el.find(f'{{{ns}}}primaryIf')
                        if primary_el is not None:
                            bond_info['primary_interface'] = primary_el.text
                        
                        # 从网卡列表
                        slave_list_el = bond_el.find(f'{{{ns}}}slaveIfList')
                        if slave_list_el is not None:
                            slaves = []
                            for slave_el in slave_list_el.findall(f'{{{ns}}}ethernetIfId'):
                                if slave_el.text:
                                    slaves.append(slave_el.text)
                            bond_info['slave_interfaces'] = slaves
                        
                        # IP地址信息
                        ip_el = bond_el.find(f'.//{{{ns}}}ipAddress')
                        if ip_el is not None:
                            bond_info['ip'] = ip_el.text
                        
                        # 子网掩码
                        mask_el = bond_el.find(f'.//{{{ns}}}subnetMask')
                        if mask_el is not None:
                            bond_info['mask'] = mask_el.text
                        
                        # 网关
                        gateway_el = bond_el.find(f'.//{{{ns}}}DefaultGateway')
                        if gateway_el is not None:
                            gw_ip = gateway_el.find(f'.//{{{ns}}}ipAddress')
                            if gw_ip is not None:
                                bond_info['gateway'] = gw_ip.text
                        
                        # MAC地址
                        mac_el = bond_el.find(f'.//{{{ns}}}MACAddress')
                        if mac_el is not None:
                            bond_info['mac'] = mac_el.text
                        
                        if bond_info:
                            break
                
                # 也尝试不带命名空间
                if not bond_info:
                    bond_el = root.find('.//Bond')
                    if bond_el is not None:
                        enabled_el = bond_el.find('enabled')
                        if enabled_el is not None:
                            bond_info['enabled'] = enabled_el.text.lower() == 'true'
                        
                        work_mode_el = bond_el.find('workMode')
                        if work_mode_el is not None:
                            bond_info['work_mode'] = work_mode_el.text
                        
                        primary_el = bond_el.find('primaryIf')
                        if primary_el is not None:
                            bond_info['primary_interface'] = primary_el.text
                        
                        ip_el = bond_el.find('.//ipAddress')
                        if ip_el is not None:
                            bond_info['ip'] = ip_el.text
                
                print(f"[ISAPI] 获取到网络绑定信息: 工作模式={bond_info.get('work_mode', 'N/A')}, 主网卡={bond_info.get('primary_interface', 'N/A')}")
            else:
                print(f"[ISAPI] 获取网络绑定信息失败: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[ISAPI] 获取网络绑定信息异常: {e}")
        return bond_info

    # ------------------------------------------------------------------ #
    #  网络接口信息
    # ------------------------------------------------------------------ #

    def get_network_interfaces(self) -> List[Dict]:
        """获取网络接口信息（IP地址、网关、DNS等）"""
        interfaces = []
        try:
            url = f"{self.base_url}/ISAPI/System/Network/interfaces"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                
                # 尝试不同的命名空间
                namespaces = [
                    'http://www.isapi.org/ver20/XMLSchema',
                    'http://www.hikvision.com/ver20/XMLSchema',
                ]
                
                for ns in namespaces:
                    network_interfaces = root.findall(f'.//{{{ns}}}NetworkInterface')
                    if network_interfaces:
                        for iface in network_interfaces:
                            iface_info = {}
                            
                            # 接口ID
                            id_el = iface.find(f'{{{ns}}}id')
                            if id_el is not None:
                                iface_info['id'] = id_el.text
                            
                            # IP地址信息 - 可能在不同层级
                            ip_el = iface.find(f'.//{{{ns}}}ipAddress')
                            if ip_el is not None:
                                iface_info['ip'] = ip_el.text
                            
                            # 子网掩码
                            mask_el = iface.find(f'.//{{{ns}}}subnetMask')
                            if mask_el is not None:
                                iface_info['mask'] = mask_el.text
                            
                            # 网关 - 尝试多种路径
                            gateway_ip = None
                            # 方式1: DefaultGateway/ipAddress
                            gateway_el = iface.find(f'.//{{{ns}}}DefaultGateway')
                            if gateway_el is not None:
                                gateway_ip_el = gateway_el.find(f'.//{{{ns}}}ipAddress')
                                if gateway_ip_el is not None:
                                    gateway_ip = gateway_ip_el.text
                            # 方式2: 直接查找gateway
                            if gateway_ip is None or gateway_ip == '0.0.0.0':
                                for gw_tag in ['gateway', 'Gateway', 'defaultGateway', 'DefaultGatewayIp']:
                                    gw_el = iface.find(f'.//{{{ns}}}{gw_tag}')
                                    if gw_el is not None:
                                        # 可能是直接值或嵌套结构
                                        if gw_el.text and gw_el.text != '0.0.0.0':
                                            gateway_ip = gw_el.text
                                            break
                                        # 尝试查找子元素
                                        gw_ip_el = gw_el.find(f'.//{{{ns}}}ipAddress')
                                        if gw_ip_el is not None and gw_ip_el.text != '0.0.0.0':
                                            gateway_ip = gw_ip_el.text
                                            break
                            if gateway_ip:
                                iface_info['gateway'] = gateway_ip
                            
                            # MAC地址
                            mac_el = iface.find(f'.//{{{ns}}}MACAddress')
                            if mac_el is not None:
                                iface_info['mac'] = mac_el.text
                            
                            # MTU
                            mtu_el = iface.find(f'.//{{{ns}}}MTU')
                            if mtu_el is not None:
                                try:
                                    iface_info['mtu'] = int(mtu_el.text)
                                except:
                                    pass
                            
                            # 是否启用
                            enabled_el = iface.find(f'.//{{{ns}}}enabled')
                            if enabled_el is not None:
                                iface_info['enabled'] = enabled_el.text.lower() == 'true'
                            
                            # 是否DHCP
                            dhcp_el = iface.find(f'.//{{{ns}}}addressingType')
                            if dhcp_el is not None:
                                iface_info['dhcp'] = dhcp_el.text.lower() == 'dynamic'
                            
                            if iface_info:
                                interfaces.append(iface_info)
                        break
                
                # 也尝试不带命名空间
                if not interfaces:
                    network_interfaces = root.findall('.//NetworkInterface')
                    for iface in network_interfaces:
                        iface_info = {}
                        
                        id_el = iface.find('id')
                        if id_el is not None:
                            iface_info['id'] = id_el.text
                        
                        ip_el = iface.find('.//ipAddress')
                        if ip_el is not None:
                            iface_info['ip'] = ip_el.text
                        
                        mask_el = iface.find('.//subnetMask')
                        if mask_el is not None:
                            iface_info['mask'] = mask_el.text
                        
                        gateway_el = iface.find('.//DefaultGateway')
                        if gateway_el is not None:
                            gateway_ip = gateway_el.find('.//ipAddress')
                            if gateway_ip is not None:
                                iface_info['gateway'] = gateway_ip.text
                        
                        mac_el = iface.find('.//MACAddress')
                        if mac_el is not None:
                            iface_info['mac'] = mac_el.text
                        
                        if iface_info:
                            interfaces.append(iface_info)
                        
                print(f"[ISAPI] 获取到 {len(interfaces)} 个网络接口")
            else:
                print(f"[ISAPI] 获取网络接口失败: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[ISAPI] 获取网络接口异常: {e}")
        return interfaces

    # ------------------------------------------------------------------ #
    #  通道流信息（分辨率、码率、编码等）
    # ------------------------------------------------------------------ #

    def get_channel_stream_info(self) -> Dict[int, Dict]:
        """
        获取通道流信息（分辨率、码率、编码格式等）
        返回 {channel_no: {'main_stream': {...}, 'sub_stream': {...}}}
        
        主码流ID格式: 101, 201, 301... (通道号*100 + 1)
        子码流ID格式: 102, 202, 302... (通道号*100 + 2)
        """
        stream_info: Dict[int, Dict] = {}
        try:
            url = f"{self.base_url}/ISAPI/Streaming/channels"
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"[ISAPI] 获取流信息失败: HTTP {resp.status_code}")
                return stream_info

            root = ET.fromstring(resp.text)
            
            # 尝试不同的命名空间
            ns_options = [
                'http://www.isapi.org/ver20/XMLSchema',
                'http://www.hikvision.com/ver20/XMLSchema',
            ]
            ns = None
            for ns_opt in ns_options:
                if root.find(f'.//{{{ns_opt}}}StreamingChannel') is not None:
                    ns = ns_opt
                    break
            
            if ns is None:
                # 尝试无命名空间
                channels = root.findall('.//StreamingChannel')
            else:
                channels = root.findall(f'.//{{{ns}}}StreamingChannel')
            
            for ch in channels:
                # 获取ID
                if ns:
                    id_el = ch.find(f'{{{ns}}}id')
                else:
                    id_el = ch.find('id')
                
                if id_el is None or not id_el.text:
                    continue
                
                try:
                    stream_id = int(id_el.text)
                    # ID格式: 101=通道1主码流, 102=通道1子码流, 104=通道1第三码流
                    ch_no = stream_id // 100
                    stream_suffix = stream_id % 100
                    if stream_suffix == 1:
                        stream_type = 'main_stream'
                    elif stream_suffix == 2:
                        stream_type = 'sub_stream'
                    else:
                        # 其他码流（如第三码流04）跳过
                        continue
                    
                    if ch_no not in stream_info:
                        stream_info[ch_no] = {}
                    
                    info = {
                        'stream_id': stream_id,
                        'enabled': False,
                        'resolution': '',
                        'codec': '',
                        'codec_profile': '',  # 编码配置文件 (Main/High/Baseline等)
                        'smart_codec': False,  # 是否启用Smart Codec (Smart H.265/H.264)
                        'smart_codec_type': '',  # Smart Codec类型
                        'bitrate_kbps': 0,
                        'bitrate_mode': '',  # 码率控制类型: CBR(定码率)/VBR(变码率)
                        'fps': 0,
                        'audio_enabled': False,
                        'audio_codec': '',
                    }
                    
                    # 获取enabled状态
                    if ns:
                        enabled_el = ch.find(f'{{{ns}}}enabled')
                    else:
                        enabled_el = ch.find('enabled')
                    if enabled_el is not None:
                        info['enabled'] = enabled_el.text == 'true'
                    
                    # 获取Video信息
                    if ns:
                        video = ch.find(f'{{{ns}}}Video')
                    else:
                        video = ch.find('Video')
                    
                    if video is not None:
                        # 分辨率
                        if ns:
                            width = video.find(f'{{{ns}}}videoResolutionWidth')
                            height = video.find(f'{{{ns}}}videoResolutionHeight')
                        else:
                            width = video.find('videoResolutionWidth')
                            height = video.find('videoResolutionHeight')
                        
                        if width is not None and height is not None:
                            info['resolution'] = f"{width.text}x{height.text}"
                        
                        # 编码格式
                        if ns:
                            codec = video.find(f'{{{ns}}}videoCodecType')
                        else:
                            codec = video.find('videoCodecType')
                        if codec is not None:
                            info['codec'] = codec.text
                        
                        # 编码配置文件 (profile)
                        if ns:
                            profile = video.find(f'{{{ns}}}videoCodecProfile')
                        else:
                            profile = video.find('videoCodecProfile')
                        if profile is not None:
                            info['codec_profile'] = profile.text
                        
                        # 码率控制类型 (CBR/VBR)
                        if ns:
                            bitrate_mode = video.find(f'{{{ns}}}videoQualityControlType')
                        else:
                            bitrate_mode = video.find('videoQualityControlType')
                        if bitrate_mode is not None:
                            info['bitrate_mode'] = bitrate_mode.text
                        
                        # Smart Codec (Smart H.265/H.264)
                        if ns:
                            smart_codec = video.find(f'{{{ns}}}smartCodec')
                        else:
                            smart_codec = video.find('smartCodec')
                        if smart_codec is not None:
                            # smartCodec可能是一个复杂结构或简单布尔值
                            if smart_codec.text:
                                info['smart_codec'] = smart_codec.text.lower() == 'true'
                            else:
                                # 查找enabled子元素
                                if ns:
                                    smart_enabled = smart_codec.find(f'{{{ns}}}enabled')
                                else:
                                    smart_enabled = smart_codec.find('enabled')
                                if smart_enabled is not None:
                                    info['smart_codec'] = smart_enabled.text.lower() == 'true'
                            
                            # Smart Codec类型
                            if ns:
                                smart_type = smart_codec.find(f'{{{ns}}}smartCodecType')
                            else:
                                smart_type = smart_codec.find('smartCodecType')
                            if smart_type is not None:
                                info['smart_codec_type'] = smart_type.text
                        
                        # 码率 (kbps) — 支持 CBR 和 VBR 模式
                        # CBR: constantBitRate; VBR: upperBitRate / peakBitRate
                        bitrate_kbps = 0
                        for bitrate_tag in ['constantBitRate', 'upperBitRate', 'peakBitRate']:
                            if ns:
                                bitrate = video.find(f'{{{ns}}}{bitrate_tag}')
                            else:
                                bitrate = video.find(bitrate_tag)
                            if bitrate is not None and bitrate.text:
                                try:
                                    bitrate_kbps = int(bitrate.text)
                                    if bitrate_kbps > 0:
                                        break
                                except:
                                    pass
                        if bitrate_kbps > 0:
                            info['bitrate_kbps'] = bitrate_kbps
                        else:
                            print(f"[ISAPI] 通道{ch_no} {stream_type} 码率为0，跳过 (CBR/VBR节点均无效)")
                        
                        # 帧率 (maxFrameRate通常是100的倍数，如2500=25fps)
                        if ns:
                            fps = video.find(f'{{{ns}}}maxFrameRate')
                        else:
                            fps = video.find('maxFrameRate')
                        if fps is not None and fps.text:
                            try:
                                fps_val = int(fps.text)
                                # 只处理大于0的帧率值，0表示未设置
                                if fps_val > 0:
                                    info['fps'] = fps_val // 100 if fps_val >= 100 else fps_val
                            except:
                                pass
                    
                    # 获取Audio信息
                    if ns:
                        audio = ch.find(f'{{{ns}}}Audio')
                    else:
                        audio = ch.find('Audio')
                    
                    if audio is not None:
                        if ns:
                            audio_enabled = audio.find(f'{{{ns}}}enabled')
                            audio_codec = audio.find(f'{{{ns}}}audioCompressionType')
                        else:
                            audio_enabled = audio.find('enabled')
                            audio_codec = audio.find('audioCompressionType')
                        
                        if audio_enabled is not None:
                            info['audio_enabled'] = audio_enabled.text == 'true'
                        if audio_codec is not None:
                            info['audio_codec'] = audio_codec.text
                    
                    stream_info[ch_no][stream_type] = info
                    
                except Exception as e:
                    print(f"[ISAPI] 解析通道流信息异常: {e}")
                    continue
            
            print(f"[ISAPI] 获取到 {len(stream_info)} 个通道的流信息")
            
        except Exception as e:
            print(f"[ISAPI] 获取通道流信息失败: {e}")
        
        return stream_info

    # ------------------------------------------------------------------ #
    #  ISAPI HTTP 录像下载（时间段截取）
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
            save_path:     保存文件路径（如 /path/to/ch1_20260326.mp4）
            stream_type:   码流类型 1=主码流, 2=子码流（默认主码流）
            rtsp_port:     RTSP端口（默认554）
            progress_callback: 进度回调 (progress_percent: int)
            log_callback:  日志回调 (msg: str)
            stop_event:    停止事件（可选，用于中断下载）
            size_callback: 文件大小回调 (size_bytes: int)，连接成功后立即回调

        Returns:
            (success, message)
        """
        import urllib.parse
        import time
        import threading as _threading

        def _log(msg: str):
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass
            print(f"[ISAPI下载] {msg}")

        # 构建内部 RTSP 回放 URI
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

        # 构建 XML 请求体
        xml_body = (
            '<?xml version="1.0" encoding="UTF-8"?>\r\n'
            '<downloadRequest version="1.0">\r\n'
            f'  <playbackURI><![CDATA[{rtsp_uri}]]></playbackURI>\r\n'
            '</downloadRequest>\r\n'
        )

        # 多种接口路径（兼容不同固件版本）
        urls_to_try = [
            f"{self.base_url}/ISAPI/ContentMgmt/download",
            f"{self.base_url}/ISAPI/Streaming/channels/download",
            f"{self.base_url}/ISAPI/ContentMgrmt/download",
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
                    timeout=30,           # 连接超时
                    stream=True,           # 流式接收
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
                    _log(f"✅ 连接成功，文件大小: {total_bytes / 1024 / 1024:.2f}MB")
                    # 立即回调通知文件大小（用于表格预显示）
                    if size_callback:
                        try:
                            size_callback(total_bytes)
                        except Exception:
                            pass
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
                            # 中断：删除不完整文件
                            f.close()
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
                                # 按 Content-Length 未知时，用时间估算
                                elapsed = time.monotonic() - t_start
                                # 码率估算：已下载/已用时间
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
                    # 删除空文件
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
                import traceback
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
        import subprocess
        import signal
        import time
        import threading as _threading

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

        import urllib.parse
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
            # 尝试 PATH
            ffmpeg_path = "ffmpeg"

        # 两套命令：先尝试带音频，失败则丢弃音频
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
                        # 停止FFmpeg
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

                    _threading.Event().wait(0.5)

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

    # ------------------------------------------------------------------ #
    #  工具函数
    # ------------------------------------------------------------------ #

    def _parse_xml_text(self, xml_str: str, tag: str) -> Optional[str]:
        """从XML字符串提取指定标签的文本"""
        try:
            root = ET.fromstring(xml_str)
            ns   = 'http://www.hikvision.com/ver20/XMLSchema'
            el   = root.find(f'.//{{{ns}}}{tag}')
            if el is None:
                el = root.find(f'.//{tag}')
            return el.text if el is not None else None
        except Exception:
            return None


# ------------------------------------------------------------------ #
#  便利工厂
# ------------------------------------------------------------------ #

def create_isapi(config: Dict) -> HikvisionISAPI:
    """根据设备配置创建ISAPI连接"""
    return HikvisionISAPI(
        host     = config['host'],
        port     = config.get('http_port', 80),
        username = config.get('username', 'admin'),
        password = config.get('password', ''),
    )
