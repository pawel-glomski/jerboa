from collections.abc import Iterable

import av
import math
from fractions import Fraction
from dataclasses import dataclass

from .media import MediaType
from .reformatters import AudioReformatter, VideoReformatter


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
    self._start_timepoint = self._stream.start_time * self._stream.time_base

    self._media_type = MediaType(self._stream.type)

    self._reformatter: AudioReformatter | VideoReformatter | None = None

    self._end_pts_gen = self._get_end_pts_gen()

  @property
  def media_type(self) -> MediaType:
    return self._media_type

  @property
  def stream(self) -> av.audio.AudioStream | av.video.VideoStream:
    return self._stream

  @property
  def start_timepoint(self) -> float:
    return self._start_timepoint

  def _get_end_pts_gen(self):

    def audio_pts_gen_simple_timebase(frame: av.AudioFrame, _) -> float:
      return frame.pts + frame.samples

    def audio_pts_gen_any_timebase(frame: av.AudioFrame, _) -> float:
      return frame.pts + round(Fraction(frame.samples, frame.sample_rate) / frame.time_base)

    def video_pts_gen(_, next_frame: av.VideoFrame) -> float:
      return next_frame.pts if next_frame is not None else math.inf

    if self.media_type == MediaType.AUDIO:
      if self.stream.time_base == Fraction(1, self.stream.sample_rate):
        return audio_pts_gen_simple_timebase
      return audio_pts_gen_any_timebase
    return video_pts_gen

  def decode(self, seek_timepoint: float) -> Iterable[TimedFrame | None]:
    current_frame: av.AudioFrame | av.VideoFrame | None = None
    for next_frame in self._standard_decode(seek_timepoint):
      if current_frame is not None:
        next_frame_pts = self._end_pts_gen(current_frame, next_frame)
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
        yield frame
      if packet.dts is None:
        yield None

  def probe_keyframe_pts(self) -> list[float]:
    '''This cannot be called inside a decoding loop'''
    if self.media_type == MediaType.AUDIO:
      return []  # audio stream does not need probing

    self._container.seek(self.stream.start_time, stream=self.stream)

    start_timepoint = self.stream.start_time * self.stream.time_base
    keyframe_pts_arr = [
        pkt.pts
        for pkt in self._container.demux(self.stream)
        if pkt.is_keyframe and pkt.pts is not None and pkt.pts * pkt.time_base >= start_timepoint
    ]
    keyframe_pts_arr = sorted(keyframe_pts_arr)
    keyframe_pts_arr.append(math.inf)

    # seek back to the beginning
    self._container.seek(self.stream.start_time, stream=self.stream)
    return keyframe_pts_arr
