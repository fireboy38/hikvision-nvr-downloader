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
    # 高DPI设置：禁用Qt自动缩放，使用系统DPI
    # 这样UI在所有缩放比例下保持一致的物理大小
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"  # 禁用自动缩放
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"  # 禁用自动检测
    os.environ["QT_SCALE_FACTOR"] = "1"  # 固定1:1缩放
    
    # 但启用高DPI字体渲染
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
