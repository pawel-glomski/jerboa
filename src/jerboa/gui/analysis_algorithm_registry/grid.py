# Jerboa - AI-powered media player
# Copyright (C) 2024 Paweł Głomski

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

import qtpy.QtWidgets as QtW
import qtpy.QtGui as QtG
from qtpy.QtCore import Qt

from jerboa.analysis.algorithm import Algorithm, Environment
from jerboa.gui.common.text import TextWidget


class Column(enum.IntEnum):
    NAME = 0
    DESCRIPTION = enum.auto()
    ENV_CONFIG = enum.auto()
    RUN = enum.auto()
    COLUMNS_NUM = enum.auto()


class ColumnHeader(TextWidget):
    def __init__(self, text: str):
        super().__init__(text, font_size_offset=2, bold=True)


class Row:
    def __init__(self, algorithm: Algorithm):
        self._entries = dict[Column, QtW.QWidget]()
        self._entries[Column.NAME] = Row._create_name_label(algorithm.name)
        self._entries[Column.DESCRIPTION] = Row._create_description_label(algorithm.description)
        self._entries[Column.ENV_CONFIG] = Row._create_env_config_button()
        self._entries[Column.RUN] = Row._create_run_button()
        self.reflect_state(algorithm.environment)

    @staticmethod
    def _create_name_label(name: str) -> TextWidget:
        widget = TextWidget(name, font_size_offset=1, bold=True)
        widget.setSizePolicy(QtW.QSizePolicy.Policy.Minimum, QtW.QSizePolicy.Policy.Minimum)
        return widget

    @staticmethod
    def _create_description_label(description: str) -> TextWidget:
        class Description(TextWidget):
            def __init__(self):
                super().__init__(description, font_size_offset=1, bold=True)
                self.setSizePolicy(
                    QtW.QSizePolicy.Policy.MinimumExpanding, QtW.QSizePolicy.Policy.Minimum
                )

            def resizeEvent(self, event: QtG.QResizeEvent) -> None:
                # sometimes text can get cut-off
                self.setMinimumHeight(self.heightForWidth(self.width()))
                super().resizeEvent(event)

        return Description()

    @staticmethod
    def _create_env_config_button() -> QtW.QToolButton:
        widget = QtW.QToolButton()
        widget.setSizePolicy(QtW.QSizePolicy.Policy.Fixed, QtW.QSizePolicy.Policy.Fixed)
        widget.setText("⚙")
        font = widget.font()
        font.setPointSizeF(font.pointSizeF() + 2)
        widget.setFont(font)
        return widget

    @staticmethod
    def _create_run_button() -> QtW.QToolButton:
        widget = Row._create_env_config_button()
        widget.setText("▶")
        return widget

    def reflect_state(self, state: Environment.State):
        env_config_button = self.get(Column.ENV_CONFIG)
        if state == Environment.State.PREPARATION_SUCCESSFUL:
            env_config_button.setStyleSheet("background-color: darkgreen")
        elif state == Environment.State.PREPARATION_FAILED:
            env_config_button.setStyleSheet("background-color: darkred")
        else:
            env_config_button.setStyleSheet("")

        self._entries[Column.RUN].setDisabled(state != Environment.State.PREPARATION_SUCCESSFUL)

    def get(self, column: Column) -> QtW.QWidget:
        return self._entries[column]

    def items(self):
        return self._entries.items()


class Grid(QtW.QWidget):
    def __init__(self, header: dict[Column, TextWidget]) -> None:
        super().__init__()

        self._rows = dict[str, Row]()

        layout = QtW.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(20)
        self.setLayout(layout)

        self._add_header(header)

    def _add_header(self, header: dict[Column, TextWidget]):
        layout: QtW.QGridLayout = self.layout()

        row = 0
        for column, widget in header.items():
            layout.addWidget(widget, row, column, Qt.AlignmentFlag.AlignLeft)

        separator = QtW.QFrame()
        separator.setFrameShape(QtW.QFrame.Shape.HLine)
        separator.setLineWidth(1)
        separator.setMidLineWidth(1)

        row = 1
        column = 0
        row_span = 1
        column_span = Column.COLUMNS_NUM
        layout.addWidget(separator, row, column, row_span, column_span)

    def add_row(self, key: str, row: Row) -> None:
        layout: QtW.QGridLayout = self.layout()

        row_idx = layout.rowCount()
        for column, widget in row.items():
            layout.addWidget(widget, row_idx, column)

        self._rows[key] = row

        self.adjustSize()

    def row(self, key: str) -> Row:
        return self._rows[key]
