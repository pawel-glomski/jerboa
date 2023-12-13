import textwrap
import pydantic

from jerboa.core.signal import Signal
from jerboa.core.multithreading import Task
from jerboa.analysis import algorithm as alg
from jerboa.media.readers.audio import AudioReader
from jerboa.media.core import AudioConfig, AudioChannelLayout, AudioSampleFormat

import jerboa.analysis.utils.environment as env_utils


PROCESSING_AUDIO_SAMPLE_FORMAT = AudioSampleFormat(AudioSampleFormat.DataType.F32, is_planar=True)
PROCESSING_AUDIO_CHANNEL_LAYOUT = AudioChannelLayout.LAYOUT_MONO
PROCESSING_AUDIO_SAMPLE_RATE = 16000
PROCESSING_AUDIO_CONFIG = AudioConfig(
    sample_format=PROCESSING_AUDIO_SAMPLE_FORMAT,
    channel_layout=PROCESSING_AUDIO_CHANNEL_LAYOUT,
    sample_rate=PROCESSING_AUDIO_SAMPLE_RATE,
    frame_duration=None,  # use the default
)

PROCESSING_FRAME_SAMPLES = 1024


class Environment(alg.Environment):
    # use_librosa: bool = False

    def prepare(self, executor: Task.Executor, progress_update_signal: Signal) -> None:
        executor.exit_if_aborted()
        dependencies = {env_utils.Package("numpy", ">=", "1.2")}
        # if self.use_librosa:
        #     dependencies.add(env_utils.Package("librosa", ">=", "0.10"))

        progress_update_signal.emit(progress=0.1, message="Downloading dependencies...")
        env_utils.pip_install(dependencies, executor=executor)
        progress_update_signal.emit(progress=0.99, message="Downloaded dependencies")


class AnalysisParams(alg.AnalysisParams):
    int_param: int = pydantic.Field(
        default=2,
        ge=2,
        le=10,
        description="This is an int param",
    )


class InterpretationParams(alg.InterpretationParams):
    float_param: float = pydantic.Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="This is a float param",
    )
    str_param: str = pydantic.Field(
        default="abcd",
        description="This is a str param",
    )


class Implementation(alg.Implementation):
    def __init__(
        self,
        analysis_params: AnalysisParams,
        interpretation_params: InterpretationParams,
    ):
        super().__init__()
        self._analysis_params = analysis_params
        self._interpretation_params = interpretation_params
        self._audio_reader = AudioReader(PROCESSING_AUDIO_CONFIG)

    def update_interpretation_params(self, params: InterpretationParams) -> None:
        raise NotImplementedError()

    def analyze(self) -> None:
        raise NotImplementedError()

    def interpret(self, file) -> None:
        for section in self._audio_reader.read_stream(file, stream_idx=0):
            ...


ALGORITHM = alg.Algorithm(
    name="Redundancy remover",
    description=textwrap.dedent(
        """\
        Removes redundancy in the audio using spectrogram analysis.
        Very fast and very low memory requirements."""
    ),
    environment=Environment(),
    analysis_params_class=AnalysisParams,
    interpretation_params_class=InterpretationParams,
    implementation_class=Implementation,
)


# class Algorithm(analysis.algorithm.Algorithm):
#     NAME = "Redundancy remover"
#     DESCRIPTION = "Removes redundancy in the audio using spectrogram analysis."

#     min_sound_len = analysis.parameter.Integer(
#         default_value=2,
#         min_value=2,
#         max_value=10,
#         description="Determines what energy levels should be considered a silence",
#         domain=analysis.parameter.Domain.ANALYSIS,
#     )
#     min_silence_len = analysis.parameter.String(
#         default_value="abcd",
#         description="Determines what energy levels should be considered a silence",
#         domain=analysis.parameter.Domain.ANALYSIS,
#     )
#     redundancy_threshold = analysis.parameter.Float(
#         default_value=0.5,
#         min_value=0,
#         max_value=1,
#         description="Determines what energy levels should be considered a silence",
#         domain=analysis.parameter.Domain.INTERPRETATION,
#     )

#     def initialize(self):
#         ...

#     def interpret(self, file):
#         ...

#     def analyze(self):
#         ...


# # import numpy as np

# # from logging import Logger
# # from argparse import ArgumentParser

# # # from librosa import power_to_db
# # # from librosa.feature import melspectrogram
# # from scipy.signal import convolve2d as conv2d
# # from scipy.stats import entropy as kl_div
# # from scipy.special import softmax

# # from jerboa.analysis.analysis import AnalysisMethod
# # from jerboa.media.readers.audio import AudioReader
# # from jerboa.core.timeline import FragmentedTimeline
# # from jerboa.core.logger import NULL_LOGGER
# # from jerboa.core.jbmath import ranges_of_truth, kernel_2d_from_window

# # SR = 16000
# # NFFT = 256
# # HOP = NFFT // 1
# # SPEC_POWER = 0.2
# # SPEC_NORM_MAX = 9

# # MIN_AMPLITUDE = 3
# # SOUND_POINT = 15  # number of freq with amplitude > 0 (after transformations)

# # REDUNDANCY_THRESHOLD = 0.005
# # MIN_SILENCE_LEN = int(0.1 * SR / HOP + 0.5)
# # MIN_SOUND_LEN = MIN_SILENCE_LEN


# # class Algorithm(AnalysisMethod):
# #     def __init__(
# #         self,
# #         th_ratio: float,
# #         dur_multi: float,
# #         silence_len: int,
# #         logger: Logger = NULL_LOGGER,
# #     ):
# #         """Spectrogram based analysis method. This method looks at features of 2 adjacent timesteps and
# #         removes segments, for which the difference is small, thus reducing redundance in the signal.
# #         This method will remove silence and prolongations of sounds, syllables, words, or phrases.

# #         Args:
# #             th_ratio (float): Threshold ratio: the greater the value, the more aggressive the cuts.
# #             dur_multi (float): Duration multiplier of segments selected for removal.
# #             silence_len (int): Desired length of silence as a number of segments.
# #             logger (Logger, optional): Logger for messages. Defaults to NULL_LOGGER.
# #         """
# #         super().__init__("Spectrogram Analysis", logger)
# #         self.th_ratio = th_ratio
# #         self.dur_multi = dur_multi
# #         self.silence_len = silence_len
# #         self.logger = logger

# #     def analyze(self, recording_path: str, _) -> FragmentedTimeline:
# #         signal, _ = read_entire_audio(recording_path, sample_rate=SR, mono=True, logger=self.logger)
# #         spec = SpectrogramAnalysis.make_spectrogram(signal[0])
# #         is_sound = SpectrogramAnalysis.find_sound_and_silence(spec)
# #         redundancy = SpectrogramAnalysis.redundancy(spec)
# #         cls_segments = self.classify(is_sound, redundancy)

# #         changes = ranges_of_truth(cls_segments == False) * HOP / SR
# #         changes = np.concatenate([changes, np.ones((changes.shape[0], 1)) * self.dur_multi], axis=1)
# #         return FragmentedTimeline(changes)

# #     def classify(self, is_sound: np.ndarray, redundancy: np.ndarray) -> np.ndarray:
# #         cls = redundancy >= REDUNDANCY_THRESHOLD * self.th_ratio
# #         cls = cls & is_sound

# #         # filter out very small silence segments
# #         ranges = ranges_of_truth(cls == False)
# #         ranges = ranges[(ranges[:, 1] - ranges[:, 0]) >= MIN_SILENCE_LEN]
# #         cls[:] = True
# #         for r in ranges:
# #             cls[r[0] : r[1]] = False

# #         # cut out very small sound segments
# #         ranges = ranges_of_truth(cls)
# #         ranges = ranges[(ranges[:, 1] - ranges[:, 0]) >= MIN_SOUND_LEN]
# #         cls[:] = False
# #         for r in ranges:
# #             cls[r[0] : r[1]] = True

# #         # keep the silence
# #         silence_ranges = ranges_of_truth(is_sound == False)
# #         redundancy_ranges = ranges_of_truth(cls == False)
# #         red_idx = 0
# #         for silence_range in silence_ranges:
# #             sil_beg, sil_end = silence_range
# #             while red_idx < len(redundancy_ranges):
# #                 red_beg, red_end = redundancy_ranges[red_idx]
# #                 common_beg = max(sil_beg, red_beg)
# #                 common_end = min(sil_end, red_end)
# #                 if common_end - common_beg > 0:
# #                     if common_end - common_beg > self.silence_len:
# #                         cls[common_end - self.silence_len : common_end] = True
# #                     red_idx += 1
# #                 elif red_beg < sil_beg:
# #                     red_idx += 1
# #                 else:
# #                     break

# #         return cls

# #     @staticmethod
# #     def make_spectrogram(signal: np.ndarray) -> np.ndarray:
# #         spec = power_to_db(
# #             melspectrogram(y=signal, n_fft=NFFT, hop_length=HOP, sr=SR, n_mels=64),
# #             ref=np.max,
# #         )
# #         spec = (spec + 80.0) / 80.0
# #         spec[spec < 0.01] = 0.01
# #         spec = conv2d(spec, kernel_2d_from_window((3, 3), np.hanning), "same")
# #         return spec

# #     @staticmethod
# #     def find_sound_and_silence(spec: np.ndarray) -> np.ndarray:
# #         is_sound = (spec > 0.333).sum(axis=0) > SOUND_POINT

# #         # filter out very small silence segments
# #         ranges = ranges_of_truth(is_sound == False)
# #         ranges = ranges[(ranges[:, 1] - ranges[:, 0]) >= MIN_SILENCE_LEN]
# #         is_sound[:] = True
# #         for r in ranges:
# #             is_sound[r[0] : r[1]] = False

# #         # cut out very small sound segments
# #         ranges = ranges_of_truth(is_sound)
# #         ranges = ranges[(ranges[:, 1] - ranges[:, 0]) >= MIN_SOUND_LEN]
# #         is_sound[:] = False
# #         for r in ranges:
# #             is_sound[r[0] : r[1]] = True

# #         return is_sound

# #     @staticmethod
# #     def redundancy(spec: np.ndarray) -> np.ndarray:
# #         spec = spec / spec.sum(axis=0, keepdims=True)
# #         # spec = softmax(spec, axis=0)
# #         redundancy = np.zeros(spec.shape[1])
# #         redundancy[1:] = kl_div(spec[:, :-1], spec[:, 1:], axis=0)
# #         # redundancy[is_sound == False] = 1
# #         redundancy = np.convolve(redundancy, np.hanning(5), "same")
# #         return redundancy
