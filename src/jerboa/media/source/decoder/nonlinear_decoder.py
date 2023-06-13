import av
import copy
import math
import numpy as np
from bisect import bisect_right
from threading import Thread, Lock, Condition

from jerboa.timeline import FragmentedTimeline, RangeMappingResult
from jerboa.media import AudioConfig, VideoConfig
from .skipping_decoder import SkippingDecoder, SkippingFrame
from .util import create_buffer, create_mapper

BUFFER_DURATION = 2.5  # in seconds

AUDIO_SEEK_THRESHOLD = 0.25  # in seconds

STOP_DECODING_SEEK_TIMEPOINT = math.nan


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
