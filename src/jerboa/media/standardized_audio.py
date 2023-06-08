import av
import math
import soxr
import numpy as np
from pylibrb import DType, SAMPLES_AXIS, CHANNELS_AXIS
from scipy.special import expit

from .media import AudioConfig
from jerboa.utils.circular_buffer import CircularBuffer

FORMAT = av.AudioFormat('flt').planar
assert DType == np.float32 and DType == np.dtype(av.audio.frame.format_dtypes[FORMAT.name])

BUFFER_SIZE_MODIFIER = 1.2
COMPENSATION_MAX_DURATION_CHANGE = 0.1  # up to 10% at once

AUDIO_TRANSITION_DURATION = 8.0 / 16000  # 8 steps when sample_rate == 16000


def get_format_dtype(fmt: av.AudioFormat) -> np.dtype:
  return np.dtype(av.audio.frame.format_dtypes[fmt.name])


def get_from_frame(frame: av.AudioFrame) -> np.ndarray:
  assert frame.format.name == FORMAT.name
  return frame.to_ndarray()


def to_real_audio(audio: np.ndarray, fmt: av.AudioFormat) -> np.ndarray:
  if fmt.is_packed:
    audio = audio.T.reshape((1, -1))

  wanted_dtype = np.dtype(av.audio.frame.format_dtypes[fmt.name])
  if wanted_dtype != DType:
    assert np.issubdtype(DType, np.floating)
    wanted_dtype_info = np.iinfo(wanted_dtype)
    if wanted_dtype_info.min >= 0:
      audio += 1.0
      audio /= 2.0
    audio *= wanted_dtype_info.max
    audio = audio.astype(wanted_dtype_info)
  return audio


def get_shape(samples: int, channels: int) -> tuple:
  data_shape = [0, 0]
  data_shape[SAMPLES_AXIS] = samples
  data_shape[CHANNELS_AXIS] = channels
  return tuple(data_shape)


def index_samples(beg_idx: int, end_idx: int) -> tuple:
  indices = [slice(None), slice(None)]
  indices[SAMPLES_AXIS] = slice(beg_idx, end_idx)
  return tuple(indices)


def calc_duration(audio: np.ndarray, sample_rate: int) -> float:
  return audio.shape[SAMPLES_AXIS] / float(sample_rate)


def smooth_out_transition(last_sample: np.ndarray, audio: np.ndarray, steps: int) -> None:
  steps = min(audio.shape[SAMPLES_AXIS], steps)
  weights = expit(np.linspace(-5, 5, steps).reshape(get_shape(steps, 1)))
  samples_idx = index_samples(0, steps)
  audio[samples_idx] = weights * audio[samples_idx] + (1.0 - weights) * last_sample


def compensated(audio: np.ndarray, sample_rate: int, compensation_time: float) -> np.ndarray:
  if compensation_time == 0.0:
    return audio

  duration = calc_duration(audio, sample_rate)
  max_change = duration * COMPENSATION_MAX_DURATION_CHANGE

  change = math.copysign(min(abs(compensation_time), max_change), compensation_time)

  new_sample_rate = round(audio.shape[SAMPLES_AXIS] / (duration - change))

  return resampled(audio, sample_rate, new_sample_rate)


def resampled(audio: np.ndarray, current_sample_rate: int, new_sample_rate: int) -> np.ndarray:
  return soxr.resample(audio.T, current_sample_rate, new_sample_rate, quality=soxr.HQ).T


def create_circular_buffer(audio_config: AudioConfig, max_duration: float = None) -> CircularBuffer:
  if max_duration is None:
    max_duration = audio_config.frame_duration

  samples_num = int(max_duration * audio_config.sample_rate * BUFFER_SIZE_MODIFIER)
  buffer_shape = get_shape(samples_num, audio_config.channels_num)
  buffer_dtype = get_format_dtype(audio_config.format)
  return CircularBuffer(buffer_shape, SAMPLES_AXIS, buffer_dtype)


def get_transition_steps(sample_rate: int) -> int:
  return int(math.ceil(AUDIO_TRANSITION_DURATION * sample_rate))
