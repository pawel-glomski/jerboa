from collections import deque
from threading import Condition, Lock

from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadSpawner
from jerboa.media.core import MediaType
from jerboa.media.source import VideoSourceVariant
from .decoding.decoder import pipeline, JbDecoder
from .decoding.pipeline.frame import JbVideoFrame
from .state import PlayerState
from .clock import SynchronizationClock


TIMEOUT_TIME = 0.1


class StopPlayerTask(Exception):
    ...


class SuspendPlayerTask(Exception):
    ...


class ResumePlayerTask(Exception):
    ...


class TimepointSeekTask(Exception):
    def __init__(self, timepoint: float):
        super().__init__()
        self._timepoint = timepoint

    @property
    def timepoint(self) -> float:
        return self._timepoint


class VideoPlayer:
    def __init__(
        self,
        thread_spawner: ThreadSpawner,
        player_stalled_signal: Signal,
        video_frame_update_signal: Signal,
        decoder: JbDecoder,
    ):
        self._decoder = decoder
        self._thread_spawner = thread_spawner
        self._player_stalled_signal = player_stalled_signal
        self._video_frame_update_signal = video_frame_update_signal

        self._mutex = Lock()
        self._tasks = deque[Exception]()
        self._new_tasks_added = Condition(self._mutex)

        self._state = PlayerState.STOPPED
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
        self.stop(wait=True)

    # @property
    # def is_playing(self) -> bool:
    #     return self._state == PlayerState.PLAYING

    # @property
    # def has_media(self) -> bool:
    #     return self._state in [PlayerState.PLAYING, PlayerState.SUSPENDED]

    def wait_for_state(self, states: list[PlayerState], timeout: float) -> None:
        with self._mutex:
            self._wait_for_state__unsafe(states, timeout)

    def _wait_for_state__unsafe(self, states: list[PlayerState], timeout: float | None) -> None:
        if not self._state_changed.wait_for(lambda: self._state in states, timeout=timeout):
            raise TimeoutError(f"Waiting for state ({states=}) timed out ({timeout=})")

    def stop(self, wait: bool = False) -> None:
        with self._mutex:
            # self._tasks.clear()
            if self.state not in [PlayerState.STOPPED, PlayerState.STOPPED_ON_ERROR]:
                # self._decoder.stop()
                self._tasks.append(StopPlayerTask())
                self._new_tasks_added.notify()
                if wait:
                    self._wait_for_state__unsafe(
                        [PlayerState.STOPPED, PlayerState.STOPPED_ON_ERROR],
                        timeout=2 * TIMEOUT_TIME,
                    )

    def start(self, source: VideoSourceVariant, sync_clock: SynchronizationClock):
        self._thread_spawner.start(self._player_job, source, sync_clock)

    def _set_state_with_notify(self, state: PlayerState) -> None:
        with self._mutex:
            self._set_state_with_notify__unsafe(state)

    def _set_state_with_notify__unsafe(self, state: PlayerState) -> None:
        assert self._mutex.locked()

        self._state = state
        self._state_changed.notify_all()

    def _player_job(self, source: VideoSourceVariant, sync_clock: SynchronizationClock) -> None:
        self.stop(wait=True)

        try:
            self._sync_clock = sync_clock
            self._decoder.start(
                pipeline.MediaContext.open(
                    source.path,
                    MediaType.VIDEO,
                    stream_idx=0,
                    media_constraints=None,
                )
            )
            self._set_state_with_notify(PlayerState.SUSPENDED)
            self._playback_seek_loop()
        except StopPlayerTask:
            self._set_state_with_notify(PlayerState.STOPPED)
        except Exception:
            self._set_state_with_notify(PlayerState.STOPPED_ON_ERROR)
            raise

    def _playback_seek_loop(self) -> None:
        while True:
            try:
                self._playback_loop()
            except TimepointSeekTask as seek:
                self._decoder.seek(seek_timepoint=seek.timepoint)

    def _playback_loop(self):
        frame: JbVideoFrame | None = None
        while True:
            self._do_tasks()

            if self.state == PlayerState.SUSPENDED:
                with self._mutex:
                    self._new_tasks_added.wait_for(lambda: len(self._tasks) > 0)
                continue

            if frame is None:
                try:
                    frame = self._decoder.pop(timeout=TIMEOUT_TIME)
                    if frame is None:
                        self._set_state_with_notify(PlayerState.SUSPENDED)
                        continue
                except TimeoutError:
                    self._set_state_with_notify(PlayerState.SUSPENDED)
                    self._player_stalled_signal.emit()
                    continue
            assert self.state == PlayerState.PLAYING

            if frame is not None and self._sync_with_clock(frame):
                self._video_frame_update_signal.emit(frame)
                frame = None

    def _do_tasks(self) -> None:
        with self._mutex:
            while self._tasks:
                try:
                    raise self._tasks.popleft()
                except ResumePlayerTask:
                    self._set_state_with_notify__unsafe(PlayerState.PLAYING)
                except SuspendPlayerTask:
                    self._set_state_with_notify__unsafe(PlayerState.SUSPENDED)

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
        self._put_task_with_lock(SuspendPlayerTask())

    def resume(self) -> None:
        self._put_task_with_lock(ResumePlayerTask())

    def toggle_suspend_resume(self) -> None:
        if self.state == PlayerState.PLAYING:
            self.suspend()
        elif self.state == PlayerState.SUSPENDED:
            self.resume()

    def seek(self, timepoint: float):
        self._put_task_with_lock(TimepointSeekTask(timepoint))

    def _put_task_with_lock(self, task: Exception):
        with self._mutex:
            self._tasks.append(task)
            self._new_tasks_added.notify()
