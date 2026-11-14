import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import ttkbootstrap as ttk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import SParamPowerSumApp


def main():
    root = ttk.Window()
    failures = []
    root.report_callback_exception = lambda *error: failures.append(error)
    with patch.object(SParamPowerSumApp, '_load_last_config'):
        app = SParamPowerSumApp(root)
    def wait():
        deadline = time.monotonic() + 60
        while app._busy or app._recalc_job or app._redraw_job:
            root.update()
            assert time.monotonic() < deadline, (app._busy, app.status_var.get())
            time.sleep(.005)
        root.update()
        assert not failures, failures
    try:
        path = str(ROOT / 'sample_data/demo.s8p')
        app.import_s_params(path)
        app.import_s_params(path)
        wait()
        assert app.file_loaded
        with app._paused():
            app.mode_var.set(app.SE_MODE)
            app.auto_select_var.set(False)
            app.port_vars[0][0].set(True)
            app.port_vars[1][1].set(True)
            app.icn_enabled_var.set(True)
            app.compute_backend_var.set('GPU')
        app.auto_calculate()
        with app._paused():
            app.port_vars[0][0].set(False)
            app.port_vars[2][0].set(True)
            app.cpu_threads_var.set('2')
        app.auto_calculate()
        assert app._collect_batch_row() is None
        wait()
        assert app._result_ports == (3,)
        assert app._last_icn_results is not None, app.status_var.get()
        assert '+ GPU' in app.execution_status_var.get(), app.execution_status_var.get()
        gpu = app.plot_data['PSXT'].copy()
        app.compute_backend_var.set('CPU')
        wait()
        np.testing.assert_allclose(gpu, app.plot_data['PSXT'], rtol=1e-9, atol=1e-10)
        app.gpu_device_var.set('missing')
        app.compute_backend_var.set('GPU')
        wait()
        assert '回退' in app.execution_status_var.get()
        app.port_format_var.set('ADS格式')
        app._on_port_format_changed()
        wait()
        assert app._result_ports == (3,)
        app.import_s_params(path)
        app._on_main_window_close()
        print('PASS asynchronous GUI GPU/CPU, stale results, settings, reparse and close')
    finally:
        if not app._closing:
            app._on_main_window_close()


if __name__ == '__main__':
    main()
