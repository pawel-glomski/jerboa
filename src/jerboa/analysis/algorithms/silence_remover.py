from jerboa import analysis

from jerboa.media.readers.audio import AudioReader
from jerboa.media.core import AudioConfig, AudioChannelLayout, AudioSampleFormat

PROCESSING_AUDIO_SAMPLE_FORMAT = AudioSampleFormat(AudioSampleFormat.DataType.F32, is_planar=True)
PROCESSING_AUDIO_CHANNEL_LAYOUT = AudioChannelLayout.LAYOUT_MONO
PROCESSING_AUDIO_SAMPLE_RATE = 16000
PROCESSING_AUDIO_CONFIG = AudioConfig(
    sample_format=PROCESSING_AUDIO_SAMPLE_FORMAT,
    channel_layout=PROCESSING_AUDIO_CHANNEL_LAYOUT,
    sample_rate=PROCESSING_AUDIO_SAMPLE_RATE,
    frame_duration=None,  # use the default
)

PROCESSING_FRAME_SAMPLES = 1024


class Algorithm(analysis.algorithm.Algorithm):
    NAME = "Silence Remover"
    DESCRIPTION = "Removes silence. Very fast and very low memory requirements."

    db_threshold = analysis.parameter.Float(
        default_value=0.5,
        min_value=0,
        max_value=1,
        description="Determines what energy levels should be considered a silence",
        domain=analysis.parameter.Domain.INTERPRETATION,
    )
    db_threshold2 = analysis.parameter.Integer(
        default_value=2,
        min_value=2,
        max_value=10,
        description="Determines what energy levels should be considered a silence",
        domain=analysis.parameter.Domain.ANALYSIS,
    )

    db_threshold3 = analysis.parameter.String(
        default_value="abcd",
        description="Determines what energy levels should be considered a silence",
        domain=analysis.parameter.Domain.INTERPRETATION,
    )

    def initialize(self):
        self._audio_reader = AudioReader(PROCESSING_AUDIO_CONFIG)

    def interpret(self, file):
        for section in self._audio_reader.read_stream(file, stream_idx=0):
            ...

    def analyze(self):
        ...
