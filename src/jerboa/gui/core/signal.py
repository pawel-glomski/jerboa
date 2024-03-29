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


from typing import Callable
from PySide6 import QtCore as QtC

from jerboa.core.signal import Signal


class QtSignal(Signal):
    class SignalWrapper(QtC.QObject):
        signal = QtC.Signal(Signal.EmitArg)

    def __init__(self, *arg_names: str, max_subscribers: float = float("inf")):
        super().__init__(*arg_names, max_subscribers=max_subscribers)
        self._signal_wrapper = QtSignal.SignalWrapper()

    def connect(self, subscriber: Callable) -> None:
        super().connect(subscriber)
        self._signal_wrapper.signal.connect(QtC.Slot(Signal.EmitArg)(self.subscribers[-1]))

    def emit(self, **kwargs: dict) -> None:
        emit_arg = Signal.EmitArg(
            slot_kwargs=kwargs,
            promise=Signal.Promise(len(self.subscribers)),
        )
        self._signal_wrapper.signal.emit(emit_arg)
        return emit_arg.promise
