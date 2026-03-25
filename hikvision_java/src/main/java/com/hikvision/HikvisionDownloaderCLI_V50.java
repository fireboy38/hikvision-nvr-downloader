package com.hikvision;

import com.sun.jna.NativeLong;
import com.sun.jna.WString;
import com.sun.jna.examples.win32.W32API.HWND;

import java.io.File;

/**
 * 海康NVR录像下载器 CLI - V50版本
 * 
 * 使用 NET_DVR_PlayBackByTime_V50 + byDownload=1 直接下载，无1GB文件限制
 * 
 * 用法:
 * java HikvisionDownloaderCLI_V50 <ip> <port> <username> <password> <channel>
 *                               <start_time> <end_time> <save_path> <channel_name>
 * 
 * 时间格式: yyyy-MM-dd HH:mm:ss
 */
public class HikvisionDownloaderCLI_V50 {
    
    public static void main(String[] args) {
        if (args.length < 9) {
            System.err.println("用法: HikvisionDownloaderCLI_V50 <ip> <port> <username> <password> <channel> " +
                             "<start_time> <end_time> <save_path> <channel_name>");
            System.err.println("时间格式: yyyy-MM-dd HH:mm:ss");
            System.exit(1);
        }
        
        String ip = args[0];
        int port = Integer.parseInt(args[1]);
        String username = args[2];
        String password = args[3];
        int channel = Integer.parseInt(args[4]);
        String startTime = args[5];
        String endTime = args[6];
        String savePath = args[7];
        String channelName = args[8];
        
        // 解析时间
        HCNetSDK_V50.NET_DVR_TIME_V50 start = parseTime(startTime);
        HCNetSDK_V50.NET_DVR_TIME_V50 end = parseTime(endTime);
        
        int durationSec = calcDurationSec(start, end);
        System.out.println("下载参数:");
        System.out.println("  NVR: " + ip + ":" + port);
        System.out.println("  通道: " + channel + " (" + channelName + ")");
        System.out.println("  时间: " + startTime + " ~ " + endTime + " (" + durationSec + "秒)");
        System.out.println("  保存: " + savePath);
        System.out.println("  方式: V50 PlayBackByTime + byDownload=1");
        System.out.println();
        
        try {
            downloadByV50(ip, port, username, password, channel, start, end, savePath, channelName, durationSec);
        } catch (Exception e) {
            System.err.println("下载失败: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }
    
    private static HCNetSDK_V50.NET_DVR_TIME_V50 parseTime(String timeStr) {
        // 格式: yyyy-MM-dd HH:mm:ss
        String[] parts = timeStr.split("[ -:]");
        HCNetSDK_V50.NET_DVR_TIME_V50 time = new HCNetSDK_V50.NET_DVR_TIME_V50();
        time.wYear = Short.parseShort(parts[0]);
        time.byMonth = Byte.parseByte(parts[1]);
        time.byDay = Byte.parseByte(parts[2]);
        time.byHour = Byte.parseByte(parts[3]);
        time.byMinute = Byte.parseByte(parts[4]);
        time.bySecond = Byte.parseByte(parts[5]);
        time.wMillisecond = 0;
        time.byRes = 0;
        return time;
    }
    
    private static int calcDurationSec(HCNetSDK_V50.NET_DVR_TIME_V50 start, HCNetSDK_V50.NET_DVR_TIME_V50 end) {
        long startSec = toSeconds(start);
        long endSec = toSeconds(end);
        return (int)(endSec - startSec);
    }
    
    private static long toSeconds(HCNetSDK_V50.NET_DVR_TIME_V50 time) {
        return time.wYear * 31536000L + time.byMonth * 2592000L + time.byDay * 86400L +
               time.byHour * 3600L + time.byMinute * 60L + time.bySecond;
    }
    
    private static void downloadByV50(
            String ip, int port, String username, String password, int channel,
            HCNetSDK_V50.NET_DVR_TIME_V50 startTime, HCNetSDK_V50.NET_DVR_TIME_V50 endTime,
            String savePath, String channelName, int durationSec) throws Exception {
        
        HCNetSDK sdk = HCNetSDK.INSTANCE;
        
        // 初始化
        if (!sdk.NET_DVR_Init()) {
            throw new RuntimeException("SDK初始化失败: " + sdk.NET_DVR_GetLastError());
        }
        try {
            // 登录
            HCNetSDK.NET_DVR_USER_LOGIN_INFO loginInfo = new HCNetSDK.NET_DVR_USER_LOGIN_INFO();
            loginInfo.bUseAsynLogin = 0;
            loginInfo.sDeviceAddress = new WString(ip);
            loginInfo.wPort = (short)port;
            loginInfo.sUserName = new WString(username);
            loginInfo.sPassword = new WString(password);
            
            HCNetSDK.NET_DVR_DEVICEINFO_V40 deviceInfo = new HCNetSDK.NET_DVR_DEVICEINFO_V40();
            
            NativeLong lUserID = sdk.NET_DVR_Login_V40(loginInfo, deviceInfo);
            if (lUserID.intValue() < 0) {
                throw new RuntimeException("登录失败: " + sdk.NET_DVR_GetLastError());
            }
            System.out.println("登录成功: " + new String(deviceInfo.sSerialNumber).trim());
            
            try {
                // 构建 VOD_PARA_V50
                HCNetSDK_V50.NET_DVR_VOD_PARA_V50 vodPara = new HCNetSDK_V50.NET_DVR_VOD_PARA_V50();
                vodPara.dwSize = vodPara.size();
                
                // 流信息
                vodPara.struIDInfo = new HCNetSDK_V50.NET_DVR_STREAM_INFO();
                vodPara.struIDInfo.dwSize = vodPara.struIDInfo.size();
                vodPara.struIDInfo.dwChannel = channel;
                
                // 时间
                vodPara.struBeginTime = startTime;
                vodPara.struEndTime = endTime;
                
                // 无窗口（纯下载，不回放）
                vodPara.hWnd = null;
                vodPara.byDrawFrame = 0;
                vodPara.byStreamType = 0;  // 主码流
                vodPara.byPlayMode = 0;    // 正放
                vodPara.byLinkMode = 0;    // TCP
                vodPara.byDownload = 1;     // 直接下载!
                vodPara.byOptimalStreamType = 0;
                vodPara.byDisplayBufNum = 0;
                vodPara.byNPQMode = 0;
                
                // 二次认证（默认不用）
                for (int i = 0; i < 32; i++) vodPara.sUserName[i] = 0;
                for (int i = 0; i < 16; i++) vodPara.sPassword[i] = 0;
                
                vodPara.byRemoteFile = 0;
                for (int i = 0; i < 202; i++) vodPara.byRes2[i] = 0;
                vodPara.byHls = 0;
                
                // 保存文件路径
                vodPara.pSavedFileName = savePath;
                
                System.out.println("开始下载...");
                
                // 调用 PlayBackByTime_V50 + byDownload=1
                NativeLong hPlayback = sdk.NET_DVR_PlayBackByTime_V50(lUserID, vodPara);
                if (hPlayback.intValue() < 0) {
                    int err = sdk.NET_DVR_GetLastError();
                    throw new RuntimeException("PlayBackByTime_V50失败: " + err);
                }
                
                // 必须调用开始播放控制
                if (!sdk.NET_DVR_PlayBackControl_V40(
                        hPlayback, 
                        HCNetSDK.NET_DVR_PLAYSTART, 
                        null, 0, null, null)) {
                    int err = sdk.NET_DVR_GetLastError();
                    sdk.NET_DVR_StopGetFile(hPlayback);
                    throw new RuntimeException("开始下载失败: " + err);
                }
                
                System.out.println("下载中...");
                
                // 监控进度
                long lastOutput = System.currentTimeMillis();
                int lastProgress = 0;
                int progress;
                while (true) {
                    progress = sdk.NET_DVR_GetDownloadPos(hPlayback);
                    
                    // 每10秒输出一次进度
                    long now = System.currentTimeMillis();
                    if (now - lastOutput > 10000 && progress != lastProgress) {
                        System.out.println("  进度: " + progress + "%");
                        lastOutput = now;
                        lastProgress = progress;
                    }
                    
                    if (progress >= 100 || progress < 0) {
                        break;
                    }
                    
                    Thread.sleep(1000);
                }
                
                // 停止下载
                if (!sdk.NET_DVR_StopGetFile(hPlayback)) {
                    System.err.println("停止下载失败: " + sdk.NET_DVR_GetLastError());
                }
                
                if (progress < 0 || progress > 100) {
                    int err = sdk.NET_DVR_GetLastError();
                    throw new RuntimeException("下载失败: " + err + " (进度=" + progress + ")");
                }
                
                System.out.println("下载完成: " + progress + "%");
                
                // 检查文件
                File f = new File(savePath);
                if (!f.exists() || f.length() == 0) {
                    throw new RuntimeException("下载文件为空或不存在");
                }
                System.out.println("文件大小: " + (f.length() / 1024.0 / 1024.0) + " MB");
                
            } finally {
                sdk.NET_DVR_Logout(lUserID);
            }
        } finally {
            sdk.NET_DVR_Cleanup();
        }
    }
}
