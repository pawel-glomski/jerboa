import pydantic
import enum
from abc import ABC, abstractmethod

from jerboa.core.signal import Signal
from jerboa.core.multithreading import Task


class Algorithm(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)

    name: str
    description: str

    environment: "Environment"
    analysis_params_class: "type[AnalysisParams]"
    interpretation_params_class: "type[InterpretationParams]"
    implementation_class: "type[Implementation]"


# ------------------------------------------- Template ------------------------------------------- #


class Environment(pydantic.BaseModel):
    class State(enum.Enum):
        NOT_PREPARED = enum.auto()
        NOT_PREPARED__TRY_BY_DEFAULT = enum.auto()
        PREPARATION_FAILED = enum.auto()
        PREPARATION_SUCCESSFUL = enum.auto()

    model_config = pydantic.ConfigDict(validate_assignment=True, validate_default=True)

    state: State = State.NOT_PREPARED

    def prepare(self, executor: Task.Executor, progress_update_signal: Signal) -> None:
        raise NotImplementedError()


class AnalysisParams(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True, validate_default=True)
    # ... analysis parameters here


class InterpretationParams(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(validate_assignment=True, validate_default=True)
    # ... interpretation parameters here


class Implementation(pydantic.BaseModel, ABC):
    # must implement  __init__(analysis_params, interpretation_params)

    @abstractmethod
    def update_interpretation_params(self, params: InterpretationParams) -> None:
        raise NotImplementedError()

    @abstractmethod
    def analyze(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def interpret(self) -> None:
        raise NotImplementedError()


ALGORITHM = Algorithm(
    name="?",
    description="?",
    environment=Environment(),
    analysis_params_class=AnalysisParams,
    interpretation_params_class=InterpretationParams,
    implementation_class=Implementation,
)
