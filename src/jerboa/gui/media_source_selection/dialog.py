import PySide6.QtWidgets as QtW
from PySide6 import QtGui
from PySide6.QtCore import Qt


from jerboa.core.signal import Signal
from jerboa.core.file import JbPath
from jerboa.media.source import MediaSource
from jerboa.media.recognizer import MediaSourceRecognizer
from jerboa.gui.common.file import PathSelector
from jerboa.gui.common.button_box import RejectAcceptDialogButtonBox
from .resolver import MediaSourceResolver


class Dialog(QtW.QDialog):
    def __init__(
        self,
        min_size: tuple[int, int],
        hint_text: str,
        loading_spinner_movie: QtGui.QMovie,
        path_selector: PathSelector,
        media_source_resolver: MediaSourceResolver,
        button_box: RejectAcceptDialogButtonBox,
        recognizer: MediaSourceRecognizer,
        media_source_selected_signal: Signal,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        self.setMinimumSize(*min_size)

        self._recognizer = recognizer
        self._path_selector = path_selector
        self._button_box = button_box
        self._panel_media_source_resolver = media_source_resolver
        self._media_source_selected_signal = media_source_selected_signal

        self._panel_hint = Dialog._create_hint_panel(hint_text)
        self._panel_loading = Dialog._create_loading_panel(loading_spinner_movie)
        self._panel_stack = Dialog._create_panel_stack(
            hint_panel=self._panel_hint,
            loading_panel=self._panel_loading,
            media_source_resolver_panel=self._panel_media_source_resolver,
        )

        self._error_dialog = QtW.QErrorMessage(parent=self)
        self._error_dialog.accepted.connect(self.reset)

        path_selector.path_selected_signal.connect(self._on_media_source_path_selected)
        path_selector.path_invalid_signal.connect(self._on_media_source_invalid_path)
        path_selector.path_modified_signal.connect(button_box.loose_accept_focus)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        main_layout = QtW.QVBoxLayout(self)
        main_layout.addWidget(path_selector)
        main_layout.addWidget(self._panel_stack)
        main_layout.addWidget(button_box)
        self.setLayout(main_layout)

        self.reset()

    @staticmethod
    def _create_hint_panel(hint_text: str) -> QtW.QWidget:
        hint_panel = QtW.QLabel(hint_text)
        hint_panel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return hint_panel

    @staticmethod
    def _create_loading_panel(loading_spinner_movie: QtGui.QMovie) -> QtW.QWidget:
        loading_panel = QtW.QLabel()
        loading_panel.setMovie(loading_spinner_movie)
        loading_panel.movie().start()
        loading_panel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return loading_panel

    @staticmethod
    def _create_panel_stack(
        hint_panel: QtW.QWidget,
        loading_panel: QtW.QWidget,
        media_source_resolver_panel: QtW.QWidget,
    ) -> QtW.QStackedWidget:
        panel_stack = QtW.QStackedWidget()
        panel_stack.setFrameShape(QtW.QFrame.Shape.Box)
        panel_stack.setSizePolicy(
            QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding
        )
        panel_stack.addWidget(hint_panel)
        panel_stack.addWidget(loading_panel)
        panel_stack.addWidget(media_source_resolver_panel)
        return panel_stack

    def open_clean(self) -> int:
        self.reset()
        with self._recognizer:
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

    def _on_media_source_path_selected(self, media_source_path: JbPath) -> None:
        self._button_box.reset()
        self._panel_stack.setCurrentWidget(self._panel_loading)
        self._recognizer.recognize(
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
