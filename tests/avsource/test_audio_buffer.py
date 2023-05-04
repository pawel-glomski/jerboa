import pytest

import av
import numpy as np

from fractions import Fraction

from jerboa.avsource import AudioBuffer, AUDIO_FORMAT
from jerboa.timeline import FragmentedTimeline, TMSection, RangeMappingResult


class TestAudioBufferInit:

  def test_init_should_create_empty_audio_buffer_when_valid_args(self):
    AudioBuffer(5, AUDIO_FORMAT, av.AudioLayout('stereo'), 16000)

  def test_prepare_should_prepare_audio_from_frame_when_frame_is_not_dropped(self):
    buffer = AudioBuffer(AUDIO_FORMAT, av.AudioLayout('stereo'), 16000)

    timeline = FragmentedTimeline(TMSection(1, 2, 0.5), TMSection(3, 4))
    timeline.time_scope = 5

    frame_audio = np.ones(buffer.audio.get_shape_for_data(5*16000), buffer.audio.dtype) * 255
    frame = av.AudioFrame.from_ndarray(AudioBuffer.reformat(frame_audio, buffer.format),
                                       buffer.format.name, buffer.layout.name)
    frame.pts = 16000
    frame.sample_rate = buffer.sample_rate
    frame.time_base = Fraction(1, buffer.sample_rate)

    mapping_results, _ = timeline.map_time_range(0, 5)
    buffer.stage(frame, mapping_results)
    buffer.put(audio_data)
