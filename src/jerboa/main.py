import sys
# import PyQt5.QtCore as QtCore
# import PyQt5.QtGui as QtGui
# import PyQt5.QtMultimedia as QtMedia
import PyQt5.QtWidgets as QtW
from PyQt5.QtCore import Qt


class PlayerView(QtW.QMainWindow):

  def __init__(self):
    super().__init__()

    self._content = QtW.QSplitter()
    self._content.setMinimumSize(400, 300)
    self._content.setSizePolicy(QtW.QSizePolicy.Policy.MinimumExpanding,
                                QtW.QSizePolicy.Policy.MinimumExpanding)
    self._content.setOrientation(Qt.Vertical)
    self._content.setStyleSheet('''
      QSplitter::handle {
        border-top: 1px solid #413F42;
        margin: 3px 0px;
      }
      ''')
    self.setCentralWidget(self._content)

    self._add_canvas()
    self._add_timeline()

  def _add_canvas(self):
    canvas = QtW.QFrame()
    canvas.setFrameShape(QtW.QFrame.Shape.Box)
    canvas.setMinimumHeight(150)
    canvas.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    idx = self._content.count()
    self._content.addWidget(canvas)
    self._content.setStretchFactor(idx, 4)
    self._content.setCollapsible(idx, False)

  def _add_timeline(self):
    timeline = QtW.QFrame()
    timeline.setMinimumHeight(50)
    timeline.setFrameShape(QtW.QFrame.Shape.Box)
    timeline.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    idx = self._content.count()
    self._content.addWidget(timeline)
    self._content.setStretchFactor(idx, 1)
    self._content.setCollapsible(idx, True)


class MainWindow(QtW.QMainWindow):

  def __init__(self):
    super().__init__()

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
    available_geometry = self._main_win.screen().availableGeometry()
    self._main_win.resize(available_geometry.width() // 2, available_geometry.height() // 2)

  def run(self) -> int:
    self._main_win.show()
    return self._app.exec()


def main():
  exit_code = JerboaApp(sys.argv).run()
  sys.exit(exit_code)


if __name__ == '__main__':
  main()
