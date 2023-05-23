import av
import pytsmod
import numpy as np
from dataclasses import dataclass

from jerboa.media import normalized_audio
from jerboa.timeline import RangeMappingResult, TMSection
from .media import MediaType, AudioConfig, VideoConfig

DEFAULT_MIN_AUDIO_DURATION = 0.25


@dataclass
class StretchedFrame:
  beg_timepoint: float
  end_timepoint: float
  data: np.ndarray


class AudioStretcher:

  def __init__(self,
               audio_config: AudioConfig,
               min_duration: float = DEFAULT_MIN_AUDIO_DURATION) -> None:
    self._processing_audio_config = AudioConfig(normalized_audio.FORMAT, audio_config.layout,
                                                audio_config.sample_rate)

    self._audio = normalized_audio.create_circular_buffer(self._processing_audio_config,
                                                          min_duration)

    self._transition_steps = normalized_audio.get_transition_steps(audio_config.sample_rate)
    self._target_samples_num = int(min_duration * audio_config.sample_rate)

    self.reset()

  @property
  def processing_media_config(self) -> AudioConfig:
    return self._processing_audio_config

  def reset(self) -> None:
    self._audio.clear()
    self._modifiers = [-1]  # start with an impossible to encounter modifier
    self._anchors_before = [0]
    self._anchors_after = [0]
    self._beg_timepoint = None
    self._end_timepoint = None
    self._last_section_end = None

  def stretch(self, frame: av.AudioFrame, mapping_results: RangeMappingResult) -> StretchedFrame:
    flush = frame is None

    if not flush:
      assert frame.format.name == self._processing_audio_config.format.name
      assert frame.layout.name == self._processing_audio_config.layout.name
      assert frame.sample_rate == self._processing_audio_config.sample_rate
      self._cut_according_to_mapping_results_and_push(frame, mapping_results)

    if len(self._audio) >= self._target_samples_num or flush:
      beg_timepoint = self._beg_timepoint
      end_timepoint = self._end_timepoint
      if self._anchors_before[-1] != self._anchors_after[-1]:
        audio = self._pop_all_and_clear_with_tsm()
      else:
        audio = self._pop_all_and_clear()
      return StretchedFrame(beg_timepoint, end_timepoint, audio)

    return StretchedFrame(0, 0, np.array([]))  # empty frame

  def _cut_according_to_mapping_results_and_push(self, frame: av.AudioFrame,
                                                 mapping_results: RangeMappingResult):
    last_sample = self._audio[-1] if len(self._audio) else None
    frame_audio = normalized_audio.get_from_frame(frame)

    for section in mapping_results.sections:
      sample_idx_beg = int((section.beg - frame.time) * self._processing_audio_config.sample_rate)
      sample_idx_end = int((section.end - frame.time) * self._processing_audio_config.sample_rate)
      audio_part = frame_audio[normalized_audio.index_samples(sample_idx_beg, sample_idx_end)]
      last_sample = self._push_audio_section(last_sample, audio_part, section)

    if len(self._audio) and self._beg_timepoint is None:
      self._beg_timepoint = mapping_results.beg
    self._end_timepoint = mapping_results.end

  def _push_audio_section(self, last_sample: np.ndarray | None, audio: np.ndarray,
                          section: TMSection):
    if audio.size == 0:
      return last_sample

    if self._last_section_end is not None and section.beg != self._last_section_end:
      normalized_audio.smooth_out_transition(last_sample, audio, self._transition_steps)

    self._audio.put(audio)

    samples_num = audio.shape[normalized_audio.SAMPLES_AXIS]
    if self._modifiers[-1] == section.modifier:
      self._anchors_before[-1] += samples_num
      self._anchors_after[-1] += round(samples_num * section.modifier)
    else:
      self._anchors_before.append(self._anchors_before[-1] + samples_num)
      self._anchors_after.append(self._anchors_after[-1] + round(samples_num * section.modifier))
      self._modifiers.append(section.modifier)

    self._last_section_end = section.end

    return self._audio[-1]

  def _pop_all_and_clear_with_tsm(self) -> np.ndarray:
    # TODO: TSM algorithm should be an option
    anchors = np.array([self._anchors_before, self._anchors_after])
    audio_before = self._pop_all_and_clear()
    audio_before = audio_before.T if normalized_audio.CHANNELS_AXIS == 1 else audio_before

    audio_after = pytsmod.hptsm(audio_before, anchors)
    return audio_after.T if normalized_audio.CHANNELS_AXIS == 1 else audio_after

  def _pop_all_and_clear(self) -> np.ndarray:
    audio = self._audio.pop(len(self._audio))
    self.reset()
    return audio


class VideoStretcher:

  def __init__(self, video_config: VideoConfig) -> None:
    self._video_config = video_config

  @property
  def processing_media_config(self) -> VideoConfig:
    return self._video_config

  def reset(self) -> None:
    pass

  def stretch(self, frame: av.VideoFrame, mapping_results: RangeMappingResult) -> StretchedFrame:
    flush = frame is None
    if not flush and mapping_results.beg < mapping_results.end:
      return StretchedFrame(mapping_results.beg, mapping_results.end, frame.to_ndarray())

    return StretchedFrame(0, 0, np.array([]))  # empty frame


def create_stretcher(media_config: AudioConfig | VideoConfig,
                     stretcher_buffer_duration: float) -> AudioStretcher | VideoStretcher:
  if media_config.media_type == MediaType.AUDIO:
    return AudioStretcher(media_config, stretcher_buffer_duration)
  return VideoStretcher(media_config)
