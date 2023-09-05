from functools import partial

import PyQt5.QtWidgets as QtW
from PyQt5.QtCore import QTimer

from jerboa.core.signal import Signal
from jerboa.core.file import PathProcessor


class PathSelector(QtW.QWidget):
    def __init__(
        self,
        path_processor: PathProcessor,
        select_local_file_button_text: str,
        placeholder_text: str,
        apply_button_text: str,
        local_file_extension_filter: str,
        path_invalid_signal: Signal,
        path_selected_signal: Signal,
        path_modified_signal: Signal,
    ) -> None:
        super().__init__()

        self._path_processor = path_processor

        self._select_local_file_button = QtW.QPushButton(select_local_file_button_text)
        self._select_local_file_button.setAutoDefault(False)
        self._select_local_file_button.clicked.connect(
            partial(
                self._on_select_local_file_button_click,
                extension_filter=local_file_extension_filter,
            )
        )

        self._apply_button = QtW.QPushButton(apply_button_text)
        self._apply_button.setAutoDefault(False)
        self._apply_button.clicked.connect(self._use_current_path)

        self._path_input = QtW.QLineEdit()
        self._path_input.setPlaceholderText(placeholder_text)
        self._path_input.returnPressed.connect(self._use_current_path)
        self._path_input.textChanged.connect(lambda _: path_modified_signal.emit())

        separator = QtW.QFrame()
        separator.setFrameShape(QtW.QFrame.VLine)

        layout = QtW.QHBoxLayout()
        layout.addWidget(self._select_local_file_button)
        layout.addWidget(separator)
        layout.addWidget(self._path_input)
        layout.addWidget(self._apply_button)
        self.setLayout(layout)

        self._path_invalid_signal = path_invalid_signal
        self._path_selected_signal = path_selected_signal
        self._path_modified_signal = path_modified_signal

        self.reset()

    @property
    def path_invalid_signal(self) -> Signal:
        return self._path_invalid_signal

    @property
    def path_selected_signal(self) -> Signal:
        return self._path_selected_signal

    @property
    def path_modified_signal(self) -> Signal:
        return self._path_modified_signal

    def reset(self) -> None:
        self._path_input.clear()
        self._path_input.setFocus()

    def _on_select_local_file_button_click(self, extension_filter: str) -> None:
        file_path, _ = QtW.QFileDialog.getOpenFileName(filter=extension_filter)
        if file_path:
            self._path_input.setText(file_path)
            self._use_current_path()

    def _use_current_path(self) -> None:
        self._path_input.clearFocus()
        self._apply_button.setDefault(False)

        def job():
            try:
                path = self._path_processor.process(self._path_input.text())
                self._path_selected_signal.emit(path)
            except PathProcessor.InvalidPathError as err:
                self._path_invalid_signal.emit(str(err))

        # had to add a delay, so when the path is selected with an 'Enter' press, the event won't
        # transfer to the gui elements created by the signal subscribers
        QTimer.singleShot(1, job)