from typing import Callable

import PyQt5.QtWidgets as QtW

from functools import partial

from jerboa.signal import Signal


class PathSelector(QtW.QWidget):

  def __init__(
      self,
      select_local_file_button_text: str,
      placeholder_text: str,
      apply_button_text: str,
      local_file_extension_filter: str,
  ) -> None:
    super().__init__()

    self._select_local_file_button = QtW.QPushButton(select_local_file_button_text)
    self._select_local_file_button.setAutoDefault(False)
    self._select_local_file_button.clicked.connect(
        partial(self._on_select_local_file_button_click,
                extension_filter=local_file_extension_filter))

    self._media_source_path_input = QtW.QLineEdit()
    self._media_source_path_input.setPlaceholderText(placeholder_text)
    self._media_source_path_input.returnPressed.connect(self._apply_media_source_path)

    self._apply_button = QtW.QPushButton(apply_button_text)
    self._apply_button.setAutoDefault(False)
    self._apply_button.clicked.connect(self._apply_media_source_path)

    separator = QtW.QFrame()
    separator.setFrameShape(QtW.QFrame.VLine)

    layout = QtW.QHBoxLayout()
    layout.addWidget(self._select_local_file_button)
    layout.addWidget(separator)
    layout.addWidget(self._media_source_path_input)
    layout.addWidget(self._apply_button)
    self.setLayout(layout)

    self._path_selected_signal = Signal()

    self.reset()

  @property
  def path_selected_signal(self) -> Signal:
    return self._path_selected_signal

  def reset(self) -> None:
    self._media_source_path_input.clear()

  def _on_select_local_file_button_click(self, extension_filter: str) -> None:
    file_path, _ = QtW.QFileDialog.getOpenFileName(filter=extension_filter)
    if file_path:
      self._media_source_path_input.setText(file_path)
      self._apply_media_source_path()

  def _apply_media_source_path(self) -> None:
    self._media_source_path_input.clearFocus()
    self._path_selected_signal.emit(self._media_source_path_input.text())
