// 测试 NET_DVR_PlayBackByTime_V50 + byDownload=1 接口
// 编译: g++ test_v50.cpp -I"C:\Users\Administrator\Downloads\HCNetSDKV6.1.11.5_build20251204_Win64_ZH_20260320151956\HCNetSDKV6.1.11.5_build20251204_Win64_ZH" -L"C:\Users\Administrator\Downloads\HCNetSDKV6.1.11.5_build20251204_Win64_ZH_20260320151956\HCNetSDKV6.1.11.5_build20251204_Win64_ZH\库文件" -lHCNetSDK -o test_v50.exe
// 运行需要: test_v50.exe 10.26.223.253 8000 admin a1111111 1 2026-03-25_07:00:00 2026-03-25_08:00:00 test_v50.mp4

#include <windows.h>
#include <stdio.h>
#include "HCNetSDK.h"

int main(int argc, char* argv[]) {
    if (argc < 9) {
        printf("用法: test_v50.exe <ip> <port> <user> <pass> <channel> <start_time> <end_time> <save_path>\n");
        printf("时间格式: yyyy-MM-dd_HH:mm:ss\n");
        return 1;
    }

    char* ip = argv[1];
    WORD port = atoi(argv[2]);
    char* user = argv[3];
    char* pass = argv[4];
    LONG channel = atol(argv[5]);
    char* startTime = argv[6];
    char* endTime = argv[7];
    char* savePath = argv[8];

    printf("=== 测试 V50 接口下载 ===\n");
    printf("NVR: %s:%d\n", ip, port);
    printf("通道: %d\n", channel);
    printf("时间: %s ~ %s\n", startTime, endTime);
    printf("保存: %s\n\n", savePath);

    // 初始化
    NET_DVR_Init();
    NET_DVR_SetConnectTime(2000, 1);
    NET_DVR_SetReconnect(10000, TRUE);

    // 登录
    NET_DVR_USER_LOGIN_INFO loginInfo = {0};
    loginInfo.bUseAsynLogin = 0;
    strcpy_s(loginInfo.sDeviceAddress, ip);
    loginInfo.wPort = port;
    strcpy_s(loginInfo.sUserName, user);
    strcpy_s(loginInfo.sPassword, pass);

    NET_DVR_DEVICEINFO_V40 deviceInfo = {0};
    LONG lUserID = NET_DVR_Login_V40(&loginInfo, &deviceInfo);
    if (lUserID < 0) {
        printf("登录失败: %d\n", NET_DVR_GetLastError());
        NET_DVR_Cleanup();
        return 1;
    }
    printf("登录成功\n");

    // 构建 NET_DVR_VOD_PARA_V50
    NET_DVR_VOD_PARA_V50 vodPara = {0};
    vodPara.dwSize = sizeof(NET_DVR_VOD_PARA_V50);

    // 流信息
    vodPara.struIDInfo.dwSize = sizeof(NET_DVR_STREAM_INFO);
    vodPara.struIDInfo.dwChannel = channel;

    // 解析时间 (yyyy-MM-dd_HH:mm:ss)
    sscanf_s(startTime, "%hd-%hhu-%hhu_%hhu:%hhu:%hhu",
        &vodPara.struBeginTime.wYear,
        &vodPara.struBeginTime.byMonth,
        &vodPara.struBeginTime.byDay,
        &vodPara.struBeginTime.byHour,
        &vodPara.struBeginTime.byMinute,
        &vodPara.struBeginTime.bySecond);
    sscanf_s(endTime, "%hd-%hhu-%hhu_%hhu:%hhu:%hhu",
        &vodPara.struEndTime.wYear,
        &vodPara.struEndTime.byMonth,
        &vodPara.struEndTime.byDay,
        &vodPara.struEndTime.byHour,
        &vodPara.struEndTime.byMinute,
        &vodPara.struEndTime.bySecond);

    vodPara.hWnd = NULL;
    vodPara.byDrawFrame = 0;
    vodPara.byStreamType = 0;  // 主码流
    vodPara.byPlayMode = 0;
    vodPara.byLinkMode = 0;
    vodPara.byDownload = 1;   // 直接下载!
    vodPara.byOptimalStreamType = 0;
    vodPara.byDisplayBufNum = 0;
    vodPara.byNPQMode = 0;
    memset(vodPara.sUserName, 0, 32);
    memset(vodPara.sPassword, 0, 16);
    vodPara.byRemoteFile = 0;
    memset(vodPara.byRes2, 0, 202);
    vodPara.byHls = 0;
    vodPara.pSavedFileName = savePath;

    printf("开始下载...\n");

    // 调用 PlayBackByTime_V50
    LONG hPlayback = NET_DVR_PlayBackByTime_V50(lUserID, &vodPara);
    if (hPlayback < 0) {
        printf("PlayBackByTime_V50 失败: %d\n", NET_DVR_GetLastError());
        NET_DVR_Logout(lUserID);
        NET_DVR_Cleanup();
        return 1;
    }

    // 开始播放控制（必须调用）
    if (!NET_DVR_PlayBackControl_V40(hPlayback, NET_DVR_PLAYSTART, NULL, 0, NULL, NULL)) {
        printf("开始下载失败: %d\n", NET_DVR_GetLastError());
        NET_DVR_StopGetFile(hPlayback);
        NET_DVR_Logout(lUserID);
        NET_DVR_Cleanup();
        return 1;
    }

    printf("下载中...\n");

    // 监控进度
    int progress = 0;
    int lastProgress = -1;
    while (true) {
        progress = NET_DVR_GetDownloadPos(hPlayback);
        if (progress != lastProgress && progress % 10 == 0) {
            printf("进度: %d%%\n", progress);
            lastProgress = progress;
        }
        if (progress >= 100 || progress < 0) {
            break;
        }
        Sleep(2000);
    }

    // 停止下载
    if (!NET_DVR_StopGetFile(hPlayback)) {
        printf("停止下载失败: %d\n", NET_DVR_GetLastError());
    }

    printf("下载完成: %d%%\n", progress);

    if (progress < 0 || progress > 100) {
        printf("下载失败: %d\n", NET_DVR_GetLastError());
        NET_DVR_Logout(lUserID);
        NET_DVR_Cleanup();
        return 1;
    }

    // 检查文件大小
    WIN32_FILE_ATTRIBUTE_DATA fileInfo;
    if (GetFileAttributesExA(savePath, GetFileExInfoStandard, &fileInfo)) {
        LARGE_INTEGER size;
        size.LowPart = fileInfo.nFileSizeLow;
        size.HighPart = fileInfo.nFileSizeHigh;
        printf("文件大小: %.2f MB\n", size.QuadPart / 1024.0 / 1024.0);
    }

    NET_DVR_Logout(lUserID);
    NET_DVR_Cleanup();

    printf("=== 测试完成 ===\n");
    return 0;
}
