from typing import Any, Callable, Generic, TypeVar
from abc import ABC, abstractmethod
from threading import Thread, Lock, RLock, Condition
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import dataclasses as dclass
import enum

from .logger import logger

T1 = TypeVar("T1")
T2 = TypeVar("T2")


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
    @dclass.dataclass
    class ConditionInfo:
        different_locks: bool
        waiters: int = 0

    class NotifyAlsoContext:
        def __init__(
            self,
            multi_condition: "MultiCondition",
            external_condition: "Condition | MultiCondition",
            *,
            different_locks: bool,
        ):
            self._multi_condition = multi_condition
            self._external_condition = external_condition
            self._different_locks = different_locks

            if isinstance(external_condition, MultiCondition):
                diff_locks = external_condition._internal_lock != multi_condition._internal_lock
                assert diff_locks == self._different_locks

        def __enter__(self) -> None:
            with self._multi_condition._internal_lock:
                info = self._multi_condition._external_conditions.setdefault(
                    self._external_condition, MultiCondition.ConditionInfo(self._different_locks)
                )
                try:
                    assert info.different_locks == self._different_locks, (
                        f"MultiCondition: The same conditon ({repr(self._external_condition)}), "
                        "added multiple times, has conflicting values for `different_locks`",
                    )
                except AssertionError as exception:
                    info.different_locks = False  # avoid deadlock, assume a shared lock
                    logger.exception(exception)
                    raise

                info.waiters += 1

        def __exit__(self, *exc_args) -> bool:
            with self._multi_condition._internal_lock:
                info = self._multi_condition._external_conditions[self._external_condition]
                info.waiters -= 1
                if info.waiters == 0:
                    self._multi_condition._external_conditions.pop(self._external_condition)

    def __init__(self, lock: "Lock | RLock | RWLock") -> None:
        self._internal_lock = lock
        self._internal_condition = Condition(lock=lock)
        self._external_conditions = dict[Condition, MultiCondition.ConditionInfo]()

    def __hash__(self) -> int:
        return hash(self._internal_condition)

    def __enter__(self):
        return self._internal_lock.__enter__()

    def __exit__(self, *args):
        return self._internal_lock.__exit__(*args)

    def notify_also(
        self,
        condition: "Condition | MultiCondition",
        *,
        different_locks: bool,
    ) -> NotifyAlsoContext:
        return MultiCondition.NotifyAlsoContext(self, condition, different_locks=different_locks)

    def wait(self, timeout: float | None) -> bool:
        """Must be locked"""
        return self._internal_condition.wait(timeout=timeout)

    def wait_for(self, predicate: Callable[[], bool], timeout: float | None) -> bool:
        """Must be locked"""
        return self._internal_condition.wait_for(predicate, timeout=timeout)

    def notify(self, n: int = 1) -> None:
        """Must be locked"""

        self._internal_condition.notify(n)

        # to ensure correct iteration, capture the current state with a list
        for external_condition, info in list(self._external_conditions.items()):
            if info.different_locks:
                with external_condition:
                    external_condition.notify(n)
            else:
                external_condition.notify(n)

    def notify_all(self) -> None:
        """Must be locked"""

        self._internal_condition.notify_all()

        # to ensure correct iteration, capture the current state with a list
        for external_condition, info in list(self._external_conditions.items()):
            if info.different_locks:
                with external_condition:
                    external_condition.notify_all()
            else:
                external_condition.notify_all()

    def notifyAll(self) -> None:
        """Must be locked"""

        self.notify_all()


# ------------------------------------------------------------------------------------------------ #
#                                              Future                                              #
# ------------------------------------------------------------------------------------------------ #


class Future(Generic[T1]):
    class State(enum.Enum):
        PENDING = enum.auto()
        IN_PROGRESS = enum.auto()
        IN_PROGRESS_ABORT = enum.auto()
        FINISHED_CLEAN = enum.auto()
        FINISHED_BY_EXCEPTION = enum.auto()
        FINISHED_BY_ABORT = enum.auto()

    class AbortedError(Exception):
        ...

    def __init__(self, task: "Task[T1]"):
        self._task = task

        self._mutex = Lock()
        self._state = Future.State.PENDING
        self._state_changed = MultiCondition(lock=self._mutex)

        self._result: T1 | None = None
        self._exception: Exception | None = None

    @property
    def state(self) -> State:
        return self._state

    @property
    def state_changed(self) -> MultiCondition:
        return self._state_changed

    def is_in_progress(self) -> bool:
        return self._state in [
            Future.State.IN_PROGRESS,
            Future.State.IN_PROGRESS_ABORT,
        ]

    def is_finished(self, finishing_aborted: bool) -> bool:
        return self._state in [
            Future.State.FINISHED_CLEAN,
            Future.State.FINISHED_BY_EXCEPTION,
            Future.State.FINISHED_BY_ABORT,
        ] or (not finishing_aborted and self._state == Future.State.IN_PROGRESS_ABORT)

    def is_aborted(self) -> bool:
        return self._state in [Future.State.IN_PROGRESS_ABORT, Future.State.FINISHED_BY_ABORT]

    def abort(self) -> bool:
        with self._mutex:
            if self._state == Future.State.PENDING:
                self._set_state__locked(Future.State.IN_PROGRESS_ABORT)
                self._set_state__locked(Future.State.FINISHED_BY_ABORT)
                logger.debug(f"Aborting a pending task ({repr(self._task)})")

            elif not self.is_finished(finishing_aborted=False):
                self._set_state__locked(Future.State.IN_PROGRESS_ABORT)
                logger.debug(f"Aborting a running task ({repr(self._task)})")
        return self.is_aborted()

    def _abort__locked(self) -> bool:
        assert self._mutex.locked()

    def result(self, timeout: float | None = 0) -> T1:
        if self.exception(timeout) is not None:
            raise self._exception

        if self.is_aborted():
            raise Future.AbortedError(f"Task ({repr(self._task)}) aborted")

        return self._result

    def exception(self, timeout: float | None = 0) -> Exception | None:
        # exception can be set only on non-aborted tasks
        if (
            timeout is not None and timeout <= 0 and not self.is_finished(finishing_aborted=False)
        ) or (
            (timeout is None or timeout > 0) and self.wait(finishing_aborted=False, timeout=timeout)
        ):
            raise TimeoutError(f"Task ({repr(self._task)}) not resolved in time")
        return self._exception

    def wait(self, finishing_aborted: bool, timeout: float | None = None) -> bool:
        with self._state_changed:
            return self._state_changed.wait_for(
                lambda: self.is_finished(finishing_aborted=finishing_aborted),
                timeout=timeout,
            )

    def _set_exception__locked(self, exception: Exception, raise_now: bool) -> None:
        assert self._mutex.locked()

        self._exception = exception
        self._set_state__locked(Future.State.FINISHED_BY_EXCEPTION)
        if raise_now:
            raise exception

    def _set_state__locked(self, new_state: "Future.State") -> None:
        assert self._mutex.locked()

        if (
            (
                self._state == Future.State.PENDING
                and new_state not in [Future.State.IN_PROGRESS, Future.State.IN_PROGRESS_ABORT]
            )
            or (
                self._state == Future.State.IN_PROGRESS
                and new_state
                not in [
                    Future.State.IN_PROGRESS_ABORT,
                    Future.State.FINISHED_CLEAN,
                    Future.State.FINISHED_BY_ABORT,
                    Future.State.FINISHED_BY_EXCEPTION,
                ]
            )
            or self.is_finished(finishing_aborted=True)
        ):
            logger.error(
                f"Invalid task ({repr(self._task)}) state transition: {self._state} -> {new_state} "
                "- this should never happen, please report this error"
            )

        self._state = new_state
        self._state_changed.notify_all()


# ------------------------------------------------------------------------------------------------ #
#                                               Task                                               #
# ------------------------------------------------------------------------------------------------ #


@dclass.dataclass(frozen=True)
class Task(Exception, Generic[T1]):
    class UnexpectedStateError(Exception):
        def __init__(self, expected_state: str, observed_state: Future.State) -> None:
            super().__init__(f"{expected_state}, state={observed_state}")

    class Abort(Exception):
        def __init__(self):
            super().__init__("`Task.Abort` not caught, please report this error")

    class FinishContext(Generic[T2]):
        def __init__(self, future: Future[T2]) -> None:
            self._future = future
            self._active = False

        def __enter__(self) -> "Task.FinishContext[T2]":
            self._future._mutex.acquire()
            try:
                assert not self._active

                if self._future.is_aborted():
                    raise Task.Abort()
                if not self._future.is_in_progress():
                    raise Task.UnexpectedStateError(
                        f"Task ({repr(self._future._task)}) not in-progress", self._future.state
                    )
            except:
                self._future._mutex.release()
                raise

            self._active = True
            return self

        def __exit__(self, exc_type: type[Exception] | None, exc: Exception, traceback) -> bool:
            try:
                if self._future.is_finished(finishing_aborted=True):
                    raise RuntimeError(
                        "Task already finished. Only Task.Executor and Task.FinishContext "
                        "can finish tasks"
                    )

                if exc_type is None:
                    self._future._set_state__locked(Future.State.FINISHED_CLEAN)
                assert self._active

                return False
            finally:
                self._active = False
                self._future._mutex.__exit__(exc_type, exc, traceback)

        def set_result(self, result: T2) -> None:
            assert self._active
            assert self._future._mutex.locked()
            assert self._future.is_in_progress()
            self._future._result = result

        def abort(self) -> None:
            assert self._active
            assert self._future._mutex.locked()
            assert self._future.is_in_progress()

            raise Task.Abort()

    class Executor(Generic[T2]):
        def __init__(self, future: Future[T2]) -> None:
            self._future = future
            self._finish_context = Task.FinishContext[T2](self._future)
            self._active = False

        def __enter__(self) -> "Task.Executor[T2]":
            if not self._future.is_in_progress():
                raise Task.UnexpectedStateError(
                    f"Task ({repr(self._future._task)}) not in-progress", self._future.state
                )

            self._active = True
            return self

        def __exit__(self, exc_type: type[Exception] | None, exc: Exception, traceback) -> bool:
            exception_handled = False

            with self._future._mutex:
                if (
                    self._future.is_finished(finishing_aborted=True)
                    and self._future.state != Future.State.FINISHED_CLEAN
                ):
                    raise RuntimeError(
                        "Task already finished. Only Task.Executor and Task.FinishContext "
                        "can finish tasks"
                    )

                if not self._future.is_finished(finishing_aborted=True):
                    if exc_type == Task.Abort:
                        self._future._set_state__locked(Future.State.FINISHED_BY_ABORT)
                        exception_handled = True
                    elif exc_type is not None:
                        self._future._set_exception__locked(exc, raise_now=False)
                        exception_handled = False
                    else:
                        self._future._set_exception__locked(
                            Task.UnexpectedStateError(
                                f"Task ({repr(self._future._task)}) finished running but did not "
                                "mark itself as finished",
                                self._future.state,
                            ).with_traceback(traceback),
                            raise_now=True,
                        )

            assert self._active
            return exception_handled

        @property
        def is_aborted(self) -> bool:
            assert self._active

            return self._future.is_aborted()

        def abort(self) -> None:
            assert self._active

            if self._finish_context._active:
                self._finish_context.abort()
            else:
                self._future.abort()
            raise Task.Abort()

        def finish(self, result: T2 = None) -> None:
            assert self._active

            with self._finish_context:
                self._finish_context.set_result(result)

        def finish_with(self, fn: Callable[[], T2], /, *args, **kwargs) -> None:
            assert self._active

            with self._finish_context:
                self._finish_context.set_result(fn(*args, **kwargs))

        def finish_context(self) -> "Task.FinishContext[T2]":
            assert self._active

            return self._finish_context

        def abort_aware_wait_for_future(
            self,
            future: Future,
            finishing_aborted: bool = False,
            timeout: float | None = None,
        ) -> bool:
            """This function locks this future's lock on its own"""
            assert self._active
            assert future is not self._future

            return self.abort_aware_wait(
                predicate=lambda: future.is_finished(finishing_aborted=finishing_aborted),
                condition=future.state_changed,
                different_locks=True,  # every future has a unique lock
                timeout=timeout,
            )

        def abort_aware_wait(
            self,
            predicate: Callable[[], bool],
            condition: Condition,
            *,
            different_locks: bool,
            timeout: float | None = None,
        ) -> bool:
            """This function locks this future's lock on its own"""
            assert self._active

            with self._future.state_changed.notify_also(condition, different_locks=different_locks):
                with condition:
                    return condition.wait_for(
                        lambda: (predicate() or self._future.is_finished(finishing_aborted=False)),
                        timeout=timeout,
                    )

    id: Any = dclass.field(default=None, kw_only=True)
    future: Future[T1] = dclass.field(init=False, compare=False, repr=False)
    already_finished: dclass.InitVar[bool] = dclass.field(default=False, kw_only=True)

    def __post_init__(self, already_finished: bool):
        super().__setattr__("future", Future(task=self))
        if already_finished:
            self.finish_without_running()

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: Any) -> bool:
        return other is self

    def __del__(self):
        with self.future._mutex:
            if not self.future.is_finished(finishing_aborted=True):
                if not self.future.is_in_progress():
                    self.future._set_state__locked(Future.State.IN_PROGRESS)
                self.future._set_exception__locked(
                    Task.UnexpectedStateError(
                        f"Task ({repr(self)}) never finished", self.future.state
                    ),
                    raise_now=True,
                )

    def finish_without_running(self) -> None:
        with self.future._mutex:
            if self.future.state == Future.State.PENDING:
                self.future._set_state__locked(Future.State.IN_PROGRESS)
                self.future._set_state__locked(Future.State.FINISHED_CLEAN)
            else:
                exception = Task.UnexpectedStateError("Should be pending", self.future.state)
                if not self.future.is_finished(finishing_aborted=True):
                    self.future._set_exception__locked(exception, raise_now=False)
                raise exception

    def execute(self) -> "Task.Executor":
        return Task.Executor(self.future)

    def execute_and_finish_with(self, fn: Callable, /, *args, **kwargs) -> None:
        with self.execute() as executor:
            executor.finish_with(fn, *args, **kwargs)

    def run_if_unresolved(self) -> None:
        can_run = False
        with self.future._mutex:
            if not self.future.is_in_progress():
                self.future._set_state__locked(Future.State.IN_PROGRESS)
                can_run = True
        if can_run:
            logger.debug(f"Running a task: {repr(self)}")
            self.run_impl()
            logger.debug(f"Finished a task: {repr(self)}")

    def run_impl(self) -> None:
        """Task implementation

        By default this method just raises `self` and the actual implementation is handled by an
        `except TaskType` block.

        This method can be overridden in derived classes to implement custom behavior.

        Raises:
            self: self
        """
        raise self

    def invalidates(self, task: "Task") -> bool:
        return False


@dclass.dataclass(frozen=True)
class FnTask(Task[T1]):
    fn: Callable[[Task.Executor[T1]], T1]

    def run_impl(self) -> None:
        # finish early if aborted
        with self.future._mutex:
            if self.future.is_aborted():
                self.future._set_state__locked(Future.State.FINISHED_BY_ABORT)

        with self.execute() as executor:
            self.fn(executor)


# ------------------------------------------------------------------------------------------------ #
#                                             TaskQueue                                            #
# ------------------------------------------------------------------------------------------------ #


class TaskQueue:
    def __init__(self, mutex: Lock = None) -> None:
        self._mutex = mutex or Lock()
        self._tasks = deque[Task]()
        self._task_added = MultiCondition(lock=self._mutex)

        self._current_task = Task(already_finished=True, id="DUMMY_INIT_TASK")

    @property
    def mutex(self) -> Lock:
        return self._mutex

    @property
    def task_added(self) -> MultiCondition:
        return self._task_added

    def is_empty(self) -> bool:
        return len(self._tasks) == 0

    def clear(self, abort_current_task: bool = True) -> None:
        with self.mutex:
            self.clear__locked(abort_current_task)

    def clear__locked(self, abort_current_task: bool) -> None:
        assert self.mutex.locked()

        if abort_current_task:
            self._current_task.future.abort()
        for task in self._tasks:
            task.future.abort()
        self._tasks.clear()

    def run_all(self, timeout: float | None = 0) -> None:
        assert self._current_task.future.is_finished(
            finishing_aborted=True
        ), f"{self._current_task} should be already finished"

        if timeout is None or timeout > 0:
            with self.task_added:
                self.task_added.wait_for(lambda: not self.is_empty(), timeout=timeout)

        while not self.is_empty():
            with self.mutex:
                self._current_task = self._tasks.popleft()
            self._current_task.run_if_unresolved()  # this should usually raise a task exception

    def add_task(self, task: Task, apply_invalidation_rules: bool = False) -> None:
        with self.mutex:
            self.add_task__locked(task, apply_invalidation_rules)

    def add_task__locked(self, task: Task, apply_invalidation_rules: bool = False) -> None:
        assert self.mutex.locked()

        if apply_invalidation_rules:
            if task.invalidates(self._current_task):
                self._current_task.future.abort()

            valid_tasks = deque[Task]()
            for other_task in self._tasks:
                if task.invalidates(other_task):
                    other_task.future.abort()
                else:
                    valid_tasks.append(other_task)
            self._tasks = valid_tasks

        self._tasks.append(task)
        self.task_added.notify_all()


# ------------------------------------------------------------------------------------------------ #
#                            Interfaces of ThreadPool and ThreadSpawner                            #
# ------------------------------------------------------------------------------------------------ #


class ThreadPool(ABC):
    @abstractmethod
    def start(self, task: FnTask) -> Future:
        raise NotImplementedError()


class ThreadSpawner(ABC):
    @abstractmethod
    def start(self, job: Callable, /, *args, **kwargs) -> None:
        raise NotImplementedError()


# ------------------------------------------------------------------------------------------------ #
#                                           PyThreadPool                                           #
# ------------------------------------------------------------------------------------------------ #


class PyThreadPool(ThreadPool):
    def __init__(self, workers: int | None = None):
        super().__init__()
        self._thread_pool = ThreadPoolExecutor(workers)
        self._running_tasks = set[FnTask]()

    def start(self, task: FnTask) -> Future:
        self._running_tasks.add(task)

        def job():
            try:
                do_job_with_exception_logging(task.run_if_unresolved, args=[], kwargs={})
            finally:
                self._running_tasks.remove(task)

        self._thread_pool.submit(job)
        return task.future
        # try:
        #     future = self._thread_pool.submit(do_job_with_exception_logging, job, args, kwargs)
        #     future.result(timeout=0)
        # except futures.TimeoutErrorTPE:
        #     pass


# ------------------------------------------------------------------------------------------------ #
#                                          PyThreadSpawner                                         #
# ------------------------------------------------------------------------------------------------ #


class PyThreadSpawner(ThreadSpawner):
    def start(self, job: Callable, /, *args, **kwargs):
        Thread(target=do_job_with_exception_logging, args=[job, args, kwargs], daemon=True).start()


def do_job_with_exception_logging(job: Callable, args: tuple = tuple(), kwargs: dict = {}) -> None:
    try:
        return job(*args, **kwargs)
    except Exception as e:
        logger.exception(e)
        raise
