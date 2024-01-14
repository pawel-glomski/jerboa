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
from typing import TypeVar, Generic

import PySide6.QtWidgets as QtW
import PySide6.QtCore as QtC
import PySide6.QtGui as QtG
from PySide6.QtCore import Qt


ValueT = TypeVar("ValueT")

# --------------------------------------------- utils -------------------------------------------- #


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


# ----------------------------------------- Input widgets ---------------------------------------- #


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


class Boolean(InputWidget):
    def __init__(self, init_value: bool):
        super().__init__()
        self.setSizePolicy(QtW.QSizePolicy.Policy.Fixed, QtW.QSizePolicy.Policy.Fixed)

        self._checkbox = QtW.QCheckBox()

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._checkbox, 1, Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)

        self._checkbox.setChecked(init_value)
        self._checkbox.clicked.connect(self._checkbox.clearFocus)

    @property
    def value(self) -> bool:
        return self._checkbox.isChecked()


class Number(InputWidget[ValueT]):
    def __init__(
        self,
        init_value: int | float,
        min_value: int | float,
        max_value: int | float,
        decimals: int,
        slider_orientation: Qt.Orientation | None = Qt.Orientation.Horizontal,
    ):
        assert min_value < max_value
        assert min_value <= init_value <= max_value
        super().__init__()

        self._min_value = min_value
        self._max_value = max_value
        self._decimals = decimals
        self._output_type = float if decimals > 0 else int

        self._slider = None
        if slider_orientation is not None:
            self._slider = BetterSlider(slider_orientation)
            self._slider.setMinimum(min_value * (10**decimals))
            self._slider.setMaximum(max_value * (10**decimals))
            self._slider.valueChanged.connect(self._on_slider_value_changed)

        self._line_edit = QtW.QLineEdit()
        self._line_edit.setMinimumWidth(50)
        self._line_edit.setSizePolicy(QtW.QSizePolicy.Policy.Fixed, QtW.QSizePolicy.Policy.Fixed)
        self._line_edit.editingFinished.connect(self._on_line_edit_value_changed)
        self._set_line_edit(init_value)

        layout = QtW.QHBoxLayout()
        layout.addWidget(self._line_edit, 1)
        if self._slider is not None:
            layout.addWidget(self._slider, 9)
        self.setLayout(layout)

        # update the slider (if present)
        self._on_line_edit_value_changed()

    @property
    def value(self) -> ValueT:
        return self._output_type(self._line_edit.text())

    def _on_slider_value_changed(self) -> None:
        progress = (self._slider.value() - self._slider.minimum()) / (
            self._slider.maximum() - self._slider.minimum()
        )
        value = self._min_value + progress * (self._max_value - self._min_value)
        self._set_line_edit(value)

    def _on_line_edit_value_changed(self) -> None:
        try:
            value = round(self._output_type(self._line_edit.text()), self._decimals)
        except ValueError:
            value = self._min_value
        self._set_line_edit(value)

        if self._slider is not None:
            progress = max(0, value - self._min_value) / (self._max_value - self._min_value)
            self._slider.setValue(progress * self._slider.maximum())

    def _set_line_edit(self, value: int | float) -> None:
        if self._output_type == int:
            self._line_edit.setText(f"{int(value)}")
        else:
            # self._line_edit.setText(f"{self._output_type(value):.{4}f}")
            self._line_edit.setText(f"{self._output_type(value):.{self._decimals}f}")

    def keyPressEvent(self, event: QtG.QKeyEvent) -> None:
        if event.key() in [Qt.Key.Key_Enter, Qt.Key.Key_Return]:
            self._line_edit.clearFocus()
        else:
            return super().keyPressEvent(event)


class String(InputWidget):
    def __init__(self, init_value: str, read_only: bool = False):
        super().__init__()

        self._line_edit = QtW.QLineEdit()
        self._line_edit.setText(init_value)
        self._line_edit.setReadOnly(read_only)

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._line_edit)
        self.setLayout(layout)

    @property
    def value(self) -> str:
        return self._line_edit.text()


class Enum(InputWidget[ValueT]):
    def __init__(self, init_value: enum.Enum):
        assert init_value is not None
        super().__init__()

        self._enum_type = init_value.__class__

        self._combobox = QtW.QComboBox()
        self._combobox.addItems(value.name for value in init_value.__class__)
        self._combobox.setCurrentText(init_value.name)

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._combobox)
        self.setLayout(layout)

    @property
    def value(self) -> ValueT:
        return self._enum_type[self._combobox.currentText()]
