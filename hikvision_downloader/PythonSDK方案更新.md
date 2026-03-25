# Python SDK 下载方案更新说明

## 问题回顾

用户发现：
1. 10分钟录像下载卡死
2. 下载成功但程序提示失败
3. 通道名称是乱码（显示"通道1"而不是实际名称）

## 根本原因

### 关键发现
用户提供的代码使用了正确的进度查询接口：
```python
status = HCNetSDK.NET_DVR_GetDownloadPos(download_handle)
```

而我们之前错误地使用了：
```java
sdk.NET_DVR_PlayBackControl(downloadHandle, NET_DVR_PLAYGETPOS, 0, pos);
```

**NET_DVR_PlayBackControl** 是回放控制接口，**NET_DVR_GetDownloadPos** 才是下载进度查询接口！

## 解决方案

### 1. 创建新的Python SDK下载器

**文件**: `core/hiksdk_downloader.py`

**关键改进**：
- 使用 `NET_DVR_GetDownloadPos` 获取下载进度（0-100%）
- 使用 `NET_DVR_GetFileByTime` 按时间下载录像
- 自动通道号转换（原始通道号+32）
- 动态超时计算（15分钟 + 每小时40分钟）
- 单例登录状态管理

**核心代码**：
```python
# 开始下载
if not HCNetSDK.NET_DVR_PlayBackControl(download_handle, NET_DVR_PLAYSTART, 0, None):
    return False, f"启动下载失败"

# 监控进度
while True:
    # 关键：使用正确的进度查询接口
    status = HCNetSDK.NET_DVR_GetDownloadPos(download_handle)
    
    if progress_callback:
        progress_callback(status)
    
    if status == 100:
        return True, "下载成功"
    
    if status == -1:
        return False, "下载失败"
    
    time.sleep(2)
```

### 2. 修改下载管理器

**文件**: `core/downloader.py`

**关键改进**：
- 替换Java下载器为Python SDK下载器
- 修改文件名生成逻辑：
  - 通道名是"通道X"时，使用"CH1"格式
  - 通道名是实际名称时，使用原名称
- 添加调试信息输出

**文件名生成**：
```python
if self.channel_name.startswith('通道'):
    # 提取通道号
    match = re.search(r'\d+', self.channel_name)
    if match:
        channel_no = match.group()
        safe_name = f"CH{channel_no}"  # "通道1" -> "CH1"
    else:
        safe_name = self.channel_name
else:
    safe_name = self.channel_name
```

### 3. 通道名称获取

**当前状态**：ISAPI接口获取通道名称失败，返回0个通道

**临时方案**：使用默认通道名称（通道1, 通道2, ...）

**文件名显示**：
- 默认：`设备_CH1_20260324_150000_151000.mp4`
- 如果有实际名称：`设备_正大门停车场通道1_20260324_150000_151000.mp4`

## 测试结果

### 命令行测试
```bash
cd hikvision_downloader
py -3 core/hiksdk_downloader.py
```

**结果**：
- ✅ 进度正常显示（0% → 100%）
- ✅ 下载成功完成
- ✅ 文件大小正常

### GUI测试
```bash
cd hikvision_downloader
py -3 main.py
```

**预期结果**：
- 进度条正常更新
- 下载完成后提示成功
- 文件名格式清晰（CH1, CH2等）

## 关键改进对比

| 项目 | Java方案（旧） | Python SDK方案（新） |
|-----|---------------|---------------------|
| 进度查询接口 | PlayBackControl（错误） | GetDownloadPos（正确）✅ |
| 进度显示 | 一直是0% | 正常0-100%✅ |
| 下载完成判定 | 文件大小稳定 | SDK返回100%✅ |
| 超时处理 | 3分钟固定 | 动态计算（15分钟起）✅ |
| 文件名 | 通道名可能乱码 | 简化为CH1格式✅ |

## 已知限制

1. **通道名称获取**
   - ISAPI接口返回0个通道
   - 临时使用"通道1"、"通道2"等默认名称
   - 文件名自动转换为CH1、CH2格式

2. **通道号转换**
   - 原始通道号+32（海康NVR规范）
   - 自动处理，用户无需关心

## 下一步优化建议

1. **通道名称获取**
   - 尝试使用SDK的配置查询接口获取通道配置
   - 接口：`NET_DVR_GetDVRConfig`
   - 命令：`NET_DVR_GET_IPPARACFG_V40 = 3399`

2. **录像完整性验证**
   - 下载后用FFprobe检查视频时长
   - 对比请求时长和实际时长
   - 不匹配时提示重新下载

3. **错误处理增强**
   - 网络断线自动重连
   - 超时后自动重试
   - 多文件并发下载优化

## 修改的文件

1. `core/hiksdk_downloader.py` - 新增Python SDK下载器
2. `core/downloader.py` - 修改下载管理器使用新下载器
3. `core/java_downloader.py` - 保留备用（不再使用）

## 测试清单

- [x] 命令行测试 - 5分钟下载成功
- [x] 进度显示 - 正常0-100%
- [x] 文件生成 - 成功保存
- [ ] GUI测试 - 等待用户确认
- [ ] 长时间测试（1小时） - 待测试
- [ ] 多通道并发 - 待测试
- [ ] 录像完整性验证 - 待测试
