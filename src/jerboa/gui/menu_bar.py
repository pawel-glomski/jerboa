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


from dataclasses import dataclass

import PySide6.QtWidgets as QtW
import PySide6.QtGui as QtG

from jerboa.core.signal import Signal


@dataclass
class MenuAction:
    name: str
    signal: Signal


@dataclass
class Menu:
    name: str
    actions: list[MenuAction]


@dataclass
class MenuBar(QtW.QMenuBar):
    def __init__(self, menus: list[Menu], actions: list[MenuAction]):
        super().__init__()

        self.setStyleSheet(
            """QMenuBar {
                border-color: palette(dark);
                border-bottom-style: solid;
                border-width: 1px;
            }
            QMenuBar::item:disabled {
                color: palette(mid);
            }"""
        )

        # separator = QtW.QFrame(frameShape=QtW.QFrame.VLine)
        separator = QtG.QAction("|", parent=self)
        separator.setDisabled(True)

        for menu in menus:
            menu_widget = self.addMenu(menu.name)
            for action in menu.actions:
                menu_widget.addAction(action.name, action.signal.emit)

        self.addAction(separator)
        for action in actions:
            action = self.addAction(action.name, action.signal.emit)
