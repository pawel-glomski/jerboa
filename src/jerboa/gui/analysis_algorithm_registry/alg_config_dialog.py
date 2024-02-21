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


import qtpy.QtWidgets as QtW
import qtpy.QtCore as QtC
import qtpy.QtGui as QtG
from qtpy.QtCore import Qt

from jerboa.core.signal import Signal
from jerboa import analysis
from jerboa.gui import common as gui


class AlgorithmConfigurator(QtW.QWidget):
    def __init__(self, parameter_collection: gui.parameter.ParameterCollection) -> None:
        super().__init__()

        self._parameter_collection = parameter_collection

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._parameter_collection)
        self.setLayout(layout)

    def reset(self, algorithm: analysis.algorithm.Algorithm) -> None:
        parameters = []

        # if algorithm is not None:
        #     for parameter_info in algorithm.parameters_info.values():
        #         parameter_widget = gui.parameter.from_algorithm_parameter(parameter_info)
        #         parameters.append(parameter_widget)

        # self._parameter_collection.reset(parameters)


class Dialog(QtW.QDialog):
    def __init__(
        self,
        title: str,
        min_size: tuple[int, int],
        analysis_params_configurator: gui.parameter.ParameterConfigurator,
        interpretation_params_configurator: gui.parameter.ParameterConfigurator,
        button_box: gui.button_box.RejectAcceptButtonBox,
        analysis_alg_selected_signal: Signal,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle(title)
        self.setMinimumSize(*min_size)

        self._analysis_params_configurator = analysis_params_configurator
        self._interpretation_params_configurator = interpretation_params_configurator

        self._button_box = button_box
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

        self._error_dialog = QtW.QErrorMessage(parent=self)

        self._analysis_alg_selected_signal = analysis_alg_selected_signal

        main_layout = QtW.QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self._analysis_params_configurator, 0, Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(
            self._interpretation_params_configurator, 0, Qt.AlignmentFlag.AlignTop
        )
        main_layout.addStretch(1)
        main_layout.addWidget(self._button_box, 0, Qt.AlignmentFlag.AlignBottom)
        self.setLayout(main_layout)

    def open_for(
        self,
        analysis_fields: dict,
        interpretation_fields: dict,
    ) -> tuple[dict[str], dict[str]] | None:
        self._algorithm = None

        self._analysis_params_configurator.set_fields(analysis_fields)
        self._interpretation_params_configurator.set_fields(interpretation_fields)

        self._button_box.reset()

        if self.exec() == QtW.QDialog.DialogCode.Accepted:
            return (
                self._analysis_params_configurator.get_configuration(),
                self._interpretation_params_configurator.get_configuration(),
            )
        return None
