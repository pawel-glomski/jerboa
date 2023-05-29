from dataclasses import dataclass
from enum import Enum

import av


class MediaType(Enum):
  AUDIO = 'audio'
  VIDEO = 'video'


@dataclass
class AudioConfig:
  format: av.AudioFormat
  layout: av.AudioLayout
  sample_rate: int
  frame_duration: float | None = None

  @property
  def media_type(self) -> MediaType:
    return MediaType.AUDIO

  @property
  def channels_num(self) -> int:
    return len(self.layout.channels)


@dataclass
class VideoConfig:
  format: av.VideoFormat
  # add resolution?

  @property
  def media_type(self) -> MediaType:
    return MediaType.VIDEO
