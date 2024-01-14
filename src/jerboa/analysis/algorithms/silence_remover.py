# Jerboa - AI-powered media player
# Copyright (C) 2023 Paweł Głomski

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


import textwrap
import pydantic

from jerboa.core.signal import Signal
from jerboa.core.multithreading import Task
from jerboa.core.timeline import TMSection
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

PROCESSING_FRAME_SAMPLES = 400
PROCESSING_HOP_SIZE = 160


class Environment(alg.Environment):
    use_librosa: bool = pydantic.Field(default=False, description="Use librosa for computations")
    test_float: float = pydantic.Field(default=2, ge=2, le=5)

    def model_post_init(self, __context):
        super().model_post_init(__context)
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


class Analyzer(alg.Analyzer):
    def analyze(self, previous_packets: list[alg.AnalysisPacket]) -> list[alg.AnalysisPacket]:
        # for section in resource_manager.create_audio_resource():
        #     ...
        raise NotImplementedError()


class Interpreter(alg.Interpreter):
    def interpret(
        self, interpretation_params: InterpretationParams, packets: list[alg.AnalysisPacket]
    ) -> list[TMSection]:
        raise NotImplementedError()


ALGORITHM = alg.Algorithm(
    name="Silence Remover",
    description=textwrap.dedent(
        """Removes silence.
        Very fast and very low memory requirements."""
    ),
    environment=Environment(),
    analysis_params_class=AnalysisParams,
    analyzer_class=Analyzer,
    interpretation_params_class=InterpretationParams,
    interpreter_class=Interpreter,
)
