"""基本 GUI 冒烟：python -B tests/_smoke_gui.py（需要桌面会话）。"""

import csv
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from unittest.mock import patch

import numpy as np
import ttkbootstrap as ttk

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
from app import APP_VERSION, SParamPowerSumApp


def run_smoke(directory):
    sample = directory / 'demo.s8p'
    shutil.copyfile(PROJECT / 'sample_data' / sample.name, sample)
    root = ttk.Window(themename='cosmo')
    failures = []
    deadline = time.monotonic() + 30

    def fail(*exc):
        failures.append(''.join(traceback.format_exception(*exc)))
        root.quit()

    root.report_callback_exception = fail
    with patch.object(SParamPowerSumApp, '_default_config_path',
                      return_value=directory / 'default.json'), \
         patch.object(ttk.Messagebox, 'show_error',
                      side_effect=RuntimeError('GUI 错误弹窗')):
        app = SParamPowerSumApp(root)
        assert app.version_author_var.get() == f'v{APP_VERSION}'

        def export():
            assert app.plot_data and app.plot_data['has_fext']
            assert app.plot_data['has_next']
            assert app._last_icn_results, app.status_var.get()
            assert all(np.all(np.isfinite(v)) for v in app._last_icn_results.values())
            count = len(app._batch_rows)
            app._batch_add_data()
            assert len(app._batch_rows) == count + 1
            output = directory / 'results.csv'
            app._batch_export_csv(str(output))
            with output.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            assert rows and 'PSXT (dB)' in rows[0]
            assert np.isfinite(float(rows[0]['PSXT (dB)']))
            assert any('ICN' in key and value and np.isfinite(float(value))
                       for key, value in rows[0].items())
            print('PASS GUI 导入、PowerSum / ICN 计算、CSV 导出读回')
            root.quit()

        def toggle():
            return next(widget for widget in app._batch_btn_bar.winfo_children()
                        if widget.cget('text') == '自动添加数据')

        def select_port(port, callback):
            app.port_vars[port - 1][0].set(True)
            app.on_victim_changed(port)
            root.after(50, lambda: wait_result(callback))

        def check_disabled_again():
            assert len(app._batch_rows) == 1
            export()

        def check_enabled():
            assert len(app._batch_rows) == 1
            assert app._batch_rows[-1]['Port'] == app._collect_batch_row()['Port']
            close = app.batch_window.protocol('WM_DELETE_WINDOW')
            app.batch_window.tk.call(close)
            app._open_batch_export()
            assert app.batch_auto_add_var.get()
            assert len(app._batch_rows) == 1
            toggle().invoke()
            select_port(3, check_disabled_again)

        def check_disabled():
            assert not app._batch_rows
            toggle().invoke()
            assert app.batch_auto_add_var.get()
            assert not app._batch_rows
            select_port(1, check_enabled)

        def check_batch():
            app._open_batch_export()
            root.update_idletasks()
            switch = toggle()
            assert not app.batch_auto_add_var.get()
            assert switch.pack_info()['side'] == 'right'
            assert switch.winfo_x() + switch.winfo_width() <= app._batch_btn_bar.winfo_width()
            for widget in app._batch_btn_bar.winfo_children():
                if widget is not switch:
                    assert widget.winfo_x() + widget.winfo_width() <= switch.winfo_x()
            select_port(3, check_disabled)

        def wait_result(callback=check_batch):
            if time.monotonic() >= deadline:
                raise TimeoutError(f'计算超时: {app.status_var.get()}')
            if (app.plot_data and app._last_icn_results
                    and not app._recalc_job and not app._redraw_job):
                callback()
            else:
                root.after(50, lambda: wait_result(callback))

        def start():
            assert root.winfo_exists()
            app.import_s_params(str(sample))
            assert app.file_loaded and len(app.port_vars) == 8
            app.mode_var.set(app.DIFF_MODE)
            app.arrange_var.set('Type1')
            app.auto_select_var.set(True)
            app.on_auto_select_toggle()
            app.port_vars[0][0].set(True)
            app.on_victim_changed(1)
            app.mark_freq_var.set(str(app.spara_obj.frequencies[-1] / 1e9))
            app.icn_enabled_var.set(True)
            app.auto_calculate()
            root.after(50, wait_result)

        try:
            root.after(0, start)
            root.mainloop()
        finally:
            app._on_main_window_close()
    if failures:
        raise RuntimeError('\n'.join(failures))


def main():
    with tempfile.TemporaryDirectory(prefix='sparam_smoke_') as directory:
        run_smoke(Path(directory))
    print('SMOKE ALL PASS')


if __name__ == '__main__':
    main()
