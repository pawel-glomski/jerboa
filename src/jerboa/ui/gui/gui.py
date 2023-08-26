from typing import Any, Callable
import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore

from jerboa.signal import Signal
from jerboa.ui import JerboaUI


class GUISignal(Signal):

  def __init__(  # pylint: disable=W0102:dangerous-default-value
      self,
      *arg_types: type,
      subscribers: list[Callable] = [],  # this is fine, it is read-only
      max_subscribers: int | str = 'min',
  ):
    self._signal_wrapper = GUISignal._dynamic_qt_signal(*arg_types)
    super().__init__(subscribers, max_subscribers)

  def connect(self, subscriber: Callable) -> None:
    super().connect(subscriber)
    self._signal_wrapper.connect(subscriber)

  def emit(self, *args) -> None:
    self._signal_wrapper.emit(*args)

  @staticmethod
  def _dynamic_qt_signal(*arg_types: type) -> QtCore.pyqtBoundSignal:

    class SignalWrapper(QtCore.QObject):
      _signal = QtCore.pyqtSignal(*arg_types)

      def __getattr__(self, name: str) -> Any:
        return getattr(self._signal, name)

      def __setattr__(self, name, value):
        if name == "_signal":
          super().__setattr__(name, value)
        else:
          setattr(self._signal, name, value)

      def __delattr__(self, name):
        delattr(self._signal, name)

    return SignalWrapper()


class GUIApp:

  def __init__(self) -> None:
    self._app = QtW.QApplication([])

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


class JerboaGUI(JerboaUI):

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
