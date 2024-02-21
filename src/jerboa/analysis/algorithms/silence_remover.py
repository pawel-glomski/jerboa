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

from __future__ import annotations

import textwrap
import pydantic
import typing as T

import jerboa.analysis.utils.environment as env_utils
import jerboa.analysis.resource as res
import jerboa.analysis.algorithm as alg
from jerboa.core.timeline import TMSection
from jerboa.core import jbmath

if T.TYPE_CHECKING:
    import numpy as np


class Environment(alg.Environment):
    test_float: float = pydantic.Field(default=2, ge=2, le=5)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = Environment.State.NOT_PREPARED__TRY_BY_DEFAULT

    def prepare(self, executor, progress_update_signal):
        executor.exit_if_aborted()
        dependencies = {
            env_utils.Package("numpy", ">=", "1.2"),
            env_utils.Package("librosa", ">=", "0.10"),
        }

        progress_update_signal.emit(progress=0.1, message="Downloading dependencies...")
        env_utils.pip_install(dependencies, executor=executor)
        progress_update_signal.emit(progress=0.99, message="Downloaded dependencies")


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


class AnalysisParams(alg.AnalysisParams):
    int_param: int = pydantic.Field(
        default=2,
        ge=2,
        le=10,
        description="This is an int param",
    )


class AnalysisData(alg.AnalysisData):
    def __init__(self, rms: np.ndarray):
        self.rms = rms

    def serialize(self):
        return super().serialize()

    @staticmethod
    def deserialize(data):
        return super(AnalysisData, AnalysisData).deserialize(data)


class Analyzer(alg.Analyzer[Environment, AnalysisParams, AnalysisData]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._audio = self.resource_manager.get_audio_resource()

    def analyze(self, executor, previous_packet):
        import librosa

        executor.exit_if_aborted()

        for audio_frame in self._audio.read(
            start_timepoint=0 if previous_packet is None else previous_packet.end_timepoint,
            frame_duration=60,  # a minute
        ):
            assert audio_frame.audio_signal.shape[res.std_audio.CHANNELS_AXIS] == 1

            yield alg.AnalysisPacket(
                beg_timepoint=audio_frame.beg_timepoint,
                end_timepoint=audio_frame.end_timepoint,
                data=AnalysisData(
                    rms=librosa.feature.rms(
                        y=audio_frame.audio_signal.reshape(-1),
                        frame_length=res.AUDIO_PROC_FRAME_SIZE,
                        hop_length=res.AUDIO_PROC_HOP_SIZE,
                    ).reshape(-1)
                ),
            )


class Interpreter(alg.Interpreter[Environment, AnalysisParams, InterpretationParams, AnalysisData]):
    def interpret_next(self, packet):
        if not hasattr(self, "_sum"):
            self._sum = 0

        sections = list[TMSection]()

        idx_to_time = 1 / packet.data.rms.shape[0]
        for beg, end in jbmath.ranges_of_truth(packet.data.rms > 0.01):
            beg_ratio = beg * idx_to_time
            end_ratio = end * idx_to_time
            sections.append(
                TMSection(
                    packet.beg_timepoint * (1 - beg_ratio) + packet.end_timepoint * beg_ratio,
                    packet.beg_timepoint * (1 - end_ratio) + packet.end_timepoint * end_ratio,
                    1,
                )
            )
            self._sum += sections[-1].duration
        return sections


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
