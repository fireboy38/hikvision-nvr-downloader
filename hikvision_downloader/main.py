# 四川新数录像批量下载器
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
    # 高DPI缩放设置（必须在创建QApplication之前）
    # 关键：不设置QT_SCALE_FACTOR，让Qt自动检测系统缩放比例
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    # 禁用Qt的缩放因子覆盖，使用系统设置
    # os.environ["QT_SCALE_FACTOR"] = "1"  # 注释掉，避免强制1:1缩放
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName("四川新数录像批量下载器")
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
