import sys
import threading
import types
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from compute_runtime import Execution, LatestWorker
from sparam_core import SParameter, resample_sparams, power_sum_db, icn_calculate


def main():
    source = SParameter(str(Path(__file__).resolve().parent.parent / 'sample_data/demo.s8p'))
    low, high = source.frequencies[[0, -1]] / 1e9
    step = (high-low)/300
    baseline = resample_sparams(source, 55, low, high, step)
    scalars = dict(Ant=.5, Aft=.4, fb=32e9, Tnt=7.5e-12, Tft=7.5e-12,
                   PAM=4, ILn=17, ILf=31.25, fstep=step*1e9)
    expected = None
    for threads, backend in [('1', 'CPU'), ('2', 'CPU'), ('1', 'GPU')]:
        execution = Execution(threads, backend)
        execution.select(source.parameters.size)
        if backend == 'GPU':
            assert execution.gpu is not None, execution.note
        with execution.limits():
            params, freqs = resample_sparams(source, 55, low, high, step, execution)
            np.testing.assert_allclose(params, baseline[0], rtol=1e-10, atol=1e-12)
            sp = types.SimpleNamespace(parameters=params, frequencies=freqs, z0=55)
            result = power_sum_db(sp, 55, [1, 2], [3, 4], [5, 6, 7, 8], True,
                                  low, high, execution=execution)
            noise = icn_calculate(freqs, result['fext_power_lin'], result['next_power_lin'],
                                  scalars, execution=execution)
            if expected is None:
                expected = result, noise
            else:
                for key in ('MDFEXT', 'MDNEXT', 'PSXT'):
                    np.testing.assert_allclose(result[key], expected[0][key], rtol=1e-9, atol=1e-10)
                for key in noise:
                    np.testing.assert_allclose(noise[key], expected[1][key], rtol=1e-9, atol=1e-12)
        print('PASS', threads, backend)
    fallback = Execution('1', 'GPU', 'missing-device')
    fallback.select(100000)
    assert fallback.gpu is None and '回退' in fallback.note
    worker = LatestWorker()
    entered, release = threading.Event(), threading.Event()
    def block():
        entered.set()
        release.wait(5)
    worker.submit('first', 1, block, None)
    assert entered.wait(5)
    worker.submit('compute', 1, lambda: 1, None)
    worker.submit('compute', 2, lambda: 2, None)
    release.set()
    worker.results.get(timeout=5)
    assert worker.results.get(timeout=5)[3] == 2
    worker.close()
    print('PASS fallback and latest-task coalescing')


if __name__ == '__main__':
    main()
