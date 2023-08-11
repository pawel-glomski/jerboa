import typing
from PyQt5 import QtCore
import PyQt5.QtWidgets as QtW
from PyQt5.QtWidgets import QWidget

from jerboa.ui import JerboaUI


class GUIApp:

  def __init__(self) -> None:
    self._app = QtW.QApplication([])

  def run_event_loop(self) -> int:
    return self._app.exec()


class MainWindow(QtW.QMainWindow):

  def __init__(self, min_size: tuple[int, int], relative_size: [float, float]):
    super().__init__()
    self.setMinimumSize(*min_size)

    available_geometry = self.screen().availableGeometry()
    self.resize(
        int(available_geometry.width() * relative_size[0]),
        int(available_geometry.height() * relative_size[1]),
    )


class JerboaGUI(JerboaUI):

  def __init__(
      self,
      gui_app: GUIApp,
      main_window: MainWindow,
      menu_bar: QtW.QMenuBar,
      main_widget: QtW.QWidget,
  ) -> None:
    self._gui_app = gui_app

    self._window = main_window
    self._window.setMenuBar(menu_bar)
    self._window.setCentralWidget(main_widget)

    # status_bar = self.statusBar()
    # status_bar.showMessage('Ready')
    # status_bar.setStyleSheet('''
    #   QStatusBar {
    #     border-top: 1px solid #413F42;
    #   }
    #   ''')

  def run_event_loop(self) -> int:
    self._window.show()
    return self._gui_app.run_event_loop()
