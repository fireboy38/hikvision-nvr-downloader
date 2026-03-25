# 海康NVR批量录像下载工具
# Hikvision NVR Batch Video Downloader

## 项目简介
基于海康威视NVR设备的ISAPI接口和SDK开发的批量录像下载工具，支持多通道录像批量下载和自动合并打包。

## 环境要求
- Python 3.8+
- PyQt5 >= 5.15
- requests >= 2.25
- opencv-python >= 4.5
- ffmpeg-python >= 0.2

## 安装依赖
```bash
pip install -r requirements.txt
```

## 功能特性
1. **设备连接管理** - 支持多台NVR设备添加、编辑、删除
2. **通道管理** - 自动获取设备通道列表，支持通道选择
3. **时间范围选择** - 可视化时间选择器，支持多日期范围
4. **批量下载** - 多线程并行下载，支持断点续传
5. **视频合并** - 自动将每通道的视频打包成一个完整视频
6. **任务监控** - 实时显示下载进度、速度、剩余时间

## 使用说明
1. 运行程序：`python main.py`
2. 添加NVR设备（IP地址、端口、用户名、密码）
3. 选择需要下载的通道
4. 选择录像时间范围
5. 点击开始下载
6. 下载完成后自动合并视频

## 目录结构
```
hikvision_downloader/
├── core/               # 核心模块
│   ├── nvr_api.py      # 海康NVR API封装
│   ├── downloader.py   # 下载管理器
│   └── merger.py       # 视频合并工具
├── gui/                # GUI界面
│   ├── main_window.py  # 主窗口
│   ├── device_dialog.py # 设备配置对话框
│   └── widgets.py      # 自定义组件
├── utils/              # 工具模块
│   ├── config.py       # 配置管理
│   └── logger.py       # 日志工具
├── resources/          # 资源文件
├── main.py            # 程序入口
└── requirements.txt   # 依赖列表
```

## 注意事项
1. 确保NVR设备已开启ISAPI服务
2. 建议使用管理员账户操作
3. 下载路径确保有足够磁盘空间
4. 确保网络连接稳定
