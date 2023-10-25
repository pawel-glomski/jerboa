import enum
from dataclasses import dataclass
from fractions import Fraction

USING_PLANAR_AUDIO_ONLY = True


class MediaType(enum.Enum):
    AUDIO = "audio"
    VIDEO = "video"


@dataclass
class AudioConstraints:
    class SampleFormat(enum.Flag):
        NONE = 0

        U8 = enum.auto()
        S16 = enum.auto()
        S32 = enum.auto()
        F32 = enum.auto()

        @property
        def is_packed(self) -> bool:
            return not self.is_planar

        @property
        def is_planar(self) -> bool:
            assert USING_PLANAR_AUDIO_ONLY
            return True

        def best_quality(self) -> "AudioConstraints.SampleFormat":
            for sf in reversed(AudioConstraints.SampleFormat):
                if sf & self:
                    return sf
            return AudioConstraints.SampleFormat.NONE

    class ChannelLayout(enum.Flag):
        NONE = 0

        CHANNEL_LFE = enum.auto()
        CHANNEL_FRONT_LEFT = enum.auto()
        CHANNEL_FRONT_RIGHT = enum.auto()
        CHANNEL_FRONT_CENTER = enum.auto()
        CHANNEL_BACK_LEFT = enum.auto()
        CHANNEL_BACK_RIGHT = enum.auto()
        CHANNEL_SIDE_LEFT = enum.auto()
        CHANNEL_SIDE_RIGHT = enum.auto()

        _LAYOUT_MARK = enum.auto()
        LAYOUT_MONO = _LAYOUT_MARK | CHANNEL_FRONT_CENTER
        LAYOUT_STEREO = _LAYOUT_MARK | CHANNEL_FRONT_LEFT | CHANNEL_FRONT_RIGHT
        LAYOUT_2_1 = LAYOUT_STEREO | CHANNEL_LFE
        LAYOUT_3_0 = _LAYOUT_MARK | CHANNEL_FRONT_LEFT | CHANNEL_FRONT_RIGHT | CHANNEL_FRONT_CENTER
        LAYOUT_3_1 = LAYOUT_3_0 | CHANNEL_LFE
        LAYOUT_SURROUND_5_0 = LAYOUT_3_0 | CHANNEL_BACK_LEFT | CHANNEL_BACK_RIGHT
        LAYOUT_SURROUND_5_1 = LAYOUT_SURROUND_5_0 | CHANNEL_LFE
        LAYOUT_SURROUND_7_0 = LAYOUT_SURROUND_5_0 | CHANNEL_SIDE_LEFT | CHANNEL_SIDE_RIGHT
        LAYOUT_SURROUND_7_1 = LAYOUT_SURROUND_7_0 | CHANNEL_LFE

        @property
        def channels_num(self) -> int:
            return self.value.bit_count() - bool(self & AudioConstraints.ChannelLayout._LAYOUT_MARK)

        def closest_standard_layout(
            self, constraint: "AudioConstraints.ChannelLayout"
        ) -> "AudioConstraints.ChannelLayout":
            assert AudioConstraints.ChannelLayout._LAYOUT_MARK & constraint

            wanted_layout = (AudioConstraints.ChannelLayout._LAYOUT_MARK | self) & constraint
            standard_layouts = AudioConstraints.ChannelLayout.get_all_standard_layouts()

            # find the wanted layout in standard layouts
            if wanted_layout in standard_layouts:
                return wanted_layout

            # find a standard layout in the wanted layout
            for std_layout in reversed():
                if (std_layout & wanted_layout) == std_layout:
                    return std_layout

            # just use mono if the wanted layout is not recognized
            return AudioConstraints.ChannelLayout.LAYOUT_MONO

        @staticmethod
        def get_all_standard_layouts() -> list["AudioConstraints.ChannelLayout"]:
            return [
                layout
                for layout in AudioConstraints.ChannelLayout.__members__.values()
                if layout & AudioConstraints.ChannelLayout._LAYOUT_MARK
                and layout != AudioConstraints.ChannelLayout._LAYOUT_MARK
            ]

    sample_formats: SampleFormat
    channel_layouts: ChannelLayout
    channels_num_min: int
    channels_num_max: int
    sample_rate_min: int
    sample_rate_max: int

    def is_valid(self) -> bool:
        return (
            bool(self.sample_formats)
            and bool(self.channel_layouts)
            and self.channels_num_min > 0
            and self.channels_num_max >= self.channels_num_min
            and self.sample_rate_min > 0
            and self.sample_rate_min <= self.sample_rate_max
        )


@dataclass
class AudioConfig:
    sample_format: AudioConstraints.SampleFormat
    channel_layout: AudioConstraints.ChannelLayout
    sample_rate: int
    frame_duration: float | None

    @property
    def media_type(self) -> MediaType:
        return MediaType.AUDIO


@dataclass
class VideoConfig:
    class PixelFormat(enum.Enum):
        RGBA8888 = enum.auto()

    pixel_format: PixelFormat
    sample_aspect_ratio: Fraction

    @property
    def media_type(self) -> MediaType:
        return MediaType.VIDEO
