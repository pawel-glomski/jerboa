import sys

from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

from jerboa import gui
from jerboa.core.signal import Signal
from jerboa.core.file import JbPath, PathProcessor
from jerboa.media.source import MediaSource
from jerboa.media.recognizer import MediaSourceRecognizer
from jerboa.media.player.audio_player import AudioPlayer
from jerboa.media.player.video_player import VideoPlayer, JbVideoFrame
from jerboa.media.player.media_player import MediaPlayer

from jerboa.core.multithreading import PyThreadPool, PyThreadSpawner


class Container(containers.DeclarativeContainer):
    # config = providers.Configuration()

    # ---------------------------------------------------------------------------- #
    #                                   Resources                                  #
    # ---------------------------------------------------------------------------- #

    # this has to be created before any gui element, thus it is a resource initialized with
    # init_resources() call below
    gui_app = providers.Resource(gui.core.GUIApp)

    # ---------------------------------------------------------------------------- #
    #                                     Core                                     #
    # ---------------------------------------------------------------------------- #

    # ---------------------------------- signals --------------------------------- #

    media_source_selected_signal = providers.Singleton(
        gui.core.GUISignal,
        MediaSource,
    )

    media_player_start_signal = providers.Singleton(gui.core.GUISignal)
    media_player_resume_signal = providers.Singleton(gui.core.GUISignal)
    media_player_pause_signal = providers.Singleton(gui.core.GUISignal)

    # ------------------------------ Multithreading ------------------------------ #

    thread_spawner = providers.Singleton(PyThreadSpawner)  # gui.core.GUIThreadSpawner)
    thread_pool = providers.Singleton(
        PyThreadPool,  # gui.core.GUIThreadPool
        workers=8,
    )

    # ------------------------------- media player ------------------------------- #

    media_player = providers.Singleton(
        MediaPlayer,
        audio_player=providers.Singleton(
            AudioPlayer,
        ),
        video_player=providers.Singleton(
            VideoPlayer,
            video_frame_update_signal=providers.Factory(
                gui.core.GUISignal,
                JbVideoFrame,
            ),
            thread_spawner=thread_spawner,
        ),
        thread_pool=thread_pool,
        ready_to_play_signal=providers.Factory(
            Signal,
        ),
        media_source_selected_signal=media_source_selected_signal,
    )

    # ---------------------------------------------------------------------------- #
    #                                      gui                                     #
    # ---------------------------------------------------------------------------- #

    gui_main_window = providers.Singleton(
        gui.core.MainWindow,
        min_size=(640, 360),
        relative_size=(0.5, 0.5),
    )

    # ------------------------------- gui resources ------------------------------ #

    gui_resource_loading_spinner = providers.Singleton(
        gui.resources.common.LoadingSpinner,
        path=":/loading_spinner.gif",
        size=(30, 30),
    )

    # ----------------------- media source selection dialog ---------------------- #

    gui_media_source_selection_dialog = providers.Singleton(
        gui.media_source_selection.dialog.MediaSourceSelectionDialog,
        min_size=(800, 400),
        hint_text="Select a local file or enter the URL of a recording",
        loading_spinner_movie=gui_resource_loading_spinner,
        path_selector=providers.Factory(
            gui.common.file.PathSelector,
            path_processor=providers.Factory(
                PathProcessor,
                invalid_path_msg="Path '{path}' has invalid format",
                local_file_not_found_msg="Local file '{path}' not found",
                not_a_file_msg="'{path}' is not a file",
            ),
            select_local_file_button_text="Select a local file",
            placeholder_text="Media file path (or URL)...",
            apply_button_text="Apply",
            local_file_extension_filter="Media files (*.mp3 *.wav *.ogg *.flac *.mp4 *.avi *.mkv *.mov);; All files (*)",
            path_invalid_signal=providers.Factory(
                gui.core.GUISignal,
                str,
            ),
            path_selected_signal=providers.Factory(
                gui.core.GUISignal,
                JbPath,
            ),
            path_modified_signal=providers.Factory(
                gui.core.GUISignal,
            ),
        ),
        media_source_resolver=providers.Factory(
            gui.media_source_selection.resolver.MediaSourceResolver,
            title_text="Title:",
            audio_variant_selector=providers.Factory(
                gui.media_source_selection.resolver.StreamVariantSelector,
                label_text="Selected audio quality:",
            ),
            video_variant_selector=providers.Factory(
                gui.media_source_selection.resolver.StreamVariantSelector,
                label_text="Selected video quality:",
            ),
        ),
        button_box=providers.Factory(
            gui.common.button_box.RejectAcceptDialogButtonBox,
            reject_button="cancel",
            accept_button="ok",
            icons=False,
            accept_disabled_by_default=True,
        ),
        recognizer=providers.Factory(
            MediaSourceRecognizer,
            recognition_finished_signal=providers.Factory(
                gui.core.GUISignal,
                object,  # accepts a callable
            ),
            thread_pool=thread_pool,
        ),
        media_source_selected_signal=media_source_selected_signal,
        parent=gui_main_window,
    )

    # --------------------------------- menu bar --------------------------------- #

    gui_menu_bar_file_open = providers.Singleton(
        gui.menu_bar.MenuAction,
        name="Open",
        signal=providers.Factory(
            Signal,
            subscribers=providers.List(
                gui_media_source_selection_dialog.provided.open_clean,
            ),
        ),
    )
    gui_menu_bar_file = providers.Singleton(
        gui.menu_bar.Menu,
        name="File",
        actions=providers.List(
            gui_menu_bar_file_open,
        ),
    )
    gui_menu_bar = providers.Singleton(
        gui.menu_bar.MenuBar,
        menus=providers.List(
            gui_menu_bar_file,
        ),
    )

    # -------------------------------- player view ------------------------------- #

    gui_player_view_canvas = providers.Singleton(
        gui.player_view.Canvas,
    )
    gui_player_view_timeline = providers.Singleton(
        gui.player_view.Timeline,
        # playback_update_signal=gui_media_player.playback_update
    )

    player_view = providers.Singleton(
        gui.player_view.PlayerView,
        canvas=gui_player_view_canvas,
        timeline=gui_player_view_timeline,
        media_source_selected_signal=media_source_selected_signal,
        video_frame_update_signal=media_player.provided.video_frame_update_signal,
    )

    # ----------------------------- main view stack ---------------------------- #

    gui_main_widget = providers.Singleton(
        gui.main_view_stack.MainViewStack,
        player_view=player_view,
        # settings_view=settings_view,
        # plugins_view=plugins_view,
    )

    # -------------------------------- jerboa gui -------------------------------- #

    gui_jerboa = providers.Singleton(
        gui.core.JerboaGUI,
        gui_app=gui_app,
        main_window=gui_main_window,
        menu_bar=gui_menu_bar,
        main_widget=gui_main_widget,
        # status_bar=gui_status_bar,
    )


@inject
def main(ui: gui.core.JerboaGUI = Provide[Container.gui_jerboa]):
    sys.exit(ui.run_event_loop())


if __name__ == "__main__":
    _dependencies_container = Container()
    _dependencies_container.init_resources()
    _dependencies_container.wire(modules=[__name__])

    main()
