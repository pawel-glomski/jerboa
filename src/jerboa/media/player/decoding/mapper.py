from jerboa.core.circular_buffer import create_circular_audio_buffer
from jerboa.media import standardized_audio as std_audio
from jerboa.media.core import AudioConfig
from .frame import PreMappedFrame, MappedAudioFrame, MappedVideoFrame


from concurrent import futures

MAX_DRIFT_FIX = 0.1  # 10%

RUBBERBAND_EXPECTED_DRIFT = 0.07  # in seconds
DRIFT_FIX_THRESHOLD = 0.05  # in seconds


class AudioMapper:
    def __init__(
        self,
        config: AudioConfig,
    ) -> None:
        assert config.sample_format == std_audio.SAMPLE_FORMAT_JB
        assert config.frame_duration is not None and config.frame_duration > 0

        self._config = config
        self._audio = create_circular_audio_buffer(
            dtype=config.sample_format.dtype,
            is_planar=config.sample_format.is_planar,
            channels_num=config.channels_num,
            sample_rate=config.sample_rate,
            max_duration=config.frame_duration,
        )
        # self._transition_steps = std_audio.get_transition_steps(audio_config.sample_rate)

        self._stretcher = std_audio.RubberBandStretcher(
            config.sample_rate,
            config.channels_num,
            std_audio.Option.PROCESS_REALTIME
            | std_audio.Option.ENGINE_FINER
            | std_audio.Option.WINDOW_SHORT,
        )
        self._stretcher.set_max_process_size(self._audio.max_size)

        self._thread_pool = futures.ThreadPoolExecutor(1)
        self._future = self._thread_pool.submit(lambda: None)

        self.reset()

    def reset(self) -> None:
        self._future.cancel()
        futures.wait([self._future])

        self._audio.clear()
        self._stretcher.reset()
        self._next_frame_beg_timepoint: float | None = None
        self._flushed = False
        self._drift = 0

    def map(self, frame: PreMappedFrame | None) -> MappedAudioFrame | None:
        if self._flushed:
            return None  # needs a reset

        futures.wait([self._future])

        flush = frame is None
        if flush:
            self._flushed = True
            if self._next_frame_beg_timepoint is not None:
                flushing_packet = std_audio.create_audio_array(
                    self._config.channels_num,
                    self._stretcher.get_samples_required(),
                )
                self._stretcher.process(flushing_packet, final=True)
                self._audio.put(self._stretcher.retrieve_available())
        else:

            def map_frame():
                drift_fix_modifier = 1.0
                if abs(self._drift) > DRIFT_FIX_THRESHOLD:
                    frame_duration = frame.mapping_scheme.end - frame.mapping_scheme.beg
                    fixed_duration = frame_duration + self._drift
                    fixed_duration = min(fixed_duration, frame_duration * (1 + MAX_DRIFT_FIX))
                    fixed_duration = max(fixed_duration, frame_duration * (1 - MAX_DRIFT_FIX))
                    drift_fix_modifier = fixed_duration / frame_duration

                # audio_data = std_audio.signal_from_av_frame(frame.av_frame)
                # self._stretcher.process(audio_data)
                # self._audio.put(self._stretcher.retrieve_available())
                for audio_section, section_modifier in self._cut_according_to_mapping_scheme(frame):
                    self._stretcher.time_ratio = section_modifier * drift_fix_modifier
                    self._stretcher.process(audio_section)
                    self._audio.put(self._stretcher.retrieve_available())

                if self._next_frame_beg_timepoint is None and len(self._audio) > 0:
                    self._next_frame_beg_timepoint = frame.mapping_scheme.beg

                self._drift = frame.mapping_scheme.end - (
                    self._next_frame_beg_timepoint + len(self._audio) / self._config.sample_rate
                )
                if self._drift > 0:
                    self._drift = max(0, self._drift - RUBBERBAND_EXPECTED_DRIFT)
                # print(f"{self._drift=:.4f}")

            self._future = self._thread_pool.submit(map_frame)

            # map_frame()

        if len(self._audio):
            assert self._next_frame_beg_timepoint is not None

            audio = self._audio.pop(len(self._audio))
            beg_timepoint = self._next_frame_beg_timepoint
            end_timepoint = beg_timepoint + std_audio.calc_duration(audio, self._config.sample_rate)
            self._next_frame_beg_timepoint = end_timepoint

            return MappedAudioFrame(
                beg_timepoint=beg_timepoint,
                end_timepoint=end_timepoint,
                audio_signal=audio,
            )
        return None

    def _cut_according_to_mapping_scheme(self, frame: PreMappedFrame):
        frame_audio = std_audio.signal_from_av_frame(frame.av_frame)
        for section in frame.mapping_scheme.sections:
            sample_idx_beg = round((section.beg - frame.beg_timepoint) * self._config.sample_rate)
            sample_idx_end = round((section.end - frame.beg_timepoint) * self._config.sample_rate)
            audio_section = frame_audio[std_audio.index_samples(sample_idx_beg, sample_idx_end)]
            if audio_section.size > 0:
                # std_audio.smooth_out_transition(audio_section)
                yield audio_section, section.modifier


class VideoMapper:
    def reset(self) -> None:
        pass

    def map(self, frame: PreMappedFrame | None) -> MappedVideoFrame | None:
        if frame is not None:
            assert (
                frame.mapping_scheme.end > frame.mapping_scheme.beg
            ), "Dropped frames should never appear here"

            return MappedVideoFrame(
                beg_timepoint=frame.mapping_scheme.beg,
                end_timepoint=frame.mapping_scheme.end,
                av_frame=frame.av_frame,
            )
        return None
