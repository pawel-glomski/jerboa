from typing import Callable

from PySide6 import QtCore as QtC

from jerboa.core.multithreading import (
    ThreadPool,
    ThreadSpawner,
    FnTask,
    Future,
    do_job_with_exception_logging,
)


class QtThreadPool(ThreadPool):
    def __init__(self, workers: int | None = None):
        super().__init__()
        self._thread_pool = QtC.QThreadPool()
        if workers:
            self._thread_pool.setMaxThreadCount(workers)

        self._running_tasks = set[FnTask]()

    def start(self, task: FnTask) -> Future:
        self._running_tasks.add(task)

        def job():
            try:
                do_job_with_exception_logging(task.run_if_unresolved, args=[], kwargs={})
            finally:
                self._running_tasks.remove(task)

        self._thread_pool.start(job)
        return task.future


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
                do_job_with_exception_logging(self._job, self._args, self._kwargs)
            finally:
                self.finished.emit()

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
