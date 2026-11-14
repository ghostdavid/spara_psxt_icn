"""只读绘图回归：python -B tests/test_plot_runtime.py。"""
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


class PlotRuntimeTests(unittest.TestCase):
    def test_read_only_rendering(self):
        code = r'''
import os
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    (folder / 'matplotlibrc').write_text('text.usetex: True\n', encoding='utf-8')
    os.environ.update(LOCALAPPDATA=str(folder / 'absent'),
                      MPLCONFIGDIR=str(folder / 'absent'),
                      MATPLOTLIBRC=str(folder / 'matplotlibrc'),
                      MPLBACKEND='invalid_backend')
    previous = Path.cwd()
    os.chdir(folder)
    sys.path.insert(0, str(previous))
    events = []
    active = True
    def audit(event, args):
        if not active:
            return
        if event == 'open':
            _, mode, flags = args
            if (mode and any(c in mode for c in 'wax+')) or flags & (
                    os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                events.append((event, str(args)))
                raise AssertionError(f'Unexpected write: {args}')
        elif event in ('os.mkdir', 'os.remove', 'os.rename', 'os.rmdir',
                       'tempfile.mkstemp', 'tempfile.mkdtemp'):
            events.append((event, str(args)))
            raise AssertionError(f'Unexpected filesystem mutation: {event} {args}')
    sys.addaudithook(audit)
    try:
        import plot_runtime
        mpl = plot_runtime.load_matplotlib()
        assert plot_runtime.load_matplotlib() is mpl
        assert Path.cwd() == folder
        assert not mpl.rcParams['text.usetex']
        assert mpl.get_backend().lower() == 'tkagg'
        from matplotlib import font_manager
        font_manager._load_fontmanager(try_read_cache=False)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        figure = Figure()
        figure.subplots().set_title('Frequency (GHz), −10 dB')
        FigureCanvasAgg(figure).draw()
        assert not events, events
        assert not (folder / 'absent').exists()
    finally:
        active = False
        os.chdir(previous)
'''
        result = subprocess.run(
            [sys.executable, '-B', '-c', code], cwd=PROJECT,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
