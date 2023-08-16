from typing import Callable


class Signal:

  class TooManySubscribers(Exception):

    def __init__(self, message: str):
      super().__init__(message)

  def __init__(self, subscribers: list[Callable] = [], max_subscribers: int | str = 'min'):
    self._subscribers = []
    match max_subscribers:
      case 'min':
        self._max_subscribers = float(max(1, len(subscribers)))
      case 'inf':
        self._max_subscribers = float('inf')
      case _:
        self._max_subscribers = float(max_subscribers)

    if self._max_subscribers <= 0:
      raise ValueError('To be useful, signal should have `max_subscribers` >= 1')

    for subscriber in subscribers:
      self.connect(subscriber)

  def emit(self, *args, **kwargs) -> None:
    for subscriber in self._subscribers:
      subscriber(*args, **kwargs)

  def connect(self, subscriber: Callable) -> None:
    if len(self._subscribers) >= self._max_subscribers:
      raise Signal.TooManySubscribers(
          f'This signal can have at most {self._max_subscribers} subscribers')
    self._subscribers.append(subscriber)
