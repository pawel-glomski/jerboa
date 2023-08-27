import PyQt5.QtWidgets as QtW
from PyQt5.QtCore import Qt

from jerboa.utils.file import JbPath
from jerboa.media.recognizer import MediaSource, MediaSorceRecognizer, RecognitionError
from jerboa.ui.gui.common import PathSelector, RejectAcceptDialogButtonBox
from .details_panel import DetailsPanel


class MediaSourceSelectionDialog(QtW.QDialog):

  def __init__(
      self,
      recognizer: MediaSorceRecognizer,
      path_selector: PathSelector,
      media_source_details_panel: DetailsPanel,
      button_box: RejectAcceptDialogButtonBox,
      parent: QtW.QWidget | None = None,
      flags: Qt.WindowFlags | Qt.WindowType = Qt.WindowType.Dialog,
  ) -> None:
    super().__init__(parent, flags)
    self.setMinimumSize(600, 300)

    self._recognizer = recognizer

    self._error_dialog = QtW.QErrorMessage(parent=self)

    path_selector.path_selected_signal.connect(self._on_media_source_selected)
    path_selector.path_invalid_signal.connect(self._error_dialog.showMessage)

    button_box.accepted.connect(self.accept)
    button_box.rejected.connect(self.reject)

    self._path_selector = path_selector
    self._media_source_details_panel = media_source_details_panel
    self._button_box = button_box

    main_layout = QtW.QVBoxLayout(self)
    main_layout.addWidget(path_selector)
    main_layout.addWidget(media_source_details_panel)
    main_layout.addWidget(button_box)
    self.setLayout(main_layout)

    self.reset()

  def open_clean(self) -> int:
    self.reset()
    return self.exec()

  def reset(self) -> None:
    self._path_selector.reset()
    self._media_source_details_panel.reset()
    self._button_box.reset()

  def _on_media_source_selected(self, media_source_path: JbPath) -> None:
    self._button_box.reset()
    self._recognizer.recognize(
        media_source_path,
        on_success=self._on_media_source_recognition_success,
        on_failure=self._on_media_source_recognition_failure,
    )

  def _on_media_source_recognition_success(self, media_source: MediaSource) -> None:
    self._media_source_details_panel.display_avcontainer(media_source.avcontainer)
    self._button_box.enable_accept()

  def _on_media_source_recognition_failure(self, recognition_error: RecognitionError) -> None:
    self._error_dialog.showMessage(recognition_error.message)
