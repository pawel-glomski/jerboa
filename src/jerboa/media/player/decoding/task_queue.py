from typing import Callable
from threading import Lock, Condition
from collections import deque


class Task(Exception):
    def run(self) -> None:
        raise self


class TaskQueue:
    def __init__(self, mutex: Lock = Lock()) -> None:
        self._mutex = mutex
        self._tasks = deque[Task]()
        self._task_added = Condition(self._mutex)
        self._task_added_callbacks = set[Callable[[Task], None]]()

        self.add_on_task_added_callback(self._task_added.notify)

    @property
    def mutex(self) -> Lock:
        return self._mutex

    def is_empty(self) -> bool:
        return len(self._tasks) == 0

    def add_on_task_added_callback(self, callback: Callable[[], None]) -> None:
        assert callback not in self._task_added_callbacks
        self._task_added_callbacks.add(callback)

    def run_all(self) -> None:
        if not self.is_empty():
            with self.mutex:
                self.run_all__without_lock()

    def run_all__without_lock(self) -> None:
        assert self.mutex.locked()
        while not self.is_empty():
            self._tasks.popleft().run()  # this should usually raise a task exception

    def wait_for_and_run_task(self) -> None:
        with self.mutex:
            self._task_added.wait_for(lambda: not self.is_empty())
            self.run_all__without_lock()

    def add_task(self, task: Task) -> None:
        with self.mutex:
            self.add_task__without_lock(task)

    def add_task__without_lock(self, task: Task) -> None:
        assert self.mutex.locked()
        self._tasks.append(task)
        for callback in self._task_added_callbacks:
            callback()
