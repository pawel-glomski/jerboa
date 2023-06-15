from collections.abc import Generator

from dataclasses import dataclass

from jerboa.media import MediaType, AudioConfig, VideoConfig, config_from_stream
from .simple_decoder import SimpleDecoder, TimedFrame
from .util import AudioReformatter, VideoReformatter, create_reformatter

MIN_SEEK_THRESHOLD = 0.25  # in seconds


@dataclass
class SkippingFrame(TimedFrame):
  skip_aware_beg_timepoint: float


class SkippingDecoder:

  def __init__(self, simple_decoder: SimpleDecoder):
    self._simple_decoder = simple_decoder
    self._reformatter: AudioReformatter | VideoReformatter | None = None

    if self.media_type == MediaType.AUDIO:
      self.decode = self._decode_audio
    else:
      self.decode = self._decode_video

    self._seek_threshold = max(MIN_SEEK_THRESHOLD, self._simple_decoder.probe_keyframe_duration())

  @property
  def media_type(self) -> MediaType:
    return self._simple_decoder.media_type

  @property
  def stream_index(self) -> SimpleDecoder:
    return self._simple_decoder.stream.index

  @property
  def start_timepoint(self) -> float:
    return self._simple_decoder.start_timepoint

  @property
  def seek_threshold(self) -> float:
    return self._seek_threshold

  def _decode_audio(
      self,
      seek_timepoint: float,
      media_config: AudioConfig,
  ) -> Generator[SkippingFrame, float, None]:
    self._init_reformatter(media_config)
    reformatter: AudioReformatter = self._reformatter

    skip_timepoint = seek_timepoint
    for timed_frame in self._simple_decoder.decode(seek_timepoint):
      if timed_frame is None:
        reformatted_frames_src = reformatter.flush()
      elif timed_frame.end_timepoint > skip_timepoint:
        reformatted_frames_src = reformatter.reformat(timed_frame.av_frame)
      else:
        reformatter.reset()
        reformatted_frames_src = []

      for reformatted_frame in reformatted_frames_src:
        skipping_frame = SkippingFrame(
            reformatted_frame,
            beg_timepoint=reformatted_frame.time,
            end_timepoint=(reformatted_frame.time +
                           reformatted_frame.samples / reformatted_frame.sample_rate),
            skip_aware_beg_timepoint=max(skip_timepoint, reformatted_frame.time),
        )
        skip_timepoint = yield skipping_frame
        yield  # wait for the `next()` call of the for loop

  def _init_reformatter(
      self,
      media_config: AudioConfig | VideoConfig,
  ) -> Generator[SkippingFrame, float, None]:
    if media_config.media_type != self.media_type:
      raise TypeError(
          f'Wrong media type! Expected "{self.media_type}", but got "{media_config.media_type}"')

    media_config = media_config or config_from_stream(self._stream)
    if self._reformatter is None or self._reformatter.config != media_config:
      self._reformatter = create_reformatter(media_config)
    else:
      self._reformatter.reset()

  def _decode_video(
      self,
      seek_timepoint: float,
      media_config: VideoConfig,
  ) -> Generator[SkippingFrame, float, None]:
    self._init_reformatter(media_config)
    reformatter: VideoReformatter = self._reformatter

    skip_timepoint = seek_timepoint
    for timed_frame in self._simple_decoder.decode(seek_timepoint):
      if timed_frame is not None and timed_frame.end_timepoint > skip_timepoint:
        reformatted_av_frame = reformatter.reformat(timed_frame.av_frame)
        timed_frame = SkippingFrame(
            reformatted_av_frame,
            beg_timepoint=timed_frame.beg_timepoint,
            end_timepoint=timed_frame.end_timepoint,
            skip_aware_beg_timepoint=max(skip_timepoint, timed_frame.beg_timepoint),
        )
        skip_timepoint = yield timed_frame
        yield  # yield again to wait for the `next()` call of the for loop

  def probe_keyframe_pts(self) -> list[float]:
    return self._simple_decoder.probe_keyframe_pts()
