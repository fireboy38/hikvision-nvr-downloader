# 构建说明

## 快速开始

### 方式1：下载预编译版本

前往 [Releases](../../releases) 页面下载最新版本。

**注意**：
- GitHub Actions构建的版本**不包含SDK DLL**
- ISAPI模式可直接使用，无需SDK
- 如需SDK模式，请使用方式2本地构建

### 方式2：本地完整构建

#### 前置条件

1. Python 3.11+
2. 海康威视SDK（从官网下载）

#### 步骤

```bash
# 1. 克隆仓库
git clone https://github.com/你的用户名/你的仓库.git
cd 你的仓库

# 2. 安装依赖
pip install -r requirements.txt
pip install pyinstaller

# 3. 下载海康SDK
# 从海康官网下载：https://www.hikvision.com/cn/support/download/sdk/
# 解压到任意目录

# 4. 修改 build_with_dll.spec 中的SDK路径
# SDK_PATH = r"你的SDK路径\库文件"

# 5. 构建完整版（DLL嵌入exe）
cd hikvision_downloader
python -m PyInstaller --noconfirm --clean build_with_dll.spec

# 6. 输出文件
# dist/四川新数录像批量下载器_完整版.exe
```

## 三种打包方式对比

| 方式 | 文件大小 | 分发 | 说明 |
|------|----------|------|------|
| `build-exe.bat` | ~86MB + DLL文件夹 | 需要整个文件夹 | 绿色版，启动快 |
| `build-standalone.bat` | ~99MB 单文件 | 单个exe | 完整版，DLL嵌入 |
| GitHub Actions | ~86MB 单文件 | 单个exe | 不含SDK，仅ISAPI模式 |

## 运行模式说明

### ISAPI模式（推荐）
- 纯HTTP下载，无需SDK
- 速度快，稳定性好
- 所有版本都支持

### SDK模式
- 需要海康SDK DLL文件
- 支持分段下载、转码等高级功能
- 需要完整版或在exe同目录放置DLL

## DLL文件清单（SDK模式需要）

```
程序目录/
├── 四川新数录像批量下载器.exe
├── HCNetSDK.dll
├── HCCore.dll
├── hpr.dll
├── PlayCtrl.dll
├── StreamTransClient.dll
├── SuperRender.dll
├── AudioRender.dll
├── GdiPlus.dll
└── HCNetSDKCom/
    ├── AnalyzeData.dll
    ├── AudioIntercom.dll
    ├── HCAlarm.dll
    ├── HCCoreDevCfg.dll
    ├── HCDisplay.dll
    ├── HCGeneralCfgMgr.dll
    ├── HCIndustry.dll
    ├── HCPlayBack.dll
    ├── HCPreview.dll
    ├── HCVoiceTalk.dll
    ├── libiconv2.dll
    ├── OpenAL32.dll
    ├── StreamTransClient.dll
    └── SystemTransform.dll
```

## 版本发布

### Nightly版本
- 每次推送到main分支自动构建
- 包含最新功能，可能不稳定
- 标签：`nightly`

### 稳定版本
- 创建以`v`开头的tag时自动发布
- 例如：`git tag v1.0.0 && git push --tags`
- 正式版本，推荐使用

## 常见问题

### Q: 为什么GitHub版本不能使用SDK模式？
A: 海康SDK有版权限制，不能公开分发。请下载本地完整版或自行构建。

### Q: 如何获取海康SDK？
A: 访问海康威视官网下载中心：https://www.hikvision.com/cn/support/download/sdk/

### Q: ISAPI模式和SDK模式哪个好？
A: 推荐ISAPI模式，纯HTTP下载，无需SDK，速度快且稳定。

## 技术支持

- 问题反馈：[Issues](../../issues)
- 版权所有：四川新数信息技术有限公司
- 网站：www.scxs.vip
