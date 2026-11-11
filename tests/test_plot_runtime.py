"""源码配置隔离回归：python -B tests/test_plot_runtime.py。"""
import os
from pathlib import Path
import subprocess
import sys
import unittest

PROJECT = Path(__file__).resolve().parent.parent


class PlotRuntimeTests(unittest.TestCase):
    def test_isolation(self):
        for fallback in (False, True):
            with self.subTest(fallback=fallback):
                code = r'''
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import plot_runtime

resources = Path(importlib.util.find_spec('matplotlib').origin).parent.parent
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    (folder / 'matplotlibrc').write_text('text.usetex: True\n', encoding='utf-8')
    cache = folder / 'cache'
    if FALLBACK:
        cache.write_text('blocked', encoding='utf-8')
    previous = Path.cwd()
    os.chdir(folder)
    try:
        with patch.object(sys, 'frozen', True, create=True), \
             patch.object(plot_runtime, '__file__', str(resources / 'plot_runtime.py')), \
             patch.dict(os.environ, {'LOCALAPPDATA': str(cache),
                                     'MPLCONFIGDIR': str(folder),
                                     'MATPLOTLIBRC': str(folder / 'matplotlibrc'),
                                     'MPLBACKEND': 'invalid_backend'}):
            mpl = plot_runtime.load_matplotlib()
            assert Path.cwd() == folder
            assert not mpl.rcParams['text.usetex']
            assert mpl.get_backend().lower() == 'tkagg'
            config = Path(mpl.get_configdir())
            assert config.is_dir()
            if not FALLBACK:
                assert config == cache / 'SParamPowerSum' / 'matplotlib'
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            figure = Figure()
            figure.subplots().set_title('Isolation test')
            FigureCanvasAgg(figure).draw()
    finally:
        os.chdir(previous)
'''.replace('FALLBACK', repr(fallback))
                result = subprocess.run(
                    [sys.executable, '-B', '-c', code], cwd=PROJECT,
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
