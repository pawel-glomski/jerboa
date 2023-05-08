import av
import math
import pytsmod
import numpy as np

from jerboa.utils.circular_buffer import CircularBuffer
from jerboa.timeline import RangeMappingResult


class AudioBuffer:
  SAMPLE_IDX = 0
  CHANNEL_IDX = 1
  TRANSITION_DURATION = 16.0 / 16000  # 16 steps when sample_rate == 16000
  STAGE_DURATION = 1.0  # in seconds

  def __init__(self, fmt: av.AudioFormat, layout: av.AudioLayout, sample_rate: int,
               max_duration: float) -> None:
    self._format = fmt
    self._layout = layout
    self._sample_rate = sample_rate
    # self.graphs = [
    #     AudioBuffer.create_graph(mod, fmt, sample_rate, layout)
    #     for mod in PLAYBACK_MODIFIERS
    #     if mod < math.inf
    # ]

    self._max_samples = int(max_duration * sample_rate)
    self._target_stage_samples = int(AudioBuffer.STAGE_DURATION * sample_rate)

    self._transition_steps = int(math.ceil(AudioBuffer.TRANSITION_DURATION * sample_rate))

    buffer_dtype = np.dtype(av.audio.frame.format_dtypes[fmt.name])

    buffer_shape = AudioBuffer.get_audio_data_shape(samples=int(1.25 * self._max_samples),
                                                    channels=len(self._layout.channels))
    self._audio = CircularBuffer(buffer_shape, AudioBuffer.SAMPLE_IDX, buffer_dtype)
    self._audio_last_sample = np.zeros(self._audio.get_shape_for_data(1), buffer_dtype)
    self._audio_beg_timepoint = 0.0
    self._audio_end_timepoint = 0.0

    stage_shape = AudioBuffer.get_audio_data_shape(samples=int(1.25 * self._target_stage_samples),
                                                   channels=len(self._layout.channels))
    self._staged_audio = CircularBuffer(stage_shape, AudioBuffer.SAMPLE_IDX, buffer_dtype)
    self._staged_audio_modifiers = [-1]  # start with some impossible to encounter modifier
    self._staged_audio_anchors_before = [0]
    self._staged_audio_anchors_after = [0]
    self._staged_audio_end_timepoint = 0.0

  def __len__(self) -> int:
    return len(self._audio)

  def clear(self) -> None:
    self.clear_stage()
    self._audio.clear()
    self._audio_last_sample[:] = 0
    self._audio_beg_timepoint = self._audio_end_timepoint = 0.0

  def clear_stage(self) -> None:
    self._staged_audio.clear()
    self._staged_audio_modifiers = [-1]
    self._staged_audio_anchors_before = [0]
    self._staged_audio_anchors_after = [0]
    self._staged_audio_end_timepoint = 0.0

  def stage(self, frame: av.AudioFrame, mapping_results: RangeMappingResult):
    frame_audio = AudioBuffer.get_audio_from_frame(frame)
    frame_audio = frame_audio[:, :len(self._layout.channels)]  # drop any extra channels

    last_sample = self._staged_audio[-1] if len(self._staged_audio) else self._audio_last_sample
    for section in mapping_results.sections:
      sample_idx_beg = int((section.beg - frame.time) * self._sample_rate)
      sample_idx_end = int((section.end - frame.time) * self._sample_rate)
      audio_part = frame_audio[AudioBuffer.index_samples(sample_idx_beg, sample_idx_end)]

      if audio_part.size > 0:
        AudioBuffer.prepare_for_concat(audio_part, last_sample, self._transition_steps)
        last_sample = self._stage(audio_part, section.modifier, section.end)

    if (len(self._staged_audio) >= self._target_stage_samples and
        self._staged_audio_anchors_before[-1] != self._staged_audio_anchors_after[-1]):
      anchors = np.array([self._staged_audio_anchors_before, self._staged_audio_anchors_after])
      audio_before = self._unstage_all()
      audio_after = pytsmod.hptsm(audio_before.T, anchors).T

      # TODO: consider adding last ~512 samples during Time-Scale Modification for better continuity
      AudioBuffer.prepare_for_concat(audio_after, self._audio_last_sample, self._transition_steps)

      self._stage(audio_after, 1.0, mapping_results.end)  # ready for commit

  def _stage(self, audio: np.ndarray, modifier: float, end_timepoint: float):
    samples_num = audio.shape[AudioBuffer.SAMPLE_IDX]
    if self._staged_audio_modifiers[-1] == modifier:
      self._staged_audio_anchors_before[-1] += samples_num
      self._staged_audio_anchors_after[-1] += round(samples_num * modifier)
    else:
      self._staged_audio_anchors_before.append(self._staged_audio_anchors_before[-1] + samples_num)
      self._staged_audio_anchors_after.append(self._staged_audio_anchors_after[-1] +
                                              round(samples_num * modifier))
      self._staged_audio_modifiers.append(modifier)

    self._staged_audio_end_timepoint = end_timepoint
    self._staged_audio.put(audio)
    return self._staged_audio[-1]

  def _unstage_all(self) -> np.ndarray:
    staged_audio = self._staged_audio.pop(len(self._staged_audio))
    self.clear_stage()
    return staged_audio

  def commit(self) -> None:
    if self._staged_audio_modifiers[-1] == 1.0:
      self._audio_end_timepoint = self._staged_audio_end_timepoint
      self._audio.put(self._unstage_all())

  def pop(self, bytes_num: int, new_sample_rate: int | None = None) -> np.ndarray:
    all_samples_num = len(self._audio)
    pop_samples_num = min(all_samples_num, int(bytes_num / self._audio.dtype.itemsize))

    audio = self._audio.pop(pop_samples_num)

    # to be consistent with the timeline, use the timeline timepoints to calculate the current
    # timepoint, instead of calculating the duration of the popped audio (popped_samples / sr)
    fraction = pop_samples_num / all_samples_num
    self._audio_beg_timepoint += fraction * (self._audio_end_timepoint - self._audio_beg_timepoint)

    if new_sample_rate:
      audio = AudioBuffer.resample(audio, new_sample_rate)
    return AudioBuffer.reorder_to_format(audio, self._format)

  def get_current_timepoint(self) -> float:
    return self._audio_beg_timepoint

  def is_empty(self) -> bool:
    return len(self) == 0

  def is_full(self) -> bool:
    return len(self) >= self._max_samples

  @staticmethod
  def resample(buffer_audio: np.ndarray, new_sr: int) -> np.ndarray:
    return buffer_audio  # TODO: use librosa/scipy to resample

  @staticmethod
  def reorder_to_format(buffer_audio: np.ndarray, fmt: av.AudioFormat) -> np.ndarray:
    if fmt.is_planar:
      return buffer_audio.T
    return buffer_audio.reshape((1, -1))

  @staticmethod
  def get_audio_data_shape(samples: int, channels: int) -> tuple:
    data_shape = [0, 0]
    data_shape[AudioBuffer.SAMPLE_IDX] = samples
    data_shape[AudioBuffer.CHANNEL_IDX] = channels
    return tuple(data_shape)

  @staticmethod
  def get_audio_from_frame(frame: av.AudioFrame) -> np.ndarray:
    frame_audio = frame.to_ndarray()
    if frame.format.is_planar:
      return frame_audio.T
    return frame_audio.reshape((-1, len(frame.layout.channels)))

  @staticmethod
  def index_samples(beg_idx: int, end_idx: int) -> tuple:
    indices = [slice(None), slice(None)]
    indices[AudioBuffer.SAMPLE_IDX] = slice(beg_idx, end_idx)
    return tuple(indices)

  @staticmethod
  def prepare_for_concat(buffer_audio: np.ndarray, last_sample: np.ndarray, steps: int):
    weights = np.linspace(0, 1, steps).reshape(AudioBuffer.get_audio_data_shape(steps, 1))
    weights = weights[AudioBuffer.index_samples(
        0, min(steps, buffer_audio.shape[AudioBuffer.SAMPLE_IDX]))]
    samples_idx = AudioBuffer.index_samples(0, steps)
    buffer_audio[samples_idx] = weights * buffer_audio[samples_idx] + (1.0 - weights) * last_sample
