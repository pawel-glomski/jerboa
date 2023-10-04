import PySide6.QtWidgets as QtW
from PySide6 import QtCore, QtGui

from PySide6.QtCore import Qt

from jerboa.core.signal import Signal
from jerboa.media.core import VideoConfig
from jerboa.media.player.video_player import JbVideoFrame


class Canvas(QtW.QLabel):
    def __init__(self):
        super().__init__()

        self.setMinimumHeight(50)
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameShape(QtW.QFrame.Shape.StyledPanel)

        self._current_pixmap: QtGui.QPixmap | None = None

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        if self._current_pixmap is not None:
            self.setPixmap(
                self._current_pixmap.scaled(
                    self.size(),
                    aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                    mode=Qt.TransformationMode.SmoothTransformation,
                )
            )


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
        media_source_selected_signal: Signal,
        video_frame_update_signal: Signal,
    ):
        super().__init__()

        self._canvas = canvas
        self._timeline = timeline

        self._splitter = QtW.QSplitter()
        self._splitter.setOrientation(Qt.Orientation.Vertical)
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

        video_frame_update_signal.connect(self._on_frame_update)
        media_source_selected_signal.connect()

    def _add_widget_to_splitter(self, widget: QtW.QWidget, stretch_factor: int, collapsible: bool):
        idx = self._splitter.count()
        self._splitter.addWidget(widget)
        self._splitter.setStretchFactor(idx, stretch_factor)
        self._splitter.setCollapsible(idx, collapsible)

    def _on_frame_update(self, frame: JbVideoFrame, image_format: VideoConfig.PixelFormat) -> None:
        image = QtGui.QImage(
            frame.data.tobytes(),
            frame.data.shape[1],
            frame.data.shape[0],
            jb_to_qt_image_format[image_format],
        )
        self._current_pixmap = QtGui.QPixmap.fromImage(image)
        self.setPixmap(
            self._current_pixmap.scaled(
                self.size(),
                aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                mode=Qt.TransformationMode.SmoothTransformation,
            )
        )
        print("displayed")
