from abc import ABC, abstractmethod
from typing import Callable, ContextManager
from dataclasses import dataclass
import inspect


class NoOpContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


@dataclass
class EmitArg:
    context: ContextManager
    post_callback: Callable
    slot_kwargs: dict


class Signal(ABC):
    class TooManySubscribers(Exception):
        pass

    def __init__(self, /, *arg_names: str, max_subscribers: float = float("inf")):
        self._arg_names = arg_names
        self._arg_names_set = set(arg_names)
        self._subscribers = list[Callable[[EmitArg], None]]()
        self._max_subscribers = float(max_subscribers)
        if self._max_subscribers <= 0:
            raise ValueError("For a signal to be functional, `max_subscribers` must be at least 1")

    @property
    def subscribers(self) -> list[Callable[[EmitArg], None]]:
        return self._subscribers

    @abstractmethod
    def connect(self, subscriber: Callable) -> None:
        subscriber_arg_names = inspect.signature(subscriber).parameters.keys()

        missing_args = self._arg_names_set - subscriber_arg_names
        unexpected_args = subscriber_arg_names - self._arg_names_set
        if len(missing_args) > 0 or len(unexpected_args):
            raise ValueError(
                f"Subscriber ({subscriber}) has wrong signature. "
                f"Missing args={missing_args}, unexpected args={unexpected_args}"
            )

        def _worker(emit_arg: EmitArg):
            with emit_arg.context:
                subscriber(**emit_arg.slot_kwargs)
                emit_arg.post_callback()

        if len(self._subscribers) >= self._max_subscribers:
            raise Signal.TooManySubscribers(
                f"Maximum number of subscribers ({self._max_subscribers}) reached.",
            )
        self._subscribers.append(_worker)

    @abstractmethod
    def emit(
        self,
        context: ContextManager = NoOpContext(),
        post_callback: Callable = lambda: None,
        /,
        **kwargs,
    ) -> None:
        emit_arg = EmitArg(
            context=context,
            post_callback=post_callback,
            slot_kwargs=kwargs,
        )
        for subscriber in self._subscribers:
            subscriber(emit_arg)
