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


import qtpy.QtCore as QtC
import qtpy.QtWidgets as QtW
from qtpy.QtCore import Qt

from jerboa.core.multithreading import Task
from jerboa.gui.common.button_box import RejectAcceptButtonBox

MINIMUM = 0
MAXIMUM = 1000


class Dialog(QtW.QDialog):
    def __init__(
        self,
        title: str,
        min_size: tuple[int, int],
        init_message: str,
        button_box: RejectAcceptButtonBox,
        parent: QtW.QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ):
        super().__init__(parent, flags)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumSize(*min_size)

        self._title = title
        self._init_message = init_message

        self._message_label = QtW.QLabel()

        self._progress_bar = QtW.QProgressBar()
        self._progress_bar.setMinimum(MINIMUM)
        self._progress_bar.setMaximum(MAXIMUM)

        self._button_box = button_box
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._progress_bar, 1, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._message_label)
        layout.addWidget(
            self._button_box, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom
        )
        self.setLayout(layout)

    def open(self, algorithm_name: str, task_future: Task.Future) -> None:
        self.setWindowTitle(f"{self._title} ({algorithm_name})")
        self._message_label.setText(self._init_message)
        self._progress_bar.reset()
        self._button_box.reset()

        if self.exec() == QtW.QDialog.DialogCode.Rejected:
            task_future.abort()

    def update(self, progress: float | None, message: str) -> None:
        if progress is None:
            QtC.QTimer.singleShot(100, self.reject)
            return

        self._progress_bar.setValue(MINIMUM + (MAXIMUM - MINIMUM) * progress)
        if progress < 1:
            self._message_label.setText(message)
        else:
            self._button_box.enable_accept()
            QtC.QTimer.singleShot(100, self.accept)
