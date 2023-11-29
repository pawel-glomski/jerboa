import PySide6.QtWidgets as QtW
import PySide6.QtCore as QtC
import PySide6.QtGui as QtG
from PySide6.QtCore import Qt

from jerboa.core.signal import Signal
from jerboa.analysis.registry import AlgorithmRegistry
from jerboa.analysis import algorithm as alg
from jerboa.gui.common.button_box import RejectAcceptButtonBox
from jerboa.gui.common.panel_stack import PanelStack, HintPanel
from jerboa.gui.common import property as gui_property


class AlgorithmSelector(QtW.QComboBox):
    def __init__(
        self,
        algorithm_registry: AlgorithmRegistry,
        algorithm_changed_signal: Signal,
    ) -> None:
        super().__init__()
        self.setSizeAdjustPolicy(QtW.QComboBox.SizeAdjustPolicy.AdjustToContents)

        self._algorithm_registry = algorithm_registry
        self._algorithms = list[type[alg.Algorithm]]()

        self._algorithm_changed_signal = algorithm_changed_signal
        self.currentIndexChanged.connect(self._on_index_changed)

    @property
    def algorithm_changed_signal(self) -> Signal:
        return self._algorithm_changed_signal

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
    def __init__(self, properties_collection: gui_property.PropertiesCollection) -> None:
        super().__init__()

        self._properties_collection = properties_collection

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._properties_collection)
        self.setLayout(layout)

    def reset(self, algorithm: type[alg.Algorithm] | None) -> None:
        properties = []

        if algorithm is not None:
            for option_info in algorithm.options_info.values():
                option_property = gui_property.from_algorithm_option(option_info)
                properties.append(option_property)

        self._properties_collection.reset(properties)


class Dialog(QtW.QDialog):
    class EventFilter(QtC.QObject):
        def eventFilter(self, _: QtC.QObject, event: QtC.QEvent):
            print("imhere1")
            if event.type() == QtC.QEvent.Type.KeyPress:
                print("imhere2")
                key_event: QtG.QKeyEvent = event
                if key_event.key() == Qt.Key.Key_Enter or key_event.key() == Qt.Key.Key_Return:
                    print("imhere3")
                    return True
            return False

    def __init__(
        self,
        min_size: tuple[int, int],
        algorithm_selector: AlgorithmSelector,
        configurator: AlgorithmConfigurator,
        button_box: RejectAcceptButtonBox,
        analysis_algorithm_selected_signal: Signal,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        self.setMinimumSize(*min_size)
        self.installEventFilter(Dialog.EventFilter())

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
