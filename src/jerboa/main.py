import sys
from PyQt5 import QtCore
# from PyQt5 import QtGui
# from PyQt5 import QtMultimedia as QtMedia
import PyQt5.QtWidgets as QtW
from PyQt5.QtCore import Qt


class PlayerView(QtW.QWidget):

  def __init__(self):
    super().__init__()
    self._splitter = PlayerView._create_splitter()
    layout = QtW.QVBoxLayout()
    layout.addWidget(self._splitter)
    layout.setContentsMargins(QtCore.QMargins())
    self.setLayout(layout)

    PlayerView._add_canvas(self._splitter)
    PlayerView._add_timeline(self._splitter)

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
  def _add_canvas(splitter: QtW.QSplitter):
    canvas = QtW.QLabel('canvas')
    canvas.setFrameShape(QtW.QFrame.Shape.StyledPanel)
    canvas.setMinimumHeight(50)
    canvas.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    idx = splitter.count()
    splitter.addWidget(canvas)
    splitter.setStretchFactor(idx, 3)
    splitter.setCollapsible(idx, False)

  @staticmethod
  def _add_timeline(splitter: QtW.QSplitter):
    timeline = QtW.QLabel('timeline')
    timeline.setMinimumHeight(50)
    timeline.setFrameShape(QtW.QFrame.Shape.StyledPanel)
    timeline.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    idx = splitter.count()
    splitter.addWidget(timeline)
    splitter.setStretchFactor(idx, 1)
    splitter.setCollapsible(idx, True)


class MainWindow(QtW.QMainWindow):

  def __init__(self):
    super().__init__()
    self.setMinimumSize(640, 360)

    self._create_menu_bar()
    self._create_status_bar()

    self._player_view = PlayerView()

    self._views = QtW.QStackedWidget()
    self._views.addWidget(self._player_view)
    self._views.setCurrentIndex(0)
    self.setCentralWidget(self._views)

  def _create_menu_bar(self):
    menu_bar = self.menuBar()

    file_menu = menu_bar.addMenu('File')
    settings_menu = menu_bar.addMenu('Settings')
    plugins_menu = menu_bar.addMenu('Plugins')

  def _create_status_bar(self):
    status_bar = self.statusBar()
    status_bar.showMessage('Ready')
    status_bar.setStyleSheet('''
      QStatusBar {
        border-top: 1px solid #413F42;
      }
      ''')


class JerboaApp:

  def __init__(self, argv: list[str]) -> None:
    self._app = QtW.QApplication(argv)
    self._main_win = MainWindow()
    # available_geometry = self._main_win.screen().availableGeometry()
    # self._main_win.resize(available_geometry.width() // 2, available_geometry.height() // 2)

  def run(self) -> int:
    self._main_win.show()
    return self._app.exec()


def main():
  exit_code = JerboaApp(sys.argv).run()
  sys.exit(exit_code)


if __name__ == '__main__':
  main()
