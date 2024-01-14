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


import pydantic

import PySide6.QtWidgets as QtW
from PySide6.QtCore import Qt

from jerboa.gui.common.parameter import ParameterCollection
from jerboa.gui.common.button_box import RejectAcceptButtonBox


class Dialog(QtW.QDialog):
    def __init__(
        self,
        title: str,
        min_size: tuple[int, int],
        parameter_collection: ParameterCollection,
        button_box: RejectAcceptButtonBox,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ):
        super().__init__(parent, flags)
        self.setWindowTitle(title)
        self.setMinimumSize(*min_size)

        self._env_params_collection = parameter_collection

        self._button_box = button_box
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._env_params_collection)
        layout.addWidget(self._button_box)
        self.setLayout(layout)

    def open(self, env_fields: dict[str, pydantic.fields.FieldInfo]) -> dict[str] | None:
        if len(env_fields) > 0:
            self._env_params_collection.reset(env_fields)
            self._button_box.reset()
            self.adjustSize()
            if self.exec() == QtW.QDialog.DialogCode.Accepted:
                return self._env_params_collection.get_parameters()
            return None
        return {}
