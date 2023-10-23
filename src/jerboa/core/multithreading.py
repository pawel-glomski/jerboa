from typing import Callable
from abc import ABC, abstractmethod

from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor, TimeoutError as TimeoutErrorTPE, wait

from jerboa.core.logger import logger


class ThreadPool(ABC):
    @abstractmethod
    def start(self, job: Callable, *args, **kwargs):
        raise NotImplementedError()

    @abstractmethod
    def wait(self, timeout: int | None = None) -> None:
        raise NotImplementedError()


class ThreadSpawner(ABC):
    @abstractmethod
    def start(self, job: Callable, *args, **kwargs):
        raise NotImplementedError()

    @abstractmethod
    def wait(self, timeout: int | None = None) -> bool:
        raise NotImplementedError()


class PyThreadPool(ThreadPool):
    def __init__(self, workers: int | None = None):
        super().__init__()
        self._thread_pool = ThreadPoolExecutor(workers)

    def start(self, job: Callable, *args, **kwargs):
        try:

            def worker():
                try:
                    job(*args, **kwargs)
                except Exception as e:
                    logger.exception(e)
                    raise

            wait([self._thread_pool.submit(worker)], timeout=0)
        except TimeoutErrorTPE:
            pass

    def wait(self, timeout: int | None = None) -> bool:
        self._thread_pool.shutdown(wait=timeout is not None and timeout > 0)


class PyThreadSpawner(ThreadSpawner):
    def __init__(self):
        super().__init__()
        self._threads = set[Thread]()
        self._mutex = Lock()

    def start(self, job: Callable, *args, **kwargs):
        thread = Thread(target=job, args=args, kwargs=kwargs)
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
