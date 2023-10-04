from collections.abc import Iterable
from typing import Callable

import av
import math
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from jerboa.media.core import MediaType, AudioStreamInfo, VideoStreamInfo, VideoConfig
from jerboa.media import standardized_audio as std_audio


MEAN_KEYFRAME_INTERVAL_SAMPLE_SIZE = 8
DEFAULT_MEAN_KEYFRAME_INTERVAL = 0


@dataclass
class TimedFrame:
    av_frame: av.AudioFrame | av.VideoFrame
    beg_timepoint: float
    end_timepoint: float


class SimpleDecoder:
    def __init__(self, filepath: str, media_type: MediaType, stream_idx: int):
        self._media_type = media_type

        with ThreadPoolExecutor(max_workers=2) as executor:
            container_feature = executor.submit(av.open, filepath)
            self._container = container_feature.result()

        if media_type == MediaType.AUDIO:
            self._stream = self._container.streams.audio[stream_idx]
            self._stream_info = SimpleDecoder._get_audio_stream_info(self._stream)
        elif media_type == MediaType.VIDEO:
            self._stream = self._container.streams.video[stream_idx]
            self._stream_info = SimpleDecoder._get_video_stream_info(self._stream)
        else:
            raise TypeError(f'Media type "{self._stream.type}" is not supported')

        self._stream.thread_type = "AUTO"

        self._mean_keyframe_interval = DEFAULT_MEAN_KEYFRAME_INTERVAL

    def __del__(self):
        self._container.close()

    @property
    def stream_info(self) -> AudioStreamInfo | VideoStreamInfo:
        return self._stream_info

    @staticmethod
    def _get_audio_stream_info(stream: av.audio.AudioStream) -> AudioStreamInfo:
        return AudioStreamInfo(
            stream_index=stream.index,
            start_timepoint=max(0, stream.start_time * stream.time_base),
            sample_rate=stream.sample_rate,
        )

    @staticmethod
    def _get_video_stream_info(stream: av.video.VideoStream) -> VideoStreamInfo:
        return VideoStreamInfo(
            stream_index=stream.index,
            start_timepoint=max(0, stream.start_time * stream.time_base),
            width=stream.width,
            height=stream.height,
            guessed_frame_rate=stream.guessed_rate or stream.average_rate,
            sample_aspect_ratio=stream.sample_aspect_ratio,
        )

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

    def _get_next_frame_pts_generator(self):
        if self.stream_info.media_type == MediaType.AUDIO:
            end_pts_gen = std_audio.get_end_pts_generator(self._stream)
            return lambda frame, _: end_pts_gen(frame)
        return lambda _, next_frame: next_frame.pts if next_frame is not None else math.inf

    def _get_frame_time_base_standardizer(self) -> Callable[[av.AudioFrame | av.VideoFrame], None]:
        if self.stream_info.media_type == MediaType.AUDIO:
            return std_audio.get_frame_time_base_standardizer(self._stream)
        return lambda _: ...  # do nothing when video

    def get_mean_keyframe_interval(self) -> float:
        return self._mean_keyframe_interval
