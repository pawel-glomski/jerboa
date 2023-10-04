from concurrent.futures import ThreadPoolExecutor

from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool
from jerboa.core.timeline import FragmentedTimeline, TMSection
from jerboa.media.core import MediaType, AudioConfig, VideoConfig
from jerboa.media.source import MediaSource
from jerboa.media.player.decoding.timeline_decoder import TimelineDecoder
from jerboa.media.player.decoding.skipping_decoder import SkippingDecoder, SimpleDecoder
from .audio_player import AudioPlayer
from .video_player import VideoPlayer

# as long as all componenets are known at "compile-time", it can be a constant global
# (this is not the case with the audio config, which is platform/audio device dependent)
VIDEO_CONFIG = VideoConfig(
    format=VideoConfig.PixelFormat.RGBA8888,
)

# TODO: remove me when the analysis module is integrated
DBG_TIMELINE = FragmentedTimeline(
    TMSection(0, 5, modifier=0.5),
    TMSection(5, 15, modifier=0.0),
    TMSection(15, float("inf"), modifier=1.5),
)


class MediaPlayer:
    def __init__(
        self,
        audio_player: AudioPlayer,
        video_player: VideoPlayer,
        thread_pool: ThreadPool,
        ready_to_play_signal: Signal,
        media_source_selected_signal: Signal,
    ):
        self._audio_player = audio_player
        self._video_player = video_player
        self._thread_pool = thread_pool
        self._ready_to_play_signal = ready_to_play_signal
        self._current_media_source: MediaSource | None = None

        media_source_selected_signal.connect(self._on_media_source_selected)
        video_player.player_stalled_signal.connect()

    @property
    def ready_to_play_signal(self) -> Signal:
        return self._ready_to_play_signal

    @property
    def video_frame_update_signal(self) -> Signal:
        return self._video_player.video_frame_update_signal

    def _on_media_source_selected(self, media_source: MediaSource):
        assert media_source.is_resolved

        # self._audio_player.stop()
        self._video_player.stop()

        def prepare_players():
            audio_decoder_future = video_decoder_future = None

            with ThreadPoolExecutor(max_workers=2) as executor:
                if media_source.audio.is_available:
                    audio_decoder_future = executor.submit(
                        self._get_audio_decoder,
                        path=media_source.audio.selected_variant_group[0].path,
                    )
                if media_source.video.is_available:
                    video_decoder_future = executor.submit(
                        self._get_video_decoder,
                        path=media_source.audio.selected_variant_group[0].path,
                    )

            if audio_decoder_future is not None:
                self._audio_player.start(audio_decoder_future.result())
            if video_decoder_future is not None:
                self._video_player.start(video_decoder_future.result())

            self._ready_to_play_signal.emit()

        self._thread_pool.start(prepare_players)

    def _get_audio_decoder(self, path: str) -> TimelineDecoder:
        return TimelineDecoder(
            skipping_decoder=SkippingDecoder(
                SimpleDecoder(
                    path,
                    media_type=MediaType.AUDIO,
                    stream_idx=0,
                )
            ),
            dst_media_config=AudioConfig(...),
            init_timeline=DBG_TIMELINE,
        )

    def _get_video_decoder(self, path: str) -> TimelineDecoder:
        return TimelineDecoder(
            skipping_decoder=SkippingDecoder(
                SimpleDecoder(
                    path,
                    MediaType.VIDEO,
                    stream_idx=0,
                )
            ),
            dst_media_config=VIDEO_CONFIG,
            init_timeline=DBG_TIMELINE,
        )
