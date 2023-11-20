from abc import ABC, abstractmethod

from jerboa.core.multithreading import Task
from jerboa.media.core import MediaType, AudioConfig, VideoConfig, AudioConstraints
from .frame import JbAudioFrame, JbVideoFrame


class Decoder(ABC):
    @property
    def media_type(self) -> MediaType:
        raise NotImplementedError()

    @property
    @abstractmethod
    def is_done(self) -> bool:
        raise NotImplementedError()

    @property
    @abstractmethod
    def buffered_duration(self) -> float:
        raise NotImplementedError()

    @property
    @abstractmethod
    def presentation_media_config(self) -> AudioConfig | VideoConfig:
        raise NotImplementedError()

    @abstractmethod
    def pop(self, /, *args, timeout: float | None = None) -> JbAudioFrame | JbVideoFrame | None:
        raise NotImplementedError()

    @abstractmethod
    def prefill(self, timeout: float | None = None) -> Task.Future:
        raise NotImplementedError()

    def kill() -> Task.Future:
        raise NotImplementedError()

    @abstractmethod
    def seek(self, timepoint: float) -> Task.Future:
        raise NotImplementedError()

    @abstractmethod
    def apply_new_media_constraints(self, new_constraints: AudioConstraints | None) -> Task.Future:
        raise NotImplementedError()
