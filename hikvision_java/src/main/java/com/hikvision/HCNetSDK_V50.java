package com.hikvision;

import com.sun.jna.NativeLong;
import com.sun.jna.Pointer;
import com.sun.jna.Structure;
import com.sun.jna.WString;
import com.sun.jna.examples.win32.W32API.HWND;

import java.util.Arrays;
import java.util.List;

public class HCNetSDK_V50 {
    
    public static class NET_DVR_TIME_V50 extends Structure {
        public static class ByReference extends NET_DVR_TIME_V50 implements Structure.ByReference {}
        
        public short wYear;   // 年
        public byte byMonth;  // 月 1-12
        public byte byDay;    // 日 1-31
        public byte byHour;   // 时 0-23
        public byte byMinute; // 分 0-59
        public byte bySecond; // 秒 0-59
        public short wMillisecond; // 毫秒
        public byte byRes;    // 保留
        
        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("wYear", "byMonth", "byDay", "byHour", "byMinute", 
                               "bySecond", "wMillisecond", "byRes");
        }
    }
    
    public static class NET_DVR_STREAM_INFO extends Structure {
        public static class ByReference extends NET_DVR_STREAM_INFO implements Structure.ByReference {}
        
        public int dwSize;
        public byte[] byID = new byte[64];  // STREAM_ID_LEN=64
        public int dwChannel;
        public byte[] byRes = new byte[32];
        
        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("dwSize", "byID", "dwChannel", "byRes");
        }
    }
    
    public static class NET_DVR_VOD_PARA_V50 extends Structure {
        public static class ByReference extends NET_DVR_VOD_PARA_V50 implements Structure.ByReference {}
        
        public int dwSize;
        public NET_DVR_STREAM_INFO struIDInfo;
        public NET_DVR_TIME_V50 struBeginTime;
        public NET_DVR_TIME_V50 struEndTime;
        public HWND hWnd;
        public byte byDrawFrame;        // 0-不抽帧, 1-抽帧
        public byte byVolumeType;       // 0-普通录像卷, 1-存档卷
        public byte byVolumeNum;       // 存档卷号
        public byte byStreamType;      // 0-主码流, 1-子码流, 2-码流三
        public int dwFileIndex;         // 存档卷录像文件索引
        public byte byAudioFile;       // 0-不回放音频文件, 1-回放音频文件
        public byte byCourseFile;       // 0-否, 1-是
        public byte byPlayMode;         // 0-正放, 1-倒放
        public byte byLinkMode;         // 0-TCP, 1-NPQ
        public byte byDownload;         // 0-否, 1-是(直接下载!)
        public byte byOptimalStreamType; // 0-否, 1-按最优码流类型回放
        public byte byDisplayBufNum;    // 播放缓冲帧数
        public byte byNPQMode;          // NPQ模式: 0-直连, 1-过流媒体
        public byte[] sUserName = new byte[32]; // 二次认证用户名 NAME_LEN=32
        public byte[] sPassword = new byte[16]; // 二次认证密码 PASSWD_LEN=16
        public byte byRemoteFile;      // 0-否, 1-是
        public byte[] byRes2 = new byte[202];
        public byte byHls;             // HLS回放: 0-否, 1-是
        public String pSavedFileName;   // 下载时的保存文件路径 (byDownload=1时有效)
        
        @Override
        protected List<String> getFieldOrder() {
            return Arrays.asList("dwSize", "struIDInfo", "struBeginTime", "struEndTime",
                               "hWnd", "byDrawFrame", "byVolumeType", "byVolumeNum", 
                               "byStreamType", "dwFileIndex", "byAudioFile", "byCourseFile",
                               "byPlayMode", "byLinkMode", "byDownload", "byOptimalStreamType",
                               "byDisplayBufNum", "byNPQMode", "sUserName", "sPassword",
                               "byRemoteFile", "byRes2", "byHls", "pSavedFileName");
        }
    }
}
