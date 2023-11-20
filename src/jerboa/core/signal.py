from abc import ABC, abstractmethod
from typing import Callable, ContextManager
from dataclasses import dataclass
from threading import Lock, Condition
import inspect

from .logger import logger


class Signal(ABC):
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

    class NoOpContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            pass

    @dataclass
    class EmitArg:
        context: ContextManager
        success_callback: Callable
        error_callback: Callable
        slot_kwargs: dict
        promise: "Signal.Promise"

    class TooManySubscribers(Exception):
        pass

    def __init__(self, /, *arg_names: str, max_subscribers: float = float("inf")):
        self._arg_names = arg_names
        self._arg_names_set = set(arg_names)
        self._subscribers = list[Callable[[Signal.EmitArg], None]]()
        self._max_subscribers = float(max_subscribers)
        if self._max_subscribers <= 0:
            raise ValueError("For a signal to be functional, `max_subscribers` must be at least 1")
        self._mutex = Lock()

    @property
    def subscribers(self) -> list[Callable[[EmitArg], None]]:
        return self._subscribers

    @abstractmethod
    def connect(self, subscriber: Callable) -> None:
        subscriber_parameters = inspect.signature(subscriber).parameters

        missing_args = self._arg_names_set - subscriber_parameters.keys()
        unexpected_args = subscriber_parameters.keys() - self._arg_names_set
        unexpected_args -= {
            param.name
            for param in subscriber_parameters.values()
            if (param.kind in [inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL])
            or param.default is not inspect.Parameter.empty
        }
        if len(missing_args) > 0 or len(unexpected_args):
            raise ValueError(
                f"Subscriber ({subscriber}) has wrong signature. "
                f"Missing args={missing_args}, unexpected args={unexpected_args}"
            )

        def _worker(emit_arg: Signal.EmitArg):
            try:
                with emit_arg.context:
                    subscriber(**emit_arg.slot_kwargs)
                    emit_arg.success_callback()
            except:
                emit_arg.error_callback()
                raise
            finally:
                emit_arg.promise.fulfill()

        with self._mutex:
            if len(self._subscribers) >= self._max_subscribers:
                raise Signal.TooManySubscribers(
                    f"Maximum number of subscribers ({self._max_subscribers}) reached.",
                )
            self._subscribers.append(_worker)

    # TODO: remove these args after a commit
    @abstractmethod
    def emit(
        self,
        context: ContextManager = NoOpContext(),
        success_callback: Callable = lambda: None,
        error_callback: Callable = lambda: None,
        /,
        **kwargs,
    ) -> Promise:
        with self._mutex:
            emit_arg = Signal.EmitArg(
                context=context,
                success_callback=success_callback,
                error_callback=error_callback,
                slot_kwargs=kwargs,
                promise=Signal.Promise(len(self.subscribers)),
            )
            for subscriber in self.subscribers:
                subscriber(emit_arg)
            return emit_arg.promise
