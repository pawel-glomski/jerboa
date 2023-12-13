from collections import deque

from jerboa.media.core import MediaType, AudioConfig, VideoConfig
from .circular_buffer import create_circular_audio_buffer
from .frame import JbAudioFrame, JbVideoFrame


AUDIO_BUFFER_SIZE_MODIFIER = 1.2


class AudioBuffer:
    def __init__(self, audio_config: AudioConfig, max_duration: float):
        self._audio_config = audio_config

        self._audio = create_circular_audio_buffer(
            dtype=audio_config.sample_format.dtype,
            is_planar=audio_config.sample_format.is_planar,
            channels_num=audio_config.channels_num,
            sample_rate=audio_config.sample_rate,
            max_duration=max_duration,
        )
        # self._audio_last_sample = np.zeros(self._audio.get_shape_for_data(1), self._audio.dtype)
        self._current_timepoint: float | None = None

        self._max_samples = int(max_duration * audio_config.sample_rate)

    def __len__(self) -> int:
        return len(self._audio)

    @property
    def duration(self) -> float:
        return len(self._audio) / self._audio_config.sample_rate

    @property
    def current_timepoint(self) -> float | None:
        return self._current_timepoint

    def clear(self) -> None:
        self._audio.clear()
        self._current_timepoint = None
        # self._audio_last_sample[:] = 0

    def put(self, audio_frame: JbAudioFrame) -> None:
        assert not self.is_full()

        self._audio.put(audio_frame.audio_signal)
        # self._audio_last_sample[:] = self._audio[-1]

        if self._current_timepoint is None:
            self._current_timepoint = audio_frame.beg_timepoint

    def pop(self, samples_num: int) -> JbAudioFrame:
        assert not self.is_empty()

        all_samples_num = len(self._audio)
        pop_samples_num = min(all_samples_num, samples_num)

        audio_signal = self._audio.pop(pop_samples_num)
        audio_duration = pop_samples_num / self._audio_config.sample_rate

        frame = JbAudioFrame(
            beg_timepoint=self._current_timepoint,
            end_timepoint=self._current_timepoint + audio_duration,
            audio_signal=audio_signal,
        )
        self._current_timepoint = frame.end_timepoint

        return frame

    def is_empty(self) -> bool:
        return len(self) == 0

    def is_full(self) -> bool:
        return len(self) >= self._max_samples


class VideoBuffer:
    def __init__(self, max_duration: float):
        self._max_duration = max_duration
        self._duration = 0.0
        self._current_timepoint: float | None = None

        self._frames = deque[JbVideoFrame]()

    def __len__(self) -> int:
        return len(self._frames)

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def current_timepoint(self) -> float | None:
        return self._current_timepoint

    def clear(self) -> None:
        self._frames.clear()
        self._duration = 0.0
        self._current_timepoint = None

    def put(self, video_frame: JbVideoFrame) -> None:
        assert not self.is_full()

        self._duration += video_frame.duration
        self._frames.append(video_frame)

        if self._current_timepoint is None:
            self._current_timepoint = video_frame.beg_timepoint

    def pop(self) -> JbVideoFrame:
        assert not self.is_empty()

        frame = self._frames.popleft()
        self._duration -= frame.duration
        self._duration *= not self.is_empty()  # ensure `_duration == 0` when `is_empty() == true`

        self._current_timepoint = frame.end_timepoint

        return frame

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
