package com.hikvision;

import com.sun.jna.Library;
import com.sun.jna.Native;
import com.sun.jna.NativeLibrary;
import java.io.File;

/**
 * Simple test to verify SDK loading with multiple approaches
 */
public class test_load {

    // SDK路径
    private static final String SDK_DIR = "C:\\Users\\Administrator\\CH-HCNetSDKV6.1.6.45_build20210302_win64_20210508181836\\CH-HCNetSDKV6.1.6.45_build20210302_win64\\库文件";
    private static final String HCNETSDK_DLL = "HCNetSDK.dll";

    public interface HCNetSDK extends Library {
        boolean NET_DVR_Init();
    }

    public static void main(String[] args) {
        System.out.println("=".repeat(50));
        System.out.println("Hikvision SDK Loading Test");
        System.out.println("=".repeat(50));

        // 设置JNA查找路径
        System.out.println("\n[Step 1] Setting JNA library path...");
        System.setProperty("jna.library.path", SDK_DIR);
        System.setProperty("jna.boot.library.path", SDK_DIR);
        System.out.println("    jna.library.path = " + System.getProperty("jna.library.path"));

        // 列出目录中的DLL文件
        System.out.println("\n[Step 2] Checking DLL files in SDK directory...");
        File sdkDir = new File(SDK_DIR);
        if (sdkDir.exists() && sdkDir.isDirectory()) {
            String[] dllFiles = sdkDir.list((dir, name) -> name.toLowerCase().endsWith(".dll"));
            System.out.println("    Found " + dllFiles.length + " DLL files:");
            for (String dll : dllFiles) {
                System.out.println("      - " + dll);
            }
        } else {
            System.out.println("    [ERROR] SDK directory not found: " + SDK_DIR);
            return;
        }

        // 方法1: 直接使用DLL名称（需要jna.library.path正确设置）
        System.out.println("\n[Step 3] Method 1: Load with just DLL name...");
        try {
            HCNetSDK sdk1 = (HCNetSDK) Native.loadLibrary(HCNETSDK_DLL, HCNetSDK.class);
            System.out.println("    [OK] Loaded with name: " + HCNETSDK_DLL);
            testSdkFunction(sdk1);
            return;
        } catch (Throwable e) {
            System.out.println("    [FAIL] " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        // 方法2: 使用绝对路径
        System.out.println("\n[Step 4] Method 2: Load with absolute path...");
        String absPath = SDK_DIR + "\\" + HCNETSDK_DLL;
        try {
            HCNetSDK sdk2 = (HCNetSDK) Native.loadLibrary(absPath, HCNetSDK.class);
            System.out.println("    [OK] Loaded with path: " + absPath);
            testSdkFunction(sdk2);
            return;
        } catch (Throwable e) {
            System.out.println("    [FAIL] " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        // 方法3: 先添加到NativeLibrary，再加载
        System.out.println("\n[Step 5] Method 3: Add to NativeLibrary first...");
        try {
            NativeLibrary.addSearchPath(HCNETSDK_DLL, SDK_DIR);
            HCNetSDK sdk3 = (HCNetSDK) Native.loadLibrary(HCNETSDK_DLL, HCNetSDK.class);
            System.out.println("    [OK] Loaded after adding to NativeLibrary");
            testSdkFunction(sdk3);
            return;
        } catch (Throwable e) {
            System.out.println("    [FAIL] " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        // 方法4: 尝试使用原始路径
        System.out.println("\n[Step 6] Method 4: Try with forward slashes...");
        try {
            String forwardPath = SDK_DIR.replace("\\", "/") + "/" + HCNETSDK_DLL;
            HCNetSDK sdk4 = (HCNetSDK) Native.loadLibrary(forwardPath, HCNetSDK.class);
            System.out.println("    [OK] Loaded with forward slashes");
            testSdkFunction(sdk4);
            return;
        } catch (Throwable e) {
            System.out.println("    [FAIL] " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        System.out.println("\n" + "=".repeat(50));
        System.out.println("All loading methods failed!");
        System.out.println("=".repeat(50));
    }

    private static void testSdkFunction(HCNetSDK sdk) {
        System.out.println("\n[Step 7] Testing NET_DVR_Init()...");
        try {
            boolean result = sdk.NET_DVR_Init();
            System.out.println("    Result: " + result);
            if (result) {
                System.out.println("\n" + "=".repeat(50));
                System.out.println("SUCCESS! SDK is working!");
                System.out.println("=".repeat(50));
            }
        } catch (Throwable e) {
            System.out.println("    [ERROR] " + e.getMessage());
        }
    }
}
