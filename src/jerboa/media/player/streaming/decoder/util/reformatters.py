from typing import Iterable

import av
from fractions import Fraction

from jerboa.media import MediaType, AudioConfig, VideoConfig


class AudioReformatter:

  def __init__(self, config: AudioConfig):
    self._config = config
    if config.frame_duration:
      self._frame_size = round(config.frame_duration * self._config.sample_rate)
    else:
      self._frame_size = None
    self._resampler = av.AudioResampler(format=self._config.format,
                                        layout=self._config.layout,
                                        rate=self._config.sample_rate,
                                        frame_size=self._frame_size)
    self._has_samples = False
    self.reset()

  def reset(self) -> None:
    if self._has_samples:
      self._resampler = av.AudioResampler(format=self._config.format,
                                          layout=self._config.layout,
                                          rate=self._config.sample_rate,
                                          frame_size=self._frame_size)
      self._has_samples = False

  @property
  def config(self) -> AudioConfig:
    return self._config

  def reformat(self, frame: av.AudioFrame | None) -> Iterable[av.AudioFrame]:
    if frame is not None:
      # remove this assert when av.AudioResampler if fixed
      assert frame.time_base == Fraction(1, frame.sample_rate)
      self._has_samples = True

    for reformatted_frame in self._resampler.resample(frame):
      if reformatted_frame is not None:
        yield reformatted_frame

  def flush(self) -> Iterable[av.AudioFrame]:
    if self._has_samples:
      reformatted_frames = list(self.reformat(None))
      self.reset()
      for reformatted_frame in reformatted_frames:
        yield reformatted_frame


class VideoReformatter:

  def __init__(self, config: VideoConfig):
    self._config = config
    self._reformatter = av.video.reformatter.VideoReformatter()

  @property
  def config(self) -> VideoConfig:
    return self._config

  def reset(self) -> None:
    pass  # av.video.VideoReformatter is stateless

  def reformat(self, frame: av.VideoFrame | None) -> av.VideoFrame:
    return self._reformatter.reformat(frame, format=self._config.format)


def create_reformatter(media_config: AudioConfig | VideoConfig):
  if media_config.media_type == MediaType.AUDIO:
    return AudioReformatter(media_config)
  return VideoReformatter(media_config)


# import errno
# def pull_from_graph(graph: av.filter.Graph):
#   while True:
#     try:
#       return graph.pull()
#     except EOFError:
#       break
#     except av.utils.AVError as e:
#       if e.errno != errno.EAGAIN:
#         raise
#       break
#   return None

# def create_audio_reformatter(in_fmt: av.AudioFormat, in_layout: av.AudioLayout, in_sample_rate: int,
#                              out_fmt: av.AudioFormat, out_layout: av.AudioLayout,
#                              out_sample_rate: int) -> av.filter.Graph:
#   if in_fmt == out_fmt and in_layout == out_layout and in_sample_rate == out_sample_rate:
#     return lambda frame: [frame]

#   graph = av.filter.Graph()
#   abuffer = graph.add("abuffer",
#                       sample_fmt=in_fmt.name,
#                       channel_layout=in_layout.name,
#                       sample_rate=str(in_sample_rate))
#   aformat = graph.add("aformat",
#                       sample_fmt=out_fmt.name,
#                       channel_layout=out_layout.name,
#                       sample_rate=str(out_sample_rate))
#   abuffersink = graph.add("abuffersink")
#   abuffer.link_to(aformat)
#   aformat.link_to(abuffersink)
#   graph.configure()

#   def reformat_audio(frame: av.AudioFrame):
#     graph.push(frame)
#     for processed_frame in pull_from_graph(graph):
#       yield processed_frame

#   return reformat_audio
