# Jerboa - AI-powered media player
# Copyright (C) 2023 Paweł Głomski

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


from qtpy import QtWidgets as QtW

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
