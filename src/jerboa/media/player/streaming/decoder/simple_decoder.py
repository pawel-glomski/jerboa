from collections.abc import Iterable
from typing import Callable

import av
import math
from dataclasses import dataclass

from jerboa.media import MediaType
from jerboa.media import standardized_audio as std_audio
from jerboa.media.config import AudioConfig, VideoConfig, config_from_stream

MEAN_KEYFRAME_INTERVAL_SAMPLE_SIZE = 8
DEFAULT_MEAN_KEYFRAME_INTERVAL = 0


@dataclass
class TimedFrame:
    av_frame: av.AudioFrame | av.VideoFrame
    beg_timepoint: float
    end_timepoint: float


class SimpleDecoder:
    def __init__(self, filepath: str, stream_idx: int):
        self._container = av.open(filepath)
        try:
            self._stream = self._container.streams[stream_idx]
        except IndexError as exc:
            raise IndexError(
                f"Wrong stream index! Tried to decode #{stream_idx} stream, while the file "
                f'"{self._container.name}" has {len(self._container.streams)} streams'
            ) from exc

        if not isinstance(self._stream, (av.audio.AudioStream, av.video.VideoStream)):
            raise TypeError(f'Media type "{self._stream.type}" is not supported')

        self._stream.thread_type = "AUTO"

        self._media_config = config_from_stream(self._stream)
        self._media_type = MediaType(self._stream.type)

        self._mean_keyframe_interval = DEFAULT_MEAN_KEYFRAME_INTERVAL

    def __del__(self):
        self._container.close()

    @property
    def media_type(self) -> MediaType:
        return self._media_type

    @property
    def media_config(self) -> AudioConfig | VideoConfig:
        return self._media_config

    @property
    def stream_index(self) -> int:
        return self._stream.index

    @property
    def mean_keyframe_interval(self) -> float:
        return self._mean_keyframe_interval

    @property
    def start_timepoint(self) -> float:
        return max(0, self._stream.start_time * self._stream.time_base)

    def _get_frame_time_base_standardizer(self) -> Callable[[av.AudioFrame | av.VideoFrame], None]:
        if self.media_type == MediaType.AUDIO:
            return std_audio.get_frame_time_base_standardizer(self._stream)
        return lambda _: ...  # do nothing when video

    def _get_next_frame_pts_generator(self):
        if self.media_type == MediaType.AUDIO:
            end_pts_gen = std_audio.get_end_pts_generator(self._stream)
            return lambda frame, _: end_pts_gen(frame)
        return lambda _, next_frame: next_frame.pts if next_frame is not None else math.inf

    def decode(self, seek_timepoint: float) -> Iterable[TimedFrame | None]:
        next_frame_pts_generator = self._get_next_frame_pts_generator()

        current_frame: av.AudioFrame | av.VideoFrame | None = None
        for next_frame in self._standard_decode(seek_timepoint):
            if current_frame is not None:
                next_frame_pts = next_frame_pts_generator(current_frame, next_frame)
                if next_frame is not None:
                    next_frame.pts = next_frame_pts
                yield TimedFrame(
                    current_frame,
                    beg_timepoint=current_frame.time,
                    end_timepoint=next_frame_pts * current_frame.time_base,
                )
                if next_frame is None:
                    yield None
            current_frame = next_frame

    def _standard_decode(
        self, seek_timepoint: float
    ) -> Iterable[av.AudioFrame | av.VideoFrame | None]:
        frame_time_base_standardizer = self._get_frame_time_base_standardizer()

        keyframes_num = 0
        last_keyframe_timepoint = None

        self._container.seek(round(seek_timepoint / self._stream.time_base), stream=self._stream)
        for packet in self._container.demux(self._stream):
            if packet.is_keyframe:
                if last_keyframe_timepoint is not None:
                    new_interval = packet.time - last_keyframe_timepoint
                    intervals_sum = (self._mean_keyframe_interval * keyframes_num) + new_interval
                    self._mean_keyframe_interval = intervals_sum / (keyframes_num + 1)
                    keyframes_num = min(MEAN_KEYFRAME_INTERVAL_SAMPLE_SIZE, keyframes_num + 1)
            for frame in packet.decode():
                frame_time_base_standardizer(frame)
                yield frame
            if packet.dts is None:
                yield None

    # def probe_keyframe_duration(self) -> list[float]:
    #   '''This cannot be called inside a decoding loop'''
    #   self._container.seek(self.stream.start_time, stream=self.stream)

    #   keyframe_pts_arr = []
    #   last_valid_pkt_timepoint = self.start_timepoint
    #   for pkt in self._container.demux(self.stream):
    #     if pkt.is_keyframe and pkt.pts is not None:
    #       pkt_timepoint = pkt.pts * pkt.time_base
    #       if pkt_timepoint >= self.start_timepoint:
    #         last_valid_pkt_timepoint = pkt_timepoint
    #         keyframe_pts_arr.append(pkt_timepoint)
    #         if len(keyframe_pts_arr) == 2:
    #           break
    #   else:
    #     keyframe_pts_arr.append(last_valid_pkt_timepoint)

    #   # seek back to the beginning
    #   self._container.seek(self.stream.start_time, stream=self.stream)

    #   if len(keyframe_pts_arr) == 2:
    #     return float(abs(keyframe_pts_arr[1] - keyframe_pts_arr[0]))
    #   return 0.0
