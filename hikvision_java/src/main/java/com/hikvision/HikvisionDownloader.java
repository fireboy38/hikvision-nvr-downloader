package com.hikvision;

import com.sun.jna.Callback;
import com.sun.jna.Library;
import com.sun.jna.Native;
import com.sun.jna.NativeLong;
import com.sun.jna.Pointer;
import com.sun.jna.Structure;
import com.sun.jna.ptr.IntByReference;
import com.sun.jna.ptr.NativeLongByReference;

/**
 * Hikvision SDK Java Demo - NVR Video Download
 */
public class HikvisionDownloader {

    // SDK path - updated to correct location
    private static final String HCNETSDK_PATH = "C:\\Users\\Administrator\\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\\CH-HCNetSDKV6.1.6.45_build20210302_win64\\库文件\\HCNetSDK.dll";

    // Static SDK instance with lazy loading
    private static HCNetSDK sdkInstance = null;

    // Hikvision SDK interface
    public interface HCNetSDK extends Library {

        static HCNetSDK getInstance() {
            if (sdkInstance == null) {
                try {
                    // First try with absolute path
                    sdkInstance = (HCNetSDK) Native.loadLibrary(HCNETSDK_PATH, HCNetSDK.class);
                } catch (UnsatisfiedLinkError e1) {
                    System.out.println("    First load attempt failed: " + e1.getMessage());
                    try {
                        // Try with just the DLL name if the DLLs are in system path or java.library.path
                        sdkInstance = (HCNetSDK) Native.loadLibrary("HCNetSDK", HCNetSDK.class);
                    } catch (UnsatisfiedLinkError e2) {
                        System.out.println("    Second load attempt failed: " + e2.getMessage());
                        throw e2;
                    }
                }
            }
            return sdkInstance;
        }
        
        // Init
        boolean NET_DVR_Init();
        boolean NET_DVR_Cleanup();
        
        // Login
        NativeLong NET_DVR_Login_V30(String sDVRIP, short wDVRPort, String sUserName, 
                                     String sPassword, NET_DVR_DEVICEINFO_V30 lpDeviceInfo);
        boolean NET_DVR_Logout(NativeLong lUserID);
        
        // Download by time
        NativeLong NET_DVR_GetFileByTime(NativeLong lUserID, NativeLong lChannel, 
                                          NET_DVR_TIME lpStartTime, NET_DVR_TIME lpStopTime, 
                                          String sFileName);
        
        // Playback control
        // NET_DVR_PLAYSTART = 1, NET_DVR_PLAYSTOP = 2, NET_DVR_PLAYGETPOS = 3
        NativeLong NET_DVR_PlayBackControl(NativeLong lPlayHandle, int dwControlCode, 
                                           int dwInValue, IntByReference lpOutValue);
        
        // Stop download
        boolean NET_DVR_StopGetFile(NativeLong lFileHandle);
        
        // Get error code
        int NET_DVR_GetLastError();
    }
    
    // Device info structure
    public static class NET_DVR_DEVICEINFO_V30 extends Structure {
        public byte[] sSerialNumber = new byte[48];
        public byte byAlarmInPortNum;
        public byte byAlarmOutPortNum;
        public byte byDiskNum;
        public byte byDVRType;
        public byte byChanNum;
        public byte byStartChan;
        public byte byAudioChanNum;
        public byte byIPChanNum;
    }
    
    // Time structure
    public static class NET_DVR_TIME extends Structure {
        public int dwYear;
        public int dwMonth;
        public int dwDay;
        public int dwHour;
        public int dwMinute;
        public int dwSecond;
    }
    
    // Constants
    private static final int NET_DVR_PLAYSTART = 1;
    private static final int NET_DVR_PLAYSTOP = 2;
    private static final int NET_DVR_PLAYGETPOS = 3;
    
    public static void main(String[] args) {
        System.out.println("======================================");
        System.out.println("Hikvision SDK Video Download Test");
        System.out.println("======================================");
        
        // Device params
        String ip = "10.4.130.245";
        int port = 8000;
        String username = "admin";
        String password = "a1111111";
        int channel = 1;

        // Get SDK instance
        HCNetSDK sdk = null;
        try {
            System.out.println("[0] Loading SDK...");
            sdk = HCNetSDK.getInstance();
            System.out.println("    [OK] SDK loaded");
        } catch (Exception e) {
            System.out.println("    [FAIL] " + e.getMessage());
            e.printStackTrace();
            return;
        }

        // Init SDK
        System.out.println("[1] Init SDK...");
        if (!sdk.NET_DVR_Init()) {
            System.out.println("    [FAIL] Error: " + sdk.NET_DVR_GetLastError());
            return;
        }
        System.out.println("    [OK]");

        // Login
        System.out.println("[2] Login " + ip + ":" + port + "...");
        NET_DVR_DEVICEINFO_V30 deviceInfo = new NET_DVR_DEVICEINFO_V30();
        NativeLong userId = sdk.NET_DVR_Login_V30(ip, (short)port, username, password, deviceInfo);

        if (userId.longValue() == -1) {
            System.out.println("    [FAIL] Error: " + sdk.NET_DVR_GetLastError());
            sdk.NET_DVR_Cleanup();
            return;
        }
        
        // Get serial number
        String serialNumber = new String(deviceInfo.sSerialNumber).trim();
        System.out.println("    [OK] Serial: " + serialNumber);
        
        // Set download time - last 1 minute
        NET_DVR_TIME startTime = new NET_DVR_TIME();
        NET_DVR_TIME endTime = new NET_DVR_TIME();
        
        java.util.Calendar cal = java.util.Calendar.getInstance();
        endTime.dwYear = cal.get(java.util.Calendar.YEAR);
        endTime.dwMonth = cal.get(java.util.Calendar.MONTH) + 1;
        endTime.dwDay = cal.get(java.util.Calendar.DAY_OF_MONTH);
        endTime.dwHour = cal.get(java.util.Calendar.HOUR_OF_DAY);
        endTime.dwMinute = cal.get(java.util.Calendar.MINUTE);
        endTime.dwSecond = cal.get(java.util.Calendar.SECOND);
        
        cal.add(java.util.Calendar.MINUTE, -1);
        startTime.dwYear = cal.get(java.util.Calendar.YEAR);
        startTime.dwMonth = cal.get(java.util.Calendar.MONTH) + 1;
        startTime.dwDay = cal.get(java.util.Calendar.DAY_OF_MONTH);
        startTime.dwHour = cal.get(java.util.Calendar.HOUR_OF_DAY);
        startTime.dwMinute = cal.get(java.util.Calendar.MINUTE);
        startTime.dwSecond = cal.get(java.util.Calendar.SECOND);
        
        System.out.println("[3] Download time range:");
        System.out.println("    Start: " + startTime.dwYear + "-" + startTime.dwMonth + "-" + startTime.dwDay 
                          + " " + startTime.dwHour + ":" + startTime.dwMinute + ":" + startTime.dwSecond);
        System.out.println("    End: " + endTime.dwYear + "-" + endTime.dwMonth + "-" + endTime.dwDay 
                          + " " + endTime.dwHour + ":" + endTime.dwMinute + ":" + endTime.dwSecond);
        
        // Save path
        String savePath = "C:\\Users\\Administrator\\WorkBuddy\\20260323192840\\hikvision_java\\downloads\\" 
                         + "ch" + channel + "_" + System.currentTimeMillis() + ".mp4";
        
        // Ensure directory exists
        new java.io.File(savePath).getParentFile().mkdirs();
        
        System.out.println("[4] Start download...");
        System.out.println("    Channel: " + channel);
        System.out.println("    Save: " + savePath);
        
        // Get download handle
        NativeLong channelNum = new NativeLong(channel);
        NativeLong downloadHandle = sdk.NET_DVR_GetFileByTime(
            userId, channelNum, startTime, endTime, savePath);

        if (downloadHandle.longValue() == -1) {
            System.out.println("    [FAIL] Get handle failed, Error: " + sdk.NET_DVR_GetLastError());
            sdk.NET_DVR_Logout(userId);
            sdk.NET_DVR_Cleanup();
            return;
        }

        // Start download - key step
        System.out.println("    Send start command...");
        NativeLong startResult = sdk.NET_DVR_PlayBackControl(
            downloadHandle, NET_DVR_PLAYSTART, 0, null);
        
        if (startResult.longValue() == -1) {
            System.out.println("    [FAIL] Start download failed, Error: " + sdk.NET_DVR_GetLastError());
            sdk.NET_DVR_StopGetFile(downloadHandle);
            sdk.NET_DVR_Logout(userId);
            sdk.NET_DVR_Cleanup();
            return;
        }

        // Wait for download
        System.out.println("    Downloading...");
        IntByReference pos = new IntByReference(0);
        int lastProgress = -1;
        long startTimeMs = System.currentTimeMillis();

        while (true) {
            try {
                Thread.sleep(1000);
            } catch (InterruptedException e) {
                e.printStackTrace();
            }

            // Get progress
            sdk.NET_DVR_PlayBackControl(downloadHandle, NET_DVR_PLAYGETPOS, 0, pos);
            int progress = pos.getValue();
            
            if (progress != lastProgress && progress >= 0) {
                System.out.println("    Progress: " + progress + "%");
                lastProgress = progress;
            }
            
            // Download complete
            if (progress >= 100) {
                System.out.println("    [OK] Download complete!");
                break;
            }
            
            // Download error
            if (progress > 100) {
                System.out.println("    [FAIL] Download error, Error: " + sdk.NET_DVR_GetLastError());
                break;
            }
            
            // Timeout check (90 seconds)
            long elapsed = System.currentTimeMillis() - startTimeMs;
            if (elapsed > 90000) {
                System.out.println("    [FAIL] Timeout (90s)");
                break;
            }
        }
        
        // Check file
        java.io.File file = new java.io.File(savePath);
        if (file.exists()) {
            long size = file.length();
            System.out.println("    File size: " + (size / 1024.0 / 1024.0) + " MB");
        } else {
            System.out.println("    [WARN] File not exists");
        }
        
        // Cleanup
        System.out.println("[5] Cleanup...");
        sdk.NET_DVR_StopGetFile(downloadHandle);
        sdk.NET_DVR_Logout(userId);
        sdk.NET_DVR_Cleanup();
        
        System.out.println("\nDone!");
    }
}