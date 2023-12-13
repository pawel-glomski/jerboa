from dependency_injector import containers, providers

import PySide6.QtWidgets as QtW

from jerboa.core.file import PathProcessor
from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool
from jerboa.media.recognizer import MediaSourceRecognizer

from .error_message_dialog import ErrorMessageDialogFactory
from .main_page_stack import MainPageStack
from .status_bar import StatusBar
from .main_window import MainWindow
from . import core
from . import common
from . import menu_bar
from . import player_page
from . import resources
from . import media_source_selection
from . import analysis_algorithm_selection
from . import analysis_algorithm_registry


class Container(containers.DeclarativeContainer):
    # --------------------------------------- Dependencies --------------------------------------- #

    qt_app = providers.Dependency(QtW.QApplication)
    thread_pool = providers.Dependency(ThreadPool)

    show_error_message_signal = providers.Dependency(Signal)

    media_source_selected_signal = providers.Dependency(Signal)
    playback_toggle_signal = providers.Dependency(Signal)
    seek_backward_signal = providers.Dependency(Signal)
    seek_forward_signal = providers.Dependency(Signal)

    analysis_alg_env_prep_signal = providers.Dependency(Signal)
    analysis_alg_selected_signal = providers.Dependency(Signal)

    # ----------------------------------------- Resources ---------------------------------------- #

    resource__loading_spinner_movie = providers.Singleton(
        resources.common.LoadingSpinner,
        path=":/loading_spinner.gif",
        size=(30, 30),
    )

    # ------------------------------------------ Palette ----------------------------------------- #

    # palette = providers.Singleton(
    #     Palette,
    #     app=qt_app,
    # )

    # ----------------------------------------- Menu bar ----------------------------------------- #

    menu_bar_file_open = providers.Singleton(
        menu_bar.MenuAction,
        name="Open",
        signal=providers.Factory(core.signal.QtSignal),
    )
    menu_bar_file = providers.Singleton(
        menu_bar.Menu,
        name="File",
        actions=providers.List(
            menu_bar_file_open,
        ),
    )

    menu_bar_algorithms = providers.Singleton(
        menu_bar.MenuAction,
        name="Algorithms",
        signal=providers.Factory(core.signal.QtSignal),
    )

    jb_menu_bar = providers.Singleton(
        menu_bar.MenuBar,
        menus=providers.List(
            menu_bar_file,
        ),
        actions=providers.List(
            menu_bar_algorithms,
        ),
    )

    # ---------------------------------------- Player page --------------------------------------- #

    player_page_canvas = providers.Singleton(player_page.Canvas, no_video_text="No video stream")
    player_page_timeline = providers.Singleton(
        player_page.Timeline,
        # playback_update_signal=media_player.playback_update
    )

    jb_player_page = providers.Singleton(
        player_page.PlayerPage,
        canvas=player_page_canvas,
        timeline=player_page_timeline,
        playback_toggle_signal=playback_toggle_signal,
        seek_backward_signal=seek_backward_signal,
        seek_forward_signal=seek_forward_signal,
    )

    # -------------------------------------- Main page stack ------------------------------------- #

    jb_main_page_stack = providers.Singleton(
        MainPageStack,
        player_page=jb_player_page,
        # settings_page=settings_page,
        # plugins_page=plugins_page,
    )

    # ---------------------------------------- Status bar ---------------------------------------- #

    jb_status_bar = providers.Singleton(
        StatusBar,
    )

    # ---------------------------------------- Main Window --------------------------------------- #

    jb_main_window = providers.Singleton(
        MainWindow,
        min_size=(640, 360),
        relative_size=(0.5, 0.5),
        menu_bar=jb_menu_bar,
        main_widget=jb_main_page_stack,
        status_bar=jb_status_bar,
    )

    # ----------------------------------- Error message dialog ----------------------------------- #

    error_message_dialog_factory = providers.Singleton(
        ErrorMessageDialogFactory,
        title="Error messsage",
        default_parent=jb_main_window,
    )

    # ------------------------------- Media source selection dialog ------------------------------ #

    media_source_selection_dialog = providers.Singleton(
        media_source_selection.dialog.Dialog,
        title="Select media file",
        min_size=(800, 400),
        path_selector=providers.Factory(
            common.file.PathSelector,
            path_processor=providers.Factory(
                PathProcessor,
                invalid_path_msg="Path '{path}' has invalid format",
                local_file_not_found_msg="Local file '{path}' not found",
                not_a_file_msg="'{path}' is not a file",
            ),
            select_local_file_button_text="Select a local file",
            placeholder_text="Media file path (or URL)...",
            apply_button_text="Apply",
            local_file_extension_filter=(
                "Media files (*.mp3 *.wav *.aac *.ogg *.flac "
                "*.mp4 *.avi *.mkv *.mov);; All files (*)"
            ),
            path_invalid_signal=providers.Factory(core.signal.QtSignal, "error_message"),
            path_selected_signal=providers.Factory(core.signal.QtSignal, "media_source_path"),
            path_modified_signal=providers.Factory(core.signal.QtSignal),
        ),
        page_stack=providers.Factory(common.page_stack.PageStack),
        hint_page=providers.Factory(
            common.page_stack.MessagePage,
            text="Select a local file or enter an URL",
        ),
        loading_spinner_page=providers.Factory(
            common.page_stack.LoadingSpinnerPage,
            loading_spinner_movie=resource__loading_spinner_movie,
        ),
        media_source_resolver=providers.Factory(
            media_source_selection.resolver.MediaSourceResolver,
            title_text="Title:",
            audio_variant_selector=providers.Factory(
                media_source_selection.resolver.StreamVariantSelector,
                label_text="Selected audio quality:",
            ),
            video_variant_selector=providers.Factory(
                media_source_selection.resolver.StreamVariantSelector,
                label_text="Selected video quality:",
            ),
        ),
        button_box=providers.Factory(common.button_box.RejectAcceptButtonBox),
        recognizer=providers.Factory(MediaSourceRecognizer, thread_pool=thread_pool),
        recognizer_success_signal=providers.Factory(core.signal.QtSignal, "media_source"),
        recognizer_failure_signal=providers.Factory(core.signal.QtSignal, "error_message"),
        media_source_selected_signal=media_source_selected_signal,
        show_error_message_signal=show_error_message_signal,
        parent=jb_main_window,
    )

    # -------------------------------- Analysis algorithm registry ------------------------------- #

    analysis_alg_registry_dialog = providers.Singleton(
        analysis_algorithm_registry.dialog.Dialog,
        title="Algorithm registry",
        min_size=(600, 400),
        name_column_header=providers.Factory(
            analysis_algorithm_registry.dialog.ColumnHeader, "Algorithm"
        ),
        description_column_header=providers.Factory(
            analysis_algorithm_registry.dialog.ColumnHeader, "Description"
        ),
        environment_column_header=providers.Factory(
            analysis_algorithm_registry.dialog.ColumnHeader, "Env"
        ),
        env_config_dialog_factory=providers.Factory(
            analysis_algorithm_registry.env_config_dialog.Dialog,
            title="Environment configuration",
            min_size=(300, 100),
            parameter_collection=providers.Factory(
                common.parameter.ParameterCollection,
                no_params_text="No parameters",
            ),
            button_box=providers.Factory(
                common.button_box.RejectAcceptButtonBox,
                is_accept_button_disabled_by_default=False,
            ),
        ).provider,
        env_prep_progress_dialog_factory=providers.Factory(
            analysis_algorithm_registry.env_prep_progress_dialog.Dialog,
            title="Preparing environment",
            min_size=(400, 100),
            init_message="Initializing...",
            button_box=providers.Factory(
                common.button_box.RejectAcceptButtonBox,
                reject_button_text="Abort",
            ),
        ).provider,
        analysis_alg_env_prep_signal=analysis_alg_env_prep_signal,
        parent=jb_main_window,
    )

    # -------------------------- Analysis algorithm configuration dialog ------------------------- #

    analysis_algorithm_selection_dialog = providers.Singleton(
        analysis_algorithm_selection.dialog.Dialog,
        title="Algorithm configuration",
        min_size=(600, 400),
        configurator=providers.Factory(
            analysis_algorithm_selection.dialog.AlgorithmConfigurator,
            parameter_collection=providers.Factory(common.parameter.ParameterCollection),
        ),
        button_box=providers.Factory(common.button_box.RejectAcceptButtonBox),
        analysis_alg_selected_signal=analysis_alg_selected_signal,
        parent=jb_main_window,
    )
