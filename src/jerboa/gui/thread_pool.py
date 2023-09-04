from typing import Callable
from jerboa.thread_pool import ThreadPoolBase

from PyQt5.QtCore import QThreadPool, QRunnable


class ThreadPool(ThreadPoolBase):
    def __init__(self, workers=None) -> None:
        super().__init__(workers)
        x = QRunnable()
        # x.
        self._thread_pool = QThreadPool()
        self._thread_pool.setMaxThreadCount(workers or 0)

    def start(self, fn: Callable[[], None]):
        self._thread_pool.start(fn)

    def wait(self, timeout: int = -1) -> None:
        self._thread_pool.waitForDone(timeout)
