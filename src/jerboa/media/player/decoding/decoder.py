import av
from dataclasses import dataclass, field
from collections import deque
from collections.abc import Iterable
from typing import Any, Callable, Optional
from abc import ABC, abstractmethod
from threading import Lock, Condition
from fractions import Fraction

from jerboa.core.timeline import FragmentedTimeline, TMSection
from jerboa.media.core import MediaType, AudioConfig, VideoConfig, AudioConstraints
from jerboa.media import standardized_audio as std_audio
from jerboa.media import av_to_jb

# from .reformatter import AudioReformatter, VideoReformatter
# from .mapper import TimedFrame, PreMappedFrame, AudioMapper, VideoMapper
# from .buffer import JbAudioFrame, JbVideoFrame, AudioBuffer, VideoBuffer

from jerboa.media.player.decoding.reformatter import AudioReformatter, VideoReformatter
from jerboa.media.player.decoding.mapper import (
    TimedFrame,
    PreMappedFrame,
    AudioMapper,
    VideoMapper,
    create_mapper,
)
from jerboa.media.player.decoding.buffer import JbAudioFrame, JbVideoFrame, AudioBuffer, VideoBuffer

DEFAULT_MEAN_KEYFRAME_INTERVAL_SAMPLE_SIZE = 8
DEFAULT_MEAN_KEYFRAME_INTERVAL = 0.0


@dataclass(frozen=True)
class MediaContext:
    av_container: av.container.InputContainer
    av_stream: av.audio.AudioStream | av.video.VideoStream

    intermediate_config: AudioConfig | VideoConfig
    presentation_config: AudioConfig | VideoConfig


@dataclass
class DecodingContext:
    media: MediaContext

    min_timepoint: float = 0
    current_timepoint: float | None = None
    mean_keyframe_interval: float = DEFAULT_MEAN_KEYFRAME_INTERVAL

    mutex: Lock = field(default_factory=Lock)
    _tasks: deque[Exception] = field(default_factory=deque)
    _conditions_to_notify_on_task_added: dict[Condition, bool] = field(default_factory=dict)

    def add_task(self, task: Exception):
        with self.mutex:
            self._tasks.append(task)
            for condition, notify_all in self._conditions_to_notify_on_task_added.items():
                if notify_all:
                    condition.notify_all()
                else:
                    condition.notify()

    def add_condition_to_notify_on_task_added(
        self, condition: Condition, notify_all: bool = True
    ) -> None:
        assert condition not in self._conditions_to_notify_on_task_added
        self._conditions_to_notify_on_task_added[condition] = notify_all

    def has_task(self) -> bool:
        return len(self._tasks) > 0

    def raise_task_unsafe(self) -> None:
        assert self.mutex.locked()
        raise self._tasks.popleft()


class PipelineNode(ABC):
    class Discontinuity(Exception):
        ...

    class DiscontinuitiesLimitExcededError(Exception):
        ...

    def __init__(
        self,
        input_types: set[type],
        output_types: set[type],
        parent: Optional["PipelineNode"],
    ) -> None:
        super().__init__()

        self._input_types = input_types
        self._output_types = output_types
        self._parent: PipelineNode | None = parent
        self._child: PipelineNode | None = None

        assert type(None) in self._input_types or parent is not None, (
            f"Non-root node ({self}) must have a parent!",
        )
        assert type(None) not in self._input_types or parent is None, (
            f"Root node ({self=}) cannot have a parent ({parent=})!",
        )
        assert parent is None or input_types.issubset(parent._output_types), (
            f"Incompatible connection: {parent._output_types=} vs {input_types=}",
        )

        if self._parent is not None:
            self._parent._child = self

    @property
    def parent(self) -> "PipelineNode":
        return self._parent

    @property
    def child(self) -> "PipelineNode":
        return self._child

    def reset(self, context: DecodingContext, recursive: bool) -> None:
        if recursive and self.child is not None:
            self.child.reset(context, recursive)

    def raise_discontinuity(self):
        self.on_discontinuity()
        if self.child:
            self.child.on_discontinuity()

    def pull_as_leaf(self, context: DecodingContext) -> Any | None:
        assert self.child is None

        repeats = 10
        while repeats > 0:
            try:
                node_output = self.pull(context)
                repeats = 10
                return node_output
            except PipelineNode.Discontinuity:
                repeats -= 1
        raise PipelineNode.DiscontinuitiesLimitExcededError()

    def on_discontinuity(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def pull(self, context: DecodingContext) -> Any | None:
        return self.parent.pull(context)


class DemuxingNode(PipelineNode):
    def __init__(self):
        super().__init__(
            input_types={type(None)},
            output_types={av.Packet},
            parent=None,
        )
        self._demuxer: Iterable[av.Packet] = None

    def reset(self, context: DecodingContext, recursive: bool) -> None:
        self._demuxer = context.media.av_container.demux(context.media.av_stream)
        super().reset(context, recursive)

    def pull(self, _) -> av.Packet:
        try:
            return next(self._demuxer)
        except StopIteration:
            return None


class KeyframeIntervalWatcherNode(PipelineNode):
    def __init__(
        self,
        parent: Optional["PipelineNode"] = None,
        sample_size: int = DEFAULT_MEAN_KEYFRAME_INTERVAL_SAMPLE_SIZE,
    ):
        super().__init__(
            input_types={av.Packet},
            output_types={av.Packet},
            parent=parent,
        )
        self._max_sample_size = sample_size

        self._sample_size: int = 0
        self._last_keyframe_timepoint: float | None = None

    def reset(self, context: DecodingContext, recursive: bool) -> None:
        self._sample_size = 0
        self._last_keyframe_timepoint = None
        super().reset(context, recursive)

    def pull(self, context: DecodingContext) -> av.Packet:
        packet: av.Packet = self.parent.pull(context)

        if packet is not None and packet.is_keyframe:
            keyframe_timepoint = packet.pts * packet.time_base
            if self._last_keyframe_timepoint is not None:
                new_interval = keyframe_timepoint - self._last_keyframe_timepoint
                intervals_sum = (context.mean_keyframe_interval * self._sample_size) + new_interval
                context.mean_keyframe_interval = intervals_sum / (self._sample_size + 1)
                self._sample_size = min(self._max_sample_size, self._sample_size + 1)
            self._last_keyframe_timepoint = keyframe_timepoint

        return packet


class DecodingNode(PipelineNode):
    def __init__(self, parent: Optional["PipelineNode"] = None) -> None:
        super().__init__(
            input_types={av.Packet},
            output_types={av.AudioFrame, av.VideoFrame},
            parent=parent,
        )
        self._decoded_frames: deque[av.AudioFrame] | deque[av.VideoFrame] = deque()

    def reset(self, context: DecodingContext, recursive: bool) -> None:
        self._decoded_frames.clear()
        super().reset(context, recursive)

    def pull(self, context: DecodingContext) -> av.AudioFrame | av.VideoFrame:
        while True:
            try:
                frame = self._decoded_frames.popleft()
                context.current_timepoint = frame.time
                return frame
            except IndexError:
                while len(self._decoded_frames) == 0:
                    packet = self.parent.pull(context)
                    if packet is not None:
                        self._decoded_frames.extend(packet.decode())
                    else:
                        return None


class AudioFrameTimingCorrectionNode(PipelineNode):
    def __init__(self, parent: PipelineNode | None):
        super().__init__(
            input_types={av.AudioFrame},
            output_types={av.AudioFrame},
            parent=parent,
        )
        self._last_frame_end_pts: int | None = None
        self._frame_time_base_standardizer: Callable[[av.AudioFrame], None] | None = None
        self._frame_end_pts_generator: Callable[[av.AudioFrame], float] | None = None

    def reset(self, context: DecodingContext, recursive: bool) -> None:
        self._last_frame_end_pts = None
        self._frame_time_base_standardizer = std_audio.get_frame_time_base_standardizer(
            context.media.av_stream
        )
        self._frame_end_pts_generator = std_audio.get_frame_end_pts_generator(
            context.media.av_stream
        )
        super().reset(context, recursive)

    def pull(self, context: DecodingContext) -> av.AudioFrame | None:
        frame = self.parent.pull(context)
        if frame is not None:
            self._frame_time_base_standardizer(frame)

            if self._last_frame_end_pts is not None:
                frame.pts = self._last_frame_end_pts

            self._last_frame_end_pts = self._frame_end_pts_generator(frame)
            return frame

        return None


class AudioReformattingNode(PipelineNode):
    def __init__(self, parent: Optional["PipelineNode"] = None) -> None:
        super().__init__(
            input_types={av.AudioFrame},
            output_types={av.AudioFrame},
            parent=parent,
        )
        self._reformatter: AudioReformatter | None = None
        self._reformatted_frames = deque[av.AudioFrame]()

    def reset(self, context: DecodingContext, recursive: bool) -> None:
        self._reformatter = AudioReformatter(context.media.intermediate_config)
        self._reformatted_frames.clear()
        super().reset(context, recursive)

    def pull(self, context: DecodingContext) -> av.AudioFrame:
        while True:
            try:
                return self._reformatted_frames.popleft()
            except IndexError:
                while len(self._reformatted_frames) == 0:
                    frame = self.parent.pull(context)
                    self._reformatted_frames.extend(self._reformatter.reformat(frame))
                    if frame is None and len(self._reformatted_frames) == 0:
                        return None


class TimedAudioFrameCreationNode(PipelineNode):
    def __init__(self, parent: PipelineNode | None):
        super().__init__(
            input_types={av.AudioFrame},
            output_types={TimedFrame},
            parent=parent,
        )

    def pull(self, context: DecodingContext) -> TimedFrame | None:
        frame = self.parent.pull(context)

        if frame is not None:
            assert frame.time_base == Fraction(1, frame.sample_rate)

            return TimedFrame(
                av_frame=frame,
                beg_timepoint=frame.time,
                end_timepoint=frame.time + frame.samples * frame.time_base,
            )
        return None


class TimedVideoFrameCreationNode(PipelineNode):
    def __init__(self, parent: PipelineNode | None):
        super().__init__(
            input_types={av.VideoFrame},
            output_types={TimedFrame},
            parent=parent,
        )
        self._frame: av.VideoFrame | None = None
        self._last_frame_duration: float | None = None

    def reset(self, context: DecodingContext, recursive: bool) -> None:
        self._frame = None
        self._last_frame_duration = None
        super().reset(context, recursive)

    def pull(self, context: DecodingContext) -> TimedFrame | None:
        if self._frame is None:
            self._frame = self.parent.pull(context)

        if self._frame is not None:
            frame = self._frame
            next_frame = self.parent.pull(context)

            self._frame = next_frame

            return TimedFrame(
                av_frame=frame,
                beg_timepoint=frame.time,
                end_timepoint=next_frame.time if next_frame is not None else float("inf"),
            )
        return None


class FrameMappingPreparationNode(PipelineNode):
    def __init__(self, parent: PipelineNode | None):
        super().__init__(
            input_types={TimedFrame},
            output_types={PreMappedFrame},
            parent=parent,
        )

        # TODO: maybe reference some global timeline instead?
        # i.e.: timeline.on_changed_signal.connect(self._on_timeline_change)
        # TODO: remove any initial sections, this should be an empty timeline
        self._timeline: FragmentedTimeline = FragmentedTimeline(TMSection(0, float("inf")))
        self._timeline_or_task_updated: Condition | None = None

    def reset(self, context: DecodingContext, recursive: bool) -> None:
        self._timeline = FragmentedTimeline(TMSection(0, float("inf")))
        self._timeline_or_task_updated = Condition(context.mutex)
        context.add_condition_to_notify_on_task_added(self._timeline_or_task_updated)
        return super().reset(context, recursive)

    def pull(self, context: DecodingContext) -> PreMappedFrame | None:
        frame: TimedFrame = self.parent.pull(context)

        if frame is not None:
            with context.mutex:
                self._timeline_or_task_updated.wait_for(
                    lambda: self._timeline.time_scope >= frame.end_timepoint or context.has_task()
                )
                if context.has_task():
                    context.raise_task_unsafe()

            # note that the value of `beg` is `max(frame.beg_timepoint, context.min_timepoint)`
            # this will make it so that the mapped frame will start exactly where it should
            # (according to the timeline)
            mapping_scheme, context.min_timepoint = self._timeline.map_time_range(
                beg=max(frame.beg_timepoint, context.min_timepoint), end=frame.end_timepoint
            )

            return PreMappedFrame(
                timed_frame=frame,
                mapping_scheme=mapping_scheme,
            )
        return None


class FrameMappingNode(PipelineNode):
    def __init__(self, parent: PipelineNode | None):
        super().__init__(
            input_types={PreMappedFrame},
            output_types={JbAudioFrame},
            parent=parent,
        )
        self._mapper: AudioMapper | VideoMapper = None

    def reset(self, context: DecodingContext, recursive: bool) -> None:
        # TODO: maybe introduce a new `clear(recursive)` method, which would only reset the node's
        # state, without re-creating all variables?
        self._mapper = create_mapper(
            intermediate_config=context.media.intermediate_config,
            presentation_config=context.media.presentation_config,
        )
        return super().reset(context, recursive)

    def pull(self, context: DecodingContext) -> PreMappedFrame | None:
        return self._mapper.map(self.parent.pull(context))


class DecodingPipeline:
    def __init__(self, media_type: MediaType, output_node: PipelineNode) -> None:
        self._media_type = media_type

        self._output_node = output_node
        self._root_node = self._output_node
        while self._root_node.parent is not None:
            self._root_node = self._root_node.parent

        self._context: DecodingContext | None = None

    def init(
        self,
        media: MediaContext,
        start_timepoint: float,
    ) -> None:
        assert media.av_container == media.av_stream.container
        assert MediaType(media.av_stream.type) == self._media_type
        assert start_timepoint >= 0

        self._context = DecodingContext(media=media)

        self._seek(start_timepoint)
        self._root_node.reset(self._context, recursive=True)

    def _seek(self, timepoint: float) -> None:
        media = self._context.media
        media.av_container.seek(
            round(timepoint / media.av_stream.time_base), stream=media.av_stream
        )

    def pull(self) -> Any:
        assert self._context is not None, "Cannot run uninitialized pipeline"
        return self._output_node.pull_as_leaf(self._context)


def select_best_audio_presentation_sample_format(
    supported_sample_formats: AudioConstraints.SampleFormat,
) -> AudioConstraints.SampleFormat:
    if std_audio.SAMPLE_FORMAT_JB & supported_sample_formats:
        return std_audio.SAMPLE_FORMAT_JB
    return supported_sample_formats.best_quality()


def select_best_audio_channel_layout(
    av_channel_layout: av.AudioLayout,
    supported_channel_layouts: AudioConstraints.ChannelLayout,
) -> AudioConstraints.SampleFormat:
    jb_channel_layout = av_to_jb.audio_channel_layout(av_channel_layout)
    return jb_channel_layout.closest_standard_layout(constraint=supported_channel_layouts)


def select_best_sample_rate(
    source_sample_rate: int,
    supported_sample_rate_min: int,
    supported_sample_rate_max: int,
) -> int:
    return min(supported_sample_rate_max, max(supported_sample_rate_min, source_sample_rate))


def create_presentation_media_config(
    stream: av.audio.AudioStream | av.video.VideoStream,
    constraints: AudioConstraints,
) -> AudioConfig | VideoConfig:
    if MediaType(stream.type) == MediaType.AUDIO:
        return AudioConfig(
            sample_format=select_best_audio_presentation_sample_format(
                supported_sample_formats=constraints.sample_formats,
            ),
            channel_layout=select_best_audio_channel_layout(
                av_channel_layout=stream.layout,
                supported_channel_layouts=constraints.channel_layouts,
            ),
            sample_rate=select_best_sample_rate(
                source_sample_rate=stream.sample_rate,
                supported_sample_rate_min=constraints.sample_rate_min,
                supported_sample_rate_max=constraints.sample_rate_max,
            ),
        )
    return VideoConfig(pixel_format=VideoConfig.PixelFormat.RGBA8888)


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


def test_case():
    audio_decoder = DecodingPipeline(
        media_type=MediaType.AUDIO,
        output_node=FrameMappingNode(
            parent=FrameMappingPreparationNode(
                parent=TimedAudioFrameCreationNode(
                    parent=AudioReformattingNode(
                        parent=AudioFrameTimingCorrectionNode(
                            parent=DecodingNode(
                                parent=KeyframeIntervalWatcherNode(
                                    parent=DemuxingNode(),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    video_decoder = DecodingPipeline(
        media_type=MediaType.VIDEO,
        output_node=FrameMappingNode(
            parent=FrameMappingPreparationNode(
                parent=TimedVideoFrameCreationNode(
                    parent=DecodingNode(
                        parent=KeyframeIntervalWatcherNode(
                            parent=DemuxingNode(),
                        ),
                    ),
                ),
            ),
        ),
    )

    container = av.open("colors_test.mp4")
    stream = container.streams.video[0]
    presentation_media_config = create_presentation_media_config(
        stream=stream,
        constraints=AudioConstraints(
            sample_formats=AudioConstraints.SampleFormat.S16,
            channel_layouts=AudioConstraints.ChannelLayout.LAYOUT_SURROUND_7_1,
            channels_num_min=1,
            channels_num_max=3,
            sample_rate_min=1,
            sample_rate_max=1e5,
        ),
    )
    intermediate_media_config = create_intermediate_media_config(presentation_media_config)

    # audio_decoder.init(
    #     media=MediaContext(
    #         av_container=container,
    #         av_stream=container.streams.audio[0],
    #         intermediate_config=intermediate_media_config,
    #         presentation_config=presentation_media_config,
    #     ),
    #     start_timepoint=0,
    # )
    video_decoder.init(
        media=MediaContext(
            av_container=container,
            av_stream=container.streams.video[0],
            intermediate_config=intermediate_media_config,
            presentation_config=presentation_media_config,
        ),
        start_timepoint=0,
    )
    while True:
        # out = audio_decoder.pull()
        out = video_decoder.pull()
        print(type(out))
        if out is None:
            break


if __name__ == "__main__":
    test_case()
