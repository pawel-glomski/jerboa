from typing import Callable

import av
import math
import numpy as np
from gmpy2 import mpq as FastFraction
from pylibrb import (  # pylint: disable=unused-import
    DType,
    SAMPLES_AXIS,
    CHANNELS_AXIS,
    create_audio_array,
)

from jerboa.media.core import AudioConstraints


SAMPLE_FORMAT_JB = AudioConstraints.SampleFormat.F32
SAMPLE_FORMAT_AV = av.AudioFormat("flt").planar
assert DType == np.float32 and DType == np.dtype(
    av.audio.frame.format_dtypes[SAMPLE_FORMAT_AV.name]
)

# bigger frames are faster - less conversions to numpy and less iterations on the python side
# usually 1 second gives good results, bigger than that may actually slow things down
FRAME_DURATION = 1.0  # in seconds

TRANSITION_DURATION = 8.0 / 16000  # in seconds, 8 steps when sample_rate == 16000


def get_from_frame(frame: av.AudioFrame) -> np.ndarray:
    assert frame.format.name == SAMPLE_FORMAT_AV.name and SAMPLE_FORMAT_AV.planar
    # this is faster than frame.to_ndarray
    return np.vstack([np.frombuffer(x, dtype=DType, count=frame.samples) for x in frame.planes])


def reformat(audio: np.ndarray, wanted_dtype: np.dtype, packed: bool = False) -> np.ndarray:
    if packed:
        audio = audio.T.reshape((-2, 2))

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
    from scipy.special import expit

    steps = min(audio.shape[SAMPLES_AXIS], steps)
    weights = expit(np.linspace(-5, 5, steps).reshape(get_shape(steps, 1)))
    samples_idx = index_samples(0, steps)
    audio[samples_idx] = weights * audio[samples_idx] + (1.0 - weights) * last_sample


def get_transition_steps(sample_rate: int) -> int:
    return int(math.ceil(TRANSITION_DURATION * sample_rate))
