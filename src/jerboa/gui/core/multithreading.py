# Jerboa - AI-powered media player
# Copyright (C) 2023 Paweł Głomski

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


from typing import Callable

from qtpy import QtCore as QtC

from jerboa.core.multithreading import (
    ThreadPool,
    ThreadSpawner,
    FnTask,
    do_job_with_exception_logging,
)


class QtThreadPool(ThreadPool):
    def __init__(self, workers: int | None = None):
        super().__init__()
        self._thread_pool = QtC.QThreadPool()
        if workers:
            self._thread_pool.setMaxThreadCount(workers)

        self._running_tasks = dict[int, FnTask]()

    def start(self, task: FnTask) -> FnTask.Future:
        task_id = id(task)
        self._running_tasks[task_id] = task

        def job():
            try:
                do_job_with_exception_logging(task.run_pending, args=[], kwargs={})
            finally:
                self._running_tasks.pop(task_id)

        self._thread_pool.start(job)
        return task.future


from jerboa.log import logger


class QtThreadSpawner(ThreadSpawner):
    class FinishedSignalWrapper(QtC.QObject):
        signal = QtC.Signal(int)

    class Worker(QtC.QObject):
        def __init__(self, job: Callable):
            super().__init__()
            self._job = job

        def run(self) -> None:
            self._job()

    def __init__(self):
        self._threads = dict[int, tuple[QtC.QThread, QtThreadSpawner.Worker]]()
        self._finished_signal_wrapper = QtThreadSpawner.FinishedSignalWrapper()
        self._finished_signal_wrapper.signal.connect(self._on_finished)

        self._counter = 0

    def _on_finished(self, thread_id: int):
        thread = self._threads[thread_id][0]
        thread.quit()

    def start(self, job: Callable, *args, **kwargs):
        thread = QtC.QThread()
        thread_id = self._counter
        self._counter += 1

        def _qt_job():
            try:
                do_job_with_exception_logging(job, args, kwargs)
            finally:
                self._finished_signal_wrapper.signal.emit(thread_id)

        worker = QtThreadSpawner.Worker(_qt_job)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        thread.finished.connect(lambda: self._threads.pop(thread_id))
        thread.start()

        self._threads[thread_id] = (thread, worker)
