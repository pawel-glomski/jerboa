from enum import Enum, auto


class PlayerState(Enum):
    UNINITIALIZED = auto()
    SUSPENDED = auto()
    PLAYING = auto()


# class PlayerInitializationError(Exception):
#     ...


# class PlayerSeekError(Exception):
#     ...


# class PlayerNotRespondingError(Exception):
#     ...
