# 设备信息模块
# 职责：获取设备状态、硬盘信息、网络接口、网络绑定
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET


class DeviceInfoMixin:
    """
    提供设备基础信息查询能力。
    混入到 HikvisionISAPI 主类使用。
    """

    # ------------------------------------------------------------------ #
    #  设备基础信息
    # ------------------------------------------------------------------ #

    def get_device_info(self) -> Dict:
        """获取设备基础信息（型号、序列号、固件版本等）"""
        info = {}
        try:
            url = f"{self.base_url}/ISAPI/System/deviceInfo"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)

                # 尝试多个命名空间
                namespaces = [
                    'http://www.isapi.org/ver20/XMLSchema',
                    'http://www.hikvision.com/ver20/XMLSchema',
                ]

                for ns in namespaces:
                    device_el = root.find(f'.//{{{ns}}}DeviceInfo')
                    if device_el is not None:
                        for child in device_el:
                            tag = child.tag.split('}')[-1]  # 去掉命名空间前缀
                            info[tag] = child.text
                        break

                # 不带命名空间也尝试一下
                if not info:
                    for child in root.findall('.//DeviceInfo'):
                        for sub in child:
                            tag = sub.tag.split('}')[-1]
                            info[tag] = sub.text
        except Exception as e:
            print(f"[ISAPI] 获取设备信息异常: {e}")
        return info

    def get_hdd_info(self) -> List[Dict]:
        """获取硬盘信息 - 使用 /ISAPI/ContentMgmt/Storage 接口"""
        hdd_list = []
        try:
            url = f"{self.base_url}/ISAPI/ContentMgmt/Storage"
            resp = self.session.get(url, timeout=8)
            if resp.status_code != 200:
                print(f"[ISAPI] 获取硬盘信息失败: HTTP {resp.status_code}")
                return hdd_list
            
            print(f"[ISAPI DEBUG] HDD response: {resp.text[:2000]}")  # 增加输出长度
            root = ET.fromstring(resp.text)

            namespaces = [
                'http://www.isapi.org/ver20/XMLSchema',
                'http://www.hikvision.com/ver20/XMLSchema',
            ]

            # 查找所有硬盘节点 <hdd>
            for ns in namespaces:
                hdd_elements = root.findall(f'.//{{{ns}}}hdd')
                if hdd_elements:
                    for hdd in hdd_elements:
                        hdd_info = {}

                        # 硬盘ID
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

                        # 硬盘序列号
                        serial_el = hdd.find(f'{{{ns}}}hddSerialNumber')
                        if serial_el is not None:
                            hdd_info['serial_number'] = serial_el.text

                        # 硬盘型号
                        model_el = hdd.find(f'{{{ns}}}hddModel')
                        if model_el is not None:
                            hdd_info['model'] = model_el.text

                        if hdd_info:
                            hdd_list.append(hdd_info)
                    break  # 找到匹配的命名空间后退出

            print(f"[ISAPI] 获取到 {len(hdd_list)} 块硬盘信息")
        except Exception as e:
            print(f"[ISAPI] 获取硬盘信息异常: {e}")
            import traceback
            traceback.print_exc()
        return hdd_list

    # ------------------------------------------------------------------ #
    #  系统状态
    # ------------------------------------------------------------------ #

    def get_system_status(self) -> Dict:
        """
        获取系统运行状态（CPU、内存、在线用户、运行时间）
        """
        status = {}
        try:
            url = f"{self.base_url}/ISAPI/System/status"
            resp = self.session.get(url, timeout=8)
            if resp.status_code != 200:
                return status

            root = ET.fromstring(resp.text)

            # 尝试多个命名空间
            namespaces = [
                'http://www.isapi.org/ver20/XMLSchema',
                'http://www.hikvision.com/ver20/XMLSchema',
            ]

            for ns in namespaces:
                # CPU使用率（尝试多种标签名）
                cpu_tags = ['cpuUsage', 'CPUUsage', 'cpuUtilization', 'CPUUtilization', 'cpu', 'CPU']
                for cpu_tag in cpu_tags:
                    cpu_el = root.find(f'.//{{{ns}}}{cpu_tag}')
                    if cpu_el is not None:
                        try:
                            status['cpu_percent'] = int(float(cpu_el.text))
                            break
                        except:
                            pass
                
                # 如果还是没找到，尝试不带命名空间
                if 'cpu_percent' not in status:
                    for cpu_tag in cpu_tags:
                        cpu_el = root.find(f'.//{cpu_tag}')
                        if cpu_el is not None:
                            try:
                                status['cpu_percent'] = int(float(cpu_el.text))
                                break
                            except:
                                pass

                # 内存使用率（主标签）
                mem_tags = ['memoryUsage', 'MemoryUsage', 'memoryUtilization', 'MemoryUtilization']
                for mem_tag in mem_tags:
                    mem_el = root.find(f'.//{{{ns}}}{mem_tag}')
                    if mem_el is not None:
                        try:
                            mem_val = int(float(mem_el.text))
                            # 判断是百分比还是绝对值（MB）
                            # 如果 > 100，说明是绝对值（MB），稍后通过memoryUsageMB计算百分比
                            if mem_val <= 100:
                                status['memory_percent'] = mem_val
                            break
                        except:
                            pass
                
                # 如果还是没找到，尝试不带命名空间
                if 'memory_percent' not in status:
                    for mem_tag in mem_tags:
                        mem_el = root.find(f'.//{mem_tag}')
                        if mem_el is not None:
                            try:
                                mem_val = int(float(mem_el.text))
                                if mem_val <= 100:
                                    status['memory_percent'] = mem_val
                                break
                            except:
                                pass

                # 计算内存使用率（备用方案：从 memoryUsageMB + memoryAvailableMB）
                memory_usage_mb = None
                memory_available_mb = None
                
                # 尝试多种可能的标签名
                usage_mb_tags = ['memoryUsageMB', 'MemoryUsageMB', 'memoryUsedMB', 'MemoryUsedMB', 'usedMemoryMB', 'UsedMemoryMB']
                for mem_tag in usage_mb_tags:
                    mem_mb_el = root.find(f'.//{{{ns}}}{mem_tag}')
                    if mem_mb_el is not None:
                        try:
                            memory_usage_mb = int(mem_mb_el.text)
                            break
                        except:
                            pass
                
                if memory_usage_mb is None:
                    for mem_tag in usage_mb_tags:
                        mem_mb_el = root.find(f'.//{mem_tag}')
                        if mem_mb_el is not None:
                            try:
                                memory_usage_mb = int(mem_mb_el.text)
                                break
                            except:
                                pass
                
                # 可用内存
                avail_mb_tags = ['memoryAvailableMB', 'MemoryAvailableMB', 'memoryFreeMB', 'MemoryFreeMB', 'freeMemoryMB', 'FreeMemoryMB']
                for avail_tag in avail_mb_tags:
                    avail_el = root.find(f'.//{{{ns}}}{avail_tag}')
                    if avail_el is not None:
                        try:
                            memory_available_mb = int(avail_el.text)
                            break
                        except:
                            pass
                
                if memory_available_mb is None:
                    for avail_tag in avail_mb_tags:
                        avail_el = root.find(f'.//{avail_tag}')
                        if avail_el is not None:
                            try:
                                memory_available_mb = int(avail_el.text)
                                break
                            except:
                                pass

                # 计算内存使用率
                if memory_usage_mb is not None and memory_available_mb is not None:
                    total_mb = memory_usage_mb + memory_available_mb
                    if total_mb > 0:
                        status['memory_percent'] = int((memory_usage_mb / total_mb) * 100)
                        status['memory_total_mb'] = int(total_mb)

                # 在线用户（尝试多种可能的标签名）
                user_tags = [
                    'onlineUserNumber', 'OnlineUserNumber',
                    'onlineUsers', 'OnlineUsers',
                    'userNumber', 'UserNumber',
                    'sessionCount', 'SessionCount',
                    'activeUsers', 'ActiveUsers'
                ]
                for users_tag in user_tags:
                    users_el = root.find(f'.//{{{ns}}}{users_tag}')
                    if users_el is not None:
                        try:
                            status['online_users'] = int(users_el.text)
                            break
                        except:
                            pass
                
                # 如果还是没找到，尝试不带命名空间
                if 'online_users' not in status:
                    for users_tag in user_tags:
                        users_el = root.find(f'.//{users_tag}')
                        if users_el is not None:
                            try:
                                status['online_users'] = int(users_el.text)
                                break
                            except:
                                pass

                # 运行时间
                for uptime_tag in ['deviceUpTime', 'DeviceUpTime', 'upTime', 'UpTime']:
                    uptime_el = root.find(f'.//{{{ns}}}{uptime_tag}')
                    if uptime_el is not None:
                        uptime_val = uptime_el.text.strip() if uptime_el.text else ""
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

                if status:
                    break

            # 不带命名空间也尝试
            if 'cpu_percent' not in status:
                for cpu_tag in ['cpuUtilization', 'CPUUtilization']:
                    cpu_el = root.find(f'.//{cpu_tag}')
                    if cpu_el is not None:
                        try:
                            status['cpu_percent'] = int(float(cpu_el.text))
                        except:
                            pass

        except Exception as e:
            print(f"[ISAPI] 获取系统状态异常: {e}")
            traceback.print_exc()
        finally:
            # 添加调试信息：打印原始响应和解析结果
            try:
                url = f"{self.base_url}/ISAPI/System/status"
                resp = self.session.get(url, timeout=8)
                print(f"[ISAPI DEBUG] System Status Response: {resp.text[:800]}")
                print(f"[ISAPI DEBUG] Parsed status: {status}")
            except:
                pass
        return status

    # ------------------------------------------------------------------ #
    #  网络绑定信息
    # ------------------------------------------------------------------ #

    def get_network_bond_info(self) -> Dict:
        """获取网络绑定（Bond）信息"""
        bond_info = {}
        try:
            url = f"{self.base_url}/ISAPI/System/Network/Bond"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)

                namespaces = [
                    'http://www.isapi.org/ver20/XMLSchema',
                    'http://www.hikvision.com/ver20/XMLSchema',
                ]

                for ns in namespaces:
                    bond_el = root.find(f'.//{{{ns}}}Bond')
                    if bond_el is not None:
                        enabled_el = bond_el.find(f'{{{ns}}}enabled')
                        if enabled_el is not None:
                            bond_info['enabled'] = enabled_el.text.lower() == 'true'

                        work_mode_el = bond_el.find(f'{{{ns}}}workMode')
                        if work_mode_el is not None:
                            mode = work_mode_el.text
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

                        primary_el = bond_el.find(f'{{{ns}}}primaryIf')
                        if primary_el is not None:
                            bond_info['primary_interface'] = primary_el.text

                        slave_list_el = bond_el.find(f'{{{ns}}}slaveIfList')
                        if slave_list_el is not None:
                            slaves = []
                            for slave_el in slave_list_el.findall(f'{{{ns}}}ethernetIfId'):
                                if slave_el.text:
                                    slaves.append(slave_el.text)
                            bond_info['slave_interfaces'] = slaves

                        ip_el = bond_el.find(f'.//{{{ns}}}ipAddress')
                        if ip_el is not None:
                            bond_info['ip'] = ip_el.text

                        mask_el = bond_el.find(f'.//{{{ns}}}subnetMask')
                        if mask_el is not None:
                            bond_info['mask'] = mask_el.text

                        gateway_el = bond_el.find(f'.//{{{ns}}}DefaultGateway')
                        if gateway_el is not None:
                            gw_ip = gateway_el.find(f'.//{{{ns}}}ipAddress')
                            if gw_ip is not None:
                                bond_info['gateway'] = gw_ip.text

                        mac_el = bond_el.find(f'.//{{{ns}}}MACAddress')
                        if mac_el is not None:
                            bond_info['mac'] = mac_el.text

                        if bond_info:
                            break

                # 不带命名空间
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

                namespaces = [
                    'http://www.isapi.org/ver20/XMLSchema',
                    'http://www.hikvision.com/ver20/XMLSchema',
                ]

                for ns in namespaces:
                    network_interfaces = root.findall(f'.//{{{ns}}}NetworkInterface')
                    if network_interfaces:
                        for iface in network_interfaces:
                            iface_info = {}

                            id_el = iface.find(f'{{{ns}}}id')
                            if id_el is not None:
                                iface_info['id'] = id_el.text

                            ip_el = iface.find(f'.//{{{ns}}}ipAddress')
                            if ip_el is not None:
                                iface_info['ip'] = ip_el.text

                            mask_el = iface.find(f'.//{{{ns}}}subnetMask')
                            if mask_el is not None:
                                iface_info['mask'] = mask_el.text

                            gateway_el = iface.find(f'.//{{{ns}}}DefaultGateway')
                            if gateway_el is not None:
                                gateway_ip_el = gateway_el.find(f'.//{{{ns}}}ipAddress')
                                if gateway_ip_el is not None:
                                    iface_info['gateway'] = gateway_ip_el.text

                            mac_el = iface.find(f'.//{{{ns}}}MACAddress')
                            if mac_el is not None:
                                iface_info['mac'] = mac_el.text

                            iface_name_el = iface.find(f'.//{{{ns}}}ifName')
                            if iface_name_el is not None:
                                iface_info['if_name'] = iface_name_el.text

                            mtu_el = iface.find(f'.//{{{ns}}}mtu')
                            if mtu_el is not None:
                                iface_info['mtu'] = mtu_el.text

                            # 中文名称
                            for name_tag in ['ifDescription', 'ifAlias', 'description']:
                                name_el = iface.find(f'.//{{{ns}}}{name_tag}')
                                if name_el is not None and name_el.text:
                                    iface_info['description'] = name_el.text
                                    break

                            if iface_info:
                                interfaces.append(iface_info)
                        break

                # 不带命名空间
                if not interfaces:
                    for iface in root.findall('.//NetworkInterface'):
                        iface_info = {}
                        for child in iface:
                            tag = child.tag.split('}')[-1]
                            iface_info[tag] = child.text
                        if iface_info:
                            interfaces.append(iface_info)

        except Exception as e:
            print(f"[ISAPI] 获取网络接口信息异常: {e}")
        return interfaces
