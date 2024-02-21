# Jerboa - AI-powered media player
# Copyright (C) 2024 Paweł Głomski

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


from qtpy.QtGui import QResizeEvent
import qtpy.QtWidgets as QtW


class TextWidget(QtW.QLabel):
    def __init__(self, text: str, *, font_size_offset: float, bold: bool = False):
        super().__init__(text)

        font = self.font()
        font.setBold(bold)
        font.setPointSizeF(font.pointSizeF() + font_size_offset)

        self.setFont(font)
        self.setWordWrap(True)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
