from abc import ABC, abstractmethod
from typing import Optional, TypeVar, Generic
from dataclasses import dataclass

import PySide6.QtWidgets as QtW
import PySide6.QtCore as QtC
import PySide6.QtGui as QtG
from PySide6.QtCore import Qt

from jerboa import analysis


ValueT = TypeVar("ValueT")
InputWidgetT = TypeVar("InputWidgetT")


class LabelWidget(QtW.QLabel):
    def __init__(self, name: str, description: str):
        super().__init__(name)
        self.setToolTip(description)


class InputWidget(QtW.QFrame, Generic[ValueT]):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QtW.QFrame.Shape.Panel)
        self.setFrameShadow(QtW.QFrame.Shadow.Raised)

    @property
    def value(self) -> ValueT:
        raise NotImplementedError()

    def reset(self, *args) -> None:
        raise NotImplementedError()


@dataclass(frozen=True)
class Property(Generic[ValueT, InputWidgetT]):
    label_widget: LabelWidget
    input_widget: InputWidgetT

    # def __post_init__(self):
    #     self.input_widget.setSizePolicy(
    #         QtW.QSizePolicy.Policy.Minimum, QtW.QSizePolicy.Policy.Minimum
    #     )


# ----------------------------------------- Input widgets ---------------------------------------- #


class IntegerInput(InputWidget):
    def __init__(
        self,
        init_value: int,
        min_value: int,
        max_value: int,
        slider_orientation: Qt.Orientation | None = Qt.Orientation.Horizontal,
    ):
        super().__init__()

        self._min_value: int = 0
        self._max_value: int = 0

        self._slider = None
        if slider_orientation is not None:
            self._slider = QtW.QSlider(slider_orientation)
            self._slider.valueChanged.connect(self._on_slider_value_changed)

        self._value_edit = QtW.QLineEdit()
        self._value_edit.editingFinished.connect(self._on_value_edit_value_changed)

        layout = QtW.QHBoxLayout()
        if self._slider is not None:
            layout.addWidget(self._slider)
        layout.addWidget(self._value_edit)
        self.setLayout(layout)

        self.reset(init_value, min_value, max_value)

    @property
    def value(self) -> int:
        return int(self._value_edit.text())

    def _on_slider_value_changed(self) -> None:
        self._value_edit.setText(str(int(self._slider.value())))

    def _on_value_edit_value_changed(self) -> None:
        try:
            value = int(self._value_edit.text())
        except ValueError:
            value = self._min_value
            self._value_edit.setText(str(value))

        if self._slider is not None:
            self._slider.setValue(value)

    def reset(self, value: int, min_value: int, max_value: int) -> None:
        assert min_value < max_value
        assert min_value <= value <= max_value

        self._min_value = min_value
        self._max_value = max_value
        if self._slider is not None:
            self._slider.setMinimum(min_value)
            self._slider.setMaximum(max_value)

        self._value_edit.setText(str(value))
        self._on_value_edit_value_changed()

    def keyPressEvent(self, event: QtG.QKeyEvent) -> None:
        if event.key() in [Qt.Key.Key_Enter, Qt.Key.Key_Return]:
            self._value_edit.clearFocus()
        else:
            return super().keyPressEvent(event)


class FloatInput(InputWidget):
    DECIMALS = 3

    def __init__(
        self,
        init_value: float,
        min_value: float,
        max_value: float,
        slider_orientation: Qt.Orientation | None = Qt.Orientation.Horizontal,
    ):
        super().__init__()

        self._min_value: float = 0
        self._max_value: float = 0

        self._slider = None
        if slider_orientation is not None:
            self._slider = QtW.QSlider(slider_orientation)
            self._slider.setMinimum(0)
            self._slider.setMaximum(10**FloatInput.DECIMALS)
            self._slider.valueChanged.connect(self._on_slider_value_changed)

        self._value_edit = QtW.QLineEdit()
        self._value_edit.editingFinished.connect(self._on_value_edit_value_changed)

        layout = QtW.QHBoxLayout()
        if self._slider is not None:
            layout.addWidget(self._slider)
        layout.addWidget(self._value_edit)

        self.setLayout(layout)

        self.reset(init_value, min_value, max_value)

    @property
    def value(self) -> float:
        return float(self._value_edit.text())

    def _on_slider_value_changed(self) -> None:
        progress = self._slider.value() / self._slider.maximum()
        value = self._min_value + progress * (self._max_value - self._min_value)
        self._value_edit.setText(str(value))

    def _on_value_edit_value_changed(self) -> None:
        try:
            value = float(self._value_edit.text())
        except ValueError:
            value = self._min_value
            self._value_edit.setText(str(value))

        if self._slider is not None:
            progress = max(0, value - self._min_value) / (self._max_value - self._min_value)
            self._slider.setValue(progress * self._slider.maximum())

    def reset(self, init_value: float, min_value: float, max_value: float) -> None:
        assert min_value < max_value
        assert min_value <= init_value <= max_value

        self._min_value = min_value
        self._max_value = max_value

        self._value_edit.setText(str(init_value))
        self._on_value_edit_value_changed()

    def keyPressEvent(self, event: QtG.QKeyEvent) -> None:
        if event.key() in [Qt.Key.Key_Enter, Qt.Key.Key_Return]:
            self._value_edit.clearFocus()
        else:
            return super().keyPressEvent(event)


class StringInput(InputWidget):
    def __init__(self, init_value: str, read_only: bool = False):
        super().__init__()

        self._value_edit = QtW.QLineEdit()
        self._value_edit.setReadOnly(read_only)

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._value_edit)
        self.setLayout(layout)

        self.reset(init_value)

    @property
    def value(self) -> float:
        return float(self._value_edit.text())

    def reset(self, init_value: str) -> None:
        self._value_edit.setText(init_value)


# --------------------------------------- Property widgets --------------------------------------- #


class Float(Property[float, FloatInput]):
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
            FloatInput(init_value, min_value, max_value),
        )


class Integer(Property[int, IntegerInput]):
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
            IntegerInput(init_value, min_value, max_value),
        )


class String(Property[str, StringInput]):
    def __init__(self, name: str, description: str, init_value: str, read_only: bool = False):
        super().__init__(
            LabelWidget(name, description),
            StringInput(init_value, read_only),
        )


class Enum(Property):
    ...  # TODO


class Path(Property):
    ...  # TODO


class PropertiesCollection(QtW.QWidget):
    def __init__(self):
        super().__init__()
        self._properties = list[Property]()

    def reset(self, properties: list[Property]) -> None:
        self._properties.clear()

        grid_layout = QtW.QGridLayout()
        grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for row_index, property_ in enumerate(properties):
            grid_layout.addWidget(property_.label_widget, row_index, 0)
            grid_layout.addWidget(property_.input_widget, row_index, 1)
        self.setLayout(grid_layout)


def from_algorithm_option(option: analysis.option.Option) -> Property:
    match option:
        case analysis.option.Integer():
            return Integer(
                name=option.name,
                description=option.description,
                init_value=option.default_value,
                min_value=option.min_value,
                max_value=option.max_value,
            )
        case analysis.option.Float():
            return Float(
                name=option.name,
                description=option.description,
                init_value=option.default_value,
                min_value=option.min_value,
                max_value=option.max_value,
            )
        case analysis.option.String():
            return String(
                name=option.name,
                description=option.description,
                init_value=option.default_value,
            )
        case analysis.option.Enum():
            raise NotImplementedError()
            # return Enum(
            #     name=option.name,
            #     description=option.description,
            #     init_value=option.default_value,
            # )
        case analysis.option.Path():
            raise NotImplementedError()
