from typing import Callable, ContextManager
from PySide6 import QtCore as QtC

from jerboa.core.signal import Signal


class QtSignal(Signal):
    class SignalWrapper(QtC.QObject):
        signal = QtC.Signal(Signal.EmitArg)

    def __init__(self, /, *arg_names: str, max_subscribers: float = float("inf")):
        super().__init__(*arg_names, max_subscribers=max_subscribers)
        self._signal_wrapper = QtSignal.SignalWrapper()

    def connect(self, subscriber: Callable) -> None:
        super().connect(subscriber)
        self._signal_wrapper.signal.connect(QtC.Slot(Signal.EmitArg)(self.subscribers[-1]))

    def emit(self, /, **kwargs: dict) -> None:
        emit_arg = Signal.EmitArg(
            slot_kwargs=kwargs,
            promise=Signal.Promise(len(self.subscribers)),
        )
        self._signal_wrapper.signal.emit(emit_arg)
        return emit_arg.promise
