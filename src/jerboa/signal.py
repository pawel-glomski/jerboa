from typing import Callable

import math


class Signal:

  class TooManySubscribers(Exception):

    def __init__(self, message: str):
      super().__init__(message)

  def __init__(self, *subscribers: Callable, max_subscribers: int | float | str = math.inf):
    self._subscribers = []
    self._max_subscribers = float(len(subscribers) if max_subscribers == 'init' else subscribers)

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
