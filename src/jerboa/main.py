import sys
from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

from PySide6 import QtWidgets as QtW

from jerboa import gui
from jerboa import media
from jerboa import core


class Container(containers.DeclarativeContainer):
    # config = providers.Configuration()

    wiring_config = containers.WiringConfiguration(
        modules=[__name__],
    )

    qt_app = providers.Singleton(QtW.QApplication, [])

    # ---------------------------------- Signals --------------------------------- #

    media_source_selected_signal = providers.Singleton(gui.core.signal.QtSignal, "media_source")
    ready_to_play_signal = providers.Singleton(gui.core.signal.QtSignal, "media_source")
    video_frame_update_signal = providers.Singleton(gui.core.signal.QtSignal, "frame")

    # media_player_start_signal = providers.Singleton(gui.core.signal.QtSignal)
    # media_player_resume_signal = providers.Singleton(gui.core.signal.QtSignal)
    # media_player_pause_signal = providers.Singleton(gui.core.signal.QtSignal)

    audio_output_devices_changed_signal = providers.Singleton(gui.core.signal.QtSignal)
    current_audio_output_device_changed_signal = providers.Singleton(gui.core.signal.QtSignal)

    # ------------------------------ Multithreading ------------------------------ #

    thread_spawner = providers.Singleton(
        # gui.core.multithreading.QtThreadSpawner
        core.multithreading.PyThreadSpawner
    )
    thread_pool = providers.Singleton(
        # gui.core.multithreading.QtThreadPool,
        core.multithreading.PyThreadPool,
        workers=8,
    )

    # ------------------------------- Media player ------------------------------- #

    audio_manager = providers.Singleton(
        media.player.audio_player.AudioManager,
        app=qt_app,
        output_devices_changed_signal=audio_output_devices_changed_signal,
        current_output_device_changed_signal=current_audio_output_device_changed_signal,
    )

    audio_player = providers.Singleton(
        media.player.audio_player.AudioPlayer,
        audio_manager=audio_manager,
        decoder=providers.Factory(
            media.player.audio_player.JbDecoder,
            decoding_pipeline=media.player.decoding.decoder.create_decoding_pipeline(
                media.core.MediaType.AUDIO
            ),
            thread_spawner=thread_spawner,
        ),
        shutdown_signal=providers.Factory(gui.core.signal.QtSignal, "lock"),
        suspend_signal=providers.Factory(gui.core.signal.QtSignal),
        resume_signal=providers.Factory(gui.core.signal.QtSignal),
        seek_signal=providers.Factory(gui.core.signal.QtSignal, "timepoint"),
    )

    video_player = providers.Singleton(
        media.player.video_player.VideoPlayer,
        decoder=providers.Factory(
            media.player.video_player.JbDecoder,
            decoding_pipeline=media.player.decoding.decoder.create_decoding_pipeline(
                media.core.MediaType.VIDEO
            ),
            thread_spawner=thread_spawner,
        ),
        thread_spawner=thread_spawner,
        player_stalled_signal=providers.Factory(gui.core.signal.QtSignal),
        video_frame_update_signal=video_frame_update_signal,
    )

    media_player = providers.Singleton(
        media.player.media_player.MediaPlayer,
        audio_player=audio_player,
        video_player=video_player,
        thread_pool=thread_pool,
        ready_to_play_signal=ready_to_play_signal,
        # playback_stalled_signal=...
    )

    # ------------------------------------ GUI ----------------------------------- #

    gui_container = providers.Container(
        gui.container.Container,
        qt_app=qt_app,
        thread_pool=thread_pool,
        media_source_selected_signal=media_source_selected_signal,
        ready_to_play_signal=ready_to_play_signal,
        video_frame_update_signal=video_frame_update_signal,
    )


@inject
def connect_signals(
    media_source_selected_signal: core.signal.Signal = Provide[
        Container.media_source_selected_signal
    ],
    media_player: media.player.media_player.MediaPlayer = Provide[Container.media_player],
):
    media_source_selected_signal.connect(media_player.start)


if __name__ == "__main__":
    _dependencies_container = Container()
    _dependencies_container.wire()
    _dependencies_container.gui_container().wire()

    connect_signals()
    gui.container.connect_signals()

    sys.exit(gui.container.run())
