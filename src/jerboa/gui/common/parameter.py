import pydantic
import enum
import pathlib
import annotated_types
from typing import TypeVar, Generic
from dataclasses import dataclass

import PySide6.QtWidgets as QtW
from PySide6.QtCore import Qt

from . import input_widget
from .page_stack import MessagePage


ValueT = TypeVar("ValueT")
InputWidgetT = TypeVar("InputWidgetT", bound=input_widget.InputWidget)


class LabelWidget(QtW.QLabel):
    def __init__(self, name: str, description: str):
        super().__init__(name)
        self.setToolTip(description)


@dataclass(frozen=True)
class Parameter(Generic[ValueT, InputWidgetT]):
    label_widget: LabelWidget
    input_widget: InputWidgetT

    # def __post_init__(self):
    #     self.input_widget.setSizePolicy(
    #         QtW.QSizePolicy.Policy.Minimum, QtW.QSizePolicy.Policy.Minimum
    #     )


class Boolean(Parameter[bool, input_widget.Boolean]):
    def __init__(self, name: str, description: str, init_value: bool):
        super().__init__(
            LabelWidget(name, description),
            input_widget.Boolean(init_value),
        )


class Integer(Parameter[int, input_widget.Number]):
    def __init__(
        self,
        name: str,
        description: str,
        init_value: float,
        min_value: float,
        max_value: float,
    ):
        super().__init__(
            LabelWidget(name, description),
            input_widget.Number(init_value, min_value, max_value, decimals=0),
        )


class Float(Parameter[float, input_widget.Number]):
    def __init__(
        self,
        name: str,
        description: str,
        init_value: float,
        min_value: float,
        max_value: float,
    ):
        super().__init__(
            LabelWidget(name, description),
            input_widget.Number(init_value, min_value, max_value, decimals=4),
        )


class String(Parameter[str, input_widget.String]):
    def __init__(self, name: str, description: str, init_value: str, read_only: bool = False):
        super().__init__(
            LabelWidget(name, description),
            input_widget.String(init_value, read_only),
        )


class Enum(Parameter[ValueT, input_widget.Enum]):
    def __init__(self, name: str, description: str, init_value: ValueT):
        super().__init__(
            LabelWidget(name, description),
            input_widget.Enum(init_value),
        )


class Path(Parameter):
    ...  # TODO


class DirectoryPath(Parameter):
    ...  # TODO


class FilePath(Parameter):
    ...  # TODO


class ParameterCollection(QtW.QWidget):
    def __init__(self, no_params_text: str):
        super().__init__()

        self._params = dict[str, Parameter]()
        self._no_params_text = no_params_text

        layout = QtW.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setHorizontalSpacing(20)
        self.setLayout(layout)

        self.reset({})

    def reset(self, model_fields: dict[str, pydantic.fields.FieldInfo]) -> None:
        layout: QtW.QGridLayout = self.layout()

        self._params.clear()
        while layout.count():
            widget = layout.itemAt(0).widget()
            widget.setParent(None)
            widget.deleteLater()
            layout.removeWidget(widget)

        if len(model_fields) > 0:
            for field_name, field_info in model_fields.items():
                param = from_pydantic_field(field_name, field_info)
                self._params[field_name] = param

                row_idx = layout.rowCount()
                layout.addWidget(
                    param.label_widget,
                    row_idx,
                    0,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                )
                layout.addWidget(param.input_widget, row_idx, 1, Qt.AlignmentFlag.AlignVCenter)
        else:
            layout.addWidget(MessagePage(self._no_params_text))
        self.adjustSize()

    def get_parameters(self) -> dict[str]:
        return {param_name: param.input_widget.value for param_name, param in self._params.items()}


def from_pydantic_field(field_name: str, field_info: pydantic.fields.FieldInfo) -> Parameter:
    default_kwargs = {
        "name": field_name,
        "description": field_info.description,
        "init_value": field_info.default,
    }
    if issubclass(field_info.annotation, bool):
        return Boolean(**default_kwargs)
    if issubclass(field_info.annotation, int):
        return Integer(
            **default_kwargs,
            min_value=get_min_value_from_pydantic(field_info),
            max_value=get_max_value_from_pydantic(field_info),
        )
    if issubclass(field_info.annotation, float):
        return Float(
            **default_kwargs,
            min_value=get_min_value_from_pydantic(field_info),
            max_value=get_max_value_from_pydantic(field_info),
        )
    if issubclass(field_info.annotation, str):
        return String(**default_kwargs)
    if issubclass(field_info.annotation, enum.Enum):
        return Enum(**default_kwargs)
    if issubclass(field_info.annotation, pathlib.Path):
        raise NotImplementedError()
    if issubclass(field_info.annotation, pydantic.DirectoryPath):
        raise NotImplementedError()
    if issubclass(field_info.annotation, pydantic.FilePath):
        raise NotImplementedError()
    raise TypeError(f"Parameter type not supported: {field_info.annotation}")


def get_min_value_from_pydantic(field_info: pydantic.fields.FieldInfo) -> float | None:
    for metadata in field_info.metadata:
        if isinstance(metadata, annotated_types.Ge):  # >=
            return metadata.ge


def get_max_value_from_pydantic(field_info: pydantic.fields.FieldInfo) -> float | None:
    for metadata in field_info.metadata:
        if isinstance(metadata, annotated_types.Le):  # <=
            return metadata.le
