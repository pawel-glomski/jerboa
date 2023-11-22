from enum import Enum, auto


class PlayerState(Enum):
    UNINITIALIZED = auto()
    SUSPENDED = auto()
    PLAYING = auto()
