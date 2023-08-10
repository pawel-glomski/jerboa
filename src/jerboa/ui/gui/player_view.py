import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore
from PyQt5 import QtGui
# from PyQt5 import QtMultimedia as QtMedia
from PyQt5.QtCore import Qt


class Canvas(QtW.QLabel):
  def __init__(self):
    super().__init__()

    self.setText('canvas')
    self.setFrameShape(QtW.QFrame.Shape.StyledPanel)
    self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)
    self.setMinimumHeight(50)

class PlayerView(QtW.QWidget):

  def __init__(self, canvas: Canvas):
    super().__init__()

    self._canvas = canvas

    self._splitter = QtW.QSplitter()
    self._splitter.setOrientation(Qt.Vertical)
    self._splitter.setStyleSheet('''
      QSplitter::handle {
        border-top: 1px solid #413F42;
        margin: 3px 0px;
      }
      ''')
    self._add_widget(canvas, stretch_factor=3, collapsible=False)

    self._timeline = PlayerView._add_timeline(self._splitter)

    layout = QtW.QVBoxLayout()
    layout.addWidget(self._splitter)
    layout.setContentsMargins(QtCore.QMargins())
    self.setLayout(layout)

  def _add_widget(self, widget: QtW.QWidget, stretch_factor: int, collapsible: bool):
    idx = self._splitter.count()
    self._splitter.addWidget(widget)
    self._splitter.setStretchFactor(idx, stretch_factor)
    self._splitter.setCollapsible(idx, collapsible)

  @staticmethod
  def _add_timeline(splitter: QtW.QSplitter) -> QtW.QWidget:
    timeline = QtW.QLabel('timeline')
    timeline.setMinimumHeight(50)
    timeline.setFrameShape(QtW.QFrame.Shape.StyledPanel)
    timeline.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    idx = splitter.count()
    splitter.addWidget(timeline)
    splitter.setStretchFactor(idx, 1)
    splitter.setCollapsible(idx, True)
    return timeline

  def set_canvas_pixmap(self, pixmap: QtGui.QPixmap) -> None:
    self._canvas.setPixmap(pixmap)
