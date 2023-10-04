from collections.abc import Generator

from dataclasses import dataclass

from jerboa.media.core import MediaType, AudioConfig, VideoConfig, AudioStreamInfo, VideoStreamInfo
from .simple_decoder import SimpleDecoder, TimedFrame
from .util.reformatters import AudioReformatter, VideoReformatter, create_reformatter

SEEK_THRESHOLD = 0.25  # in seconds


@dataclass
class SkippingFrame(TimedFrame):
    skip_aware_beg_timepoint: float


class SkippingDecoder:
    def __init__(self, simple_decoder: SimpleDecoder):
        self._simple_decoder = simple_decoder
        self._reformatter: AudioReformatter | VideoReformatter | None = None

        if self.stream_info.media_type == MediaType.AUDIO:
            self.decode = self._decode_audio
        else:
            self.decode = self._decode_video

    @property
    def stream_info(self) -> AudioStreamInfo | VideoStreamInfo:
        return self._simple_decoder.stream_info

    @property
    def seek_threshold(self) -> float:
        return max(SEEK_THRESHOLD, self._simple_decoder.get_mean_keyframe_interval())

    def _decode_audio(
        self,
        seek_timepoint: float,
        media_config: AudioConfig,
    ) -> Generator[SkippingFrame, float, None]:
        self._init_reformatter(media_config)
        reformatter: AudioReformatter = self._reformatter

        skip_timepoint = seek_timepoint
        for timed_frame in self._simple_decoder.decode(seek_timepoint):
            if timed_frame is None:
                reformatted_frames_src = reformatter.flush()
            elif timed_frame.end_timepoint > skip_timepoint:
                reformatted_frames_src = reformatter.reformat(timed_frame.av_frame)
            else:
                reformatter.reset()
                reformatted_frames_src = []

            for reformatted_frame in reformatted_frames_src:
                skipping_frame = SkippingFrame(
                    reformatted_frame,
                    beg_timepoint=reformatted_frame.time,
                    end_timepoint=(
                        reformatted_frame.time
                        + reformatted_frame.samples / reformatted_frame.sample_rate
                    ),
                    skip_aware_beg_timepoint=max(skip_timepoint, reformatted_frame.time),
                )
                skip_timepoint = yield skipping_frame
                yield  # wait for the `next()` call of the for loop

    def _init_reformatter(
        self,
        media_config: AudioConfig | VideoConfig,
    ) -> Generator[SkippingFrame, float, None]:
        assert media_config.media_type == self.stream_info.media_type

        if self._reformatter is None or self._reformatter.config != media_config:
            self._reformatter = create_reformatter(media_config, self.stream_info)
        else:
            self._reformatter.reset()

    def _decode_video(
        self,
        seek_timepoint: float,
        media_config: VideoConfig,
    ) -> Generator[SkippingFrame, float, None]:
        self._init_reformatter(media_config)
        reformatter: VideoReformatter = self._reformatter

        skip_timepoint = seek_timepoint
        for timed_frame in self._simple_decoder.decode(seek_timepoint):
            if timed_frame is not None and timed_frame.end_timepoint > skip_timepoint:
                reformatted_av_frame = reformatter.reformat(timed_frame.av_frame)
                timed_frame = SkippingFrame(
                    reformatted_av_frame,
                    beg_timepoint=timed_frame.beg_timepoint,
                    end_timepoint=timed_frame.end_timepoint,
                    skip_aware_beg_timepoint=max(skip_timepoint, timed_frame.beg_timepoint),
                )
                skip_timepoint = yield timed_frame
                yield  # yield again to wait for the `next()` call of the for loop
