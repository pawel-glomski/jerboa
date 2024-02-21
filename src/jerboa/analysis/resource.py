# Jerboa - AI-powered media player
# Copyright (C) 2024 Paweł Głomski

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


# import multiprocessing as mp
import typing as T

import jerboa.media.standardized_audio as std_audio
from jerboa.core.timeline import FragmentedTimeline, TMSection
from jerboa.media.source import MediaSource, MediaStreamSource, AudioFeatures
from jerboa.media.core import MediaType, AudioConfig, AudioChannelLayout
from jerboa.media.player.decoding import context, circular_buffer, node
from jerboa.media.player.decoding.frame import TimedAVFrame, JbAudioFrame

asfsadf = 123

AUDIO_CONFIG = AudioConfig(
    sample_format=std_audio.SAMPLE_FORMAT_JB,
    channel_layout=AudioChannelLayout.LAYOUT_MONO,
    sample_rate=16000,
    frame_duration=2,  # in seconds
)
AUDIO_PROC_HOP_SIZE = 160  # = 100 samples in a second
AUDIO_PROC_FRAME_SIZE = AUDIO_PROC_HOP_SIZE * 2


class AudioResource:
    def __init__(self, audio_source: MediaStreamSource):
        audio_path = audio_source.find_closest_variant_group(
            AudioFeatures(channels=AUDIO_CONFIG.channels_num, sample_rate=AUDIO_CONFIG.sample_rate)
        )[-1].path

        avc = context.AVContext.open(audio_path, media_type=MediaType.AUDIO, stream_idx=0)
        self._decoding_context = context.DecodingContext(
            context.MediaContext(
                avc,
                intermediate_config=AUDIO_CONFIG,
                presentation_config=AUDIO_CONFIG,
            ),
            timeline=FragmentedTimeline(init_sections=[TMSection(0, float("inf"), modifier=1)]),
        )

        # TODO: add multi-processing caching node for online media
        self._decoding_graph = node.AudioIntermediateReformattingNode(
            parent=node.SemiAccurateSeekNode(
                parent=node.TimedAudioFrameCreationNode(
                    parent=node.AudioFrameTimingCorrectionNode(
                        parent=node.DecodingNode(
                            parent=node.KeyframeIntervalWatcherNode(
                                parent=node.DemuxingNode(),
                            ),
                        ),
                    ),
                ),
            ),
        )
        self._decoding_graph.find_root_node().reset(
            context=self._decoding_context,
            reason=node.Node.ResetReason.NEW_CONTEXT,
            recursive=True,
        )

    def read(self, start_timepoint: float, frame_duration: float) -> T.Iterable[JbAudioFrame]:
        self._decoding_context.seek(start_timepoint)
        self._decoding_graph.find_root_node().reset(
            context=self._decoding_context,
            reason=node.Node.ResetReason.HARD_DISCONTINUITY,
            recursive=True,
        )

        buffer = circular_buffer.create_circular_audio_buffer(
            dtype=AUDIO_CONFIG.sample_format.data_type.dtype,
            is_planar=AUDIO_CONFIG.sample_format.is_planar,
            channels_num=AUDIO_CONFIG.channels_num,
            sample_rate=AUDIO_CONFIG.sample_rate,
            max_duration=frame_duration + AUDIO_CONFIG.frame_duration,
        )

        frame_size = int(frame_duration * AUDIO_CONFIG.sample_rate)
        last_timepoint = None

        while True:
            frame: TimedAVFrame | None = self._decoding_graph.pull_as_leaf(self._decoding_context)
            if frame is not None:
                if last_timepoint is None:
                    last_timepoint = frame.beg_timepoint
                buffer.put(std_audio.signal_from_av_frame(frame.av_frame))

            while len(buffer) >= frame_size or (frame is None and len(buffer) > 0):
                audio_signal = buffer.pop(min(len(buffer), frame_size))
                end_timepoint = last_timepoint + std_audio.calc_duration(
                    audio_signal, AUDIO_CONFIG.sample_rate
                )
                yield JbAudioFrame(
                    beg_timepoint=last_timepoint,
                    end_timepoint=end_timepoint,
                    audio_signal=audio_signal,
                )
                last_timepoint = end_timepoint
            if frame is None:
                break


class ResourceManager:
    def __init__(self):
        self._media_source: MediaSource | None = None
        # self._sync_manager = mp.Manager()  # this can take a while in debug mode (~2 seconds)

    def set_media_source(self, media_source: MediaSource) -> None:
        # TODO: invalidate previous resources
        self._media_source = media_source

    def get_audio_resource(self) -> AudioResource | None:
        assert self._media_source is not None
        if self._media_source.audio.is_available:
            return AudioResource(self._media_source.audio)
        return None
