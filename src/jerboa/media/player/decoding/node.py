import av
import enum
import numpy as np
from collections import deque
from collections.abc import Iterable
from typing import Any, Callable, Optional
from abc import ABC, abstractmethod

from jerboa.core.jbmath import Fraction
from jerboa.core.timeline import FragmentedTimeline
from jerboa.media import standardized_audio as std_audio
from jerboa.media.core import MediaType
from .context import DecodingContext, SkipDiscardedFramesSeekTask
from .reformatter import AudioReformatter, VideoReformatter
from .mapper import AudioMapper, VideoMapper
from .frame import (
    TimedAVFrame,
    PreMappedFrame,
    MappedAudioFrame,
    MappedVideoFrame,
    JbAudioFrame,
    JbVideoFrame,
)

DEFAULT_MEAN_KEYFRAME_INTERVAL_SAMPLE_SIZE = 8


class Node(ABC):
    class ResetReason(enum.Enum):
        NEW_CONTEXT = enum.auto()
        HARD_DISCONTINUITY = enum.auto()  # seek
        SOFT_DISCONTINUITY = enum.auto()  # skip

    class Discontinuity(Exception):
        ...

    class DiscontinuitiesLimitExcededError(Exception):
        ...

    def __init__(
        self,
        *,
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

    def find_root_node(self) -> "Node":
        root_node = self.parent
        while root_node.parent is not None:
            root_node = root_node.parent
        return root_node

    def reset(self, context: DecodingContext, reason: ResetReason, *, recursive: bool) -> None:
        if recursive and self.child is not None:
            self.child.reset(context, reason, recursive=recursive)

    def raise_discontinuity(self, context: DecodingContext, *, hard: bool) -> None:
        """Resets this node and its descendants. Resets execution if this node or any of its
        descendants "breaks_on_discontinuity".

        This method introduces side-effects that may lead to unexpected node state of descendant
        nodes when execution eventually returns (from a `parent.pull()` call) to the descendant's
        `pull()` method. In such a case, the execution should be reset, which is signaled by the
        `breaks_on_discontinuity` attribute of a node.
        """
        self.reset(
            context,
            Node.ResetReason.HARD_DISCONTINUITY if hard else Node.ResetReason.SOFT_DISCONTINUITY,
            recursive=True,
        )

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
            except SkipDiscardedFramesSeekTask as skip_task:
                skip_task.execute_and_finish(self._skip, context, skip_task.timepoint)
            except Node.Discontinuity:
                repeats -= 1
        raise Node.DiscontinuitiesLimitExcededError()

    def _skip(self, context: DecodingContext, timepoint: float) -> None:
        context.seek(timepoint)
        self.find_root_node().reset(context, Node.ResetReason.SOFT_DISCONTINUITY, recursive=True)

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

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        self._demuxer = context.media.avc.container.demux(context.media.avc.stream)
        super().reset(context, reason, recursive=recursive)

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

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        self._sample_size = 0
        self._last_keyframe_timepoint = None
        super().reset(context, reason, recursive=recursive)

    def pull(self, context: DecodingContext) -> av.Packet | None:
        packet: av.Packet = self.parent.pull(context)

        if packet is not None and packet.is_keyframe:
            keyframe_timepoint = packet.pts * float(packet.time_base)
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

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        self._decoded_frames.clear()
        super().reset(context, reason, recursive=recursive)

    def pull(self, context: DecodingContext) -> av.AudioFrame | av.VideoFrame | None:
        while True:
            try:
                return self._decoded_frames.popleft()
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

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        self._last_frame_end_pts = None
        if reason == Node.ResetReason.NEW_CONTEXT:
            self._frame_time_base_standardizer = lambda _: None  # do nothing by default

            std_time_base = Fraction(1, context.media.avc.stream.sample_rate)
            frame_time_base_to_std_time_base = (
                Fraction(context.media.avc.stream.time_base) / std_time_base
            )
            if frame_time_base_to_std_time_base != 1:

                def time_base_standardizer(frame: av.AudioFrame):
                    frame.pts = int(frame.pts * frame_time_base_to_std_time_base)
                    frame.time_base = std_time_base

                self._frame_time_base_standardizer = time_base_standardizer

        super().reset(context, reason, recursive=recursive)

    def pull(self, context: DecodingContext) -> av.AudioFrame | None:
        frame = self.parent.pull(context)
        if frame is not None:
            self._frame_time_base_standardizer(frame)

            if self._last_frame_end_pts is not None:
                frame.pts = self._last_frame_end_pts

            self._last_frame_end_pts = frame.pts + frame.samples
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
        return TimedAVFrame(
            av_frame=frame,
            beg_timepoint=frame.time,
            end_timepoint=frame.time + (frame.samples / frame.sample_rate),
        )


class TimedVideoFrameCreationNode(Node):
    def __init__(self, parent: Node | None):
        super().__init__(
            input_types={av.VideoFrame},
            output_types={TimedAVFrame},
            breaks_on_discontinuity=True,
            parent=parent,
        )
        self._frame: av.VideoFrame | None = None

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        self._frame = None
        super().reset(context, reason, recursive=recursive)

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
                end_timepoint=next_frame.time if next_frame is not None else frame.time + 1 / 24,
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

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        self._returned_frame = False
        super().reset(context, reason, recursive=recursive)

    def pull(self, context: DecodingContext) -> TimedAVFrame | None:
        while True:
            frame: TimedAVFrame = self.parent.pull(context)

            if frame is not None and (
                context.min_timepoint - frame.end_timepoint >= context.mean_keyframe_interval
            ):
                if context.last_seek_timepoint != context.min_timepoint:
                    SkipDiscardedFramesSeekTask(context.min_timepoint).run_pending()

                # we cannot get any closer using "seek", so we drop all the frames until we get to
                # the "min_timepoint"

                # we have to signalize when the continuity has been broken
                if self._returned_frame:
                    self.raise_discontinuity(context, hard=False)

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

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        if reason == Node.ResetReason.NEW_CONTEXT:
            self._reformatter = AudioReformatter(context.media.intermediate_config)
        else:
            self._reformatter.reset()
        self._reformatted_frames.clear()
        super().reset(context, reason, recursive=recursive)

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

        self._timeline: FragmentedTimeline | None = None
        self._returned_frame = False

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        self._returned_frame = False
        self._timeline = context.timeline
        super().reset(context, reason, recursive=recursive)

    def pull(self, context: DecodingContext) -> PreMappedFrame | None:
        while True:
            frame: TimedAVFrame = self.parent.pull(context)

            if frame is not None:
                if frame.end_timepoint >= context.min_timepoint:
                    while context.timeline.time_scope < frame.end_timepoint:
                        scope_extended_event = context.timeline.create_scope_extended_event(
                            frame.end_timepoint
                        )
                        context.tasks.add_event_to_abort_on_task_added(scope_extended_event)
                        scope_extended_event.wait()
                        context.tasks.run_all()

                    # note the value of `beg` is `max(beg_timepoint, min_timepoint)`
                    # this assures the mapped frame will start exactly where it should
                    # (according to the timeline/seek)
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
                    self.raise_discontinuity(context, hard=False)

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

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        if reason == Node.ResetReason.NEW_CONTEXT:
            if context.media.intermediate_config.media_type == MediaType.AUDIO:
                self._mapper = AudioMapper(context.media.intermediate_config)
            else:
                self._mapper = VideoMapper()
        elif reason == Node.ResetReason.HARD_DISCONTINUITY:
            self._mapper.reset()
        super().reset(context, reason, recursive=recursive)

    def pull(self, context: DecodingContext) -> MappedAudioFrame | MappedVideoFrame | None:
        while True:
            pre_mapped_frame: PreMappedFrame = self.parent.pull(context)
            mapped_frame = self._mapper.map(pre_mapped_frame)
            if mapped_frame is not None or pre_mapped_frame is None:
                return mapped_frame


class AudioPresentationReformattingNode(Node):
    assert JbAudioFrame == MappedAudioFrame

    def __init__(self, parent: Node | None):
        super().__init__(
            input_types={MappedAudioFrame},
            output_types={JbAudioFrame},
            breaks_on_discontinuity=False,
            parent=parent,
        )
        self._wanted_dtype: np.dtype | None = None

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        assert context.media.intermediate_config.sample_format == std_audio.SAMPLE_FORMAT_JB
        self._wanted_dtype = context.media.presentation_config.sample_format.dtype

        super().reset(context, reason, recursive=recursive)

    def pull(self, context: DecodingContext) -> JbAudioFrame | None:
        frame: MappedAudioFrame = self.parent.pull(context)
        if frame is not None:
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

    def reset(self, context: DecodingContext, reason: Node.ResetReason, *, recursive: bool) -> None:
        if reason == Node.ResetReason.NEW_CONTEXT:
            self._reformatter = VideoReformatter(context.media.presentation_config)
        else:
            self._reformatter.reset()
        super().reset(context, reason, recursive=recursive)

    def pull(self, context: DecodingContext) -> JbVideoFrame | None:
        frame: MappedVideoFrame = self.parent.pull(context)
        if frame is not None:
            return JbVideoFrame(
                beg_timepoint=frame.beg_timepoint,
                end_timepoint=frame.end_timepoint,
                width=frame.av_frame.width,
                height=frame.av_frame.height,
                planes=self._reformatter.reformat(frame.av_frame),
            )
        return None
