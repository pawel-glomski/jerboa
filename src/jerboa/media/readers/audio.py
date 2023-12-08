import av
import numpy as np

from typing import Iterable
from pathlib import Path

from jerboa.media import standardized_audio as std_audio
from jerboa.media.core import AudioConfig
from jerboa.media.player.decoding.reformatter import AudioReformatter


class AudioReader:
    def __init__(self, config: AudioConfig):
        """Audio reader

        Args:
            config (optional):
              Configuration for the output audio format.
        """
        self._config = config
        if self._config.frame_duration is None:
            self._config.frame_duration = std_audio.FRAME_DURATION

    def read_stream(self, file_path: Path, stream_idx: int = 0) -> Iterable[np.ndarray]:
        """Creates a generator of audio frames of a given audio stream in the recording

        Args:
        file_path:
            Path to the recording.
        stream_idx (int, optional):
            Considering only the audio streams, which stream should be read
            (0 -> the first audio stream, 1 -> the second audio stream). Defaults to 0.

        Returns:
        Tuple[Generator[np.ndarray, None, None], Dict[StreamInfo, object]]: A generator of the \
            audio frames and a dictionary with info about the stream
        """
        file_path = Path(file_path).resolve()

        with av.open(str(file_path)) as container:
            if len(container.streams.audio) == 0:
                raise ValueError("No audio streams to read")

            if stream_idx >= len(container.streams.audio):
                raise IndexError(
                    f"Bad audio stream index: {stream_idx=}, {len(container.streams.audio)=}"
                )
            container.streams.audio[stream_idx].thread_type = "AUTO"

            reformatter = AudioReformatter(self._config)
            for raw_frame in container.decode(container.streams.audio[stream_idx]):
                for reformatted_frame in reformatter.reformat(raw_frame):
                    yield reformatted_frame.to_ndarray()
