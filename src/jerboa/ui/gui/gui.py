from typing import Callable

import PyQt5.QtWidgets as QtW
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget

from jerboa.ui import JerboaUI
from .player_view import PlayerView
from .media_source_selection_dialog import MediaSourceSelectionDialog


class GUIApp:

  def __init__(self) -> None:
    self._app = QtW.QApplication([])

  def run_event_loop(self) -> int:
    return self._app.exec()


class JerboaGUI(JerboaUI):

  def __init__(
      self,
      gui_app: GUIApp,
      menu_bar: QtW.QMenuBar,
  ) -> None:
    self._gui_app = gui_app

    self._window = QtW.QMainWindow()
    self._window.setMinimumSize(640, 360)

    available_geometry = self._window.screen().availableGeometry()
    self._window.resize(available_geometry.width() // 2, available_geometry.height() // 2)

    menu_bar = self._window.setMenuBar(menu_bar)

    # status_bar = self.statusBar()
    # status_bar.showMessage('Ready')
    # status_bar.setStyleSheet('''
    #   QStatusBar {
    #     border-top: 1px solid #413F42;
    #   }
    #   ''')

    # self._window.setCentralWidget(self._sub_views)

  def run_event_loop(self) -> int:
    self._window.show()
    return self._gui_app.run_event_loop()


class JerboaViewStack(QtW.QStackedWidget):

  def __init__(
      self,
      player_view: PlayerView,
      # settings_view,
      # plugins_view,
  ):
    super().__init__()
    self.addWidget(player_view)
    self.setCurrentWidget(player_view)
