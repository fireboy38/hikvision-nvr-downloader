package com.hikvision;

import com.sun.jna.Library;
import com.sun.jna.Native;
import com.sun.jna.NativeLong;
import com.sun.jna.Pointer;
import com.sun.jna.Structure;
import com.sun.jna.ptr.IntByReference;

/**
 * 设置通道名称测试
 */
public class SetChannelName {

    private static final String SDK_DIR = "C:\\Users\\Administrator\\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\\CH-HCNetSDKV6.1.6.45_build20210302_win64\\库文件";

    public interface HCNetSDK extends Library {
        static HCNetSDK INSTANCE = (HCNetSDK) Native.loadLibrary("HCNetSDK", HCNetSDK.class);

        boolean NET_DVR_Init();
        boolean NET_DVR_Cleanup();

        NativeLong NET_DVR_Login_V30(String sDVRIP, short wDVRPort, String sUserName,
                                     String sPassword, NET_DVR_DEVICEINFO_V30 lpDeviceInfo);
        boolean NET_DVR_Logout(NativeLong lUserID);

        // NET_DVR_SetDeviceConfig - 设置设备配置
        boolean NET_DVR_SetDeviceConfig(NativeLong lUserID, int dwCommand, int dwCount,
                                        Pointer pInConfig, int dwInConfigSize,
                                        Pointer pOutConfig, int dwOutConfigSize,
                                        Pointer lpStatus);

        // NET_DVR_GetDeviceConfig - 获取设备配置
        boolean NET_DVR_GetDeviceConfig(NativeLong lUserID, int dwCommand, int dwCount,
                                        Pointer pInConfig, int dwInConfigSize,
                                        Pointer pOutConfig, int dwOutConfigSize,
                                        Pointer lpStatus);

        int NET_DVR_GetLastError();
    }

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

    // Channel name structure - 32 bytes
    public static class NET_DVR_CHANNELNAME extends Structure {
        public byte[] sName = new byte[32];  // 通道名称
    }

    // For input config - need to match SDK's structure
    public static class NET_DVR_SINGLE_CHANNEL extends Structure {
        public int dwChannel;  // 通道号
    }

    public static void main(String[] args) {
        System.out.println("======================================");
        System.out.println("Set Channel Name Test");
        System.out.println("======================================");

        // Set library path
        System.setProperty("jna.library.path", SDK_DIR);

        String ip = "10.4.130.245";
        int port = 8000;
        String username = "admin";
        String password = "a1111111";
        int channel = 1;
        String newName = "正大门停车场通道1";

        // Init SDK
        System.out.println("\n[1] Init SDK...");
        if (!HCNetSDK.INSTANCE.NET_DVR_Init()) {
            System.out.println("    [FAIL] Error: " + HCNetSDK.INSTANCE.NET_DVR_GetLastError());
            return;
        }
        System.out.println("    [OK]");

        // Login
        System.out.println("[2] Login " + ip + ":" + port + "...");
        NET_DVR_DEVICEINFO_V30 deviceInfo = new NET_DVR_DEVICEINFO_V30();
        NativeLong userId = HCNetSDK.INSTANCE.NET_DVR_Login_V30(ip, (short)port, username, password, deviceInfo);

        if (userId.longValue() == -1) {
            System.out.println("    [FAIL] Error: " + HCNetSDK.INSTANCE.NET_DVR_GetLastError());
            HCNetSDK.INSTANCE.NET_DVR_Cleanup();
            return;
        }
        System.out.println("    [OK] UserID: " + userId);

        // First, get current channel name
        System.out.println("\n[3] Getting current channel " + channel + " name...");
        NET_DVR_CHANNELNAME currentName = new NET_DVR_CHANNELNAME();
        NET_DVR_SINGLE_CHANNEL inConfig = new NET_DVR_SINGLE_CHANNEL();
        inConfig.dwChannel = channel;
        inConfig.write();

        IntByReference status = new IntByReference(0);

        // NET_DVR_GET_CHANNELNAME = 1061
        int NET_DVR_GET_CHANNELNAME = 1061;

        boolean getResult = HCNetSDK.INSTANCE.NET_DVR_GetDeviceConfig(
            userId,
            NET_DVR_GET_CHANNELNAME,
            1,
            inConfig.getPointer(),
            inConfig.size(),
            currentName.getPointer(),
            currentName.size(),
            status.getPointer()
        );

        if (getResult) {
            currentName.read();
            String nameStr;
            try {
                nameStr = new String(currentName.sName, "GBK").trim();
            } catch (java.io.UnsupportedEncodingException e) {
                nameStr = new String(currentName.sName).trim();
            }
            System.out.println("    Current name: '" + nameStr + "'");
        } else {
            System.out.println("    [WARN] Get failed, error: " + HCNetSDK.INSTANCE.NET_DVR_GetLastError());
        }

        // Now set channel name
        System.out.println("\n[4] Setting channel " + channel + " name to: " + newName);

        // Create channel name structure with GBK encoding
        NET_DVR_CHANNELNAME channelName = new NET_DVR_CHANNELNAME();
        try {
            byte[] nameBytes = newName.getBytes("GBK");
            int copyLen = Math.min(nameBytes.length, channelName.sName.length);
            System.arraycopy(nameBytes, 0, channelName.sName, 0, copyLen);
        } catch (Exception e) {
            System.out.println("    [ERROR] GBK encoding failed: " + e.getMessage());
            // Fallback to UTF-8
            byte[] nameBytes = newName.getBytes();
            int copyLen = Math.min(nameBytes.length, channelName.sName.length);
            System.arraycopy(nameBytes, 0, channelName.sName, 0, copyLen);
        }
        channelName.write();

        // NET_DVR_SET_CHANNELNAME = 1060
        int NET_DVR_SET_CHANNELNAME = 1060;

        boolean result = HCNetSDK.INSTANCE.NET_DVR_SetDeviceConfig(
            userId,
            NET_DVR_SET_CHANNELNAME,
            1,
            inConfig.getPointer(),
            inConfig.size(),
            channelName.getPointer(),
            channelName.size(),
            status.getPointer()
        );

        if (result) {
            System.out.println("    [OK] Channel name set successfully!");
        } else {
            System.out.println("    [FAIL] Error: " + HCNetSDK.INSTANCE.NET_DVR_GetLastError());
        }

        // Verify
        System.out.println("\n[5] Verifying...");
        try { Thread.sleep(1000); } catch (Exception e) {}

        currentName = new NET_DVR_CHANNELNAME();
        getResult = HCNetSDK.INSTANCE.NET_DVR_GetDeviceConfig(
            userId,
            NET_DVR_GET_CHANNELNAME,
            1,
            inConfig.getPointer(),
            inConfig.size(),
            currentName.getPointer(),
            currentName.size(),
            status.getPointer()
        );

        if (getResult) {
            currentName.read();
            try {
                String nameStr = new String(currentName.sName, "GBK").trim();
                System.out.println("    New name: '" + nameStr + "'");
            } catch (Exception e) {
                String nameStr = new String(currentName.sName).trim();
                System.out.println("    New name: '" + nameStr + "'");
            }
        }

        // Logout
        System.out.println("\n[6] Logout...");
        HCNetSDK.INSTANCE.NET_DVR_Logout(userId);

        // Cleanup
        System.out.println("[7] Cleanup...");
        HCNetSDK.INSTANCE.NET_DVR_Cleanup();

        System.out.println("\nDone!");
    }
}
