import av
import numpy as np
from pylibrb import RubberBandStretcher, Option
from dataclasses import dataclass

from jerboa.media import MediaType, AudioConfig, VideoConfig, std_audio
from jerboa.timeline import RangeMappingResult


@dataclass
class MappedFrame:
  timepoint: float
  duration: float
  data: np.ndarray


class AudioMapper:

  def __init__(self, audio_config: AudioConfig) -> None:
    self._audio_config = AudioConfig(std_audio.FORMAT,
                                     audio_config.layout,
                                     audio_config.sample_rate,
                                     frame_duration=std_audio.FRAME_DURATION)
    self._audio = std_audio.create_circular_buffer(self._audio_config)
    # self._transition_steps = std_audio.get_transition_steps(audio_config.sample_rate)

    self._stretcher = RubberBandStretcher(audio_config.sample_rate, audio_config.channels_num,
                                          Option.PROCESS_REALTIME | Option.ENGINE_FASTER)
    # self._stretcher.set_max_process_size(self._audio.max_size)
    self.reset()

  @property
  def internal_media_config(self) -> AudioConfig:
    return self._audio_config

  def reset(self) -> None:
    self._audio.clear()
    self._stretcher.reset()
    self._last_frame_end_timepoint = None

  def map(self, frame: av.AudioFrame, mapping_results: RangeMappingResult) -> MappedFrame:
    flush = frame is None

    if flush and self._last_frame_end_timepoint is not None:
      flushing_packet = std_audio.create_audio_array(self._audio_config.channels_num,
                                                     self._stretcher.get_samples_required())
      self._stretcher.process(flushing_packet, final=True)
    else:
      assert frame.format.name == self._audio_config.format.name
      assert frame.layout.name == self._audio_config.layout.name
      assert frame.sample_rate == self._audio_config.sample_rate

      for audio_segment, modifier in self._cut_according_to_mapping_results(frame, mapping_results):
        self._stretcher.time_ratio = modifier
        self._stretcher.process(audio_segment)
        self._audio.put(self._stretcher.retrieve_available())

      if self._last_frame_end_timepoint is None and len(self._audio) > 0:
        self._last_frame_end_timepoint = mapping_results.beg

    if len(self._audio) > 0:
      audio = self._audio.pop(len(self._audio))
      beg_timepoint = self._last_frame_end_timepoint
      duration = std_audio.calc_duration(audio, self._audio_config.sample_rate)
      self._last_frame_end_timepoint = beg_timepoint + duration
      return MappedFrame(beg_timepoint, duration, audio)
    return MappedFrame(0, 0, None)

  def _cut_according_to_mapping_results(self, frame: av.AudioFrame,
                                        mapping_results: RangeMappingResult):

    frame_audio = std_audio.get_from_frame(frame)
    for section in mapping_results.sections:
      sample_idx_beg = round((section.beg - frame.time) * self._audio_config.sample_rate)
      sample_idx_end = round((section.end - frame.time) * self._audio_config.sample_rate)
      audio_section = frame_audio[std_audio.index_samples(sample_idx_beg, sample_idx_end)]
      if audio_section.size > 0:
        # std_audio.smooth_out_transition(audio_section)
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

    return MappedFrame(0, 0, None)  # empty frame


def create_mapper(media_config: AudioConfig | VideoConfig) -> AudioMapper | VideoMapper:
  if media_config.media_type == MediaType.AUDIO:
    return AudioMapper(media_config)
  return VideoMapper(media_config)
