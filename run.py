"""启动脚本 - 方便直接运行"""
import sys
from pathlib import Path

# 添加 src 目录到路径
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# 运行主程序
from main import main
main()