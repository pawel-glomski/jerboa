from typing import Callable

from pathlib import Path

import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5.QtCore import Qt

from jerboa.media import MediaType
from jerboa.ui.gui.common import LabelValuePair
from .media_stream_selector import MediaStreamSelector


class MediaSourceSelector(QtW.QWidget):

  def __init__(self) -> None:
    super().__init__()

    self._select_local_file_button = QtW.QPushButton('Select a local file')
    self._select_local_file_button.setAutoDefault(False)
    self._select_local_file_button.clicked.connect(self._on_select_local_file_button_click)

    separator = QtW.QFrame()
    separator.setFrameShape(QtW.QFrame.VLine)

    self._media_source_path_input = QtW.QLineEdit()
    self._media_source_path_input.setPlaceholderText('Media file path (or URL)...')
    self._media_source_path_input.returnPressed.connect(self._apply_media_source_path)

    self._apply_button = QtW.QPushButton('Apply')
    self._apply_button.setAutoDefault(False)
    self._apply_button.clicked.connect(self._apply_media_source_path)

    layout = QtW.QHBoxLayout()
    layout.addWidget(self._select_local_file_button)
    layout.addWidget(separator)
    layout.addWidget(self._media_source_path_input)
    layout.addWidget(self._apply_button)
    self.setLayout(layout)

    self._on_selected_callback: Callable[[str], None] = lambda _: ...

  def _on_select_local_file_button_click(self) -> None:
    file_path, _ = QtW.QFileDialog.getOpenFileName(
        filter='Media files (*.mp3 *.wav *.ogg *.flac *.mp4 *.avi *.mkv *.mov);; All files (*)')
    if file_path:
      self._media_source_path_input.setText(file_path)
      self._apply_media_source_path()

  def set_on_selected_callback(self, on_selected_callback: Callable[[str], None]) -> None:
    self._on_selected_callback = on_selected_callback

  def _apply_media_source_path(self) -> None:
    self._media_source_path_input.clearFocus()
    self._on_selected_callback(self._media_source_path_input.text())


class LoadingSpinnerPanel(QtW.QWidget):

  def __init__(self):
    super().__init__()
    spinner_movie = QtGui.QMovie(':/loading_spinner.gif')
    spinner_movie.setScaledSize(QtCore.QSize(30, 30))
    spinner = QtW.QLabel()
    spinner.setMovie(spinner_movie)
    spinner.show()
    spinner.movie().start()

    layout = QtW.QVBoxLayout()
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(spinner)
    self.setLayout(layout)


class AVContainerPanel(QtW.QWidget):

  def __init__(self):
    super().__init__()
    self._file_name = LabelValuePair('File name')

    self._audio_stream_selector = MediaStreamSelector(MediaType.AUDIO)
    self._video_stream_selector = MediaStreamSelector(MediaType.VIDEO)
    streams_selection_layout = QtW.QHBoxLayout()
    streams_selection_layout.addWidget(self._audio_stream_selector)
    streams_selection_layout.addWidget(self._video_stream_selector)

    main_layout = QtW.QVBoxLayout()
    main_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
    main_layout.addWidget(self._file_name)
    main_layout.addLayout(streams_selection_layout)
    self.setLayout(main_layout)

  # TODO: remove PyAV references and use dataclasses instead
  def set_container(self, container) -> None:
    self._file_name.set_value(container.name)
    self._audio_stream_selector.set_available_streams(container.streams.audio)
    self._video_stream_selector.set_available_streams(container.streams.video)


class StreamingSitePanel(QtW.QWidget):

  def __init__(self):
    super().__init__()
    layout = QtW.QVBoxLayout()
    layout.addWidget(QtW.QLabel('Remote'))
    self.setLayout(layout)


class MediaSourceSelectionDialog(QtW.QDialog):
  update_gui = QtCore.pyqtSignal(object)

  def __init__(
      self,
      media_source_selector: MediaSourceSelector,
      panel_init: QtW.QLabel,
      panel_loading_spinner: LoadingSpinnerPanel,
      panel_avcontainer: AVContainerPanel,
      panel_streaming_site: StreamingSitePanel,
      decision_button_box: QtW.QDialogButtonBox,
      parent: QtW.QWidget | None = None,
      flags: Qt.WindowFlags | Qt.WindowType = Qt.WindowType.Dialog,
  ) -> None:
    super().__init__(parent, flags)
    self.setMinimumSize(600, 300)

    media_source_selector.set_on_selected_callback(self._on_media_source_selected)

    self._panel_init = panel_init
    self._panel_init.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self._panel_init.setText('Select a local file or enter the URL of a recording')

    self._panel_loading_spinner = panel_loading_spinner
    self._panel_avcontainer = panel_avcontainer
    self._panel_streaming_site = panel_streaming_site

    self._content_panel = QtW.QStackedWidget()
    self._content_panel.setFrameShape(QtW.QFrame.Shape.Box)
    self._content_panel.setSizePolicy(QtW.QSizePolicy.Policy.Expanding,
                                      QtW.QSizePolicy.Policy.Expanding)
    self._content_panel.addWidget(self._panel_init)
    self._content_panel.addWidget(self._panel_loading_spinner)
    self._content_panel.addWidget(self._panel_avcontainer)
    self._content_panel.addWidget(self._panel_streaming_site)
    self._content_panel.setCurrentWidget(self._panel_init)

    self._ok_button = decision_button_box.button(QtW.QDialogButtonBox.StandardButton.Ok)
    self._cancel_button = decision_button_box.button(QtW.QDialogButtonBox.StandardButton.Cancel)

    decision_button_box.accepted.connect(self.accept)
    decision_button_box.rejected.connect(self.reject)

    main_layout = QtW.QVBoxLayout(self)
    main_layout.addWidget(media_source_selector)
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

  @staticmethod
  def create_default(
      parent: QtW.QWidget | None = None,
      flags: Qt.WindowFlags | Qt.WindowType = Qt.WindowType.Dialog) -> 'MediaSourceSelectionDialog':

    decision_button_box = QtW.QDialogButtonBox(QtW.QDialogButtonBox.StandardButton.Cancel |
                                               QtW.QDialogButtonBox.StandardButton.Ok)
    for button in decision_button_box.buttons():
      button.setIcon(QtGui.QIcon())

    return MediaSourceSelectionDialog(
        media_source_selector=MediaSourceSelector(),
        panel_init=QtW.QLabel(),
        panel_loading_spinner=LoadingSpinnerPanel(),
        panel_avcontainer=AVContainerPanel(),
        panel_streaming_site=StreamingSitePanel(),
        decision_button_box=decision_button_box,
        parent=parent,
        flags=flags,
    )
