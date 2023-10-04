from typing import Iterable, Callable

import av
import errno
from fractions import Fraction

from jerboa.media.core import MediaType, AudioConfig, VideoConfig, AudioStreamInfo, VideoStreamInfo


def jb_to_av_pixel_format(jb_format: VideoConfig.PixelFormat) -> str:
    match jb_format:
        case VideoConfig.PixelFormat.RGBA8888:
            return "rgba"
        case _:
            raise NotImplementedError()


class AudioReformatter:
    def __init__(self, config: AudioConfig, _: AudioStreamInfo):
        self._config = config
        if config.frame_duration:
            self._frame_size = round(config.frame_duration * self._config.sample_rate)
        else:
            self._frame_size = None
        self._resampler = av.AudioResampler(
            format=self._config.format,
            layout=self._config.layout,
            rate=self._config.sample_rate,
            frame_size=self._frame_size,
        )
        self._has_samples = False
        self.reset()

    def reset(self) -> None:
        if self._has_samples:
            self._resampler = av.AudioResampler(
                format=self._config.format,
                layout=self._config.layout,
                rate=self._config.sample_rate,
                frame_size=self._frame_size,
            )
            self._has_samples = False

    @property
    def config(self) -> AudioConfig:
        return self._config

    def reformat(self, frame: av.AudioFrame | None) -> Iterable[av.AudioFrame]:
        if frame is not None:
            # remove this assert when av.AudioResampler if fixed
            assert frame.time_base == Fraction(1, frame.sample_rate)
            self._has_samples = True

        for reformatted_frame in self._resampler.resample(frame):
            if reformatted_frame is not None:
                yield reformatted_frame

    def flush(self) -> Iterable[av.AudioFrame]:
        if self._has_samples:
            reformatted_frames = list(self.reformat(None))
            self.reset()
            for reformatted_frame in reformatted_frames:
                yield reformatted_frame


class VideoReformatter:
    def __init__(self, config: VideoConfig, stream_info: VideoStreamInfo):
        self._config = config
        self._stream_info = stream_info
        self._reformatter: Callable[[av.VideoFrame], av.VideoFrame] | None = None

    @property
    def config(self) -> VideoConfig:
        return self._config

    def reset(self) -> None:
        pass  # VideoReformatter is stateless

    def reformat(self, frame: av.VideoFrame | None) -> av.VideoFrame:
        if self._reformatter is None:
            self._reformatter = self._create_reformatter(frame)
        return self._reformatter(frame)

    def _create_reformatter(self, frame_template: av.VideoFrame) -> av.filter.Graph:
        out_pixel_format_av = jb_to_av_pixel_format(self.config.format)

        if frame_template.format.name == out_pixel_format_av:
            return lambda frame: frame

        graph = self._create_filter_graph(frame_template, out_pixel_format_av)

        def filter_graph_reformatter(frame: av.VideoFrame):
            graph.push(frame)
            return VideoReformatter._pull_from_filter_graph(graph)

        return filter_graph_reformatter

    def _create_filter_graph(
        self,
        frame_template: av.VideoFrame,
        out_pixel_format_av: str,
    ) -> av.filter.Graph:
        graph = av.filter.Graph()

        time_base = frame_template.time_base
        sample_aspect_ratio = self._stream_info.sample_aspect_ratio or Fraction(1, 1)

        buffer = graph.add(
            "buffer",
            width=str(frame_template.width),
            height=str(frame_template.height),
            pix_fmt=frame_template.format.name,
            time_base=f"{time_base.numerator}/{time_base.denominator}",
            sar=f"{sample_aspect_ratio.numerator}/{sample_aspect_ratio.denominator}",
        )

        format_filter = graph.add(
            "format",
            pix_fmts=out_pixel_format_av,
        )

        buffersink = graph.add("buffersink")

        buffer.link_to(format_filter)
        format_filter.link_to(buffersink)
        graph.configure()

        return graph

    @staticmethod
    def _pull_from_filter_graph(graph: av.filter.Graph):
        while True:
            try:
                return graph.pull()
            except EOFError:
                break
            except av.utils.AVError as e:
                if e.errno != errno.EAGAIN:
                    raise
                break
        return None


def create_reformatter(
    media_config: AudioConfig | VideoConfig,
    stream_info: AudioStreamInfo | VideoStreamInfo,
) -> AudioReformatter | VideoReformatter:
    assert media_config.media_type == stream_info.media_type

    if media_config.media_type == MediaType.AUDIO:
        return AudioReformatter(media_config, stream_info)
    return VideoReformatter(media_config, stream_info)
