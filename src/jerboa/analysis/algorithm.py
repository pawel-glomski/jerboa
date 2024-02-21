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


import enum
import pickle
import pydantic
import typing as T
import abc
from dataclasses import dataclass

from jerboa.core.signal import Signal
from jerboa.core.multithreading import Task
from jerboa.core.timeline import TMSection
from .resource import ResourceManager


class Environment(pydantic.BaseModel, abc.ABC):
    class State(enum.Enum):
        NOT_PREPARED = enum.auto()
        NOT_PREPARED__TRY_BY_DEFAULT = enum.auto()
        PREPARATION_FAILED = enum.auto()
        PREPARATION_SUCCESSFUL = enum.auto()

    model_config = pydantic.ConfigDict(validate_assignment=True, validate_default=True)

    state: State = State.NOT_PREPARED

    @abc.abstractmethod
    def prepare(self, executor: Task.Executor, progress_update_signal: Signal) -> None:
        raise NotImplementedError()


class InterpretationParams(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(validate_assignment=True, validate_default=True)
    # ... interpretation parameters here


class AnalysisParams(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, validate_default=True)
    # ... analysis parameters here


class AnalysisData:
    def serialize(self) -> bytes:
        return pickle.dumps(self)

    @staticmethod
    def deserialize(data: bytes) -> "AnalysisData":
        return pickle.loads(data)


# ------------------------------------------- Generics ------------------------------------------- #

EnvT = T.TypeVar("EnvT", bound=Environment)
AParamsT = T.TypeVar("AParamsT", bound=AnalysisParams)
IParamsT = T.TypeVar("IParamsT", bound=InterpretationParams)
ADataT = T.TypeVar("ADataT", bound=AnalysisData)

# ----------------------------------------------- - ---------------------------------------------- #


class AnalysisPacket(pydantic.BaseModel, abc.ABC, T.Generic[ADataT]):
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    beg_timepoint: float = pydantic.Field(frozen=True)
    end_timepoint: float = pydantic.Field(frozen=True)

    data: ADataT = pydantic.Field(frozen=True, exclude=True)  # data is serialized manually

    interpretation: list[TMSection] = pydantic.Field(default_factory=list)


class Analyzer(
    pydantic.BaseModel,
    T.Generic[EnvT, AParamsT, ADataT],
    abc.ABC,
):
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True, extra="allow")

    environment: EnvT = pydantic.Field(frozen=True)
    params: AParamsT = pydantic.Field(frozen=True)

    resource_manager: ResourceManager = pydantic.Field(frozen=True)

    @abc.abstractmethod
    def analyze(
        self,
        executor: Task.Executor,
        previous_packet: AnalysisPacket[ADataT] | None,
    ) -> T.Iterable[AnalysisPacket[ADataT]]:
        raise NotImplementedError()


class Interpreter(
    pydantic.BaseModel,
    T.Generic[EnvT, AParamsT, IParamsT, ADataT],
    abc.ABC,
):
    model_config = pydantic.ConfigDict(frozen=True)

    environment: EnvT
    analysis_params: AParamsT
    interpretation_params: IParamsT

    @abc.abstractmethod
    def interpret_next(self, packet: AnalysisPacket[ADataT]) -> list[TMSection]:
        raise NotImplementedError()


class PassthroughInterpreter(Interpreter):
    def interpret_next(self, packet):
        assert packet.interpretation is not None
        return packet.interpretation


# ------------------------------------------- Algorithm ------------------------------------------ #


class Algorithm(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)

    name: str
    description: str

    environment: Environment

    analysis_params_class: type[AnalysisParams]
    analyzer_class: type[Analyzer]

    interpretation_params_class: type[InterpretationParams]
    interpreter_class: type[Interpreter]


@dataclass
class AlgorithmInstanceDesc:
    algorithm: Algorithm
    analysis_params: AnalysisParams
    interpretation_params: InterpretationParams
