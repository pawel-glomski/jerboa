from threading import Lock

from jerboa.core.logger import logger
from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool
from jerboa.media.source import MediaSource
from .audio_player import AudioPlayer
from .video_player import VideoPlayer
from .state import PlayerState
from .clock import SynchronizationClock


PLAYER_PREP_TIMEOUT = 5  # in seconds


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

        self._sync_clock = SynchronizationClock()

        video_player.player_stalled_signal.connect(self._on_player_stalled)

        self._mutex = Lock()

    @property
    def ready_to_play_signal(self) -> Signal:
        return self._ready_to_play_signal

    @property
    def video_frame_update_signal(self) -> Signal:
        return self._video_player.video_frame_update_signal

    def start(self, media_source: MediaSource):
        assert media_source.is_resolved

        logger.info(f'MediaPlayer: Preparing to play "{media_source.title}"')

        self._audio_player.stop()
        self._video_player.stop()
        self._sync_clock.stop()

        def prepare_players():
            # we need a mutex here, to make sure only one thread interacts with media players at a
            # time - this should never really happen during a normal use case
            if self._mutex.locked():
                logger.warning(
                    "The media player is still preparing previous media. "
                    "We must wait before proceeding."
                )

            players = list[AudioPlayer | VideoPlayer]()
            with self._mutex:
                if media_source.audio.is_available:
                    pass
                    # self._audio_player.start(media_source.audio.selected_variant_group[0])
                    # players.append(self._audio_player)
                if media_source.video.is_available:
                    sync_clock = self._sync_clock
                    # if media_source.audio.is_available:
                    #     sync_clock = self._audio_player
                    self._video_player.start(
                        media_source.video.selected_variant_group[0], sync_clock
                    )
                    players.append(self._video_player)

            for player in players:
                player.wait_for_state(
                    states=[PlayerState.SUSPENDED, PlayerState.STOPPED_ON_ERROR],
                    timeout=PLAYER_PREP_TIMEOUT,
                )
                if player.state == PlayerState.STOPPED_ON_ERROR:
                    logger.error(f"MediaPlayer: Failed to play '{media_source.title}'")
                    break
            else:
                self._sync_clock.start()
                self._video_player.resume()

                logger.info(f'MediaPlayer: Ready to play "{media_source.title}"')
                self._ready_to_play_signal.emit()

        self._thread_pool.start(prepare_players)

    def _on_player_stalled(self) -> None:
        ...
