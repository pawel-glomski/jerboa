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

  @staticmethod
  def from_stream(stream: av.audio.AudioStream) -> 'AudioConfig':
    if MediaType(stream.type) != MediaType.AUDIO:
      raise ValueError(f'Wrong stream type: {stream.type}')
    return AudioConfig(stream.format, stream.layout, stream.sample_rate)


@dataclass
class VideoConfig:
  format: av.VideoFormat

  @property
  def media_type(self) -> MediaType:
    return MediaType.VIDEO

  @staticmethod
  def from_stream(stream: av.video.VideoStream) -> 'VideoConfig':
    if MediaType(stream.type) != MediaType.VIDEO:
      raise ValueError(f'Wrong stream type: {stream.type}')
    return VideoConfig(stream.format)


def config_from_stream(stream: av.audio.AudioStream | av.video.VideoStream):
  if MediaType(stream.type) == MediaType.AUDIO:
    return AudioConfig.from_stream(stream)
  return VideoConfig.from_stream(stream)
