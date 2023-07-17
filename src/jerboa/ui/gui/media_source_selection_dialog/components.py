from typing import Callable

import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5.QtCore import Qt

from jerboa.media import MediaType
from jerboa.ui.utils import seconds_to_hh_mm_ss
from jerboa.ui.gui.common import LabelValuePair, PropertiesCollection

PROPERTY_KEY_START_TIME = 'Start time'
PROPERTY_KEY_DURATION = 'Duration'
PROPERTY_KEY_CODEC = 'Codec'
PROPERTY_KEY_BIT_RATE = 'Bit rate'
PROPERTY_KEY_SAMPLE_RATE = 'Sample rate'
PROPERTY_KEY_FPS = 'FPS'
PROPERTY_KEY_RESOLUTION = 'Resolution'

# TODO: remove references to PyAV, introduce stream properties dataclass


class MediaSourcePathSelector(QtW.QWidget):

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

  class MediaStreamProperties(PropertiesCollection):

    def __init__(self, media_type: MediaType):
      super().__init__()
      self._media_type = media_type

      self.add_property(PROPERTY_KEY_START_TIME)
      self.add_property(PROPERTY_KEY_DURATION)
      self.add_property(PROPERTY_KEY_CODEC)
      self.add_property(PROPERTY_KEY_BIT_RATE)
      if media_type == MediaType.AUDIO:
        self.add_property(PROPERTY_KEY_SAMPLE_RATE)
      else:
        self.add_property(PROPERTY_KEY_FPS)
        self.add_property(PROPERTY_KEY_RESOLUTION)

    def set_stream(self, stream) -> None:
      if stream is None:
        self.clear_values()
      else:
        self.set_value(PROPERTY_KEY_START_TIME,
                       seconds_to_hh_mm_ss((stream.start_time or 0) * stream.time_base))
        self.set_value(PROPERTY_KEY_DURATION,
                       seconds_to_hh_mm_ss(stream.duration * stream.time_base))
        self.set_value(PROPERTY_KEY_CODEC, stream.codec.name)
        self.set_value(PROPERTY_KEY_BIT_RATE, stream.duration)
        if self._media_type == MediaType.AUDIO:
          self.set_value(PROPERTY_KEY_SAMPLE_RATE, stream.sample_rate)
        else:
          self.set_value(PROPERTY_KEY_FPS, f'{float(stream.guessed_rate):.2f}')
          self.set_value(PROPERTY_KEY_RESOLUTION, f'{stream.width}x{stream.height}')

  class MediaStreamSelector(QtW.QWidget):

    def __init__(self, media_type: MediaType):
      super().__init__()
      self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)
      self._media_type = media_type
      self._streams = []
      self._streams_combobox_label = QtW.QLabel(f'Selected {media_type.value} stream:')
      self._streams_combobox = QtW.QComboBox()
      self._streams_combobox.currentIndexChanged.connect(self._on_stream_change)
      stream_selection_layout = QtW.QHBoxLayout()
      stream_selection_layout.addWidget(self._streams_combobox_label)
      stream_selection_layout.addWidget(self._streams_combobox)

      self._stream_properties = AVContainerPanel.MediaStreamProperties(media_type)

      layout = QtW.QVBoxLayout()
      layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
      layout.addLayout(stream_selection_layout)
      layout.addWidget(self._stream_properties)
      self.setLayout(layout)

    def _on_stream_change(self):
      if self._streams_combobox.currentIndex() < 0:
        stream = None
      else:
        stream = self._streams[self._streams_combobox.currentIndex()]

      self._stream_properties.set_stream(stream)

    def set_available_streams(self, streams: list) -> None:
      assert all(MediaType(stream.type) == self._media_type for stream in streams)

      self._streams = streams
      self._streams_combobox.clear()
      if len(streams) > 0:
        self._streams_combobox.addItems([str(i) for i in range(len(streams))])
        self._streams_combobox.setCurrentIndex(0)

  def __init__(self):
    super().__init__()
    self._file_name = LabelValuePair('File name')

    self._audio_stream_selector = AVContainerPanel.MediaStreamSelector(MediaType.AUDIO)
    self._video_stream_selector = AVContainerPanel.MediaStreamSelector(MediaType.VIDEO)
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