import av
import copy
import math
import numpy as np
from bisect import bisect_right
from threading import Thread, Lock, Condition
from fractions import Fraction

from jerboa.timeline import FragmentedTimeline, RangeMappingResult
from .media import MediaType, AudioConfig, VideoConfig
from .buffers import create_buffer
from .stretchers import create_stretcher
from .reformatters import create_reformatter

BUFFER_DURATION = 5.0  # in seconds
STRETCHER_BUFFER_DURATION = 0.2  # in seconds

AUDIO_SEEK_THRESHOLD = 0.5  # in seconds

STOP_DECODING_SEEK_TIMEPOINT = math.nan


def probe_keyframe_pts(container: av.container.Container, stream: av.stream.Stream) -> list[float]:
  if isinstance(stream, av.audio.AudioStream):
    return []  # audio stream does not need probing

  container.seek(stream.start_time, stream=stream)

  start_timepoint = stream.start_time * stream.time_base
  keyframe_pts_arr = [
      pkt.pts
      for pkt in container.demux(stream)
      if pkt.is_keyframe and pkt.pts is not None and pkt.pts * pkt.time_base >= start_timepoint
  ]
  keyframe_pts_arr = sorted(keyframe_pts_arr)
  keyframe_pts_arr.append(math.inf)

  # seek back to the beginning
  container.seek(stream.start_time, stream=stream)
  return keyframe_pts_arr


class StreamDecoder:

  def __init__(self,
               filepath: str,
               stream_idx: int,
               media_config: AudioConfig | VideoConfig,
               init_timeline: FragmentedTimeline = None):
    self.container = av.open(filepath)
    if not (0 <= stream_idx < len(self.container.streams)):
      raise ValueError(f'Wrong stream index! Tried to decode #{stream_idx} stream, while the file '
                       f'"{filepath}" has {len(self.container.streams)} streams')

    self.stream = self.container.streams[stream_idx]
    self.stream.thread_type = 'AUTO'
    self.start_timepoint = self.stream.start_time * self.stream.time_base
    assert isinstance(self.stream, (av.audio.AudioStream, av.video.VideoStream))

    if media_config.media_type == MediaType.AUDIO:
      if self.stream.time_base == Fraction(1, self.stream.sample_rate):
        self._fixed_next_frame_pts = lambda frame, _: frame.pts + frame.samples
      else:
        self._fixed_next_frame_pts = lambda frame, _: frame.pts + round(
            Fraction(frame.samples, frame.sample_rate) / frame.time_base)
    else:
      self._fixed_next_frame_pts = lambda _, next_fame: next_fame.pts

    self._target_media_format = media_config.format
    self._stretcher = create_stretcher(media_config, STRETCHER_BUFFER_DURATION)
    self._buffer = create_buffer(self._stretcher.internal_media_config, BUFFER_DURATION)
    self._reformatter = create_reformatter(self._stretcher.internal_media_config)

    self._timeline = FragmentedTimeline() if init_timeline is None else init_timeline
    self._keyframe_pts_arr = list[float]()  # probing is done in the decoding thread

    self._seek_timepoint: None | float = self.start_timepoint
    self._is_done = False

    self._mutex = Lock()
    self._seeking = Condition(self._mutex)
    self._buffer_not_empty_or_done = Condition(self._mutex)
    self._buffer_not_full_or_seeking = Condition(self._mutex)
    self._timeline_updated_or_seeking = Condition(self._mutex)

    # this has the same value as _seek_timepoint after the seek, but changes during decoding
    self._min_frame_time: float = None

    self._dec_thread = Thread(target=self._decoding,
                              name=f'Decoding #{self.stream.index} stream ({self.stream.type})',
                              daemon=True)
    self._dec_thread.start()

  def __del__(self):
    if hasattr(self, '_dec_thread') and self._dec_thread.is_alive():
      self.seek(STOP_DECODING_SEEK_TIMEPOINT)

  @property
  def target_media_format(self) -> av.AudioFormat | av.VideoFormat:
    return self._target_media_format

  @property
  def internal_media_config(self) -> AudioConfig | VideoConfig:
    return self._stretcher.internal_media_config

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
    self._keyframe_pts_arr = probe_keyframe_pts(self.container, self.stream)
    self._seek_timepoint = self.start_timepoint  # start decoding from start
    while True:
      self._decoding__wait_and_seek()
      self._decoding__loop()

  def _decoding__wait_and_seek(self):
    with self._mutex:
      self._seeking.wait_for(lambda: self._seek_timepoint is not None)
      self._is_done = False

      if self._seek_timepoint == STOP_DECODING_SEEK_TIMEPOINT:
        return

      seek_timestamp = int(self._seek_timepoint / self.stream.time_base)
      self._min_frame_time = self._seek_timepoint
      self._seek_timepoint = None

    self.container.seek(seek_timestamp, stream=self.stream)

  def _decoding__loop(self):
    self._reformatter.reset()
    self._stretcher.reset()

    current_frame: av.VideoFrame | av.AudioFrame | None = None
    for next_pkt in self.container.demux(self.stream):
      for next_raw_frame in next_pkt.decode():
        if (next_raw_frame.time < self._min_frame_time and
            not math.isclose(next_raw_frame.time, self._min_frame_time, abs_tol=1e-3)):
          current_frame = None
          continue

        for next_frame in self._reformatter.reformat(next_raw_frame):
          if current_frame is not None:
            next_frame.pts = self._fixed_next_frame_pts(current_frame, next_frame)

            frame_beg, frame_end = current_frame.time, next_frame.time
            mapping_results, self._min_frame_time = self._decoding__get_frame_mapping_results(
                frame_beg, frame_end)

            if (mapping_results is None or
                (not self._decoding__try_to_stretch_and_put_frame(current_frame, mapping_results)
                 and self._decoding__try_to_skip_dropped_frames(frame_beg, frame_end))):
              return  # begin seeking
          current_frame = next_frame

    self._decoding__flush_stretcher()  # TODO: this should also handle the last `current_frame`

  def _decoding__get_frame_mapping_results(
      self, frame_beg: float,
      frame_end: float) -> tuple[RangeMappingResult, float] | tuple[None, None]:
    with self._mutex:
      self._timeline_updated_or_seeking.wait_for(
          lambda: self._timeline.time_scope >= frame_end or self._seek_timepoint is not None)
      if self._seek_timepoint is not None:
        return (None, None)  # begin seeking

    return self._timeline.map_time_range(frame_beg, frame_end)

  def _decoding__try_to_stretch_and_put_frame(self, current_frame: av.AudioFrame | av.VideoFrame,
                                              mapping_results: RangeMappingResult) -> bool:
    stretched_frame = self._stretcher.stretch(current_frame, mapping_results)
    if stretched_frame.duration > 0:
      with self._mutex:
        self._buffer_not_full_or_seeking.wait_for(
            lambda: not self._buffer.is_full() or self._seek_timepoint is not None)
        if self._seek_timepoint is not None:
          return False  # begin seeking

        self._buffer.put(stretched_frame)
        self._buffer_not_empty_or_done.notify()

    # returns false only when interrupted, not putting a dropped frame is a success too
    return True

  def _decoding__try_to_skip_dropped_frames(self, frame_beg, frame_end: float) -> bool:
    if self._keyframe_pts_arr:
      current_keyframe_idx = bisect_right(self._keyframe_pts_arr, frame_beg)
      next_keyframe_idx = bisect_right(self._keyframe_pts_arr, self._min_frame_time)
      should_seek = current_keyframe_idx < next_keyframe_idx
    else:
      should_seek = self._min_frame_time - frame_end >= AUDIO_SEEK_THRESHOLD

    if should_seek:
      with self._mutex:
        if self._seek_timepoint is None:  # must never overwrite the user's seek
          self._seek_timepoint = self._min_frame_time
      return True  # return to begin seeking
    return False

  def _decoding__flush_stretcher(self) -> None:
    stretched_frame = self._stretcher.stretch(None, None)
    with self._mutex:
      if self._seek_timepoint is None:
        if stretched_frame.duration > 0:
          self._buffer_not_full_or_seeking.wait_for(
              lambda: not self._buffer.is_full() or self._seek_timepoint is not None)
          self._buffer.put(stretched_frame)
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
