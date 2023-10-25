import av
import numpy as np
from dataclasses import dataclass

from jerboa.core.timeline import RangeMappingResult


@dataclass
class TimedFrame:
    beg_timepoint: float
    end_timepoint: float


@dataclass
class TimedAVFrame(TimedFrame):
    av_frame: av.AudioFrame | av.VideoFrame


@dataclass
class PreMappedFrame(TimedAVFrame):
    mapping_scheme: RangeMappingResult | None = None


@dataclass
class MappedAudioFrame(TimedFrame):
    audio_signal: np.ndarray


@dataclass
class MappedVideoFrame(TimedFrame):
    av_frame: av.VideoFrame


JbAudioFrame = MappedAudioFrame


@dataclass
class JbVideoFrame(TimedFrame):
    width: int
    height: int
    planes: list[bytes]
