from typing import Any, Callable, Generic, TypeVar
import enum
import pathlib


class Domain(enum.Enum):
    ANALYSIS = enum.auto()
    INTERPRETATION = enum.auto()


T = TypeVar("T")


class Option(Generic[T]):
    def __init__(
        self,
        value_type: type[T],
        default_value: T,
        description: str,
        domain: Domain,
        setter_transformer: Callable[[Any], T] | None = None,
    ):
        self.name = "?"
        self.variable_name = f"_{self.name}"
        self.value_type = value_type
        self.default_value = value_type(default_value)
        self.description = description
        self.domain = domain
        self.setter_transformer = setter_transformer or (lambda value: value_type(value))

    def __set_name__(self, owner, name: str):
        self.name = name.replace("_", " ")
        self.variable_name = f"_{name}"

    def __get__(self, instance, owner=None) -> T:
        return getattr(instance, self.variable_name, self.default_value)

    def __set__(self, instance, value: T) -> None:
        if self.domain == Domain.ANALYSIS and hasattr(instance, self.variable_name):
            raise TypeError("Analysis option can be assigned only once")
        setattr(instance, self.variable_name, self.setter_transformer(value))

    def __delete__(self, instance) -> None:
        delattr(instance, self.variable_name)

    def __repr__(self) -> str:
        attributes = (
            attr
            for attr in self.__dict__  # using `__dict__` (and not `dir()`) for proper order
            if not attr.startswith("_") and not attr == "setter_transformer"
        )
        attributes = (f"{attr}={repr(getattr(self, attr))}" for attr in attributes)
        attributes = ", ".join(attributes)
        return f"{self.__class__.__name__}({attributes})"


class Number(Option[T]):
    def __init__(
        self,
        value_type: type[T],
        default_value: T,
        min_value: T,
        max_value: T,
        description: str,
        domain: Domain = Domain.ANALYSIS,
    ):
        super().__init__(
            value_type=value_type,
            default_value=default_value,
            description=description,
            domain=domain,
            setter_transformer=self._clamp,
        )
        self.min_value = value_type(min_value)
        self.max_value = value_type(max_value)
        if self.setter_transformer(default_value) != default_value:
            raise ValueError(f"{default_value=} not in the range ({min_value}, {max_value})")

    def _clamp(self, value) -> T:
        return min(max(self.min_value, self.value_type(value)), self.max_value)


class Integer(Number[int]):
    def __init__(
        self,
        default_value: int,
        min_value: int,
        max_value: int,
        description: str = "",
        domain: Domain = Domain.ANALYSIS,
    ):
        super().__init__(
            value_type=int,
            default_value=default_value,
            min_value=min_value,
            max_value=max_value,
            description=description,
            domain=domain,
        )


class Float(Number[float]):
    def __init__(
        self,
        default_value: float,
        min_value: float,
        max_value: float,
        description: str = "",
        domain: Domain = Domain.ANALYSIS,
    ):
        super().__init__(
            value_type=float,
            default_value=default_value,
            min_value=min_value,
            max_value=max_value,
            description=description,
            domain=domain,
        )


class String(Option[str]):
    def __init__(
        self,
        default_value: str,
        description: str = "",
        domain: Domain = Domain.ANALYSIS,
    ):
        super().__init__(
            value_type=str,
            default_value=default_value,
            description=description,
            domain=domain,
        )


class Enum(Option[T]):
    def __init__(
        self,
        enum_type: type[T],
        default_value: T,
        description: str = "",
        domain: Domain = Domain.ANALYSIS,
    ):
        super().__init__(
            value_type=enum_type,
            default_value=default_value,
            description=description,
            domain=domain,
        )
        if not issubclass(enum_type, enum.Enum):
            raise ValueError(f"{enum_type=} is not an enum")
        self.possible_values = [enum_value.value for enum_value in enum_type]


class Path(Option[pathlib.Path]):
    def __init__(
        self,
        default_value: pathlib.Path,
        reads: bool = True,
        writes: bool = False,
        is_directory: bool = False,
        extensions: list[str] | None = None,
        should_already_exist: bool = True,
        description: str = "",
        domain: Domain = Domain.ANALYSIS,
    ):
        self.writes = writes
        self.reads = reads
        self.is_directory = is_directory
        self.extensions = extensions or []
        self.should_already_exist = should_already_exist

        if not reads and not writes:
            raise ValueError("Useless option")

        if self.is_directory and self.extensions:
            raise ValueError("Directory option should not have extensions")

        super().__init__(
            value_type=pathlib.Path,
            default_value=default_value,
            description=description,
            domain=domain,
            setter_transformer=self._path_transformer,
        )

    def _path_transformer(self, path: pathlib.Path):
        path = pathlib.Path(path)

        what = "Directory" if path.is_dir() else "File"
        if self.should_already_exist and not path.exists():
            raise ValueError(f'{what} "{path}" does not exist.')
        if not self.should_already_exist and path.exists():
            raise ValueError(f'{what} "{path}" already exists.')
        if path.is_dir() != self.is_directory:
            raise ValueError(f'Path "{path}" should point a directory.')
        if not self.is_directory and path.suffix not in self.extensions:
            raise ValueError(
                f'Unexpected extension ({path.suffix}) of "{path}", this option accepts only '
                f"the following extensions: {self.extensions}."
            )
        return path.resolve()
