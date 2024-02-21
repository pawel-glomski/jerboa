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


import qtpy.QtWidgets as QtW
import qtpy.QtGui as QtG
from qtpy.QtCore import Qt


class PageStack(QtW.QStackedWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QtW.QFrame.Shape.Box)
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    def set_pages(self, pages: list[QtW.QWidget]) -> None:
        while self.count() > 0:
            self.removeWidget(self.widget(0))
        for page in pages:
            self.addWidget(page)


class MessagePage(QtW.QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class LoadingSpinnerPage(QtW.QLabel):
    def __init__(self, loading_spinner_movie: QtG.QMovie):
        super().__init__()
        self.setMovie(loading_spinner_movie)
        self.movie().start()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
