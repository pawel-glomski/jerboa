import av
import enum
from dataclasses import dataclass
from fractions import Fraction


class MediaType(enum.Enum):
    AUDIO = "audio"
    VIDEO = "video"


class AudioCapabilities:
    # ordered by the preference
    class SampleFormat(enum.Flag):
        U8 = enum.auto()
        S16 = enum.auto()
        S32 = enum.auto()
        # float32 is the most preffered since it is the internal format used for processing
        FP32 = enum.auto()

    class ChannelLayout(enum.Flag):
        MONO = enum.auto()
        STEREO = enum.auto()
        SURROUND_3_0 = enum.auto()  # CH_LAYOUT_SURROUND in ffmpeg
        SURROUND_3_1 = enum.auto()  # CH_LAYOUT_4POINT0 in ffmpeg
        SURROUND_5_0 = enum.auto()
        SURROUND_5_1 = enum.auto()
        SURROUND_7_0 = enum.auto()
        SURROUND_7_1 = enum.auto()

    sample_formats: SampleFormat
    channel_layouts: ChannelLayout
    channels_num_min: int
    channels_num_max: int
    sample_rate_min: int
    sample_rate_max: int


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
    class PixelFormat(enum.Enum):
        RGBA8888 = enum.auto()

    format: PixelFormat

    @property
    def media_type(self) -> MediaType:
        return MediaType.VIDEO


@dataclass(frozen=True)
class AudioStreamInfo:
    stream_index: int
    start_timepoint: float

    sample_rate: int

    @property
    def media_type(self) -> MediaType:
        return MediaType.AUDIO


@dataclass(frozen=True)
class VideoStreamInfo:
    stream_index: int
    start_timepoint: float

    width: int
    height: int
    guessed_frame_rate: float
    sample_aspect_ratio: Fraction

    @property
    def media_type(self) -> MediaType:
        return MediaType.VIDEO
