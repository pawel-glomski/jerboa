import numpy as np
from collections import deque

from jerboa.media import normalized_audio
from .stretchers import StretchedFrame
from .media import MediaType, AudioConfig, VideoConfig


class AudioBuffer:

  def __init__(self, audio_config: AudioConfig, max_duration: float) -> None:
    self._audio_config = audio_config

    self._audio = normalized_audio.create_circular_buffer(audio_config, max_duration)
    self._audio_last_sample = np.zeros(self._audio.get_shape_for_data(1), self._audio.dtype)
    self._timepoint = None

    self._max_samples = int(max_duration * audio_config.sample_rate)

  def __len__(self) -> int:
    return len(self._audio)

  @property
  def duration(self) -> float:
    return len(self._audio) / self._audio_config.sample_rate

  def clear(self) -> None:
    self._audio.clear()
    self._audio_last_sample[:] = 0
    self._timepoint = None

  def put(self, stretched_audio_frame: StretchedFrame) -> None:
    assert stretched_audio_frame.duration > 0
    assert stretched_audio_frame.data.size > 0
    assert not self.is_full()

    if self._timepoint is None:
      self._timepoint = stretched_audio_frame.timepoint

    self._audio.put(stretched_audio_frame.data)
    self._audio_last_sample[:] = self._audio[-1]

  def pop(self, samples_num: int) -> np.ndarray:
    assert not self.is_empty()

    all_samples_num = len(self._audio)
    pop_samples_num = min(all_samples_num, samples_num)

    audio = self._audio.pop(pop_samples_num)
    audio_duration = normalized_audio.calc_duration(audio, self._audio_config.sample_rate)

    self._timepoint += audio_duration
    return audio

  def get_next_timepoint(self) -> float | None:
    return self._timepoint

  def is_empty(self) -> bool:
    return len(self) == 0

  def is_full(self) -> bool:
    return len(self) >= self._max_samples


class VideoBuffer:

  def __init__(self, max_duration: float) -> None:
    self._max_duration = max_duration
    self._duration = 0.0

    self._frames = deque[StretchedFrame]()

  def __len__(self) -> int:
    return len(self._frames)

  @property
  def duration(self) -> float:
    return self._duration

  def clear(self) -> None:
    self._frames.clear()
    self._duration = 0.0

  def put(self, stretched_video_frame: StretchedFrame) -> None:
    assert not self.is_full()
    assert stretched_video_frame.duration > 0

    self._frames.append(stretched_video_frame)
    self._duration += stretched_video_frame.duration

  def pop(self) -> np.ndarray:
    assert not self.is_empty()

    frame = self._frames.popleft()
    self._duration -= frame.duration
    self._duration *= (not self.is_empty())  # ensure _duration == 0 when is_empty() == true
    return frame.data

  def get_next_timepoint(self) -> float:
    return self._frames[0].timepoint

  def is_empty(self) -> bool:
    return len(self) == 0

  def is_full(self) -> bool:
    return self._duration >= self._max_duration


def create_buffer(media_config: AudioConfig | VideoConfig,
                  buffer_duration: float) -> AudioBuffer | VideoBuffer:
  if media_config.media_type == MediaType.AUDIO:
    return AudioBuffer(media_config, max_duration=buffer_duration)
  return VideoBuffer(max_duration=buffer_duration)
