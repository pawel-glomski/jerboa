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


from PySide6 import QtWidgets as QtW

from jerboa.settings import PROJECT_NAME


class MainWindow(QtW.QMainWindow):
    def __init__(
        self,
        min_size: tuple[int, int],
        relative_size: [float, float],
        menu_bar: QtW.QMenuBar,
        main_widget: QtW.QWidget,
        status_bar: QtW.QStatusBar,
    ):
        super().__init__()
        self.setMinimumSize(*min_size)
        self.setWindowTitle(PROJECT_NAME)

        available_geometry = self.screen().availableGeometry()
        self.resize(
            int(available_geometry.width() * relative_size[0]),
            int(available_geometry.height() * relative_size[1]),
        )

        self.setMenuBar(menu_bar)
        self.setCentralWidget(main_widget)
        # self.setStatusBar(status_bar)
