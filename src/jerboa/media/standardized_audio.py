from typing import Callable

import av
import math
import numpy as np
from fractions import Fraction
from pylibrb import DType, SAMPLES_AXIS, CHANNELS_AXIS, create_audio_array
from scipy.special import expit

from jerboa.media.core import MediaType

FORMAT = av.AudioFormat("flt").planar
assert DType == np.float32 and DType == np.dtype(av.audio.frame.format_dtypes[FORMAT.name])

# bigger frames are faster - less conversions to numpy and less iterations on the python side
# usually 1 second gives good results, bigger than that may actually slow things down
FRAME_DURATION = 1.0  # in seconds

TRANSITION_DURATION = 8.0 / 16000  # in seconds, 8 steps when sample_rate == 16000

COMPENSATION_MAX_DURATION_CHANGE = 0.1  # up to 10% at once


def get_time_base(audio_stream: av.audio.AudioStream) -> Fraction:
    assert audio_stream.type == MediaType.AUDIO.value
    return Fraction(1, audio_stream.sample_rate)


def get_frame_time_base_standardizer(
    audio_stream: av.audio.AudioStream,
) -> Callable[[av.AudioFrame], None]:
    assert audio_stream.type == MediaType.AUDIO.value

    std_time_base = get_time_base(audio_stream)
    if audio_stream.time_base == std_time_base:
        return lambda _: ...  # do nothing when time base is already correct

    def standardize_audio_frame_time_base(frame: av.AudioFrame):
        frame.pts = int(frame.pts * frame.time_base / std_time_base)
        frame.time_base = std_time_base

    return standardize_audio_frame_time_base


def get_end_pts_generator(audio_stream: av.audio.AudioStream) -> Callable[[av.AudioFrame], int]:
    std_time_base = get_time_base(audio_stream)

    def audio_pts_gen_simple_timebase(frame: av.AudioFrame) -> int:
        assert frame.time_base == std_time_base
        return frame.pts + frame.samples

    return audio_pts_gen_simple_timebase
    # def audio_pts_gen_any_timebase(frame: av.AudioFrame, _) -> int:
    #   return frame.pts + int(Fraction(frame.samples, frame.sample_rate) / frame.time_base)
    # return audio_pts_gen_any_timebase


def get_from_frame(frame: av.AudioFrame) -> np.ndarray:
    assert frame.format.name == FORMAT.name
    return frame.to_ndarray()


def get_format_dtype(fmt: av.AudioFormat) -> np.dtype:
    return np.dtype(av.audio.frame.format_dtypes[fmt.name])


def to_real_audio(audio: np.ndarray, fmt: av.AudioFormat) -> np.ndarray:
    if fmt.is_packed:
        audio = audio.T.reshape((-2, 2))

    wanted_dtype = get_format_dtype(fmt)
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


def get_transition_steps(sample_rate: int) -> int:
    return int(math.ceil(TRANSITION_DURATION * sample_rate))
