from typing import Callable
from abc import ABC, abstractmethod
from threading import Thread, Lock, RLock, Condition
from concurrent import futures
from collections import deque
from dataclasses import dataclass, field
import enum

from .logger import logger


# ------------------------------------------------------------------------------------------------ #
#                                               Task                                               #
# ------------------------------------------------------------------------------------------------ #


@dataclass(frozen=True)
class Task(Exception):
    class State(enum.Enum):
        UNRESOLVED = enum.auto()
        IN_PROGRESS = enum.auto()
        COMPLETED = enum.auto()
        CANCELLED = enum.auto()

    class NeverResolvedError(Exception):
        ...

    class Future:
        def __init__(self):
            self._mutex = Lock()
            self._is_resolved = Condition(lock=self._mutex)
            self._state = Task.State.UNRESOLVED

        @property
        def is_unresolved(self) -> bool:
            return self._state == Task.State.UNRESOLVED

        @property
        def is_resolved(self) -> bool:
            return self.is_completed or self.is_cancelled

        @property
        def is_cancelled(self) -> bool:
            return self._state == Task.State.CANCELLED

        @property
        def is_in_progress(self) -> bool:
            return self._state == Task.State.IN_PROGRESS

        @property
        def is_completed(self) -> bool:
            return self._state == Task.State.COMPLETED

        def wait_done(self, timeout: float | None = None) -> bool:
            with self._mutex:
                if not self._is_resolved.wait_for(lambda: self.is_resolved, timeout=timeout):
                    raise TimeoutError("Task not resolved in time")
                return self.is_completed

        def _set_state__locked(self, new_state: "Task.State") -> None:
            assert self._mutex.locked()
            assert (
                self._state == Task.State.UNRESOLVED and new_state != Task.State.UNRESOLVED
            ) or (self._state == Task.State.IN_PROGRESS and new_state == Task.State.COMPLETED)

            self._state = new_state
            if self.is_resolved:
                self._is_resolved.notify_all()

    future: Future = field(default_factory=Future, init=False, compare=False, repr=False)

    def __del__(self):
        with self.future._mutex:
            if self.future.is_unresolved:
                self.future._set_state__locked(Task.State.CANCELLED)
                raise Task.NeverResolvedError(f"{type(self).__name__} never resolved")
            if self.future.is_in_progress:
                self.future._set_state__locked(Task.State.COMPLETED)
                raise Task.NeverResolvedError(f"{type(self).__name__} never fully completed")

    def run_impl(self) -> None:
        """Task implementation

        By default this method just raises `self` and the actual implementation is handled by an
        `except TaskType` block.

        This method can be overridden in derived classes to implement custom behavior.

        Raises:
            self: self
        """
        raise self

    def run(self) -> None:
        can_run = False
        with self.future._mutex:
            if self.future._state == Task.State.UNRESOLVED:
                self.future._set_state__locked(Task.State.IN_PROGRESS)
                can_run = True
        if can_run:
            self.run_impl()

    def complete(self) -> None:
        with self.future._mutex:
            self.future._set_state__locked(Task.State.COMPLETED)

    def complete_after(self, fn: Callable, /, *args, **kwargs) -> None:
        try:
            fn(*args, **kwargs)
        finally:
            with self.future._mutex:
                self.future._set_state__locked(Task.State.COMPLETED)

    def cancel(self) -> None:
        with self.future._mutex:
            if self.future.is_unresolved:
                self.future._set_state__locked(Task.State.CANCELLED)


class FnTask(Task):
    def __init__(self, fn: Callable, /, *args, **kwargs) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run_impl(self) -> None:
        self.complete_after(self._fn, *self._args, **self._kwargs)


# ------------------------------------------------------------------------------------------------ #
#                                             TaskQueue                                            #
# ------------------------------------------------------------------------------------------------ #


class TaskQueue:
    def __init__(self, mutex: Lock = None) -> None:
        self._mutex = mutex or Lock()
        self._tasks = deque[Task]()
        self._task_added = Condition(self._mutex)
        self._task_added_callbacks = set[Callable[[], None]]()

        self.add_on_task_added_callback(self.task_added.notify)

    @property
    def mutex(self) -> Lock:
        return self._mutex

    @property
    def task_added(self) -> Condition:
        return self._task_added

    def is_empty(self) -> bool:
        return len(self._tasks) == 0

    def clear(self) -> None:
        with self.mutex:
            self.clear__locked()

    def clear__locked(self) -> None:
        assert self.mutex.locked()

        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    def run_all(self, wait_when_empty: bool = False, timeout: float | None = None) -> int:
        if wait_when_empty:
            with self._mutex:
                self.task_added.wait_for(lambda: not self.is_empty(), timeout=timeout)

        tasks_run = 0
        while True:
            with self._mutex:
                if self.is_empty():
                    break
                tasks_run += 1
                task = self._tasks.popleft()
            task.run()  # this should usually raise a task exception
        return tasks_run

    def add_task(self, task: Task) -> None:
        with self.mutex:
            self.add_task__locked(task)

    def add_task__locked(self, task: Task) -> None:
        assert self.mutex.locked()

        self._tasks.append(task)
        self.task_added.notify_all()
        for callback in self._task_added_callbacks:
            callback()

    def add_on_task_added_callback(self, callback: Callable[[], None]) -> None:
        assert callback not in self._task_added_callbacks
        self._task_added_callbacks.add(callback)


# ------------------------------------------------------------------------------------------------ #
#                            Interfaces of ThreadPool and ThreadSpawner                            #
# ------------------------------------------------------------------------------------------------ #


class ThreadPool(ABC):
    @abstractmethod
    def start(self, job: Callable, /, *args, **kwargs) -> Task.Future:
        raise NotImplementedError()

    @abstractmethod
    def wait(self, timeout: int | None = None) -> None:
        raise NotImplementedError()


class ThreadSpawner(ABC):
    @abstractmethod
    def start(self, job: Callable, /, *args, **kwargs) -> None:
        raise NotImplementedError()

    @abstractmethod
    def wait(self, timeout: int | None = None) -> bool:
        raise NotImplementedError()


# ------------------------------------------------------------------------------------------------ #
#                                           PyThreadPool                                           #
# ------------------------------------------------------------------------------------------------ #


class PyThreadPool(ThreadPool):
    def __init__(self, workers: int | None = None):
        super().__init__()
        self._workers = workers
        self._thread_pool = futures.ThreadPoolExecutor(workers)

    def start(self, job: Callable, /, *args, **kwargs) -> futures.Future:
        return self._thread_pool.submit(do_job_with_exception_logging, job, args, kwargs)

        # try:
        #     future = self._thread_pool.submit(do_job_with_exception_logging, job, args, kwargs)
        #     future.result(timeout=0)
        # except futures.TimeoutErrorTPE:
        #     pass

    def wait(self, timeout: int | None = None) -> bool:
        self._thread_pool.shutdown(wait=(timeout or 0) > 0)
        self._thread_pool = futures.ThreadPoolExecutor(self._workers)


# ------------------------------------------------------------------------------------------------ #
#                                          PyThreadSpawner                                         #
# ------------------------------------------------------------------------------------------------ #


class PyThreadSpawner(ThreadSpawner):
    def __init__(self):
        super().__init__()
        self._threads = set[Thread]()
        self._mutex = Lock()

    def start(self, job: Callable, /, *args, **kwargs):
        thread = Thread(target=do_job_with_exception_logging, args=[job, args, kwargs])
        thread.start()
        with self._mutex:
            self._threads.add(thread)

    def wait(self, timeout: int | None = None) -> bool:
        with self._mutex:
            threads = list(self._threads)

        for thread in threads:
            thread.join(timeout)
        result = all(thread.is_alive() for thread in threads)

        with self._mutex:
            self._threads = {thread for thread in self._threads if thread.is_alive()}
        return result


def do_job_with_exception_logging(job: Callable, args: tuple, kwargs: dict) -> None:
    try:
        return job(*args, **kwargs)
    except Exception as e:
        logger.exception(e)
        raise


# ------------------------------------------------------------------------------------------------ #
#         RWLock from https://gist.github.com/tylerneylon/a7ff6017b7a1f9a506cf75aa23eacfd6         #
# ------------------------------------------------------------------------------------------------ #


class RWLockView:
    def __init__(self, acquire_fn: Callable, release_fn: Callable) -> None:
        self._acquire_fn = acquire_fn
        self._release_fn = release_fn

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        return self.release()

    def acquire(self, *args, **kwargs):
        return self._acquire_fn(*args, **kwargs)

    def release(self):
        return self._release_fn()


class RWLock:
    def __init__(self):
        self._w_lock = Lock()
        self._num_r_lock = Lock()
        self._num_r = 0

    def as_reader(self) -> RWLockView:
        return RWLockView(acquire_fn=self._reader_acquire, release_fn=self._reader_release)

    def _reader_acquire(self, *args, **kwargs):
        acquired = False
        if self._num_r_lock.acquire(*args, **kwargs):
            if self._num_r > 0 or self._w_lock.acquire(*args, **kwargs):
                acquired = True
                self._num_r += 1
            self._num_r_lock.release()
        return acquired

    def _reader_release(self) -> None:
        assert self._num_r > 0
        with self._num_r_lock:
            self._num_r -= 1
            if self._num_r == 0:
                self._w_lock.release()

    def as_writer(self) -> RWLockView:
        return RWLockView(acquire_fn=self._writer_acquire, release_fn=self._writer_release)

    def _writer_acquire(self, *args, **kwargs) -> bool:
        return self._w_lock.acquire(*args, **kwargs)

    def _writer_release(self) -> None:
        self._w_lock.release()


# ------------------------------------------------------------------------------------------------ #
#                                          MultiCondition                                          #
# ------------------------------------------------------------------------------------------------ #


class MultiCondition:
    def __init__(self, lock: "Lock | RLock | RWLock") -> None:
        self._conditions = set[Condition]()
        self._lock = lock

    def __enter__(self):
        return self._lock.__enter__()

    def __exit__(self, *args):
        return self._lock.__exit__(*args)

    def wait_with(
        self,
        condition: Condition,
        condition_predicate: Callable[[], bool],
        interrupt_predicate: Callable[[], bool] = lambda: False,
        timeout: float | None = None,
    ) -> bool:
        """Both this instance and `condition` must be locked"""

        if condition_predicate() or interrupt_predicate():
            return True

        def predicate__safe():
            self._lock.acquire()

            # in case of any exceptions, we want the lock to be acquired,
            # so we do not catch anything here
            if condition_predicate() or interrupt_predicate():
                return True  # returns with the lock acquired on True

            self._lock.release()  # releases the lock on False
            return False

        self._conditions.add(condition)
        try:
            self._lock.release()
            if condition.wait_for(predicate=predicate__safe, timeout=timeout):
                # `self._lock` is already acquired
                return condition_predicate()

            # timed out
            self._lock.acquire()
            return False  # treat it as if the wait has been interrupted

        finally:
            self._conditions.remove(condition)

    def notify(self, n: int = 1) -> None:
        """Must be locked"""

        # to ensure correct iteration, capture the current state with a list
        for interrupt_condition in list(self._conditions):
            with interrupt_condition:
                interrupt_condition.notify(n)

    def notify_all(self) -> None:
        """Must be locked"""

        # to ensure correct iteration, capture the current state with a list
        for interrupt_condition in list(self._conditions):
            with interrupt_condition:
                interrupt_condition.notify_all()

    def notifyAll(self) -> None:
        """Must be locked"""

        self.notify_all()
