from .media import MediaType, AudioConfig, VideoConfig

import av

PROCESSING_AUDIO_FRAME_SIZE = 1024 * 10


class AudioReformatter:

  def __init__(self, config: AudioConfig):
    self._config = config
    self.reset()

  def reset(self):
    self._resampler = av.AudioResampler(format=self._config.format,
                                        layout=self._config.layout,
                                        rate=self._config.sample_rate,
                                        frame_size=PROCESSING_AUDIO_FRAME_SIZE)

  def reformat(self, frame: av.AudioFrame):
    for reformatted_frame in self._resampler.resample(frame):
      if reformatted_frame is not None:
        yield reformatted_frame


class VideoReformatter:

  def __init__(self, config: VideoConfig):
    self._config = config
    self._reformatter = av.video.reformatter.VideoReformatter()

  def reset(self):
    pass  # av.video.VideoReformatter does not have a persistent state

  def reformat(self, frame: av.VideoFrame):
    # TODO: this can also handle resize, etc
    yield self._reformatter.reformat(frame, format=self._config.format)


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
