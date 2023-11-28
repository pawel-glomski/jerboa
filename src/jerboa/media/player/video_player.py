from dataclasses import dataclass
from threading import Lock

from jerboa.core.logger import logger
from jerboa.core.signal import Signal
from jerboa.core.multithreading import (
    ThreadSpawner,
    TaskQueue,
    Task,
    FnTask,
    Future,
    MultiCondition,
)
from jerboa.media.core import MediaType
from .decoding.decoder import Decoder
from .decoding.frame import JbVideoFrame
from .state import PlayerState
from .timer import PlaybackTimer


THREAD_RESPONSE_TIMEOUT = 0.1
SLEEP_THRESHOLD_RATIO = 1 / 3  # how much earlier can we display the frame (ratio of frame duration)
SLEEP_THRESHOLD_MAX = 1 / 24 * SLEEP_THRESHOLD_RATIO  # but we cannot display it earlier than this
SLEEP_TIME_MAX = 0.25
FRAME_RETRIES_MAX = 128  # at the start of playback usually ~32, but let's be safe with 128


class VideoPlayer:
    class DeinitializeTask(Task):
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

    @property
    def is_initialized(self) -> bool:
        return self._state != PlayerState.UNINITIALIZED

    def deinitialize(self) -> Future:
        with self._mutex:
            return self._deinitialize__locked()

    def _deinitialize__locked(self) -> Future:
        assert self._mutex.locked()

        deinit_task = VideoPlayer.DeinitializeTask()
        if self.state == PlayerState.UNINITIALIZED:
            logger.debug("VideoPlayer: Player is already uninitialized")
            deinit_task.finish_without_running()
        else:
            self._tasks.clear()  # aborts current task (if any is running)
            self._tasks.add_task(deinit_task)
        return deinit_task.future

    def initialize(self, decoder: Decoder, timer: PlaybackTimer) -> Future:
        assert decoder.media_type == MediaType.VIDEO

        def _initialize(executor: Task.Executor):
            logger.debug("VideoPlayer: Initializing...")
            with self._mutex:
                assert self._state == PlayerState.UNINITIALIZED

                deinitialize_future = self._deinitialize__locked()
                executor.abort_aware_wait_for_future(deinitialize_future, finishing_aborted=True)
                if deinitialize_future.state != Future.State.FINISHED_CLEAN:
                    logger.debug("VideoPlayer: Initializing... Failed (Deinitializing failed)")
                    executor.abort()

                with executor.finish_context():
                    self._tasks.clear(abort_current_task=True)  # this task is not in _tasks
                    self._timer = timer
                    self._decoder = decoder
                    self.__thread__set_state__locked(PlayerState.SUSPENDED)
                    logger.debug("VideoPlayer: Initializing... Successful")

        task = FnTask(_initialize)
        self._thread_spawner.start(self.__thread, task)
        return task.future

    def __thread(self, init_task: Task) -> None:
        init_task.run_if_unresolved()
        if self.state == PlayerState.UNINITIALIZED:
            logger.debug("VideoPlayer: Initializing... Failed")
            return
        try:
            self.__thread__playback_loop()
        except VideoPlayer.DeinitializeTask as deinit_task:
            with deinit_task.execute() as executor:
                logger.debug("VideoPlayer: Deinitializing...")
                with executor.finish_context():
                    with self._mutex:
                        self._tasks.clear(abort_current_task=False)
                        self._decoder.kill()
                        self._decoder = None
                        self.__thread__set_state__locked(PlayerState.UNINITIALIZED)
                        logger.debug("VideoPlayer: Deinitializing... Successful")
        except:
            with self._mutex:
                logger.error("VideoPlayer: Crashed by an error")
                self._tasks.clear(abort_current_task=True)
                self._fatal_error_signal.emit()
                self._decoder.kill()
                self._decoder = None
                self.__thread__set_state__locked(PlayerState.UNINITIALIZED)
            raise

    def __thread__playback_loop(self) -> None:
        frame: JbVideoFrame | None = None
        frame_retries = 0

        self.__thread__emit_first_frame()
        while True:
            try:
                self._tasks.run_all(MultiCondition.WaitArg() if self.state.is_suspended else None)
                if self.state.is_suspended:
                    continue

                if frame is None:
                    frame = self.__thread__get_frame()
                else:
                    frame_retries += 1

                if frame is not None and self.__thread__sync_with_timer(frame):
                    self._video_frame_update_signal.emit(frame=frame)
                    frame = None
                    frame_retries = 0
                elif frame_retries >= FRAME_RETRIES_MAX:
                    logger.error(
                        "VideoPlayer: The timer is not progressing... This player will be "
                        "suspended and a buffer underrun signal will be emitted..."
                    )
                    frame_retries = 0
                    self.__thread__set_state(PlayerState.SUSPENDED)
                    self.buffer_underrun_signal.emit()

            except VideoPlayer.SeekTask as seek_task:
                with seek_task.execute() as executor:
                    logger.debug("VideoPlayer: Seeking...")

                    seek_future = self._decoder.seek(seek_task.timepoint)
                    executor.abort_aware_wait_for_future(seek_future)
                    if seek_future.state != Future.State.FINISHED_CLEAN:
                        logger.debug("VideoPlayer: Seeking... Failed (Decoder seek error)")
                        executor.abort()

                    prefill_future = self._decoder.prefill()
                    executor.abort_aware_wait_for_future(prefill_future)
                    if prefill_future.state != Future.State.FINISHED_CLEAN:
                        if self._decoder.is_done and self._decoder.buffered_duration <= 0:
                            logger.debug("VideoPlayer: Seeking... Failed (EOF)")
                            self._state = PlayerState.SUSPENDED_EOF
                            self.eof_signal.emit()
                        else:
                            logger.debug("VideoPlayer: Seeking... Failed (Decoder prefill error)")
                        executor.abort()

                    with executor.finish_context():
                        self.__thread__emit_first_frame()
                        frame = None
                        frame_retries = 0

    def __thread__emit_first_frame(self) -> None:
        self.video_frame_update_signal.emit(frame=self.__thread__get_frame())

    def __thread__get_frame(self) -> JbVideoFrame | None:
        try:
            frame = self._decoder.pop(timeout=0)
            if frame is None:
                logger.debug("VideoPlayer: Suspended by EOF")
                self.__thread__set_state(PlayerState.SUSPENDED_EOF)
                self.eof_signal.emit()
            return frame
        except TimeoutError:
            logger.warning("VideoPlayer: Suspended by buffer underrun")
            self.__thread__set_state(PlayerState.SUSPENDED)
            self.buffer_underrun_signal.emit()
        return None

    def __thread__sync_with_timer(self, frame: JbVideoFrame) -> bool:
        sleep_threshold = min(SLEEP_THRESHOLD_MAX, frame.duration * SLEEP_THRESHOLD_RATIO)

        current_timepoint = self._timer.current_timepoint()
        if current_timepoint is None:
            return False

        sleep_time = frame.beg_timepoint - current_timepoint
        if sleep_time > sleep_threshold:
            # wait for the timer to catch up
            with self._tasks.task_added:
                self._tasks.task_added.wait(MultiCondition.WaitArg(timeout=sleep_time))

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
            logger.debug(f"VideoPlayer: Changing the state ({self.state} -> {state})")
            self._state = state
        else:
            logger.debug(f"VideoPlayer: Player already has the state '{state}'")

    def suspend(self) -> Future:
        return self._add_task(
            FnTask(
                lambda executor: executor.finish_with(
                    self.__thread__set_state, PlayerState.SUSPENDED
                )
            )
        )

    def resume(self) -> Future:
        return self._add_task(
            FnTask(
                lambda executor: executor.finish_with(self.__thread__set_state, PlayerState.PLAYING)
            )
        )

    def seek(self, source_timepoint: float) -> Future:
        assert source_timepoint >= 0

        return self._add_task(VideoPlayer.SeekTask(timepoint=source_timepoint))

    def _add_task(self, task: Task) -> Future:
        with self._mutex:
            if self.state == PlayerState.UNINITIALIZED:
                logger.debug(f"VideoPlayer: Player is uninitialized, aborting a task: {repr(task)}")
                task.future.abort()
            else:
                self._tasks.add_task(task)
        return task.future
