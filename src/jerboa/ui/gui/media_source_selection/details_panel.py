from typing import Callable

import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore, QtGui
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


class InitPanel(QtW.QLabel):

  def __init__(self, text: str):
    super().__init__(text)
    self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class LoadingSpinnerPanel(QtW.QWidget):

  def __init__(self, spinner_movie: QtGui.QMovie):
    super().__init__()
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


class DetailsPanel(QtW.QStackedWidget):

  def __init__(
      self,
      init_panel: InitPanel,
      loading_panel: LoadingSpinnerPanel,
  ) -> None:
    super().__init__()

    self.setFrameShape(QtW.QFrame.Shape.Box)
    self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    self._panel_loading_spinner = loading_panel
    self._panel_avcontainer = AVContainerPanel()
    self._panel_streaming_site = StreamingSitePanel()

    self.addWidget(init_panel)
    self.addWidget(self._panel_loading_spinner)
    self.addWidget(self._panel_avcontainer)
    self.addWidget(self._panel_streaming_site)
    self.setCurrentWidget(init_panel)

  def display_loading_spinner(self) -> None:
    self.setCurrentWidget(self._panel_loading_spinner)

  def display_avcontainer(self, avcontainer) -> None:
    self._panel_avcontainer.set_container(avcontainer)
    self.setCurrentWidget(self._panel_avcontainer)

  def display_streaming_site(self) -> None:
    self.setCurrentWidget(self._panel_streaming_site)
