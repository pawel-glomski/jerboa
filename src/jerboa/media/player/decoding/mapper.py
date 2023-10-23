import av
from dataclasses import dataclass
from pylibrb import RubberBandStretcher, Option

from jerboa.media import standardized_audio as std_audio
from jerboa.media.core import MediaType, AudioConfig, VideoConfig
from jerboa.core.timeline import RangeMappingResult
from .buffer import JbAudioFrame, JbVideoFrame, create_audio_circular_buffer


@dataclass
class TimedFrame:
    av_frame: av.AudioFrame | av.VideoFrame
    beg_timepoint: float
    end_timepoint: float


@dataclass
class PreMappedFrame:
    timed_frame: TimedFrame
    mapping_scheme: RangeMappingResult | None = None


class AudioMapper:
    def __init__(
        self,
        intermediate_config: AudioConfig,
        presentation_config: AudioConfig,
    ) -> None:
        self._intermediate_config = intermediate_config
        self._presentation_config = presentation_config
        self._audio = create_audio_circular_buffer(intermediate_config)
        # self._transition_steps = std_audio.get_transition_steps(audio_config.sample_rate)

        self._stretcher = RubberBandStretcher(
            intermediate_config.sample_rate,
            intermediate_config.channel_layout.channels_num,
            Option.PROCESS_REALTIME | Option.ENGINE_FINER | Option.WINDOW_SHORT,
        )
        self._stretcher.set_max_process_size(self._audio.max_size)
        self._last_frame_end_timepoint = None
        self._flushed = False
        self.reset()

    def reset(self) -> None:
        self._audio.clear()
        self._stretcher.reset()
        self._last_frame_end_timepoint = None
        self._flushed = False

    def map(self, frame: PreMappedFrame | None) -> JbAudioFrame | None:
        if self._flushed:
            return None  # needs a reset

        flush = frame is None
        if flush:
            if self._last_frame_end_timepoint is not None:
                flushing_packet = std_audio.create_audio_array(
                    self._intermediate_config.channel_layout.channels_num,
                    self._stretcher.get_samples_required(),
                )
                self._stretcher.process(flushing_packet, final=True)
                self._audio.put(self._stretcher.retrieve_available())
                self._flushed = True
        else:
            for audio_segment, modifier in self._cut_according_to_mapping_scheme(frame):
                self._stretcher.time_ratio = modifier
                self._stretcher.process(audio_segment)
                self._audio.put(self._stretcher.retrieve_available())

            if self._last_frame_end_timepoint is None and len(self._audio) > 0:
                self._last_frame_end_timepoint = frame.mapping_scheme.beg

        if len(self._audio) > 0:
            assert self._last_frame_end_timepoint is not None

            audio = self._audio.pop(len(self._audio))
            beg_timepoint = self._last_frame_end_timepoint
            duration = std_audio.calc_duration(audio, self._intermediate_config.sample_rate)
            self._last_frame_end_timepoint = beg_timepoint + duration

            real_audio_data = std_audio.to_real_audio(
                audio, self._presentation_config.sample_format
            )
            return JbAudioFrame(
                timepoint=beg_timepoint,
                duration=duration,
                signal=real_audio_data,
            )
        return None

    def _cut_according_to_mapping_scheme(self, frame: PreMappedFrame):
        frame_audio = std_audio.get_from_frame(frame.timed_frame.av_frame)
        for section in frame.mapping_scheme.sections:
            sample_idx_beg = round(
                (section.beg - frame.timed_frame.beg_timepoint)
                * self._intermediate_config.sample_rate
            )
            sample_idx_end = round(
                (section.end - frame.timed_frame.beg_timepoint)
                * self._intermediate_config.sample_rate
            )
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

    def map(self, frame: PreMappedFrame | None) -> JbVideoFrame | None:
        if frame is not None:
            av_frame = frame.timed_frame.av_frame
            mapping_scheme = frame.mapping_scheme
            duration = mapping_scheme.end - mapping_scheme.beg
            if duration > 0:
                return JbVideoFrame(
                    timepoint=mapping_scheme.beg,
                    duration=duration,
                    width=av_frame.width,
                    height=av_frame.height,
                    planes=[bytes(plane) for plane in av_frame.planes],
                )
        return None


def create_mapper(
    intermediate_config: AudioConfig | VideoConfig,
    presentation_config: AudioConfig | VideoConfig,
) -> AudioMapper | VideoMapper:
    if intermediate_config.media_type == MediaType.AUDIO:
        return AudioMapper(
            intermediate_config=intermediate_config,
            presentation_config=presentation_config,
        )
    return VideoMapper(presentation_config)
