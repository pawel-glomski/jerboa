import sys
from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

from PySide6 import QtWidgets as QtW

from jerboa import core
from jerboa import analysis
from jerboa import media
from jerboa import gui


class Container(containers.DeclarativeContainer):
    # config = providers.Configuration()

    wiring_config = containers.WiringConfiguration(
        modules=[__name__],
    )

    qt_app = providers.Singleton(QtW.QApplication, [])

    # ------------------------------------------ Signals ----------------------------------------- #

    media_source_selected_signal = providers.Singleton(gui.core.signal.QtSignal, "media_source")
    ready_to_play_signal = providers.Singleton(gui.core.signal.QtSignal, "media_source")
    video_frame_update_signal = providers.Singleton(gui.core.signal.QtSignal, "frame")

    playback_toggle_signal = providers.Singleton(gui.core.signal.QtSignal)
    seek_backward_signal = providers.Singleton(gui.core.signal.QtSignal)
    seek_forward_signal = providers.Singleton(gui.core.signal.QtSignal)

    audio_output_devices_changed_signal = providers.Singleton(gui.core.signal.QtSignal)
    current_audio_output_device_changed_signal = providers.Singleton(gui.core.signal.QtSignal)

    analysis_algorithm_registered_signal = providers.Singleton(
        gui.core.signal.QtSignal, "algorithm"
    )
    analysis_algorithm_selected_signal = providers.Singleton(gui.core.signal.QtSignal, "algorithm")

    # -------------------------------------- Multithreading -------------------------------------- #

    thread_spawner = providers.Singleton(
        gui.core.multithreading.QtThreadSpawner
        # core.multithreading.PyThreadSpawner
    )
    thread_pool = providers.Singleton(
        # gui.core.multithreading.QtThreadPool,
        core.multithreading.PyThreadPool,
        workers=8,
    )

    # ----------------------------------------- Timeline ----------------------------------------- #

    timeline = providers.Singleton(
        core.timeline.FragmentedTimeline,
        # init_sections=[core.timeline.TMSection(0, float("inf"), 1)],
        init_sections=[
            core.timeline.TMSection(i * 3, i * 3 + 3, (2 - (i % 3)) / 2) for i in range(1000)
        ],
    )

    # ------------------------------------- Analysis Manager ------------------------------------- #

    analysis_algorithm_registry = providers.Singleton(
        analysis.registry.AlgorithmRegistry,
        analysis_algorithm_registered_signal=analysis_algorithm_registered_signal,
    )

    analysis_manager = providers.Singleton(analysis.manager.AnalysisManager)

    # --------------------------------------- Media player --------------------------------------- #

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
        audio_decoder_factory=providers.Factory(
            media.player.decoding.decoder.create_audio_decoder,
            thread_spawner=thread_spawner,
        ).provider,
        video_decoder_factory=providers.Factory(
            media.player.decoding.decoder.create_video_decoder,
            thread_spawner=thread_spawner,
        ).provider,
        timeline=timeline,
        thread_pool=thread_pool,
        thread_spawner=thread_spawner,
        fatal_error_signal=providers.Factory(gui.core.signal.QtSignal),
        ready_to_play_signal=ready_to_play_signal,
    )

    # -------------------------------------------- GUI ------------------------------------------- #

    gui_container = providers.Container(
        gui.container.Container,
        qt_app=qt_app,
        thread_pool=thread_pool,
        media_source_selected_signal=media_source_selected_signal,
        ready_to_play_signal=ready_to_play_signal,
        playback_toggle_signal=playback_toggle_signal,
        seek_backward_signal=seek_backward_signal,
        seek_forward_signal=seek_forward_signal,
        video_frame_update_signal=video_frame_update_signal,
        analysis_algorithm_selected_signal=analysis_algorithm_selected_signal,
        analysis_algorithm_registered_signal=analysis_algorithm_registered_signal,
    )


def main():
    dependencies_container = Container()
    dependencies_container.wire()
    dependencies_container.gui_container().wire()

    connect_signals()

    sys.exit(gui.container.run())


if __name__ == "__main__":
    main()


@inject
def connect_signals(
    media_source_selected: core.signal.Signal = Provide[Container.media_source_selected_signal],
    playback_toggle: core.signal.Signal = Provide[Container.playback_toggle_signal],
    seek_backward: core.signal.Signal = Provide[Container.seek_backward_signal],
    seek_forward: core.signal.Signal = Provide[Container.seek_forward_signal],
    media_player: media.player.media_player.MediaPlayer = Provide[Container.media_player],
) -> None:
    media_source_selected.connect(media_player.initialize)
    playback_toggle.connect(media_player.playback_toggle)
    seek_backward.connect(media_player.seek_backward)
    seek_forward.connect(media_player.seek_forward)


@inject
def register_analysis_algorithms(
    analysis_algorithm_registry: analysis.registry.AlgorithmRegistry = Provide[
        Container.analysis_algorithm_registry
    ],
) -> None:
    analysis_algorithm_registry.register_algorithm(analysis.algorithms.silence_remover.Algorithm)
    analysis_algorithm_registry.register_algorithm(analysis.algorithms.redundancy_remover.Algorithm)
