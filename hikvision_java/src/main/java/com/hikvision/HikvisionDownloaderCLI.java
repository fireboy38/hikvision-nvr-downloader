package com.hikvision;

import com.sun.jna.Library;
import com.sun.jna.Native;
import com.sun.jna.NativeLong;
import com.sun.jna.Structure;
import com.sun.jna.ptr.IntByReference;
import java.util.Arrays;
import java.util.List;

/**
 * Hikvision SDK Java CLI
 *
 * 智能接口选择策略：
 * 1. 优先使用 NET_DVR_GetFileByTime_V40/V50（无1GB文件大小限制）
 * 2. 如果设备不支持，回退到 NET_DVR_GetFileByTime（V30，有1GB限制）
 * 3. 使用竞业达验证的旧版本SDK（5.3.1.61），兼容性更好
 *
 * 用法: java HikvisionDownloaderCLI <ip> <port> <user> <pass> <channel>
 *           <startTime> <endTime> <savePath> <channelName>
 * 时间格式: yyyy-MM-dd HH:mm:ss
 */
public class HikvisionDownloaderCLI {

    // 使用64位新版本SDK (6.1.6.45) - 配合V40/V50接口和分段策略
    private static final String HCNETSDK_PATH =
        "C:\\Users\\Administrator\\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836" +
        "\\CH-HCNetSDKV6.1.6.45_build20210302_win64\\库文件\\HCNetSDK.dll";

    // 备用：竞业达SDK (5.3.1.61) - 32位，需要32位JDK
    // private static final String HCNETSDK_PATH =
    //     "C:\\Users\\Administrator\\WorkBuddy\\20260323192840\\hikvision_java\\HCNetSDK_v531.dll";

    private static HCNetSDK sdkInstance = null;

    // ─────────────────── SDK 接口 ───────────────────────────────────────────
    public interface HCNetSDK extends Library {
        static HCNetSDK getInstance() {
            if (sdkInstance == null) {
                sdkInstance = (HCNetSDK) Native.loadLibrary(HCNETSDK_PATH, HCNetSDK.class);
            }
            return sdkInstance;
        }

        boolean   NET_DVR_Init();
        boolean   NET_DVR_Cleanup();

        NativeLong NET_DVR_Login_V30(String sDVRIP, short wDVRPort,
                                     String sUserName, String sPassword,
                                     NET_DVR_DEVICEINFO_V30 lpDeviceInfo);
        boolean   NET_DVR_Logout(NativeLong lUserID);

        // ── 下载接口（V40：支持大文件，无1GB限制）────────────────────────────
        NativeLong NET_DVR_GetFileByTime_V40(NativeLong lUserID,
                                             String     sSavedFileName,
                                             NET_DVR_PLAYCOND pDownloadCond);

        // ── 旧接口（备用，有1GB限制，保留以便回退）──────────────────────────
        NativeLong NET_DVR_GetFileByTime(NativeLong lUserID, NativeLong lChannel,
                                         NET_DVR_TIME lpStartTime,
                                         NET_DVR_TIME lpStopTime,
                                         String sSavedFileName);

        boolean   NET_DVR_StopGetFile(NativeLong lFileHandle);

        NativeLong NET_DVR_PlayBackControl(NativeLong lPlayHandle,
                                           int dwControlCode,
                                           int dwInValue,
                                           IntByReference lpOutValue);
        int NET_DVR_GetDownloadPos(NativeLong lFileHandle);
        int NET_DVR_GetLastError();

        // 回放控制命令
        int NET_DVR_PLAYSTART  = 1;
        int NET_DVR_PLAYSTOP   = 2;
        int NET_DVR_PLAYGETPOS = 6;
    }

    // ─────────────────── 结构体 ─────────────────────────────────────────────
    public static class NET_DVR_DEVICEINFO_V30 extends Structure {
        public byte[] sSerialNumber   = new byte[48];
        public byte   byAlarmInPortNum;
        public byte   byAlarmOutPortNum;
        public byte   byDiskNum;
        public byte   byDVRType;
        public byte   byChanNum;
        public byte   byStartChan;
        public byte   byAudioChanNum;
        public byte   byIPChanNum;
        public byte[] byRes           = new byte[24];

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("sSerialNumber","byAlarmInPortNum","byAlarmOutPortNum",
                "byDiskNum","byDVRType","byChanNum","byStartChan","byAudioChanNum",
                "byIPChanNum","byRes");
        }
    }

    public static class NET_DVR_TIME extends Structure {
        public int dwYear;
        public int dwMonth;
        public int dwDay;
        public int dwHour;
        public int dwMinute;
        public int dwSecond;
        public int wMillisecond;

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("dwYear","dwMonth","dwDay","dwHour","dwMinute","dwSecond","wMillisecond");
        }
    }

    /**
     * NET_DVR_PLAYCOND — 下载条件结构体（V40接口使用）
     * 注意：byRes 长度为 30，总结构体大小 = 4 + 28 + 28 + 1 + 1 + 32 + 30 = 124 字节
     */
    public static class NET_DVR_PLAYCOND extends Structure {
        public int   dwChannel;
        public NET_DVR_TIME struStartTime = new NET_DVR_TIME();
        public NET_DVR_TIME struStopTime  = new NET_DVR_TIME();
        public byte  byDrawFrame;     // 0-正常帧率，1-抽帧
        public byte  byStreamType;    // 0-主码流，1-子码流
        public byte[] byStreamID     = new byte[32];  // STREAM_ID_LEN
        public byte[] byRes          = new byte[30];

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("dwChannel","struStartTime","struStopTime",
                "byDrawFrame","byStreamType","byStreamID","byRes");
        }
    }

    // ─────────────────── 错误码描述 ─────────────────────────────────────────
    private static String errDesc(int code) {
        switch (code) {
            case  1: return "用户名密码错误";
            case  2: return "用户被锁定";
            case  3: return "用户权限不足";
            case  4: return "超过最大连接数";
            case  7: return "连接设备失败/超时";
            case  9: return "SDK未初始化";
            case 10: return "IP地址错误";
            case 17: return "参数错误";
            case 23: return "子系统不支持";
            case 41: return "通道号错误";
            case 44: return "带宽不足";
            case 52: return "录像文件不存在";
            case 68: return "用户不存在";
            case 72: return "登录已达上限";
            default: return "未知错误(code=" + code + ")";
        }
    }

    // ─────────────────── main ────────────────────────────────────────────────
    public static void main(String[] args) {
        if (args.length < 9) {
            System.out.println("用法: HikvisionDownloaderCLI <ip> <port> <user> <pass> <channel>" +
                " <startTime> <endTime> <savePath> <channelName>");
            System.exit(1);
        }

        String ip          = args[0];
        int    port        = Integer.parseInt(args[1]);
        String user        = args[2];
        String pass        = args[3];
        int    channel     = Integer.parseInt(args[4]);
        String startStr    = args[5];
        String endStr      = args[6];
        String finalPath   = args[7];
        // args[8] = channelName (仅用于显示/重命名，不影响下载)

        HCNetSDK sdk = null;
        NativeLong userId       = new NativeLong(-1);
        NativeLong downloadHandle = new NativeLong(-1);

        try {
            // 生成 ASCII 临时路径（避免中文路径编码问题）
            String dir      = new java.io.File(finalPath).getParent();
            String tempPath = dir + java.io.File.separator
                + "temp_" + System.currentTimeMillis() + "_ch" + channel + ".mp4";

            java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
            java.util.Date startDate = sdf.parse(startStr);
            java.util.Date endDate   = sdf.parse(endStr);

            // ── [1] Init SDK ───────────────────────────────────────────────
            System.out.println("[1] Init SDK...");
            sdk = HCNetSDK.getInstance();
            if (!sdk.NET_DVR_Init()) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("    [FAIL] SDK init failed. Error: " + e + " (" + errDesc(e) + ")");
                System.exit(1);
            }
            System.out.println("    [OK]");

            // ── [2] Login ──────────────────────────────────────────────────
            System.out.println("[2] Login " + ip + ":" + port + "...");
            NET_DVR_DEVICEINFO_V30 devInfo = new NET_DVR_DEVICEINFO_V30();
            userId = sdk.NET_DVR_Login_V30(ip, (short) port, user, pass, devInfo);
            if (userId.longValue() == -1) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("    [FAIL] Login failed. Error: " + e + " (" + errDesc(e) + ")");
                sdk.NET_DVR_Cleanup();
                System.exit(1);
            }
            System.out.println("    [OK] UserId=" + userId);

            // ── [3] 构建时间结构体 ─────────────────────────────────────────
            java.util.Calendar cal = java.util.Calendar.getInstance();

            NET_DVR_TIME startTime = new NET_DVR_TIME();
            cal.setTime(startDate);
            startTime.dwYear   = cal.get(java.util.Calendar.YEAR);
            startTime.dwMonth  = cal.get(java.util.Calendar.MONTH) + 1;
            startTime.dwDay    = cal.get(java.util.Calendar.DAY_OF_MONTH);
            startTime.dwHour   = cal.get(java.util.Calendar.HOUR_OF_DAY);
            startTime.dwMinute = cal.get(java.util.Calendar.MINUTE);
            startTime.dwSecond = cal.get(java.util.Calendar.SECOND);
            startTime.wMillisecond = 0;

            NET_DVR_TIME endTime = new NET_DVR_TIME();
            cal.setTime(endDate);
            endTime.dwYear   = cal.get(java.util.Calendar.YEAR);
            endTime.dwMonth  = cal.get(java.util.Calendar.MONTH) + 1;
            endTime.dwDay    = cal.get(java.util.Calendar.DAY_OF_MONTH);
            endTime.dwHour   = cal.get(java.util.Calendar.HOUR_OF_DAY);
            endTime.dwMinute = cal.get(java.util.Calendar.MINUTE);
            endTime.dwSecond = cal.get(java.util.Calendar.SECOND);
            endTime.wMillisecond = 999;

            // ── [4] 下载（智能接口选择：V40 -> V30）──────────────────────────
            System.out.println("[3] Download ch" + channel + " [" + startStr + " -> " + endStr + "]");
            System.out.println("    Temp: " + tempPath);
            System.out.println("    Final: " + finalPath);
            System.out.flush();

            NET_DVR_PLAYCOND cond = new NET_DVR_PLAYCOND();
            cond.dwChannel     = channel;
            cond.struStartTime = startTime;
            cond.struStopTime  = endTime;
            cond.byDrawFrame   = 0;    // 0=正常帧率（不抽帧）
            cond.byStreamType  = 0;    // 0=主码流
            cond.write();

            // 尝试V40接口（无1GB限制）
            System.out.println("    [TRY] NET_DVR_GetFileByTime_V40 (no 1GB limit)...");
            downloadHandle = sdk.NET_DVR_GetFileByTime_V40(userId, tempPath, cond);

            if (downloadHandle.longValue() == -1) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("    [WARN] V40 failed (error " + e + "), trying V30...");
                System.out.flush();

                // 回退到V30接口（有1GB限制，但兼容性最好）
                startTime.write();
                endTime.write();
                downloadHandle = sdk.NET_DVR_GetFileByTime(
                    userId, new NativeLong(channel), startTime, endTime, tempPath);

                if (downloadHandle.longValue() == -1) {
                    e = sdk.NET_DVR_GetLastError();
                    System.out.println("    [FAIL] All interfaces failed. Error: " + e + " (" + errDesc(e) + ")");
                    sdk.NET_DVR_Logout(userId);
                    sdk.NET_DVR_Cleanup();
                    System.exit(1);
                }
                System.out.println("    [OK] Using V30 handle: " + downloadHandle + " (注意: V30有1GB限制)");
            } else {
                System.out.println("    [OK] V40 handle: " + downloadHandle + " (无1GB限制)");
            }

            // ── [5] 开始播放/下载 ─────────────────────────────────────────
            System.out.println("[4] Start download...");
            NativeLong startResult = sdk.NET_DVR_PlayBackControl(
                downloadHandle, HCNetSDK.NET_DVR_PLAYSTART, 0, null);
            if (startResult.longValue() == -1) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("    [FAIL] PlayBackControl(START) failed. Error: " + e + " (" + errDesc(e) + ")");
                sdk.NET_DVR_StopGetFile(downloadHandle);
                sdk.NET_DVR_Logout(userId);
                sdk.NET_DVR_Cleanup();
                System.exit(1);
            }
            System.out.println("    [OK] Download started.");
            System.out.flush();

            // ── [6] 进度监控 ──────────────────────────────────────────────
            long startMs       = System.currentTimeMillis();
            long durationMs    = endDate.getTime() - startDate.getTime();
            // 超时 = max(录像时长 × 3, 5分钟)，最长不超过6小时
            long timeoutMs     = Math.max(durationMs * 3L, 5L * 60 * 1000);
            timeoutMs          = Math.min(timeoutMs, 6L * 3600 * 1000);

            int  lastProgress  = -1;
            long lastChangedMs = startMs;
            long stuckTimeoutMs = 5L * 60 * 1000;   // 进度5分钟不变则超时

            System.out.println("    Timeout: " + (timeoutMs / 1000) + "s, StuckTimeout: "
                + (stuckTimeoutMs / 1000) + "s");
            System.out.flush();

            while (true) {
                Thread.sleep(1000);
                long now = System.currentTimeMillis();

                int progress = sdk.NET_DVR_GetDownloadPos(downloadHandle);

                if (progress >= 0 && progress != lastProgress) {
                    System.out.println("    Progress: " + progress + "%");
                    System.out.flush();
                    lastProgress  = progress;
                    lastChangedMs = now;
                }

                // 完成
                if (progress >= 100) {
                    System.out.println("    [OK] Download progress reached 100%!");
                    System.out.flush();
                    break;
                }

                // 全局超时
                if (now - startMs > timeoutMs) {
                    java.io.File f = new java.io.File(tempPath);
                    System.out.println("    [WARN] Global timeout (" + (timeoutMs/1000) + "s). "
                        + "File=" + (f.exists() ? (f.length()/1024/1024)+"MB" : "not found"));
                    System.out.flush();
                    break;
                }

                // 进度卡死超时（文件持续没有变化）
                if (progress > 0 && progress == lastProgress && (now - lastChangedMs) > stuckTimeoutMs) {
                    java.io.File f = new java.io.File(tempPath);
                    System.out.println("    [WARN] Progress stuck at " + progress + "% for "
                        + (stuckTimeoutMs/1000) + "s. File=" + (f.exists() ? (f.length()/1024/1024)+"MB" : "not found"));
                    System.out.flush();
                    break;
                }
            }

            // ── [7] 停止下载 ──────────────────────────────────────────────
            System.out.println("[5] Stop download...");
            sdk.NET_DVR_PlayBackControl(downloadHandle, HCNetSDK.NET_DVR_PLAYSTOP, 0, null);
            sdk.NET_DVR_StopGetFile(downloadHandle);
            downloadHandle = new NativeLong(-1);
            sdk.NET_DVR_Logout(userId);
            userId = new NativeLong(-1);
            sdk.NET_DVR_Cleanup();
            sdk = null;

            // ── [8] 检查临时文件 ──────────────────────────────────────────
            java.io.File tempFile = new java.io.File(tempPath);
            if (!tempFile.exists() || tempFile.length() == 0) {
                System.out.println("[FAIL] Temp file missing or empty: " + tempPath);
                System.exit(1);
            }
            long size = tempFile.length();
            System.out.println("[OK] Temp file: " + (size / 1024.0 / 1024.0) + " MB  (" + tempPath + ")");

            // ── [9] 重命名为最终路径 ──────────────────────────────────────
            System.out.println("[6] Rename to: " + finalPath);
            java.io.File finalFile = new java.io.File(finalPath);
            if (finalFile.exists()) finalFile.delete();

            boolean renamed = tempFile.renameTo(finalFile);
            if (!renamed) {
                System.out.println("[WARN] Rename failed, keeping temp file: " + tempPath);
                System.out.println("[OK] Download complete, file saved to: " + tempPath);
            } else {
                System.out.println("[OK] Download complete!");
                System.out.println("[OK] File: " + finalPath);
            }
            System.out.println("[OK] Size: " + (size / 1024.0 / 1024.0) + " MB");
            System.out.println("\nNOTE: File is in MPEG/PS format, needs FFmpeg conversion to MP4");
            System.exit(0);

        } catch (Exception e) {
            System.out.println("[FAIL] Exception: " + e.getMessage());
            e.printStackTrace();
            // 尽量清理资源
            try {
                if (sdk != null) {
                    if (downloadHandle.longValue() != -1) {
                        sdk.NET_DVR_StopGetFile(downloadHandle);
                    }
                    if (userId.longValue() != -1) {
                        sdk.NET_DVR_Logout(userId);
                    }
                    sdk.NET_DVR_Cleanup();
                }
            } catch (Exception ex) { /* ignore */ }
            System.exit(1);
        }
    }
}
