from typing import Callable

import PySide6.QtWidgets as QtW
from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt

from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool, ThreadSpawner


class GUIThreadPool(ThreadPool):
    def __init__(self, workers: int | None = None):
        super().__init__()
        self._thread_pool = QtCore.QThreadPool()
        if workers:
            self._thread_pool.setMaxThreadCount(workers)

    def start(self, job: Callable, *args, **kwargs):
        self._thread_pool.start(lambda: job(*args, **kwargs))

    def wait(self, timeout: int | None = None) -> bool:
        return self._thread_pool.waitForDone(-1 if timeout is None else timeout)


class GUIThreadSpawner(ThreadSpawner):
    class Worker(QtCore.QObject):
        finished = QtCore.Signal()

        def __init__(
            self,
            job: Callable,
            args: tuple | None = None,
            kwargs: dict | None = None,
        ):
            super().__init__()

            self._job = job
            self._args = args or tuple()
            self._kwargs = kwargs or {}

        def run(self) -> None:
            self._job(*self._args, **self._kwargs)
            self.finished.emit()

    def __init__(self):
        self._threads = dict[QtCore.QThread, GUIThreadSpawner.Worker]()

    def start(self, job: Callable, *args, **kwargs):
        thread = QtCore.QThread()

        def on_finished():
            thread.quit()
            self._threads.pop(thread)

        worker = GUIThreadSpawner.Worker(job, args, kwargs)
        worker.moveToThread(thread)
        worker.finished.connect(on_finished)

        thread.started.connect(worker.run)
        thread.start()

        self._threads[thread] = worker

    def wait(self, timeout: int | None = None) -> bool:
        for thread in self._threads:
            thread.wait(-1 if timeout is None else timeout)


class GUISignal(Signal):
    def __init__(  # pylint: disable=W0102:dangerous-default-value
        self,
        *arg_types: type,
        subscribers: list[Callable] = [],  # this is fine, it is read-only
        max_subscribers: int | str = "min",
    ):
        self._arg_types = arg_types
        self._signal_wrapper = GUISignal._dynamic_qt_signal(*arg_types)
        super().__init__(subscribers, max_subscribers)

    def connect(self, subscriber: Callable) -> None:
        super().connect(subscriber)
        self._signal_wrapper.signal.connect(subscriber)

    def emit(self, *args) -> None:
        self._signal_wrapper.signal.emit(*args)

    @staticmethod
    def _dynamic_qt_signal(*arg_types: type):
        class SignalWrapper(QtCore.QObject):
            signal = QtCore.Signal(*arg_types)

        return SignalWrapper()


class GUIApp:
    def __init__(self) -> None:
        self._app = QtW.QApplication([])

        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(53, 53, 53))
        palette.setColor(QtGui.QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QtGui.QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QtGui.QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(25, 25, 25))
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(53, 53, 53))
        palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(42, 130, 218))
        palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        palette.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(42, 130, 218))
        palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(53, 53, 53))
        palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)

        self._app.setStyle("Fusion")
        self._app.setPalette(palette)

    def run_event_loop(self) -> int:
        return self._app.exec()


class MainWindow(QtW.QMainWindow):
    def __init__(self, min_size: tuple[int, int], relative_size: [float, float]):
        super().__init__()
        self.setMinimumSize(*min_size)

        available_geometry = self.screen().availableGeometry()
        self.resize(
            int(available_geometry.width() * relative_size[0]),
            int(available_geometry.height() * relative_size[1]),
        )


class JerboaGUI:
    def __init__(
        self,
        gui_app: GUIApp,
        main_window: MainWindow,
        menu_bar: QtW.QMenuBar,
        main_widget: QtW.QWidget,
    ) -> None:
        self._gui_app = gui_app

        self._window = main_window
        self._window.setMenuBar(menu_bar)
        self._window.setCentralWidget(main_widget)

        # status_bar = self.statusBar()
        # status_bar.showMessage('Ready')
        # status_bar.setStyleSheet('''
        #   QStatusBar {
        #     border-top: 1px solid #413F42;
        #   }
        #   ''')

    def run_event_loop(self) -> int:
        self._window.show()
        return self._gui_app.run_event_loop()
