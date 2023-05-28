import av
import numpy as np
from pylibrb import RubberBandStretcher, Option
from dataclasses import dataclass

from jerboa.media import normalized_audio as naudio
from jerboa.timeline import RangeMappingResult
from .media import MediaType, AudioConfig, VideoConfig

DEFAULT_MIN_AUDIO_DURATION = 0.25


@dataclass
class MappedFrame:
  timepoint: float
  duration: float
  data: np.ndarray


class AudioMapper:

  def __init__(self,
               audio_config: AudioConfig,
               min_duration: float = DEFAULT_MIN_AUDIO_DURATION) -> None:
    self._processing_audio_config = AudioConfig(naudio.FORMAT, audio_config.layout,
                                                audio_config.sample_rate)

    self._audio = naudio.create_circular_buffer(self._processing_audio_config, min_duration)

    self._transition_steps = naudio.get_transition_steps(audio_config.sample_rate)
    self._target_samples_num = int(min_duration * audio_config.sample_rate)

    self._stretcher = RubberBandStretcher(audio_config.sample_rate, audio_config.channels_num,
                                          Option.PROCESS_REALTIME | Option.ENGINE_FINER)
    self.reset()

  @property
  def internal_media_config(self) -> AudioConfig:
    return self._processing_audio_config

  def reset(self) -> None:
    self._audio.clear()
    self._beg_timepoint = None
    self._stretcher.reset()

  def map(self, frame: av.AudioFrame, mapping_results: RangeMappingResult) -> MappedFrame:
    flush = frame is None

    if not flush:
      assert frame.format.name == self._processing_audio_config.format.name
      assert frame.layout.name == self._processing_audio_config.layout.name
      assert frame.sample_rate == self._processing_audio_config.sample_rate

      for audio_segment, modifier in self._cut_according_to_mapping_results(frame, mapping_results):
        self._stretcher.time_ratio = modifier
        self._stretcher.process(audio_segment)
        available_samples_num = self._stretcher.available()
        if available_samples_num:
          stretched_audio = self._stretcher.retrieve(self._stretcher.available())
          self._audio.put(stretched_audio)

      if len(self._audio) and self._beg_timepoint is None:
        self._beg_timepoint = mapping_results.beg

    if len(self._audio) >= self._target_samples_num or flush:
      beg_timepoint = self._beg_timepoint
      audio = self._audio.pop(len(self._audio))
      duration = naudio.calc_duration(audio, self._processing_audio_config.sample_rate)
      self._beg_timepoint = None  # += duration
      return MappedFrame(beg_timepoint, duration, audio)

    return MappedFrame(0, 0, np.array([]))  # empty frame

  def _cut_according_to_mapping_results(self, frame: av.AudioFrame,
                                        mapping_results: RangeMappingResult):

    frame_audio = naudio.get_from_frame(frame)
    for section in mapping_results.sections:
      sample_idx_beg = round((section.beg - frame.time) * self._processing_audio_config.sample_rate)
      sample_idx_end = round((section.end - frame.time) * self._processing_audio_config.sample_rate)
      audio_section = frame_audio[naudio.index_samples(sample_idx_beg, sample_idx_end)]
      if audio_section.size > 0:
        # naudio.smooth_out_transition(audio_section)
        yield audio_section, section.modifier


class VideoMapper:

  def __init__(self, video_config: VideoConfig) -> None:
    self._video_config = video_config

  @property
  def internal_media_config(self) -> VideoConfig:
    return self._video_config

  def reset(self) -> None:
    pass

  def map(self, frame: av.VideoFrame, mapping_results: RangeMappingResult) -> MappedFrame:
    flush = frame is None
    if not flush and mapping_results.beg < mapping_results.end:
      duration = mapping_results.end - mapping_results.beg
      return MappedFrame(mapping_results.beg, duration, frame.to_ndarray())

    return MappedFrame(0, 0, np.array([]))  # empty frame


def create_mapper(media_config: AudioConfig | VideoConfig,
                  mapper_buffer_duration: float) -> AudioMapper | VideoMapper:
  if media_config.media_type == MediaType.AUDIO:
    return AudioMapper(media_config, mapper_buffer_duration)
  return VideoMapper(media_config)
