import sys

from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

from jerboa.ui import JerboaUI, gui
from jerboa.signal import Signal
# from jerboa.ui.gui.thread_pool import ThreadPool as GUIThreadPool


class Container(containers.DeclarativeContainer):

  # config = providers.Configuration()

  # audio_player = providers.Singleton(MediaPlayer)
  # video_player = providers.Singleton(MediaPlayer)
  # media_player = providers.Singleton(
  #     MediaPlayer,
  #     audio_player=audio_player,
  #     video_player=video_player,
  # )

  # thread_pool = providers.Resource(GUIThreadPool)

  # ---------------------------------------------------------------------------- #
  #                                    signals                                   #
  # ---------------------------------------------------------------------------- #

  # ---------------------------------------------------------------------------- #
  #                                      gui                                     #
  # ---------------------------------------------------------------------------- #

  # this has to be created before any gui element, thus it is a resource initialized with
  # init_resources() call below
  gui_app = providers.Resource(gui.GUIApp)

  gui_main_window = providers.Singleton(
      gui.MainWindow,
      min_size=(640, 360),
      relative_size=(0.5, 0.5),
  )

  # ------------------------------- gui resources ------------------------------ #

  # gui_resource_loading_spinner = providers.Resource(
  #     gui.resources.LoadingSpinner,
  #     path=':/loading_spinner.gif',
  #     size=(30, 30),
  # )

  # ----------------------- media source selection dialog ---------------------- #

  # ------------------------------- details panel ------------------------------ #

  # gui_media_source_details_panel_init = providers.Factory(
  #     gui.media_source_selection.details_panel.InitPanel,
  #     text='Select a local file or enter the URL of a recording')
  # gui_media_source_details_panel_loading = providers.Factory(
  #     gui.media_source_selection.details_panel.LoadingSpinnerPanel,
  #     spinner_gif=gui_resource_loading_spinner,
  # )
  # gui_media_source_details_panel_streaming_quality_selection = providers.Factory(
  #     gui.media_source_selection.details_panel.InitPanel,
  # )
  # gui_media_source_details_panel_stream_selection = providers.Factory(
  #     gui.media_source_selection.details_panel.InitPanel,
  # )
  # gui_media_source_details_panel = providers.Factory(
  #     gui.media_source_selection.details_panel.InitPanel,
  #     init_panel=gui_media_source_details_panel_init,
  #     loading_panel=gui_media_source_details_panel_loading,
  #     streaming_quality_selection_panel=gui_media_source_details_panel_streaming_quality_selection,
  #     stream_selection_panel=gui_media_source_details_panel_stream_selection,
  # )

  gui_meida_source_path_selector = providers.Factory(
      gui.common.PathSelector,
      select_local_file_button_text='Select a local file',
      placeholder_text='Media file path (or URL)...',
      apply_button_text='Apply',
      local_file_extension_filter=
      'Media files (*.mp3 *.wav *.ogg *.flac *.mp4 *.avi *.mkv *.mov);; All files (*)',
  )
  gui_media_source_selection_dialog_button_box = providers.Factory(
      gui.common.RejectAcceptDialogButtonBox,
      reject_button='cancel',
      accept_button='ok',
      icons=False,
      accept_disabled_by_default=True,
  )
  gui_media_source_selection_dialog = providers.Factory(
      gui.MediaSourceSelectionDialog,
      path_selector=gui_meida_source_path_selector,
      # media_source_details_panel=gui_media_source_details_panel,
      button_box=gui_media_source_selection_dialog_button_box,
      parent=gui_main_window,
  )

  # --------------------------------- menu bar --------------------------------- #

  gui_menu_bar_file_open = providers.Singleton(
      gui.menu_bar.MenuAction,
      name='Open',
      signal=providers.Factory(
          Signal,
          subscribers=providers.List(gui_media_source_selection_dialog.provided.exec),
      ),
  )
  gui_menu_bar_file = providers.Singleton(
      gui.menu_bar.Menu,
      name='File',
      actions=providers.List(gui_menu_bar_file_open,),
  )
  gui_menu_bar = providers.Singleton(
      gui.MenuBar,
      menus=providers.List(gui_menu_bar_file,),
  )

  # ----------------------------- main view stack ---------------------------- #

  # -------------------------------- player view ------------------------------- #

  gui_player_view_canvas = providers.Singleton(
      gui.player_view.Canvas,
      # frame_changed_signal=gui_video_player.frame_changed,
  )
  gui_player_view_timeline = providers.Singleton(
      gui.player_view.Timeline,
      # playback_update_signal=gui_media_player.playback_update
  )

  player_view = providers.Singleton(
      gui.PlayerView,
      canvas=gui_player_view_canvas,
      timeline=gui_player_view_timeline,
  )

  gui_main_widget = providers.Singleton(
      gui.MainViewStack,
      player_view=player_view,
      # settings_view=settings_view,
      # plugins_view=plugins_view,
  )

  # -------------------------------- jerboa gui -------------------------------- #

  gui_jerboa = providers.Singleton(
      gui.JerboaGUI,
      gui_app=gui_app,
      main_window=gui_main_window,
      menu_bar=gui_menu_bar,
      main_widget=gui_main_widget,
      # status_bar=gui_status_bar,
  )


@inject
def main(ui: JerboaUI = Provide[Container.gui_jerboa]):
  sys.exit(ui.run_event_loop())


if __name__ == '__main__':
  _dependencies_container = Container()
  _dependencies_container.init_resources()
  _dependencies_container.wire(modules=[__name__])

  main()

# from typing import Callable
# from jerboa.media import MediaType
# from jerboa.media.source.decoder import JerboaDecoder, SkippingDecoder, SimpleDecoder

# class MediaSource:

#   def __init__(self):
#     pass

#   @property
#   def audio_decoder(self) -> JerboaDecoder | None:
#     return None

#   @property
#   def video_decoder(self) -> JerboaDecoder | None:
#     return None

# class PlaybackClock:

#   def __init__(self) -> None:
#     self._start_time = 0

#   def time(self) -> float:
#     return 0

# class AudioPlayer(PlaybackClock):

#   def __init__(self) -> None:
#     super().__init__()

# class MediaPlayer:

#   def __init__(self, audio_player: AudioPlayer) -> None:
#     self._audio_player = audio_player

#   def play(self, audio_decoder: JerboaDecoder, video_decoder: JerboaDecoder, start_time: float):
#     self.reset()

#     if audio_decoder.has_audio:
#       audio_decoder = media_source.decode(MediaType.Audio, start_time=start_time)
#       self._audio_player.play(audio_decoder)

#       playback_clock = self._audio_player
#     else:
#       playback_clock = PlaybackClock()

#     if media_source.has_video:
#       video_decoder = media_source.decode(MediaType.Video, start_time=start_time)
#       self._video_player.play(playback_clock=playback_clock)

#   def reset(self):
#     self._audio_player.reset()
#     self._video_player.reset()