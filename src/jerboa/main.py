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

    playback_toggle_signal = providers.Singleton(gui.core.signal.QtSignal)
    seek_backward_signal = providers.Singleton(gui.core.signal.QtSignal)
    seek_forward_signal = providers.Singleton(gui.core.signal.QtSignal)

    audio_output_devices_changed_signal = providers.Singleton(gui.core.signal.QtSignal)
    current_audio_output_device_changed_signal = providers.Singleton(gui.core.signal.QtSignal)

    # ------------------------------ Multithreading ------------------------------ #

    thread_spawner = providers.Singleton(
        gui.core.multithreading.QtThreadSpawner
        # core.multithreading.PyThreadSpawner
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
        thread_spawner=thread_spawner,
        output_devices_changed_signal=audio_output_devices_changed_signal,
        current_output_device_changed_signal=current_audio_output_device_changed_signal,
    )

    audio_player = providers.Singleton(
        media.player.audio_player.AudioPlayer,
        audio_manager=audio_manager,
        fatal_error_signal=providers.Factory(gui.core.signal.QtSignal),
        buffer_underrun_signal=providers.Factory(gui.core.signal.QtSignal),
        eof_signal=providers.Factory(gui.core.signal.QtSignal),
    )

    video_player = providers.Singleton(
        media.player.video_player.VideoPlayer,
        thread_spawner=thread_spawner,
        fatal_error_signal=providers.Factory(gui.core.signal.QtSignal),
        buffer_underrun_signal=providers.Factory(gui.core.signal.QtSignal),
        eof_signal=providers.Factory(gui.core.signal.QtSignal),
        video_frame_update_signal=video_frame_update_signal,
    )

    media_player = providers.Singleton(
        media.player.media_player.MediaPlayer,
        audio_player=audio_player,
        video_player=video_player,
        audio_decoding_pipeline_factory=providers.Factory(
            media.player.decoding.pipeline.create_audio_decoding_pipeline,
            thread_spawner=thread_spawner,
        ).provider,
        video_decoding_pipeline_factory=providers.Factory(
            media.player.decoding.pipeline.create_video_decoding_pipeline,
            thread_spawner=thread_spawner,
        ).provider,
        timeline=providers.Factory(
            core.timeline.FragmentedTimeline,
            init_sections=[core.timeline.TMSection(i, i + 0.5) for i in range(1000)],
        ),
        thread_pool=thread_pool,
        fatal_error_signal=providers.Factory(gui.core.signal.QtSignal),
        ready_to_play_signal=ready_to_play_signal,
    )

    # ------------------------------------ GUI ----------------------------------- #

    gui_container = providers.Container(
        gui.container.Container,
        qt_app=qt_app,
        thread_pool=thread_pool,
        media_source_selected_signal=media_source_selected_signal,
        ready_to_play_signal=ready_to_play_signal,
        playback_toggle_signal=playback_toggle_signal,
        video_frame_update_signal=video_frame_update_signal,
        seek_backward_signal=seek_backward_signal,
        seek_forward_signal=seek_forward_signal,
    )


@inject
def connect_signals(
    media_source_selected: core.signal.Signal = Provide[Container.media_source_selected_signal],
    playback_toggle: core.signal.Signal = Provide[Container.playback_toggle_signal],
    seek_backward: core.signal.Signal = Provide[Container.seek_backward_signal],
    seek_forward: core.signal.Signal = Provide[Container.seek_forward_signal],
    media_player: media.player.media_player.MediaPlayer = Provide[Container.media_player],
):
    media_source_selected.connect(media_player.initialize)
    playback_toggle.connect(media_player.playback_toggle)
    seek_backward.connect(media_player.seek_backward)
    seek_forward.connect(media_player.seek_forward)


if __name__ == "__main__":
    _dependencies_container = Container()
    _dependencies_container.wire()
    _dependencies_container.gui_container().wire()

    connect_signals()
    gui.container.connect_signals()

    sys.exit(gui.container.run())
