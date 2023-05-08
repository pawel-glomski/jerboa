import av
import numpy as np
from collections import deque
from dataclasses import dataclass

from jerboa.timeline import RangeMappingResult


@dataclass
class VideoFrame:
  timepoint: float
  duration: float
  image_data: np.ndarray


class VideoBuffer:

  def __init__(self, fmt: av.VideoFormat, max_duration: float) -> None:
    self._format = fmt
    self._max_duration = max_duration

    self._frames = deque[VideoFrame]()
    self._staged_frame: VideoFrame | None = None
    self._duration = 0.0

  def __len__(self) -> int:
    return len(self._frames)

  def clear(self) -> None:
    self.clear_stage()
    self._frames.clear()
    self._duration = 0.0

  def clear_stage(self) -> None:
    self._staged_frame = None

  def stage(self, frame: av.VideoFrame, mapping_results: RangeMappingResult) -> None:
    if self._staged_frame is not None:
      raise RuntimeError('Buffer stage was not properly cleared!')

    image_data: np.ndarray = frame.to_ndarray(self._format)
    frame = VideoFrame(mapping_results.beg, mapping_results.end - mapping_results.beg, image_data)

    self._staged_frame = frame

  def commit(self) -> None:
    if self._staged_frame is not None:
      self._frames.append(self._staged_frame)
      self._duration += self._staged_frame.duration
      self._staged_frame = None

  def pop(self) -> np.ndarray:
    frame = self._frames.popleft()
    self._duration -= frame.duration
    self._duration *= (not self.is_empty())  # ensures _duration == 0 when empty
    return frame.image_data

  def get_current_timepoint(self) -> float:
    return self._frames[0].timepoint

  def is_empty(self) -> bool:
    return len(self) == 0

  def is_full(self) -> bool:
    return self._duration >= self._max_duration