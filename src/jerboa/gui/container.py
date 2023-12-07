from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

import PySide6.QtWidgets as QtW

from jerboa.core.file import PathProcessor
from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool
from jerboa.media.recognizer import MediaSourceRecognizer
from .main_view_stack import MainViewStack
from .status_bar import StatusBar
from .main_window import MainWindow
from . import core
from . import common
from . import menu_bar
from . import player_view
from . import resources
from . import media_source_selection
from . import analysis_algorithm_selection


class Container(containers.DeclarativeContainer):
    # config = providers.Configuration()
    wiring_config = containers.WiringConfiguration(
        modules=[__name__],
    )

    # --------------------------------------- Dependencies --------------------------------------- #

    qt_app = providers.Dependency(QtW.QApplication)
    thread_pool = providers.Dependency(ThreadPool)

    media_source_selected_signal = providers.Dependency(Signal)
    ready_to_play_signal = providers.Dependency(Signal)
    playback_toggle_signal = providers.Dependency(Signal)
    seek_backward_signal = providers.Dependency(Signal)
    seek_forward_signal = providers.Dependency(Signal)
    video_frame_update_signal = providers.Dependency(Signal)

    analysis_algorithm_registered_signal = providers.Dependency(Signal)
    analysis_algorithm_selected_signal = providers.Dependency(Signal)

    # ------------------------------------------ Palette ----------------------------------------- #

    # palette = providers.Singleton(
    #     Palette,
    #     app=qt_app,
    # )

    # ----------------------------------------- Resources ---------------------------------------- #

    resource_loading_spinner = providers.Singleton(
        resources.common.LoadingSpinner,
        path=":/loading_spinner.gif",
        size=(30, 30),
    )

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

    menu_bar_analyze = providers.Singleton(
        menu_bar.MenuAction,
        name="Analyze",
        signal=providers.Factory(core.signal.QtSignal),
    )

    jb_menu_bar = providers.Singleton(
        menu_bar.MenuBar,
        menus=providers.List(
            menu_bar_file,
        ),
        actions=providers.List(
            menu_bar_analyze,
        ),
    )

    # ---------------------------------------- Player view --------------------------------------- #

    player_view_canvas = providers.Singleton(
        player_view.Canvas,
        video_frame_update_signal=video_frame_update_signal,
        no_video_text="No video stream",
    )
    player_view_timeline = providers.Singleton(
        player_view.Timeline,
        # playback_update_signal=media_player.playback_update
    )

    jb_player_view = providers.Singleton(
        player_view.PlayerView,
        canvas=player_view_canvas,
        timeline=player_view_timeline,
        playback_toggle_signal=playback_toggle_signal,
        seek_backward_signal=seek_backward_signal,
        seek_forward_signal=seek_forward_signal,
    )

    # -------------------------------------- Main view stack ------------------------------------- #

    jb_main_view_stack = providers.Singleton(
        MainViewStack,
        player_view=jb_player_view,
        # settings_view=settings_view,
        # plugins_view=plugins_view,
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
        main_widget=jb_main_view_stack,
        status_bar=jb_status_bar,
    )

    # ------------------------------- Media source selection dialog ------------------------------ #

    media_source_selection_dialog = providers.Singleton(
        media_source_selection.dialog.Dialog,
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
        panel_stack=providers.Factory(common.panel_stack.PanelStack),
        hint_panel=providers.Factory(
            common.panel_stack.HintPanel,
            text="Select a local file or enter an URL",
        ),
        loading_spinner_panel=providers.Factory(
            common.panel_stack.LoadingSpinnerPanel,
            loading_spinner_movie=resource_loading_spinner,
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
        button_box=providers.Factory(
            common.button_box.RejectAcceptButtonBox,
            reject_button=common.button_box.ButtonType.Cancel,
            accept_button=common.button_box.ButtonType.Ok,
            icons=False,
            is_accept_button_disabled_by_default=True,
        ),
        recognizer=providers.Factory(
            MediaSourceRecognizer,
            recognition_finished_signal=providers.Factory(core.signal.QtSignal, "callback"),
            thread_pool=thread_pool,
        ),
        media_source_selected_signal=media_source_selected_signal,
        parent=jb_main_window,
    )

    # ---------------------------- Analysis algorithm selection dialog --------------------------- #

    analysis_algorithm_selector = providers.Singleton(
        analysis_algorithm_selection.dialog.AlgorithmSelector,
        algorithm_changed_signal=providers.Factory(core.signal.QtSignal, "algorithm"),
    )

    analysis_algorithm_selection_dialog = providers.Singleton(
        analysis_algorithm_selection.dialog.Dialog,
        min_size=(600, 400),
        algorithm_selector=analysis_algorithm_selector,
        configurator=providers.Factory(
            analysis_algorithm_selection.dialog.AlgorithmConfigurator,
            parameter_collection=providers.Factory(common.parameter.ParameterCollection),
        ),
        button_box=providers.Factory(
            common.button_box.RejectAcceptButtonBox,
            reject_button=common.button_box.ButtonType.Cancel,
            accept_button=common.button_box.ButtonType.Ok,
            icons=False,
            is_accept_button_disabled_by_default=False,
        ),
        analysis_algorithm_selected_signal=analysis_algorithm_selected_signal,
        parent=jb_main_window,
    )


@inject
def run(
    qt_app: QtW.QApplication = Provide[Container.qt_app],
    jb_main_window: MainWindow = Provide[Container.jb_main_window],
) -> int:
    connect_signals()
    fix_palette()

    jb_main_window.show()
    return qt_app.exec()


def connect_signals():
    connect_menu_bar_signals()


@inject
def connect_menu_bar_signals(
    menu_bar_file_open: menu_bar.MenuAction = Provide[Container.menu_bar_file_open],
    menu_bar_analyze: menu_bar.MenuAction = Provide[Container.menu_bar_analyze],
    media_source_selection_dialog: media_source_selection.dialog.Dialog = Provide[
        Container.media_source_selection_dialog
    ],
    analysis_algorithm_selection_dialog: analysis_algorithm_selection.dialog.Dialog = Provide[
        Container.analysis_algorithm_selection_dialog
    ],
) -> None:
    menu_bar_file_open.signal.connect(media_source_selection_dialog.open_clean)
    menu_bar_analyze.signal.connect(analysis_algorithm_selection_dialog.open_clean)


@inject
def connect_analysis_algorithm_selector(
    analysis_algorithm_registered_signal: Signal = Provide[
        Container.analysis_algorithm_registered_signal
    ],
    analysis_algorithm_selector: analysis_algorithm_selection.dialog.AlgorithmSelector = Provide[
        Container.analysis_algorithm_selector
    ],
) -> None:
    analysis_algorithm_registered_signal.connect(analysis_algorithm_selector.add_algorithm)


@inject
def fix_palette(qt_app: QtW.QApplication = Provide[Container.qt_app]) -> None:
    palette = qt_app.palette()
    palette.setColor(palette.ColorRole.ToolTipBase, palette.color(palette.ColorRole.Window))
    qt_app.setPalette(palette)
