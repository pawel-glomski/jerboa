import av
import numpy as np

from typing import Generator
from pathlib import Path

from jerboa.media.media import AudioConfig
from jerboa.media.reformatters import AudioReformatter


class AudioReader:

  def __init__(self, config: AudioConfig = None):
    """Audio reader

    Args:
        config (optional):
          Configuration for the output audio format. If `None`, the audio will be provided in the
          same format as it is in the recording.
    """
    self._config = config
    if self._config is not None and self._config.frame_duration is None:
      # bigger frames are faster, less conversions to numpy and less iterations on the python side
      # usually 1 second gives good results, bigger than that may actually slow things down
      self._config.frame_duration = 1

  def read_stream(self, file_path: Path, stream_idx: int = 0) -> Generator[np.ndarray, None, None]:
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
        raise ValueError('No audio streams to read')

      if stream_idx >= len(container.streams.audio):
        raise IndexError(f'Bad audio stream index: {stream_idx=}, {len(container.streams.audio)=}')

      audio_stream = container.streams.audio[stream_idx]
      if self._config is None:
        config = AudioConfig(audio_stream.format, audio_stream.layout, audio_stream.sample_rate)
      else:
        config = self._config
      reformatter = AudioReformatter(config)

      for raw_frame in container.decode(audio_stream):
        for reformatted_frame in reformatter.reformat(raw_frame):
          yield reformatted_frame.to_ndarray()
