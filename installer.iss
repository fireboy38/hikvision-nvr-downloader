; 四川新数录像批量下载器 - Inno Setup 安装脚本
; 需要安装 Inno Setup: https://jrsoftware.org/isinfo.php

#define MyAppName "四川新数录像批量下载器"
#define MyAppVersion "2.0"
#define MyAppPublisher "四川新数信息技术有限公司"
#define MyAppURL "http://www.scxs.vip"
#define MyAppExeName "四川新数录像批量下载器.exe"

[Setup]
AppId={{E8B7F8A1-2D3C-4B5A-9F1E-8C7D9A2B3E4F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\四川新数录像批量下载器
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=installer
OutputBaseFilename=四川新数录像批量下载器-安装程序-v2.0
Compression=lzma
SolidCompression=yes
WizardStyle=modern

; 管理员权限
PrivilegesRequired=admin

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimp.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
; 主程序
Source: "dist\四川新数录像批量下载器_完整版\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; _internal 目录（包含所有DLL和依赖）
Source: "dist\四川新数录像批量下载器_完整版\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

; Java 组件
Source: "dist\四川新数录像批量下载器_完整版\java\*"; DestDir: "{app}\java"; Flags: ignoreversion recursesubdirs createallsubdirs

; 配置文件
Source: "hikvision_java\DemoLocalCfg.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "hikvision_java\DeviceCfg.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
