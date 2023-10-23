import numpy as np
from collections import deque
from dataclasses import dataclass

from jerboa.core.circular_buffer import CircularBuffer
from jerboa.media import jb_to_av, standardized_audio as std_audio
from jerboa.media.core import MediaType, AudioConfig, VideoConfig

AUDIO_BUFFER_SIZE_MODIFIER = 1.2


@dataclass
class JbFrame:
    timepoint: float | None = None
    duration: float | None = None

    def is_valid(self) -> bool:
        return (self.timepoint is not None and self.timepoint >= 0) and (
            self.duration is not None and self.duration > 0
        )


@dataclass
class JbAudioFrame(JbFrame):
    signal: np.ndarray | None = None

    def is_valid(self) -> bool:
        return super().is_valid() and self.signal is not None and self.signal.size > 0


@dataclass
class JbVideoFrame(JbFrame):
    width: int | None = None
    height: int | None = None
    planes: list[bytes] | None = None

    def is_valid(self) -> bool:
        return (
            super().is_valid()
            and all(attr is not None and attr > 0 for attr in [self.width, self.height])
            and self.planes is not None
            and len(self.planes) > 0
        )


class AudioBuffer:
    def __init__(self, audio_config: AudioConfig, max_duration: float) -> None:
        self._audio_config = audio_config

        self._audio = create_audio_circular_buffer(audio_config, max_duration)
        # self._audio_last_sample = np.zeros(self._audio.get_shape_for_data(1), self._audio.dtype)
        self._timepoint = None

        self._max_samples = int(max_duration * audio_config.sample_rate)

    def __len__(self) -> int:
        return len(self._audio)

    @property
    def duration(self) -> float:
        return len(self._audio) / self._audio_config.sample_rate

    def clear(self) -> None:
        self._audio.clear()
        # self._audio_last_sample[:] = 0
        self._timepoint = None

    def put(self, audio_frame: JbAudioFrame) -> None:
        assert audio_frame.is_valid()
        assert not self.is_full()

        if self._timepoint is None:
            self._timepoint = audio_frame.timepoint

        self._audio.put(audio_frame.signal)
        # self._audio_last_sample[:] = self._audio[-1]

    def pop(self, samples_num: int) -> JbAudioFrame:
        assert not self.is_empty()

        all_samples_num = len(self._audio)
        pop_samples_num = min(all_samples_num, samples_num)

        audio = self._audio.pop(pop_samples_num)
        audio_duration = pop_samples_num / self._audio_config.sample_rate

        frame = JbAudioFrame(
            timepoint=self._timepoint,
            duration=audio_duration,
            signal=audio,
        )

        self._timepoint += audio_duration
        return frame

    def get_next_timepoint(self) -> float | None:
        return self._timepoint

    def is_empty(self) -> bool:
        return len(self) == 0

    def is_full(self) -> bool:
        return len(self) >= self._max_samples


class VideoBuffer:
    def __init__(self, max_duration: float) -> None:
        self._max_duration = max_duration
        self._duration = 0.0

        self._frames = deque[JbVideoFrame]()

    def __len__(self) -> int:
        return len(self._frames)

    @property
    def duration(self) -> float:
        return self._duration

    def clear(self) -> None:
        self._frames.clear()
        self._duration = 0.0

    def put(self, video_frame: JbVideoFrame) -> None:
        assert video_frame.is_valid()
        assert not self.is_full()

        self._frames.append(video_frame)
        self._duration += video_frame.duration

    def pop(self) -> JbVideoFrame:
        assert not self.is_empty()

        frame = self._frames.popleft()
        self._duration -= frame.duration
        self._duration *= not self.is_empty()  # ensure `_duration == 0` when `is_empty() == true`
        return frame

    def get_next_timepoint(self) -> float:
        assert not self.is_empty()

        return self._frames[0].timepoint

    def is_empty(self) -> bool:
        return len(self) == 0

    def is_full(self) -> bool:
        return self._duration >= self._max_duration


def create_buffer(
    media_config: AudioConfig | VideoConfig, buffer_duration: float
) -> AudioBuffer | VideoBuffer:
    if media_config.media_type == MediaType.AUDIO:
        return AudioBuffer(media_config, max_duration=buffer_duration)
    return VideoBuffer(max_duration=buffer_duration)


def create_audio_circular_buffer(
    audio_config: AudioConfig, max_duration: float = None
) -> CircularBuffer:
    if max_duration is None and audio_config.frame_duration is None:
        raise ValueError("`max_duration` or `audio_config.frame_duration` must be provided")

    if max_duration is None:
        max_duration = audio_config.frame_duration

    buffer_dtype = jb_to_av.audio_sample_format_dtype(audio_config.sample_format)
    buffer_length = int(max_duration * audio_config.sample_rate * AUDIO_BUFFER_SIZE_MODIFIER)
    if audio_config.sample_format.is_planar:
        buffer_shape = [audio_config.channel_layout.channels_num, buffer_length]
        axis = 1
    else:
        buffer_shape = [buffer_length, audio_config.channel_layout.channels_num]
        axis = 0

    return CircularBuffer(buffer_shape, axis, buffer_dtype)
