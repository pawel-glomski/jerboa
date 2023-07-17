import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore

from jerboa.media import MediaType
from jerboa.ui.utils import seconds_to_hh_mm_ss
from jerboa.ui.gui.common import PropertiesCollection

PROPERTY_KEY_START_TIME = 'Start time'
PROPERTY_KEY_DURATION = 'Duration'
PROPERTY_KEY_CODEC = 'Codec'
PROPERTY_KEY_BIT_RATE = 'Bit rate'
PROPERTY_KEY_SAMPLE_RATE = 'Sample rate'
PROPERTY_KEY_FPS = 'FPS'
PROPERTY_KEY_RESOLUTION = 'Resolution'

# TODO: remove references to PyAV, introduce stream properties dataclass


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
      self.set_value(PROPERTY_KEY_DURATION, seconds_to_hh_mm_ss(stream.duration * stream.time_base))
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

    self._stream_properties = MediaStreamProperties(media_type)

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
