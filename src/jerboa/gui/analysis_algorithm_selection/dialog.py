import PySide6.QtWidgets as QtW
import PySide6.QtCore as QtC
import PySide6.QtGui as QtG
from PySide6.QtCore import Qt

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
        configurator: AlgorithmConfigurator,
        button_box: gui.button_box.RejectAcceptButtonBox,
        analysis_algorithm_selected_signal: Signal,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle(title)
        self.setMinimumSize(*min_size)

        self._configurator = configurator

        self._button_box = button_box
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

        self._error_dialog = QtW.QErrorMessage(parent=self)

        self.analysis_algorithm_selected_signal = analysis_algorithm_selected_signal

        main_layout = QtW.QVBoxLayout(self)
        main_layout.addWidget(self._configurator)
        main_layout.addWidget(self._button_box)
        self.setLayout(main_layout)

    def open_for(self, algorithm: analysis.algorithm.Algorithm) -> int:
        self.reset(algorithm)
        return self.exec()

    def reset(self, algorithm: analysis.algorithm.Algorithm) -> None:
        self._algorithm = None

        self._configurator.reset(algorithm)
        self._button_box.reset()

    def reject(self) -> None:
        print("reject")
        super().reject()

    def accept(self) -> None:
        print("accept")
        super().accept()
