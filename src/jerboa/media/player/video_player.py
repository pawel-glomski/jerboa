import time
from collections import deque
from enum import Enum, auto
from threading import Condition, Lock

from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadSpawner
from jerboa.media.player.decoding.timeline_decoder import TimelineDecoder, JbVideoFrame


TIMEOUT_TIME = 0.1


class SynchronizationClock:
    def __init__(self) -> None:
        self._cumulative_time_ns = 0
        self._last_time_ns: int | None = None
        self._time_now_ns = time.perf_counter_ns

    def start(self) -> None:
        self._last_time_ns = self._time_now_ns()

    def stop(self) -> None:
        self._cumulative_time_ns += self._time_now_ns() - self._last_time_ns
        self._last_time_ns = None

    def time(self) -> float:
        result = self._cumulative_time_ns
        if self._last_time_ns is not None:
            result += self._time_now_ns() - self._last_time_ns
        return result / 1e9


class PlayerState(Enum):
    STOPPED = auto()
    SUSPENDED = auto()
    PLAYING = auto()


class StopPlayer(Exception):
    ...


class SuspendPlaying(Exception):
    ...


class ResumePlaying(Exception):
    ...


class SeekToTimepoint(Exception):
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
    ):
        self._thread_spawner = thread_spawner
        self._player_stalled_signal = player_stalled_signal
        self._video_frame_update_signal = video_frame_update_signal
        self._sync_clock = SynchronizationClock()

        self._state = PlayerState.STOPPED

        self._tasks = deque[Exception]()
        self._mutex = Lock()
        self._state_changed = Condition(self._mutex)
        self._new_tasks_added = Condition(self._mutex)

    @property
    def player_stalled_signal(self) -> Signal:
        return self._player_stalled_signal

    @property
    def video_frame_update_signal(self) -> Signal:
        return self._video_frame_update_signal

    def __del__(self):
        self.stop(wait=True)

    # @property
    # def is_playing(self) -> bool:
    #     return self._state == PlayerState.PLAYING

    # @property
    # def has_media(self) -> bool:
    #     return self._state in [PlayerState.PLAYING, PlayerState.SUSPENDED]

    def stop(self, wait: bool) -> None:
        with self._mutex:
            self._tasks.clear()
            if self._state != PlayerState.STOPPED:
                self._tasks.append(StopPlayer())
                self._new_tasks_added.notify()
                assert not wait or self._state_changed.wait_for(
                    lambda: self._state == PlayerState.STOPPED, timeout=2 * TIMEOUT_TIME
                )

    def start(self, decoder: TimelineDecoder):
        self._thread_spawner.start(self._player_job, decoder)

    def _player_job(self, decoder: TimelineDecoder) -> None:
        self.stop(wait=True)
        self._state = PlayerState.SUSPENDED
        try:
            self._playback_seek_loop(decoder)
        except Exception as e:
            with self._mutex:
                self._state = PlayerState.STOPPED
                self._state_changed.notify_all()
            if not isinstance(e, StopPlayer):
                raise

    def _playback_seek_loop(self, decoder: TimelineDecoder) -> None:
        while True:
            try:
                self._playback_loop(decoder)
            except SeekToTimepoint as seek:
                decoder.seek(seek_timepoint=seek.timepoint)

    def _playback_loop(self, decoder: TimelineDecoder):
        frame: JbVideoFrame | None = None
        while True:
            self._do_tasks()
            if self._state == PlayerState.SUSPENDED:
                with self._mutex:
                    self._new_tasks_added.wait_for(lambda: len(self._tasks) > 0)
                continue

            assert self._state == PlayerState.PLAYING

            if frame is None:
                try:
                    frame = decoder.pop(timeout=TIMEOUT_TIME)
                    if frame is None:
                        self._state = PlayerState.SUSPENDED
                except TimeoutError:
                    self._state = PlayerState.SUSPENDED
                    self._player_stalled_signal.emit()

            if frame is not None and self._sync_to_frame(frame):
                self._video_frame_update_signal.emit(frame)
                frame = None

    def _do_tasks(self) -> None:
        with self._mutex:
            while self._tasks:
                task = self._tasks.pop()
                try:
                    raise task
                except ResumePlaying:
                    self._state = PlayerState.PLAYING
                except SuspendPlaying:
                    self._state = PlayerState.SUSPENDED

    def _sync_to_frame(self, frame: JbVideoFrame) -> bool:
        sleep_threshold = min(0.004, frame.duration / 3)
        with self._mutex:
            sleep_time = frame.timepoint - self._sync_clock.time()
            if sleep_time > sleep_threshold and not self._new_tasks_added.wait(sleep_time):
                sleep_time = frame.timepoint - self._sync_clock.time()

        if sleep_time <= sleep_threshold:
            return True
        return False

    def suspend(self) -> None:
        self._put_task_with_lock(SuspendPlaying())

    def resume(self) -> None:
        self._put_task_with_lock(ResumePlaying())

    def toggle_suspend_resume(self) -> None:
        if self._state == PlayerState.PLAYING:
            self.suspend()
        elif self._state == PlayerState.SUSPENDED:
            self.resume()

    def seek(self, timepoint: float):
        self._put_task_with_lock(SeekToTimepoint(timepoint))

    def _put_task_with_lock(self, task: Exception):
        with self._mutex:
            self._tasks.append(task)
            self._new_tasks_added.notify()
