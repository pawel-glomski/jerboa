from typing import Callable

import av
import errno
import numpy as np

from jerboa.media.core import AudioConfig, VideoConfig
from jerboa.media import jb_to_av


class AudioReformatter:
    def __init__(self, config: AudioConfig):
        self._sample_rate = config.sample_rate
        self._av_format = jb_to_av.audio_sample_format(config.sample_format)
        self._av_channel_layout = jb_to_av.audio_channel_layout(config.channel_layout)
        if config.frame_duration:
            self._frame_size = round(config.frame_duration * config.sample_rate)
        else:
            self._frame_size = None

        self._has_samples = True  # set to True, to trigger resampler creation at `reset()``
        self.reset()

    def reset(self) -> None:
        if self._has_samples:
            self._has_samples = False
            self._resampler = av.AudioResampler(
                format=self._av_format,
                layout=self._av_channel_layout,
                rate=self._sample_rate,
                frame_size=self._frame_size,
            )

    def reformat(self, frame: av.AudioFrame | None) -> list[av.AudioFrame]:
        if frame is not None:
            # remove this assert when av.AudioResampler if fixed
            assert frame.time_base.numerator == 1
            self._has_samples = True

        return self._resampler.resample(frame)


class VideoReformatter:
    def __init__(self, config: VideoConfig):
        self._config = config
        self._reformatter: Callable[[av.VideoFrame], av.VideoFrame] | None = None

        # filter graph is quite slow and lot of time is spent waiting for the output frame.
        # Thus we could delegate the waiting task to another thread and return a future instead.
        # This speeds up the pipeline by ~25% on a test video, on my machine, on a single-threaded
        # test.

        # from concurrent.futures import ThreadPoolExecutor
        # self._thread_pool = ThreadPoolExecutor(1)

    def reset(self) -> None:
        # just like in the case of the AudioReformatter, filter graph does not accept frames after
        # the flushing frame (None), thus we would have to re-create it each time.
        # But since video reformatting is stateless, we can just omit flushing and reuse the filter
        # graph.
        pass  # self._reformatter = None

    def reformat(self, frame: av.VideoFrame) -> av.VideoFrame:
        assert frame is not None, "VideoReformatter cannot be flushed"

        if self._reformatter is None:
            self._reformatter = self._create_reformatter(frame)
        return self._reformatter(frame)
        # return self._thread_pool.submit(self._reformatter, frame)

    def _create_reformatter(self, frame_template: av.VideoFrame) -> av.filter.Graph:
        def get_planes(frame: av.VideoFrame):
            return [np.frombuffer(plane, dtype=np.ubyte) for plane in frame.planes]

        out_pixel_format_av = jb_to_av.video_pixel_format(self._config.pixel_format)

        if frame_template.format.name == out_pixel_format_av.name:
            return get_planes

        graph = self._create_filter_graph(frame_template, out_pixel_format_av)

        def filter_graph_reformatter(frame_in: av.VideoFrame):
            graph.push(frame_in)
            frame_out = get_planes(VideoReformatter._pull_from_filter_graph(graph))
            return frame_out

        return filter_graph_reformatter

    def _create_filter_graph(
        self,
        frame_template: av.VideoFrame,
        out_pixel_format_av: str,
    ) -> tuple[av.filter.context.FilterContext, av.filter.context.FilterContext]:
        graph = av.filter.Graph()

        time_base = frame_template.time_base
        sample_aspect_ratio = self._config.sample_aspect_ratio

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
            pix_fmts=out_pixel_format_av.name,
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
