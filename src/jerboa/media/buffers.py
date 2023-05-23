import numpy as np
from collections import deque

from jerboa.media import normalized_audio
from .mappers import MappedNumpyFrame
from .media import MediaType, AudioConfig, VideoConfig


class AudioBuffer:

  def __init__(self, audio_config: AudioConfig, max_duration: float) -> None:
    self._audio_config = audio_config

    self._audio = normalized_audio.create_circular_buffer(audio_config, max_duration)
    self._audio_last_sample = np.zeros(self._audio.get_shape_for_data(1), self._audio.dtype)
    self._audio_beg_timepoint = None
    self._audio_end_timepoint = None

    self._max_samples = int(max_duration * audio_config.sample_rate)
    self._transition_steps = normalized_audio.get_transition_steps(audio_config.sample_rate)

  def __len__(self) -> int:
    return len(self._audio)

  @property
  def duration(self) -> float:
    return len(self._audio) / self._audio_config.sample_rate

  def clear(self) -> None:
    self._audio.clear()
    self._audio_last_sample[:] = 0
    self._audio_beg_timepoint = None
    self._audio_end_timepoint = None

  def put(self, mapped_audio_frame: MappedNumpyFrame) -> None:
    assert mapped_audio_frame.beg_timepoint < mapped_audio_frame.end_timepoint
    assert mapped_audio_frame.data.size > 0
    assert not self.is_full()

    # if mapped_audio_frame.beg_timepoint != self._audio_end_timepoint:
    # normalized_audio.smooth_out_transition(self._audio_last_sample, mapped_audio_frame.data,
    #                                        self._transition_steps)

    if self._audio_beg_timepoint is None:
      self._audio_beg_timepoint = mapped_audio_frame.beg_timepoint
    self._audio_end_timepoint = mapped_audio_frame.end_timepoint

    self._audio.put(mapped_audio_frame.data)
    self._audio_last_sample[:] = self._audio[-1]

  def pop(self, bytes_num: int) -> np.ndarray:
    assert not self.is_empty()

    all_samples_num = len(self._audio)
    pop_samples_num = min(all_samples_num, int(bytes_num / self._audio.dtype.itemsize))

    audio = self._audio.pop(pop_samples_num)

    # to be consistent with the timeline, use the timeline timepoints to calculate the current
    # timepoint, instead of calculating the duration of the returned audio (pop_samples_num / sr)
    fraction = pop_samples_num / all_samples_num
    self._audio_beg_timepoint += fraction * (self._audio_end_timepoint - self._audio_beg_timepoint)

    return audio

  def get_next_timepoint(self) -> float | None:
    return self._audio_beg_timepoint

  def is_empty(self) -> bool:
    return len(self) == 0

  def is_full(self) -> bool:
    return len(self) >= self._max_samples


class VideoBuffer:

  def __init__(self, max_duration: float) -> None:
    self._max_duration = max_duration
    self._duration = 0.0

    self._frames = deque[MappedNumpyFrame]()

  def __len__(self) -> int:
    return len(self._frames)

  @property
  def duration(self) -> float:
    return self._duration

  def clear(self) -> None:
    self._frames.clear()
    self._duration = 0.0

  def put(self, mapped_video_frame: MappedNumpyFrame) -> None:
    assert not self.is_full()
    assert mapped_video_frame.beg_timepoint < mapped_video_frame.end_timepoint

    self._frames.append(mapped_video_frame)
    self._duration += mapped_video_frame.end_timepoint - mapped_video_frame.beg_timepoint

  def pop(self) -> np.ndarray:
    assert not self.is_empty()

    frame = self._frames.popleft()
    self._duration -= frame.end_timepoint - frame.beg_timepoint
    self._duration *= (not self.is_empty())  # ensure _duration == 0 when is_empty() == true
    return frame.data

  def get_next_timepoint(self) -> float:
    return self._frames[0].beg_timepoint

  def is_empty(self) -> bool:
    return len(self) == 0

  def is_full(self) -> bool:
    return self._duration >= self._max_duration


def create_buffer(media_config: AudioConfig | VideoConfig,
                  buffer_duration: float) -> AudioBuffer | VideoBuffer:
  if media_config.media_type == MediaType.AUDIO:
    return AudioBuffer(media_config, max_duration=buffer_duration)
  return VideoBuffer(max_duration=buffer_duration)
