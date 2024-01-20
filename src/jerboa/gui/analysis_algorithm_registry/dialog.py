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


from typing import Callable

import PySide6.QtWidgets as QtW
from PySide6.QtCore import Qt

from jerboa.core.multithreading import Task
from jerboa.core.signal import Signal
from jerboa.analysis.algorithm import Algorithm, AlgorithmInstanceDesc
from .env_config_dialog import Dialog as EnvConfigDialog
from .env_prep_progress_dialog import Dialog as EnvPrepProgressDialog
from .alg_config_dialog import Dialog as AlgConfigDialog
from .grid import Grid, Row, Column


class Dialog(QtW.QDialog):
    def __init__(
        self,
        title: str,
        min_size: tuple[int, int],
        grid: Grid,
        row_factory: Callable[[Algorithm], Row],
        env_config_dialog_factory: Callable,
        env_prep_progress_dialog_factory: Callable,
        alg_config_dialog_factory: Callable,
        alg_env_prep_singal: Signal,
        alg_run_signal: Signal,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ):
        super().__init__(parent, flags)
        self.setWindowTitle(title)
        self.setMinimumSize(*min_size)

        self._grid = grid
        self._row_factory = row_factory

        self._env_config_dialog: EnvConfigDialog = env_config_dialog_factory(parent=self)
        self._env_prep_progress_dialog: EnvPrepProgressDialog = env_prep_progress_dialog_factory(
            parent=self
        )
        self._alg_config_dialog: AlgConfigDialog = alg_config_dialog_factory(parent=self)

        self._alg_env_prep_singal = alg_env_prep_singal
        self._alg_run_signal = alg_run_signal

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._grid)
        self.setLayout(layout)

    def add_algorithm(self, algorithm: Algorithm) -> None:
        row = self._row_factory(algorithm)
        env_config_button: QtW.QToolButton = row.get(Column.ENV_CONFIG)
        run_button: QtW.QToolButton = row.get(Column.RUN)
        env_config_button.pressed.connect(lambda: self._open_env_config_dialog_for(algorithm))
        run_button.pressed.connect(lambda: self._run_algorithm(algorithm))

        self._grid.add_row(algorithm.name, row)

    def _open_env_config_dialog_for(self, algorithm: Algorithm) -> None:
        env_fields = algorithm.environment.model_fields.copy()
        env_fields.pop("state")

        env_parameters = self._env_config_dialog.open(env_fields)
        if env_parameters is not None:
            self._alg_env_prep_singal.emit(algorithm=algorithm, env_parameters=env_parameters)

    def _run_algorithm(self, algorithm: Algorithm):
        analysis_fields = algorithm.analysis_params_class.model_fields.copy()
        interpretation_fields = algorithm.interpretation_params_class.model_fields.copy()
        configuration = self._alg_config_dialog.open_for(analysis_fields, interpretation_fields)

        if configuration is not None:
            analysis_params, interpretation_params = configuration
            self._alg_run_signal.emit(
                alg_desc=AlgorithmInstanceDesc(
                    algorithm=algorithm,
                    analysis_params=algorithm.analysis_params_class.model_validate(
                        analysis_params, strict=True
                    ),
                    interpretation_params=algorithm.interpretation_params_class.model_validate(
                        interpretation_params, strict=True
                    ),
                )
            )

    def open_env_prep_progress_dialog(self, algorithm: Algorithm, task_future: Task.Future) -> None:
        # only show the progress dialog if the task takes longer
        task_future.wait(finishing_aborted=True, timeout=0.1)
        if not task_future.stage.is_finished(finishing_aborted=True):
            self._env_prep_progress_dialog.open(algorithm, task_future)

        self._grid.row(algorithm.name).reflect_state(algorithm.environment.state)

    def update_env_prep_progress_dialog(self, progress: float | None, message: str) -> None:
        self._env_prep_progress_dialog.update(progress, message)

    def open(self) -> None:
        self.exec()
