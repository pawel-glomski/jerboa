from collections.abc import Iterable
from typing import Callable

import av
import math
from dataclasses import dataclass

from jerboa.media import MediaType

from jerboa.media import std_audio


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
      raise IndexError(f'Wrong stream index! Tried to decode #{stream_idx} stream, while the file '
                       f'"{filepath}" has {len(self._container.streams)} streams') from exc

    if not isinstance(self._stream, (av.audio.AudioStream, av.video.VideoStream)):
      raise TypeError(f'Media type "{self._stream.type}" is not supported')

    self._stream.thread_type = 'AUTO'
    self._start_timepoint = max(0, self._stream.start_time * self._stream.time_base)

    self._media_type = MediaType(self._stream.type)

    self._frame_time_base_standardizer = self._get_frame_time_base_standardizer()
    self._next_frame_pts_generator = self._get_next_frame_pts_generator()

  @property
  def media_type(self) -> MediaType:
    return self._media_type

  @property
  def stream(self) -> av.audio.AudioStream | av.video.VideoStream:
    return self._stream

  @property
  def start_timepoint(self) -> float:
    return self._start_timepoint

  def _get_frame_time_base_standardizer(self) -> Callable[[av.AudioFrame | av.VideoFrame], None]:
    if self.media_type == MediaType.AUDIO:
      return std_audio.get_frame_time_base_standardizer(self.stream)
    return lambda _: ...  # do nothing when video

  def _get_next_frame_pts_generator(self):
    if self.media_type == MediaType.AUDIO:
      end_pts_gen = std_audio.get_end_pts_generator(self.stream)
      return lambda frame, _: end_pts_gen(frame)
    return lambda _, next_frame: next_frame.pts if next_frame is not None else math.inf

  def decode(self, seek_timepoint: float) -> Iterable[TimedFrame | None]:
    current_frame: av.AudioFrame | av.VideoFrame | None = None
    for next_frame in self._standard_decode(seek_timepoint):
      if current_frame is not None:
        next_frame_pts = self._next_frame_pts_generator(current_frame, next_frame)
        if next_frame is not None:
          next_frame.pts = next_frame_pts
        yield TimedFrame(current_frame,
                         beg_timepoint=current_frame.time,
                         end_timepoint=next_frame_pts * current_frame.time_base)
        if next_frame is None:
          yield None
      current_frame = next_frame

  def _standard_decode(self,
                       seek_timepoint: float) -> Iterable[av.AudioFrame | av.VideoFrame | None]:
    self._container.seek(round(seek_timepoint / self._stream.time_base), stream=self._stream)
    for packet in self._container.demux(self.stream):
      for frame in packet.decode():
        self._frame_time_base_standardizer(frame)
        yield frame
      if packet.dts is None:
        yield None

  def probe_keyframe_duration(self) -> list[float]:
    '''This cannot be called inside a decoding loop'''
    self._container.seek(self.stream.start_time, stream=self.stream)

    keyframe_pts_arr = []
    last_valid_pkt_timepoint = self.start_timepoint
    for pkt in self._container.demux(self.stream):
      if pkt.is_keyframe and pkt.pts is not None:
        pkt_timepoint = pkt.pts * pkt.time_base
        if pkt_timepoint >= self.start_timepoint:
          last_valid_pkt_timepoint = pkt_timepoint
          keyframe_pts_arr.append(pkt_timepoint)
          if len(keyframe_pts_arr) == 2:
            break
    else:
      keyframe_pts_arr.append(last_valid_pkt_timepoint)

    # seek back to the beginning
    self._container.seek(self.stream.start_time, stream=self.stream)

    if len(keyframe_pts_arr) == 2:
      return float(abs(keyframe_pts_arr[1] - keyframe_pts_arr[0]))
    return 0.0
