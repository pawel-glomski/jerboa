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
from dataclasses import dataclass
from threading import Lock, Condition
import inspect

from jerboa import utils


class Signal:
    class Promise:
        class AlreadyFulfilledError(Exception):
            ...

        class NotFulfilledError(Exception):
            ...

        def __init__(self, fulfill_num: int) -> None:
            self._fulfill_num = fulfill_num
            self._condition = Condition()

        def __del__(self):
            with self._condition:
                if not self.is_fulfilled:
                    raise Signal.Promise.NotFulfilledError("Promise never fulfilled")

        @property
        def is_fulfilled(self) -> bool:
            return self._fulfill_num == 0

        def fulfill(self) -> None:
            with self._condition:
                if self.is_fulfilled:
                    raise Signal.Promise.AlreadyFulfilledError("Promise already fulfilled")

                self._fulfill_num -= 1
                if self.is_fulfilled:
                    self._condition.notify_all()

        def wait_done(self, timeout: float | None = None) -> None:
            with self._condition:
                if not self._condition.wait_for(lambda: self.is_fulfilled, timeout=timeout):
                    raise TimeoutError("Promise not fulfilled in time")

    @dataclass
    class EmitArg:
        slot_kwargs: dict
        promise: "Signal.Promise"

    class TooManySubscribers(Exception):
        pass

    def __init__(self, *arg_names: str, max_subscribers: float = float("inf")):
        self._arg_names = set(arg_names)
        self._subscribers = list[Callable[[Signal.EmitArg], None]]()
        self._max_subscribers = float(max_subscribers)
        if self._max_subscribers <= 0:
            raise ValueError("For a signal to be functional, `max_subscribers` must be at least 1")
        self._mutex = Lock()

    @property
    def subscribers(self) -> list[Callable[[EmitArg], None]]:
        return self._subscribers

    def connect(self, subscriber: Callable) -> None:
        utils.assert_callable(subscriber, expected_args=self._arg_names)

        def _worker(emit_arg: Signal.EmitArg):
            try:
                subscriber(**emit_arg.slot_kwargs)
            finally:
                emit_arg.promise.fulfill()

        with self._mutex:
            if len(self._subscribers) >= self._max_subscribers:
                raise Signal.TooManySubscribers(
                    f"Maximum number of subscribers ({self._max_subscribers}) reached.",
                )
            self._subscribers.append(_worker)

    # capture positional arguments to `_`, to crash on the "missing arguments" error instead
    def emit(self, *_, **kwargs) -> Promise:
        with self._mutex:
            emit_arg = Signal.EmitArg(
                slot_kwargs=kwargs,
                promise=Signal.Promise(len(self.subscribers)),
            )
            for subscriber in self.subscribers:
                subscriber(emit_arg)
            return emit_arg.promise
