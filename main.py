"""S参数串扰计算工具 —— 程序入口。

用法:
    python main.py                  # 打开空界面
    python main.py 路径/文件.s4p    # 打开界面并自动导入指定 S 参数文件

依赖安装: pip install numpy scipy matplotlib ttkbootstrap
运行环境: Python 3.10+ (项目 venv 为 3.14)
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True

import ttkbootstrap as ttk

from app import APP_NAME, APP_VERSION, SParamPowerSumApp


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)

    extension = 'ico' if sys.platform == 'win32' else 'png'
    icon_path = Path(__file__).resolve().parent / 'assets' / f'app_icon.{extension}'
    root = ttk.Window(title=f'{APP_NAME} v{APP_VERSION}', themename='cosmo',
                      iconphoto=str(icon_path))
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            'SParamTools.CrosstalkNoise')
    app = SParamPowerSumApp(root)

    if argv:
        root.after(200, lambda: app.import_s_params(argv[0]))

    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
