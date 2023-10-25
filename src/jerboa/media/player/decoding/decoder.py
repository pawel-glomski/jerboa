from collections.abc import Generator

import copy
import math
from threading import Thread, Lock, Condition
from dataclasses import dataclass

from jerboa.core.timeline import FragmentedTimeline, RangeMappingResult
from jerboa.media.core import (
    MediaType,
    AudioConfig,
    VideoConfig,
    AudioConstraints,
)

from .buffer import JbAudioFrame, JbVideoFrame, create_buffer
from . import pipeline

SEEK_THRESHOLD = 0.25  # in seconds

BUFFER_DURATION = 2.5  # in seconds


class TimelineDecoder:
    def __init__(
        self,
        decoding_node: pipeline.DecodingNode,
        output_constraints: AudioConstraints,
        init_timeline: FragmentedTimeline = None,
    ):
        self._skipping_decoder = skipping_decoder
        self._output_constraints = output_constraints

        self._output_media_config = create_output_media_config(
            skipping_decoder.stream_info,
            output_constraints,
        )
        self._intermediate_media_config = create_intermediate_media_config(
            self._output_media_config
        )

        self._mapper = create_mapper(self._intermediate_media_config)
        self._buffer = create_buffer(self._output_media_config, BUFFER_DURATION)

        self._timeline = FragmentedTimeline() if init_timeline is None else init_timeline

        self._seek_timepoint: None | float = skipping_decoder.stream_info.start_timepoint
        self._is_done = False

        self._mutex = Lock()
        self._seeking = Condition(self._mutex)
        self._buffer_not_empty_or_done = Condition(self._mutex)
        self._buffer_not_full_or_seeking = Condition(self._mutex)
        self._timeline_updated_or_seeking = Condition(self._mutex)

        self._dec_thread = Thread(
            target=self._decoding,
            name=(
                f"Decoding #{self._skipping_decoder.stream_info.stream_index} stream "
                f"({self._skipping_decoder.stream_info.media_type})"
            ),
            daemon=True,
        )
        self._dec_thread.start()

    def __del__(self):
        if hasattr(self, "_dec_thread") and self._dec_thread.is_alive():
            self.seek(STOP_DECODING_SEEK_TIMEPOINT)

    @property
    def dst_media_config(self) -> AudioConfig | VideoConfig:
        return self._output_media_config

    def update_timeline(self, updated_timeline: FragmentedTimeline):
        assert updated_timeline.time_scope > self._timeline.time_scope
        with self._mutex:
            self._timeline = copy.copy(updated_timeline)  # TODO: maybe improve updating
            self._timeline_updated_or_seeking.notify_all()

    def set_new_timeline(self, new_timeline: FragmentedTimeline, current_mapped_timepoint: float):
        with self._mutex:
            current_timepoint = self._timeline.unmap_timepoint_to_source(current_mapped_timepoint)
            new_timepoint = self._timeline.map_time_range(current_timepoint, current_timepoint)

            self._timeline = copy.copy(new_timeline)
            self._seek_without_lock(new_timepoint)

    def _seek_without_lock(self, seek_timepoint: float):
        self._seek_timepoint = self._timeline.unmap_timepoint_to_source(seek_timepoint)
        self._buffer.clear()

        self._seeking.notify()
        self._buffer_not_full_or_seeking.notify()
        self._timeline_updated_or_seeking.notify()

    def seek(self, seek_timepoint: float):
        with self._mutex:
            self._seek_without_lock(seek_timepoint)

    def apply_new_output_media_constraints(
        self,
        constraints: AudioConstraints,
        start_timepoint: float,
    ):
        with self._mutex:
            output_media_config = create_output_media_config(
                self._skipping_decoder.stream_info,
                constraints,
            )
            if self._output_media_config != output_media_config:
                self._output_media_config = output_media_config
                self._seek_without_lock(start_timepoint)

    def _decoding(self):
        # start decoding from start
        self._seek_timepoint = self._skipping_decoder.stream_info.start_timepoint
        while True:
            seek_timepoint = self._decoding__wait_for_seek()
            if seek_timepoint == STOP_DECODING_SEEK_TIMEPOINT:
                break
            self._decoding__loop(seek_timepoint)

    def _decoding__wait_for_seek(self) -> float:
        with self._mutex:
            self._seeking.wait_for(lambda: self._seek_timepoint is not None)
            self._is_done = False

            seek_timestamp = self._seek_timepoint
            self._seek_timepoint = None
            return seek_timestamp

    def _decoding__loop(self, seek_timepoint: float):
        self._mapper.reset()

        skip_timepoint = seek_timepoint
        skipping_decoder = self._skipping_decoder.decode(
            seek_timepoint, self._intermediate_media_config
        )
        for skipping_frame in skipping_decoder:
            mapping_scheme, skip_timepoint = self._decoding__try_getting_mapping_scheme(
                skipping_frame
            )
            skipping_decoder.send(skip_timepoint)

            if mapping_scheme is None or (
                not self._decoding__try_to_map_and_put_frame(skipping_frame, mapping_scheme)
                and self._decoding__try_to_skip_dropped_frames(skipping_frame, skip_timepoint)
            ):
                break  # begin seeking
        else:
            self._decoding__flush_mapper()

    def _decoding__put_frame(self, frame) -> None:
        with self._mutex:
            self._buffer_not_full_or_seeking.wait_for(
                lambda: not self._buffer.is_full() or self._seek_timepoint is not None
            )
            if self._seek_timepoint is not None:
                raise False  # TODO: raise a task

            self._buffer.put(frame)
            self._buffer_not_empty_or_done.notify()

    def _decoding__try_to_skip_dropped_frames(self) -> bool:
        if (
            context.min_timepoint - current_frame.end_timepoint
            >= self._skipping_decoder.seek_threshold
        ):
            with self._mutex:
                if self._seek_timepoint is None:  # must never overwrite the user's seek
                    self._seek_timepoint = skip_timepoint
            return True  # begin seeking
        return False

    def _decoding__flush_mapper(self) -> None:
        mapped_frame = self._mapper.map(None, None)
        with self._mutex:
            if self._seek_timepoint is None:
                if mapped_frame.is_valid():
                    self._buffer_not_full_or_seeking.wait_for(
                        lambda: not self._buffer.is_full() or self._seek_timepoint is not None
                    )
                    self._buffer.put(mapped_frame)
                self._is_done = True
                self._buffer_not_empty_or_done.notify()

    def is_done(self) -> bool:
        return self._is_done

    def pop(self, *args, timeout: float | None = None) -> JbAudioFrame | JbVideoFrame | None:
        frame = None
        with self._mutex:
            if self._buffer_not_empty_or_done.wait_for(
                lambda: not self._buffer.is_empty() or self.is_done(),
                timeout=timeout,
            ):
                if not self._buffer.is_empty():
                    frame = self._buffer.pop(*args)
                    self._buffer_not_full_or_seeking.notify()
            else:
                raise TimeoutError()
        return frame

    def get_next_timepoint(self) -> float | None:
        with self._mutex:
            self._buffer_not_empty_or_done.wait_for(
                lambda: not self._buffer.is_empty() or self.is_done()
            )
            if not self._buffer.is_empty():
                return self._buffer.get_next_timepoint()
            return None
