# Jerboa - AI-powered media player
# Copyright (C) 2023 Paweł Głomski

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


import enum
import numpy as np
from dataclasses import dataclass
from fractions import Fraction


class MediaType(enum.Enum):
    AUDIO = "audio"
    VIDEO = "video"


@dataclass(frozen=True)
class AudioSampleFormat:
    class DataType(enum.Enum):
        NONE = 0
        U8 = enum.auto()
        S16 = enum.auto()
        S32 = enum.auto()
        F32 = enum.auto()

        @property
        def dtype(self) -> np.dtype:
            match self:
                case AudioSampleFormat.DataType.U8:
                    return np.dtype(np.uint8)
                case AudioSampleFormat.DataType.S16:
                    return np.dtype(np.int16)
                case AudioSampleFormat.DataType.S32:
                    return np.dtype(np.int32)
                case AudioSampleFormat.DataType.F32:
                    return np.dtype(np.float32)
                case _:
                    raise ValueError(f"Unrecognized sample format: {self}")

    data_type: DataType
    is_planar: bool

    @property
    def is_packed(self) -> bool:
        return not self.is_planar

    @property
    def dtype(self) -> np.dtype:
        return self.data_type.dtype

    def planar(self) -> "AudioSampleFormat":
        return AudioSampleFormat(data_type=self.data_type, is_planar=True)

    def packed(self) -> "AudioSampleFormat":
        return AudioSampleFormat(data_type=self.data_type, is_planar=False)


class AudioChannelLayout(enum.Flag):
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
        return self.value.bit_count() - bool(self & AudioChannelLayout._LAYOUT_MARK)

    def closest_standard_layout(self, constraint: "AudioChannelLayout") -> "AudioChannelLayout":
        assert AudioChannelLayout._LAYOUT_MARK & constraint

        wanted_layout = (AudioChannelLayout._LAYOUT_MARK | self) & constraint
        standard_layouts = AudioChannelLayout.get_all_standard_layouts()

        # find the wanted layout in standard layouts
        if wanted_layout in standard_layouts:
            return wanted_layout

        # find a standard layout in the wanted layout
        for std_layout in reversed(standard_layouts):
            if (std_layout & wanted_layout) == std_layout:
                return std_layout

        # use mono if the wanted layout is not recognized
        return AudioChannelLayout.LAYOUT_MONO

    @staticmethod
    def get_all_standard_layouts() -> list["AudioChannelLayout"]:
        return [
            layout
            for layout in AudioChannelLayout.__members__.values()
            if layout & AudioChannelLayout._LAYOUT_MARK
            and layout != AudioChannelLayout._LAYOUT_MARK
        ]


@dataclass
class AudioConstraints:
    sample_formats: list[AudioSampleFormat]
    channel_layouts: AudioChannelLayout
    channels_num_min: int
    channels_num_max: int
    sample_rate_min: int
    sample_rate_max: int

    def __post_init__(self):
        super().__setattr__(
            "sample_formats",
            sorted(
                self.sample_formats,
                key=lambda sample_format: (sample_format.data_type.value, sample_format.is_planar),
            ),
        )

    def is_valid(self) -> bool:
        return (
            len(self.sample_formats) > 0
            and bool(self.channel_layouts)
            and self.channels_num_min > 0
            and self.channels_num_max >= self.channels_num_min
            and self.sample_rate_min > 0
            and self.sample_rate_min <= self.sample_rate_max
        )


@dataclass
class AudioConfig:
    sample_format: AudioSampleFormat
    channel_layout: AudioChannelLayout
    sample_rate: int
    frame_duration: float | None

    @property
    def media_type(self) -> MediaType:
        return MediaType.AUDIO

    @property
    def channels_num(self) -> int:
        return self.channel_layout.channels_num

    @property
    def bytes_per_sample(self) -> int:
        return self.channels_num * self.sample_format.dtype.itemsize


@dataclass
class VideoConfig:
    class PixelFormat(enum.Enum):
        RGBA8888 = enum.auto()

    pixel_format: PixelFormat
    sample_aspect_ratio: Fraction = Fraction(1, 1)

    @property
    def media_type(self) -> MediaType:
        return MediaType.VIDEO


VIDEO_FRAME_PIXEL_FORMAT = VideoConfig.PixelFormat.RGBA8888
