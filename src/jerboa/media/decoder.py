from collections.abc import Iterable, Generator

import av
import copy
import math
import numpy as np
from bisect import bisect_right
from threading import Thread, Lock, Condition
from fractions import Fraction
from dataclasses import dataclass

from jerboa.timeline import FragmentedTimeline, RangeMappingResult
from .media import MediaType, AudioConfig, VideoConfig, config_from_stream
from .buffers import create_buffer
from .mappers import create_mapper
from .reformatters import AudioReformatter, VideoReformatter, create_reformatter

BUFFER_DURATION = 2.5  # in seconds

AUDIO_SEEK_THRESHOLD = 0.25  # in seconds

STOP_DECODING_SEEK_TIMEPOINT = math.nan


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


@dataclass
class SkippingFrame(TimedFrame):
  skip_aware_beg_timepoint: float


class SkippingDecoder:

  def __init__(self, simple_decoder: SimpleDecoder):
    self._simple_decoder = simple_decoder
    self._reformatter: AudioReformatter | VideoReformatter | None = None

    if self.media_type == MediaType.AUDIO:
      self.decode = self._decode_audio
    else:
      self.decode = self._decode_video

  @property
  def media_type(self) -> MediaType:
    return self._simple_decoder.media_type

  @property
  def stream_index(self) -> SimpleDecoder:
    return self._simple_decoder.stream.index

  @property
  def start_timepoint(self) -> float:
    return self._simple_decoder.start_timepoint

  def _decode_audio(
      self,
      seek_timepoint: float,
      media_config: AudioConfig,
  ) -> Generator[SkippingFrame, float, None]:
    self._init_reformatter(media_config)
    reformatter: AudioReformatter = self._reformatter

    skip_timepoint = seek_timepoint
    for timed_frame in self._simple_decoder.decode(seek_timepoint):
      if timed_frame is None:
        reformatted_frames_src = reformatter.flush()
      elif timed_frame.end_timepoint > skip_timepoint:
        reformatted_frames_src = reformatter.reformat(timed_frame.av_frame)
      else:
        reformatter.reset()
        reformatted_frames_src = []

      for reformatted_frame in reformatted_frames_src:
        skipping_frame = SkippingFrame(
            reformatted_frame,
            beg_timepoint=reformatted_frame.time,
            end_timepoint=(reformatted_frame.time +
                           reformatted_frame.samples * reformatted_frame.time_base),
            skip_aware_beg_timepoint=max(skip_timepoint, reformatted_frame.time),
        )
        skip_timepoint = yield skipping_frame
        yield  # wait for the `next()` call of the for loop

  def _init_reformatter(
      self,
      media_config: AudioConfig | VideoConfig,
  ) -> Generator[SkippingFrame, float, None]:
    if media_config.media_type != self.media_type:
      raise TypeError(
          f'Wrong media type! Expected "{self.media_type}", but got "{media_config.media_type}"')

    media_config = media_config or config_from_stream(self._stream)
    if self._reformatter is None or self._reformatter.config != media_config:
      self._reformatter = create_reformatter(media_config)
    else:
      self._reformatter.reset()

  def _decode_video(
      self,
      seek_timepoint: float,
      media_config: VideoConfig,
  ) -> Generator[SkippingFrame, float, None]:
    self._init_reformatter(media_config)
    reformatter: VideoReformatter = self._reformatter

    skip_timepoint = seek_timepoint
    for timed_frame in self._simple_decoder.decode(seek_timepoint):
      if timed_frame is not None and timed_frame.end_timepoint > skip_timepoint:
        reformatted_av_frame = reformatter.reformat(timed_frame.av_frame)
        timed_frame = SkippingFrame(
            reformatted_av_frame,
            beg_timepoint=timed_frame.beg_timepoint,
            end_timepoint=timed_frame.end_timepoint,
            skip_aware_beg_timepoint=max(skip_timepoint, timed_frame.beg_timepoint),
        )
        skip_timepoint = yield timed_frame
        yield  # yield again to wait for the `next()` call of the for loop

  def probe_keyframe_pts(self) -> list[float]:
    return self._simple_decoder.probe_keyframe_pts()


class NonlinearDecoder:

  def __init__(self,
               skipping_decoder: SkippingDecoder,
               media_config: AudioConfig | VideoConfig,
               init_timeline: FragmentedTimeline = None):
    self._skipping_decoder = skipping_decoder

    self._target_media_format = media_config.format
    self._mapper = create_mapper(media_config)
    self._buffer = create_buffer(self._mapper.internal_media_config, BUFFER_DURATION)

    self._timeline = FragmentedTimeline() if init_timeline is None else init_timeline
    self._keyframe_timepoints = list[float]()  # probing is done in the decoding thread

    self._seek_timepoint: None | float = skipping_decoder.start_timepoint
    self._is_done = False

    self._mutex = Lock()
    self._seeking = Condition(self._mutex)
    self._buffer_not_empty_or_done = Condition(self._mutex)
    self._buffer_not_full_or_seeking = Condition(self._mutex)
    self._timeline_updated_or_seeking = Condition(self._mutex)

    self._dec_thread = Thread(target=self._decoding,
                              name=(f'Decoding #{self._skipping_decoder.stream_index} stream '
                                    f'({self._skipping_decoder.media_type})'),
                              daemon=True)
    self._dec_thread.start()

  def __del__(self):
    if hasattr(self, '_dec_thread') and self._dec_thread.is_alive():
      self.seek(STOP_DECODING_SEEK_TIMEPOINT)

  @property
  def start_timepoint(self) -> float:
    return self._skipping_decoder.start_timepoint

  @property
  def target_media_format(self) -> av.AudioFormat | av.VideoFormat:
    return self._target_media_format

  @property
  def internal_media_config(self) -> AudioConfig | VideoConfig:
    return self._mapper.internal_media_config

  def update_timeline(self, updated_timeline: FragmentedTimeline):
    assert updated_timeline.time_scope > self._timeline.time_scope
    with self._mutex:
      self._timeline = copy.copy(updated_timeline)  # TODO: maybe improve updating
      self._timeline_updated_or_seeking.notify_all()

  def set_new_timeline(self, new_timeline: FragmentedTimeline, current_mapped_timepoint: float):
    with self._mutex:
      current_timepoint = self._timeline.unmap_timepoint_to_source(current_mapped_timepoint)
      new_timepoint = self._timeline.map_time_range(current_timepoint, current_timepoint)

      self._timeline = copy.copy(new_timeline)
      self._seek_without_lock(new_timepoint)

  def _seek_without_lock(self, seek_timepoint: float):
    self._seek_timepoint = self._timeline.unmap_timepoint_to_source(seek_timepoint)
    self._buffer.clear()

    self._seeking.notify()
    self._buffer_not_full_or_seeking.notify()
    self._timeline_updated_or_seeking.notify()

  def seek(self, seek_timepoint: float):
    with self._mutex:
      self._seek_without_lock(seek_timepoint)

  def _decoding(self):
    self._keyframe_timepoints = self._skipping_decoder.probe_keyframe_pts()
    self._seek_timepoint = self._skipping_decoder.start_timepoint  # start decoding from start
    while True:
      seek_timepoint = self._decoding__wait_for_seek()
      if seek_timepoint == STOP_DECODING_SEEK_TIMEPOINT:
        break
      self._decoding__loop(seek_timepoint)

  def _decoding__wait_for_seek(self) -> float:
    with self._mutex:
      self._seeking.wait_for(lambda: self._seek_timepoint is not None)
      self._is_done = False

      seek_timestamp = self._seek_timepoint
      self._seek_timepoint = None
      return seek_timestamp

  def _decoding__loop(self, seek_timepoint: float):
    self._mapper.reset()

    skip_timepoint = seek_timepoint
    decoder = self._skipping_decoder.decode(seek_timepoint, self.internal_media_config)
    for timed_frame in decoder:
      mapping_results, skip_timepoint = self._decoding__try_mapping_frame(timed_frame)
      decoder.send(skip_timepoint)

      if (mapping_results is None or
          (not self._decoding__try_to_map_and_put_frame(timed_frame, mapping_results) and
           self._decoding__try_to_skip_dropped_frames(timed_frame, skip_timepoint))):
        return  # begin seeking

    self._decoding__flush_mapper()  # TODO: this should also handle the last `current_frame`

  def _decoding__try_mapping_frame(
      self,
      timed_frame: SkippingFrame,
  ) -> tuple[RangeMappingResult, float] | tuple[None, None]:
    with self._mutex:

      def cond():
        return (self._timeline.time_scope >= timed_frame.end_timepoint or
                self._seek_timepoint is not None)

      self._timeline_updated_or_seeking.wait_for(cond)
      if self._seek_timepoint is not None:
        return (None, None)  # begin seeking

    return self._timeline.map_time_range(timed_frame.skip_aware_beg_timepoint,
                                         timed_frame.end_timepoint)

  def _decoding__try_to_map_and_put_frame(self, timed_frame: SkippingFrame,
                                          mapping_results: RangeMappingResult) -> bool:
    mapped_frame = self._mapper.map(timed_frame.av_frame, mapping_results)
    if mapped_frame.duration > 0:
      with self._mutex:
        self._buffer_not_full_or_seeking.wait_for(
            lambda: not self._buffer.is_full() or self._seek_timepoint is not None)
        if self._seek_timepoint is not None:
          return False  # begin seeking

        self._buffer.put(mapped_frame)
        self._buffer_not_empty_or_done.notify()

    # returns false only when interrupted, not putting a dropped frame is a success too
    return True

  def _decoding__try_to_skip_dropped_frames(self, current_frame: SkippingFrame,
                                            skip_timepoint: float) -> bool:
    if self._keyframe_timepoints:
      current_keyframe_idx = bisect_right(self._keyframe_timepoints, current_frame.end_timepoint)
      next_keyframe_idx = bisect_right(self._keyframe_timepoints, skip_timepoint)
      should_seek = current_keyframe_idx < next_keyframe_idx
    else:
      should_seek = skip_timepoint - current_frame.end_timepoint >= AUDIO_SEEK_THRESHOLD

    if should_seek:
      with self._mutex:
        if self._seek_timepoint is None:  # must never overwrite the user's seek
          self._seek_timepoint = skip_timepoint
      return True  # return to begin seeking
    return False

  def _decoding__flush_mapper(self) -> None:
    mapped_frame = self._mapper.map(None, None)
    with self._mutex:
      if self._seek_timepoint is None:
        if mapped_frame.duration > 0:
          self._buffer_not_full_or_seeking.wait_for(
              lambda: not self._buffer.is_full() or self._seek_timepoint is not None)
          self._buffer.put(mapped_frame)
        self._is_done = True
        self._buffer_not_empty_or_done.notify()

  def is_done(self) -> bool:
    return self._is_done

  def pop(self, *args) -> np.ndarray:
    frame = None
    with self._mutex:
      self._buffer_not_empty_or_done.wait_for(lambda: not self._buffer.is_empty() or self.is_done())
      if not self._buffer.is_empty():
        frame = self._buffer.pop(*args)
        self._buffer_not_full_or_seeking.notify()
    return frame

  def get_next_timepoint(self) -> float | None:
    with self._mutex:
      self._buffer_not_empty_or_done.wait_for(lambda: not self._buffer.is_empty() or self.is_done())
      if not self._buffer.is_empty():
        return self._buffer.get_next_timepoint()
      return None

  def prefill_buffer(self, duration: float) -> None:
    with self._mutex:
      self._buffer_not_empty_or_done.wait_for(
          lambda: self._buffer.duration >= duration or self.is_done())
