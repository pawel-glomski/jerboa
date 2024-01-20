# Jerboa - AI-powered media player
# Copyright (C) 2023 Paweł Głomski

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import multiprocessing as mp

if __name__ == "__main__":
    mp.set_start_method("spawn")

# pylint: disable=wrong-import-position
import sys
from dependency_injector import containers, providers

from PySide6 import QtWidgets as QtW

from jerboa import core
from jerboa import analysis
from jerboa import media
from jerboa import gui
from jerboa.settings import Settings
from jerboa.log import logger


class Container(containers.DeclarativeContainer):
    settings = providers.Singleton(Settings.load)

    qt_app = providers.Singleton(QtW.QApplication, [])

    # ------------------------------------------ Signals ----------------------------------------- #

    show_error_message_signal = providers.Singleton(
        gui.core.signal.QtSignal, "message", "title", "parent"  # "title" and "parent" are optional
    )

    media_source_selected_signal = providers.Singleton(gui.core.signal.QtSignal, "media_source")
    ready_to_play_signal = providers.Singleton(gui.core.signal.QtSignal)
    video_frame_update_signal = providers.Singleton(gui.core.signal.QtSignal, "frame")

    playback_toggle_signal = providers.Singleton(gui.core.signal.QtSignal)
    seek_backward_signal = providers.Singleton(gui.core.signal.QtSignal)
    seek_forward_signal = providers.Singleton(gui.core.signal.QtSignal)

    audio_output_devices_changed_signal = providers.Singleton(gui.core.signal.QtSignal)
    current_audio_output_device_changed_signal = providers.Singleton(gui.core.signal.QtSignal)

    analysis_alg_registered_signal = providers.Singleton(gui.core.signal.QtSignal, "algorithm")
    analysis_alg_env_prep_signal = providers.Singleton(
        gui.core.signal.QtSignal, "algorithm", "env_parameters"
    )
    analysis_alg_env_prep_task_started_signal = providers.Singleton(
        gui.core.signal.QtSignal, "algorithm", "task_future"
    )
    analysis_alg_env_prep_progress_signal = providers.Singleton(
        gui.core.signal.QtSignal, "progress", "message"
    )
    analysis_alg_selected_signal = providers.Singleton(gui.core.signal.QtSignal, "algorithm")
    analysis_alg_run_signal = providers.Singleton(gui.core.signal.QtSignal, "alg_desc")

    analysis_run_created_signal = providers.Singleton(
        gui.core.signal.QtSignal, "run_id", "algorithm"
    )

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
        init_sections=[core.timeline.TMSection(0, float("inf"), 1)],
        # init_sections=[
        #     core.timeline.TMSection(i * 3, i * 3 + 3, (2 - (i % 3)) / 2) for i in range(1000)
        # ],
    )

    # ------------------------------------- AlgorithmRegistry ------------------------------------ #

    # TODO(?): refactor out the environment preparation to a separate class
    analysis_alg_registry = providers.Singleton(
        analysis.registry.AlgorithmRegistry,
        settings=settings,
        thread_pool=thread_pool,
        prev_task_still_running_error_msg="Previous task is still running",
        alg_env_prep_error_message=(
            "An error occurred while setting up the environment for an analysis algorithm"
        ),
        alg_registered_signal=analysis_alg_registered_signal,
        alg_env_prep_task_started_signal=analysis_alg_env_prep_task_started_signal,
        alg_env_prep_progress_signal=analysis_alg_env_prep_progress_signal,
        show_error_message_signal=show_error_message_signal,
    )

    # -------------------------------------- AnalysisManager ------------------------------------- #

    analysis_manager = providers.Singleton(
        analysis.run.manager.AnalysisManager,
        error_message_title="Analysis Management Process Error",
        show_error_message_signal=show_error_message_signal,
        run_created_signal=analysis_run_created_signal,
    )

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
        show_error_message_signal=show_error_message_signal,
        media_source_selected_signal=media_source_selected_signal,
        playback_toggle_signal=playback_toggle_signal,
        seek_backward_signal=seek_backward_signal,
        seek_forward_signal=seek_forward_signal,
        analysis_alg_env_prep_signal=analysis_alg_env_prep_signal,
        analysis_alg_selected_signal=analysis_alg_selected_signal,
        analysis_alg_run_signal=analysis_alg_run_signal,
    )


def main():
    logger.initialize(name="Main")

    core_c = Container()
    connect_signals(core_c)

    core_c.analysis_alg_registry().register_all()

    sys.exit(run_gui(core_c.gui_container()))


def connect_signals(core_c: Container) -> None:
    gui_c = core_c.gui_container()

    # ----------------------------------- media player signals ----------------------------------- #

    core_c.media_source_selected_signal().connect(core_c.media_player().initialize)
    core_c.playback_toggle_signal().connect(core_c.media_player().playback_toggle)
    core_c.seek_backward_signal().connect(core_c.media_player().seek_backward)
    core_c.seek_forward_signal().connect(core_c.media_player().seek_forward)

    core_c.ready_to_play_signal().connect(gui_c.jb_main_page_stack().show_player_page)
    core_c.video_frame_update_signal().connect(gui_c.player_page_canvas().update_frame)

    # -------------------------------- algorithm registry signals -------------------------------- #

    core_c.analysis_alg_registered_signal().connect(
        gui_c.analysis_alg_registry_dialog().add_algorithm
    )
    core_c.analysis_alg_env_prep_signal().connect(
        core_c.analysis_alg_registry().prepare_environment
    )
    core_c.analysis_alg_env_prep_task_started_signal().connect(
        gui_c.analysis_alg_registry_dialog().open_env_prep_progress_dialog
    )
    core_c.analysis_alg_env_prep_progress_signal().connect(
        gui_c.analysis_alg_registry_dialog().update_env_prep_progress_dialog
    )

    # ------------------------------------- analysis manager ------------------------------------- #

    core_c.analysis_alg_run_signal().connect(core_c.analysis_manager().run_algorithm)

    # ------------------------------- error message dialog signals ------------------------------- #

    core_c.show_error_message_signal().connect(gui_c.error_message_dialog_factory().open)

    # ------------------------------------- menu bar signals ------------------------------------- #

    gui_c.menu_bar_file_open().signal.connect(gui_c.media_source_selection_dialog().open_clean)
    gui_c.menu_bar_algorithms().signal.connect(gui_c.analysis_alg_registry_dialog().open)


def run_gui(gui_c: gui.container.Container) -> int:
    qt_app = gui_c.qt_app()
    jb_main_window = gui_c.jb_main_window()

    # TODO: Just define a dark/light palettes. Using system's pallete is too unpredicable
    palette = qt_app.palette()
    palette.setColor(palette.ColorRole.ToolTipBase, palette.color(palette.ColorRole.Window))
    palette.setColor(
        palette.ColorRole.ToolTipText, palette.color(palette.ColorRole.PlaceholderText)
    )
    # palette.setColor(
    #     palette.ColorGroup.Disabled,
    #     palette.ColorRole.Button,
    #     palette.color(palette.ColorRole.Button).darker(150),
    # )
    qt_app.setPalette(palette)

    jb_main_window.show()
    return qt_app.exec()


if __name__ == "__main__":
    main()
