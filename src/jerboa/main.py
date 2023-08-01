import sys

from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

from jerboa.model import PlayerModel
from jerboa.ui import JerboaUI
from jerboa.ui.gui import GUIApp, JerboaGUI
from jerboa.ui.gui.player_view import PlayerView


class Container(containers.DeclarativeContainer):

  # config = providers.Configuration()

  player_model = providers.Singleton(PlayerModel)

  gui_app = providers.Singleton(GUIApp)  # this has to be created before any view
  player_view = providers.Factory(
      PlayerView,
      player_model=player_model,
  )
  jerboa_gui = providers.Singleton(
      JerboaGUI,
      gui_app=gui_app,
      player_view=player_view,
  )


@inject
def main(ui: JerboaUI = Provide[Container.jerboa_gui]):
  sys.exit(ui.run_event_loop())


if __name__ == '__main__':
  _dependencies_container = Container()
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