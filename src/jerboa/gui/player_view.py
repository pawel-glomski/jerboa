from PySide6 import (
    QtWidgets as QtW,
    QtCore as QtC,
    QtGui as QtG,
    QtMultimedia as QtM,
    QtMultimediaWidgets as QtMW,
)
from PySide6.QtCore import Qt

from jerboa.core.signal import Signal
from jerboa.media.core import VideoConfig, VIDEO_FRAME_PIXEL_FORMAT
from jerboa.media.player.video_player import JbVideoFrame


def jb_to_qt_video_frame_pixel_format(
    pixel_format_jb: VideoConfig.PixelFormat,
) -> QtM.QVideoFrameFormat.PixelFormat:
    match pixel_format_jb:
        case VideoConfig.PixelFormat.RGBA8888:
            return QtM.QVideoFrameFormat.PixelFormat.Format_RGBA8888
        case _:
            raise ValueError(f"Unrecognized pixel format: {pixel_format_jb}")


class FrameMappingContext:
    def __init__(self, frame: QtM.QVideoFrame, mode: QtM.QVideoFrame.MapMode) -> None:
        self._frame = frame
        self._mode = mode

    def __enter__(self) -> "FrameMappingContext":
        self._frame.map(self._mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._frame.unmap()


class Canvas(QtW.QStackedWidget):
    def __init__(self, video_frame_update_signal: Signal, no_video_text: str):
        super().__init__()

        self.setMinimumHeight(50)
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

        self._frame_canvas = QtMW.QVideoWidget()
        self._frame_format = QtM.QVideoFrameFormat(
            QtC.QSize(0, 0),
            jb_to_qt_video_frame_pixel_format(VIDEO_FRAME_PIXEL_FORMAT),
        )

        self._no_video_label = QtW.QLabel(no_video_text)
        self._no_video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # self._no_video_label.setFrameShape(QtW.QFrame.Shape.StyledPanel)

        self.addWidget(self._frame_canvas)
        self.addWidget(self._no_video_label)
        self.setCurrentWidget(self._no_video_label)

        video_frame_update_signal.connect(self._on_frame_update)

    def _on_frame_update(self, frame: JbVideoFrame) -> None:
        if frame is not None:
            self._assure_correct_frame_size(frame.width, frame.height)

            frame_qt = self._new_frame()
            with FrameMappingContext(frame_qt, QtM.QVideoFrame.MapMode.ReadWrite):
                for plane_idx in range(frame_qt.planeCount()):
                    frame_qt.bits(plane_idx)[:] = frame.planes[plane_idx]

            self._frame_canvas.videoSink().setVideoFrame(frame_qt)
            self.setCurrentWidget(self._frame_canvas)
        else:
            self.setCurrentWidget(self._no_video_label)

    def _assure_correct_frame_size(self, width: int, height: int) -> None:
        if width != self._frame_format.frameWidth() or height != self._frame_format.frameHeight():
            self._frame_format.setFrameSize(QtC.QSize(width, height))
            self._frames = [
                QtM.QVideoFrame(self._frame_format),
                QtM.QVideoFrame(self._frame_format),
            ]
            self._frame_idx = 0

    def _new_frame(self) -> QtM.QVideoFrame:
        self._frame_idx = (self._frame_idx + 1) % 2
        return self._frames[self._frame_idx]


class Timeline(QtW.QLabel):
    def __init__(self):
        super().__init__()

        self.setText("timeline")
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)
        # self.setFrameShape(QtW.QFrame.Shape.StyledPanel)
        self.setMinimumHeight(50)


class PlayerView(QtW.QWidget):
    def __init__(
        self,
        canvas: Canvas,
        timeline: Timeline,
        playback_toggle_signal: Signal,
        seek_forward_signal: Signal,
        seek_backward_signal: Signal,
    ):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._canvas = canvas
        self._timeline = timeline
        self._playback_toggle_signal = playback_toggle_signal
        self._seek_backward_signal = seek_backward_signal
        self._seek_forward_signal = seek_forward_signal

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

        self._add_widget_to_splitter(canvas, stretch_factor=10, collapsible=False)
        self._add_widget_to_splitter(timeline, stretch_factor=1, collapsible=True)

        layout = QtW.QVBoxLayout()
        layout.addWidget(self._splitter)
        layout.setContentsMargins(QtC.QMargins())
        self.setLayout(layout)

    def _add_widget_to_splitter(self, widget: QtW.QWidget, stretch_factor: int, collapsible: bool):
        idx = self._splitter.count()
        self._splitter.addWidget(widget)
        self._splitter.setStretchFactor(idx, stretch_factor)
        self._splitter.setCollapsible(idx, collapsible)

    def keyPressEvent(self, event: QtG.QKeyEvent):
        super().keyPressEvent(event)
        if event.key() == Qt.Key.Key_Space:
            self._playback_toggle_signal.emit()
        if event.key() == Qt.Key.Key_Left:
            self._seek_backward_signal.emit()
        if event.key() == Qt.Key.Key_Right:
            self._seek_forward_signal.emit()
        else:
            super().keyPressEvent(event)
