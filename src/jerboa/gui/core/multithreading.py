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

from PySide6 import QtCore as QtC

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


class QtThreadSpawner(ThreadSpawner):
    class Worker(QtC.QObject):
        finished = QtC.Signal()

        def __init__(self, job: Callable, args: tuple, kwargs: dict):
            super().__init__()

            self._job = job
            self._args = args
            self._kwargs = kwargs

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
