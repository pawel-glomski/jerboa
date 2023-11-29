from typing import Any
from abc import ABC, abstractmethod

from .option import Option


class Algorithm(ABC):
    NAME = "?"
    DESCRIPTION = "?"

    @classmethod
    @property
    def options_info(cls: "type[Algorithm]") -> dict[str, Option]:
        if not hasattr(cls, "_options_info"):
            cls._options_info = {
                attr_name: attr
                for attr_name, attr in cls.__dict__.items()
                if isinstance(attr, Option)
            }
        return cls._options_info

    def configure(self, options: dict[str, Any]) -> None:
        missing_options = self.options_info.keys() - options.keys()
        extra_options = options.keys() - self.options_info.keys()
        if len(missing_options) > 0 or len(extra_options) > 0:
            raise KeyError(
                f"Algorithm ({self.NAME}) cannot be configured! "
                f"Missing options={missing_options}, unexpected options={extra_options}"
            )

        self._set_options(options)

    def update_interpretation_options(self, options: dict[str, Any]) -> None:
        assert all(
            self.options_info[k].domain == Option.Domain.INTERPRETATION for k in options.keys()
        )

        self._set_options(options)

    def _set_options(self, options: dict[str, Any]) -> None:
        for option_key, option_value in options.items():
            self.__setattr__(option_key, option_value)

    @abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def analyze(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def interpret(self) -> None:
        raise NotImplementedError()
