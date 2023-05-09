import av
import copy
import math
import numpy as np
from bisect import bisect_right
from threading import Thread, Lock, Condition

from jerboa.timeline import FragmentedTimeline
from .buffers import create_buffer
from .mappers import create_mapper
from .reformatters import AudioReformatter, VideoReformatter

BUFFER_DEFAULT_DURATION = 5.0  # in seconds

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
               reformatter: AudioReformatter | VideoReformatter,
               init_timeline: FragmentedTimeline = None):
    self.container = av.open(filepath)
    if not (0 <= stream_idx < len(self.container.streams)):
      raise ValueError(f'Wrong stream index! Tried to decode #{stream_idx} stream, while the file '
                       f'"{filepath}" has {len(self.container.streams)} streams')

    self.stream = self.container.streams[stream_idx]
    self.stream.thread_type = 'AUTO'
    self.start_timepoint = self.stream.start_time * self.stream.time_base
    assert isinstance(self.stream, (av.audio.AudioStream, av.video.VideoStream))

    self._reformatter = reformatter
    self._mapper = create_mapper(reformatter)
    self._buffer = create_buffer(reformatter, BUFFER_DEFAULT_DURATION)

    self._timeline = FragmentedTimeline() if init_timeline is None else init_timeline

    self._seek_timepoint: None | float = self.start_timepoint
    self._is_done = False

    self._mutex = Lock()
    self._seeking = Condition(self._mutex)
    self._buffer_not_empty_or_done = Condition(self._mutex)
    self._buffer_not_full_or_seeking = Condition(self._mutex)
    self._timeline_updated_or_seeking = Condition(self._mutex)

    self._dec_thread = Thread(target=self._decode,
                              name=f'Decoding #{self.stream.index} stream ({self.stream.type})',
                              daemon=True)
    self._dec_thread.start()

  def __del__(self):
    if hasattr(self, '_dec_thread') and self._dec_thread.is_alive():
      self.seek(STOP_DECODING_SEEK_TIMEPOINT)

  @property
  def reformatter(self) -> AudioReformatter | VideoReformatter:
    return self._reformatter

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

  def _decode(self):
    keyframe_pts_arr = probe_keyframe_pts(self.container, self.stream)

    self._seek_timepoint = self.start_timepoint  # start decoding from start
    min_frame_time = self.start_timepoint
    while True:
      self._av_demux_and_decode(min_frame_time, keyframe_pts_arr)
      with self._mutex:
        self._seeking.wait_for(lambda: self._seek_timepoint is not None)
        self._is_done = False

        if self._seek_timepoint == STOP_DECODING_SEEK_TIMEPOINT:
          return

        min_frame_time = self._seek_timepoint
        seek_timestamp = int(self._seek_timepoint / self.stream.time_base)
        self._seek_timepoint = None

      self.container.seek(seek_timestamp, stream=self.stream)

  def _av_demux_and_decode(self, min_frame_time: float, keyframe_pts_arr: list[float]):
    self._mapper.reset()

    current_frame: av.VideoFrame | av.AudioFrame | None = None
    for next_pkt in self.container.demux(self.stream):
      for next_raw_frame in next_pkt.decode():
        if math.isclose(next_raw_frame.time, min_frame_time, abs_tol=1e-3):
          current_frame = None

        for next_frame in self.reformatter.reformat(next_raw_frame):
          if current_frame is not None:
            frame_beg, frame_end = current_frame.time, next_frame.time

            with self._mutex:
              self._timeline_updated_or_seeking.wait_for(
                  lambda: self._timeline.time_scope >= frame_end or self._seek_timepoint is not None
              )
              if self._seek_timepoint is not None:
                return  # return to begin seeking

            mapping_results, min_frame_time = self._timeline.map_time_range(frame_beg, frame_end)
            if mapping_results.beg < mapping_results.end:
              mapped_frame = self._mapper.map(current_frame, mapping_results)
              if mapped_frame is not None:
                with self._mutex:
                  self._buffer_not_full_or_seeking.wait_for(
                      lambda: not self._buffer.is_full() or self._seek_timepoint is not None)
                  if self._seek_timepoint is not None:
                    return  # return to begin seeking

                  self._buffer.put(mapped_frame)
                  self._buffer_not_empty_or_done.notify()
            else:  # frame was dropped, check if it is worth to seek to the next one
              if keyframe_pts_arr:
                current_keyframe_idx = bisect_right(keyframe_pts_arr, current_frame.time)
                next_keyframe_idx = bisect_right(keyframe_pts_arr, min_frame_time)
                should_seek = current_keyframe_idx < next_keyframe_idx
              else:
                should_seek = min_frame_time - frame_end >= AUDIO_SEEK_THRESHOLD

              if should_seek:
                with self._mutex:
                  if self._seek_timepoint is None:  # must never overwrite the user's seek
                    self._seek_timepoint = min_frame_time
                return  # return to begin seeking

          current_frame = next_frame
    # flush the staged frames (if any) and TODO: the current_frame
    mapped_frame = self._mapper.map(None, None)  # TODO: push current_frame instead
    with self._mutex:
      if self._seek_timepoint is None:
        if mapped_frame is not None:
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