import csv
import io
import sys
import tempfile
import unittest
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import sparam_core as core
from test_icn import SCALARS


class AccuracyTests(unittest.TestCase):
    def parse(self, text):
        with patch('builtins.open', return_value=io.StringIO(text)):
            return core.SParameter('memory.s1p')

    def test_parser(self):
        sp = self.parse('# Hz S RI R 50 ! revision 75\n1 .1 0 ! inline\n2 .2 0\n')
        np.testing.assert_array_equal(sp.frequencies, [1, 2])
        self.assertEqual(sp.z0, 50)
        np.testing.assert_allclose(sp.parameters.ravel(), [.1, .2])
        for text in ('# Hz S RI R 50\n1 .1 0\n2 .2',
                     '# Hz Z RI R 50\n1 .1 0',
                     '# Hz S RI R 50\n1 .1 bad',
                     '# Hz S RI R 50\n1 nan 0',
                     '[Version] 2.0\n', '# Hz S RI R 0\n1 .1 0',
                     '# Hz S RI R 50\n-1 .1 0'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.parse(text)
        for fmt, values in [('RI', '.1 0'), ('MA', '.1 0'), ('DB', '-20 0')]:
            sp = self.parse(f'# Hz S {fmt} R 50\n1 {values}\n')
            np.testing.assert_allclose(sp.parameters.ravel(), [.1])

    def test_grid(self):
        np.testing.assert_array_equal(core.frequency_grid(1e9, 2e9, .3e9),
                                      [1e9, 1.3e9, 1.6e9, 1.9e9])
        for args in [(1, 1, 1), (1, 2, 3), (1, 2, 0), (1, np.inf, 1)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                core.frequency_grid(*args)

    def test_zero_and_direction(self):
        s = np.zeros((4, 4, 4), complex)
        s[0, 2] = s[1, 3] = .02
        s[2, 0] = s[3, 1] = .2
        sp = SimpleNamespace(parameters=s, frequencies=np.arange(1, 5)*1e9, z0=50)
        out = core.power_sum_db(sp, 50, [1, 2], [3, 4], [], True, 1, 4)
        np.testing.assert_allclose(out['MDFEXT'], 20*np.log10(.02))
        np.testing.assert_array_equal(out['PSXT'], out['MDFEXT'])
        self.assertTrue(np.all(out['next_power_lin'] == 0))
        self.assertEqual(core.icn_calculate(out['fn_hz'], out['fext_power_lin'],
                                          out['next_power_lin'], SCALARS)['icn_n'], 0)
        s[0, 2] = s[1, 3] = 1e-6
        out = core.power_sum_db(sp, 50, [1, 2], [3, 4], [], True, 1, 4)
        np.testing.assert_allclose(out['PSXT'], -120)
        s[:] = 0
        out = core.power_sum_db(sp, 50, [1, 2], [3, 4], [], True, 1, 4)
        self.assertTrue(np.all(np.isneginf(out['PSXT'])))
        result = core.icn_calculate(out['fn_hz'], out['fext_power_lin'],
                                    out['next_power_lin'], SCALARS)
        self.assertTrue(all(v == 0 for v in result.values()))

    def test_nonfinite(self):
        with self.assertRaises(ValueError):
            core.safe_db(np.array([np.nan]))
        with self.assertRaises(ValueError):
            core.icn_calculate(np.array([1e9, 2e9]), np.ones(2), np.ones(2),
                               dict(SCALARS, Ant=np.inf))
        sp = SimpleNamespace(parameters=np.ones((2, 2, 2))*.1,
                             frequencies=np.array([1e9, 2e9]), z0=50)
        for expr in ['psum(RAW_FEXT_dB)*0/0', 'abs(psum(RAW_FEXT_dB))/0']:
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                core.power_sum_db(sp, 50, [1], [2], [], False, 1, 2,
                                   {'PSFEXT': expr})

    def test_gui(self):
        import ttkbootstrap as ttk
        import app as app_mod
        root = ttk.Window(themename='cosmo')
        root.withdraw()
        try:
            with patch.object(app_mod.SParamPowerSumApp, '_load_last_config'), \
                 patch.object(app_mod.SParamPowerSumApp, '_load_file_config', return_value=None):
                app = app_mod.SParamPowerSumApp(root)
                def wait():
                    deadline = time.monotonic() + 30
                    while app._busy or app._recalc_job or app._redraw_job:
                        root.update()
                        if time.monotonic() > deadline:
                            self.fail(f'异步任务超时：{app._busy} {app.status_var.get()}')
                        time.sleep(.01)
                original_calculate = app.auto_calculate
                def calculate():
                    original_calculate()
                    wait()
                app.auto_calculate = calculate
                app.import_s_params(str(ROOT / 'sample_data/demo.s8p'))
                wait()
            self.assertTrue(app.file_loaded)
            def select(v=(1, 2), f=(3, 4), n=()):
                with app._paused():
                    app.mode_var.set(app.DIFF_MODE)
                    app.arrange_var.set('Type1')
                    app.auto_select_var.set(False)
                    for p, variables in enumerate(app.port_vars, 1):
                        for var, ports in zip(variables, (v, f, n)):
                            var.set(p in ports)
            select()
            with app._paused():
                app.icn_enabled_var.set(True)
                app.fmin_var.set('1e9')
                app.fmax_var.set('2e9')
                app.fstep_var.set('3e8')
                app.mark_freq_var.set('1.6')
            app.auto_calculate()
            self.assertIsNotNone(app._last_icn_results, app.status_var.get())
            np.testing.assert_allclose(app.plot_data['fn_hz'], [1e9, 1.3e9, 1.6e9, 1.9e9])
            self.assertEqual(app._last_icn_results['icn_n'], 0)
            self.assertTrue(all(f <= 1.6 for f, _ in app._last_mark_peaks.values()))
            self.assertIsNotNone(app._collect_batch_row())
            app._batch_rows = [{'Port': '1,2', '端口名': 'test',
                                '_vals': {'ICN': 1.234567890123456e-6, 'PSXT': -120.123456789}}]
            with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as tmp:
                path = Path(tmp) / 'export.csv'
                app._batch_export_csv(str(path))
                wait()
                with path.open(encoding='utf-8-sig', newline='') as f:
                    row = next(csv.DictReader(f))
                self.assertEqual(float(row['ICN (V)']), 1.234567890123456e-6)
                self.assertEqual(float(row['PSXT (dB)']), -120.123456789)
            app.fmin_var.set('1/0')
            self.assertIsNone(app.plot_data)
            self.assertIsNone(app._collect_batch_row())
            app.auto_calculate()
            self.assertIsNone(app._last_icn_results)
            self.assertEqual(app._last_mark_peaks, {})
            app.fmin_var.set('1e9')
            select(v=(1, 3), f=(5, 6))
            app.auto_calculate()
            self.assertIsNone(app.plot_data)
            select(v=(1, 2), f=(1, 2))
            app.auto_calculate()
            self.assertIsNone(app.plot_data)
            select()
            app.fmax_var.set(str(app.spara_obj.frequencies[-1] + 1e9))
            app.auto_calculate()
            self.assertIn('平坦延拓', app.status_var.get())
            self.assertIsNotNone(app._last_icn_results)
            next(iter(app.icn_scalar_vars.values())).set('1/0')
            with patch.object(app, '_batch_auto_add',
                              side_effect=lambda: app._set_status('cached', 'success')):
                app.auto_calculate()
            self.assertIsNone(app._last_icn_results)
            self.assertIn('ICN/ccICN 计算失败', app.status_var.get())
            root.update_idletasks()
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main(verbosity=2)
