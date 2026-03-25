import urllib.request
import sys

# 使用华为云镜像
url = "https://mirrors.huaweicloud.com/java/jdk/11.0.9/jdk-11.0.9_windows-x64_bin.zip"
output = "C:/Users/Administrator/Downloads/openjdk.zip"

print(f"开始下载Java: {url}")
try:
    urllib.request.urlretrieve(url, output)
    print(f"下载完成: {output}")
except Exception as e:
    print(f"下载失败: {e}")
    # 尝试其他镜像
    try:
        url = "https://mirrors.aliyun.com/AdoptOpenJDK/11/jdk/x64/windows/OpenJDK11U-jdk_x64_windows_hotspot_11.0.21_9.zip"
        print(f"尝试备用镜像: {url}")
        urllib.request.urlretrieve(url, output)
        print(f"下载完成: {output}")
    except Exception as e2:
        print(f"备用镜像也失败: {e2}")
        sys.exit(1)
