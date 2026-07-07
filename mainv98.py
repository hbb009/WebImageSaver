import sys
import os
import ctypes

def _is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def _relaunch_as_admin():
    """用管理员权限重新启动当前脚本，然后退出当前进程"""
    script = os.path.abspath(sys.argv[0])
    params = " ".join(f'"{a}"' for a in sys.argv[1:])
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable,
        f'"{script}" {params}',
        None, 1
    )
    sys.exit(0)

if not _is_admin():
    _relaunch_as_admin()

from PyQt5.QtWidgets import QApplication
from ui_main import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
