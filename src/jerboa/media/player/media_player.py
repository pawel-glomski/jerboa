from threading import Lock
from concurrent.futures import Future, wait as futures_wait
from typing import Any, Callable
import enum

from jerboa.core.logger import logger
from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool, ThreadSpawner, TaskQueue, Task, FnTask
from jerboa.core.timeline import FragmentedTimeline
from jerboa.media.core import AudioConstraints
from jerboa.media.source import MediaSource, MediaStreamVariant
from .audio_player import AudioPlayer
from .video_player import VideoPlayer
from .timer import ClockPlaybackTimer
from .state import PlayerState
from . import decoding


THREAD_RESPONSE_TIMEOUT = 0.1
DECODER_PREFILL_TIMEOUT = 10
SEEK_TIME = 5  # in seconds


class PlayerTask(FnTask):
    class ID(enum.Enum):
        INITIALIZE = enum.auto()
        DEINITIALIZE = enum.auto()
        SUSPEND = enum.auto()
        RESUME = enum.auto()
        SEEK = enum.auto()

    def __init__(self, fn: Callable[[], None], *, id: ID) -> None:
        super().__init__(fn, id=id)

    def invalidates(self, task: Task) -> bool:
        match self.id:
            case None:  # default unnamed task
                return False  # invalidates none
            case PlayerTask.ID.INITIALIZE:
                return task.id != PlayerTask.ID.DEINITIALIZE
            case PlayerTask.ID.DEINITIALIZE:
                return True  # invalidates all
            case PlayerTask.ID.SUSPEND | PlayerTask.ID.RESUME:
                return (task.id in [PlayerTask.ID.SUSPEND, PlayerTask.ID.RESUME],)
            case PlayerTask.ID.SEEK:
                return task.id == PlayerTask.ID.SEEK
            case _:
                return False


class MediaPlayer:
    class KillTask(Task):
        ...

    def __init__(
        self,
        audio_player: AudioPlayer,
        video_player: VideoPlayer,
        audio_decoding_pipeline_factory: Callable[
            [decoding.context.DecodingContext], decoding.pipeline.Pipeline
        ],
        video_decoding_pipeline_factory: Callable[
            [decoding.context.DecodingContext], decoding.pipeline.Pipeline
        ],
        timeline: FragmentedTimeline,
        thread_pool: ThreadPool,
        thread_spawner: ThreadSpawner,
        fatal_error_signal: Signal,
        ready_to_play_signal: Signal,
    ):
        self._audio_player = audio_player
        self._video_player = video_player

        self._audio_decoding_pipeline_factory = audio_decoding_pipeline_factory
        self._video_decoding_pipeline_factory = video_decoding_pipeline_factory

        self._timeline = timeline
        self._thread_pool = thread_pool
        self._ready_to_play_signal = ready_to_play_signal
        self._current_media_source: MediaSource | None = None

        self._clock_timer = ClockPlaybackTimer()

        self._fatal_error_signal = fatal_error_signal
        self._fatal_error_signal.connect(self._on_fatal_error)

        self._audio_player.fatal_error_signal.connect(self._fatal_error_signal.emit)
        self._video_player.fatal_error_signal.connect(self._fatal_error_signal.emit)

        self._audio_player.buffer_underrun_signal.connect(self._on_buffer_underrun)
        self._video_player.buffer_underrun_signal.connect(self._on_buffer_underrun)

        self._audio_player.eof_signal.connect(self._on_eof)
        self._video_player.eof_signal.connect(self._on_eof)

        self._mutex = Lock()
        self._tasks = TaskQueue()
        thread_spawner.start(self.__player_job)

    @property
    def ready_to_play_signal(self) -> Signal:
        return self._ready_to_play_signal

    @property
    def video_frame_update_signal(self) -> Signal:
        return self._video_player.video_frame_update_signal

    def _on_fatal_error(self) -> None:
        logger.error("MediaPlayer: Player crashed")
        self.deinitialize()

    def _on_buffer_underrun(self) -> None:
        logger.error("MediaPlayer: Buffer underrun, suspending playback")
        self.suspend()

    def _on_eof(self) -> None:
        logger.info("MediaPlayer: EOF Reached... Suspending playback")
        self.suspend()

    def deinitialize(self) -> None:
        self._add_player_task(
            PlayerTask(self.__player_job__deinitialize, id=PlayerTask.ID.DEINITIALIZE)
        )

    def __player_job__deinitialize(self) -> None:
        with self._mutex:
            self.__player_job__deinitialize__locked()

    def __player_job__deinitialize__locked(self) -> None:
        assert self._mutex.locked()

        try:
            self._clock_timer.deinitialize()
            deinit_task_audio = self._audio_player.deinitialize()
            deinit_task_video = self._video_player.deinitialize()

            deinit_task_audio.wait_done(timeout=THREAD_RESPONSE_TIMEOUT)
            deinit_task_video.wait_done(timeout=THREAD_RESPONSE_TIMEOUT)

            failed = False
            if self._audio_player.state != PlayerState.UNINITIALIZED:
                failed = True
                logger.error("MediaPlayer: Audio player failed to deinitialize")
            if self._video_player.state != PlayerState.UNINITIALIZED:
                failed = True
                logger.error("MediaPlayer: Video player failed to deinitialize")

            if failed:
                raise RuntimeError("Failed to deinitialize")
        except:
            logger.error("MediaPlayer: Failed to deinitialize")
            raise

    def initialize(self, media_source: MediaSource):
        assert media_source.audio.is_available or media_source.video.is_available
        assert media_source.is_resolved

        logger.info(f"MediaPlayer: Preparing to play '{media_source.title}'")

        self._add_player_task(
            PlayerTask(
                lambda: self.__player_job__initialize(media_source),
                id=PlayerTask.ID.INITIALIZE,
            )
        )

    def __player_job__initialize(self, media_source: MediaSource):
        audio_context, video_context = self.__player_job__initialize__open_media_contexts(
            media_source
        )
        assert not (audio_context is None and video_context is None)

        audio_decoder, video_decoder = self.__player_job__initialize__create_decoders(
            audio_context, video_context
        )
        assert not (audio_decoder is None and video_decoder is None)

        with self._mutex:
            try:
                self.__player_job__deinitialize__locked()

                self._clock_timer.initialize()
                video_timer = self._clock_timer
                if audio_decoder is not None:
                    self._audio_player.initialize(decoder=audio_decoder).wait_done(
                        timeout=THREAD_RESPONSE_TIMEOUT
                    )
                    video_timer = self._audio_player
                if video_decoder is not None:
                    self._video_player.initialize(
                        decoder=video_decoder, timer=video_timer
                    ).wait_done(timeout=THREAD_RESPONSE_TIMEOUT)

                if (
                    audio_decoder is not None
                    and self._audio_player.state == PlayerState.UNINITIALIZED
                ):
                    raise RuntimeError("MediaPlayer: Audio player failed to initialize")
                if (
                    video_decoder is not None
                    and self._video_player.state == PlayerState.UNINITIALIZED
                ):
                    raise RuntimeError("MediaPlayer: Video player failed to initialize")

                # initialization succeeded
                logger.info(f"MediaPlayer: Ready to play '{media_source.title}'")
                self._ready_to_play_signal.emit()

            except:
                if audio_decoder is not None:
                    audio_decoder.kill()
                if video_decoder is not None:
                    video_decoder.kill()

                self.__player_job__deinitialize__locked()

                self._fatal_error_signal.emit()
                logger.error(
                    "MediaPlayer: The following exception interrupted the initialization for "
                    f"'{media_source.title}'"
                )
                raise  # thread pool worker will log the exception

    def __player_job__initialize__open_media_contexts(
        self, media_source: MediaSource
    ) -> tuple[decoding.context.DecodingContext | None, decoding.context.DecodingContext | None]:
        audio_context: Future[decoding.context.DecodingContext] | None = None
        video_context: Future[decoding.context.DecodingContext] | None = None
        if media_source.audio.is_available:
            audio_context = self._thread_pool.start(
                self.__player_job__initialize__open_media_context,
                source=media_source.audio.selected_variant_group[0],
                constraints=self._audio_player.get_constraints(),
            )
        if media_source.video.is_available:
            video_context = self._thread_pool.start(
                self.__player_job__initialize__open_media_context,
                source=media_source.video.selected_variant_group[0],
                constraints=None,
            )

        futures_wait(future for future in [audio_context, video_context] if future is not None)

        # these should raise exceptions on errors
        if audio_context is not None:
            audio_context = audio_context.result()
        if video_context is not None:
            video_context = video_context.result()
        return (audio_context, video_context)

    def __player_job__initialize__open_media_context(
        self, source: MediaStreamVariant, constraints: AudioConstraints
    ) -> decoding.decoder.Decoder:
        return decoding.context.DecodingContext(
            media=decoding.context.MediaContext(
                av=decoding.context.AVContext.open(
                    filepath=source.path,
                    media_type=source.media_type,
                    stream_idx=0,
                ),
                media_constraints=constraints,
            ),
            timeline=self._timeline,
        )

    def __player_job__initialize__create_decoders(
        self,
        audio_media_context: decoding.context.DecodingContext | None,
        video_media_context: decoding.context.DecodingContext | None,
    ) -> tuple[decoding.decoder.Decoder, decoding.decoder.Decoder]:
        try:
            audio_decoder: decoding.decoder.Decoder | None = None
            video_decoder: decoding.decoder.Decoder | None = None

            if audio_media_context is not None:
                audio_decoder = self._audio_decoding_pipeline_factory(context=audio_media_context)
                audio_prefill_task = audio_decoder.prefill(timeout=DECODER_PREFILL_TIMEOUT)
            if video_media_context is not None:
                video_decoder = self._video_decoding_pipeline_factory(context=video_media_context)
                video_prefill_task = video_decoder.prefill(timeout=DECODER_PREFILL_TIMEOUT)

            if audio_decoder is not None:
                audio_prefill_task.wait_done()
            if video_decoder is not None:
                video_prefill_task.wait_done()

            return (audio_decoder, video_decoder)

        except:
            if audio_decoder is not None:
                audio_decoder.kill()
            if video_decoder is not None:
                audio_decoder.kill()
            raise

    def playback_toggle(self) -> None:
        with self._mutex:
            if not self._clock_timer.is_initialized:
                return

            if self._clock_timer.is_running:
                self.suspend()

            else:
                self.resume()

    def suspend(self) -> None:
        self._add_player_task(PlayerTask(self.__player_job__suspend, id=PlayerTask.ID.SUSPEND))

    def __player_job__suspend(self) -> None:
        with self._mutex:
            self.__player_job__suspend__locked()

    def __player_job__suspend__locked(self) -> None:
        assert self._mutex.locked()

        try:
            audio_task = self._audio_player.suspend()
            video_task = self._video_player.suspend()

            audio_task.wait_done(timeout=THREAD_RESPONSE_TIMEOUT)
            video_task.wait_done(timeout=THREAD_RESPONSE_TIMEOUT)
            self._clock_timer.suspend()

            assert self._audio_player.state != PlayerState.PLAYING
            assert self._video_player.state != PlayerState.PLAYING
        except:
            logger.error("MediaPlayer: Failed to suspend")
            raise

    def resume(self) -> None:
        self._add_player_task(PlayerTask(self.__player_job__resume, id=PlayerTask.ID.RESUME))

    def __player_job__resume(self) -> None:
        with self._mutex:
            self.__player_job__resume__locked()

    def __player_job__resume__locked(self) -> None:
        assert self._mutex.locked()

        try:
            audio_task = self._audio_player.resume()
            video_task = self._video_player.resume()

            audio_task.wait_done(timeout=THREAD_RESPONSE_TIMEOUT)
            video_task.wait_done(timeout=THREAD_RESPONSE_TIMEOUT)
            if PlayerState.PLAYING in [self._audio_player.state, self._video_player.state]:
                self._clock_timer.resume()
            else:
                logger.info("MediaPlayer: Players failed to resume")
        except:
            self.__player_job__suspend__locked()  # suspend players that may have succeeded
            logger.error("MediaPlayer: Failed to resume")
            raise

    def seek_backward(self) -> None:
        self._seek(-SEEK_TIME)

    def seek_forward(self) -> None:
        self._seek(SEEK_TIME)

    def _seek(self, time_change: float):
        self._add_player_task(
            PlayerTask(lambda: self.__player_job__seek(time_change), id=PlayerTask.ID.SEEK)
        )

    def __player_job__seek(self, time_change: float):
        with self._mutex:
            if not self._clock_timer.is_initialized:
                return

            playing = self._clock_timer.is_running
            self.__player_job__suspend__locked()

            if self._audio_player.state == PlayerState.UNINITIALIZED:
                current_timepoint = self._clock_timer.current_timepoint()
            else:
                current_timepoint = self._audio_player.current_timepoint()

            current_timepoint = max(0, current_timepoint + time_change)

            source_timepoint = self._timeline.unmap_timepoint_to_source(current_timepoint)
            self._clock_timer.seek(current_timepoint)
            audio_task = self._audio_player.seek(
                source_timepoint=source_timepoint,
                new_timer_offset=current_timepoint,
            )
            video_task = self._video_player.seek(source_timepoint)

            audio_task.wait_done()
            video_task.wait_done()

            if playing:
                self.__player_job__resume__locked()

    def __player_job(self) -> None:
        while True:
            try:
                self._current_task = self._tasks.pop(wait_when_empty=True)
                self._current_task.run_if_unresolved()
            except MediaPlayer.KillTask as kill_task:
                logger.info("MediaPlayer: Killed by a task")
                kill_task.complete()
                break
            except:
                logger.error("MediaPlayer: Killed by an error")
                raise
            finally:
                with self._mutex:
                    self._current_task = None
                    self._tasks.clear()

    def _add_player_task(self, task: PlayerTask) -> None:
        self._tasks.add_task(task, apply_invalidation_rules=True)
