from typing import Callable, ContextManager
from PySide6 import QtCore as QtC

from jerboa.core.signal import Signal, EmitArg, NoOpContext


class QtSignal(Signal):
    class SignalWrapper(QtC.QObject):
        signal = QtC.Signal(EmitArg)

    def __init__(self, /, *arg_names: str, max_subscribers: float = float("inf")):
        super().__init__(*arg_names, max_subscribers=max_subscribers)
        self._signal_wrapper = QtSignal.SignalWrapper()

    def connect(self, subscriber: Callable) -> None:
        super().connect(subscriber)
        self._signal_wrapper.signal.connect(QtC.Slot(EmitArg)(self.subscribers[-1]))

    def emit(
        self,
        context: ContextManager = NoOpContext(),
        post_callback: Callable = lambda: None,
        /,
        **kwargs: dict,
    ) -> None:
        self._signal_wrapper.signal.emit(
            EmitArg(
                context=context,
                post_callback=post_callback,
                slot_kwargs=kwargs,
            )
        )
