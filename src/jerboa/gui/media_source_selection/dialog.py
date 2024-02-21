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


import qtpy.QtWidgets as QtW
from qtpy.QtCore import Qt


from jerboa.core.signal import Signal
from jerboa.core.file import JbPath
from jerboa.core.multithreading import Task
from jerboa.media.source import MediaSource
from jerboa.media.recognizer import MediaSourceRecognizer
from jerboa.gui.common.file import PathSelector
from jerboa.gui.common.button_box import RejectAcceptButtonBox
from jerboa.gui.common.page_stack import PageStack, MessagePage, LoadingSpinnerPage
from .resolver import MediaSourceResolver


class Dialog(QtW.QDialog):
    def __init__(
        self,
        title: str,
        min_size: tuple[int, int],
        path_selector: PathSelector,
        page_stack: PageStack,
        hint_page: MessagePage,
        loading_spinner_page: LoadingSpinnerPage,
        media_source_resolver: MediaSourceResolver,
        button_box: RejectAcceptButtonBox,
        recognizer: MediaSourceRecognizer,
        recognizer_success_signal: Signal,
        recognizer_failure_signal: Signal,
        media_source_selected_signal: Signal,
        show_error_message_signal: Signal,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle(title)
        self.setMinimumSize(*min_size)

        self._path_selector = path_selector
        self._path_selector.path_selected_signal.connect(self._on_media_source_path_selected)
        self._path_selector.path_invalid_signal.connect(self._on_media_source_invalid_path)
        self._path_selector.path_modified_signal.connect(button_box.loose_accept_focus)

        self._page_hint = hint_page
        self._page_loading = loading_spinner_page
        self._page_media_source_resolver = media_source_resolver
        self._page_stack = page_stack
        self._page_stack.set_pages(
            [self._page_hint, self._page_loading, self._page_media_source_resolver]
        )

        self._button_box = button_box
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

        self._recognizer = recognizer
        self._recognizer_task_future: Task.Future | None = None

        self._recognizer_success_signal = recognizer_success_signal
        self._recognizer_failure_signal = recognizer_failure_signal
        self._recognizer_success_signal.connect(self._on_media_source_recognition_success)
        self._recognizer_failure_signal.connect(self._on_media_source_recognition_failure)
        self._media_source_selected_signal = media_source_selected_signal
        self._show_error_message_signal = show_error_message_signal

        main_layout = QtW.QVBoxLayout(self)
        main_layout.addWidget(path_selector)
        main_layout.addWidget(self._page_stack)
        main_layout.addWidget(button_box)
        self.setLayout(main_layout)

        self.reset()

    def open_clean(self) -> int:
        self.reset()
        return self.exec()

    def reset(self) -> None:
        self._media_source = None

        self._path_selector.reset()
        self._page_stack.setCurrentWidget(self._page_hint)
        self._page_media_source_resolver.reset()
        self._button_box.reset()

    def accept(self) -> None:
        super().accept()

        media_source = self._media_source
        if not self._media_source.is_resolved:
            media_source = self._page_media_source_resolver.get_resolved_media_source()
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
        self._page_stack.setCurrentWidget(self._page_loading)

        if self._recognizer_task_future is not None:
            self._recognizer_task_future.abort()
        self._recognizer_task_future = self._recognizer.recognize(
            media_source_path,
            success_signal=self._recognizer_success_signal,
            failure_signal=self._recognizer_failure_signal,
        )

    def _on_media_source_recognition_success(self, media_source: MediaSource) -> None:
        self._media_source = media_source
        if media_source.is_resolved:
            self.accept()
        else:
            self._page_media_source_resolver.set_media_source(media_source)
            self._page_stack.setCurrentWidget(self._page_media_source_resolver)
            self._button_box.enable_accept()

    def _on_media_source_recognition_failure(self, error_message: str) -> None:
        self._on_media_source_invalid_path(error_message)

    def _on_media_source_invalid_path(self, error_message: str):
        self.reset()
        self._show_error_message_signal.emit(message=error_message, parent=self)
