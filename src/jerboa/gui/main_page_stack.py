from PySide6 import QtWidgets as QtW

from .player_page import PlayerPage


class MainPageStack(QtW.QStackedWidget):
    def __init__(
        self,
        player_page: PlayerPage,
        # settings_page,
        # plugins_page,
    ):
        super().__init__()

        self._player_page = player_page

        self.addWidget(self._player_page)
        self.setCurrentWidget(self._player_page)

    def show_player_page(self):
        self.setCurrentWidget(self._player_page)
