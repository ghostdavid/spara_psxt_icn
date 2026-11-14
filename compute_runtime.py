import os
import queue
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor
from contextlib import contextmanager

import numpy as np
from scipy.interpolate import PchipInterpolator
from threadpoolctl import threadpool_limits


class LatestWorker:
    def __init__(self):
        self._condition = threading.Condition()
        self._pending = {}
        self._closed = False
        self.results = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name='sparam-worker')
        self._thread.start()

    def submit(self, channel, token, work, done):
        with self._condition:
            self._pending[channel] = (token, work, done)
            self._condition.notify()

    def discard(self, channel):
        with self._condition:
            self._pending.pop(channel, None)

    def close(self):
        with self._condition:
            self._closed = True
            self._pending.clear()
            self._condition.notify()

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._pending)
                if self._closed:
                    return
                channel = next(iter(self._pending))
                token, work, done = self._pending.pop(channel)
            try:
                value, error = work(), None
            except Exception as exc:
                value, error = None, exc
            self.results.put((channel, token, done, value, error))


def thread_count(value):
    available = os.cpu_count() or 1
    if str(value) in ('自动', 'auto', '0'):
        return max(1, available - 1)
    count = int(value)
    if not 1 <= count <= available:
        raise ValueError(f'CPU 线程数必须为 1–{available} 或自动')
    return count


class Execution:
    def __init__(self, threads='自动', backend='自动', device='', cancelled=None):
        self.threads = thread_count(threads)
        if backend not in ('自动', 'CPU', 'GPU'):
            raise ValueError('计算后端必须为 自动、CPU 或 GPU')
        self.backend = backend
        self.device = device
        self.cancelled = cancelled or threading.Event()
        self.gpu = None
        self.note = f'CPU {self.threads} 线程'

    def check(self):
        if self.cancelled.is_set():
            raise CancelledError()

    def select(self, size):
        self.check()
        if self.backend == 'CPU' or (self.backend == '自动' and size < 32768):
            return
        try:
            from gpu_runtime import OpenCLBackend
            self.gpu = OpenCLBackend(self.device)
            self.note += f' + GPU {self.gpu.name}（混合计算）'
        except Exception as exc:
            self.note += f'；GPU 不可用，CPU 回退：{exc}'

    @contextmanager
    def limits(self):
        with threadpool_limits(limits=self.threads):
            yield

    def interpolate(self, x, values, target):
        self.check()
        if self.gpu is not None:
            return self.gpu.interpolate(x, values, target, self.check)
        flat = values.reshape(-1, len(x))
        out = np.empty((len(flat), len(target)), dtype=np.complex128)
        width = max(1, min(32, 32 * 1024 * 1024 // max(1, 64 * (len(x) + len(target)))))

        def chunk(start):
            self.check()
            stop = min(start + width, len(flat))
            for component in ('real', 'imag'):
                source = getattr(flat[start:stop], component)
                result = PchipInterpolator(x, source, axis=1)(np.clip(target, x[0], x[-1]))
                getattr(out[start:stop], component)[:] = result
            self.check()

        with threadpool_limits(limits=1):
            if self.threads == 1:
                for start in range(0, len(flat), width):
                    chunk(start)
            else:
                with ThreadPoolExecutor(max_workers=self.threads,
                                        thread_name_prefix='sparam-numeric') as pool:
                    starts = range(0, len(flat), width)
                    for offset in range(0, len(starts), self.threads):
                        for _ in pool.map(chunk, starts[offset:offset + self.threads]):
                            pass
        return out.reshape(values.shape[:2] + (len(target),))

    def evaluate(self, expression, env):
        from sparam_core import evaluate_expr
        self.check()
        if self.gpu is None:
            return evaluate_expr(expression, env)
        return self.gpu.evaluate(expression, env)
