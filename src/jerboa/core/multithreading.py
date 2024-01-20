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


from typing import Any, Callable, Generic, TypeVar
from abc import ABC, abstractmethod
from threading import Thread, Lock, Condition
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import dataclasses as dclass
import enum

from jerboa.log import logger

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
#                                               Event                                              #
# ------------------------------------------------------------------------------------------------ #


class Event:
    class State(enum.Enum):
        PENDING = enum.auto()
        EMITTED = enum.auto()
        ABORTED = enum.auto()

    def __init__(self):
        self._cond = Condition()
        self._state = Event.State.PENDING

    def __del__(self):
        assert self._state != Event.State.PENDING

    @property
    def is_pending(self) -> bool:
        return self._state == Event.State.PENDING

    @property
    def is_emitted(self) -> bool:
        return self._state == Event.State.EMITTED

    @property
    def is_aborted(self) -> bool:
        return self._state == Event.State.ABORTED

    def emit(self) -> bool:
        assert not self.is_emitted

        with self._cond:
            if self.is_pending:
                self._state = Event.State.EMITTED
            self._cond.notify_all()
        return self.is_emitted

    def abort(self) -> None:
        with self._cond:
            if self.is_pending:
                self._state = Event.State.ABORTED
                self._cond.notify_all()

    def wait(self, timeout: float | None = None) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: not self.is_pending, timeout=timeout)


# ------------------------------------------------------------------------------------------------ #
#                                         PredicateEmitter                                         #
# ------------------------------------------------------------------------------------------------ #


class PredicateEmitter:
    @dclass.dataclass(frozen=True)
    class Case:
        event: Event = dclass.field(kw_only=True)
        predicate_kwargs: dict[str, Any] = dclass.field(kw_only=True)
        aborts: bool = dclass.field(kw_only=True)

        def finish(self) -> None:
            if self.aborts:
                self.event.abort()
            else:
                self.event.emit()

    def __init__(self, predicate: Callable[..., bool]) -> None:
        self._predicate = predicate
        self._cases = list[PredicateEmitter.Case]()

    def create_emit_event__locked(self, **predicate_kwargs) -> Event:
        return self._add_case__locked(
            PredicateEmitter.Case(
                event=Event(),
                predicate_kwargs=predicate_kwargs,
                aborts=False,
            )
        )

    def add_event_to_abort__locked(self, event: Event, **predicate_kwargs) -> None:
        self._add_case__locked(
            PredicateEmitter.Case(
                event=event,
                predicate_kwargs=predicate_kwargs,
                aborts=True,
            )
        )

    def _add_case__locked(self, case: "PredicateEmitter.Case") -> Event:
        self._remove_expiried_cases__locked()

        if case.event.is_pending:
            if self._predicate(**case.predicate_kwargs):
                case.finish()
            else:
                self._cases.append(case)
        return case.event

    def _remove_expiried_cases__locked(self) -> None:
        cases_left = []
        for case in self._cases:
            assert not case.event.is_emitted or case.aborts

            if case.event.is_pending:
                cases_left.append(case)
        self._cases = cases_left

    def evaluate_and_emit__locked(self) -> None:
        cases_left = []
        for case in self._cases:
            if case.event.is_pending:
                if self._predicate(**case.predicate_kwargs):
                    case.finish()
                else:
                    cases_left.append(case)
        self._cases = cases_left


# ------------------------------------------------------------------------------------------------ #
#                                               Task                                               #
# ------------------------------------------------------------------------------------------------ #


@dclass.dataclass(frozen=True)
class Task(Exception, Generic[T1]):
    class Abort(Exception):
        def __init__(self):
            super().__init__("`Task.Abort` not caught, please report this error")

    # ------------------------------------------- Stage ------------------------------------------ #

    class Stage(enum.Enum):
        class InvalidTransitionError(Exception):
            ...

        PENDING = enum.auto()
        IN_PROGRESS = enum.auto()
        IN_PROGRESS_ABORT = enum.auto()
        FINISHED_CLEAN = enum.auto()
        FINISHED_BY_ABORT = enum.auto()
        FINISHED_BY_EXCEPTION = enum.auto()

        def __bool__(self) -> bool:
            return self == Task.Stage.FINISHED_CLEAN

        def is_in_progress(self) -> bool:
            return self in [
                Task.Stage.IN_PROGRESS,
                Task.Stage.IN_PROGRESS_ABORT,
            ]

        def is_aborted(self) -> bool:
            return self in [
                Task.Stage.IN_PROGRESS_ABORT,
                Task.Stage.FINISHED_BY_ABORT,
            ]

        def is_finished(self, *, finishing_aborted: bool) -> bool:
            return self in [
                Task.Stage.FINISHED_CLEAN,
                Task.Stage.FINISHED_BY_EXCEPTION,
                Task.Stage.FINISHED_BY_ABORT,
            ] or (not finishing_aborted and self == Task.Stage.IN_PROGRESS_ABORT)

        @staticmethod
        def validate_transition(stage: "Task.Stage", next_stage: "Task.Stage") -> Exception | None:
            if (
                (
                    stage == Task.Stage.PENDING
                    and next_stage
                    not in [
                        Task.Stage.IN_PROGRESS,
                        Task.Stage.IN_PROGRESS_ABORT,
                    ]
                )
                or (
                    stage == Task.Stage.IN_PROGRESS
                    and next_stage
                    not in [
                        Task.Stage.IN_PROGRESS_ABORT,
                        Task.Stage.FINISHED_CLEAN,
                        Task.Stage.FINISHED_BY_ABORT,
                        Task.Stage.FINISHED_BY_EXCEPTION,
                    ]
                )
                or (
                    stage == Task.Stage.IN_PROGRESS_ABORT
                    and next_stage
                    not in [
                        Task.Stage.FINISHED_BY_ABORT,
                        Task.Stage.FINISHED_BY_EXCEPTION,
                    ]
                )
                or stage.is_finished(finishing_aborted=True)
            ):
                return Task.Stage.InvalidTransitionError(
                    f"Invalid task stage transition: {stage} -> {next_stage} "
                    "- this should never happen, please report this error"
                )
            return None

    # ------------------------------------------- State ------------------------------------------ #

    @dclass.dataclass
    class State(Generic[T2]):
        _task: "Task" = dclass.field(repr=False)
        _stage: "Task.Stage"
        result: T2 | None = None
        exception: Exception | None = None
        mutex: Lock = dclass.field(default_factory=Lock)

        def __post_init__(self):
            self._is_finished = PredicateEmitter(
                # stage has value semantics, so we have to use a lambda here
                lambda finishing_aborted: self.stage.is_finished(
                    finishing_aborted=finishing_aborted
                )
            )

        @property
        def task(self) -> "Task.Stage":
            return self._task

        @property
        def stage(self) -> "Task.Stage":
            return self._stage

        def set_stage__locked(self, new_stage: "Task.Stage") -> None:
            assert self.mutex.locked()

            transition_exception = Task.Stage.validate_transition(self._stage, new_stage)
            if transition_exception is not None:
                transition_exception.add_note(f"({self.task})")
                # this exception should be caught by an executor
                raise transition_exception

            self._stage = new_stage
            self._is_finished.evaluate_and_emit__locked()

        def create_finished_event__locked(self, *, finishing_aborted: bool) -> Event:
            assert self.mutex.locked()

            return self._is_finished.create_emit_event__locked(finishing_aborted=finishing_aborted)

        def add_event_to_abort_on_finish__locked(
            self,
            event: Event,
            *,
            finishing_aborted: bool,
        ) -> None:
            assert self.mutex.locked()

            self._is_finished.add_event_to_abort__locked(event, finishing_aborted=finishing_aborted)

        def finish_with_exception__locked(self, exception: Exception, *, raise_now: bool) -> None:
            assert self.mutex.locked()
            assert not self.stage.is_finished(finishing_aborted=True)

            if self.stage == Task.Stage.PENDING:
                self.set_stage__locked(Task.Stage.IN_PROGRESS_ABORT)

            self._exception = exception
            self.set_stage__locked(Task.Stage.FINISHED_BY_EXCEPTION)
            if raise_now:
                raise exception

        def finish_without_running__locked(self) -> None:
            assert self.mutex.locked()
            assert self._stage == Task.Stage.PENDING

            self.set_stage__locked(Task.Stage.IN_PROGRESS)
            self.set_stage__locked(Task.Stage.FINISHED_CLEAN)

    # ------------------------------------------ Future ------------------------------------------ #

    class Future(Generic[T2]):
        class AbortedError(Exception):
            ...

        def __init__(self, state: "Task.State[T2]"):
            self._state = state

        @property
        def stage(self) -> "Task.Stage":
            return self._state.stage

        def abort(self) -> bool:
            with self._state.mutex:
                if self.stage == Task.Stage.PENDING:
                    logger.debug("Aborting a pending task", details=self._state.task)
                    self._state.set_stage__locked(Task.Stage.IN_PROGRESS_ABORT)
                    self._state.set_stage__locked(Task.Stage.FINISHED_BY_ABORT)
                elif not self.stage.is_finished(finishing_aborted=False):
                    logger.debug("Aborting a running task", details=self._state.task)
                    self._state.set_stage__locked(Task.Stage.IN_PROGRESS_ABORT)
            return self.stage.is_aborted()

        def result(self, timeout: float | None = 0) -> T2:
            # finishing_aborted=False - result can be set only on non-aborted tasks
            if (
                timeout is not None
                and timeout <= 0
                and not self.stage.is_finished(finishing_aborted=False)
            ) or (
                (timeout is None or timeout > 0)
                and not self.wait(finishing_aborted=False, timeout=timeout)
            ):
                raise TimeoutError("Task not finished in time", details=self._task)

            if self._state.exception is not None:
                raise self._state.exception

            if self.stage.is_aborted():
                raise Task.Future.AbortedError("Task was aborted", details=self._task)

            return self._state.result

        def wait(self, finishing_aborted: bool, timeout: float | None = None) -> bool:
            return self.create_finished_event(finishing_aborted=finishing_aborted).wait(
                timeout=timeout
            )

        def create_finished_event(self, *, finishing_aborted: bool) -> Event:
            with self._state.mutex:
                return self._state.create_finished_event__locked(
                    finishing_aborted=finishing_aborted
                )

    # --------------------------------------- FinishContext -------------------------------------- #

    class FinishContext(Generic[T2]):
        def __init__(self, state: "Task.State[T2]"):
            self._state = state
            self._active = False

        def __enter__(self) -> None:
            self._state.mutex.acquire()
            try:
                assert not self._active
                assert (
                    self._state.stage.is_in_progress()
                ), f"Task not in-progress ({self._state.task})"

                if self._state.stage.is_aborted():
                    raise Task.Abort()
            except:
                self._state.mutex.release()
                raise

            self._active = True

        def __exit__(self, exc_type: type[Exception] | None, exc: Exception, traceback) -> bool:
            try:
                assert self._active
                assert self._state.stage.is_in_progress(), (
                    "Task already finished - only `Task.Executor` and `Task.FinishContext` "
                    f"can finish tasks ({self._state.task})"
                )

                if exc_type is None:
                    self._state.set_stage__locked(Task.Stage.FINISHED_CLEAN)
                return False
            finally:
                self._active = False
                self._state.mutex.release()

        @property
        def active(self) -> bool:
            return self._active

    # ----------------------------------------- Executor ----------------------------------------- #

    class Executor(Generic[T2]):
        def __init__(self, state: "Task.State[T2]") -> None:
            self._state = state
            self._finish_context = Task.FinishContext[T2](state)
            self._active = False

        def __enter__(self) -> None:
            with self._state.mutex:
                try:
                    assert not self._active, f"({self._state.task})"
                    assert self._state.stage.is_in_progress(), f"({self._state.task})"

                    if self._state.stage.is_aborted():
                        logger.debug(
                            "Task aborted before it could reach the executor",
                            details=self._state.task,
                        )
                        self._state.set_stage__locked(Task.Stage.FINISHED_BY_ABORT)
                        raise Task.Abort()
                except Exception as exception:
                    if not self._state.stage.is_finished(finishing_aborted=True):
                        self._state.finish_with_exception__locked(exception, raise_now=True)
                    raise

            self._active = True

        def __exit__(self, exc_type: type[Exception] | None, exc: Exception, traceback) -> bool:
            exception_handled = False

            with self._state.mutex:
                assert exc_type != Task.Abort or self._state.stage.is_in_progress()
                assert (
                    self._state.stage.is_in_progress()
                    or self._state.stage == Task.Stage.FINISHED_CLEAN
                ), (
                    "Task not in progress - only `Task.Executor` and `Task.FinishContext` "
                    f"can finish aborted/crashed tasks ({self._state.task})"
                )

                if self._state.stage.is_in_progress():
                    if exc_type == Task.Abort:
                        if self._state.stage == Task.Stage.IN_PROGRESS_ABORT:
                            logger.debug("Task aborted as requested", details=self._state.task)
                        else:
                            logger.debug("Task self-aborted", details=self._state.task)

                        self._state.set_stage__locked(Task.Stage.FINISHED_BY_ABORT)
                        exception_handled = True
                    elif exc_type is not None:
                        logger.error("Task crashed", details=self._state.task)
                        self._state.finish_with_exception__locked(exc, raise_now=False)
                        exception_handled = False
                    else:
                        logger.error("Task implementaion error", details=self._state.task)
                        self._state.finish_with_exception__locked(
                            AssertionError(
                                "Task finished running but did not mark itself as finished "
                                f"({self._state.task})",
                            ).with_traceback(traceback),
                            raise_now=True,
                        )

            assert self._active
            return exception_handled

        @property
        def stage(self) -> "Task.Stage":
            assert self._active

            return self._state.stage

        @property
        def finish_context(self) -> "Task.FinishContext[T2]":
            assert self._active

            return self._finish_context

        def set_result(self, result: T2) -> None:
            assert self._active
            assert self.finish_context.active
            assert self._state.mutex.locked()
            assert self._state.stage.is_in_progress()

            self._state.result = result

        def exit_if_aborted(self) -> None:
            if self.stage.is_aborted():
                self.abort()

        def abort(self) -> None:
            assert self._active

            raise Task.Abort()

        def finish(self, result: T2 = None) -> None:
            assert self._active
            assert not self.finish_context.active

            with self.finish_context:
                self.set_result(result)

        def finish_with(self, fn: Callable[..., T2], /, *args, **kwargs) -> None:
            assert self._active
            assert not self.finish_context.active

            with self.finish_context:
                self.set_result(fn(*args, **kwargs))

        def abort_aware_wait_for_future(
            self,
            future: "Task.Future",
            *,
            finishing_aborted: bool = False,
            timeout: float | None = None,
            abort_future: bool = True,
        ) -> bool:
            assert self._active
            assert future._state.task is not self._state.task  # pylint: disable=protected-access

            is_finished_event = future.create_finished_event(finishing_aborted=finishing_aborted)
            try:
                return self.abort_aware_wait(is_finished_event, timeout=timeout)
            except Task.Abort:
                if abort_future:
                    future.abort()
                raise

        def abort_aware_wait(self, event: Event, *, timeout: float | None = None) -> bool:
            assert self._active

            with self._state.mutex:
                self._state.add_event_to_abort_on_finish__locked(event, finishing_aborted=False)
            result = event.wait(timeout=timeout)
            self.exit_if_aborted()
            return result

        def abort_aware_sleep(self, sleep_time: float) -> bool:
            """Returns `False` if aborted"""
            assert self._active
            assert sleep_time is not None

            with self._state.mutex:
                event = self._state.create_finished_event__locked(finishing_aborted=False)
            event.wait(timeout=sleep_time)
            return not self.stage.is_aborted()

    # ------------------------------------------- Task ------------------------------------------- #

    id: Any = dclass.field(default=None, kw_only=True)
    already_finished: dclass.InitVar[bool] = dclass.field(default=False, kw_only=True)
    future: "Task.Future[T1]" = dclass.field(init=False, repr=False)
    _state: "Task.State[T1]" = dclass.field(init=False)
    _executor: "Task.Executor[T1]" = dclass.field(init=False, repr=False)

    def __post_init__(self, already_finished: bool):
        init_stage = Task.Stage.FINISHED_CLEAN if already_finished else Task.Stage.PENDING
        super().__setattr__("_state", Task.State(self, init_stage))
        super().__setattr__("future", Task.Future(state=self._state))
        super().__setattr__("_executor", Task.Executor(state=self._state))

    def __del__(self):
        with self._state.mutex:
            if not self._state.stage.is_finished(finishing_aborted=True):
                self._state.finish_with_exception__locked(
                    Task.UnexpectedStageError("Task never finished", self._state),
                    raise_now=True,
                )

    def __str__(self) -> str:
        return repr(self)

    def finish_without_running(self) -> None:
        with self._state.mutex:
            self._state.finish_without_running__locked()

    def execute_and_finish(self, fn: Callable, /, *args, **kwargs) -> "Task.Stage":
        def job(executor: Task.Executor):
            with executor.finish_context:
                executor.set_result(fn(*args, **kwargs))

        return self.execute(job)

    def execute(self, fn: Callable[["Task.Executor"], None]) -> "Task.Stage":
        try:
            with self._executor:
                fn(self._executor)
        except Task.Abort:
            assert self._state.stage.is_finished(finishing_aborted=True)
        return self._state.stage

    def run_pending(self) -> None:
        can_run = False
        with self._state.mutex:
            if self._state.stage == Task.Stage.PENDING:
                self._state.set_stage__locked(Task.Stage.IN_PROGRESS)
                can_run = True
        if can_run:
            logger.debug("Running a task", details=self)
            self.run_impl()
            logger.debug("Finished a task", details=self)

    def run_impl(self) -> None:
        """Task implementation

        By default this method just raises `self` and the actual implementation is handled by an
        `except TaskType` block.

        This method can be overridden in derived classes to implement custom behavior.

        Raises:
            self: self
        """
        raise self

    def invalidates(self, task: "Task") -> bool:  # pylint: disable=unused-argument
        return False


@dclass.dataclass(frozen=True)
class FnTask(Task[T1]):
    fn: Callable[[Task.Executor[T1]], T1]

    def run_impl(self) -> None:
        self.execute(self.fn)


# ------------------------------------------------------------------------------------------------ #
#                                             TaskQueue                                            #
# ------------------------------------------------------------------------------------------------ #


class TaskQueue:
    def __init__(self, mutex: Lock = None) -> None:
        self._mutex = mutex or Lock()
        self._tasks = deque[Task]()
        self._task_added = PredicateEmitter(predicate=lambda: not self.is_empty())

        self._current_task = Task(id="DUMMY_INIT_TASK", already_finished=True)

    def __len__(self) -> int:
        return len(self._tasks)

    @property
    def mutex(self) -> Lock:
        return self._mutex

    def is_empty(self) -> bool:
        return len(self._tasks) == 0

    def clear(self, *, abort_current_task: bool = True) -> None:
        with self.mutex:
            self.clear__locked(abort_current_task=abort_current_task)

    def clear__locked(self, *, abort_current_task: bool) -> None:
        assert self.mutex.locked()

        if abort_current_task:
            self._current_task.future.abort()
        for task in self._tasks:
            task.future.abort()
        self._tasks.clear()

    def add_task(self, task: Task, *, apply_invalidation_rules: bool = False) -> None:
        with self.mutex:
            self.add_task__locked(task, apply_invalidation_rules=apply_invalidation_rules)

    def add_task__locked(self, task: Task, *, apply_invalidation_rules: bool = False) -> None:
        assert self.mutex.locked()

        if apply_invalidation_rules:
            if not self._current_task.future.stage.is_finished(finishing_aborted=False):
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
        self._task_added.evaluate_and_emit__locked()

    def run_all(self, timeout: float | None = 0) -> None:
        assert self._current_task.future.stage.is_finished(
            finishing_aborted=True
        ), f"Previous task should be already finished ({self._current_task})"

        if timeout is None or timeout > 0:
            self.create_task_added_event().wait(timeout=timeout)

        while not self.is_empty():
            with self.mutex:
                self._current_task = self._tasks.popleft()
            self._current_task.run_pending()  # this can raise a task exception

    def create_task_added_event(self) -> Event:
        with self.mutex:
            return self._task_added.create_emit_event__locked()

    def add_event_to_abort_on_task_added(self, event: Event) -> None:
        with self.mutex:
            self._task_added.add_event_to_abort__locked(event)


# ------------------------------------------------------------------------------------------------ #
#                            Interfaces of ThreadPool and ThreadSpawner                            #
# ------------------------------------------------------------------------------------------------ #


class ThreadPool(ABC):
    @abstractmethod
    def start(self, task: FnTask[T1]) -> Task.Future[T1]:
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
        self._running_tasks = dict[int, FnTask]()

    def start(self, task: FnTask[T1]) -> Task.Future[T1]:
        task_id = id(task)
        self._running_tasks[task_id] = task

        def job():
            try:
                do_job_with_exception_logging(task.run_pending, args=[], kwargs={})
            finally:
                self._running_tasks.pop(task_id)

        self._thread_pool.submit(job)
        return task.future


# ------------------------------------------------------------------------------------------------ #
#                                          PyThreadSpawner                                         #
# ------------------------------------------------------------------------------------------------ #


class PyThreadSpawner(ThreadSpawner):
    def start(self, job: Callable, /, *args, **kwargs):
        Thread(target=do_job_with_exception_logging, args=[job, args, kwargs], daemon=True).start()


def do_job_with_exception_logging(job: Callable, args: tuple, kwargs: dict) -> None:
    with logger.catch():
        return job(*args, **kwargs)
