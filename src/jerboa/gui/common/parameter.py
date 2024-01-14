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

from .text import TextWidget


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


# -------------------------------------- ParameterCollection ------------------------------------- #


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


# ------------------------------------- ParameterConfigurator ------------------------------------ #


class ParameterConfigurator(QtW.QWidget):
    def __init__(self, title: str, params_collection: ParameterCollection):
        super().__init__()

        self._params_collection = params_collection

        layout = QtW.QVBoxLayout()
        layout.addLayout(self._create_panel_title_layout(title))
        layout.addWidget(params_collection)
        self.setLayout(layout)

    @staticmethod
    def _create_panel_title_layout(title: str) -> QtW.QLayout:
        title_label = TextWidget(title, font_size_offset=-2, bold=True)
        title_label.setSizePolicy(QtW.QSizePolicy.Policy.Fixed, QtW.QSizePolicy.Policy.Fixed)
        title_label.setStyleSheet("color: palette(mid);")

        layout = QtW.QHBoxLayout()
        layout.addWidget(ParameterConfigurator._create_separator(), 1)
        layout.addWidget(title_label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ParameterConfigurator._create_separator(), 1)
        return layout

    @staticmethod
    def _create_separator() -> QtW.QFrame:
        separator = QtW.QFrame()
        separator.setFrameShape(QtW.QFrame.Shape.HLine)
        separator.setLineWidth(0)
        separator.setMidLineWidth(1)
        separator.setStyleSheet(
            """QFrame[frameShape="4"], /* QFrame::HLine == 0x0004 */
            QFrame[frameShape="5"] /* QFrame::VLine == 0x0005 */
            {
                color: palette(mid);
            }"""
        )
        return separator

    def set_fields(self, model_fields: dict[str, pydantic.fields.FieldInfo]) -> None:
        self._params_collection.reset(model_fields)

    def get_configuration(self) -> dict[str]:
        return self._params_collection.get_parameters()
