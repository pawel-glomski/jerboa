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
class Parameter(Generic[ValueT, InputWidgetT]):
    label_widget: LabelWidget
    input_widget: InputWidgetT

    # def __post_init__(self):
    #     self.input_widget.setSizePolicy(
    #         QtW.QSizePolicy.Policy.Minimum, QtW.QSizePolicy.Policy.Minimum
    #     )


# ----------------------------------------- Input widgets ---------------------------------------- #


class BetterSlider(QtW.QSlider):
    def mousePressEvent(self, event: QtG.QMouseEvent):
        if event.button() == QtC.Qt.LeftButton:
            self.setValue(self.value_at_mouse_position(event.pos()))
        super().mousePressEvent(event)

    @property
    def value_range(self) -> int:
        return self.maximum() - self.minimum()

    def value_at_mouse_position(self, position: QtC.QPoint) -> int:
        style_option = QtW.QStyleOptionSlider()
        self.initStyleOption(style_option)

        groove_rect = self.style().subControlRect(
            QtW.QStyle.ComplexControl.CC_Slider,
            style_option,
            QtW.QStyle.SubControl.SC_SliderGroove,
            self,
        )
        handle_rect = self.style().subControlRect(
            QtW.QStyle.ComplexControl.CC_Slider,
            style_option,
            QtW.QStyle.SubControl.SC_SliderHandle,
            self,
        )
        handle_half_size = handle_rect.center() - handle_rect.topLeft()

        position -= groove_rect.topLeft()  # make it relative to the groove
        position -= handle_half_size  # we want the handle's center to land at the cursor
        available_space = groove_rect.size() - handle_rect.size()

        if self.orientation() == Qt.Orientation.Horizontal:
            position = position.x()
            available_space = available_space.width()
        else:
            position = position.y()
            available_space = available_space.height()

        return QtW.QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), position, available_space, style_option.upsideDown
        )


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
            self._slider = BetterSlider(slider_orientation)
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
            self._slider = BetterSlider(slider_orientation)
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


# --------------------------------------- Parameter widgets --------------------------------------- #


class Float(Parameter[float, FloatInput]):
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


class Integer(Parameter[int, IntegerInput]):
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


class String(Parameter[str, StringInput]):
    def __init__(self, name: str, description: str, init_value: str, read_only: bool = False):
        super().__init__(
            LabelWidget(name, description),
            StringInput(init_value, read_only),
        )


class Enum(Parameter):
    ...  # TODO


class Path(Parameter):
    ...  # TODO


class ParameterCollection(QtW.QWidget):
    def __init__(self):
        super().__init__()
        self._parameters = list[Parameter]()

    def reset(self, parameters: list[Parameter]) -> None:
        if self.layout() is not None:
            grid_layout = self.layout()
            while grid_layout.count():
                widget = grid_layout.itemAt(0).widget()
                widget.setParent(None)
                widget.deleteLater()
                grid_layout.removeWidget(widget)
        else:
            grid_layout = QtW.QGridLayout()
            grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.setLayout(grid_layout)

        for row_index, parameter in enumerate(parameters):
            grid_layout.addWidget(parameter.label_widget, row_index, 0)
            grid_layout.addWidget(parameter.input_widget, row_index, 1)
        self.setLayout(grid_layout)


def from_algorithm_parameter(parameter: analysis.parameter.Parameter) -> Parameter:
    match parameter:
        case analysis.parameter.Integer():
            return Integer(
                name=parameter.name,
                description=parameter.description,
                init_value=parameter.default_value,
                min_value=parameter.min_value,
                max_value=parameter.max_value,
            )
        case analysis.parameter.Float():
            return Float(
                name=parameter.name,
                description=parameter.description,
                init_value=parameter.default_value,
                min_value=parameter.min_value,
                max_value=parameter.max_value,
            )
        case analysis.parameter.String():
            return String(
                name=parameter.name,
                description=parameter.description,
                init_value=parameter.default_value,
            )
        case analysis.parameter.Enum():
            raise NotImplementedError()
            # return Enum(
            #     name=parameter.name,
            #     description=parameter.description,
            #     init_value=parameter.default_value,
            # )
        case analysis.parameter.Path():
            raise NotImplementedError()
