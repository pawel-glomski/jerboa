from collections import deque
from threading import Condition, Lock
from dataclasses import dataclass

from jerboa.core.logger import logger
from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadSpawner
from jerboa.media.core import MediaType
from jerboa.media.source import VideoSourceVariant
from .decoding.task_queue import Task, FnTask
from .decoding.decoder import pipeline, JbDecoder
from .decoding.pipeline.frame import JbVideoFrame
from .state import PlayerState
from .clock import SynchronizationClock


TIMEOUT_TIME = 0.1


class ShutdownTask(Task):
    ...


@dataclass(frozen=True)
class SeekTask(Task):
    timepoint: float


class VideoPlayer:
    def __init__(
        self,
        decoder: JbDecoder,
        thread_spawner: ThreadSpawner,
        player_stalled_signal: Signal,
        video_frame_update_signal: Signal,
    ):
        self._decoder = decoder
        self._thread_spawner = thread_spawner
        self._player_stalled_signal = player_stalled_signal
        self._video_frame_update_signal = video_frame_update_signal

        self._mutex = Lock()
        self._tasks = deque[Task]()
        self._new_tasks_added = Condition(self._mutex)

        self._state = PlayerState.SHUT_DOWN
        self._state_changed = Condition(self._mutex)

        self._sync_clock: SynchronizationClock | None = None

    @property
    def player_stalled_signal(self) -> Signal:
        return self._player_stalled_signal

    @property
    def video_frame_update_signal(self) -> Signal:
        return self._video_frame_update_signal

    @property
    def state(self) -> PlayerState:
        return self._state

    def __del__(self):
        self.shutdown(wait=True)

    # @property
    # def is_playing(self) -> bool:
    #     return self._state == PlayerState.PLAYING

    # @property
    # def has_media(self) -> bool:
    #     return self._state in [PlayerState.PLAYING, PlayerState.SUSPENDED]

    def shutdown(self, wait: bool = False) -> None:
        with self._mutex:
            self._shutdown__without_lock(wait=wait)

    def _shutdown__without_lock(self, wait: bool) -> None:
        assert self._mutex.locked()

        if self.state != PlayerState.SHUT_DOWN:
            self._tasks.clear()
            self._put_task__without_lock(ShutdownTask())
            if wait:
                self._wait_for_state__without_lock(
                    PlayerState.SHUT_DOWN,
                    timeout=2 * TIMEOUT_TIME,
                )

    def _wait_for_state__without_lock(self, state: PlayerState, timeout: float | None) -> None:
        assert self._mutex.locked()

        if not self._state_changed.wait_for(lambda: self._state == state, timeout=timeout):
            raise TimeoutError(f"Waiting for state ({state=}) timed out ({timeout=})")

    def startup(self, source: VideoSourceVariant, sync_clock: SynchronizationClock) -> None:
        assert source.media_type == MediaType.VIDEO

        with self._mutex:
            self._shutdown__without_lock(wait=True)

            self._sync_clock = sync_clock
            self._tasks.clear()

            self._decoder.start(
                pipeline.context.MediaContext(
                    av=pipeline.context.AVContext.open(
                        source.path,
                        MediaType.VIDEO,
                        stream_idx=0,
                    ),
                    media_constraints=None,
                )
            )

            logger.debug("VideoPlayer: Starting the job")
            self._thread_spawner.start(self._player_job)

    def _player_job(self) -> None:
        try:
            self._set_state_with_notify(PlayerState.SUSPENDED)
            self._playback_seek_loop()
        except ShutdownTask:
            logger.debug("VideoPlayer: The job was stopped by a task")
            self._decoder.stop()
            self._set_state_with_notify(PlayerState.SHUT_DOWN)
        except Exception:
            logger.debug("VideoPlayer: The job was stopped by an error")
            self._set_state_with_notify(PlayerState.SHUT_DOWN)
            raise

    def _set_state_with_notify(self, state: PlayerState) -> None:
        with self._mutex:
            self._set_state_with_notify__without_lock(state)

    def _set_state_with_notify__without_lock(self, state: PlayerState) -> None:
        assert self._mutex.locked()

        self._state = state
        self._state_changed.notify_all()

    def _playback_seek_loop(self) -> None:
        while True:
            try:
                self._playback_loop()
            except SeekTask as seek:
                self._decoder.seek(seek_timepoint=seek.timepoint)

    def _playback_loop(self):
        frame: JbVideoFrame | None = None
        while True:
            self._do_tasks()

            if self.state == PlayerState.SUSPENDED:
                frame = None
                with self._mutex:
                    self._new_tasks_added.wait_for(lambda: len(self._tasks) > 0)
                continue

            if frame is None:
                try:
                    frame = self._decoder.pop(timeout=TIMEOUT_TIME)
                    if frame is None:
                        logger.warning("VideoPlayer: Player suspended by EOF")
                        self._set_state_with_notify(PlayerState.SUSPENDED)
                        continue
                except TimeoutError:
                    logger.warning("VideoPlayer: Player suspended by a timeout")
                    self._set_state_with_notify(PlayerState.SUSPENDED)
                    self._player_stalled_signal.emit()
                    continue
            assert self.state == PlayerState.PLAYING

            if frame is not None and self._sync_with_clock(frame):
                self._video_frame_update_signal.emit(frame=frame)
                frame = None

    def _do_tasks(self) -> None:
        with self._mutex:
            while self._tasks:
                self._tasks.popleft().run()

    def _sync_with_clock(self, frame: JbVideoFrame) -> bool:
        sleep_threshold = min(0.004, frame.duration / 3)
        with self._mutex:
            sleep_time = frame.beg_timepoint - self._sync_clock.time()
            if sleep_time > sleep_threshold and not self._new_tasks_added.wait(sleep_time):
                sleep_time = frame.beg_timepoint - self._sync_clock.time()

        if sleep_time <= sleep_threshold:
            return True
        return False

    def suspend(self) -> None:
        self._put_task__with_lock(
            FnTask(self._set_state_with_notify__without_lock, PlayerState.SUSPENDED)
        )

    def resume(self) -> None:
        self._put_task__with_lock(
            FnTask(self._set_state_with_notify__without_lock, PlayerState.PLAYING)
        )

    def seek(self, timepoint: float):
        self._put_task__with_lock(SeekTask(timepoint))

    def _put_task__with_lock(self, task: Exception):
        with self._mutex:
            self._put_task__without_lock(task)

    def _put_task__without_lock(self, task: Exception):
        self._tasks.append(task)
        self._new_tasks_added.notify()
