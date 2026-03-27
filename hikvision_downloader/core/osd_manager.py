# OSD管理模块
# 职责：通道OSD（屏幕显示）名称设置
import re


class OSDManagerMixin:
    """
    提供通道OSD名称设置能力。
    混入到 HikvisionISAPI 主类使用。
    """

    def set_channel_osd(self, channel_no: int, osd_name: str, enabled: bool = True) -> tuple:
        """
        设置通道OSD名称（实际上是修改通道名称）。

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
            url = f"{self.base_url}/ISAPI/ContentMgmt/InputProxy/channels/{channel_no}"
            resp = self.session.get(url, timeout=10)

            if resp.status_code != 200:
                return False, f"获取通道配置失败: HTTP {resp.status_code}"

            original_xml = resp.text

            # 使用正则表达式替换 <name> 标签内容
            name_pattern = r'(<name[^>]*>)[^<]*(</name>)'
            match = re.search(name_pattern, original_xml)

            if match:
                new_xml = re.sub(name_pattern, rf'\g<1>{osd_name}\g<2>', original_xml)
            else:
                # 如果没有 name 标签，在根元素内添加
                insert_pattern = r'(<InputProxyChannel[^>]*>)'
                new_xml = re.sub(insert_pattern, rf'\g<1>\n<name>{osd_name}</name>', original_xml, count=1)

            headers = {'Content-Type': 'application/xml'}
            resp = self.session.put(url, data=new_xml.encode('utf-8'), headers=headers, timeout=10)

            if resp.status_code == 200:
                return True, f"通道{channel_no} 名称/OSD更新成功"
            else:
                error_detail = resp.text[:300] if resp.text else "无响应内容"
                return False, f"更新通道名称失败: HTTP {resp.status_code} - {error_detail}"

        except Exception as e:
            print(f"[OSD] 异常: {e}")
            print(f"[OSD] 异常详情: {traceback.format_exc()}")
            return False, f"设置OSD异常: {str(e)}"
