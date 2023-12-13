import enum
from dataclasses import dataclass
from typing import Callable

import PySide6.QtWidgets as QtW
from PySide6.QtCore import Qt

from jerboa.core.multithreading import Task
from jerboa.core.signal import Signal
from jerboa.analysis.algorithm import Algorithm, Environment
from .env_config_dialog import Dialog as EnvConfigDialog
from .env_prep_progress_dialog import Dialog as EnvPrepProgressDialog


# TODO: refactor this file


class Column(enum.IntEnum):
    NAME = 0
    DESCRIPTION = enum.auto()
    ENV_CONFIG = enum.auto()
    COLUMNS_NUM = enum.auto()


class ColumnHeader(QtW.QLabel):
    def __init__(self, text: str):
        super().__init__(text)

        font = self.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 1)
        self.setFont(font)


@dataclass
class RegistryEntry:
    name_label: QtW.QLabel
    description_label: QtW.QLabel
    environment_config_button: QtW.QToolButton


class Dialog(QtW.QDialog):
    def __init__(
        self,
        title: str,
        min_size: tuple[int, int],
        name_column_header: QtW.QWidget,
        description_column_header: QtW.QWidget,
        environment_column_header: QtW.QWidget,
        env_config_dialog_factory: Callable,
        env_prep_progress_dialog_factory: Callable,
        analysis_alg_env_prep_signal: Signal,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ):
        super().__init__(parent, flags)
        self.setWindowTitle(title)
        self.setMinimumSize(*min_size)

        self._entries = dict[str, RegistryEntry]()

        self._env_config_dialog: EnvConfigDialog = env_config_dialog_factory(parent=self)
        self._env_prep_progress_dialog: EnvPrepProgressDialog = env_prep_progress_dialog_factory(
            parent=self
        )

        self._analysis_alg_env_prep_signal = analysis_alg_env_prep_signal

        layout = QtW.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(20)

        layout.addWidget(name_column_header, 0, Column.NAME, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(
            description_column_header, 0, Column.DESCRIPTION, Qt.AlignmentFlag.AlignLeft
        )
        layout.addWidget(
            environment_column_header, 0, Column.ENV_CONFIG, Qt.AlignmentFlag.AlignLeft
        )

        separator = QtW.QFrame()
        separator.setLineWidth(1)
        separator.setMidLineWidth(1)
        separator.setFrameShape(QtW.QFrame.Shape.HLine)
        layout.addWidget(separator, layout.rowCount(), 0, 1, 3)

        self.setLayout(layout)

    def add_algorithm(self, algorithm: Algorithm) -> None:
        layout: QtW.QGridLayout = self.layout()

        row_idx = layout.rowCount()

        # -------------------------------------- name label -------------------------------------- #

        name_label = QtW.QLabel(algorithm.name)
        name_label.setWordWrap(True)
        name_label.setSizePolicy(QtW.QSizePolicy.Policy.Fixed, QtW.QSizePolicy.Policy.Minimum)
        name_font = name_label.font()
        name_font.setBold(True)
        name_font.setPointSizeF(name_font.pointSizeF() + 1)
        name_label.setFont(name_font)

        # -------------------------------------- desc label -------------------------------------- #

        description_label = QtW.QLabel(algorithm.description)
        description_label.setWordWrap(True)
        description_label.setSizePolicy(
            QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Minimum
        )
        desc_font = description_label.font()
        desc_font.setPointSizeF(desc_font.pointSizeF() - 1)
        description_label.setFont(desc_font)

        # -------------------------------------- env button -------------------------------------- #

        env_config_button = QtW.QToolButton()
        env_config_button.setText("⚙")
        env_config_button.setSizePolicy(QtW.QSizePolicy.Policy.Fixed, QtW.QSizePolicy.Policy.Fixed)
        env_font = env_config_button.font()
        env_font.setBold(True)
        env_config_button.setFont(env_font)
        env_config_button.pressed.connect(lambda: self._open_env_config_dialog_for(algorithm))

        # --------------------------------------- add entry -------------------------------------- #

        self._entries[algorithm.name] = RegistryEntry(
            name_label=name_label,
            description_label=description_label,
            environment_config_button=env_config_button,
        )

        self._update_alg_env_state_color(algorithm)
        self._env_prep_progress_dialog.finished.connect(
            lambda _: self._update_alg_env_state_color(algorithm)
        )

        # ------------------------------------- add to layout ------------------------------------ #

        layout.addWidget(name_label, row_idx, Column.NAME)
        layout.addWidget(description_label, row_idx, Column.DESCRIPTION)
        layout.addWidget(env_config_button, row_idx, Column.ENV_CONFIG)

    def _open_env_config_dialog_for(self, algorithm: Algorithm) -> None:
        env_fields = algorithm.environment.model_fields.copy()
        env_fields.pop("state")

        env_parameters = self._env_config_dialog.open(env_fields)
        if env_parameters is not None:
            self._analysis_alg_env_prep_signal.emit(
                algorithm_name=algorithm.name,
                env_parameters=env_parameters,
            )

    def _update_alg_env_state_color(self, algorithm: Algorithm) -> None:
        env_config_button = self._entries[algorithm.name].environment_config_button
        if algorithm.environment.state == Environment.State.PREPARATION_SUCCESSFUL:
            env_config_button.setStyleSheet("background-color: darkgreen")
        elif algorithm.environment.state == Environment.State.PREPARATION_FAILED:
            env_config_button.setStyleSheet("background-color: darkred")

    def open_env_prep_progress_dialog(self, algorithm_name: str, task_future: Task.Future) -> None:
        return self._env_prep_progress_dialog.open(algorithm_name, task_future)

    def update_env_prep_progress_dialog(self, progress: float | None, message: str) -> None:
        self._env_prep_progress_dialog.update(progress, message)

    def open(self) -> None:
        self.exec()
