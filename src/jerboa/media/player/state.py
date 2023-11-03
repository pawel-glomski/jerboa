from enum import Enum, auto


class PlayerState(Enum):
    SHUT_DOWN = auto()
    SUSPENDED = auto()
    PLAYING = auto()
