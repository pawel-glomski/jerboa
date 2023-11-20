import time
from abc import ABC, abstractmethod


class PlaybackTimer(ABC):
    @abstractmethod
    def current_timepoint(self) -> float | None:
        raise NotImplementedError()


class ClockPlaybackTimer(PlaybackTimer):
    def __init__(self) -> None:
        super().__init__()
        self._time_now_ns = time.perf_counter_ns
        self.deinitialize()

    @property
    def is_initialized(self) -> bool:
        return self._cumulative_time_ns is not None

    @property
    def is_running(self) -> bool:
        return self._last_time_ns is not None

    def deinitialize(self) -> None:
        self._cumulative_time_ns: int | None = None
        self._last_time_ns: int | None = None

    def initialize(self) -> None:
        assert not self.is_initialized

        self._cumulative_time_ns = 0

    def resume(self) -> None:
        assert self.is_initialized

        self._last_time_ns = self._time_now_ns()

    def suspend(self) -> None:
        assert self.is_initialized

        if self._last_time_ns is not None:
            self._cumulative_time_ns += self._time_now_ns() - self._last_time_ns
        self._last_time_ns = None

    def current_timepoint(self) -> float | None:
        if self.is_initialized:
            result = self._cumulative_time_ns
            if self._last_time_ns is not None:
                result += self._time_now_ns() - self._last_time_ns
            return result / 1e9
        return None

    def seek(self, timepoint: float) -> None:
        assert self.is_initialized
        assert not self.is_running

        self._cumulative_time_ns = timepoint * 1e9
