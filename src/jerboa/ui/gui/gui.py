from typing import Callable

import PyQt5.QtWidgets as QtW
from PyQt5.QtCore import Qt

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
      player_view: PlayerView,
  ) -> None:
    self._gui_app = gui_app
    self._player_view = player_view

    self._window = QtW.QMainWindow()
    self._window.setMinimumSize(640, 360)

    available_geometry = self._window.screen().availableGeometry()
    self._window.resize(available_geometry.width() // 2, available_geometry.height() // 2)

    menu_bar = self._window.menuBar()
    file_menu = menu_bar.addMenu('File')
    file_menu.addAction('Open', self._on_file_open_action)
    # settings_menu = menu_bar.addMenu('Settings')
    # plugins_menu = menu_bar.addMenu('Plugins')

    # status_bar = self.statusBar()
    # status_bar.showMessage('Ready')
    # status_bar.setStyleSheet('''
    #   QStatusBar {
    #     border-top: 1px solid #413F42;
    #   }
    #   ''')

    self._sub_views = QtW.QStackedWidget()
    self._sub_views.addWidget(player_view)
    self._sub_views.setCurrentIndex(0)
    self._window.setCentralWidget(self._sub_views)

  def _on_file_open_action(self):

    media_source_selection_dialog = MediaSourceSelectionDialog(parent=self._window)
    print(media_source_selection_dialog.exec())

  def run_event_loop(self) -> int:
    self._window.show()
    return self._gui_app.run_event_loop()
