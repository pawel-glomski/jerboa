import av
import math

from pyglet.image import ImageData
from pyglet.media import StreamingSource
from pyglet.media.codecs import AudioFormat, VideoFormat, AudioData

from jerboa.media import normalized_audio
from jerboa.timeline import FragmentedTimeline
from .decoder import StreamDecoder
from .media import MediaType, AudioConfig, VideoConfig

VIDEO_FORMAT_PYGLET = 'RGB'
VIDEO_FORMAT = av.VideoFormat('rgb24')
AUDIO_FORMAT = av.AudioFormat('s16').packed
AUDIO_MAX_LAYOUT = av.AudioLayout('stereo')


def create_stream_config(stream: av.stream.Stream) -> AudioConfig | VideoConfig:
  if MediaType(stream.type) == MediaType.AUDIO:
    config = AudioConfig(AUDIO_FORMAT, stream.layout, stream.sample_rate)
    if len(config.layout.channels) > len(AUDIO_MAX_LAYOUT.channels):
      config.layout = AUDIO_MAX_LAYOUT
    return config

  return VideoConfig(VIDEO_FORMAT)


#TODO: fix desync after seeking, does not happen when: pause -> seek 0 -> play


class JBSource(StreamingSource):

  def __init__(self, filepath: str):
    from jerboa.timeline import TMSection  # TODO: remove me, for debugging only
    debug_timeline = FragmentedTimeline(
        # *[TMSection(i * 1.0, i * 1.0 + 0.5, 1 - 0.5 * (i % 2)) for i in range(200)]
        # TMSection(0, 4, 0.75),
        # TMSection(0, math.inf, 1 / 1.5)
        TMSection(0, math.inf))

    self.container = av.open(filepath)
    self.decoders: dict[MediaType, StreamDecoder] = {}
    if self.container.streams.audio:
      audio_stream = self.container.streams.audio[0]
      audio_config = create_stream_config(audio_stream)

      audio_decoder = StreamDecoder(filepath,
                                    audio_stream.index,
                                    media_config=audio_config,
                                    init_timeline=debug_timeline)
      self.decoders[MediaType.AUDIO] = audio_decoder

      self.audio_format = AudioFormat(channels=audio_config.channels_num,
                                      sample_size=audio_config.format.bits,
                                      sample_rate=audio_config.sample_rate)

    if self.container.streams.video:
      video_stream = self.container.streams.video[0]
      video_config = create_stream_config(video_stream)

      video_decoder = StreamDecoder(filepath,
                                    video_stream.index,
                                    media_config=video_config,
                                    init_timeline=debug_timeline)
      self.decoders[MediaType.VIDEO] = video_decoder

      sar = video_stream.sample_aspect_ratio
      self.video_format = VideoFormat(width=video_stream.width,
                                      height=video_stream.height,
                                      sample_aspect=sar if sar else 1.0)
      self.video_format.frame_rate = float(video_stream.average_rate)

    self.start_time = min(dec.start_timepoint for dec in self.decoders.values())
    self.last_video_frame: ImageData = None

  def __del__(self):
    self.container.close()

  def seek(self, timepoint: float):
    for decoder in self.decoders.values():
      decoder.seek(timepoint)

  def get_audio_data(self, num_bytes, compensation_time=0.0) -> AudioData:
    audio_decoder = self.decoders[MediaType.AUDIO]
    target_media_format = audio_decoder.target_media_format
    sample_rate = audio_decoder.processing_media_config.sample_rate
    timestamp = audio_decoder.get_next_timepoint()
    audio = audio_decoder.pop(num_bytes)
    if audio is None:
      return None

    audio = normalized_audio.compensated(audio, sample_rate, compensation_time)
    duration = normalized_audio.calc_duration(audio, sample_rate)
    audio_bytes = normalized_audio.to_real_audio(audio, target_media_format).tobytes()

    return AudioData(audio_bytes, len(audio_bytes), timestamp, duration, [])

  def get_next_video_timestamp(self):
    next_timepoint = self.decoders[MediaType.VIDEO].get_next_timepoint()
    if next_timepoint is None:
      return math.inf
    return next_timepoint

  def get_next_video_frame(self, skip_empty_frame=True):
    frame = self.decoders[MediaType.VIDEO].pop()
    if frame is not None:
      image_data = frame.data
      height, width = image_data.shape[:2]
      self.last_video_frame = ImageData(width, height, VIDEO_FORMAT_PYGLET, image_data.tobytes(),
                                        width * len(VIDEO_FORMAT_PYGLET))
    return self.last_video_frame
