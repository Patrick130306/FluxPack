"""FluxPack 桌面启动器 —— 双击运行即打开 GUI"""
import sys
import os

# 确保能找到项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ui.desktop import main

if __name__ == "__main__":
    main()
