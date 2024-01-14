# Jerboa - AI-powered media player
# Copyright (C) 2023 Paweł Głomski

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


from dataclasses import dataclass
from threading import Lock

from jerboa.log import logger
from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadSpawner, TaskQueue, Task, FnTask
from jerboa.media.core import MediaType
from .decoding.decoder import Decoder
from .decoding.frame import JbVideoFrame
from .state import PlayerState
from .timer import PlaybackTimer


THREAD_RESPONSE_TIMEOUT = 0.1
SLEEP_THRESHOLD_RATIO = 1 / 3  # how much earlier can we display the frame (ratio of frame duration)
SLEEP_THRESHOLD_MAX = 1 / 24 * SLEEP_THRESHOLD_RATIO  # but we cannot display it earlier than this
SLEEP_TIME_MAX = 0.25

TIMER_STARTUP_WAIT_TIME = 1 / 120
TIMER_SYNC_RETRIES_MAX = 32


class VideoPlayer:
    class UninitializeTask(Task):
        ...

    @dataclass(frozen=True)
    class SeekTask(Task):
        timepoint: float

    def __init__(
        self,
        thread_spawner: ThreadSpawner,
        fatal_error_signal: Signal,
        buffer_underrun_signal: Signal,
        eof_signal: Signal,
        video_frame_update_signal: Signal,
    ):
        self._decoder: Decoder | None = None

        self._thread_spawner = thread_spawner

        self._fatal_error_signal = fatal_error_signal
        self._buffer_underrun_signal = buffer_underrun_signal
        self._eof_signal = eof_signal
        self._video_frame_update_signal = video_frame_update_signal

        self._mutex = Lock()
        self._tasks = TaskQueue()

        self._state = PlayerState.UNINITIALIZED

        self._timer: PlaybackTimer | None = None

    def __del__(self):
        self.uninitialize()

    @property
    def fatal_error_signal(self) -> Signal:
        return self._fatal_error_signal

    @property
    def buffer_underrun_signal(self) -> Signal:
        return self._buffer_underrun_signal

    @property
    def eof_signal(self) -> Signal:
        return self._eof_signal

    @property
    def video_frame_update_signal(self) -> Signal:
        return self._video_frame_update_signal

    @property
    def state(self) -> PlayerState:
        return self._state

    @property
    def is_initialized(self) -> bool:
        return self._state != PlayerState.UNINITIALIZED

    @property
    def reached_eof(self) -> bool:
        return (
            self._state != PlayerState.UNINITIALIZED
            and self._decoder.is_done
            and self._decoder.buffered_duration <= 0
        )

    def uninitialize(self) -> Task.Future:
        with self._mutex:
            return self._uninitialize__locked()

    def _uninitialize__locked(self) -> Task.Future:
        assert self._mutex.locked()

        uninit_task = VideoPlayer.UninitializeTask()
        if self.state == PlayerState.UNINITIALIZED:
            logger.debug("Player is already uninitialized")
            uninit_task.finish_without_running()
        else:
            self._tasks.clear(abort_current_task=True)
            self._tasks.add_task(uninit_task)
        return uninit_task.future

    def initialize(self, decoder: Decoder, timer: PlaybackTimer) -> Task.Future:
        assert decoder.media_type == MediaType.VIDEO

        def _initialize(executor: Task.Executor):
            logger.debug("Initializing...")
            with self._mutex:
                assert self._state == PlayerState.UNINITIALIZED

                with executor.finish_context:
                    self._timer = timer
                    self._decoder = decoder
                    self.__thread__set_state__locked(PlayerState.SUSPENDED)
                    logger.debug("Initializing... Successful")

        task = FnTask(_initialize)
        self._thread_spawner.start(self.__thread, task)
        return task.future

    def __thread(self, init_task: Task) -> None:
        init_task.run_pending()
        if self.state == PlayerState.UNINITIALIZED:
            logger.error("Initializing... Failed")
            return

        try:
            self.__thread__playback_loop()
        except VideoPlayer.UninitializeTask as uninit_task:
            uninit_task.execute_and_finish(self.__thread__uninitialize, crashed=False)
        except:
            logger.error("Crashed by an error")
            self.__thread__uninitialize(crashed=True)
            raise

    def __thread__uninitialize(self, *, crashed: bool) -> None:
        logger.debug("Uninitializing...")
        with self._mutex:
            self._tasks.clear(abort_current_task=crashed)
            self._decoder.kill()
            self._decoder = None
            self.__thread__set_state__locked(PlayerState.UNINITIALIZED)
            logger.debug("Uninitializing... Successful")

    def __thread__playback_loop(self) -> None:
        frame: JbVideoFrame | None = None
        sync_retries = 0

        self.__thread__emit_first_frame()
        while True:
            try:
                self._tasks.run_all(None if self.state == PlayerState.SUSPENDED else 0)
                if self.state == PlayerState.SUSPENDED:
                    continue

                if frame is None:
                    frame = self.__thread__get_frame()
                    sync_retries = 0
                else:
                    sync_retries += 1

                if frame is not None and self.__thread__sync_with_timer(frame):
                    self._video_frame_update_signal.emit(frame=frame)
                    frame = None
                elif sync_retries >= TIMER_SYNC_RETRIES_MAX:
                    logger.error(
                        "The timer is not progressing... This player will be "
                        "suspended and a 'Buffer Underrun' signal will be emitted..."
                    )
                    sync_retries = 0
                    self.__thread__set_state(PlayerState.SUSPENDED)
                    self.buffer_underrun_signal.emit()

            except VideoPlayer.SeekTask as seek_task:
                if seek_task.execute(
                    lambda executor: self.__thread__seek(executor, seek_task.timepoint)
                ):
                    frame = None

    def __thread__seek(self, executor: Task.Executor, timepoint: float) -> None:
        logger.debug("Seeking...")

        seek_future = self._decoder.seek(timepoint)
        executor.abort_aware_wait_for_future(seek_future)
        if seek_future.stage != Task.Stage.FINISHED_CLEAN:
            logger.error("Seeking... Failed (Decoder seek error)")
            executor.abort()

        prefill_future = self._decoder.prefill()
        executor.abort_aware_wait_for_future(prefill_future)
        if prefill_future.stage != Task.Stage.FINISHED_CLEAN:
            if self._decoder.is_done and self._decoder.buffered_duration <= 0:
                logger.info("Seeking... Failed (EOF)")
                self._state = PlayerState.SUSPENDED
                self.eof_signal.emit()
            else:
                logger.error("Seeking... Failed (Decoder prefill error)")
            executor.abort()

        with executor.finish_context:
            self.__thread__emit_first_frame()

    def __thread__emit_first_frame(self) -> None:
        self.video_frame_update_signal.emit(frame=self.__thread__get_frame())

    def __thread__get_frame(self) -> JbVideoFrame | None:
        try:
            frame = self._decoder.pop(timeout=0)
            if frame is None:
                logger.debug("Suspended by EOF")
                self.__thread__set_state(PlayerState.SUSPENDED)
                self.eof_signal.emit()
            return frame
        except TimeoutError:
            logger.warning("Suspended by buffer underrun")
            self.__thread__set_state(PlayerState.SUSPENDED)
            self.buffer_underrun_signal.emit()
        return None

    def __thread__sync_with_timer(self, frame: JbVideoFrame) -> bool:
        sleep_threshold = min(SLEEP_THRESHOLD_MAX, frame.duration * SLEEP_THRESHOLD_RATIO)

        current_timepoint = self._timer.current_timepoint()
        if current_timepoint is None:
            self._tasks.create_task_added_event().wait(timeout=TIMER_STARTUP_WAIT_TIME)
            return False

        sleep_time = frame.beg_timepoint - current_timepoint
        if sleep_time > sleep_threshold:
            # wait for the timer to catch up
            self._tasks.create_task_added_event().wait(timeout=min(SLEEP_TIME_MAX, sleep_time))

            current_timepoint = self._timer.current_timepoint()
            if current_timepoint is None:
                return False

            sleep_time = frame.beg_timepoint - current_timepoint

        if sleep_time <= sleep_threshold:
            return True
        return False

    def __thread__set_state(self, state: PlayerState) -> None:
        with self._mutex:
            self.__thread__set_state__locked(state)

    def __thread__set_state__locked(self, state: PlayerState) -> None:
        assert self._mutex.locked()

        if state != self._state:
            logger.debug(f"Changing the state ({self.state} -> {state})")
            self._state = state
        else:
            logger.debug(f"Player already has state '{state}'")

    def suspend(self) -> Task.Future:
        return self._add_task(
            FnTask(
                lambda executor: executor.finish_with(
                    self.__thread__set_state, PlayerState.SUSPENDED
                )
            )
        )

    def resume(self) -> Task.Future:
        return self._add_task(
            FnTask(
                lambda executor: executor.finish_with(self.__thread__set_state, PlayerState.PLAYING)
            )
        )

    def seek(self, source_timepoint: float) -> Task.Future:
        assert source_timepoint >= 0

        return self._add_task(VideoPlayer.SeekTask(timepoint=source_timepoint))

    def _add_task(self, task: Task) -> Task.Future:
        with self._mutex:
            if self.state == PlayerState.UNINITIALIZED:
                logger.debug("Player is uninitialized, aborting a task", details=task)
                task.future.abort()
            else:
                self._tasks.add_task(task)
        return task.future
