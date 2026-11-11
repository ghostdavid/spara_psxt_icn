import atexit
import os
import sys
import tempfile
from pathlib import Path


def load_matplotlib():
    if not getattr(sys, 'frozen', False):
        import matplotlib
        matplotlib.use('TkAgg')
        return matplotlib

    base = Path(os.environ.get('LOCALAPPDATA') or Path.home())
    config = base / 'SParamPowerSum' / 'matplotlib'
    try:
        config.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=config):
            pass
    except OSError:
        temporary = tempfile.TemporaryDirectory(prefix='sparam_matplotlib_')
        atexit.register(temporary.cleanup)
        config = Path(temporary.name)

    resources = Path(__file__).resolve().parent / 'matplotlib' / 'mpl-data'
    os.environ['MPLCONFIGDIR'] = str(config)
    os.environ['MATPLOTLIBRC'] = str(resources / 'matplotlibrc')
    os.environ['MPLBACKEND'] = 'TkAgg'
    previous = Path.cwd()
    try:
        # Matplotlib searches the working directory before MATPLOTLIBRC.
        os.chdir(resources)
        import matplotlib
    finally:
        os.chdir(previous)
    matplotlib.rcdefaults()
    matplotlib.use('TkAgg')
    return matplotlib
