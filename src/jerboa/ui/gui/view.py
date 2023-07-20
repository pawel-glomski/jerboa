import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore
from PyQt5 import QtGui
# from PyQt5 import QtMultimedia as QtMedia
from PyQt5.QtCore import Qt

from jerboa.ui import JerboaUI
from .media_source_selection_dialog import MediaSourceSelectionDialog


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


class JerboaView(JerboaUI):

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

    media_source_selection_dialog = MediaSourceSelectionDialog.create_default(
        parent=self._app_window)
    print(media_source_selection_dialog.exec())

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
