from dataclasses import dataclass
from enum import Enum

import av
import numpy as np

from jerboa.utils.circular_buffer import CircularBuffer

AUDIO_BUFFER_SIZE_MODIFIER = 1.2


class MediaType(Enum):
    AUDIO = "audio"
    VIDEO = "video"


@dataclass
class AudioConfig:
    format: av.AudioFormat
    layout: av.AudioLayout
    sample_rate: int
    frame_duration: float | None = None

    @property
    def media_type(self) -> MediaType:
        return MediaType.AUDIO

    @property
    def channels_num(self) -> int:
        return len(self.layout.channels)

    @staticmethod
    def from_stream(stream: av.audio.AudioStream) -> "AudioConfig":
        if MediaType(stream.type) != MediaType.AUDIO:
            raise ValueError(f"Wrong stream type: {stream.type}")
        return AudioConfig(stream.format, stream.layout, stream.sample_rate)


@dataclass
class VideoConfig:
    format: av.VideoFormat

    @property
    def media_type(self) -> MediaType:
        return MediaType.VIDEO

    @staticmethod
    def from_stream(stream: av.video.VideoStream) -> "VideoConfig":
        if MediaType(stream.type) != MediaType.VIDEO:
            raise ValueError(f"Wrong stream type: {stream.type}")
        return VideoConfig(stream.format)


def config_from_stream(stream: av.audio.AudioStream | av.video.VideoStream):
    if MediaType(stream.type) == MediaType.AUDIO:
        return AudioConfig.from_stream(stream)
    return VideoConfig.from_stream(stream)


def get_format_dtype(fmt: av.AudioFormat) -> np.dtype:
    return np.dtype(av.audio.frame.format_dtypes[fmt.name])


def create_audio_buffer(audio_config: AudioConfig, max_duration: float = None) -> CircularBuffer:
    if max_duration is None and audio_config.frame_duration is None:
        raise ValueError("`max_duration` or `audio_config.frame_duration` must be provided")

    if max_duration is None:
        max_duration = audio_config.frame_duration

    buffer_dtype = get_format_dtype(audio_config.format)
    buffer_length = int(max_duration * audio_config.sample_rate * AUDIO_BUFFER_SIZE_MODIFIER)
    if audio_config.format.is_planar:
        buffer_shape = [audio_config.channels_num, buffer_length]
        axis = 1
    else:
        buffer_shape = [buffer_length, audio_config.channels_num]
        axis = 0

    return CircularBuffer(buffer_shape, axis, buffer_dtype)
