# 海康NVR批量录像下载工具
# 主程序入口

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from gui.main_window import MainWindow
from utils.logger import logger


def main():
    """主函数"""
    # 启用高DPI缩放
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName("海康NVR批量录像下载工具")
    app.setApplicationVersion("1.0.0")
    
    # 设置样式
    app.setStyle('Fusion')
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    logger.info("应用程序启动")
    
    # 运行应用
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
