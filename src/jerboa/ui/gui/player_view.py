import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore
from PyQt5 import QtGui
# from PyQt5 import QtMultimedia as QtMedia
from PyQt5.QtCore import Qt

from jerboa.model import PlayerModel


class PlayerView(QtW.QWidget):

  def __init__(self, player_model: PlayerModel):
    super().__init__()
    self._splitter = PlayerView._create_splitter()
    self._canvas = PlayerView._add_canvas(self._splitter)
    self._timeline = PlayerView._add_timeline(self._splitter)

    layout = QtW.QVBoxLayout()
    layout.addWidget(self._splitter)
    layout.setContentsMargins(QtCore.QMargins())
    self.setLayout(layout)

  @staticmethod
  def _create_splitter() -> QtW.QSplitter:
    splitter = QtW.QSplitter()
    splitter.setOrientation(Qt.Vertical)
    splitter.setStyleSheet('''
      QSplitter::handle {
        border-top: 1px solid #413F42;
        margin: 3px 0px;
      }
      ''')
    return splitter

  @staticmethod
  def _add_canvas(splitter: QtW.QSplitter) -> QtW.QLabel:
    canvas = QtW.QLabel('canvas')
    canvas.setFrameShape(QtW.QFrame.Shape.StyledPanel)
    canvas.setMinimumHeight(50)
    canvas.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    idx = splitter.count()
    splitter.addWidget(canvas)
    splitter.setStretchFactor(idx, 3)
    splitter.setCollapsible(idx, False)
    return canvas

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
