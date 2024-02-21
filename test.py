# %%
import sys
import random
import math

import PySide6.QtCore as QtC
import PySide6.QtWidgets as QtW
import PySide6.QtGui as QtG
from PySide6.QtCore import Qt

import jerboa.core.timeline as tl


def time_to_str(timepoint: float, seconds_decimals: int) -> str:
    text = "-" if timepoint < 0 else ""
    timepoint = abs(timepoint)

    hours = int(timepoint // 3600)
    minutes = int(timepoint % 3600) // 60
    seconds = timepoint % 60

    if hours:
        text += f"{hours}:{minutes:02d}:"
    elif minutes:
        text += f"{minutes}:"

    if (hours or minutes) and seconds < 10:
        text += f"0{seconds:.{seconds_decimals+1}g}"
    else:
        text += f"{seconds:.{seconds_decimals+2}g}"

    return text


class PlayHead(QtW.QWidget):
    def __init__(self, parent: QtW.QWidget):
        super().__init__(parent)
        self.setSizePolicy(QtW.QSizePolicy.Policy.Fixed, QtW.QSizePolicy.Policy.Fixed)
        self.setFixedSize(8, 8)

    def paintEvent(self, event: QtG.QPaintEvent) -> None:
        super().paintEvent(event)

        with QtG.QPainter(self) as painter:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QtG.QColor(51, 102, 255))

            painter.drawConvexPolygon(
                [
                    QtC.QPointF(0, 0),
                    QtC.QPointF(self.width(), 0),
                    QtC.QPointF(self.width(), 5),
                    QtC.QPointF(self.width() / 2, 8),
                    QtC.QPointF(0, 5),
                ]
            )

            painter.setPen(QtG.QColor(102, 153, 255))
            painter.drawLine(self.width() / 2, 8, self.width() / 2, self.height())


class TimeRuler(QtW.QWidget):
    def __init__(self):
        super().__init__()
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Minimum)
        self.setMinimumSize(240, 16)

        self._beg_timepoint = 0
        self._end_timepoint = 1

        self._zero_point_offset_in_pixels = 0

    def set_time_range(self, beg_timepoint: float, end_timepoint: float) -> None:
        self._beg_timepoint = beg_timepoint
        self._end_timepoint = end_timepoint

    def set_zero_point_offset(self, offset: float):
        self._zero_point_offset_in_pixels = offset

    def sizeHint(self) -> QtC.QSize:
        font_metrics = QtG.QFontMetricsF(QtG.QFont())

        return QtC.QSize(640, font_metrics.height() + 5 + 2)

    def paintEvent(self, event: QtG.QPaintEvent) -> None:
        super().paintEvent(event)

        width = self.width()
        height = self.height() - 1

        time_span = self._end_timepoint - self._beg_timepoint
        pixels_per_second = (width - self._zero_point_offset_in_pixels) / time_span
        seconds_per_pixel = 1 / pixels_per_second

        with QtG.QPainter(self) as painter:
            painter.drawLine(0, height, width, height)

            font = painter.font()
            font.setPointSizeF(font.pointSizeF() - 2)
            painter.setFont(font)
            font_metrics = QtG.QFontMetricsF(font)

            seconds_decimals = 4 if time_span < 1 else (2 if time_span < 120 else 0)
            target_step_in_pixels = 1.75 * int(
                font_metrics.horizontalAdvance(
                    time_to_str(
                        999 * 3600,  # we expect at most 999 hours
                        seconds_decimals=seconds_decimals,
                    )
                )
            )
            if target_step_in_pixels > 56:
                ...
            target_step_in_seconds = target_step_in_pixels * seconds_per_pixel

            step_in_seconds = 2 ** math.ceil(math.log(target_step_in_seconds, 2))

            start_timepoint = (
                self._beg_timepoint - self._zero_point_offset_in_pixels * seconds_per_pixel
            )
            start_timepoint_in_pixels = start_timepoint * pixels_per_second

            timepoint = math.floor(start_timepoint / step_in_seconds) * step_in_seconds
            while timepoint < self._end_timepoint:
                timepoint += step_in_seconds

                timepoint_text = time_to_str(timepoint, seconds_decimals)
                view_x = timepoint * pixels_per_second - start_timepoint_in_pixels

                painter.drawLine(view_x, height - 5, view_x, height)
                painter.drawText(
                    view_x - font_metrics.horizontalAdvance(str(timepoint_text)) / 2,
                    height - 5 - 2,
                    str(timepoint_text),
                )


class AnalysisRunTimeline(QtW.QWidget):
    def __init__(self):
        super().__init__()
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Minimum)
        self.setMinimumSize(240, 40)

        self._view_rect = QtC.QRectF(0, 0, 1, 0)
        self._timeline = [tl.FragmentedTimeline() for _ in range(4)]
        self._timeline[0].extend_time_scope(0)
        for _ in range(int(1e4)):
            beg = self._timeline[0].time_scope
            width = 0.1 + random.random() * 5
            modifier = random.random()
            self._timeline[0].append_section(tl.TMSection(beg, beg + width, modifier))

        segment_duration = 2
        for timeline, timeline_zoom in zip(self._timeline[:-1], self._timeline[1:]):
            segment_duration *= 6
            for segment_idx in range(int(timeline.time_scope / segment_duration)):
                beg = segment_idx * segment_duration
                end = beg + segment_duration

                assert (
                    mapping_result := timeline.map_time_range(beg, min(end, timeline.time_scope))[0]
                )

                modifier = (mapping_result.end - mapping_result.beg) / segment_duration

                import numpy as np

                durations = np.fromiter((s.end - s.beg for s in mapping_result.sections), float)
                durations_mod = np.fromiter((s.duration for s in mapping_result.sections), float)
                idx = durations >= np.percentile(durations, 0.75)

                modifier = durations_mod[idx].sum() / durations[idx].sum()

                # modifier = int((mapping_result.end - mapping_result.beg) / segment_duration >= 0.5)
                # majority_duration = 0
                # majority_duration_mapped = 0
                # for section in mapping_result.sections:
                #     if math.isclose(section.modifier, modifier, abs_tol=0.5):
                #         majority_duration += section.end - section.beg
                #         majority_duration_mapped += section.duration
                # modifier = majority_duration_mapped / majority_duration

                timeline_zoom.append_section(tl.TMSection(beg, end, modifier))

    @property
    def _scope(self) -> float:
        return self._timeline[0].time_scope

    def set_view_rect(self, view_rect: QtC.QRectF) -> None:
        self._view_rect = view_rect

    def sizeHint(self) -> QtC.QSize:
        return QtC.QSize(10000, 25)

    # def minimumSizeHint(self) -> QtC.QSize:
    #     return QtC.QSize(640, 25)

    def paintEvent(self, event: QtG.QPaintEvent) -> None:
        super().paintEvent(event)

        vrect = self._view_rect

        lod = 0
        for lod in range(len(self._timeline)):
            timeline = self._timeline[lod]
            view_sections = timeline.get_sections(vrect.left(), vrect.right())[0]
            if len(view_sections) < 256:
                break

        with QtG.QPainter(self) as painter:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setRenderHint(QtG.QPainter.RenderHint.Antialiasing)

            to_pixels = self.width() / vrect.width()
            for section in view_sections:
                view_overlap = section.overlap(vrect.left(), vrect.right())
                section_pixels = (view_overlap.end - view_overlap.beg) * to_pixels

                painter.setBrush(
                    QtG.QColor(
                        255 * (1 - section.modifier) + section.modifier * 0,
                        0 * (1 - section.modifier) + section.modifier * 255,
                        0 * (1 - section.modifier) + section.modifier * 0,
                    )
                )
                painter.drawRect(
                    QtC.QRectF(
                        (view_overlap.beg - vrect.left()) * to_pixels,
                        0,
                        section_pixels,
                        self.height(),
                    )
                )

    # def set_view_rect(self, rect: QtC.QRectF) -> None:
    #     rect = self._constrain_view_rect(rect)
    #     if rect == self._view_rect:
    #         return

    #     lod = 0
    #     for lod in range(len(self._timeline)):
    #         timeline = self._timeline[lod]
    #         new_view_sections = timeline.get_sections(rect.left(), rect.right())[0]
    #         if len(new_view_sections) < 4096:
    #             break
    #     # print(rect.width(), len(new_view_sections))

    #     if rect.intersects(self._view_rect) and lod == self._current_lod:
    #         new_view_sections_set = set(new_view_sections)

    #         new_sections = new_view_sections_set - self._section_to_item.keys()
    #         extra_sections = self._section_to_item.keys() - new_view_sections_set

    #         self._add_sections(new_sections)
    #         self._remove_sections(extra_sections)

    #     else:
    #         self._current_lod = lod
    #         self._view_sections.clear()
    #         self._add_sections(new_view_sections)

    #     self._view_rect = rect

    # def _add_sections(self, sections: list[tl.TMSection]) -> None:
    #     for section in sections:
    #         self._view_sections.add(section)
    #     self.update()

    # def _remove_sections(self, sections: list[tl.TMSection]) -> None:
    #     self._view_sections -= sections

    def resizeEvent(self, event: QtG.QResizeEvent) -> None:
        super().resizeEvent(event)


class AnalysisRunHeader(QtW.QWidget):
    def __init__(self, run_id: int) -> None:
        super().__init__()
        layout = QtW.QVBoxLayout(self)
        layout.addWidget(QtW.QLabel(f"Run #{run_id}"))


class TimelineWidget(QtW.QFrame):
    def __init__(self):
        super().__init__()
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Minimum)

        self._layout = QtW.QGridLayout()
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._time_ruler = TimeRuler()
        self._play_head = PlayHead(self)

        self._layout.addWidget(self._time_ruler, 0, 0, 1, 2, Qt.AlignmentFlag.AlignTop)

        self._playback_timeline = AnalysisRunTimeline()
        self._layout.addWidget(QtW.QLabel("Playback"), 1, 0, Qt.AlignmentFlag.AlignTop)
        self._layout.addWidget(self._playback_timeline, 1, 1, Qt.AlignmentFlag.AlignTop)

        self._runs = list[tuple[AnalysisRunHeader, AnalysisRunTimeline]]()
        self._view_rect = QtC.QRectF(0, 0, 10, 0)

        self.add_analysis_run(0)
        self.setLayout(self._layout)

    @property
    def _scope(self) -> float:
        return max(0, *[tl._scope for _, tl in self._runs])

    def add_analysis_run(self, run_id: int) -> None:
        run_header = AnalysisRunHeader(run_id)
        run_timeline = AnalysisRunTimeline()

        row = self._layout.rowCount()
        self._layout.addWidget(
            run_header, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._layout.addWidget(run_timeline, row, 1, Qt.AlignmentFlag.AlignTop)
        self._runs.append((run_header, run_timeline))

    def resizeEvent(self, event: QtG.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._time_ruler.set_zero_point_offset(
            self._playback_timeline.pos().x() - self._time_ruler.pos().x()
        )
        self._play_head.setFixedHeight(self.height() - self.contentsMargins().bottom())
        self._play_head.move(
            self._playback_timeline.pos().x() - self._time_ruler.pos().x(),
            self._time_ruler.geometry().bottom() - 8,
        )

    def wheelEvent(self, event: QtG.QWheelEvent) -> None:
        modifiers = QtW.QApplication.keyboardModifiers()
        if event.angleDelta().y() == 0 or not (
            modifiers & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)
        ):
            return super().wheelEvent(event)

        direction = -1 if event.angleDelta().y() > 0 else 1  # -1 = left; 1 = right
        vrect = QtC.QRectF(self._view_rect)

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            vrect.translate(0.01 * vrect.width() * direction, 0)
        elif modifiers & Qt.KeyboardModifier.ControlModifier:
            tl_w = self._playback_timeline

            zoom_point = (
                vrect.left()
                + tl_w.mapFromGlobal(QtG.QCursor.pos()).x() / tl_w.width() * vrect.width()
            )
            zoom_point_ratio = (zoom_point - vrect.left()) / vrect.width()

            new_width = max(
                0.1,
                vrect.width() * (1 + 0.1 * (1 if event.angleDelta().y() < 0 else -1)),
            )

            vrect.setLeft(zoom_point - zoom_point_ratio * new_width)
            vrect.setWidth(new_width)

        self._set_view_rect(vrect)

    def _constrain_view_rect(self, rect: QtC.QRectF) -> QtC.QRectF:
        # first try moving the timeline to the scope
        rect.translate(max(-rect.left(), 0) - max(rect.right() - self._scope, 0), 0)

        rect.setWidth(max(0.1, rect.width()))
        rect.setLeft(max(0, rect.left()))
        rect.setRight(min(self._scope, rect.right()))

        return rect

    def _set_view_rect(self, rect: QtC.QRectF) -> None:
        rect = self._constrain_view_rect(rect)
        if rect != self._view_rect:
            self._view_rect = rect
            for _, timeline in self._runs:
                timeline.set_view_rect(rect)
            self.update()
            self._playback_timeline.set_view_rect(rect)
            self._time_ruler.set_time_range(rect.left(), rect.right())


if __name__ == "__main__":
    app = QtW.QApplication(sys.argv)

    canvas_widget = QtW.QLabel("canvas")
    canvas_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    canvas_widget.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)
    # canvas_widget.setFrameStyle(1)

    timeline_widget = TimelineWidget()
    timeline_widget.add_analysis_run(1)

    test_widget_scroll = QtW.QScrollArea()
    test_widget_scroll.setSizePolicy(
        QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding
    )
    test_widget_scroll.setWidget(timeline_widget)
    test_widget_scroll.setWidgetResizable(True)

    central_widget = QtW.QSplitter(Qt.Orientation.Vertical)
    central_widget.addWidget(canvas_widget)
    central_widget.setStretchFactor(0, 1)
    central_widget.addWidget(test_widget_scroll)
    central_widget.setStretchFactor(1, 1)

    main_window = QtW.QMainWindow()
    main_window.setMinimumSize(640, 360)
    main_window.setCentralWidget(central_widget)
    main_window.show()

    sys.exit(app.exec())
