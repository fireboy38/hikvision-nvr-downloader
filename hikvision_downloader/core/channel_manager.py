# 通道管理模块
# 职责：通道名称查询、通道状态、通道流信息（分辨率/码率）
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET


class ChannelManagerMixin:
    """
    提供通道管理能力：名称查询、在线状态、流信息。
    混入到 HikvisionISAPI 主类使用。
    """

    # ------------------------------------------------------------------ #
    #  通道名称
    # ------------------------------------------------------------------ #

    def get_channel_names(self) -> Dict[int, str]:
        """
        获取所有通道名称。
        优先从 InputProxy 接口获取，失败则回退到 Streaming 接口。
        """
        names: Dict[int, str] = {}

        # 方式1：从 InputProxy 获取
        try:
            url = f"{self.base_url}/ISAPI/ContentMgmt/InputProxy/channels"
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)

                ns_options = [
                    'http://www.isapi.org/ver20/XMLSchema',
                    'http://www.hikvision.com/ver20/XMLSchema',
                ]
                ns = None
                for ns_opt in ns_options:
                    if root.find(f'.//{{{ns_opt}}}InputProxyChannel') is not None:
                        ns = ns_opt
                        break

                if ns:
                    for ch in root.findall(f'.//{{{ns}}}InputProxyChannel'):
                        id_el = ch.find(f'{{{ns}}}id')
                        name_el = ch.find(f'{{{ns}}}name')
                        if id_el is not None and name_el is not None:
                            try:
                                no = int(id_el.text)
                                names[no] = (name_el.text or '').strip()
                            except:
                                pass
                else:
                    for ch in root.findall('.//InputProxyChannel'):
                        id_el = ch.find('id')
                        name_el = ch.find('name')
                        if id_el is not None and name_el is not None:
                            try:
                                no = int(id_el.text)
                                names[no] = (name_el.text or '').strip()
                            except:
                                pass
        except Exception:
            pass

        # 方式2：从 Streaming 接口获取
        if not names:
            names = self._get_names_from_streaming()

        return names

    def _get_names_from_streaming(self) -> Dict[int, str]:
        """从 /ISAPI/Streaming/channels 获取通道名称"""
        names: Dict[int, str] = {}
        try:
            url = f"{self.base_url}/ISAPI/Streaming/channels"
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return names

            root = ET.fromstring(resp.text)
            ns_options = [
                'http://www.isapi.org/ver20/XMLSchema',
                'http://www.hikvision.com/ver20/XMLSchema',
            ]
            ns = None
            for ns_opt in ns_options:
                if root.find(f'.//{{{ns_opt}}}StreamingChannel') is not None:
                    ns = ns_opt
                    break

            seen: set = set()
            search_path = f'.//{{{ns}}}StreamingChannel' if ns else './/StreamingChannel'
            id_tag = f'{{{ns}}}id' if ns else 'id'
            name_tag = f'{{{ns}}}channelName' if ns else 'channelName'

            for ch in root.findall(search_path):
                id_el = ch.find(id_tag)
                name_el = ch.find(name_tag)
                if id_el is None or name_el is None:
                    continue
                try:
                    raw_id = int(id_el.text)
                    ch_no = raw_id // 100
                    if ch_no > 0 and ch_no not in seen:
                        seen.add(ch_no)
                        names[ch_no] = (name_el.text or f"通道{ch_no}").strip()
                except:
                    pass
        except Exception as e:
            print(f"[ISAPI] Streaming通道名称获取异常: {e}")
        return names

    # ------------------------------------------------------------------ #
    #  通道状态（含名称+在线状态）
    # ------------------------------------------------------------------ #

    def _get_channels_from_input_proxy(self) -> Dict[int, Dict]:
        """
        从 InputProxy 接口获取通道基础信息（名称、协议、IP地址）。
        在线状态可能缺失，需要调用 _enrich_status_from_status_api 补充。
        """
        channels: Dict[int, Dict] = {}

        try:
            url = f"{self.base_url}/ISAPI/ContentMgmt/InputProxy/channels"
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return channels

            print(f"[ISAPI DEBUG] InputProxy channels response length: {len(resp.text)}")
            print(f"[ISAPI DEBUG] First 2000 chars: {resp.text[:2000]}")
            
            root = ET.fromstring(resp.text)

            ns_options = [
                'http://www.isapi.org/ver20/XMLSchema',
                'http://www.hikvision.com/ver20/XMLSchema',
            ]
            ns = None
            for ns_opt in ns_options:
                if root.find(f'.//{{{ns_opt}}}InputProxyChannel') is not None:
                    ns = ns_opt
                    break

            has_connection_status = False

            def _parse_ch(ch_elem, ns_prefix=''):
                nonlocal has_connection_status

                def _find(tag):
                    if ns_prefix:
                        # ns_prefix 已经包含花括号，直接使用
                        result = ch_elem.find(f'.//{ns_prefix}{tag}')
                        print(f"[ISAPI DEBUG] _find('{tag}') with ns='{ns_prefix}': {result is not None}")
                        return result
                    else:
                        # 直接查找当前节点的子节点
                        result = ch_elem.find(tag)
                        print(f"[ISAPI DEBUG] _find('{tag}') without ns: {result is not None}")
                        return result

                id_el     = _find('id')
                name_el   = _find('name')
                proto_el  = _find('proxyProtocol')  # 在sourceInputPortDescriptor下
                ip_el     = _find('ipAddress')      # 在sourceInputPortDescriptor下
                port_el   = _find('managePortNo')   # 在sourceInputPortDescriptor下
                online_el = _find('connectionStatus')

                if id_el is None:
                    return
                try:
                    no = int(id_el.text)
                except:
                    return

                channels[no] = {
                    'name': (name_el.text or f'通道{no}').strip() if name_el is not None else f'通道{no}',
                    'online': False,
                    'status': 'offline',
                    'protocol': (proto_el.text or '').strip().upper() if proto_el is not None else '',
                    'ip': (ip_el.text or '') if ip_el is not None else '',
                }

                print(f"[ISAPI DEBUG] Channel {no}: name='{channels[no]['name']}', protocol='{channels[no]['protocol']}', ip='{channels[no]['ip']}'")

                if online_el is not None:
                    has_connection_status = True
                    online = (online_el.text or '').strip().lower() in ('connect', 'connected', 'true', '1')
                    channels[no]['online'] = online
                    channels[no]['status'] = 'online' if online else 'offline'
                    print(f"[ISAPI DEBUG] Channel {no}: connectionStatus='{online_el.text}', online={online}")

            if ns:
                for ch in root.findall(f'.//{{{ns}}}InputProxyChannel'):
                    _parse_ch(ch, f'{{{ns}}}')
            else:
                for ch in root.findall('.//InputProxyChannel'):
                    _parse_ch(ch, '')

            if channels and not has_connection_status:
                self._enrich_status_from_status_api(channels)

        except Exception as e:
            print(f"[ISAPI] InputProxy异常: {e}")
        return channels

    def _enrich_status_from_status_api(self, channels: Dict[int, Dict]) -> None:
        """
        从 /ISAPI/ContentMgmt/InputProxy/channels/status 补充在线状态。
        新固件使用 <online>true/false</online> 字段。
        结果直接写回传入的 channels 字典。
        """
        try:
            url = f"{self.base_url}/ISAPI/ContentMgmt/InputProxy/channels/status"
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return

            print(f"[ISAPI DEBUG] InputProxy channels/status response length: {len(resp.text)}")
            print(f"[ISAPI DEBUG] First 1000 chars: {resp.text[:1000]}")
            
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
                    if ns_prefix:
                        # ns_prefix 已经包含花括号，直接使用
                        return ch_elem.find(f'.//{ns_prefix}{tag}')
                    else:
                        return ch_elem.find(tag)

                id_el     = _find('id')
                online_el = _find('online')
                detect_el = _find('chanDetectResult')
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
                except:
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
        获取所有通道信息（含在线状态）。
        返回 {channel_no: {'name': str, 'online': bool, 'status': str}}
        """
        channels = self._get_channels_from_input_proxy()
        if channels:
            online_count = sum(1 for c in channels.values() if c['online'])
            offline_count = len(channels) - online_count
            print(f"[ISAPI] 通道在线状态: {online_count}在线, {offline_count}离线/未知")
        return channels

    # ------------------------------------------------------------------ #
    #  通道流信息（分辨率/码率/编码）
    # ------------------------------------------------------------------ #

    def get_channel_stream_info(self) -> Dict[int, Dict]:
        """
        获取通道流信息（分辨率、码率、帧率、编码格式）。
        返回 {channel_no: {'main_stream': {...}, 'sub_stream': {...}}}
        """
        channels: Dict[int, Dict] = {}

        try:
            url = f"{self.base_url}/ISAPI/Streaming/channels"
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return channels

            print(f"[ISAPI DEBUG] Streaming channels response length: {len(resp.text)}")
            print(f"[ISAPI DEBUG] First 1000 chars: {resp.text[:1000]}")
            
            root = ET.fromstring(resp.text)

            # 探测命名空间
            ns_options = [
                'http://www.isapi.org/ver20/XMLSchema',
                'http://www.hikvision.com/ver20/XMLSchema',
            ]
            ns = None
            for ns_opt in ns_options:
                if root.find(f'.//{{{ns_opt}}}StreamingChannel') is not None:
                    ns = ns_opt
                    break

            search_path = f'.//{{{ns}}}StreamingChannel' if ns else './/StreamingChannel'
            id_tag = f'{{{ns}}}id' if ns else 'id'

            seen: set = set()

            for ch in root.findall(search_path):
                id_el = ch.find(id_tag)
                if id_el is None:
                    continue

                try:
                    raw_id = int(id_el.text)
                    ch_no = raw_id // 100
                    stream_idx = raw_id % 10  # 1=主码流, 2=子码流
                except:
                    continue

                if ch_no < 1 or ch_no > 256:
                    continue

                if ch_no not in channels:
                    channels[ch_no] = {'main_stream': {}, 'sub_stream': {}}

                # ns是不带花括号的URL，需要加上花括号再传递
                ns_with_braces = f'{{{ns}}}' if ns else ''
                stream_data = self._parse_stream_channel(ch, ns_with_braces)
                if stream_idx == 1:
                    channels[ch_no]['main_stream'] = stream_data
                elif stream_idx == 2:
                    channels[ch_no]['sub_stream'] = stream_data

        except Exception as e:
            print(f"[ISAPI] 获取通道流信息异常: {e}")

        return channels

    def _parse_stream_channel(self, ch, ns_prefix: str) -> Dict:
        """解析单个 StreamingChannel 节点，提取流参数"""
        info = {}

        def _find(tag):
            if ns_prefix:
                # ns_prefix 已经包含花括号，直接使用
                return ch.find(f'.//{ns_prefix}{tag}')
            else:
                return ch.find(tag)
        
        # DEBUG: 打印节点信息
        if ch.tag:
            print(f"[ISAPI DEBUG] Parsing StreamingChannel, tag={ch.tag}, ns_prefix={ns_prefix}")
            
        # DEBUG: 检查videoCodecType是否存在
        test_el = _find('videoCodecType')
        if test_el is None:
            # 尝试不带命名空间的查找
            test_el = ch.find('videoCodecType')
            print(f"[ISAPI DEBUG] videoCodecType not found with ns, direct find: {test_el is not None}")

        # 视频编码
        vc_el = _find('videoCodecType')
        if vc_el is not None:
            info['codec'] = (vc_el.text or 'N/A').strip().upper()

        # 视频编码等级（profile）
        profile_el = _find('videoCodecType')
        if profile_el is not None:
            raw = (profile_el.text or '').strip().upper()
            if raw in ('H.264', 'H264'):
                info['codec_profile'] = 'High Profile'  # 监控场景通常用High
            elif raw == 'H.265' or raw == 'HEVC':
                # 尝试找 extended codec type 或其他字段
                info['codec_profile'] = ''

        # 尝试从额外字段获取codecProfile
        for profile_tag in ['codecProfile', 'CodecProfile', 'videoCodecType']:
            pe = _find(profile_tag)
            if pe is not None and pe.text:
                text = pe.text.strip().upper()
                if 'HIGH' in text or 'HP' in text:
                    info['codec_profile'] = 'High Profile'
                    break
                elif 'MAIN' in text:
                    info['codec_profile'] = 'Main Profile'
                    break
                elif 'BASELINE' in text:
                    info['codec_profile'] = 'Baseline'
                    break

        # Smart Codec
        for sc_tag in ['smartCodec', 'SmartCodec', 'smart_codec', 'enabledSmartCodec']:
            sce = _find(sc_tag)
            if sce is not None and sce.text:
                info['smart_codec'] = sce.text.strip().lower() in ('true', '1', 'on')
                if info['smart_codec']:
                    # 尝试找smart codec类型
                    for sct_tag in ['smartCodecType', 'SmartCodecType']:
                        scte = _find(sct_tag)
                        if scte is not None and scte.text:
                            info['smart_codec_type'] = scte.text.strip()
                            break
                break

        # 分辨率
        for res_tag in ['videoResolutionWidth', 'videoResolutionHeight',
                        'resolution', 'Resolution']:
            w_el = _find(res_tag.replace('Height', '').replace('Height', ''))
            h_el = _find('videoResolutionHeight')
            if w_el is not None and h_el is not None:
                try:
                    info['resolution'] = f"{int(w_el.text)}x{int(h_el.text)}"
                    break
                except:
                    pass
            # 直接从 resolution 标签
            res_el = _find('resolution')
            if res_el is not None and res_el.text:
                info['resolution'] = res_el.text.strip()
                break

        # 码率
        for br_tag in ['videoBitrate', 'videoBitRate', 'constantBitRate', 'bitrate', 'Bitrate']:
            bre = _find(br_tag)
            if bre is not None and bre.text:
                try:
                    info['bitrate_kbps'] = int(float(bre.text))
                    break
                except:
                    pass

        # 码率模式
        for brm_tag in ['bitrateType', 'bitrateMode', 'BitrateType', 'BitrateMode']:
            brme = _find(brm_tag)
            if brme is not None and brme.text:
                raw = brme.text.strip().upper()
                if raw in ('1', 'VBR', 'VAR'):
                    info['bitrate_mode'] = 'VBR (可变码率)'
                elif raw in ('2', 'CBR'):
                    info['bitrate_mode'] = 'CBR (固定码率)'
                else:
                    info['bitrate_mode'] = raw
                break

        # 帧率
        for fps_tag in ['videoFrameRate', 'frameRate', 'FrameRate', 'fps', 'FPS']:
            fpse = _find(fps_tag)
            if fpse is not None and fpse.text:
                try:
                    info['fps'] = int(float(fpse.text))
                    break
                except:
                    pass

        # 码率上限（VBR时参考）
        for ubr_tag in ['upperBitrate', 'upperBitRate', 'maxBitrate']:
            incre = _find(ubr_tag)
            if incre is not None and incre.text:
                try:
                    info['upper_bitrate'] = int(float(incre.text))
                    break
                except:
                    pass

        # 峰值码率
        for pbr_tag in ['peakBitrate', 'peakBitRate']:
            incre = _find(pbr_tag)
            if incre is not None and incre.text:
                try:
                    info['peak_bitrate'] = int(float(incre.text))
                    break
                except:
                    pass

        return info
