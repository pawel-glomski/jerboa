from typing import Callable

import sys

from jerboa.ui import JerboaUI
from jerboa.ui.gui import JerboaGUI
from jerboa.media import MediaType
from jerboa.media.source.decoder import JerboaDecoder, SkippingDecoder, SimpleDecoder


class MediaSource:

  def __init__(self):
    pass

  @property
  def audio_decoder(self) -> JerboaDecoder | None:
    return None

  @property
  def video_decoder(self) -> JerboaDecoder | None:
    return None


class PlaybackClock:

  def __init__(self) -> None:
    self._start_time = 0

  def time(self) -> float:
    return 0


class AudioPlayer(PlaybackClock):

  def __init__(self) -> None:
    super().__init__()


class VideoPlayer:

  def __init__(self, frame_display_fn: Callable[[], None]) -> None:
    self._frame_display_fn = frame_display_fn
    self._playback_clock: PlaybackClock | None = None

  def play(self, playback_clock: PlaybackClock = PlaybackClock()):
    ...


class MediaPlayer:

  def __init__(self, audio_player: AudioPlayer, video_player: VideoPlayer) -> None:
    self._audio_player = audio_player
    self._video_player = video_player

  def play(self, audio_decoder: JerboaDecoder, video_decoder: JerboaDecoder, start_time: float):
    self.reset()

    if audio_decoder.has_audio:
      audio_decoder = media_source.decode(MediaType.Audio, start_time=start_time)
      self._audio_player.play(audio_decoder)

      playback_clock = self._audio_player
    else:
      playback_clock = PlaybackClock()

    if media_source.has_video:
      video_decoder = media_source.decode(MediaType.Video, start_time=start_time)
      self._video_player.play(playback_clock=playback_clock)

  def reset(self):
    self._audio_player.reset()
    self._video_player.reset()


class JerboaApp:

  def __init__(self, ui: JerboaUI) -> None:
    self._ui = ui

    audio_player = AudioPlayer()
    video_player = VideoPlayer(frame_display_fn=ui.display_video_frame)
    self._media_player = MediaPlayer(audio_player=audio_player, video_player=video_player)

  def run(self):
    return self._ui.run_event_loop()


def main():
  ui = JerboaGUI()
  app = JerboaApp(ui)
  sys.exit(app.run())


if __name__ == '__main__':
  main()
