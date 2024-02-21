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
from dataclasses import dataclass, field

from jerboa.core.jbmath import Fraction
from jerboa.core.timeline import FragmentedTimeline
from jerboa.media import av_to_jb, standardized_audio as std_audio
from jerboa.media.core import (
    MediaType,
    AudioConfig,
    VideoConfig,
    AudioSampleFormat,
    AudioConstraints,
    AudioChannelLayout,
    VIDEO_FRAME_PIXEL_FORMAT,
)
from jerboa.core.multithreading import Task, TaskQueue

DEFAULT_MEAN_KEYFRAME_INTERVAL = 0.25


@dataclass(frozen=True)
class AVContext:
    container: av.container.InputContainer
    stream: av.audio.AudioStream | av.video.VideoStream

    def __post_init__(self):
        assert self.stream.container is self.container

    @property
    def start_timepoint(self) -> float:
        return max(0, (self.stream.start_time or 0) * self.stream.time_base)

    def close(self) -> None:
        self.container.close()

    @staticmethod
    def open(
        filepath: str,
        media_type: MediaType,
        stream_idx: int,
    ) -> "AVContext":
        assert media_type in [MediaType.AUDIO, MediaType.VIDEO]

        container = av.open(
            f"{filepath}",
            # f"cache:{filepath}",  # TODO: use cache protocol only for remote files
            # timeout=(None, 0.5),
        )
        # container.flags |= av.container.core.Flags.NONBLOCK
        if media_type == MediaType.AUDIO:
            stream = container.streams.audio[stream_idx]
        else:
            stream = container.streams.video[stream_idx]
        stream.thread_type = "AUTO"

        return AVContext(container, stream)


@dataclass(frozen=True)
class MediaContext:
    avc: AVContext
    intermediate_config: AudioConfig | VideoConfig
    presentation_config: AudioConfig | VideoConfig

    @staticmethod
    def open(
        filepath: str,
        media_type: MediaType,
        stream_idx: int,
        media_constraints: AudioConstraints | None,
    ) -> "MediaContext":
        avc = AVContext.open(filepath=filepath, media_type=media_type, stream_idx=stream_idx)
        presentation_config = MediaContext.create_presentation_media_config(
            stream=avc.stream,
            constraints=media_constraints,
        )
        intermediate_config = MediaContext.create_intermediate_media_config(presentation_config)

        return MediaContext(
            avc=avc,
            presentation_config=presentation_config,
            intermediate_config=intermediate_config,
        )

    @staticmethod
    def create_intermediate_media_config(
        presentation_media_config: AudioConfig | VideoConfig,
    ) -> AudioConfig | VideoConfig:
        if presentation_media_config.media_type == MediaType.AUDIO:
            return AudioConfig(
                sample_format=std_audio.SAMPLE_FORMAT_JB,
                channel_layout=presentation_media_config.channel_layout,
                sample_rate=presentation_media_config.sample_rate,
                frame_duration=presentation_media_config.frame_duration or std_audio.FRAME_DURATION,
            )
        return presentation_media_config  # no changes for video config

    @staticmethod
    def create_presentation_media_config(
        stream: av.audio.AudioStream | av.video.VideoStream,
        constraints: AudioConstraints,
    ) -> AudioConfig | VideoConfig:
        if MediaType(stream.type) == MediaType.AUDIO:
            return AudioConfig(
                sample_format=MediaContext._select_best_audio_presentation_sample_format(
                    supported_sample_formats=constraints.sample_formats,
                ),
                channel_layout=MediaContext._select_best_audio_channel_layout(
                    av_channel_layout=stream.layout,
                    supported_channel_layouts=constraints.channel_layouts,
                ),
                sample_rate=MediaContext._select_best_sample_rate(
                    source_sample_rate=stream.sample_rate,
                    supported_sample_rate_min=constraints.sample_rate_min,
                    supported_sample_rate_max=constraints.sample_rate_max,
                ),
                frame_duration=None,
            )
        return VideoConfig(
            pixel_format=VIDEO_FRAME_PIXEL_FORMAT,
            sample_aspect_ratio=stream.sample_aspect_ratio or Fraction(1, 1),
        )

    @staticmethod
    def _select_best_audio_presentation_sample_format(
        supported_sample_formats: list[AudioSampleFormat],
    ) -> AudioSampleFormat:
        if std_audio.SAMPLE_FORMAT_JB in supported_sample_formats:
            return std_audio.SAMPLE_FORMAT_JB
        return supported_sample_formats[-1]  # last == best quality

    @staticmethod
    def _select_best_audio_channel_layout(
        av_channel_layout: av.AudioLayout,
        supported_channel_layouts: AudioChannelLayout,
    ) -> AudioChannelLayout:
        jb_channel_layout = av_to_jb.audio_channel_layout(av_channel_layout)
        return jb_channel_layout.closest_standard_layout(constraint=supported_channel_layouts)

    @staticmethod
    def _select_best_sample_rate(
        source_sample_rate: int,
        supported_sample_rate_min: int,
        supported_sample_rate_max: int,
    ) -> int:
        return min(supported_sample_rate_max, max(supported_sample_rate_min, source_sample_rate))


@dataclass
class DecodingContext:
    media: MediaContext
    timeline: FragmentedTimeline

    tasks: TaskQueue = field(default_factory=TaskQueue)

    last_seek_timepoint: float | None = field(default=None, init=False)
    min_timepoint: float = field(default=0, init=False)
    mean_keyframe_interval: float = field(default=DEFAULT_MEAN_KEYFRAME_INTERVAL, init=False)

    def seek(self, timepoint: float) -> None:
        assert timepoint >= 0

        self.media.avc.container.seek(round(timepoint * av.time_base))
        self.last_seek_timepoint = timepoint
        self.min_timepoint = timepoint

    def close(self):
        self.media.avc.close()


@dataclass(frozen=True)
class SkipDiscardedFramesSeekTask(Task):
    timepoint: float
