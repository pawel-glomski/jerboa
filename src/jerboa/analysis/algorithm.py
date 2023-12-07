from typing import Any
from abc import ABC, abstractmethod

from .parameter import Parameter


class Algorithm(ABC):
    NAME = "?"
    DESCRIPTION = "?"

    @classmethod
    @property
    def parameters_info(cls: "type[Algorithm]") -> dict[str, Parameter]:
        if not hasattr(cls, "_parameters_info"):
            cls._parameters_info = {
                attr_name: attr
                for attr_name, attr in cls.__dict__.items()
                if isinstance(attr, Parameter)
            }
        return cls._parameters_info

    def configure(self, parameters: dict[str, Any]) -> None:
        missing_parameters = self.parameters_info.keys() - parameters.keys()
        extra_parameters = parameters.keys() - self.parameters_info.keys()
        if len(missing_parameters) > 0 or len(extra_parameters) > 0:
            raise KeyError(
                f"Algorithm ({self.NAME}) cannot be configured! "
                f"Missing parameters={missing_parameters}, unexpected parameters={extra_parameters}"
            )

        self._set_parameters(parameters)

    def update_interpretation_parameters(self, parameters: dict[str, Any]) -> None:
        assert all(
            self.parameters_info[k].domain == Parameter.Domain.INTERPRETATION
            for k in parameters.keys()
        )

        self._set_parameters(parameters)

    def _set_parameters(self, parameters: dict[str, Any]) -> None:
        for parameter_key, parameter_value in parameters.items():
            setattr(self, parameter_key, parameter_value)

    @abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def analyze(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def interpret(self) -> None:
        raise NotImplementedError()
