import av.audio
import math
import librosa
import numpy as np
from scipy.special import expit

from jerboa.utils.circular_buffer import CircularBuffer

SAMPLE_IDX = 0
CHANNEL_IDX = 1

BUFFER_SIZE_MODIFIER = 1.2
COMPENSATION_MAX_DURATION_CHANGE = 0.5  # up to 10% at once

AUDIO_TRANSITION_DURATION = 8.0 / 16000  # 8 steps when sample_rate == 16000


def get_from_frame(frame: av.AudioFrame) -> np.ndarray:
  frame_audio = frame.to_ndarray()
  if frame.format.is_planar:
    return frame_audio.T
  return frame_audio.reshape((-1, len(frame.layout.channels)))


def to_real_audio(audio: np.ndarray, fmt: av.AudioFormat) -> np.ndarray:
  if fmt.is_planar and CHANNEL_IDX == 1:
    return audio.T
  return audio.reshape((1, -1))


def get_shape(samples: int, channels: int) -> tuple:
  data_shape = [0, 0]
  data_shape[SAMPLE_IDX] = samples
  data_shape[CHANNEL_IDX] = channels
  return tuple(data_shape)


def index_samples(beg_idx: int, end_idx: int) -> tuple:
  indices = [slice(None), slice(None)]
  indices[SAMPLE_IDX] = slice(beg_idx, end_idx)
  return tuple(indices)


def calc_duration(audio: np.ndarray, sample_rate: int) -> float:
  return audio.shape[SAMPLE_IDX] / float(sample_rate)


def smooth_out_transition(last_sample: np.ndarray, audio: np.ndarray, steps: int) -> None:
  steps = min(audio.shape[SAMPLE_IDX], steps)
  weights = expit(np.linspace(-3, 3, steps).reshape(get_shape(steps, 1)))
  samples_idx = index_samples(0, steps)
  audio[samples_idx] = weights * audio[samples_idx] + (1.0 - weights) * last_sample


def compensated(audio: np.ndarray, sample_rate: int, compensation_time: float) -> np.ndarray:
  if compensation_time == 0.0:
    return audio

  duration = calc_duration(audio, sample_rate)
  max_change = duration * COMPENSATION_MAX_DURATION_CHANGE

  change = math.copysign(min(abs(compensation_time), max_change), compensation_time)

  new_sample_rate = round(audio.shape[SAMPLE_IDX] / (duration - change))

  return resampled(audio, sample_rate, new_sample_rate)


def resampled(audio: np.ndarray, current_sample_rate: int, new_sample_rate: int) -> np.ndarray:
  return librosa.resample(audio.astype(np.float64),
                          axis=SAMPLE_IDX,
                          orig_sr=current_sample_rate,
                          target_sr=new_sample_rate).astype(audio.dtype)


def create_circular_buffer(fmt: av.AudioFormat, layout: av.AudioLayout, sample_rate: int,
                           max_duration: float) -> CircularBuffer:
  samples_num = int(max_duration * sample_rate * BUFFER_SIZE_MODIFIER)
  channels_num = len(layout.channels)
  buffer_shape = get_shape(samples_num, channels_num)
  buffer_dtype = np.dtype(av.audio.frame.format_dtypes[fmt.name])
  return CircularBuffer(buffer_shape, SAMPLE_IDX, buffer_dtype)


def get_transition_steps(sample_rate: int) -> int:
  return int(math.ceil(AUDIO_TRANSITION_DURATION * sample_rate))
