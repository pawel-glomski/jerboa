from PySide6 import QtWidgets as QtW

from .player_view import PlayerView


class MainViewStack(QtW.QStackedWidget):
    def __init__(
        self,
        player_view: PlayerView,
        # settings_view,
        # plugins_view,
    ):
        super().__init__()
        self.addWidget(player_view)
        self.setCurrentWidget(player_view)
