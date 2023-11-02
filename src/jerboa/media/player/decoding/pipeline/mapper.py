from pylibrb import RubberBandStretcher, Option

from jerboa.core.circular_buffer import create_circular_audio_buffer
from jerboa.media import standardized_audio as std_audio
from jerboa.media.core import AudioConfig
from .frame import PreMappedFrame, MappedAudioFrame, MappedVideoFrame


from concurrent import futures


class AudioMapper:
    def __init__(
        self,
        config: AudioConfig,
    ) -> None:
        assert config.sample_format == std_audio.SAMPLE_FORMAT_JB

        self._config = config
        self._audio = create_circular_audio_buffer(config)
        # self._transition_steps = std_audio.get_transition_steps(audio_config.sample_rate)

        self._stretcher = RubberBandStretcher(
            config.sample_rate,
            config.channel_layout.channels_num,
            Option.PROCESS_REALTIME | Option.ENGINE_FASTER | Option.WINDOW_LONG,
        )
        self._stretcher.set_max_process_size(self._audio.max_size)
        self._next_frame_beg_timepoint = None
        self._flushed = False
        self.reset()

        self._thread_pool = futures.ThreadPoolExecutor(1)
        self._future: futures.Future = self._thread_pool.submit(lambda: None)

    def reset(self) -> None:
        self._audio.clear()
        self._stretcher.reset()
        self._next_frame_beg_timepoint = None
        self._flushed = False

    def map(self, frame: PreMappedFrame | None) -> MappedAudioFrame | None:
        if self._flushed:
            return None  # needs a reset

        futures.wait([self._future])

        flush = frame is None
        if flush:
            if self._next_frame_beg_timepoint is not None:
                flushing_packet = std_audio.create_audio_array(
                    self._config.channel_layout.channels_num,
                    self._stretcher.get_samples_required(),
                )
                self._stretcher.process(flushing_packet, final=True)
                self._audio.put(self._stretcher.retrieve_available())
                self._flushed = True
        else:

            def map_frame():
                for audio_segment, modifier in self._cut_according_to_mapping_scheme(frame):
                    self._stretcher.time_ratio = modifier
                    self._stretcher.process(audio_segment)
                    self._audio.put(self._stretcher.retrieve_available())

                if self._next_frame_beg_timepoint is None and len(self._audio) > 0:
                    self._next_frame_beg_timepoint = frame.mapping_scheme.beg

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

    def _create_mapped_frame(self) -> MappedAudioFrame:
        ...

    def _cut_according_to_mapping_scheme(self, frame: PreMappedFrame):
        frame_audio = std_audio.get_from_frame(frame.av_frame)
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
            av_frame = frame.av_frame
            mapping_scheme = frame.mapping_scheme
            duration = mapping_scheme.end - mapping_scheme.beg
            assert duration > 0, "Dropped frames should never appear here"

            return MappedVideoFrame(
                beg_timepoint=mapping_scheme.beg,
                end_timepoint=mapping_scheme.beg + duration,
                av_frame=av_frame,
            )
        return None
