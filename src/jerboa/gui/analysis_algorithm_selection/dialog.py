import PySide6.QtWidgets as QtW
import PySide6.QtCore as QtC
import PySide6.QtGui as QtG
from PySide6.QtCore import Qt

from jerboa.core.signal import Signal
from jerboa import analysis
from jerboa.gui import common as gui


class AlgorithmSelector(QtW.QComboBox):
    def __init__(self, algorithm_changed_signal: Signal) -> None:
        super().__init__()
        self.setSizeAdjustPolicy(QtW.QComboBox.SizeAdjustPolicy.AdjustToContents)

        self._algorithms = list[type[analysis.algorithm.Algorithm]]()

        self._algorithm_changed_signal = algorithm_changed_signal
        self.currentIndexChanged.connect(self._on_index_changed)

    @property
    def algorithm_changed_signal(self) -> Signal:
        return self._algorithm_changed_signal

    def add_algorithm(self, algorithm: type[analysis.algorithm.Algorithm]) -> None:
        self._algorithms.append(algorithm)
        self.addItem(algorithm.NAME)

    def reset(self) -> None:
        # copy the list, to ensure valid (index -> algorithm) mapping
        self._algorithms = list(self._algorithm_registry.algorithms)

        self.clear()
        self.addItems(alg.NAME for alg in self._algorithms)

    def _on_index_changed(self):
        idx = self.currentIndex()
        if idx <= -1:
            self.algorithm_changed_signal.emit(algorithm=None)
        else:
            self.algorithm_changed_signal.emit(algorithm=self._algorithms[idx])


class AlgorithmConfigurator(QtW.QWidget):
    def __init__(self, parameter_collection: gui.parameter.ParameterCollection) -> None:
        super().__init__()

        self._parameter_collection = parameter_collection

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._parameter_collection)
        self.setLayout(layout)

    def reset(self, algorithm: type[analysis.algorithm.Algorithm] | None) -> None:
        parameters = []

        if algorithm is not None:
            for parameter_info in algorithm.parameters_info.values():
                parameter_widget = gui.parameter.from_algorithm_parameter(parameter_info)
                parameters.append(parameter_widget)

        self._parameter_collection.reset(parameters)


class Dialog(QtW.QDialog):
    def __init__(
        self,
        min_size: tuple[int, int],
        algorithm_selector: AlgorithmSelector,
        configurator: AlgorithmConfigurator,
        button_box: gui.button_box.RejectAcceptButtonBox,
        analysis_algorithm_selected_signal: Signal,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        self.setMinimumSize(*min_size)

        self._algorithm_selector = algorithm_selector
        self._algorithm_selector.algorithm_changed_signal.connect(configurator.reset)

        self._configurator = configurator

        self._button_box = button_box
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

        self._error_dialog = QtW.QErrorMessage(parent=self)

        self.analysis_algorithm_selected_signal = analysis_algorithm_selected_signal

        main_layout = QtW.QVBoxLayout(self)
        main_layout.addWidget(self._algorithm_selector)
        main_layout.addWidget(self._configurator)
        main_layout.addWidget(self._button_box)
        self.setLayout(main_layout)

        self.reset()

    def open_clean(self) -> int:
        self.reset()
        return self.exec()

    def reset(self) -> None:
        self._algorithm = None

        self._algorithm_selector.reset()
        self._button_box.reset()

    def reject(self) -> None:
        print("reject")
        super().reject()

    def accept(self) -> None:
        print("accept")
        super().accept()
