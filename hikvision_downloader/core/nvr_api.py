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

                    channels[no] = {'name': name, 'online': online, 'status': status}
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
