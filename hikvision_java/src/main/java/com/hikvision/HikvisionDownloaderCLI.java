package com.hikvision;

import com.sun.jna.win32.StdCallLibrary;
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
    public interface HCNetSDK extends StdCallLibrary {
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

        // ── 下载接口（V30，分段下载绕过1GB限制）──────────────────────────
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

        // ── 录像文件查询（用于获取录像文件大小）────────────────────────────
        NativeLong NET_DVR_FindFile_V30(NativeLong lUserID, NET_DVR_FILECOND pFindCond);
        NativeLong NET_DVR_FindNextFile_V30(NativeLong lFindHandle, NET_DVR_FINDDATA_V30 lpFindData);
        boolean NET_DVR_FindClose_V30(NativeLong lFindHandle);

        // ── V40 录像文件查询 ────────────────────────────────────────────
        NativeLong NET_DVR_FindFile_V40(NativeLong lUserID, NET_DVR_FILECOND_V40 pFindCond);
        NativeLong NET_DVR_FindNextFile_V40(NativeLong lFindHandle, NET_DVR_FINDDATA_V40 lpFindData);

        // ── V50 录像文件查询（用于获取录像文件大小，兼容新固件）───────────
        NativeLong NET_DVR_FindFile_V50(NativeLong lUserID, NET_DVR_FILECOND_V50 pFindCond);
        NativeLong NET_DVR_FindNextFile_V50(NativeLong lFindHandle, NET_DVR_FINDDATA_V50 lpFindData);

        // 回放控制命令
        int NET_DVR_PLAYSTART  = 1;
        int NET_DVR_PLAYSTOP   = 2;
        int NET_DVR_PLAYGETPOS = 6;
    }

    // ─────────────────── 结构体 ─────────────────────────────────────────────

    // NET_DVR_FILECOND — 录像文件查找条件（FindFile_V30用）
    // 严格按照 HCNetSDK.h 第13641-13652行: 7个字段, 共96字节
    public static class NET_DVR_FILECOND extends Structure {
        public int   lChannel;           // 通道号
        public int   dwFileType;         // 0xff=全部, 0=定时录像, 1=移动侦测...
        public int   dwIsLocked;         // 0=正常, 1=锁定, 0xff=全部
        public int   dwUseCardNo;        // 0=不用卡号
        public byte[] sCardNumber = new byte[32];
        public NET_DVR_TIME struStartTime = new NET_DVR_TIME();
        public NET_DVR_TIME struStopTime  = new NET_DVR_TIME();

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("lChannel","dwFileType","dwIsLocked","dwUseCardNo",
                "sCardNumber","struStartTime","struStopTime");
        }
    }

    // NET_DVR_FILECOND_V40 — 录像文件查找条件V40（FindFile_V40用）
    // HCNetSDK.h 第28387-28412行: 160字节
    public static class NET_DVR_FILECOND_V40 extends Structure {
        public int   lChannel;
        public int   dwFileType;
        public int   dwIsLocked;
        public int   dwUseCardNo;
        public byte[] sCardNumber = new byte[32];
        public NET_DVR_TIME struStartTime = new NET_DVR_TIME();
        public NET_DVR_TIME struStopTime  = new NET_DVR_TIME();
        public byte  byDrawFrame;           // 0=不抽帧
        public byte  byFindType;            // 0=普通卷
        public byte  byQuickSearch;         // 0=普通查询
        public byte  bySpecialFindInfoType; // 0=无效
        public int   dwVolumeNum;           // 0
        public byte[] byWorkingDeviceGUID = new byte[16];
        public NET_DVR_SPECIAL_FINDINFO_UNION uSpecialFindInfo = new NET_DVR_SPECIAL_FINDINFO_UNION();
        public byte  byStreamType;          // 0=主码流优先
        public byte  byAudioFile;           // 0=非音频文件
        public byte[] byRes2 = new byte[30];

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("lChannel","dwFileType","dwIsLocked","dwUseCardNo",
                "sCardNumber","struStartTime","struStopTime",
                "byDrawFrame","byFindType","byQuickSearch","bySpecialFindInfoType",
                "dwVolumeNum","byWorkingDeviceGUID","uSpecialFindInfo",
                "byStreamType","byAudioFile","byRes2");
        }
    }

    // NET_DVR_FINDDATA_V30 — 录像文件信息（FindNextFile_V30用）
    // 严格按照 HCNetSDK.h 第13579-13590行: 8个字段
    public static class NET_DVR_FINDDATA_V30 extends Structure {
        public byte[] sFileName = new byte[100];      // 文件名
        public NET_DVR_TIME struStartTime = new NET_DVR_TIME();  // 开始时间
        public NET_DVR_TIME struStopTime  = new NET_DVR_TIME();  // 结束时间
        public int dwFileSize;                               // ⭐ 文件大小（字节）
        public byte[] sCardNum = new byte[32];
        public byte byLocked;          // 0=正常, 1=锁定
        public byte byFileType;        // 文件类型
        public byte[] byRes = new byte[2];

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("sFileName","struStartTime","struStopTime",
                "dwFileSize","sCardNum","byLocked","byFileType","byRes");
        }
    }

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
        // 严格按照 HCNetSDK.h 第9353-9361行: 6个DWORD，无毫秒字段
        public int dwYear;
        public int dwMonth;
        public int dwDay;
        public int dwHour;
        public int dwMinute;
        public int dwSecond;

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("dwYear","dwMonth","dwDay","dwHour","dwMinute","dwSecond");
        }
    }

    // NET_DVR_STREAM_INFO — 流信息（V50用，72字节）
    // HCNetSDK.h 第10859-10866行
    public static class NET_DVR_STREAM_INFO extends Structure {
        public int   dwSize;
        public byte[] byID = new byte[32];     // STREAM_ID_LEN = 32
        public int   dwChannel;
        public byte[] byRes = new byte[32];

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("dwSize", "byID", "dwChannel", "byRes");
        }
    }

    // NET_DVR_TIME_SEARCH_COND — V50时间条件（12字节）
    // HCNetSDK.h 第9120-9132行
    public static class NET_DVR_TIME_SEARCH_COND extends Structure {
        public short wYear;           // WORD = 2 bytes
        public byte  byMonth;
        public byte  byDay;
        public byte  byHour;
        public byte  byMinute;
        public byte  bySecond;
        public byte  byLocalOrUTC;    // 0=本地时间
        public short wMillisecond;    // WORD = 2 bytes
        public byte  cTimeDifferenceH;
        public byte  cTimeDifferenceM;

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("wYear", "byMonth", "byDay", "byHour", "byMinute",
                "bySecond", "byLocalOrUTC", "wMillisecond", "cTimeDifferenceH", "cTimeDifferenceM");
        }
    }

    // NET_DVR_SPECIAL_FINDINFO_UNION — 专有查询条件联合体（8字节）
    public static class NET_DVR_SPECIAL_FINDINFO_UNION extends Structure {
        public byte[] byLenth = new byte[8];

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("byLenth");
        }
    }

    // NET_DVR_FILECOND_V50 — V50录像查找条件
    // HCNetSDK.h 第28415-28435行
    public static class NET_DVR_FILECOND_V50 extends Structure {
        public NET_DVR_STREAM_INFO struStreamID = new NET_DVR_STREAM_INFO();   // 72字节
        public NET_DVR_TIME_SEARCH_COND struStartTime = new NET_DVR_TIME_SEARCH_COND(); // 12字节
        public NET_DVR_TIME_SEARCH_COND struStopTime = new NET_DVR_TIME_SEARCH_COND();  // 12字节
        public byte  byFindType;           // 0=普通卷
        public byte  byDrawFrame;          // 0=不抽帧
        public byte  byQuickSearch;        // 0=普通查询
        public byte  byStreamType;         // 0xff=全部
        public int   dwFileType;           // 0xff=全部
        public int   dwVolumeNum;          // 0
        public byte  byIsLocked;           // 0xff=全部
        public byte  byNeedCard;           // 0=不需要
        public byte  byOnlyAudioFile;      // 0=视频文件
        public byte  bySpecialFindInfoType; // 0=无效
        public byte[] szCardNum = new byte[32];
        public byte[] szWorkingDeviceGUID = new byte[16];
        public NET_DVR_SPECIAL_FINDINFO_UNION uSpecialFindInfo = new NET_DVR_SPECIAL_FINDINFO_UNION(); // 8字节
        public int   dwTimeout;            // 0=默认
        public byte[] byRes = new byte[252];

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("struStreamID", "struStartTime", "struStopTime",
                "byFindType", "byDrawFrame", "byQuickSearch", "byStreamType",
                "dwFileType", "dwVolumeNum", "byIsLocked", "byNeedCard",
                "byOnlyAudioFile", "bySpecialFindInfoType", "szCardNum",
                "szWorkingDeviceGUID", "uSpecialFindInfo", "dwTimeout", "byRes");
        }
    }

    // NET_DVR_FINDDATA_V40 — V40录像文件信息（FindNextFile_V40用）
    // HCNetSDK.h 第13592-13608行: 264字节
    public static class NET_DVR_FINDDATA_V40 extends Structure {
        public byte[] sFileName = new byte[100];
        public NET_DVR_TIME struStartTime = new NET_DVR_TIME();
        public NET_DVR_TIME struStopTime  = new NET_DVR_TIME();
        public int   dwFileSize;
        public byte[] sCardNum = new byte[32];
        public byte  byLocked;
        public byte  byFileType;
        public byte  byQuickSearch;   // 0:普通查询结果，1：快速（日历）查询结果
        public byte  byRes;           // 1字节填充
        public int   dwFileIndex;     // 文件索引号
        public byte  byStreamType;
        public byte[] byRes1 = new byte[127];

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("sFileName","struStartTime","struStopTime",
                "dwFileSize","sCardNum","byLocked","byFileType","byQuickSearch",
                "byRes","dwFileIndex","byStreamType","byRes1");
        }
    }

    // NET_DVR_FINDDATA_V50 — V50录像文件信息
    // HCNetSDK.h 第13610行起
    public static class NET_DVR_FINDDATA_V50 extends Structure {
        public byte[] sFileName = new byte[100];
        public NET_DVR_TIME_SEARCH struStartTime = new NET_DVR_TIME_SEARCH();
        public NET_DVR_TIME_SEARCH struStopTime = new NET_DVR_TIME_SEARCH();
        public byte[] struAddrBytes = new byte[24]; // NET_DVR_ADDRESS
        public int   dwFileSize;
        public byte  byLocked;
        public byte  byFileType;
        public byte  byQuickSearch;
        public byte[] byRes = new byte[243];

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("sFileName", "struStartTime", "struStopTime",
                "struAddrBytes", "dwFileSize", "byLocked", "byFileType",
                "byQuickSearch", "byRes");
        }
    }

    // NET_DVR_TIME_SEARCH — V50搜索返回时间
    // HCNetSDK.h 第9108-9118行
    public static class NET_DVR_TIME_SEARCH extends Structure {
        public short wYear;
        public byte  byMonth;
        public byte  byDay;
        public byte  byHour;
        public byte  byMinute;
        public byte  bySecond;
        public byte  byLocalOrUTC;
        public short wMillisecond;
        public byte  cTimeDifferenceH;
        public byte  cTimeDifferenceM;

        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("wYear", "byMonth", "byDay", "byHour", "byMinute",
                "bySecond", "byLocalOrUTC", "wMillisecond", "cTimeDifferenceH", "cTimeDifferenceM");
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
    /**
     * 三种模式:
     *  1a) findFileSizeV40: findFileSizeV40 <ip> <port> <user> <pass> <channel> <startTime> <endTime> dummy dummy
     *     → 使用V40接口查询，输出格式同上
     *  1b) findFileSizeV50: findFileSizeV50 <ip> <port> <user> <pass> <channel> <startTime> <endTime> dummy dummy
     *     → 使用V50接口查询，输出格式同上
     *  1c) findFileSize:  findFileSize <ip> <port> <user> <pass> <channel> <startTime> <endTime> dummy dummy
     *     → 使用V30接口查询（回退方案）
     *  2) download (默认):  <ip> <port> <user> <pass> <channel> <startTime> <endTime> <savePath> <channelName>
     */
    public static void main(String[] args) {
        // ── findFileSizeV40 模式 ──────────────────────────────────────────
        if (args.length >= 8 && "findFileSizeV40".equalsIgnoreCase(args[0])) {
            doFindFileSizeV40(args);
            return;
        }

        // ── findFileSizeV50 模式 ──────────────────────────────────────────
        if (args.length >= 8 && "findFileSizeV50".equalsIgnoreCase(args[0])) {
            doFindFileSizeV50(args);
            return;
        }

        // ── findFileSize 模式 ─────────────────────────────────────────────
        if (args.length >= 8 && "findFileSize".equalsIgnoreCase(args[0])) {
            doFindFileSize(args);
            return;
        }

        // ── download 模式（原有逻辑）──────────────────────────────────────
        if (args.length < 9) {
            System.out.println("用法1: HikvisionDownloaderCLI findFileSize <ip> <port> <user> <pass> <channel> <startTime> <endTime> dummy dummy");
            System.out.println("用法2: HikvisionDownloaderCLI <ip> <port> <user> <pass> <channel> <startTime> <endTime> <savePath> <channelName>");
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
            startTime.dwSecond = cal.get(java.util.Calendar.SECOND);

            NET_DVR_TIME endTime = new NET_DVR_TIME();
            cal.setTime(endDate);
            endTime.dwYear   = cal.get(java.util.Calendar.YEAR);
            endTime.dwMonth  = cal.get(java.util.Calendar.MONTH) + 1;
            endTime.dwDay    = cal.get(java.util.Calendar.DAY_OF_MONTH);
            endTime.dwHour   = cal.get(java.util.Calendar.HOUR_OF_DAY);
            endTime.dwMinute = cal.get(java.util.Calendar.MINUTE);
            endTime.dwSecond = cal.get(java.util.Calendar.SECOND);
            endTime.dwSecond = cal.get(java.util.Calendar.SECOND);

            // ── [4] 下载（统一使用V30接口，避免V40的1GB限制问题）──────────
            System.out.println("[3] Download ch" + channel + " [" + startStr + " -> " + endStr + "]");
            System.out.println("    Temp: " + tempPath);
            System.out.println("    Final: " + finalPath);
            System.out.println("    Mode: V30 (分段下载，绕过1GB限制)");
            System.out.flush();

            startTime.write();
            endTime.write();
            downloadHandle = sdk.NET_DVR_GetFileByTime(
                userId, new NativeLong(channel), startTime, endTime, tempPath);

            if (downloadHandle.longValue() == -1) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("    [FAIL] V30 download failed. Error: " + e + " (" + errDesc(e) + ")");
                sdk.NET_DVR_Logout(userId);
                sdk.NET_DVR_Cleanup();
                System.exit(1);
            }
            System.out.println("    [OK] V30 handle: " + downloadHandle);

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

    // ─────────────────── findFileSize 模式 ─────────────────────────────────
    /**
     * 通过 NET_DVR_FindFile_V30 查询指定时间段录像文件总大小
     * 参数: findFileSize <ip> <port> <user> <pass> <channel> <startTime> <endTime> dummy dummy
     * 输出: [SIZE] total_bytes=N   或   [SIZE] error=描述
     */
    private static void doFindFileSize(String[] args) {
        if (args.length < 8) {
            System.out.println("[SIZE] error=参数不足, 需要8个参数");
            System.exit(1);
        }

        String ip       = args[1];
        int    port     = Integer.parseInt(args[2]);
        String user     = args[3];
        String pass     = args[4];
        int    channel  = Integer.parseInt(args[5]);
        String startStr = args[6];
        String endStr   = args[7];

        HCNetSDK sdk = null;
        NativeLong userId = new NativeLong(-1);

        try {
            // ── [1] Init SDK ──
            sdk = HCNetSDK.getInstance();
            if (!sdk.NET_DVR_Init()) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("[SIZE] error=SDK初始化失败(" + e + " " + errDesc(e) + ")");
                System.exit(1);
            }

            // ── [2] Login ──
            NET_DVR_DEVICEINFO_V30 devInfo = new NET_DVR_DEVICEINFO_V30();
            userId = sdk.NET_DVR_Login_V30(ip, (short) port, user, pass, devInfo);
            if (userId.longValue() == -1) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("[SIZE] error=登录失败(" + e + " " + errDesc(e) + ")");
                sdk.NET_DVR_Cleanup();
                System.exit(1);
            }

            // ── [3] 构建时间 ──
            java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
            java.util.Date startDate = sdf.parse(startStr);
            java.util.Date endDate   = sdf.parse(endStr);

            java.util.Calendar cal = java.util.Calendar.getInstance();

            NET_DVR_TIME startTime = new NET_DVR_TIME();
            cal.setTime(startDate);
            startTime.dwYear   = cal.get(java.util.Calendar.YEAR);
            startTime.dwMonth  = cal.get(java.util.Calendar.MONTH) + 1;
            startTime.dwDay    = cal.get(java.util.Calendar.DAY_OF_MONTH);
            startTime.dwHour   = cal.get(java.util.Calendar.HOUR_OF_DAY);
            startTime.dwMinute = cal.get(java.util.Calendar.MINUTE);
            startTime.dwSecond = cal.get(java.util.Calendar.SECOND);

            NET_DVR_TIME endTime = new NET_DVR_TIME();
            cal.setTime(endDate);
            endTime.dwYear   = cal.get(java.util.Calendar.YEAR);
            endTime.dwMonth  = cal.get(java.util.Calendar.MONTH) + 1;
            endTime.dwDay    = cal.get(java.util.Calendar.DAY_OF_MONTH);
            endTime.dwHour   = cal.get(java.util.Calendar.HOUR_OF_DAY);
            endTime.dwMinute = cal.get(java.util.Calendar.MINUTE);
            endTime.dwSecond = cal.get(java.util.Calendar.SECOND);

            // ── [4] 构建查找条件 ──
            NET_DVR_FILECOND findCond = new NET_DVR_FILECOND();
            findCond.lChannel    = channel;
            findCond.dwFileType  = 0xff;   // 全部文件类型
            findCond.dwIsLocked  = 0xff;   // 全部（含锁定/未锁定）
            findCond.dwUseCardNo = 0;      // 不用卡号
            findCond.struStartTime = startTime;
            findCond.struStopTime  = endTime;
            findCond.write();

            // ── [5] FindFile_V30 ──
            NativeLong findHandle = sdk.NET_DVR_FindFile_V30(userId, findCond);
            if (findHandle.longValue() == -1) {
                int e = sdk.NET_DVR_GetLastError();
                sdk.NET_DVR_Logout(userId);
                sdk.NET_DVR_Cleanup();
                System.out.println("[SIZE] error=查找录像失败(" + e + " " + errDesc(e) + ")");
                System.exit(1);
            }
            // findHandle=0 也可能表示没有录像（根据SDK文档）
            // 但 FindNextFile 会返回 1002，最终 total_bytes=0

            // ── [6] FindNextFile_V30 循环累加 dwFileSize ──
            long totalBytes = 0;
            int fileCount   = 0;

            while (true) {
                NET_DVR_FINDDATA_V30 findData = new NET_DVR_FINDDATA_V30();
                findData.read();
                NativeLong findResult = sdk.NET_DVR_FindNextFile_V30(findHandle, findData);
                int result = findResult.intValue();

                if (result == 1000) {
                    // NET_DVR_FILE_SUCCESS = 1000, 找到了一个文件
                    totalBytes += findData.dwFileSize & 0xFFFFFFFFL;  // unsigned int → long
                    fileCount++;
                } else if (result == 1002) {
                    // NET_DVR_NOMOREFILE = 1002, 没有更多文件
                    break;
                } else if (result == -1) {
                    int e = sdk.NET_DVR_GetLastError();
                    System.out.println("[SIZE] error=FindNextFile出错(" + e + " " + errDesc(e) + ")");
                    sdk.NET_DVR_FindClose_V30(findHandle);
                    sdk.NET_DVR_Logout(userId);
                    sdk.NET_DVR_Cleanup();
                    System.exit(1);
                } else {
                    // 其他返回码（如 1003 = 网络连接失败）
                    System.out.println("[SIZE] error=FindNextFile返回" + result);
                    sdk.NET_DVR_FindClose_V30(findHandle);
                    sdk.NET_DVR_Logout(userId);
                    sdk.NET_DVR_Cleanup();
                    System.exit(1);
                }
            }

            // ── [7] 关闭查找 ──
            sdk.NET_DVR_FindClose_V30(findHandle);
            sdk.NET_DVR_Logout(userId);
            sdk.NET_DVR_Cleanup();

            // ── [8] 输出结果 ──
            System.out.println("[SIZE] total_bytes=" + totalBytes + " file_count=" + fileCount);
            System.exit(0);

        } catch (Exception e) {
            System.out.println("[SIZE] error=" + e.getMessage());
            try {
                if (sdk != null && userId.longValue() != -1) {
                    sdk.NET_DVR_Logout(userId);
                }
                if (sdk != null) {
                    sdk.NET_DVR_Cleanup();
                }
            } catch (Exception ex) { /* ignore */ }
            System.exit(1);
        }
    }

    // ─────────────────── findFileSizeV40 模式 ──────────────────────────────
    /**
     * 通过 NET_DVR_FindFile_V40 查询指定时间段录像文件总大小（V40接口）
     * 参数: findFileSizeV40 <ip> <port> <user> <pass> <channel> <startTime> <endTime> dummy dummy
     * 输出: [SIZE] total_bytes=N   或   [SIZE] error=描述
     */
    private static void doFindFileSizeV40(String[] args) {
        if (args.length < 8) {
            System.out.println("[SIZE] error=参数不足, 需要8个参数");
            System.exit(1);
        }

        String ip       = args[1];
        int    port     = Integer.parseInt(args[2]);
        String user     = args[3];
        String pass     = args[4];
        int    channel  = Integer.parseInt(args[5]);
        String startStr = args[6];
        String endStr   = args[7];

        HCNetSDK sdk = null;
        NativeLong userId = new NativeLong(-1);

        try {
            // ── [1] Init SDK ──
            sdk = HCNetSDK.getInstance();
            if (!sdk.NET_DVR_Init()) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("[SIZE] error=SDK初始化失败(" + e + " " + errDesc(e) + ")");
                System.exit(1);
            }

            // ── [2] Login ──
            NET_DVR_DEVICEINFO_V30 devInfo = new NET_DVR_DEVICEINFO_V30();
            userId = sdk.NET_DVR_Login_V30(ip, (short) port, user, pass, devInfo);
            if (userId.longValue() == -1) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("[SIZE] error=登录失败(" + e + " " + errDesc(e) + ")");
                sdk.NET_DVR_Cleanup();
                System.exit(1);
            }

            // ── [3] 构建时间 ──
            java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
            java.util.Date startDate = sdf.parse(startStr);
            java.util.Date endDate   = sdf.parse(endStr);

            java.util.Calendar cal = java.util.Calendar.getInstance();

            NET_DVR_TIME startTime = new NET_DVR_TIME();
            cal.setTime(startDate);
            startTime.dwYear   = cal.get(java.util.Calendar.YEAR);
            startTime.dwMonth  = cal.get(java.util.Calendar.MONTH) + 1;
            startTime.dwDay    = cal.get(java.util.Calendar.DAY_OF_MONTH);
            startTime.dwHour   = cal.get(java.util.Calendar.HOUR_OF_DAY);
            startTime.dwMinute = cal.get(java.util.Calendar.MINUTE);
            startTime.dwSecond = cal.get(java.util.Calendar.SECOND);

            NET_DVR_TIME endTime = new NET_DVR_TIME();
            cal.setTime(endDate);
            endTime.dwYear   = cal.get(java.util.Calendar.YEAR);
            endTime.dwMonth  = cal.get(java.util.Calendar.MONTH) + 1;
            endTime.dwDay    = cal.get(java.util.Calendar.DAY_OF_MONTH);
            endTime.dwHour   = cal.get(java.util.Calendar.HOUR_OF_DAY);
            endTime.dwMinute = cal.get(java.util.Calendar.MINUTE);
            endTime.dwSecond = cal.get(java.util.Calendar.SECOND);

            // ── [4] 构建V40查找条件 ──
            NET_DVR_FILECOND_V40 findCond = new NET_DVR_FILECOND_V40();
            findCond.lChannel    = channel;
            findCond.dwFileType  = 0xff;   // 全部文件类型
            findCond.dwIsLocked  = 0xff;   // 全部
            findCond.dwUseCardNo = 0;      // 不用卡号
            findCond.struStartTime = startTime;
            findCond.struStopTime  = endTime;
            findCond.byDrawFrame       = 0;  // 不抽帧
            findCond.byFindType        = 0;  // 普通卷
            findCond.byQuickSearch     = 0;  // 普通查询
            findCond.bySpecialFindInfoType = 0;
            findCond.dwVolumeNum       = 0;
            findCond.byStreamType      = 0;  // 主码流优先
            findCond.byAudioFile       = 0;  // 非音频文件
            findCond.write();

            // ── [5] FindFile_V40 ──
            NativeLong findHandle = sdk.NET_DVR_FindFile_V40(userId, findCond);

            if (findHandle.longValue() == -1) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("[SIZE] error=V40查找录像失败(" + e + " " + errDesc(e) + ")");
                sdk.NET_DVR_Logout(userId);
                sdk.NET_DVR_Cleanup();
                System.exit(1);
            }

            // ── [6] FindNextFile_V40 循环累加 dwFileSize ──
            long totalBytes = 0;
            int fileCount   = 0;

            while (true) {
                NET_DVR_FINDDATA_V40 findData = new NET_DVR_FINDDATA_V40();
                findData.read();
                NativeLong findResult = sdk.NET_DVR_FindNextFile_V40(findHandle, findData);
                int result = findResult.intValue();

                if (result == 1000) {
                    totalBytes += findData.dwFileSize & 0xFFFFFFFFL;
                    fileCount++;
                } else if (result == 1002) {
                    break;
                } else if (result == -1) {
                    int e = sdk.NET_DVR_GetLastError();
                    System.out.println("[SIZE] error=FindNextFile_V40出错(" + e + " " + errDesc(e) + ")");
                    sdk.NET_DVR_FindClose_V30(findHandle);
                    sdk.NET_DVR_Logout(userId);
                    sdk.NET_DVR_Cleanup();
                    System.exit(1);
                } else {
                    System.out.println("[SIZE] error=FindNextFile_V40返回" + result);
                    sdk.NET_DVR_FindClose_V30(findHandle);
                    sdk.NET_DVR_Logout(userId);
                    sdk.NET_DVR_Cleanup();
                    System.exit(1);
                }
            }

            // ── [7] 关闭查找 ──
            sdk.NET_DVR_FindClose_V30(findHandle);
            sdk.NET_DVR_Logout(userId);
            sdk.NET_DVR_Cleanup();

            // ── [8] 输出结果 ──
            System.out.println("[SIZE] total_bytes=" + totalBytes + " file_count=" + fileCount);
            System.exit(0);

        } catch (Exception e) {
            System.out.println("[SIZE] error=" + e.getMessage());
            try {
                if (sdk != null && userId.longValue() != -1) {
                    sdk.NET_DVR_Logout(userId);
                }
                if (sdk != null) {
                    sdk.NET_DVR_Cleanup();
                }
            } catch (Exception ex) { /* ignore */ }
            System.exit(1);
        }
    }

    // ─────────────────── findFileSizeV50 模式 ──────────────────────────────
    /**
     * 通过 NET_DVR_FindFile_V50 查询指定时间段录像文件总大小（V50接口，兼容新固件）
     * 参数: findFileSizeV50 <ip> <port> <user> <pass> <channel> <startTime> <endTime> dummy dummy
     * 输出: [SIZE] total_bytes=N   或   [SIZE] error=描述
     */
    private static void doFindFileSizeV50(String[] args) {
        if (args.length < 8) {
            System.out.println("[SIZE] error=参数不足, 需要8个参数");
            System.exit(1);
        }

        String ip       = args[1];
        int    port     = Integer.parseInt(args[2]);
        String user     = args[3];
        String pass     = args[4];
        int    channel  = Integer.parseInt(args[5]);
        String startStr = args[6];
        String endStr   = args[7];

        HCNetSDK sdk = null;
        NativeLong userId = new NativeLong(-1);

        try {
            // ── [1] Init SDK ──
            sdk = HCNetSDK.getInstance();
            if (!sdk.NET_DVR_Init()) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("[SIZE] error=SDK初始化失败(" + e + " " + errDesc(e) + ")");
                System.exit(1);
            }

            // ── [2] Login ──
            NET_DVR_DEVICEINFO_V30 devInfo = new NET_DVR_DEVICEINFO_V30();
            userId = sdk.NET_DVR_Login_V30(ip, (short) port, user, pass, devInfo);
            if (userId.longValue() == -1) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("[SIZE] error=登录失败(" + e + " " + errDesc(e) + ")");
                sdk.NET_DVR_Cleanup();
                System.exit(1);
            }

            // ── [3] 构建V50时间条件 ──
            java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
            java.util.Date startDate = sdf.parse(startStr);
            java.util.Date endDate   = sdf.parse(endStr);

            java.util.Calendar cal = java.util.Calendar.getInstance();

            NET_DVR_TIME_SEARCH_COND startTime = new NET_DVR_TIME_SEARCH_COND();
            cal.setTime(startDate);
            startTime.wYear   = (short) cal.get(java.util.Calendar.YEAR);
            startTime.byMonth = (byte) (cal.get(java.util.Calendar.MONTH) + 1);
            startTime.byDay   = (byte) cal.get(java.util.Calendar.DAY_OF_MONTH);
            startTime.byHour  = (byte) cal.get(java.util.Calendar.HOUR_OF_DAY);
            startTime.byMinute = (byte) cal.get(java.util.Calendar.MINUTE);
            startTime.bySecond = (byte) cal.get(java.util.Calendar.SECOND);
            startTime.byLocalOrUTC = 0;

            NET_DVR_TIME_SEARCH_COND endTime = new NET_DVR_TIME_SEARCH_COND();
            cal.setTime(endDate);
            endTime.wYear   = (short) cal.get(java.util.Calendar.YEAR);
            endTime.byMonth = (byte) (cal.get(java.util.Calendar.MONTH) + 1);
            endTime.byDay   = (byte) cal.get(java.util.Calendar.DAY_OF_MONTH);
            endTime.byHour  = (byte) cal.get(java.util.Calendar.HOUR_OF_DAY);
            endTime.byMinute = (byte) cal.get(java.util.Calendar.MINUTE);
            endTime.bySecond = (byte) cal.get(java.util.Calendar.SECOND);
            endTime.byLocalOrUTC = 0;

            // ── [4] 构建V50查找条件 ──
            NET_DVR_FILECOND_V50 findCond = new NET_DVR_FILECOND_V50();
            // 设置 struStreamID — 用通道号方式
            findCond.struStreamID.dwSize = 72;  // 结构体大小
            // byID 默认全0（使用通道号方式）
            findCond.struStreamID.dwChannel = channel;
            findCond.struStartTime = startTime;
            findCond.struStopTime  = endTime;
            findCond.byFindType    = 0;     // 普通卷
            findCond.byDrawFrame   = 0;     // 不抽帧
            findCond.byQuickSearch = 0;     // 普通查询
            findCond.byStreamType  = (byte) 0xff; // 全部码流
            findCond.dwFileType    = 0xff;  // 全部文件类型
            findCond.dwVolumeNum   = 0;
            findCond.byIsLocked    = (byte) 0xff; // 全部
            findCond.byNeedCard    = 0;
            findCond.byOnlyAudioFile = 0;
            findCond.bySpecialFindInfoType = 0;
            findCond.dwTimeout    = 10000; // 10秒超时
            findCond.write();

            // ── [5] FindFile_V50 ──
            NativeLong findHandle = sdk.NET_DVR_FindFile_V50(userId, findCond);
            if (findHandle.longValue() == -1) {
                int e = sdk.NET_DVR_GetLastError();
                System.out.println("[SIZE] error=V50查找录像失败(" + e + " " + errDesc(e) + ")");
                sdk.NET_DVR_Logout(userId);
                sdk.NET_DVR_Cleanup();
                System.exit(1);
            }

            // ── [6] FindNextFile_V30 循环累加 dwFileSize ──
            // 注意：V50查找用 V30 的 FindNext 遍历即可，因为返回的结构体是兼容的
            long totalBytes = 0;
            int fileCount   = 0;

            while (true) {
                NET_DVR_FINDDATA_V30 findData = new NET_DVR_FINDDATA_V30();
                findData.read();
                NativeLong findResult = sdk.NET_DVR_FindNextFile_V30(findHandle, findData);
                int result = findResult.intValue();

                if (result == 1000) {
                    // NET_DVR_FILE_SUCCESS = 1000, 找到了一个文件
                    totalBytes += findData.dwFileSize & 0xFFFFFFFFL;  // unsigned int → long
                    fileCount++;
                } else if (result == 1002) {
                    // NET_DVR_NOMOREFILE = 1002, 没有更多文件
                    break;
                } else if (result == -1) {
                    int e = sdk.NET_DVR_GetLastError();
                    System.out.println("[SIZE] error=FindNextFile_V30出错(" + e + " " + errDesc(e) + ")");
                    sdk.NET_DVR_FindClose_V30(findHandle);
                    sdk.NET_DVR_Logout(userId);
                    sdk.NET_DVR_Cleanup();
                    System.exit(1);
                } else {
                    // 其他返回码
                    System.out.println("[SIZE] error=FindNextFile_V30返回" + result);
                    sdk.NET_DVR_FindClose_V30(findHandle);
                    sdk.NET_DVR_Logout(userId);
                    sdk.NET_DVR_Cleanup();
                    System.exit(1);
                }
            }

            // ── [7] 关闭查找 ──
            sdk.NET_DVR_FindClose_V30(findHandle);
            sdk.NET_DVR_Logout(userId);
            sdk.NET_DVR_Cleanup();

            // ── [8] 输出结果 ──
            System.out.println("[SIZE] total_bytes=" + totalBytes + " file_count=" + fileCount);
            System.exit(0);

        } catch (Exception e) {
            System.out.println("[SIZE] error=" + e.getMessage());
            try {
                if (sdk != null && userId.longValue() != -1) {
                    sdk.NET_DVR_Logout(userId);
                }
                if (sdk != null) {
                    sdk.NET_DVR_Cleanup();
                }
            } catch (Exception ex) { /* ignore */ }
            System.exit(1);
        }
    }
}
