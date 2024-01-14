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
    audio_signal: np.ndarray = field(repr=False)


@dataclass
class MappedVideoFrame(TimedFrame):
    av_frame: av.VideoFrame = field(repr=False)


JbAudioFrame = MappedAudioFrame


@dataclass
class JbVideoFrame(TimedFrame):
    width: int
    height: int
    planes: list[np.ndarray[np.ubyte]] = field(repr=False)
