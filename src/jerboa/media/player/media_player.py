from typing import Callable
import enum

from jerboa.logger import logger
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

SEEK_TIME = 5  # in seconds


class PlayerTask(FnTask):
    class ID(enum.Enum):
        INITIALIZE = enum.auto()
        UNINITIALIZE = enum.auto()
        PLAYBACK_TOGGLE = enum.auto()
        SUSPEND = enum.auto()
        RESUME = enum.auto()
        SEEK = enum.auto()
        EOF = enum.auto()

    def invalidates(self, task: Task) -> bool:
        if not isinstance(task.id, PlayerTask.ID):
            return False

        match self.id:
            case PlayerTask.ID.INITIALIZE:
                return task.id != PlayerTask.ID.UNINITIALIZE
            case PlayerTask.ID.UNINITIALIZE:
                return True  # invalidates all
            case PlayerTask.ID.PLAYBACK_TOGGLE:
                return task.id == PlayerTask.ID.PLAYBACK_TOGGLE
            case PlayerTask.ID.SUSPEND:
                return task.id in [PlayerTask.ID.RESUME, PlayerTask.ID.PLAYBACK_TOGGLE]
            case PlayerTask.ID.RESUME:
                return task.id == [PlayerTask.ID.SUSPEND, PlayerTask.ID.PLAYBACK_TOGGLE]
            case PlayerTask.ID.SEEK:
                return task.id == PlayerTask.ID.SEEK
            case PlayerTask.ID.EOF:
                return task.id not in [PlayerTask.ID.INITIALIZE, PlayerTask.ID.UNINITIALIZE]
            case _:
                return False


class MediaPlayer:
    class KillTask(Task):
        ...

    def __init__(
        self,
        audio_player: AudioPlayer,
        video_player: VideoPlayer,
        audio_decoder_factory: Callable[
            [decoding.context.DecodingContext], decoding.decoder.Decoder
        ],
        video_decoder_factory: Callable[
            [decoding.context.DecodingContext], decoding.decoder.Decoder
        ],
        timeline: FragmentedTimeline,
        thread_pool: ThreadPool,
        thread_spawner: ThreadSpawner,
        fatal_error_signal: Signal,
        ready_to_play_signal: Signal,
    ):
        self._audio_player = audio_player
        self._video_player = video_player

        self._audio_decoder_factory = audio_decoder_factory
        self._video_decoder_factory = video_decoder_factory

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

        self._tasks = TaskQueue()
        thread_spawner.start(self.__thread)

    @property
    def ready_to_play_signal(self) -> Signal:
        return self._ready_to_play_signal

    @property
    def video_frame_update_signal(self) -> Signal:
        return self._video_player.video_frame_update_signal

    def _on_fatal_error(self) -> None:
        logger.error("Player crashed")
        self.uninitialize()

    def _on_buffer_underrun(self) -> None:
        logger.error("Buffer underrun, suspending playback")
        self.suspend()

    def _on_eof(self) -> None:
        self._add_player_task(PlayerTask(self.__thread__eof, id=PlayerTask.ID.EOF))

    def __thread__eof(self, executor: Task.Executor) -> None:
        logger.info("Suspending by EOF...")
        try:
            self.__thread__suspend(executor)
            logger.debug("Suspending by EOF... Successful")
        except:
            logger.debug("Suspending by EOF... Failed")
            raise

    def uninitialize(self) -> None:
        self._add_player_task(
            PlayerTask(self.__thread__uninitialize, id=PlayerTask.ID.UNINITIALIZE)
        )

    def __thread__uninitialize(self, executor: Task.Executor, *, finish_task: bool = True) -> None:
        logger.debug("Uninitializing...")
        try:
            self._clock_timer.uninitialize()
            audio_future = self._audio_player.uninitialize()
            video_future = self._video_player.uninitialize()

            executor.abort_aware_wait_for_future(audio_future)
            executor.abort_aware_wait_for_future(video_future)

            failed = False
            if self._audio_player.is_initialized:
                failed = True
                logger.error("Audio player failed to uninitialize")
            if self._video_player.is_initialized:
                failed = True
                logger.error("Video player failed to uninitialize")

            if failed:
                raise RuntimeError()
            if finish_task:
                executor.finish()
            logger.debug("Uninitializing... Successful")
        except:
            logger.error("Uninitializing... Failed")
            raise

    def initialize(self, media_source: MediaSource):
        assert media_source.audio.is_available or media_source.video.is_available
        assert media_source.is_resolved

        logger.info(f"Preparing to play '{media_source.title}'")

        self._add_player_task(
            PlayerTask(
                lambda executor: self.__thread__initialize(executor, media_source),
                id=PlayerTask.ID.INITIALIZE,
            )
        )

    def __thread__initialize(self, executor: Task.Executor, media_source: MediaSource) -> None:
        logger.debug(f"Initializing '{media_source.title}'...")
        try:
            audio_context, video_context = self.__thread__initialize__open_media_contexts(
                executor, media_source
            )
            assert not (audio_context is None and video_context is None)

            audio_decoder, video_decoder = self.__thread__initialize__create_decoders(
                executor, audio_context, video_context
            )
            assert not (audio_decoder is None and video_decoder is None)
        except:
            logger.debug(f"Initializing '{media_source.title}'... Failed")
            raise

        try:
            self.__thread__uninitialize(executor, finish_task=False)

            self._clock_timer.initialize()
            video_timer = self._clock_timer
            if audio_decoder is not None:
                executor.abort_aware_wait_for_future(
                    self._audio_player.initialize(decoder=audio_decoder)
                )
                video_timer = self._audio_player
            if video_decoder is not None:
                executor.abort_aware_wait_for_future(
                    self._video_player.initialize(decoder=video_decoder, timer=video_timer)
                )
            else:
                self.video_frame_update_signal.emit(frame=None)  # send "no-video-stream" frame

            if audio_decoder is not None and not self._audio_player.is_initialized:
                raise RuntimeError("Audio player failed to initialize")
            if video_decoder is not None and not self._video_player.is_initialized:
                raise RuntimeError("Video player failed to initialize")

            with executor.finish_context:
                logger.info(f"Initializing '{media_source.title}'... Successful")
                self._ready_to_play_signal.emit()

        except:
            logger.error(f"Initializing '{media_source.title}'... Failed")

            if audio_decoder is not None:
                audio_decoder.kill()
            if video_decoder is not None:
                video_decoder.kill()

            self.__thread__uninitialize(executor, finish_task=False)

            self._fatal_error_signal.emit()
            raise

    def __thread__initialize__open_media_contexts(
        self,
        executor: Task.Executor,
        media_source: MediaSource,
    ) -> tuple[decoding.context.DecodingContext | None, decoding.context.DecodingContext | None]:
        audio_future: Task.Future[decoding.context.DecodingContext] | None = None
        video_future: Task.Future[decoding.context.DecodingContext] | None = None
        if media_source.audio.is_available:
            audio_future = self._thread_pool.start(
                FnTask[decoding.decoder.Decoder](
                    lambda sub_executor: sub_executor.finish_with(
                        self.__thread__initialize__open_media_context,
                        media_source.audio.selected_variant_group[0],
                        self._audio_player.get_constraints(),
                    )
                )
            )
        if media_source.video.is_available:
            video_future = self._thread_pool.start(
                FnTask[decoding.decoder.Decoder](
                    lambda sub_executor: sub_executor.finish_with(
                        self.__thread__initialize__open_media_context,
                        media_source.video.selected_variant_group[0],
                        constraints=None,
                    )
                )
            )

        audio_context: decoding.context.DecodingContext | None = None
        video_context: decoding.context.DecodingContext | None = None
        # these will raise exceptions on errors
        if audio_future is not None:
            executor.abort_aware_wait_for_future(audio_future)
            audio_context = audio_future.result()
        if video_future is not None:
            executor.abort_aware_wait_for_future(video_future)
            video_context = video_future.result()

        return (audio_context, video_context)

    def __thread__initialize__open_media_context(
        self,
        source: MediaStreamVariant,
        constraints: AudioConstraints,
    ) -> decoding.decoder.Decoder:
        return decoding.context.DecodingContext(
            media=decoding.context.MediaContext(
                avc=decoding.context.AVContext.open(
                    filepath=source.path,
                    media_type=source.media_type,
                    stream_idx=0,
                ),
                media_constraints=constraints,
            ),
            timeline=self._timeline,
        )

    def __thread__initialize__create_decoders(
        self,
        executor: Task.Executor,
        audio_media_context: decoding.context.DecodingContext | None,
        video_media_context: decoding.context.DecodingContext | None,
    ) -> tuple[decoding.decoder.Decoder, decoding.decoder.Decoder]:
        executor.exit_if_aborted()

        audio_decoder: decoding.decoder.Decoder | None = None
        video_decoder: decoding.decoder.Decoder | None = None
        try:
            if audio_media_context is not None:
                audio_decoder = self._audio_decoder_factory(context=audio_media_context)
                audio_future = audio_decoder.prefill()
            if video_media_context is not None:
                video_decoder = self._video_decoder_factory(context=video_media_context)
                video_future = video_decoder.prefill()

            if audio_decoder is not None:
                executor.abort_aware_wait_for_future(audio_future)
                if audio_future.stage != Task.Stage.FINISHED_CLEAN:
                    executor.abort()
            if video_decoder is not None:
                executor.abort_aware_wait_for_future(video_future)
                if video_future.stage != Task.Stage.FINISHED_CLEAN:
                    executor.abort()

            return (audio_decoder, video_decoder)

        except:
            if audio_decoder is not None:
                audio_decoder.kill()
            if video_decoder is not None:
                video_decoder.kill()
            raise

    def playback_toggle(self) -> None:
        self._add_player_task(
            PlayerTask(self.__thread__playback_toggle, id=PlayerTask.ID.PLAYBACK_TOGGLE)
        )

    def __thread__playback_toggle(self, executor: Task.Executor) -> None:
        if not self._clock_timer.is_initialized:
            logger.info("Cannot toggle playback (player is unintialized)")
            return

        if self._clock_timer.is_running:
            self.__thread__suspend(executor)

        else:
            self.__thread__resume(executor)

    def suspend(self) -> None:
        self._add_player_task(PlayerTask(self.__thread__suspend, id=PlayerTask.ID.SUSPEND))

    def __thread__suspend(self, executor: Task.Executor, *, finish_task: bool = True) -> None:
        logger.debug("Suspending...")
        try:
            self._clock_timer.suspend()
            audio_future = self._audio_player.suspend()
            video_future = self._video_player.suspend()

            executor.abort_aware_wait_for_future(audio_future)
            executor.abort_aware_wait_for_future(video_future)

            assert self._audio_player.state != PlayerState.PLAYING
            assert self._video_player.state != PlayerState.PLAYING

            logger.debug("Suspending... Successful")
            if finish_task:
                executor.finish()
        except:
            logger.debug("Suspending... Failed")
            raise

    def resume(self) -> None:
        self._add_player_task(PlayerTask(self.__thread__resume, id=PlayerTask.ID.RESUME))

    def __thread__resume(self, executor: Task.Executor, finish_task: bool = True) -> None:
        logger.debug("Resuming...")
        try:
            self._clock_timer.resume()

            audio_future = self._audio_player.resume()
            executor.abort_aware_wait_for_future(audio_future)
            video_future = self._video_player.resume()
            executor.abort_aware_wait_for_future(video_future)

            if self._audio_player.is_initialized:
                if self._audio_player.reached_eof:
                    logger.info("Resuming... Failed (EOF)")
                    executor.abort()
                else:
                    assert audio_future.stage == Task.Stage.FINISHED_CLEAN

            if self._video_player.is_initialized:
                if self._video_player.reached_eof:
                    logger.info("Resuming... Failed (EOF)")
                    executor.abort()
                else:
                    assert video_future.stage == Task.Stage.FINISHED_CLEAN

            logger.debug("Resuming... Successful")
            if finish_task:
                executor.finish()
        except:
            logger.debug("Resuming... Failed")
            raise

    def seek_backward(self) -> None:
        self._seek(-SEEK_TIME)

    def seek_forward(self) -> None:
        self._seek(SEEK_TIME)

    def _seek(self, time_change: float):
        self._add_player_task(
            PlayerTask(
                lambda executor: self.__thread__seek(executor, time_change), id=PlayerTask.ID.SEEK
            )
        )

    def __thread__seek(self, executor: Task.Executor, time_change: float):
        if not self._clock_timer.is_initialized:
            return

        playing = self._clock_timer.is_running
        logger.debug("Seeking...")

        if self._audio_player.is_initialized:
            current_timepoint = self._audio_player.current_timepoint()
        else:
            current_timepoint = self._clock_timer.current_timepoint()

        next_timepoint = max(0, current_timepoint + time_change)

        try:
            self.__thread__suspend(executor, finish_task=False)

            self._clock_timer.seek(next_timepoint)

            # TODO: assure `next_timepoint` is in the scope (abort-aware wait)
            next_timepoint__source = self._timeline.unmap_timepoint_to_source(next_timepoint)
            assert next_timepoint__source is not None

            audio_future = self._audio_player.seek(next_timepoint__source)
            video_future = self._video_player.seek(next_timepoint__source)

            executor.abort_aware_wait_for_future(audio_future)
            executor.abort_aware_wait_for_future(video_future)

            if self._audio_player.reached_eof or self._video_player.reached_eof:
                logger.info("Seeking... Failed (EOF)")
                executor.abort()

            if self._audio_player.is_initialized:
                assert audio_future.stage == Task.Stage.FINISHED_CLEAN

            if self._video_player.is_initialized:
                assert video_future.stage == Task.Stage.FINISHED_CLEAN

            if playing:
                self.__thread__resume(executor, finish_task=False)

            with executor.finish_context:
                logger.debug("Seeking... Successful")

        except Task.Abort:
            logger.debug("Seeking... Aborted")
            # undo
            self._clock_timer.suspend()
            self._clock_timer.seek(timepoint=current_timepoint)
            if playing:
                self._clock_timer.resume()
                audio_future = self._audio_player.resume()
                video_future = self._video_player.resume()
            raise
        except:
            logger.debug("Seeking... Failed")
            raise

    def __thread(self) -> None:
        while True:
            try:
                self._tasks.run_all(timeout=None)
            except MediaPlayer.KillTask as kill_task:
                if kill_task.execute_and_finish(self.__thread__kill):
                    break
            except Exception:
                logger.exception("Task crashed with the following exception:")

    def __thread__kill(self) -> None:
        logger.info("Killed by a task")
        self._tasks.clear(abort_current_task=False)

    def _add_player_task(self, task: PlayerTask) -> None:
        logger.debug("Scheduling a task...", details=task)
        self._tasks.add_task(task, apply_invalidation_rules=True)
        logger.debug("Scheduling a task... Done", details=task)
