from dataclasses import dataclass

import PyQt5.QtWidgets as QtW

from jerboa.signal import Signal


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
    def __init__(self, menus: list[Menu]):
        super().__init__()

        for menu in menus:
            menu_widget = self.addMenu(menu.name)
            for action in menu.actions:
                menu_widget.addAction(action.name, action.signal.emit)
