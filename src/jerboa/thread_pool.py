from typing import Callable
from abc import ABC, abstractmethod


class ThreadPoolBase(ABC):
    @abstractmethod
    def __init__(self, workers=None) -> None:
        super().__init__()

    @abstractmethod
    def start(self, fn: Callable[[], None]):
        raise NotImplementedError()

    @abstractmethod
    def wait(self, timeout: int = 0) -> None:
        raise NotImplementedError()
