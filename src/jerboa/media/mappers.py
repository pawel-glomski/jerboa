import av
import pytsmod
import numpy as np
from dataclasses import dataclass

import jerboa.media.normalized_audio as normalized_audio
from jerboa.timeline import RangeMappingResult, TMSection
from .reformatters import MediaType, AudioReformatter, VideoReformatter

DEFAULT_TSM_MIN_DURATION = 0.5


@dataclass
class MappedAudioFrame:
  beg_timepoint: float
  end_timepoint: float
  normalized_audio: np.ndarray


@dataclass
class MappedVideoFrame:
  beg_timepoint: float
  duration: float
  image: np.ndarray


class AudioMapper:

  def __init__(self,
               fmt: av.AudioFormat,
               layout: av.AudioLayout,
               sample_rate: int,
               tsm_min_duration: float = DEFAULT_TSM_MIN_DURATION) -> None:
    self._format = fmt
    self._layout = layout
    self._sample_rate = sample_rate
    self._audio = normalized_audio.create_circular_buffer(fmt, layout, sample_rate,
                                                          tsm_min_duration)
    self._last_samples = np.zeros(self._audio.get_shape_for_data(512), self._audio.dtype)

    self._transition_steps = normalized_audio.get_transition_steps(sample_rate)
    self._target_tsm_samples_num = int(tsm_min_duration * sample_rate)

    self.reset()

  def reset(self) -> None:
    self._audio.clear()
    self._modifiers = [-1]  # start with an impossible to encounter modifier
    self._anchors_before = [0]
    self._anchors_after = [0]
    self._beg_timepoint = None
    self._end_timepoint = None

  def map(self, frame: av.AudioFrame,
          mapping_results: RangeMappingResult) -> MappedAudioFrame | None:
    flush = frame is None
    if not flush:
      assert frame.format.name == self._format.name
      assert frame.layout.name == self._layout.name
      assert frame.sample_rate == self._sample_rate

      last_sample = self._audio[-1] if len(self._audio) else None
      frame_audio = normalized_audio.get_from_frame(frame)

      for section in mapping_results.sections:
        sample_idx_beg = int((section.beg - frame.time) * self._sample_rate)
        sample_idx_end = int((section.end - frame.time) * self._sample_rate)
        audio_part = frame_audio[normalized_audio.index_samples(sample_idx_beg, sample_idx_end)]
        last_sample = self._push(last_sample, audio_part, section)

      if len(self._audio) and self._beg_timepoint is None:
        self._beg_timepoint = mapping_results.beg
      self._end_timepoint = mapping_results.end

    if self._anchors_before[-1] != self._anchors_after[-1]:
      if len(self._audio) >= self._target_tsm_samples_num or flush:
        beg_timepoint = self._beg_timepoint
        end_timepoint = self._end_timepoint
        audio = self._pop_all_and_reset_with_tsm()
        return MappedAudioFrame(beg_timepoint, end_timepoint, audio)
    elif len(self._audio) > 0:
      beg_timepoint = self._beg_timepoint
      end_timepoint = self._end_timepoint
      audio = self._pop_all_and_reset()
      return MappedAudioFrame(beg_timepoint, end_timepoint, audio)
    return None

  def _push(self, last_sample: np.ndarray | None, audio: np.ndarray, section: TMSection):
    if audio.size == 0:
      return last_sample

    if last_sample is not None:
      normalized_audio.smooth_out_transition(last_sample, audio, self._transition_steps)

    samples_num = audio.shape[normalized_audio.SAMPLE_IDX]
    if self._modifiers[-1] == section.modifier:
      self._anchors_before[-1] += samples_num
      self._anchors_after[-1] += round(samples_num * section.modifier)
    else:
      self._anchors_before.append(self._anchors_before[-1] + samples_num)
      self._anchors_after.append(self._anchors_after[-1] + round(samples_num * section.modifier))
      self._modifiers.append(section.modifier)

    self._audio.put(audio)
    return self._audio[-1]

  def _pop_all_and_reset_with_tsm(self) -> np.ndarray:
    # TODO: consider adding last ~512 samples during TSM for better audio continuity
    # TODO: TSM algorithm should be an option
    anchors = np.array([self._anchors_before, self._anchors_after])
    audio_before = self._pop_all_and_reset()
    audio_before = audio_before.T if normalized_audio.CHANNEL_IDX == 1 else audio_before

    audio_after = pytsmod.hptsm(audio_before, anchors)
    return audio_after.T if normalized_audio.CHANNEL_IDX == 1 else audio_after

  def _pop_all_and_reset(self) -> np.ndarray:
    audio = self._audio.pop(len(self._audio))
    self.reset()
    return audio


class VideoMapper:

  @property
  def media_type(self) -> MediaType:
    return MediaType.VIDEO

  def reset(self) -> None:
    pass

  def map(self, frame: av.VideoFrame,
          mapping_results: RangeMappingResult) -> MappedVideoFrame | None:
    flush = frame is None
    if not flush and mapping_results.beg < mapping_results.end:
      return MappedVideoFrame(mapping_results.beg, mapping_results.end - mapping_results.beg,
                              frame.to_ndarray())
    return None


def create_mapper(reformatter: AudioReformatter | VideoReformatter) -> AudioMapper | VideoMapper:
  if reformatter.media_type == MediaType.AUDIO:
    return AudioMapper(reformatter.format, reformatter.layout, reformatter.sample_rate)
  return VideoMapper()
