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
        self.uninitialize()

    @property
    def is_initialized(self) -> bool:
        return self._cumulative_time_ns is not None

    @property
    def is_running(self) -> bool:
        return self._last_time_ns is not None

    def uninitialize(self) -> None:
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
