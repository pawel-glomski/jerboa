import av
import numpy as np
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
from jerboa.media import av_to_jb, jb_to_av

# from .reformatter import AudioReformatter, VideoReformatter
# from .mapper import TimedAVFrame, PreMappedFrame, AudioMapper, VideoMapper
# from .buffer import JbAudioFrame, JbVideoFrame, AudioBuffer, VideoBuffer

from jerboa.media.player.decoding.reformatter import AudioReformatter, VideoReformatter
from jerboa.media.player.decoding.mapper import AudioMapper, VideoMapper
from jerboa.media.player.decoding.frame import (
    TimedAVFrame,
    PreMappedFrame,
    MappedAudioFrame,
    MappedVideoFrame,
)
from jerboa.media.player.decoding.buffer import JbAudioFrame, JbVideoFrame

DEFAULT_MEAN_KEYFRAME_INTERVAL_SAMPLE_SIZE = 8
DEFAULT_MEAN_KEYFRAME_INTERVAL = 0.25


@dataclass
class SeekTask(Exception):
    timepoint: float


@dataclass(frozen=True)
class MediaContext:
    av_container: av.container.InputContainer
    av_stream: av.audio.AudioStream | av.video.VideoStream

    intermediate_config: AudioConfig | VideoConfig
    presentation_config: AudioConfig | VideoConfig


@dataclass
class DecodingContext:
    media: MediaContext

    last_seek_timepoint: float | None = None
    min_timepoint: float = 0
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


class Node(ABC):
    class Discontinuity(Exception):
        ...

    class DiscontinuitiesLimitExcededError(Exception):
        ...

    def __init__(
        self,
        input_types: set[type],
        output_types: set[type],
        breaks_on_discontinuity: bool,
        parent: Optional["Node"],
    ) -> None:
        super().__init__()

        self._input_types = input_types
        self._output_types = output_types
        self._breaks_on_discontinuity = breaks_on_discontinuity
        self._parent: Node | None = parent
        self._child: Node | None = None

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
    def breaks_on_discontinuity(self) -> bool:
        """
        Returns:
            Whether the execution should be reset on discontinuity.
        """
        return self._breaks_on_discontinuity

    @property
    def parent(self) -> "Node":
        return self._parent

    @property
    def child(self) -> "Node":
        return self._child

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        if recursive and self.child is not None:
            self.child.reset(context, hard, recursive)

    def raise_discontinuity(self, context: DecodingContext) -> None:
        """Soft-resets this node and its descendants. Resets execution if this node or any of its
        descendants "breaks_on_discontinuity".

        This method introduces side-effects that may lead to unexpected node state of descendant
        nodes when execution eventually returns (from a `parent.pull()` call) to the descendant's
        `pull()` method. In such a case, the execution should be reset, which is signaled by the
        `breaks_on_discontinuity` property.

        """
        self.reset(context, hard=False, recursive=True)

        node = self
        while node is not None:
            if node.breaks_on_discontinuity:
                raise Node.Discontinuity()
            node = node.child

    def pull_as_leaf(self, context: DecodingContext) -> Any | None:
        assert self.child is None

        repeats = 10
        while repeats > 0:
            try:
                node_output = self.pull(context)
                repeats = 10
                return node_output
            except Node.Discontinuity:
                repeats -= 1
        raise Node.DiscontinuitiesLimitExcededError()

    @abstractmethod
    def pull(self, context: DecodingContext) -> Any | None:
        return self.parent.pull(context)


class DemuxingNode(Node):
    def __init__(self):
        super().__init__(
            input_types={type(None)},
            output_types={av.Packet},
            breaks_on_discontinuity=False,
            parent=None,
        )
        self._demuxer: Iterable[av.Packet] = None

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        self._demuxer = context.media.av_container.demux(context.media.av_stream)
        super().reset(context, hard, recursive)

    def pull(self, _) -> av.Packet | None:
        try:
            return next(self._demuxer)
        except StopIteration:
            return None


class KeyframeIntervalWatcherNode(Node):
    def __init__(
        self,
        parent: Optional["Node"] = None,
        sample_size: int = DEFAULT_MEAN_KEYFRAME_INTERVAL_SAMPLE_SIZE,
    ):
        super().__init__(
            input_types={av.Packet},
            output_types={av.Packet},
            breaks_on_discontinuity=False,
            parent=parent,
        )
        self._max_sample_size = sample_size

        self._sample_size: int = 0
        self._last_keyframe_timepoint: float | None = None

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        self._sample_size = 0
        self._last_keyframe_timepoint = None
        super().reset(context, hard, recursive)

    def pull(self, context: DecodingContext) -> av.Packet | None:
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


class DecodingNode(Node):
    def __init__(self, parent: Optional["Node"] = None) -> None:
        super().__init__(
            input_types={av.Packet},
            output_types={av.AudioFrame, av.VideoFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )
        self._decoded_frames: deque[av.AudioFrame] | deque[av.VideoFrame] = deque()

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        self._decoded_frames.clear()
        super().reset(context, hard, recursive)

    def pull(self, context: DecodingContext) -> av.AudioFrame | av.VideoFrame | None:
        while True:
            try:
                frame = self._decoded_frames.popleft()
                return frame
            except IndexError:
                while len(self._decoded_frames) == 0:
                    packet = self.parent.pull(context)
                    if packet is not None:
                        self._decoded_frames.extend(packet.decode())
                    else:
                        return None


class AudioFrameTimingCorrectionNode(Node):
    def __init__(self, parent: Node | None):
        super().__init__(
            input_types={av.AudioFrame},
            output_types={av.AudioFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )
        self._last_frame_end_pts: int | None = None
        self._frame_time_base_standardizer: Callable[[av.AudioFrame], None] | None = None
        self._frame_end_pts_generator: Callable[[av.AudioFrame], float] | None = None

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        self._last_frame_end_pts = None
        if hard:
            self._frame_time_base_standardizer = std_audio.get_frame_time_base_standardizer(
                context.media.av_stream
            )
            self._frame_end_pts_generator = std_audio.get_frame_end_pts_generator(
                context.media.av_stream
            )
        super().reset(context, hard, recursive)

    def pull(self, context: DecodingContext) -> av.AudioFrame | None:
        frame = self.parent.pull(context)
        if frame is not None:
            self._frame_time_base_standardizer(frame)

            if self._last_frame_end_pts is not None:
                frame.pts = self._last_frame_end_pts

            self._last_frame_end_pts = self._frame_end_pts_generator(frame)
            return frame

        return None


class TimedAudioFrameCreationNode(Node):
    def __init__(self, parent: Node | None):
        super().__init__(
            input_types={av.AudioFrame},
            output_types={TimedAVFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )

    def pull(self, context: DecodingContext) -> TimedAVFrame | None:
        frame = self.parent.pull(context)

        if frame is not None:
            return TimedAudioFrameCreationNode.timed_frame_from_av_frame(frame)
        return None

    @staticmethod
    def timed_frame_from_av_frame(frame: av.AudioFrame) -> TimedAVFrame:
        assert frame.time_base == Fraction(1, frame.sample_rate)
        return TimedAVFrame(
            av_frame=frame,
            beg_timepoint=frame.time,
            end_timepoint=frame.time + (frame.samples * frame.time_base),
        )


class TimedVideoFrameCreationNode(Node):
    def __init__(self, parent: Node | None):
        super().__init__(
            input_types={av.VideoFrame},
            output_types={TimedAVFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )
        self._frame: av.VideoFrame | None = None
        self._last_frame_duration: float | None = None

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        self._frame = None
        self._last_frame_duration = None
        super().reset(context, hard, recursive)

    def pull(self, context: DecodingContext) -> TimedAVFrame | None:
        if self._frame is None:
            self._frame = self.parent.pull(context)

        if self._frame is not None:
            frame = self._frame
            next_frame = self.parent.pull(context)

            self._frame = next_frame

            return TimedAVFrame(
                av_frame=frame,
                beg_timepoint=frame.time,
                end_timepoint=next_frame.time if next_frame is not None else float("inf"),
            )
        return None


class AccurateSeekNode(Node):
    def __init__(self, parent: Node | None):
        super().__init__(
            input_types={TimedAVFrame},
            output_types={TimedAVFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )
        self._returned_frame = False

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        self._returned_frame = False
        super().reset(context, hard, recursive)

    def pull(self, context: DecodingContext) -> TimedAVFrame | None:
        while True:
            frame: TimedAVFrame = self.parent.pull(context)

            if frame is not None and (
                context.min_timepoint - frame.end_timepoint >= context.mean_keyframe_interval
            ):
                if context.last_seek_timepoint != context.min_timepoint:
                    raise SeekTask(timepoint=context.min_timepoint)

                # we cannot get any closer using "seek", so we drop all the frames until we get to
                # the "min_timepoint"

                # we have to signalize when the continuity has been broken
                if self._returned_frame:
                    self.raise_discontinuity(context)

                continue  # drop the frame

            self._returned_frame = frame is not None
            return frame


class AudioIntermediateReformattingNode(Node):
    def __init__(self, parent: Optional["Node"] = None) -> None:
        super().__init__(
            input_types={TimedAVFrame},
            output_types={TimedAVFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )
        self._reformatter: AudioReformatter | None = None
        self._reformatted_frames = deque[av.AudioFrame]()

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        if hard:
            self._reformatter = AudioReformatter(context.media.intermediate_config)
        else:
            self._reformatter.reset()
        self._reformatted_frames.clear()
        super().reset(context, hard, recursive)

    def pull(self, context: DecodingContext) -> av.AudioFrame | None:
        while True:
            try:
                return TimedAudioFrameCreationNode.timed_frame_from_av_frame(
                    self._reformatted_frames.popleft()
                )
            except IndexError:
                while len(self._reformatted_frames) == 0:
                    frame: TimedAVFrame = self.parent.pull(context)
                    self._reformatted_frames.extend(
                        self._reformatter.reformat(frame.av_frame if frame else None)
                    )
                    if frame is None and len(self._reformatted_frames) == 0:
                        return None


class FrameMappingPreparationNode(Node):
    def __init__(self, parent: Node | None):
        super().__init__(
            input_types={TimedAVFrame},
            output_types={PreMappedFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )

        # TODO: maybe reference some global timeline instead?
        # i.e.: timeline.on_changed_signal.connect(self._on_timeline_change)
        # TODO: remove any initial sections, this should be an empty timeline
        self._timeline: FragmentedTimeline = FragmentedTimeline(
            TMSection(0, 0.5), TMSection(1.5, float("inf"), 0.25)
        )
        self._timeline_or_task_updated: Condition | None = None
        self._returned_frame = False

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        self._returned_frame = False
        if hard:
            # self._timeline = FragmentedTimeline() TODO: uncomment this
            self._timeline_or_task_updated = Condition(context.mutex)
            context.add_condition_to_notify_on_task_added(self._timeline_or_task_updated)
        return super().reset(context, hard, recursive)

    def pull(self, context: DecodingContext) -> PreMappedFrame | None:
        while True:
            frame: TimedAVFrame = self.parent.pull(context)

            if frame is not None:
                with context.mutex:
                    self._timeline_or_task_updated.wait_for(
                        lambda: self._timeline.time_scope >= frame.end_timepoint
                        or context.has_task()
                    )
                    if context.has_task():
                        context.raise_task_unsafe()

                if frame.end_timepoint >= context.min_timepoint:
                    # note that the value of `beg` is `max(beg_timepoint, min_timepoint)`
                    # this assures the mapped frame will start exactly where it should
                    # (according to the timeline)
                    mapping_scheme, context.min_timepoint = self._timeline.map_time_range(
                        beg=max(frame.beg_timepoint, context.min_timepoint),
                        end=frame.end_timepoint,
                    )

                    if mapping_scheme.beg < mapping_scheme.end:
                        self._returned_frame = True
                        return PreMappedFrame(
                            **vars(frame),
                            mapping_scheme=mapping_scheme,
                        )

                # dropping a frame
                if self._returned_frame:
                    self.raise_discontinuity(context)

                continue  # try next frame
            return None  # no more frames


class FrameMappingNode(Node):
    def __init__(self, parent: Node | None):
        super().__init__(
            input_types={PreMappedFrame},
            output_types={MappedAudioFrame, MappedVideoFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )
        self._mapper: AudioMapper | VideoMapper = None

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        if hard:
            if context.media.intermediate_config.media_type == MediaType.AUDIO:
                self._mapper = AudioMapper(context.media.intermediate_config)
            else:
                self._mapper = VideoMapper()
        else:
            self._mapper.reset()
        return super().reset(context, hard, recursive)

    def pull(self, context: DecodingContext) -> MappedAudioFrame | MappedVideoFrame | None:
        return self._mapper.map(self.parent.pull(context))


class AudioPresentationReformattingNode(Node):
    def __init__(self, parent: Node | None):
        super().__init__(
            input_types={MappedAudioFrame},
            output_types={JbAudioFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )
        self._wanted_dtype: np.dtype | None = None

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        assert context.media.intermediate_config.sample_format == std_audio.SAMPLE_FORMAT_JB
        self._wanted_dtype = jb_to_av.audio_sample_format_dtype(
            context.media.presentation_config.sample_format
        )
        return super().reset(context, hard, recursive)

    def pull(self, context: DecodingContext) -> JbAudioFrame | None:
        frame: MappedAudioFrame = self.parent.pull(context)
        if frame is not None:
            assert JbAudioFrame == MappedAudioFrame

            frame.audio_signal = std_audio.reformat(
                frame.audio_signal,
                wanted_dtype=self._wanted_dtype,
                packed=context.media.presentation_config.sample_format.is_packed,
            )
        return frame


class VideoPresentationReformattingNode(Node):
    def __init__(self, parent: Optional["Node"] = None) -> None:
        super().__init__(
            input_types={MappedVideoFrame},
            output_types={JbVideoFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )
        self._reformatter: VideoReformatter | None = None

    def reset(self, context: DecodingContext, hard: bool, recursive: bool) -> None:
        if hard:
            self._reformatter = VideoReformatter(context.media.presentation_config)
        else:
            self._reformatter.reset()
        super().reset(context, hard, recursive)

    def pull(self, context: DecodingContext) -> JbVideoFrame | None:
        frame: MappedVideoFrame = self.parent.pull(context)
        if frame is not None:
            reformatted_av_frame = self._reformatter.reformat(frame.av_frame)
            return JbVideoFrame(
                beg_timepoint=frame.beg_timepoint,
                end_timepoint=frame.end_timepoint,
                width=reformatted_av_frame.width,
                height=reformatted_av_frame.height,
                planes=[bytes(plane) for plane in reformatted_av_frame.planes],
            )
        return None


class Pipeline:
    def __init__(self, media_type: MediaType, output_node: Node) -> None:
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
        self._root_node.reset(self._context, hard=True, recursive=True)

        self._seek(start_timepoint)

    def _seek(self, timepoint: float) -> None:
        self._context.media.av_container.seek(
            round(timepoint / self._context.media.av_stream.time_base),
            stream=self._context.media.av_stream,
        )
        self._context.last_seek_timepoint = timepoint
        self._context.min_timepoint = timepoint
        self._root_node.reset(self._context, hard=False, recursive=True)

    def pull(self) -> JbAudioFrame | JbVideoFrame:
        assert self._context is not None, "Cannot run uninitialized pipeline"
        while True:
            try:
                return self._output_node.pull_as_leaf(self._context)
            except SeekTask as seek_task:
                self._seek(seek_task.timepoint)


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
            frame_duration=None,
        )
    return VideoConfig(
        pixel_format=VideoConfig.PixelFormat.RGBA8888,
        sample_aspect_ratio=stream.sample_aspect_ratio or Fraction(1, 1),
    )


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
    decoder = Pipeline(
        media_type=MediaType.AUDIO,
        output_node=AudioPresentationReformattingNode(
            parent=FrameMappingNode(
                parent=FrameMappingPreparationNode(
                    parent=AudioIntermediateReformattingNode(
                        parent=AccurateSeekNode(
                            parent=TimedAudioFrameCreationNode(
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
            ),
        ),
    )
    decoder = Pipeline(
        media_type=MediaType.VIDEO,
        output_node=VideoPresentationReformattingNode(
            parent=FrameMappingNode(
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

    decoder.init(
        media=MediaContext(
            av_container=container,
            av_stream=stream,
            intermediate_config=intermediate_media_config,
            presentation_config=presentation_media_config,
        ),
        start_timepoint=0,
    )
    import time

    last_time = time.time_ns()
    while True:
        out = decoder.pull()
        if out is not None:
            latency = (time.time_ns() - last_time) / 1e9
            footage_duration = out.end_timepoint - out.beg_timepoint
            print(f"{latency=}, {footage_duration=}, {footage_duration/latency=}")
            last_time = time.time_ns()

        if out is not None:
            ...
            # print(f"{out.beg_timepoint}, {out.end_timepoint}")
        else:
            decoder._seek(0)


if __name__ == "__main__":
    test_case()
