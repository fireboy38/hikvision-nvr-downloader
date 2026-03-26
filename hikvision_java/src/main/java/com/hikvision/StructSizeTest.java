package com.hikvision;

import com.sun.jna.win32.StdCallLibrary;
import com.sun.jna.Native;
import com.sun.jna.NativeLong;
import com.sun.jna.Structure;
import java.util.Arrays;
import java.util.List;

public class StructSizeTest {
    public static void main(String[] args) {
        try {
            NET_DVR_FILECOND_V50 fc = new NET_DVR_FILECOND_V50();
            fc.write();
            System.out.println("NET_DVR_FILECOND_V50 size: " + fc.size());
            System.out.println("  struStreamID size: " + fc.struStreamID.size());
            System.out.println("  struStartTime size: " + fc.struStartTime.size());
            System.out.println("  struStopTime size: " + fc.struStopTime.size());
            System.out.println("  uSpecialFindInfo size: " + fc.uSpecialFindInfo.size());

            NET_DVR_FINDDATA_V30 fd = new NET_DVR_FINDDATA_V30();
            fd.write();
            System.out.println("NET_DVR_FINDDATA_V30 size: " + fd.size());

            NET_DVR_FINDDATA_V40 fd40 = new NET_DVR_FINDDATA_V40();
            fd40.write();
            System.out.println("NET_DVR_FINDDATA_V40 size: " + fd40.size());

            NET_DVR_FINDDATA_V50 fd50 = new NET_DVR_FINDDATA_V50();
            fd50.write();
            System.out.println("NET_DVR_FINDDATA_V50 size: " + fd50.size());

            NET_DVR_STREAM_INFO si = new NET_DVR_STREAM_INFO();
            si.write();
            System.out.println("NET_DVR_STREAM_INFO size: " + si.size());
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
