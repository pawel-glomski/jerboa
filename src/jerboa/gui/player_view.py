import PyQt5.QtWidgets as QtW
from PyQt5 import QtCore, QtGui

# from PyQt5 import QtMultimedia as QtMedia
from PyQt5.QtCore import Qt


class Canvas(QtW.QLabel):
    def __init__(self):
        super().__init__()

        self.setText("canvas")
        self.setFrameShape(QtW.QFrame.Shape.StyledPanel)
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(50)


class Timeline(QtW.QLabel):
    def __init__(self):
        super().__init__()

        self.setText("timeline")
        self.setFrameShape(QtW.QFrame.Shape.StyledPanel)
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(50)


class PlayerView(QtW.QWidget):
    def __init__(
        self,
        canvas: Canvas,
        timeline: Timeline,
    ):
        super().__init__()

        self._canvas = canvas
        self._timeline = timeline

        self._splitter = QtW.QSplitter()
        self._splitter.setOrientation(Qt.Vertical)
        self._splitter.setStyleSheet(
            """
      QSplitter::handle {
        border-top: 1px solid #413F42;
        margin: 3px 0px;
      }
      """
        )

        self._add_widget_to_splitter(canvas, stretch_factor=3, collapsible=False)
        self._add_widget_to_splitter(timeline, stretch_factor=1, collapsible=True)

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._splitter)
        layout.setContentsMargins(QtCore.QMargins())
        self.setLayout(layout)

    def _add_widget_to_splitter(self, widget: QtW.QWidget, stretch_factor: int, collapsible: bool):
        idx = self._splitter.count()
        self._splitter.addWidget(widget)
        self._splitter.setStretchFactor(idx, stretch_factor)
        self._splitter.setCollapsible(idx, collapsible)

    def set_canvas_pixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._canvas.setPixmap(pixmap)
