import av
import math
import numpy as np
from enum import Enum
from threading import Thread, Lock, Condition
from fractions import Fraction
from bisect import bisect_left, bisect_right

from pyglet.image import ImageData
from pyglet.media import StreamingSource
from pyglet.media.codecs import AudioFormat, VideoFormat, AudioData

from jerboa.timeline import FragmentedTimeline
from .audio_buffer import AudioBuffer
from .video_buffer import VideoBuffer


class MediaType(Enum):
  AUDIO = 'audio'
  VIDEO = 'video'


VIDEO_FORMATS_MAP_PYGLET_TO_AV = {'RGB': 'rgb24'}
VIDEO_FORMAT_PYGLET = 'RGB'

AUDIO_FORMAT = av.AudioFormat('s16').packed
VIDEO_FORMAT = VIDEO_FORMATS_MAP_PYGLET_TO_AV[VIDEO_FORMAT_PYGLET]
AUDIO_MAX_LAYOUT = av.AudioLayout('stereo')

BUFFER_MAX_DURATION = 5.0  # in seconds
AUDIO_SEEK_THRESHOLD = 1.0  # in seconds
AUDIO_MAX_COMPENSATION = 0.1  # duration can be changed up to 10%
STOP_DECODING_SEEK_TIME = math.nan


def create_frame_buffer(stream: av.stream.Stream) -> AudioBuffer | VideoBuffer:
  if isinstance(stream, av.audio.AudioStream):
    layout = stream.layout
    if len(stream.layout.channels > len(AUDIO_MAX_LAYOUT.channels)):
      layout = AUDIO_MAX_LAYOUT

    return AudioBuffer(AUDIO_FORMAT, layout, stream.sample_rate, max_duration=BUFFER_MAX_DURATION)
  return VideoBuffer(VIDEO_FORMAT, max_duration=BUFFER_MAX_DURATION)


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

    self._seek_time: None | float = None
    self._waiting_for_seek = False

    self._buffer = create_frame_buffer(self.stream)

    self._timeline = init_timeline or FragmentedTimeline()

    self._dec_thread = Thread(target=self._decode,
                              name=f'Decoding #{self.stream.index} stream ({self.stream.type})',
                              daemon=True)
    self._dec_thread.start()

  def __del__(self):
    if hasattr(self, '_dec_thread') and self._dec_thread.is_alive():
      self.seek(STOP_DECODING_SEEK_TIME)

  def set_timeline(self, new_timeline: FragmentedTimeline):
    with self._mutex:
      self._timeline = new_timeline
      self._timeline_updated_or_seeking.notify_all()

  def seek(self, seek_time: float):
    with self._mutex:
      self._seek_time = seek_time
      self._waiting_for_seek = False
      self._buffer.clear()

      self._seeking.notify()
      self._buffer_not_full_or_seeking.notify()
      self._timeline_updated_or_seeking.notify()

  def _decode(self):
    keyframe_pts_arr = probe_keyframe_pts(self.container, self.stream)
    
    self._seek_time = self.start_time # start decoding from start
    while True:
      with self._mutex:
        self._waiting_for_seek = True
        self._seeking.wait_for(lambda: self._seek_time is not None)
        self._waiting_for_seek = False

        if self._seek_time == STOP_DECODING_SEEK_TIME:
          return

        min_frame_time = self._seek_time
        seek_timestamp = self._seek_time / self.stream.time_base
        self._seek_time = None

      self.container.seek(seek_timestamp, stream=self.stream)
      self._av_demux_and_decode(min_frame_time, keyframe_pts_arr)
      

  def _av_demux_and_decode(self, min_frame_time: float, keyframe_pts_arr: list[float] | None):
    for next_pkt in self.container.demux(self.stream):
      for next_frame in next_pkt.decode():
        if next_frame.time <= min_frame_time or current_frame is None:
          current_frame = next_frame
          continue

        frame_beg, frame_end = current_frame.time, next_frame.time
        with self._mutex:
          self._buffer_not_full_or_seeking.wait_for(
              lambda: self._buffer_duration < BUFFER_MAX_DURATION or self._seek_time is
              not None)
          self._timeline_updated_or_seeking.wait_for(
              lambda: self._timeline.time_scope >= frame_end or self._seek_time is not None)
          if self._seek_time is not None:
            break

          results, next_min_frame_time = self._timeline.map_time_range(frame_beg, frame_end)
          frame = preprocess_frame(current_frame, frame_beg, frame_end)

          keyframe_idx = bisect_right(keyframe_pts_arr, current_frame.pts)

          frame_duration = frame_end - frame_end
          if frame_duration > 0:
            self._buffer_duration += frame_duration
            self._buffer.put(frame)
            self._buffer_not_empty.notify()
          else:
            if (keyframe_pts_arr and abs(next_keyframe_idx - current_keyframe_idx)
                >= 1) or (not keyframe_pts_arr and
                          (next_min_frame_time - min_frame_time) >= AUDIO_SEEK_THRESHOLD):
              self.container.seek(next_min_frame_time * self.stream.time_base, stream=self.stream)
              break
          current_frame = next_frame
          current_keyframe_idx = next_keyframe_idx
          min_frame_time = next_min_frame_time
      else:
        continue
      break
    else:
      # TODO: flush current_frame
      self._waiting_for_seek = True

  def is_done(self) -> bool:
    return self._waiting_for_seek

  def pop(self) -> np.ndarray:
    frame = None
    with self._mutex:
      self._buffer_not_empty.wait_for(lambda: self._buffer or self.is_done())
      if not self.is_done():
        frame = self._buffer.pop()
        self._buffer_not_full_or_seeking.notify()
    return frame

  def peek_next_timepoint(self) -> float | None:
    with self._mutex:
      self._buffer_not_empty.wait_for(lambda: len(self._buffer) > 0 or self.is_done())
      if self.is_done():
        return None
      return self._buffer.peek_timepoint()


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
                                    FragmentedTimeline(TimelineSection(-math.inf, math.inf, 1.0)))
      self.decoders[MediaType.AUDIO] = audio_decoder

      audio_stream = audio_decoder.stream
      self._audio_format = AudioFormat(channels=min(MAX_AUDIO_CHANNELS, audio_stream.channels),
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
    self.last_video_frame: ImageData = None

  def __del__(self):
    self.container.close()

  def seek(self, timepoint: float):
    for decoder in self.decoders.values():
      decoder.seek(timepoint)

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
      max_compensation_time = duration * MAX_COMPENSATION_RATIO
      compensation_time = -Fraction(compensation_time)
      compensation_time = (int(math.copysign(1, compensation_time)) *
                           min(abs(compensation_time), max_compensation_time))
      duration = duration - compensation_time

      layout = audio_stream.layout
      out_sample_rate = samples / (duration + compensation_time)
      # todo: use librosa to resample
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
    next_timepoint = self.decoders[MediaType.VIDEO].peek_next_timepoint()
    if next_timepoint is None:
      return math.inf
    return next_timepoint

  def get_next_video_frame(self, skip_empty_frame=True):
    frame = self.decoders[MediaType.VIDEO].pop()
    if frame is not None:
      image_data = frame.data
      height, width = image_data.shape[:2]
      self.last_video_frame = ImageData(width, height, VIDEO_FORMAT_PYGLET, image_data.tobytes(),
                                        width * len(VIDEO_FORMAT_PYGLET))
    return self.last_video_frame
