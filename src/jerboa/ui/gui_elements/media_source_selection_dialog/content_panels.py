import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5.QtCore import Qt

from jerboa.media import MediaType
from jerboa.ui.gui_elements.common import LabelValuePair
from .media_stream_selection import MediaStreamSelection


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

    self._audio_stream_selector = MediaStreamSelection(MediaType.AUDIO)
    self._video_stream_selector = MediaStreamSelection(MediaType.VIDEO)
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
