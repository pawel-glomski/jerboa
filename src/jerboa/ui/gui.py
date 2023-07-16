from pathlib import Path

import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore
from PyQt5 import QtGui
# from PyQt5 import QtMultimedia as QtMedia
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget

from jerboa.ui import JerboaUI
from jerboa.media import MediaType
from jerboa.logger import logger


class LabelValuePair(QtW.QWidget):

  def __init__(self, label: str, read_only=True):
    super().__init__()
    self._label = QtW.QLabel(f'{label}:')
    self._value = QtW.QLineEdit()
    self._value.setReadOnly(read_only)

    layout = QtW.QHBoxLayout()
    layout.addWidget(self._label)
    layout.addWidget(self._value)
    self.setLayout(layout)

  def set_value(self, value):
    self._value.setText(str(value))


class PropertiesContainer(QtW.QWidget):

  def __init__(self):
    super().__init__()
    self._values = dict[str, QtW.QLineEdit]()
    self._labels_layout = QtW.QVBoxLayout()
    self._values_layout = QtW.QVBoxLayout()

    main_layout = QtW.QHBoxLayout()
    main_layout.addLayout(self._labels_layout)
    main_layout.addLayout(self._values_layout)
    self.setLayout(main_layout)

  def add_property(self, key: str, read_only: bool = True):
    label = QtW.QLabel(f'{key}:')
    value = QtW.QLineEdit()
    value.setReadOnly(read_only)

    self._values[key] = value
    self._labels_layout.addWidget(label)
    self._values_layout.addWidget(value)
  
  def set_value(self, key: str, value):
    value_widget = self._values.get(key, None)
    if value_widget is not None:
      value_widget.setText(str(value))
    else:
      logger.error(f'Tried to set the value of a missing property: "{key}"')

  def reset_values(self):
    for value in self._values.values():
      value.setText('')


PROPERTY_KEY_START_TIME = 'Start time'
PROPERTY_KEY_DURATION = 'Duration'
PROPERTY_KEY_CODEC = 'Codec'
PROPERTY_KEY_BIT_RATE = 'Bit rate'
PROPERTY_KEY_SAMPLE_RATE = 'Sample rate'
PROPERTY_KEY_FPS = 'FPS'
PROPERTY_KEY_RESOLUTION = 'Resolution'


def seconds_to_hh_mm_ss(seconds):
  seconds = round(seconds)
  hours = seconds // 3600
  minutes = (seconds % 3600) // 60
  seconds = seconds % 60
  return f'{hours:02d}:{minutes:02d}:{seconds:02d}'

class MediaStreamSelection(QtW.QWidget):

  def __init__(self, media_type: MediaType):
    super().__init__()
    self._media_type = media_type
    self._streams = []
    self._streams_combobox_label = QtW.QLabel(f'Selected {media_type.value} stream:')
    self._streams_combobox = QtW.QComboBox()
    self._streams_combobox.currentIndexChanged.connect(self._on_stream_change)
    stream_selection_layout = QtW.QHBoxLayout()
    stream_selection_layout.addWidget(self._streams_combobox_label)
    stream_selection_layout.addWidget(self._streams_combobox)

    self._properties = PropertiesContainer()
    self._properties.add_property(PROPERTY_KEY_START_TIME)
    self._properties.add_property(PROPERTY_KEY_DURATION)
    self._properties.add_property(PROPERTY_KEY_CODEC)
    self._properties.add_property(PROPERTY_KEY_BIT_RATE)
    if media_type == MediaType.AUDIO:
      self._properties.add_property(PROPERTY_KEY_SAMPLE_RATE)
    else:
      self._properties.add_property(PROPERTY_KEY_FPS)
      self._properties.add_property(PROPERTY_KEY_RESOLUTION)

    layout = QtW.QVBoxLayout()
    layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
    layout.addLayout(stream_selection_layout)
    layout.addWidget(self._properties)
    self.setLayout(layout)

  def _on_stream_change(self):
    if self._streams_combobox.currentIndex() < 0:
      self._properties.reset_values()
    else:
      stream = self._streams[self._streams_combobox.currentIndex()]

      self._properties.set_value(PROPERTY_KEY_START_TIME,
                                 seconds_to_hh_mm_ss((stream.start_time or 0) * stream.time_base))
      self._properties.set_value(PROPERTY_KEY_DURATION,
                                 seconds_to_hh_mm_ss(stream.duration * stream.time_base))
      self._properties.set_value(PROPERTY_KEY_CODEC, stream.codec.name)
      self._properties.set_value(PROPERTY_KEY_BIT_RATE, stream.duration)
      if self._media_type == MediaType.AUDIO:
        self._properties.set_value(PROPERTY_KEY_SAMPLE_RATE, stream.sample_rate)
      else:
        self._properties.set_value(PROPERTY_KEY_FPS, f'{float(stream.guessed_rate):.2f}')
        self._properties.set_value(PROPERTY_KEY_RESOLUTION, f'{stream.width}x{stream.height}')

  def set_available_streams(self, streams: list) -> None:
    assert all(MediaType(stream.type) == self._media_type for stream in streams)

    self._streams = streams
    self._streams_combobox.clear()
    if len(streams) > 0:
      self._streams_combobox.addItems([str(i) for i in range(len(streams))])
      self._streams_combobox.setCurrentIndex(0)


class MediaContainerContentPanel(QtW.QWidget):

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

  def set_container(self, container) -> None:
    self._file_name.set_value(container.name)
    self._audio_stream_selector.set_available_streams(container.streams.audio)
    self._video_stream_selector.set_available_streams(container.streams.video)


class OpenMediaFileDialog(QtW.QDialog):
  update_gui = QtCore.pyqtSignal(object)

  def __init__(self,
               parent: QWidget | None = None,
               flags: Qt.WindowFlags | Qt.WindowType = Qt.WindowType.Dialog) -> None:
    super().__init__(parent, flags)
    self.setMinimumSize(600, 300)
    self._select_local_file_button = QtW.QPushButton('Select a local file')
    self._select_local_file_button.setAutoDefault(False)
    self._select_local_file_button.clicked.connect(self._on_select_local_file_button_click)
    self._media_source_path_input = QtW.QLineEdit()
    self._media_source_path_input.setPlaceholderText('Media file path (or URL)...')
    self._media_source_path_input.returnPressed.connect(self._apply_media_source_path_input)
    self._apply_button = QtW.QPushButton('Apply')
    self._apply_button.setAutoDefault(False)
    self._apply_button.clicked.connect(self._apply_media_source_path_input)
    separator = QtW.QFrame()
    separator.setFrameShape(QtW.QFrame.VLine)

    input_layout = QtW.QHBoxLayout()
    input_layout.addWidget(self._select_local_file_button)
    input_layout.addWidget(separator)
    input_layout.addWidget(self._media_source_path_input)
    input_layout.addWidget(self._apply_button)

    self._content_panel_container = MediaContainerContentPanel()
    self._content_panel_streaming_site = QtW.QLabel('remote')  # StreamingSiteContentPanel()

    spinner_movie = QtGui.QMovie(':/loading_spinner.gif')
    spinner_movie.setScaledSize(QtCore.QSize(30, 30))
    self._content_panel_loading_spinner = QtW.QLabel()
    self._content_panel_loading_spinner.setMovie(spinner_movie)
    self._content_panel_loading_spinner.show()
    self._content_panel_loading_spinner.movie().start()
    self._content_panel_loading_spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)

    self._content_panel_msg = QtW.QLabel('Select a local file or enter the URL of a recording')
    self._content_panel_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)

    self._content_panel = QtW.QStackedWidget()
    self._content_panel.setFrameShape(QtW.QFrame.Shape.Box)
    self._content_panel.setSizePolicy(QtW.QSizePolicy.Policy.Expanding,
                                      QtW.QSizePolicy.Policy.Expanding)
    self._content_panel.addWidget(self._content_panel_container)
    self._content_panel.addWidget(self._content_panel_streaming_site)
    self._content_panel.addWidget(self._content_panel_loading_spinner)
    self._content_panel.addWidget(self._content_panel_msg)
    self._content_panel.setCurrentWidget(self._content_panel_msg)

    self._ok_button = QtW.QPushButton('OK')
    self._ok_button.clicked.connect(self.accept)
    self._cancel_button = QtW.QPushButton('Cancel')
    self._cancel_button.setAutoDefault(False)
    self._cancel_button.clicked.connect(self.reject)

    bottom_layout = QtW.QHBoxLayout()
    bottom_layout.addWidget(self._cancel_button)
    bottom_layout.addWidget(self._ok_button)

    main_layout = QtW.QVBoxLayout(self)
    main_layout.addLayout(input_layout)
    main_layout.addWidget(self._content_panel)
    main_layout.addLayout(bottom_layout)
    self.setLayout(main_layout)

    self._reset()

    self.update_gui.connect(lambda fn: fn())

  def _on_select_local_file_button_click(self):
    file_path, _ = QtW.QFileDialog.getOpenFileName(
        filter='Media files (*.mp3 *.wav *.ogg *.flac *.mp4 *.avi *.mkv *.mov);; All files (*)')
    if file_path:
      self._media_source_path_input.setText(file_path)
      self._apply_media_source_path_input()

  def _apply_media_source_path_input(self):
    self._reset()

    url = QtCore.QUrl.fromUserInput(
        str(self._media_source_path_input.text()),
        str(Path('.').resolve()),
        QtCore.QUrl.UserInputResolutionOption.AssumeLocalFile,
    )

    error_msg = None
    if url.isValid():
      self._content_panel.setCurrentWidget(self._content_panel_loading_spinner)

      if url.isLocalFile():
        if Path(url.toLocalFile()).is_file():
          import av

          from threading import Thread

          def open_container_task():
            container = av.open(url.toLocalFile())

            def update_gui():
              self._content_panel.setCurrentWidget(self._content_panel_container)
              self._content_panel_container.set_container(container)
              self._media_source_path_input.clearFocus()
              self._ok_button.setDisabled(False)

            # QtCore.QTimer.singleShot(1, update_gui)
            self.update_gui.emit(update_gui)
          # QtCore.QThread().
          Thread(target=open_container_task, daemon=True).start()
        else:
          error_msg = 'Local file not found!'
      else:
        # related_content_panel = self._content_panel_streaming_site
        ...
    else:
      error_msg = 'Media source path is invalid!'

    if error_msg is not None:
      self._content_panel_msg.setText(error_msg)
      self._content_panel.setCurrentWidget(self._content_panel_msg)

  def _reset(self):
    self._ok_button.setDisabled(True)


class PlayerView(QtW.QWidget):

  def __init__(self):
    super().__init__()
    self._splitter = PlayerView._create_splitter()
    self._canvas = PlayerView._add_canvas(self._splitter)
    self._timeline = PlayerView._add_timeline(self._splitter)

    layout = QtW.QVBoxLayout()
    layout.addWidget(self._splitter)
    layout.setContentsMargins(QtCore.QMargins())
    self.setLayout(layout)

  @staticmethod
  def _create_splitter() -> QtW.QSplitter:
    splitter = QtW.QSplitter()
    splitter.setOrientation(Qt.Vertical)
    splitter.setStyleSheet('''
      QSplitter::handle {
        border-top: 1px solid #413F42;
        margin: 3px 0px;
      }
      ''')
    return splitter

  @staticmethod
  def _add_canvas(splitter: QtW.QSplitter) -> QtW.QLabel:
    canvas = QtW.QLabel('canvas')
    canvas.setFrameShape(QtW.QFrame.Shape.StyledPanel)
    canvas.setMinimumHeight(50)
    canvas.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    idx = splitter.count()
    splitter.addWidget(canvas)
    splitter.setStretchFactor(idx, 3)
    splitter.setCollapsible(idx, False)
    return canvas

  @staticmethod
  def _add_timeline(splitter: QtW.QSplitter) -> QtW.QWidget:
    timeline = QtW.QLabel('timeline')
    timeline.setMinimumHeight(50)
    timeline.setFrameShape(QtW.QFrame.Shape.StyledPanel)
    timeline.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    idx = splitter.count()
    splitter.addWidget(timeline)
    splitter.setStretchFactor(idx, 1)
    splitter.setCollapsible(idx, True)
    return timeline

  def set_canvas_pixmap(self, pixmap: QtGui.QPixmap) -> None:
    self._canvas.setPixmap(pixmap)


class JerboaGUI(JerboaUI):

  def __init__(self) -> None:
    self._app = QtW.QApplication([])
    self._app_window = QtW.QMainWindow()
    self._app_window.setMinimumSize(640, 360)

    available_geometry = self._app_window.screen().availableGeometry()
    self._app_window.resize(available_geometry.width() // 2, available_geometry.height() // 2)

    menu_bar = self._app_window.menuBar()
    file_menu = menu_bar.addMenu('File')
    file_menu.addAction('Open', self._open_file)
    # settings_menu = menu_bar.addMenu('Settings')
    # plugins_menu = menu_bar.addMenu('Plugins')

    # status_bar = self.statusBar()
    # status_bar.showMessage('Ready')
    # status_bar.setStyleSheet('''
    #   QStatusBar {
    #     border-top: 1px solid #413F42;
    #   }
    #   ''')

    self._player_view = PlayerView()

    self._views = QtW.QStackedWidget()
    self._views.addWidget(self._player_view)
    self._views.setCurrentIndex(0)
    self._app_window.setCentralWidget(self._views)
    # available_geometry = self._app_window.screen().availableGeometry()
    # self._app_window.resize(available_geometry.width() // 2, available_geometry.height() // 2)

  def _open_file(self):
    open_media_file_dialog = OpenMediaFileDialog(parent=self._app_window)
    print(open_media_file_dialog.exec())

    # audio_decoder = JerboaDecoder(dst_media_config=AudioConfig())
    # video_decoder = JerboaDecoder(dst_media_config=VideoConfig())

    # audio_decoder.start('path_to_file.mp4', stream_index=0, init_timeline=FragmentedTimeline())
    # video_decoder.start('path_to_file.mp4', stream_index=0, init_timeline=FragmentedTimeline())

    # self._media_player.play(audio_decoder, video_decoder)

  def run_event_loop(self) -> int:
    self._app_window.show()
    return self._app.exec()

  def display_video_frame(self, frame: QtGui.QPixmap):
    self._player_view.set_canvas_pixmap(frame)
