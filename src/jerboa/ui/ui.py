from abc import ABC, abstractmethod


class JerboaUI(ABC):

  @abstractmethod
  def run_event_loop(self) -> int:
    raise NotImplementedError()
