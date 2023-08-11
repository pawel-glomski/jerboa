from pathlib import Path

import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5.QtCore import Qt

from jerboa.ui.gui.common import PathSelector
from . import components


class MediaSourceSelectionDialog(QtW.QDialog):
  update_gui = QtCore.pyqtSignal(object)

  def __init__(
      self,
      path_selector: PathSelector,
      parent: QtW.QWidget | None = None,
      flags: Qt.WindowFlags | Qt.WindowType = Qt.WindowType.Dialog,
  ) -> None:
    super().__init__(parent, flags)
    self.setMinimumSize(600, 300)
    path_selector.path_selected_signal.connect(self._on_media_source_selected)

    self._panel_init = QtW.QLabel()
    self._panel_init.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self._panel_init.setText('Select a local file or enter the URL of a recording')

    self._panel_loading_spinner = components.LoadingSpinnerPanel()
    self._panel_avcontainer = components.AVContainerPanel()
    self._panel_streaming_site = components.StreamingSitePanel()

    self._content_panel = QtW.QStackedWidget()
    self._content_panel.setFrameShape(QtW.QFrame.Shape.Box)
    self._content_panel.setSizePolicy(QtW.QSizePolicy.Policy.Expanding,
                                      QtW.QSizePolicy.Policy.Expanding)
    self._content_panel.addWidget(self._panel_init)
    self._content_panel.addWidget(self._panel_loading_spinner)
    self._content_panel.addWidget(self._panel_avcontainer)
    self._content_panel.addWidget(self._panel_streaming_site)
    self._content_panel.setCurrentWidget(self._panel_init)

    decision_button_box = QtW.QDialogButtonBox(QtW.QDialogButtonBox.StandardButton.Cancel |
                                               QtW.QDialogButtonBox.StandardButton.Ok)
    self._cancel_button = decision_button_box.button(QtW.QDialogButtonBox.StandardButton.Cancel)
    self._ok_button = decision_button_box.button(QtW.QDialogButtonBox.StandardButton.Ok)

    self._cancel_button.setIcon(QtGui.QIcon())
    self._ok_button.setIcon(QtGui.QIcon())

    decision_button_box.accepted.connect(self.accept)
    decision_button_box.rejected.connect(self.reject)

    main_layout = QtW.QVBoxLayout(self)
    main_layout.addWidget(path_selector)
    main_layout.addWidget(self._content_panel)
    main_layout.addWidget(decision_button_box)
    self.setLayout(main_layout)

    self._error_dialog = QtW.QErrorMessage(parent=self)

    self._reset()

    self.update_gui.connect(lambda fn: fn())

  def _on_media_source_selected(self, media_source_path: str) -> None:
    self._reset()

    url = QtCore.QUrl.fromUserInput(
        media_source_path,
        str(Path('.').resolve()),
        QtCore.QUrl.UserInputResolutionOption.AssumeLocalFile,
    )

    error_message = None
    if url.isValid():
      self._content_panel.setCurrentWidget(self._panel_loading_spinner)

      if url.isLocalFile():
        if Path(url.toLocalFile()).is_file():
          import av

          from threading import Thread

          def open_container_task():
            container = av.open(url.toLocalFile())

            def update_gui():
              self._content_panel.setCurrentWidget(self._panel_avcontainer)
              self._panel_avcontainer.set_container(container)
              self._ok_button.setDisabled(False)

            # QtCore.QTimer.singleShot(1, update_gui)
            self.update_gui.emit(update_gui)

          # QtCore.QThread().
          Thread(target=open_container_task, daemon=True).start()
        else:
          error_message = 'Local file not found!'
      else:
        # related_content_panel = self._content_panel_streaming_site
        ...
    else:
      error_message = 'Media source path is invalid!'

    if error_message is not None:
      self._error_dialog.showMessage(error_message)
      # self._error_dialog.exec()

  def _reset(self):
    self._ok_button.setDisabled(True)
