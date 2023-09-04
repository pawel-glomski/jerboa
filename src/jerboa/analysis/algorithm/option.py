from typing import Generic, TypeVar, Type
from enum import Enum

from pathlib import Path

T = TypeVar("T")


class AlgorithmOption(Generic[T]):
    def __init__(self, name: str, type_: Type[T], default_value: T = None, description: str = ""):
        self.name = f"__{name}"
        self.type = type_
        self.default_value = default_value
        self.description = description
        self.setter_transformer = lambda value: value  # identity

    def __get__(self, instance, owner) -> T:
        return getattr(instance, self.name, self.default_value)

    def __set__(self, instance, value) -> None:
        assert isinstance(value, self.type)
        setattr(instance, self.name, self.setter_transformer(value))

    def __delete__(self, instance) -> None:
        delattr(instance, self.name)

    def __repr__(self) -> str:
        attributes = (
            attr
            for attr in dir(self)
            if not attr.startswith("_") and not attr == "setter_transformer"
        )
        attributes = (f"{attr}={getattr(self, attr)}" for attr in attributes)
        attributes = ", ".join(attributes)
        return f"AlgorithmOption({attributes})"


def option_number(
    type_: Type[int] | Type[float],
    min_value: int | float,
    max_value: int | float,
    default_value: int | float,
    description: str = "",
) -> AlgorithmOption:
    def create(option_fn):
        option = AlgorithmOption(option_fn.__name__, type_, default_value, description)
        option.min_value = min_value
        option.max_value = max_value
        option.setter_transformer = lambda value: min(max(min_value, value), max_value)
        return option

    return create


def option_int(
    min_value: int, max_value: int, default_value: int, description: str = ""
) -> AlgorithmOption:
    return option_number(int, min_value, max_value, default_value, description)


def option_float(
    min_value: float, max_value: float, default_value: float, description: str = ""
) -> AlgorithmOption:
    return option_number(float, min_value, max_value, default_value, description)


def option_path(  # pylint: disable=W0102:dangerous-default-value
    default_value: Path,
    reads: bool = True,
    writes: bool = False,
    should_already_exist: bool = True,
    extensions: list[str] = [],  # this is fine, it is read-only
    description: str = "",
):
    if not reads and not writes:
        raise ValueError("Useless option")

    is_directory = default_value.is_dir()
    if is_directory and extensions:
        raise ValueError("Directories do not have extensions")

    def path_transformer(path: Path):
        what = "Directory" if is_directory else "File"
        if should_already_exist and not path.exists():
            raise ValueError(f'{what} "{path}" does not exist.')
        if not should_already_exist and path.exists():
            raise ValueError(f'{what} "{path}" already exists.')
        if path.is_dir() != is_directory:
            raise ValueError(f'Path "{path}" should point a directory.')
        if path.suffix not in extensions:
            raise ValueError(
                f'{what} "{path}" has unexpected extension "{path.suffix}", while should '
                f"have one of these: {extensions}."
            )
        return path.resolve()

    def create(option_fn):
        option = AlgorithmOption(option_fn.__name__, Path, default_value, description)
        option.is_directory = is_directory
        option.extensions = extensions
        option.setter_transformer = path_transformer
        return option

    return create


def option_enum(enum: Type[Enum], default_value: Enum, description: str = ""):
    def create(option_fn):
        option = AlgorithmOption(option_fn.__name__, enum, default_value, description)
        option.possible_values = [enum_value.value for enum_value in enum]
        return option

    return create


def get_all_algorithm_options(algorithm) -> dict[str, AlgorithmOption]:
    return {
        attr_name: attr
        for attr_name, attr in algorithm.__class__.__dict__.items()
        if isinstance(attr, AlgorithmOption)
    }
