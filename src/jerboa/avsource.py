import av
import pyglet
import math
import numpy as np
from typing import Callable, Iterable
from enum import Enum
from threading import Thread, Lock, Condition
from collections import deque
from fractions import Fraction
from dataclasses import dataclass
from bisect import bisect_left, bisect_right

from pyglet.media import StreamingSource
from pyglet.media.codecs import AudioFormat, VideoFormat, AudioData

from jerboa.timeline import TMSection, FragmentedTimeline


class MediaType(Enum):
  AUDIO = 'audio'
  VIDEO = 'video'


BUFFER_MAX_DURATION = 5.0  # in seconds
SEEK_THRESHOLD = 20.0  # in seconds

MAX_COMPENSATION_RATIO = Fraction(1, 10)
MAX_AUDIO_CHANNELS = 2
AUDIO_FORMAT = av.AudioFormat('s16').packed
VIDEO_FORMAT = 'rgb24'
VIDEO_FORMAT_PYGLET = 'RGB'

STOP_DECODING_TIMESTAMP = math.inf

PLAYBACK_MODIFIERS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, math.inf]
DURATION_MODIFIERS = [1 / mod for mod in PLAYBACK_MODIFIERS]


@dataclass
class TimedFrame:
  data: np.ndarray
  timestamp_beg: float
  timestamp_end: float


class VideoBuffer:

  def __init__(self, max_duration: float, format: VideoFormat) -> None:
    self.max_duration = max_duration
    self.format = format
    self.queue = deque()
    self.graph = ...

  def push(self, frame: av.VideoFrame, end_timestamp: float, timeline: ModifiedTimeline) -> None:

    ...

  def pull(self) -> TimedFrame:
    ...

  def peek(self) -> TimedFrame:
    ...

  def clear(self):

    ...


class AudioBuffer:

  def __init__(self, max_duration: float, fmt: av.AudioFormat, layout: av.AudioLayout,
               sample_rate: int) -> None:
    self.max_duration = max_duration
    self.format = fmt
    self.layout = layout
    self.sample_rate = sample_rate
    self.graphs = [
        AudioBuffer.create_graph(mod, fmt, sample_rate, layout)
        for mod in PLAYBACK_MODIFIERS
        if mod < math.inf
    ]
    self.last_two_samples = (0, 0)

    self.byte_array = bytearray()

  def push(self, frame: av.AudioFrame, end_timestamp: float, timeline: ModifiedTimeline) -> None:
    # TODO: speed up audio here using number of filter graphs with predefined speeds
    # (i.e 0.75, 1.25, etc). Also, change the format and resample there
    # then connect neighboring frames using hann window or something
    format_resampler = av.AudioResampler(
        format=self.format,
        layout=self.layout,
        rate=self.sample_rate,
    )

    def process_audio_frame(self, frame, frame_beg, frame_end):
      subframes = [subframe.to_ndarray() for subframe in format_resampler.resample(frame)]
      frame_data = np.concatenate(subframes, 0)
      return TimedFrame(frame_data, frame.time, frame)

  def empty(self) -> bool:
    return len(self.byte_array) > 0

  def pull(self, bytes: int):
    ...

  def clear(self):
    ...


def create_frame_buffer(stream: av.stream.Stream, max_duration: float) -> AudioBuffer | VideoBuffer:
  if isinstance(stream, av.audio.AudioStream):
    return AudioBuffer(max_duration, AUDIO_FORMAT, stream.layout, stream.sample_rate)
  return VideoBuffer(max_duration, VIDEO_FORMAT)


def probe_keyframe_pts(container: av.container.Container, stream: av.stream.Stream) -> list[float]:
  if isinstance(stream, av.audio.AudioStream):
    return None  # audio stream does not need probing, it should almost always seek

  # start at the beginning
  container.seek(stream.start_time, stream=stream)

  start_time = stream.start_time * stream.time_base
  keyframe_pts_arr = [
      pkt.pts
      for pkt in container.demux(stream)
      if pkt.is_keyframe and pkt.pts is not None and pkt.pts * pkt.time_base >= start_time
  ]
  keyframe_pts_arr = sorted(keyframe_pts_arr)
  keyframe_pts_arr.append(math.inf)

  # seek back to the beginning
  container.seek(stream.start_time, stream=stream)
  return keyframe_pts_arr


class StreamDecoder:

  def __init__(self, filepath: str, stream_idx: int, init_timeline: FragmentedTimeline = None):
    self.container = av.open(filepath)
    if not (0 <= stream_idx < len(self.container.streams)):
      raise ValueError(f'Wrong stream index! Tried to decode #{stream_idx} stream, while the file '
                       f'"{filepath}" has {len(self.container.streams)} streams')

    self.stream = self.container.streams[stream_idx]
    self.stream.thread_type = 'AUTO'
    self.start_time = self.stream.start_time * self.stream.time_base
    assert isinstance(self.stream, (av.audio.AudioStream, av.video.VideoStream))

    self._mutex = Lock()
    self._seeking = Condition(self._mutex)
    self._buffer_not_empty = Condition(self._mutex)
    self._buffer_not_full_or_seeking = Condition(self._mutex)
    self._timeline_updated_or_seeking = Condition(self._mutex)

    self._seek_timestamp: None | float = None
    self._waiting_for_seek = False

    self._buffer = create_frame_buffer(self.stream, BUFFER_MAX_DURATION)

    self._timeline = init_timeline or FragmentedTimeline()

    self._dec_thread = Thread(target=self._decode,
                              name=f'Decoding #{self.stream.index} stream ({self.stream.type})',
                              daemon=True)
    self._dec_thread.start()

  def __del__(self):
    if hasattr(self, '_dec_thread') and self._dec_thread.is_alive():
      self.seek(STOP_DECODING_TIMESTAMP)

  def set_timeline(self, new_timeline: ModifiedTimeline):
    with self._mutex:
      if math.isinf(new_timeline.time_scope) or math.isinf(self._timeline.time_scope):
        new_buffer = []
        for frame in self._buffer:
          frame_src_range = (frame.src_timestamp_beg, frame.src_timestamp_end)
          frame_dst_range = new_timeline.apply_to_frame(*frame_src_range)
          if frame_dst_range[1] - frame_dst_range[0] > 0:
            frame.dst_timestamp_beg, frame.dst_timestamp_end = frame_dst_range
            new_buffer.append(frame)
        self._buffer = deque(new_buffer)
      self._timeline = new_timeline
      self._timeline_updated_or_seeking.notify_all()

  def seek(self, timestamp: float):
    timestamp = timestamp / self.stream.time_base
    with self._mutex:
      self._seek_timestamp = timestamp
      self._waiting_for_seek = False

      self._seeking.notify()
      self._buffer_not_full_or_seeking.notify()
      self._timeline_updated_or_seeking.notify()

  def _decode(self):
    keyframe_pts_arr = probe_keyframe_pts(self.container, self.stream)

    def find_keyframe_idx(pts: float, current_idx: int):
      if not keyframe_pts_arr:
        return None
      # try to find the keyframe in O(1)
      if current_idx is not None:
        # keyframe_pts_arr always has `inf` at the end, so current_idx <= len(keyframe_pts_arr) - 2
        if keyframe_pts_arr[current_idx] <= pts < keyframe_pts_arr[current_idx + 1]:
          return current_idx
        # since the above failed, we know that current_idx < len(keyframe_pts_arr) - 2
        if keyframe_pts_arr[current_idx + 1] <= pts < keyframe_pts_arr[current_idx + 2]:
          return current_idx + 1
      # find the keyframe in O(log n)
      return max(0, bisect_right(keyframe_pts_arr, current_frame.pts) - 1)

    while True:
      min_timestamp = self.start_time
      current_frame = None
      current_keyframe_idx = None

      with self._mutex:
        if self._waiting_for_seek:
          self._seeking.wait()
          self._waiting_for_seek = False
        if self._seek_timestamp is not None:
          if self._seek_timestamp == STOP_DECODING_TIMESTAMP:
            return
          self.container.seek(self._seek_timestamp, stream=self.stream)
          min_timestamp = self._seek_timestamp * self.stream.time_base
          self._seek_timestamp = None

      # TODO: move this to function
      for next_pkt in self.container.demux(self.stream):
        for next_frame in next_pkt.decode():
          if next_frame.time <= min_timestamp or current_frame is None:
            current_frame = next_frame
            current_keyframe_idx = find_keyframe_idx(current_frame.pts, current_keyframe_idx)
            continue

          frame_beg, frame_end = current_frame.time, next_frame.time
          with self._mutex:
            self._buffer_not_full_or_seeking.wait_for(
                lambda: self._buffer_duration < BUFFER_MAX_DURATION or self._seek_timestamp is
                not None)
            self._timeline_updated_or_seeking.wait_for(
                lambda: self._timeline.time_scope >= frame_end or self._seek_timestamp is not None)
            if self._seek_timestamp is not None:
              break

            frame_beg, frame_end, next_min_timestamp = self._timeline.apply(frame_beg, frame_end)
            frame = preprocess_frame(current_frame, frame_beg, frame_end)

            next_keyframe_idx = find_keyframe_idx(next_frame.pts, current_keyframe_idx)

            frame_duration = frame_end - frame_end
            if frame_duration > 0:
              self._buffer_duration += frame_duration
              self._buffer.put(frame)
              self._buffer_not_empty.notify()
            else:
              if (keyframe_pts_arr and abs(next_keyframe_idx - current_keyframe_idx) >= 1) or (
                  not keyframe_pts_arr and (next_min_timestamp - min_timestamp) >= SEEK_THRESHOLD):
                self.container.seek(next_min_timestamp * self.stream.time_base, stream=self.stream)
                break
            current_frame = next_frame
            current_keyframe_idx = next_keyframe_idx
            min_timestamp = next_min_timestamp
        else:
          continue
        break
      else:
        # TODO: flush current_frame
        self._waiting_for_seek = True

  def is_done(self) -> bool:
    return self._waiting_for_seek

  def pop(self) -> DecodedFrame | None:
    frame = None
    with self._mutex:
      self._buffer_not_empty.wait_for(lambda: self._buffer or self.is_done())
      if not self.is_done():
        frame = self._buffer.pop()
        self._buffer_not_full_or_seeking.notify()
    return frame

  def peek_next_timestamp(self) -> float | None:
    with self._mutex:
      self._buffer_not_empty.wait_for(lambda: self._buffer or self.is_done())
      if self.is_done():
        return None
      return self._buffer[0].dst_timestamp_beg


class SLSource(StreamingSource):

  def __init__(self, filepath: str):
    # find if there is a file with analysis results
    # if there is not, create one
    # use analysis results to skip frames
    self.container = av.open(filepath)
    self.decoders: dict[MediaType, StreamDecoder] = {}
    if self.container.streams.audio:
      from jerboa.timeline import TimelineSection
      audio_decoder = StreamDecoder(filepath, self.container.streams.audio[0].index,
                                    ModifiedTimeline(TimelineSection(-math.inf, math.inf, 1.0)))
      self.decoders[MediaType.AUDIO] = audio_decoder

      audio_stream = audio_decoder.stream
      self.audio_format = AudioFormat(channels=min(MAX_AUDIO_CHANNELS, audio_stream.channels),
                                      sample_size=AUDIO_FORMAT.bits,
                                      sample_rate=audio_stream.sample_rate)
    if self.container.streams.video:
      video_decoder = StreamDecoder(filepath, self.container.streams.video[0].index)
      self.decoders[MediaType.VIDEO] = video_decoder

      video_stream = video_decoder.stream
      sar = video_stream.sample_aspect_ratio
      self.video_format = VideoFormat(width=video_stream.width,
                                      height=video_stream.height,
                                      sample_aspect=sar if sar else 1.0)
      self.video_format.frame_rate = float(video_stream.average_rate)

    self.start_time = min(dec.start_time for dec in self.decoders.values())
    self.last_video_frame: pyglet.image.ImageData = None

  def __del__(self):
    self.container.close()

  def seek(self, timestamp):
    for decoder in self.decoders.values():
      decoder.seek(timestamp)

  def get_audio_data(self, num_bytes, compensation_time=0.0) -> AudioData:
    frames = []
    bytes_sum = 0
    timestamp = None
    audio_decoder = self.decoders[MediaType.AUDIO]
    audio_stream = audio_decoder.stream
    while bytes_sum < num_bytes:
      frame = audio_decoder.pop()
      if frame is None:
        break
      if timestamp is None:
        timestamp = frame.timestamp

      frame_data = frame.data.reshape((-1, audio_stream.channels))
      frame_data = frame_data[:, :MAX_AUDIO_CHANNELS]
      frames.append(frame_data)
      bytes_sum += frame_data.size * frame_data.dtype.itemsize

    if len(frames) == 0:
      return None

    assert AUDIO_FORMAT.is_packed
    data = np.concatenate(frames, axis=0)
    samples = data.shape[0]

    duration = Fraction(samples, audio_stream.sample_rate)
    if compensation_time != 0:
      max_comp_time = duration * MAX_COMPENSATION_RATIO
      comp_time = -Fraction(compensation_time)
      comp_time = int(math.copysign(1, comp_time)) * min(abs(comp_time), max_comp_time)
      duration = duration - comp_time

      layout = 'mono' if data.shape[1] == 1 else 'stereo'
      out_sample_rate = samples / (duration + comp_time)
      resampler = av.AudioResampler(format=AUDIO_FORMAT, layout=layout, rate=out_sample_rate)

      frame = av.AudioFrame.from_ndarray(data.reshape((1, -1)), AUDIO_FORMAT.name, layout)
      frame.sample_rate = audio_stream.sample_rate
      frame.time_base = audio_stream.time_base
      frames = resampler.resample(frame)

      data = [frame.to_ndarray() for frame in frames]
      data = np.concatenate(data, axis=1)

    data = data.tobytes()
    return AudioData(data, len(data), timestamp, duration, [])

  def get_next_video_timestamp(self):
    next_timestamp = self.decoders[MediaType.VIDEO].peek_next_timestamp()
    if next_timestamp is None:
      return math.inf
    return next_timestamp

  def get_next_video_frame(self, skip_empty_frame=True):
    frame = self.decoders[MediaType.VIDEO].pop()
    if frame is not None:
      image_data = frame.data
      height, width = image_data.shape[:2]
      self.last_video_frame = pyglet.image.ImageData(width, height, VIDEO_FORMAT_PYGLET,
                                                     image_data.tobytes(),
                                                     width * len(VIDEO_FORMAT_PYGLET))
    return self.last_video_frame
