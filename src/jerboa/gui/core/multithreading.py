from typing import Callable

from PySide6 import QtCore as QtC

from jerboa.core.logger import logger
from jerboa.core.multithreading import ThreadPool, ThreadSpawner


class QtThreadPool(ThreadPool):
    def __init__(self, workers: int | None = None):
        super().__init__()
        self._thread_pool = QtC.QThreadPool()
        if workers:
            self._thread_pool.setMaxThreadCount(workers)

    def start(self, job: Callable, *args, **kwargs):
        def worker():
            try:
                job(*args, **kwargs)
            except Exception as e:
                logger.exception(e)
                raise

        self._thread_pool.start(worker)

    def wait(self, timeout: int | None = None) -> bool:
        return self._thread_pool.waitForDone(-1 if timeout is None else timeout)


class QtThreadSpawner(ThreadSpawner):
    class Worker(QtC.QObject):
        finished = QtC.Signal()

        def __init__(
            self,
            job: Callable,
            args: tuple | None = None,
            kwargs: dict | None = None,
        ):
            super().__init__()

            self._job = job
            self._args = args or tuple()
            self._kwargs = kwargs or {}

        def run(self) -> None:
            try:
                self._job(*self._args, **self._kwargs)
                self.finished.emit()
            except Exception as e:
                logger.exception(e)
                raise

    def __init__(self):
        self._threads = dict[QtC.QThread, QtThreadSpawner.Worker]()

    def start(self, job: Callable, *args, **kwargs):
        thread = QtC.QThread()

        def on_finished():
            thread.quit()
            self._threads.pop(thread)

        worker = QtThreadSpawner.Worker(job, args, kwargs)
        worker.moveToThread(thread)
        worker.finished.connect(on_finished)

        thread.started.connect(worker.run)
        thread.start()

        self._threads[thread] = worker

    def wait(self, timeout: int | None = None) -> bool:
        for thread in self._threads:
            thread.wait(-1 if timeout is None else timeout)