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


import PySide6.QtWidgets as QtW


class ErrorMessageDialogFactory:
    def __init__(self, title: str, default_parent: QtW.QWidget) -> None:
        self._title = title
        self._default_parent = default_parent

    def open(
        self,
        message: str,
        title: str | None = None,
        parent: QtW.QWidget | None = None,
    ) -> None:
        if title is not None:
            main_message = title
            details = message
        else:
            main_message = message
            details = None

        dialog = QtW.QMessageBox(
            QtW.QMessageBox.Icon.NoIcon,
            self._title,
            main_message,
            parent=(parent or self._default_parent),
        )
        dialog.setModal(True)
        if details is not None:
            dialog.setDetailedText(details)
        dialog.exec()
