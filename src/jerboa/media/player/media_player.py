from threading import Lock
from concurrent.futures import ThreadPoolExecutor, Future

from jerboa.core.logger import logger
from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool
from jerboa.media.source import MediaSource
from .audio_player import AudioPlayer
from .video_player import VideoPlayer
from .timer import ClockPlaybackTimer


PLAYER_PREP_TIMEOUT = 10  # in seconds


class MediaPlayer:
    def __init__(
        self,
        audio_player: AudioPlayer,
        video_player: VideoPlayer,
        thread_pool: ThreadPool,
        ready_to_play_signal: Signal,
    ):
        self._audio_player = audio_player
        self._video_player = video_player
        self._thread_pool = thread_pool
        self._ready_to_play_signal = ready_to_play_signal
        self._current_media_source: MediaSource | None = None

        self._clock_timer = ClockPlaybackTimer()

        video_player.player_stalled_signal.connect(self._on_player_stalled)

        self._mutex = Lock()

    @property
    def ready_to_play_signal(self) -> Signal:
        return self._ready_to_play_signal

    @property
    def video_frame_update_signal(self) -> Signal:
        return self._video_player.video_frame_update_signal

    def start(self, media_source: MediaSource):
        assert media_source.audio.is_available or media_source.video.is_available
        assert media_source.is_resolved

        logger.info(f"MediaPlayer: Preparing to play '{media_source.title}'")

        self._audio_player.shutdown()
        self._video_player.shutdown()
        self._clock_timer.reset()

        def prepare_players():
            # we need a mutex here, to make sure only one thread interacts with media players at a
            # time - this should never really happen during a normal use case
            if self._mutex.locked():
                logger.warning(
                    "The media player is still preparing previous media. "
                    "We must wait before proceeding."
                )

            # TODO: this should also use the global ThreadPool
            with self._mutex, ThreadPoolExecutor(max_workers=2) as executor:
                players_future = list[tuple[AudioPlayer | VideoPlayer, Future]]()
                if media_source.audio.is_available:
                    players_future.append(
                        (
                            self._audio_player,
                            executor.submit(
                                self._audio_player.startup,
                                source=media_source.audio.selected_variant_group[0],
                            ),
                        )
                    )
                if media_source.video.is_available:
                    video_timer = self._clock_timer
                    if media_source.audio.is_available:
                        video_timer = self._audio_player
                    players_future.append(
                        (
                            self._video_player,
                            executor.submit(
                                self._video_player.startup,
                                source=media_source.video.selected_variant_group[0],
                                timer=video_timer,
                            ),
                        )
                    )

                for player, future in players_future:
                    try:
                        exception = future.exception(timeout=PLAYER_PREP_TIMEOUT)
                    except TimeoutError as exc:
                        exception = exc

                    if exception is not None:
                        logger.error(
                            f"MediaPlayer: Failed to start {type(player).__name__} "
                            f"to play '{media_source.title}'"
                        )
                        # in case any of the players succeeded, shut it down
                        # (this is not really necessary, but it can save some memory and CPU usage)
                        self._video_player.shutdown()
                        self._audio_player.shutdown()
                        raise exception

                # startup succeeded
                self._clock_timer.resume()
                self._audio_player.resume()
                self._video_player.resume()

                logger.info(f"MediaPlayer: Ready to play '{media_source.title}'")
                self._ready_to_play_signal.emit()

        self._thread_pool.start(prepare_players)

    def _on_player_stalled(self) -> None:
        ...
