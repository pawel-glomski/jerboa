from typing import Callable


class Signal:
    class TooManySubscribers(Exception):
        pass

    def __init__(self, max_subscribers: float = float("inf")):
        self._subscribers = []
        self._max_subscribers = float(max_subscribers)
        if self._max_subscribers <= 0:
            raise ValueError("For a signal to be functional, `max_subscribers` must be at least 1")

    def emit(self, *args) -> None:
        for subscriber in self._subscribers:
            subscriber(*args)

    def connect(self, subscriber: Callable) -> None:
        if len(self._subscribers) >= self._max_subscribers:
            raise Signal.TooManySubscribers(
                f"Maximum number of subscribers ({self._max_subscribers}) reached.",
            )
        self._subscribers.append(subscriber)
