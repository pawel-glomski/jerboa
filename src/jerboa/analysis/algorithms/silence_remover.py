import textwrap
import pydantic

from jerboa.core.signal import Signal
from jerboa.core.multithreading import Task
from jerboa.media.readers.audio import AudioReader
from jerboa.media.core import AudioConfig, AudioChannelLayout, AudioSampleFormat
from jerboa.analysis import algorithm as alg

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
    use_librosa: bool = pydantic.Field(default=False, description="Use librosa for computations")
    test_float: float = pydantic.Field(default=2, ge=2, le=5)

    def model_post_init(self, _):
        self.state = Environment.State.NOT_PREPARED__TRY_BY_DEFAULT

    def prepare(self, executor: Task.Executor, progress_update_signal: Signal) -> None:
        executor.exit_if_aborted()
        dependencies = {env_utils.Package("numpy", ">=", "1.2")}
        if self.use_librosa:
            dependencies.add(env_utils.Package("librosa", ">=", "0.10"))

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
    name="Silence Remover",
    description=textwrap.dedent(
        """\
        Removes silence.
        Very fast and very low memory requirements."""
    ),
    environment=Environment(),
    analysis_params_class=AnalysisParams,
    interpretation_params_class=InterpretationParams,
    implementation_class=Implementation,
)
