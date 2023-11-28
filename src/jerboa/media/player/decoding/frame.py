import av
import numpy as np
from dataclasses import dataclass, field

from jerboa.core.timeline import RangeMappingResult


@dataclass
class TimedFrame:
    beg_timepoint: float
    end_timepoint: float

    @property
    def duration(self) -> float:
        return self.end_timepoint - self.beg_timepoint


@dataclass
class TimedAVFrame(TimedFrame):
    av_frame: av.AudioFrame | av.VideoFrame = field(repr=False)


@dataclass
class PreMappedFrame(TimedAVFrame):
    mapping_scheme: RangeMappingResult | None = None


@dataclass
class MappedAudioFrame(TimedFrame):
    audio_signal: np.ndarray


@dataclass
class MappedVideoFrame(TimedFrame):
    av_frame: av.VideoFrame = field(repr=False)


JbAudioFrame = MappedAudioFrame


@dataclass
class JbVideoFrame(TimedFrame):
    width: int
    height: int
    planes: list[np.ndarray[np.ubyte]]
