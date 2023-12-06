import math
from bisect import bisect_left
from dataclasses import dataclass, field

from jerboa.core.multithreading import RWLock, PredicateEmitter, Event


@dataclass(frozen=True, slots=True)
class TMSection:
    """Represents a Timeline Modified Section - a timeline section with a duration modifier."""

    beg: float
    end: float
    modifier: float = 1.0
    duration: float = field(init=False)

    def __post_init__(self):
        """Initializes a `TMSection` instance.

        Args:
            beg: The beginning time of the section.
            end: The end time of the section.
            modifier: The duration modifier of the section (default 1.0).
        """
        assert not math.isnan(self.end - self.beg)
        assert not math.isnan(self.modifier)
        assert self.beg <= self.end
        assert self.modifier >= 0.0

        # super() does not work with slots ¯\_(ツ)_/¯
        super(TMSection, self).__setattr__(
            "duration", (self.end - self.beg) * self.modifier if self.modifier != 0 else 0.0
        )

    def can_be_merged(self, other: "TMSection") -> bool:
        """If the other section is a direct continuation, extends this section.

        A TMSection is considered a direct continuation of another if it begins where the other
        ends, and they share a common modifier.

        Args:
            other: The section to extend to.

        Returns:
            True if the section was extended, False otherwise.
        """
        return (
            max(self.beg, other.beg) <= min(self.end, other.end) and self.modifier == other.modifier
        )

    def merged(self, other: "TMSection") -> "TMSection | None":
        if self.can_be_merged(other):
            return TMSection(beg=self.beg, end=max(self.end, other.end), modifier=self.modifier)
        return None

    def overlap(self, beg: float, end: float) -> "TMSection":
        """Returns a new `TMSection` instance representing the overlap between the current section
        and the given time range.

        The new section will have the same modifier as the original section.

        Args:
            beg: The beginning time of the range.
            end: The end time of the range.

        Returns:
            A new `TMSection` instance representing the overlap. `beg` == `end` when there is
            no overlap.
        """
        beg = max(self.beg, beg)
        end = max(beg, min(self.end, end))
        return TMSection(beg=beg, end=end, modifier=self.modifier)


@dataclass(frozen=True, slots=True)
class RangeMappingResult:
    beg: float  # The mapped beginning of the range.
    end: float  # The mapped ending of the range.
    sections: list[TMSection]  # A list of sections that overlapped the time range.


class FragmentedTimeline:
    """Represents a timeline that is made up of sections, where each section can have different
    duration modifier (different playback speed).

    Note:
        The timeline sections must be added in ascending order by their beginning time.
    """

    def __init__(
        self,
        init_sections: list[TMSection] = None,
        mutex: RWLock = None,
    ) -> None:
        """Initialize a new FragmentedTimeline instance.

        Args:
            *init_sections: Optional initial sections to add to the timeline.
        """
        self._sections: list[TMSection] = []
        self._resulting_timepoints: list[float] = []
        self._time_scope = -math.inf

        self._mutex = mutex or RWLock()
        self._scope_extended = PredicateEmitter(
            lambda target_scope: self.time_scope >= target_scope
        )

        for section in init_sections or []:
            self.append_section(section)

    def __len__(self) -> int:
        return len(self._sections)

    @property
    def time_scope(self) -> float:
        """Getter for the time scope of the timeline, which represents the maximum timepoint for
        which the mapping is defined in the timeline.

        Returns:
            float: the time scope of the timeline
        """

        return self._time_scope

    def extend_time_scope(self, new_value: float):
        with self._mutex.as_writer():
            self._extend_time_scope__locked(new_value)

    def _extend_time_scope__locked(self, extended_scope: float):
        """Setter for the timeline's scope in seconds. This operation must always extend the scope.

        Args:
            new_value: The new time scope to set.

        Raises:
            AssertionError: If `new_value` does not extend the current scope.
        """
        if extended_scope < self._time_scope:
            raise ValueError(f"Scope cannot decrease: {self._time_scope=}, {extended_scope=}")
        if extended_scope > self._time_scope:
            self._time_scope = extended_scope
            self._scope_extended.evaluate_and_emit__locked()

    def get_sections(self) -> list[tuple[TMSection, float]]:
        with self._mutex.as_reader():
            return list(zip(self._sections, self._resulting_timepoints))

    def append_section(self, section: TMSection) -> None:
        """
        Appends a new section to the timeline.

        Args:
            section: The section to be appended. Must follow the existing sections.

        Raises:
            AssertionError: If the new section precedes existing sections or it overlaps the current
            time scope (which it should always extend).
        """
        with self._mutex.as_writer():
            if self._sections and section.beg < self._sections[-1].end:
                raise ValueError(
                    f"Section ({section}) precedes existing sections ({self._sections[-1]=})"
                )
            if section.beg < self.time_scope:
                raise ValueError(f"Section ({section}) precedes the time scope ({self.time_scope})")

            if section.beg < 0:
                section = TMSection(0, section.end, section.modifier)

            section_duration = section.duration
            if section_duration > 0:
                sections_merge = self._sections[-1].merged(section) if self._sections else None
                if sections_merge is not None:
                    self._sections[-1] = sections_merge
                    self._resulting_timepoints[-1] += section_duration
                else:
                    self._sections.append(section)
                    last_timepoint = (
                        self._resulting_timepoints[-1] if self._resulting_timepoints else 0.0
                    )
                    self._resulting_timepoints.append(last_timepoint + section_duration)

            self._extend_time_scope__locked(section.end)

    def unmap_timepoint_to_source(self, mapped_timepoint: float) -> float | None:
        """Unmaps a timepoint from the resulting timeline back to its source timeline counterpart.

        Args:
            mapped_timepoint: The timepoint to be unmapped.

        Returns:
            If the timepoint is in scope:
                The unmapped timepoint.
            Otherwise:
                `None`
        """
        with self._mutex.as_reader():
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

    def map_time_range(
        self,
        beg: float,
        end: float,
    ) -> tuple[RangeMappingResult, float] | tuple[None, None]:
        """Maps a time range to the resulting timeline.

        This method maps a time range specified by its beginning and ending timepoints in the source
        timeline to the corresponding range in the resulting timeline.

        Args:
            beg: The beginning of the time range to be mapped.

            end: The ending of the time range to be mapped.

        Returns:
            If the range is in scope, a tuple of 2 objects:
                0: Results of the mapping.
                1: The next closest timepoint that can be mapped after the range ends. If such a
                timepoint does not exist in the current time scope, it returns the scope itself.

            Otherwise:
                `(None, None)`
        """
        beg = max(0, beg)
        if beg > end:
            raise ValueError(f"The beginning must precede the end ({beg}, {end}).")

        with self._mutex.as_reader():
            if end > self.time_scope:
                return (None, None)

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
                    overlap_section = self._sections[idx].overlap(beg, end)
                    if overlap_section.duration > 0:
                        mapped_end += overlap_section.duration
                        involved_sections.append(overlap_section)
                    idx += 1

                if idx > 0 and end < self._sections[idx - 1].end:
                    next_timepoint = end
                elif idx < len(self._sections):
                    next_timepoint = self._sections[idx].beg
                else:
                    next_timepoint = self._time_scope

            return (RangeMappingResult(mapped_beg, mapped_end, involved_sections), next_timepoint)

    def create_scope_extended_event(self, target_scope: float) -> Event:
        with self._mutex.as_writer():
            return self._scope_extended.create_emit_event__locked(target_scope=target_scope)
