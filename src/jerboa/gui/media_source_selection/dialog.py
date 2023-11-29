import PySide6.QtWidgets as QtW
from PySide6.QtCore import Qt


from jerboa.core.signal import Signal
from jerboa.core.file import JbPath
from jerboa.core.multithreading import Future
from jerboa.media.source import MediaSource
from jerboa.media.recognizer import MediaSourceRecognizer
from jerboa.gui.common.file import PathSelector
from jerboa.gui.common.button_box import RejectAcceptButtonBox
from jerboa.gui.common.panel_stack import PanelStack, HintPanel, LoadingSpinnerPanel
from .resolver import MediaSourceResolver


class Dialog(QtW.QDialog):
    def __init__(
        self,
        min_size: tuple[int, int],
        path_selector: PathSelector,
        panel_stack: PanelStack,
        hint_panel: HintPanel,
        loading_spinner_panel: LoadingSpinnerPanel,
        media_source_resolver: MediaSourceResolver,
        button_box: RejectAcceptButtonBox,
        recognizer: MediaSourceRecognizer,
        media_source_selected_signal: Signal,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        self.setMinimumSize(*min_size)

        self._path_selector = path_selector
        self._path_selector.path_selected_signal.connect(self._on_media_source_path_selected)
        self._path_selector.path_invalid_signal.connect(self._on_media_source_invalid_path)
        self._path_selector.path_modified_signal.connect(button_box.loose_accept_focus)

        self._panel_hint = hint_panel
        self._panel_loading = loading_spinner_panel
        self._panel_media_source_resolver = media_source_resolver
        self._panel_stack = panel_stack
        self._panel_stack.set_panels(
            [self._panel_hint, self._panel_loading, self._panel_media_source_resolver]
        )

        self._button_box = button_box
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

        self._recognizer = recognizer
        self._recognizer_task_future: Future | None = None

        self._error_dialog = QtW.QErrorMessage(parent=self)
        self._error_dialog.accepted.connect(self.reset)

        self._media_source_selected_signal = media_source_selected_signal

        main_layout = QtW.QVBoxLayout(self)
        main_layout.addWidget(path_selector)
        main_layout.addWidget(self._panel_stack)
        main_layout.addWidget(button_box)
        self.setLayout(main_layout)

        self.reset()

    def open_clean(self) -> int:
        self.reset()
        return self.exec()

    def reset(self) -> None:
        self._media_source = None

        self._path_selector.reset()
        self._panel_stack.setCurrentWidget(self._panel_hint)
        self._panel_media_source_resolver.reset()
        self._button_box.reset()

    def accept(self) -> None:
        super().accept()

        media_source = self._media_source
        if not self._media_source.is_resolved:
            media_source = self._panel_media_source_resolver.get_resolved_media_source()
            assert self._media_source.title == media_source.title
            assert media_source.is_resolved

        self._media_source_selected_signal.emit(media_source=media_source)

    def reject(self) -> None:
        if self._recognizer_task_future is not None:
            self._recognizer_task_future.abort()
            self._recognizer_task_future = None
        super().reject()

    def _on_media_source_path_selected(self, media_source_path: JbPath) -> None:
        self._button_box.reset()
        self._panel_stack.setCurrentWidget(self._panel_loading)

        if self._recognizer_task_future is not None:
            self._recognizer_task_future.abort()
        self._recognizer_task_future = self._recognizer.recognize(
            media_source_path,
            on_success=self._on_media_source_recognition_success,
            on_failure=self._on_media_source_recognition_failure,
        )

    def _on_media_source_recognition_success(self, media_source: MediaSource) -> None:
        self._media_source = media_source
        if media_source.is_resolved:
            self.accept()
        else:
            self._panel_media_source_resolver.set_media_source(media_source)
            self._panel_stack.setCurrentWidget(self._panel_media_source_resolver)
            self._button_box.enable_accept()

    def _on_media_source_recognition_failure(self, error_message: str) -> None:
        self._on_media_source_invalid_path(error_message)

    def _on_media_source_invalid_path(self, error_message: str):
        self.reset()
        self._error_dialog.showMessage(error_message)
