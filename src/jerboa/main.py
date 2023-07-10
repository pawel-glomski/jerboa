from typing import Callable

import sys
from abc import ABC, abstractmethod
from PyQt5 import QtCore
from PyQt5 import QtGui
# from PyQt5 import QtMultimedia as QtMedia
import PyQt5.QtWidgets as QtW
from PyQt5.QtCore import Qt

from jerboa.media import MediaType
from jerboa.media.source.decoder import JerboaDecoder, SkippingDecoder, SimpleDecoder


class MediaSource:

  def __init__(self):
    pass

  @property
  def audio_decoder(self) -> JerboaDecoder | None:
    return None

  @property
  def video_decoder(self) -> JerboaDecoder | None:
    return None


class PlaybackClock:

  def __init__(self) -> None:
    self._start_time = 0

  def time(self) -> float:
    return 0


class AudioPlayer(PlaybackClock):

  def __init__(self) -> None:
    super().__init__()


class VideoPlayer:

  def __init__(self, frame_display_fn: Callable[[QtGui.QPixmap], None]) -> None:
    self._frame_display_fn = frame_display_fn
    self._playback_clock: PlaybackClock | None = None

  def play(self, playback_clock: PlaybackClock = PlaybackClock()):
    ...


class MediaPlayer:

  def __init__(self, audio_player: AudioPlayer, video_player: VideoPlayer) -> None:
    self._audio_player = audio_player
    self._video_player = video_player

  def play(self, audio_decoder: JerboaDecoder, video_decoder: JerboaDecoder, start_time: float):
    self.reset()

    if audio_decoder.has_audio:
      audio_decoder = media_source.decode(MediaType.Audio, start_time=start_time)
      self._audio_player.play(audio_decoder)

      playback_clock = self._audio_player
    else:
      playback_clock = PlaybackClock()

    if media_source.has_video:
      video_decoder = media_source.decode(MediaType.Video, start_time=start_time)
      self._video_player.play(playback_clock=playback_clock)

  def reset(self):
    self._audio_player.reset()
    self._video_player.reset()


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


class JerboaUI(ABC):

  @abstractmethod
  def run_event_loop(self) -> int:
    raise NotImplementedError()

  @abstractmethod
  def display_video_frame(self, frame):
    raise NotImplementedError()


class JerboaGUI(JerboaUI):

  def __init__(self) -> None:
    self._app = QtW.QApplication([])
    self._app_window = QtW.QMainWindow()
    self._app_window.setMinimumSize(640, 360)

    # menu_bar = self.menuBar()
    # file_menu = menu_bar.addMenu('File')
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

  def run_event_loop(self) -> int:
    self._app_window.show()
    return self._app.exec()

  def display_video_frame(self, frame: QtGui.QPixmap):
    self._player_view.set_canvas_pixmap(frame)


class JerboaApp:

  def __init__(self, ui: JerboaUI) -> None:
    self._ui = ui

    audio_player = AudioPlayer()
    video_player = VideoPlayer(frame_display_fn=ui.display_video_frame)
    self._media_player = MediaPlayer(audio_player=audio_player, video_player=video_player)

  def run(self):
    return self._ui.run_event_loop()


def main():
  ui = JerboaGUI()
  app = JerboaApp(ui)
  sys.exit(app.run())


if __name__ == '__main__':
  main()
