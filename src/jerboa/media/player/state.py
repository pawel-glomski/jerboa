from enum import Enum, auto


class PlayerState(Enum):
    STOPPED = auto()
    SUSPENDED = auto()
    PLAYING = auto()
