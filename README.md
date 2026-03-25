# 海康威视 NVR 批量录像下载器

基于 PyQt5 开发的海康威视 NVR 录像批量下载工具，支持通过 ISAPI 接口获取通道信息，使用 Java SDK 进行高效录像下载。

## 功能特性

- 📹 **批量下载** - 支持多通道同时下载录像
- ⏱️ **时间选择** - 灵活的开始/结束时间设置
- 📊 **进度显示** - 实时显示下载进度和速度
- 🔧 **智能分段** - 长录像自动分段下载并合并
- 📁 **设备管理** - 支持设备列表的导入/导出 (CSV)
- 🖥️ **友好界面** - 直观的图形化操作界面

## 系统要求

- Windows 7/10/11
- Python 3.8+
- Java Runtime Environment (JRE) 8+
- 海康威视 NVR 设备

## 安装

### 1. 克隆仓库
```bash
git clone https://github.com/你的用户名/hikvision-nvr-downloader.git
cd hikvision-nvr-downloader
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置海康 SDK
将海康 SDK 的 DLL 文件放置在 `hikvision_java/库文件/` 目录下。

## 使用方法

### 启动程序
```bash
cd hikvision_downloader
python main.py
```

### 操作步骤

1. **添加设备**
   - 点击 "➕ 添加设备"
   - 填写 NVR IP、端口、用户名、密码

2. **连接设备**
   - 点击 "🔌 连接设备"
   - 获取通道列表和设备信息

3. **选择通道**
   - 勾选需要下载的通道
   - 支持全选/取消全选

4. **设置时间**
   - 选择开始时间和结束时间
   - 支持快速选择今天、昨天、最近7天等

5. **开始下载**
   - 点击 "▶ 开始下载"
   - 查看下载进度和日志

### 设备列表导入/导出

**导出设备列表：**
- 点击 "📤 导出设备列表"
- 保存为 CSV 文件

**导入设备列表：**
- 点击 "📥 导入设备列表"
- 选择 CSV 文件
- 支持追加或替换现有设备

CSV 格式示例：
```csv
name,ip,port,username,password
NVR-主楼,192.168.1.100,8000,admin,password123
NVR-仓库,192.168.1.101,8000,admin,password456
```

## 项目结构

```
hikvision_downloader/
├── main.py                 # 程序入口
├── core/
│   ├── nvr_api.py         # ISAPI 接口封装
│   ├── java_downloader.py # Java SDK 下载器
│   └── downloader.py      # 下载管理器
├── gui/
│   └── main_window.py     # 主界面
└── downloads/             # 下载文件保存目录

hikvision_java/            # Java SDK 项目
├── src/
│   └── main/java/com/hikvision/
│       └── HikvisionDownloaderCLI.java
└── 库文件/                # SDK DLL 文件
```

## 技术方案

- **通道信息获取**: ISAPI 接口 (XML/JSON)
- **录像下载**: Java SDK (HCNetSDK) 通过 JNA 调用
- **视频处理**: FFmpeg (用于合并和格式转换)
- **GUI 框架**: PyQt5

## 注意事项

1. **NVR 固件版本**: 建议使用 V4.2.0 以上版本以获得最佳兼容性
2. **存储空间**: 确保下载目录有足够的磁盘空间
3. **网络稳定**: 下载过程中保持网络连接稳定
4. **SDK 版本**: 使用与海康设备匹配的 SDK 版本

## 常见问题

**Q: 连接设备失败？**
A: 检查 IP 地址、端口、用户名密码是否正确，确保设备在线。

**Q: 下载速度很慢？**
A: 检查网络带宽，或尝试减少同时下载的通道数。

**Q: 视频无法播放？**
A: 尝试取消 "跳过转码" 选项，让程序转换为标准 MP4 格式。

## 许可证

MIT License

## 致谢

- 海康威视 SDK
- PyQt5
- FFmpeg