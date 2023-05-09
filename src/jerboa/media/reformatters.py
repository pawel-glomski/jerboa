import av
from enum import Enum


class MediaType(Enum):
  AUDIO = 'audio'
  VIDEO = 'video'


class AudioReformatter:

  def __init__(self, fmt: av.AudioFormat, layout: av.AudioLayout, sample_rate: int):
    self._format = fmt
    self._layout = layout
    self._sample_rate = sample_rate
    self._resampler = av.AudioResampler(format=fmt, layout=layout, rate=sample_rate)

  @property
  def media_type(self) -> MediaType:
    return MediaType.AUDIO

  @property
  def format(self) -> av.AudioFormat:
    return self._format

  @property
  def layout(self) -> av.AudioLayout:
    return self._layout

  @property
  def channels_num(self) -> int:
    return len(self._layout.channels)

  @property
  def sample_rate(self) -> int:
    return self._sample_rate

  def clear(self):
    pass  # av.AudioResampler does not have a persistent state

  def reformat(self, frame: av.AudioFrame):
    for reformatted_frame in self._resampler.resample(frame):
      yield reformatted_frame


class VideoReformatter:

  def __init__(self, fmt: av.AudioFormat):
    self._format = fmt
    self._reformatter = av.video.reformatter.VideoReformatter()

  @property
  def media_type(self) -> MediaType:
    return MediaType.VIDEO

  @property
  def format(self) -> av.VideoFormat:
    return self._format

  def clear(self):
    pass  # av.video.VideoReformatter does not have a persistent state

  def reformat(self, frame: av.VideoFrame):
    # TODO: this can also handle resize, etc
    yield self._reformatter.reformat(frame, format=self._format)


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
