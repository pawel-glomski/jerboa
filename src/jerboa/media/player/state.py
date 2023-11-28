from enum import Enum, auto


class PlayerState(Enum):
    UNINITIALIZED = auto()
    SUSPENDED = auto()
    SUSPENDED_EOF = auto()
    PLAYING = auto()

    @property
    def is_suspended(self) -> bool:
        return self in [PlayerState.SUSPENDED, PlayerState.SUSPENDED_EOF]
