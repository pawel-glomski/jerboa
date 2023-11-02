import time


class SynchronizationClock:
    def __init__(self) -> None:
        self._time_now_ns = time.perf_counter_ns
        self.stop()

    def stop(self) -> None:
        self._cumulative_time_ns = 0
        self._last_time_ns: int | None = None

    def resume(self) -> None:
        self._last_time_ns = self._time_now_ns()

    def suspend(self) -> None:
        if self._last_time_ns is not None:
            self._cumulative_time_ns += self._time_now_ns() - self._last_time_ns
        self._last_time_ns = None

    def time(self) -> float:
        result = self._cumulative_time_ns
        if self._last_time_ns is not None:
            result += self._time_now_ns() - self._last_time_ns
        return result / 1e9
