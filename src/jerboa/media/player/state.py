from enum import Enum, auto


class PlayerState(Enum):
    STOPPED = auto()
    STOPPED_ON_ERROR = auto()
    SUSPENDED = auto()
    PLAYING = auto()
