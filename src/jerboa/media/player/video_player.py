from dataclasses import dataclass

from jerboa.core.logger import logger
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


class DeinitializeTask(Task):
    ...


@dataclass(frozen=True)
class SeekTask(Task):
    timepoint: float


class VideoPlayer:
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

        self._tasks = TaskQueue()
        self._mutex = self._tasks.mutex

        self._state = PlayerState.UNINITIALIZED

        self._timer: PlaybackTimer | None = None

    def __del__(self):
        self.deinitialize(wait=True)

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

    def deinitialize(self) -> Task.Future:
        with self._mutex:
            return self._deinitialize__locked()

    def _deinitialize__locked(self) -> Task.Future:
        assert self._mutex.locked()

        deinit_task = DeinitializeTask()
        if self.state != PlayerState.UNINITIALIZED:
            self._tasks.clear__locked()
            self._tasks.add_task__locked(deinit_task)
        else:
            deinit_task.complete()
        return deinit_task.future

    def initialize(self, decoder: Decoder, timer: PlaybackTimer) -> Task.Future:
        assert decoder.media_type == MediaType.VIDEO

        def _initialize():
            with self._mutex:
                assert self._state == PlayerState.UNINITIALIZED
                self._deinitialize__locked().wait_done(timeout=THREAD_RESPONSE_TIMEOUT)

                self._tasks.clear__locked()
                self._timer = timer
                self._decoder = decoder

                self.__player_job__set_state__locked(PlayerState.SUSPENDED)

        task = FnTask(_initialize)
        self._thread_spawner.start(self.__player_job, task)
        return task.future

    def __player_job(self, init_task: Task) -> None:
        logger.debug("VideoPlayer: Starting the job")
        init_task.run()
        try:
            self.__player_job__playback_loop()
        except Exception as exc:
            try:
                self._decoder.kill()
                self._decoder = None
            finally:
                self.__player_job__set_state(PlayerState.UNINITIALIZED)

                if isinstance(exc, DeinitializeTask):
                    task: DeinitializeTask = exc
                    task.complete()
                    logger.debug("VideoPlayer: Stopped by a task")
                else:
                    logger.error("VideoPlayer: Stopped by an error")
                    self._fatal_error_signal.emit()
                    raise exc

    def __player_job__playback_loop(self) -> None:
        frame: JbVideoFrame | None = None

        self.__player_job__emit_first_frame()
        while True:
            try:
                if self._tasks.run_all(wait_when_empty=(self.state == PlayerState.SUSPENDED)) > 0:
                    continue

                if frame is None:
                    frame = self.__player_job__get_frame()

                if frame is not None and self.__player_job__sync_with_timer(frame):
                    self._video_frame_update_signal.emit(frame=frame)
                    frame = None

            except SeekTask as seek_task:
                logger.debug(f"VideoPlayer: Seeking to {seek_task.timepoint}")

                seek_task.complete_after(self.__player_job__seek, seek_task.timepoint)

                self.__player_job__emit_first_frame()
                frame = None

    def __player_job__seek(self, timepoint: float) -> None:
        self._decoder.seek(timepoint).wait_done(
            timeout=THREAD_RESPONSE_TIMEOUT  # TODO: better timeout
        )
        self._decoder.prefill(timeout=1.0).wait_done()

    def __player_job__emit_first_frame(self) -> None:
        self.video_frame_update_signal.emit(frame=self.__player_job__get_frame())

    def __player_job__get_frame(self) -> JbVideoFrame | None:
        try:
            frame = self._decoder.pop(timeout=0)
            logger.info(frame)
            if frame is None:
                logger.debug("VideoPlayer: Suspended by EOF")
                self.__player_job__set_state(PlayerState.SUSPENDED)
                self._eof_signal.emit()
            return frame
        except TimeoutError:
            logger.warning("VideoPlayer: Suspended by buffer underrun")
            self.__player_job__set_state(PlayerState.SUSPENDED)
            self._buffer_underrun_signal.emit()
        return None

    def __player_job__sync_with_timer(self, frame: JbVideoFrame) -> bool:
        sleep_threshold = min(SLEEP_THRESHOLD_MAX, frame.duration * SLEEP_THRESHOLD_RATIO)
        with self._mutex:
            current_timepoint = self._timer.current_timepoint()
            if current_timepoint is None:
                return False

            sleep_time = frame.beg_timepoint - current_timepoint
            if sleep_time > sleep_threshold:
                # wait for the timer to catch up
                if self._tasks.task_added.wait(timeout=min(SLEEP_TIME_MAX, sleep_time)):
                    current_timepoint = self._timer.current_timepoint()
                    if current_timepoint is None:
                        return False

                    sleep_time = frame.beg_timepoint - current_timepoint

        if sleep_time <= sleep_threshold:
            return True
        return False

    def __player_job__set_state(self, state: PlayerState) -> None:
        with self._mutex:
            self.__player_job__set_state__locked(state)

    def __player_job__set_state__locked(self, state: PlayerState) -> None:
        assert self._mutex.locked()

        self._state = state

    def suspend(self) -> Task.Future:
        task = FnTask(self.__player_job__set_state, state=PlayerState.SUSPENDED)
        with self._mutex:
            if self.state != PlayerState.UNINITIALIZED:
                self._tasks.add_task__locked(task)
            else:
                task.cancel()
        return task.future

    def resume(self) -> Task.Future:
        task = FnTask(self.__player_job__set_state, state=PlayerState.PLAYING)
        with self._mutex:
            if self.state != PlayerState.UNINITIALIZED:
                self._tasks.add_task__locked(task)
            else:
                task.cancel()
        return task.future

    def seek(self, source_timepoint: float) -> Task.Future:
        assert source_timepoint >= 0

        task = SeekTask(timepoint=source_timepoint)
        with self._mutex:
            if self.state != PlayerState.UNINITIALIZED:
                self._tasks.add_task__locked(task)
            else:
                task.cancel()
        return task.future
