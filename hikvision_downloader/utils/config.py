# 配置管理模块
import os
import json
from typing import Dict, Any, List


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: str = None):
        if config_file is None:
            config_dir = os.path.join(os.path.expanduser("~"), ".hikvision_downloader")
            os.makedirs(config_dir, exist_ok=True)
            config_file = os.path.join(config_dir, "config.json")
        
        self.config_file = config_file
        self.config: Dict[str, Any] = {}
        self.load()
    
    def load(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"加载配置失败: {e}")
                self.config = self.get_default_config()
        else:
            self.config = self.get_default_config()
    
    def save(self):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'devices': [],
            'download_dir': os.path.expanduser("~/Downloads"),
            'max_concurrent': 3,
            'auto_merge': True,
            'log_level': 'INFO'
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        self.config[key] = value
    
    @property
    def devices(self) -> List[Dict]:
        """获取设备列表"""
        return self.config.get('devices', [])
    
    @devices.setter
    def devices(self, value: List[Dict]):
        self.config['devices'] = value
    
    @property
    def download_dir(self) -> str:
        """获取下载目录"""
        return self.config.get('download_dir', os.path.expanduser("~/Downloads"))
    
    @download_dir.setter
    def download_dir(self, value: str):
        self.config['download_dir'] = value
    
    @property
    def max_concurrent(self) -> int:
        """获取最大并发数"""
        return self.config.get('max_concurrent', 3)
    
    @max_concurrent.setter
    def max_concurrent(self, value: int):
        self.config['max_concurrent'] = value
    
    @property
    def auto_merge(self) -> bool:
        """获取是否自动合并"""
        return self.config.get('auto_merge', True)
    
    @auto_merge.setter
    def auto_merge(self, value: bool):
        self.config['auto_merge'] = value
