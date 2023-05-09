import math
from bisect import bisect_left
from typing import Generator
from dataclasses import dataclass


class TMSection:
  '''Represents a Timeline Modified Section - a timeline section with a duration modifier.'''

  def __init__(self, beg: float, end: float, modifier: float = 1.0):
    '''Initializes a `TMSection` instance.

    Args:
      beg (float): The beginning time of the section.
      end (float): The end time of the section.
      modifier (float): The duration modifier of the section (default 1.0).
    '''
    assert not math.isnan(end - beg), f'Invalid range values: ({beg}, {end})).'
    assert not math.isnan(modifier), f'Invalid modifier value: {modifier}).'
    assert beg <= end, f'The beginning must precede the end: ({beg}, {end}).'
    assert modifier >= 0.0, f'Section modifier cannot be negative: {modifier}.'

    self._beg = beg
    self._end = end
    self._modifier = modifier
    self._duration = self.modifier * (self.end - self.beg) if modifier else 0.0

  @property
  def beg(self) -> float:
    '''float: The beginning time of the section.'''
    return self._beg

  @property
  def end(self) -> float:
    '''float: The end time of the section.'''
    return self._end

  @property
  def modifier(self) -> float:
    '''float: The duration modifier of the section.'''
    return self._modifier

  @property
  def duration(self) -> float:
    '''float: The duration of the section, taking into account the duration modifier.'''
    return self._duration

  def __repr__(self) -> str:
    '''Returns a string representation of the section.'''
    return f'TMSection({self.beg=}, {self.end=}, {self.modifier=})'

  def __eq__(self, other: object) -> bool:
    '''Checks if two sections are equal.'''
    if isinstance(other, TMSection):
      return (self.beg == other.beg and self.end == other.end and self.modifier == other.modifier)
    return False

  def try_extending_with(self, other: 'TMSection') -> bool:
    '''If the other section is a direct continuation, extends this section.

    A TMSection is considered a direct continuation of another if its `beg` time is the same as the
    other's `end` time, and both sections have the same duration modifier.

    Args:
      other (TMSection): The section to extend to.

    Returns:
      bool: True if the section was extended, False otherwise.
    '''
    if self.end == other.beg and self.modifier == other.modifier:
      self._end = other.end
      self._duration += other.duration
      return True
    return False

  def overlap(self, beg, end) -> 'TMSection':
    '''Returns a new `TMSection` instance representing the overlap between the current section
    and the given time range.

    The new section will have the same modifier as the original section.

    Args:
      beg (float): The beginning time of the range.
      end (float): The end time of the range.

    Returns:
      TMSection: The new `TMSection` instance representing the overlap, `beg` == `end` when there is
      no overlap.
    '''
    beg = max(self.beg, beg)
    end = max(beg, min(self.end, end))  # end == beg when the section does not overlap the range
    return TMSection(beg, end, self.modifier)


@dataclass
class RangeMappingResult:
  beg: float  # The mapped beginning of the range.
  end: float  # The mapped ending of the range.
  sections: list[TMSection]  # A list of sections that overlapped the time range.


class FragmentedTimeline:
  '''Represents a timeline that is made up of sections, where each section can have different
  duration modifier (different playback speed).

  Note:
    The timeline sections must be added in ascending order by their beginning time.
  '''

  def __init__(self, *init_sections: tuple[TMSection]) -> None:
    '''Initialize a new FragmentedTimeline instance.

    Args:
      *init_sections (tuple[TMSection]): Optional initial sections to add to the timeline.
    '''
    self._sections: list[TMSection] = []
    self._resulting_timepoints: list[float] = []
    self._time_scope = -math.inf

    for section in init_sections:
      self.append_section(section)

  def __len__(self) -> int:
    return len(self._sections)

  def __iter__(self) -> Generator[tuple[TMSection, float], None, None]:
    for idx in range(len(self)):
      yield self[idx]

  def __getitem__(self, idx: int) -> tuple[float, float]:
    return (self._sections[idx], self._resulting_timepoints[idx])

  @property
  def time_scope(self) -> float:
    '''Getter for the time scope of the timeline, which represents the maximum timepoint for which
    the mapping is defined for the timeline.

    Returns:
      float: the time scope of the timeline
    '''

    return self._time_scope

  @time_scope.setter
  def time_scope(self, new_value):
    '''Setter for the timeline's scope in seconds. This operation must always extend the scope.

    Args:
      new_value (float): The new time scope to set.

    Raises:
      AssertionError: If `new_value` does not extend the current scope.
    '''
    if new_value < self._time_scope:
      raise ValueError(f'Scope cannot decrease: {self._time_scope=}, {new_value=}')
    self._time_scope = new_value

  def append_section(self, section: TMSection) -> None:
    '''
    Appends a new section to the timeline.

    Args:
      section (TMSection): The section to be appended. Must follow the existing sections.

    Raises:
      AssertionError: If the new section precedes existing sections or it overlaps the current
      time scope (which it should always extend).
    '''
    if self._sections and section.beg < self._sections[-1].end:
      raise ValueError(f'Section ({section}) precedes existing sections ({self._sections[-1]=})')
    if section.beg < self.time_scope:
      raise ValueError(f'Section ({section}) precedes the time scope ({self.time_scope})')

    if section.beg < 0:
      section = TMSection(0, section.end, section.modifier)

    self.time_scope = section.end
    section_duration = section.duration
    if section_duration > 0:
      if self._sections and self._sections[-1].try_extending_with(section):
        self._resulting_timepoints[-1] += section_duration
      else:
        self._sections.append(section)
        last_timepoint = self._resulting_timepoints[-1] if self._resulting_timepoints else 0.0
        self._resulting_timepoints.append(last_timepoint + section_duration)

  # TODO(OPT): optimize for frequent sequential checks
  def unmap_timepoint_to_source(self, mapped_timepoint: float) -> float | None:
    '''Unmaps a timepoint from the resulting timeline to its source timeline counterpart.

    Args:
      mapped_timepoint (float): The timepoint to be unmapped.

    Returns:
      float | None: The unmapped timepoint if the timepoint was valid; None otherwise.
    '''
    if self._resulting_timepoints:
      mapped_timepoint = max(0, mapped_timepoint)
      idx = bisect_left(self._resulting_timepoints, mapped_timepoint)
      if idx < len(self._resulting_timepoints):
        scale = 1.0 / self._sections[idx].modifier
        beg_src = self._resulting_timepoints[idx - 1] if idx > 0 else 0.0
        return self._sections[idx].beg + scale * (mapped_timepoint - beg_src)
      if self.time_scope == math.inf:
        return self._sections[-1].end
    return None

  # TODO(OPT): optimize for frequent sequential checks
  def map_time_range(self, beg: float, end: float) -> tuple[RangeMappingResult, float]:
    '''Maps a time range to the resulting timeline.

    This method maps a time range specified by its beginning and ending timepoints in the source
    timeline to the corresponding range in the resulting timeline.
  
    Args:
      beg (float): The beginning of the time range to be mapped.
      end (float): The ending of the time range to be mapped.

    Returns:
      tuple[RangeMappingResult, float]: A tuple of 2 values:\n
        0: (RangeMappingResult) Results of the mapping.\n
        1: (float) The next closest timepoint that can be mapped after the range ends. If such a
        timepoint does not exist in the current time scope, it returns the scope itself.

    Raises:
      AssertionError: If the beginning timepoint is greater than the ending timepoint, or if the
      end of the range is beyond the timeline's scope.
    '''
    beg = max(0, beg)
    if beg > end:
      raise ValueError(f'The beginning must precede the end ({beg}, {end}).')
    if end > self.time_scope:
      raise ValueError(f'Range out of scope: ({beg}, {end}), {self.time_scope=}.')

    involved_sections = list[TMSection]()
    idx = bisect_left(self._sections, beg, key=lambda s: s.end)  # TODO(OPT): don't use key
    if idx >= len(self._sections):
      mapped_beg = self._sections[-1].end if self._sections else 0
      mapped_end = mapped_beg
      next_timepoint = self.time_scope
    else:
      mapped_beg = self._resulting_timepoints[idx - 1] if idx > 0 else 0.0
      mapped_beg += self._sections[idx].modifier * max(0, beg - self._sections[idx].beg)
      mapped_end = mapped_beg

      while idx < len(self._sections) and end > self._sections[idx].beg:
        involved_sections.append(self._sections[idx].overlap(beg, end))
        mapped_end += involved_sections[-1].duration
        idx += 1
      assert all(s.duration > 0.0 for s in involved_sections)

      if end < self._sections[idx - 1].end:
        next_timepoint = end
      elif idx < len(self._sections):
        next_timepoint = self._sections[idx].beg
      else:
        next_timepoint = self._time_scope

    return (RangeMappingResult(mapped_beg, mapped_end, involved_sections), next_timepoint)
