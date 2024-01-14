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


from typing import Iterable

from jerboa.core.timeline import FragmentedTimeline, TMSection
from jerboa.media.source import MediaSource, MediaStreamSource
from jerboa.media.core import MediaType, AudioConfig, AudioChannelLayout, AudioSampleFormat
from jerboa.media.readers.audio import AudioReader
from jerboa.media.player.decoding import context, node, frame as jbframe


AUDIO_SAMPLE_FORMAT = AudioSampleFormat(AudioSampleFormat.DataType.F32, is_planar=True)
AUDIO_CHANNEL_LAYOUT = AudioChannelLayout.LAYOUT_MONO
AUDIO_SAMPLE_RATE = 16000
AUDIO_CONFIG = AudioConfig(
    sample_format=AUDIO_SAMPLE_FORMAT,
    channel_layout=AUDIO_CHANNEL_LAYOUT,
    sample_rate=AUDIO_SAMPLE_RATE,
    frame_duration=None,  # use the default
)


class AudioResource:
    def __init__(self, audio_source: MediaStreamSource):
        self._audio_reader = AudioReader(AUDIO_CONFIG).read_stream(
            audio_source.selected_variant_group[0].path
        )
        audio_path = audio_source.selected_variant_group[0].path

        avc = context.AVContext.open(audio_path, media_type=MediaType.AUDIO, stream_idx=0)
        self._decoding_context = context.DecodingContext(
            context.MediaContext(
                avc,
                intermediate_config=AUDIO_CONFIG,
                presentation_config=AUDIO_CONFIG,
            ),
            timeline=FragmentedTimeline(init_sections=[TMSection(0, float("inf"), modifier=1)]),
        )

        # TODO: add caching node for online media
        self._decoding_graph = node.SemiAccurateSeekNode(
            parent=node.AudioIntermediateReformattingNode(
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

    def read(self, start_timepoint: float) -> Iterable[jbframe.TimedAVFrame]:
        self._decoding_context.seek(start_timepoint)
        while True:
            frame: jbframe.TimedAVFrame | None = self._decoding_graph.pull_as_leaf(
                self._decoding_context
            )
            if frame is not None:
                yield frame
            else:
                break


class ResourceManager:
    def __init__(self):
        self._media_source: MediaSource | None = None

    def set_media_source(self, media_source: MediaSource) -> None:
        # TODO: invalidate previous resources
        self._media_source = media_source

    def get_audio_resource(self) -> AudioResource:
        assert self._media_source is not None
        assert self._media_source.audio.is_available
        return AudioResource(self._media_source.audio)
