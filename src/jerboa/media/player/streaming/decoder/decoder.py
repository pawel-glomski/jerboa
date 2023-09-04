from collections.abc import Iterable

import av
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from jerboa.media import MediaType, std_audio

# TODO: zrobić push architecture
# audio processing pipeline:
# frame_timing_repair --> timed_frame_creator --> mapper_reformat --> mapper --> dst_reformat -> sink
#                                                                       |
#                                                                       v
#                                                                raise SeekRequest

# video processing pipeline:
# timed_frame_creator -> mapper -> dst_reformat -> sink
#                          |
#                          v
#                   raise SeekRequest

SupportedStreamType = av.audio.AudioStream | av.video.VideoStream
SupportedFrameType = av.AudioFrame | av.VideoFrame


@dataclass
class TimedFrame:
    av_frame: SupportedFrameType
    beg_timepoint: float
    end_timepoint: float


class JerboaFrame(TimedFrame):
    skip_aware_beg_timepoint: float


class StreamDemuxer:
    def __init__(self, stream: SupportedStreamType) -> None:
        self._stream = stream
        self._container = stream.container

    @property
    def stream(self) -> SupportedStreamType:
        return self._stream

    def pull(self, start_timepoint: float):
        while True:
            self._container.seek(
                round(max(0, start_timepoint) / self.stream.time_base), stream=self.stream
            )
            for packet in self._container.demux(self.stream):
                start_timepoint = yield packet
                if start_timepoint is not None:
                    break  # seek
            else:
                break  # finish


class StreamDemuxer:
    def __init__(self, filepath: str, stream_idx: int):
        self._container = av.open(filepath)
        self._stream = self._get_stream_for_demuxing(stream_idx)
        self._is_infinite = True

    def __del__(self):
        self._container.close()

    def _get_stream_for_demuxing(self, stream_idx: int) -> None:
        try:
            stream = self._container.streams[stream_idx]
        except IndexError as exc:
            raise IndexError(
                f"Wrong stream index! Tried to decode #{stream_idx} stream, while the source "
                f'"{self._container.name}" has {len(self._container.streams)} streams'
            ) from exc

        if not isinstance(stream, (av.audio.AudioStream, av.video.VideoStream)):
            raise TypeError(f'Media type "{stream.type}" is not supported')

        stream.thread_type = "AUTO"

        return stream

    def pull(self, start_timepoint: float):
        keep_going = True
        while keep_going:
            self._container.seek(
                round(max(0, start_timepoint) / self.stream.time_base), stream=self.stream
            )
            for packet in self._container.demux(self.stream):
                start_timepoint = yield packet
                if start_timepoint is not None:
                    break
            else:
                keep_going = self._is_infinite


class Container:
    def __init__(self, filepath: str):
        self._container = av.open(filepath)
        self._stream_demuxer = None

    def __del__(self):
        self._container.close()

    def _get_stream_for_demuxing(self, stream_idx: int) -> None:
        try:
            stream = self._container.streams[stream_idx]
        except IndexError as exc:
            raise IndexError(
                f"Wrong stream index! Tried to decode #{stream_idx} stream, while the source "
                f'"{self._container.name}" has {len(self._container.streams)} streams'
            ) from exc

        if not isinstance(stream, (av.audio.AudioStream, av.video.VideoStream)):
            raise TypeError(f'Media type "{stream.type}" is not supported')

        stream.thread_type = "AUTO"

        return stream

    def create_demuxer(self, stream_idx: int, start_timepoint: float) -> StreamDemuxer:
        # if self._stream_demuxer
        stream = self._get_stream_for_demuxing(stream_idx)
        self._stream_demuxer = StreamDemuxer


ParentBaseT = TypeVar("ParentBaseT")


class PipelineNode(ABC, Generic[ParentBaseT]):
    def __init__(self, parent: ParentBaseT, **_) -> None:
        compatible_parent_base = get_args(type(self))[0]
        if not isinstance(parent, compatible_parent_base):
            raise TypeError(
                f'Parent type "{type(parent)}" is incompatible! '
                f"Parent must be a subclass of: {compatible_parent_base}"
            )
        self._parent = parent

    @property
    def parent(self) -> ParentBaseT:
        return self._parent

    @abstractmethod
    def pull(self) -> Iterable:
        raise NotImplementedError()

    def reset(self) -> None:
        pass


class FirstPipelineNode(PipelineNode[None]):
    @abstractmethod
    def __init__(self, stream: SupportedStreamType) -> None:
        super().__init__(None)
        self._stream = stream

    @property
    def stream(self) -> SupportedStreamType:
        return self._stream


class LastPipelineNode(PipelineNode):
    @abstractmethod
    def pull(self) -> Iterable[JerboaFrame]:
        raise NotImplementedError()


class DecodingPipeline:
    def __init__(
        self,
        stream: SupportedStreamType,
        first_node_type: type[FirstPipelineNode],
        itermediate_node_types: list[type[PipelineNode]],
        last_node_type: type[LastPipelineNode],
    ) -> None:
        self._stream = stream
        self._nodes = [first_node_type(stream=stream)]
        for node_type in itermediate_node_types:
            self._nodes.append(node_type(parent=self._nodes[-1], stream=stream))
        self._nodes.append(last_node_type(parent=self._nodes[-1], stream=stream))

    def decode(self, start_timepoint: float) -> Iterable[JerboaFrame]:
        self.stream.container.seek(
            round(max(0, start_timepoint) / self.stream.time_base), stream=self.stream
        )

        for node in self._nodes:
            node.reset()

        last_node: LastPipelineNode = self._nodes[-1]
        for frame in last_node.pull():
            yield frame


class AVPacketReturningNode(ABC):
    @abstractmethod
    def pull(self) -> Iterable[av.Packet]:
        raise NotImplementedError()


class DemuxerNode(FirstPipelineNode, AVPacketReturningNode):
    def __init__(self, stream: SupportedStreamType) -> None:
        if not isinstance(stream, av.audio.AudioStream, av.video.VideoStream):
            raise TypeError(f"Unsupported stream type: {type(stream)}")
        super().__init__(stream)

    def pull(self) -> Iterable[av.Packet]:
        for packet in self.stream.container.demux():
            yield packet


class AVFrameReturningNode(ABC):
    @abstractmethod
    def pull(self) -> Iterable[SupportedFrameType | None]:
        raise NotImplementedError()


class AVDecoderNode(PipelineNode[AVPacketReturningNode], AVFrameReturningNode):
    def __init__(self, parent: AVPacketReturningNode, **kwargs) -> None:
        super().__init__(parent, **kwargs)

    def pull(self) -> Iterable[SupportedFrameType | None]:
        for packet in self.parent.pull():
            for frame in packet.decode():
                yield frame


class AudioTimeBaseStandardizerNode(PipelineNode[AVFrameReturningNode], AVFrameReturningNode):
    def __init__(
        self,
        parent: AVFrameReturningNode,
        stream: SupportedStreamType,
        **kwargs,
    ) -> None:
        if MediaType(stream.type) != MediaType.AUDIO:
            raise ValueError("This node supports only audio streams")
        super().__init__(parent, **kwargs)
        self._time_base_standardizer = std_audio.get_frame_time_base_standardizer(stream)

    def pull(self) -> Iterable[SupportedFrameType | None]:
        for frame in self.parent.pull():
            if frame is not None:
                self._time_base_standardizer(frame)
            yield frame


class AudioPTSCorrectorNode(PipelineNode[AVFrameReturningNode], AVFrameReturningNode):
    def __init__(
        self,
        parent: AVFrameReturningNode,
        stream: SupportedStreamType,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.next_pts_generator = std_audio.get_end_pts_generator(stream)

    def pull(self) -> Iterable[SupportedFrameType | None]:
        next_frame_pts = None
        for frame in self.parent.pull():
            if frame is not None:
                if next_frame_pts is not None:
                    frame.pts = next_frame_pts
                next_frame_pts = self.next_pts_generator(frame)
            yield frame


class TimedFrameReturningNode:
    @abstractmethod
    def pull(self) -> Iterable[TimedFrame]:
        raise NotImplementedError()


class TimedFrameCreatorNode(PipelineNode[AVFrameReturningNode], TimedFrameReturningNode):
    def pull(self) -> Iterable[TimedFrame]:
        current_frame: SupportedFrameType | None = None
        for next_frame in self.parent.pull():
            if current_frame is not None:
                current_frame = TimedFrame(
                    current_frame, beg_timepoint=current_frame.time, end_timepoint=next_frame.time
                )
            yield current_frame
            current_frame = next_frame
