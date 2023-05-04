import math

import pytest

from jerboa.timeline import TMSection, FragmentedTimeline


class TestTMSection:

  @pytest.mark.parametrize("beg, end, modifier", [
      (0, 10, 1.0),
      (-10, 10, 2.0),
      (0, 0, 0.5),
  ])
  def test_should_create_new_instance_when_valid_input(self, beg, end, modifier):
    section = TMSection(beg, end, modifier)

    assert section.beg == beg
    assert section.end == end
    assert section.modifier == modifier

  @pytest.mark.parametrize("beg, end, modifier", [
      (10, 0, 1.0),
      (10, 0, -1.0),
      (0, 10, -1.0),
      (math.nan, 10, 1.0),
      (math.nan, 10, -1.0),
      (0, math.nan, 1.0),
      (0, math.nan, -1.0),
      (0, 10, math.nan),
  ])
  def test_should_raise_assertion_error_when_invalid_input(self, beg, end, modifier):
    with pytest.raises(AssertionError):
      TMSection(beg, end, modifier)

  @pytest.mark.parametrize("section1, section2, expected_section", [
      (
          TMSection(0, 10, 1.0),
          TMSection(10, 20, 1.0),
          TMSection(0, 20, 1.0),
      ),
      (
          TMSection(-10, 0, 2.0),
          TMSection(0, 10, 2.0),
          TMSection(-10, 10, 2.0),
      ),
      (
          TMSection(-math.inf, 0, 0),
          TMSection(0, 10, 0.0),
          TMSection(-math.inf, 10, 0),
      ),
      (
          TMSection(-math.inf, 10, 0),
          TMSection(10, math.inf, 0),
          TMSection(-math.inf, math.inf, 0),
      ),
      (
          TMSection(-math.inf, 10, 0.5),
          TMSection(10, math.inf, 0.5),
          TMSection(-math.inf, math.inf, 0.5),
      ),
  ])
  def test_try_extending_with_should_extend_to_expected_section_when_is_direct_continuation(
      self, section1: TMSection, section2: TMSection, expected_section: TMSection):
    assert section1.try_extending_with(section2) is True and section1 == expected_section

  @pytest.mark.parametrize("section1, section2", [
      (TMSection(-10, 10, 1.0), TMSection(-10, 10, 1.0)),
      (TMSection(5, 10, 1.0), TMSection(5, 15, 1.0)),
      (TMSection(6, 10, 0.5), TMSection(11, 15, 1.0)),
      (TMSection(7, 10, 2.0), TMSection(10, 15, 0.5)),
      (TMSection(8, 10, 1.0), TMSection(10, 15, 0.0)),
      (TMSection(0, 10, 1.0), TMSection(-10, 0, 1.0)),
  ])
  def test_try_extending_with_should_return_false_when_is_not_direct_continuation(
      self, section1: TMSection, section2: TMSection):
    section1_before = TMSection(section1.beg, section1.end, section1.modifier)
    assert section1.try_extending_with(section2) is False and section1 == section1_before

  @pytest.mark.parametrize("section, expected_duration", [
      (TMSection(0, 10, 1.0), 10),
      (TMSection(-10, 10, 2.0), 40),
      (TMSection(0, 100, 0.5), 50),
      (TMSection(0, 100, 0.0), 0),
      (TMSection(10, 10, 1.0), 0),
      (TMSection(0, math.inf, 0.0), 0),
      (TMSection(-math.inf, 0, 1.0), math.inf),
      (TMSection(0, math.inf, 0.5), math.inf),
      (TMSection(-math.inf, math.inf, 1.0), math.inf),
  ])
  def test_duration_should_return_expected_duration(self, section, expected_duration):
    assert section.duration == expected_duration

  @pytest.mark.parametrize("section, beg, end, expected_section", [
      (TMSection(0, 3, 2), 1, 2, TMSection(1, 2, 2)),
      (TMSection(1, 2, 2), 0, 3, TMSection(1, 2, 2)),
      (TMSection(1, 2, 1), 0, 3, TMSection(1, 2, 1)),
      (TMSection(0, 2, 1), 1, 3, TMSection(1, 2, 1)),
      (TMSection(0, 3, 1), 1, 2, TMSection(1, 2, 1)),
      (TMSection(1, 3, 1), 0, 2, TMSection(1, 2, 1)),
  ])
  def test_overlap_should_return_expected_section_for_overlapping_range(
      self,
      section: TMSection,
      beg: float,
      end: float,
      expected_section: TMSection,
  ):
    result = section.overlap(beg, end)

    assert result == expected_section

  @pytest.mark.parametrize("section, beg, end", [
      (TMSection(0, 1, 1), 2, 3),
      (TMSection(4, 5, 0.5), 2, 3),
  ])
  def test_overlap_should_return_empty_section_for_non_overlapping_range(
      self,
      section: TMSection,
      beg: float,
      end: float,
  ):
    result = section.overlap(beg, end)

    assert result.beg == result.end


# class TestFragmentedTimeline:
#   def test_modified_timeline():
#     timeline = FragmentedTimeline(TMSection(0, 3, 0.75), TMSection(4, 5, 0.5), TMSection(5, 20, 0.25))
#     timeline.map_timepoint_to_source(0)
#     timeline.map_timepoint_to_source(3.5)
#     timeline.map_time_range(1.5, 5)

#   def test_length_of_empty_set_should_be_zero():
#     timeline = FragmentedTimeline()
#     assert len(timeline) == 0

#   def test_accessing_invalid_range_should_throw():
#     timeline = FragmentedTimeline()

#     with pytest.raises(IndexError):
#       timeline.get(0)

#   #################################### add ####################################

#   @pytest.mark.parametrize('beg, end', [(1, 0), (float('nan'), 1), (0, float('nan'))])
#   def test_adding_invalid_range_to_empty_set_should_throw(beg, end):
#     timeline = FragmentedTimeline()

#     with pytest.raises(AssertionError):
#       timeline.add(beg, end)
#     assert len(timeline) == 0

#   def test_adding_valid_range_to_empty_set_should_succeed():
#     timeline = FragmentedTimeline((0, 1))

#     assert len(timeline) == 1
#     assert timeline[0] == (0, 1)

#   @pytest.mark.parametrize('beg, end, expected_idx', [(-2, -1, 0), (2, 3, 1)])
#   def test_adding_non_overlapping_range_should_add_new_range__one_range(beg, end, expected_idx):
#     timeline = FragmentedTimeline((0, 1))

#     timeline.add(beg, end)
#     assert len(timeline) == 2
#     assert timeline[expected_idx] == (beg, end)
#     assert timeline[0 if expected_idx == 1 else 1] == (0, 1)

#   @pytest.mark.parametrize('beg, end, expected_idx', [(-2, -1, 0), (2, 3, 1), (6, 7, 2)])
#   def test_adding_non_overlapping_range_should_add_new_range__many_ranges(beg, end, expected_idx):
#     timeline = FragmentedTimeline((0, 1), (4, 5))

#     timeline.add(beg, end)
#     assert len(timeline) == 3
#     assert timeline[expected_idx] == (beg, end)
#     assert timeline[0 if expected_idx > 0 else 1] == (0, 1)
#     assert timeline[2 if expected_idx < 2 else 1] == (4, 5)

#   @pytest.mark.parametrize('beg, end, expected_range', [
#       [-1, 2, (-1, 2)],
#       [-1, 1, (-1, 1)],
#       [0, 2, (0, 2)],
#       [0.5, 2, (0, 2)],
#       [1, 2, (0, 2)],
#       [0, 1, (0, 1)],
#       [0.25, 0.75, (0, 1)],
#       [0.5, 0.5, (0, 1)],
#       [0.0, 0.0, (0, 1)],
#       [1.0, 1.0, (0, 1)],
#   ])
#   def test_adding_overlapping_range_should_extend_existing_range__one_range(
#       beg, end, expected_range):
#     timeline = FragmentedTimeline((0, 1))

#     timeline.add(beg, end)
#     assert len(timeline) == 1
#     assert timeline[0] == expected_range

#   @pytest.mark.parametrize('beg, end, expected_ranges', [
#       [-1, 4, [(-1, 4)]],
#       [-1, 3, [(-1, 3)]],
#       [0, 6, [(0, 6)]],
#       [0.5, 2.5, [(0, 3)]],
#       [0, 2, [(0, 3)]],
#       [1, 2, [(0, 3)]],
#       [1, 3, [(0, 3)]],
#       [0.5, 1.5, [(0, 1.5), (2, 3)]],
#       [1, 1.5, [(0, 1.5), (2, 3)]],
#       [1.5, 2, [(0, 1), (1.5, 3)]],
#       [1.5, 2.5, [(0, 1), (1.5, 3)]],
#       [0, 0, [(0, 1), (2, 3)]],
#       [0.5, 0.5, [(0, 1), (2, 3)]],
#       [1, 1, [(0, 1), (2, 3)]],
#       [3, 3, [(0, 1), (2, 3)]],
#   ])
#   def test_adding_overlapping_range_should_extend_existing_ranges__many_ranges(
#       beg, end, expected_ranges):
#     timeline = FragmentedTimeline((0, 1), (2, 3))

#     timeline.add(beg, end)
#     assert len(timeline) == len(expected_ranges)
#     for observed_range, expected_range in zip(timeline, expected_ranges):
#       assert observed_range == expected_range

#   #################################### append ####################################

#   @pytest.mark.parametrize('beg, end', [(1, 0), (float('nan'), 1), (0, float('nan'))])
#   def test_append_invalid_range_to_empty_set_should_throw(beg, end):
#     timeline = FragmentedTimeline()

#     with pytest.raises(AssertionError):
#       timeline.append(beg, end)
#     assert len(timeline) == 0

#   def test_append_valid_range_to_empty_set_should_succeed():
#     timeline = FragmentedTimeline()

#     timeline.append(beg=0, end=1)
#     assert len(timeline) == 1
#     assert timeline[0] == (0, 1)

#   def test_append_non_overlapping_range_should_add_new_range__one_range():
#     timeline = FragmentedTimeline((0, 1))

#     timeline.append(beg=2, end=3)
#     assert len(timeline) == 2
#     assert timeline[0] == (0, 1)
#     assert timeline[1] == (2, 3)

#   def test_append_non_overlapping_range_should_add_new_range__many_ranges():
#     timeline = FragmentedTimeline((0, 1), (2, 3))

#     timeline.append(beg=4, end=5)
#     assert len(timeline) == 3
#     assert timeline[0] == (0, 1)
#     assert timeline[1] == (2, 3)
#     assert timeline[2] == (4, 5)

#   @pytest.mark.parametrize('beg, end', [
#       (-2, -1),
#       (-2, 2),
#       (-1, 0),
#       (-1, 0.5),
#       (-1, 1),
#       (-1, 2),
#   ])
#   def test_append_unordered_range_should_throw__one_range(beg, end):
#     timeline = FragmentedTimeline((0, 1))

#     with pytest.raises(AssertionError):
#       timeline.append(beg, end)

#   @pytest.mark.parametrize('beg', [-2, -1, 0, 0.25, 1, 1.25])
#   @pytest.mark.parametrize('end', [-1, 0, 0.5, 1, 1.5, 2, 3, 4])
#   def test_append_unordered_range_should_throw__many_ranges(beg, end):
#     if beg < end:
#       timeline = FragmentedTimeline((0, 1), (2, 3))

#       with pytest.raises(AssertionError):
#         timeline.append(beg, end)

#   @pytest.mark.parametrize('beg, end, expected_range', [
#       [0, 1, (0, 1)],
#       [0, 2, (0, 2)],
#       [0.5, 2, (0, 2)],
#       [1, 2, (0, 2)],
#   ])
#   def test_append_overlapping_range_should_extend_existing_range__one_range(
#       beg, end, expected_range):
#     timeline = FragmentedTimeline((0, 1))

#     timeline.add(beg, end)
#     assert len(timeline) == 1
#     assert timeline[0] == expected_range

#   @pytest.mark.parametrize('beg, end, expected_ranges', [
#       [2, 3, [(0, 1), (2, 3)]],
#       [2, 4, [(0, 1), (2, 4)]],
#       [2.5, 4, [(0, 1), (2, 4)]],
#       [3, 4, [(0, 1), (2, 4)]],
#   ])
#   def test_append_overlapping_range_should_extend_existing_ranges__many_ranges(
#       beg, end, expected_ranges):
#     timeline = FragmentedTimeline((0, 1), (2, 3))

#     timeline.add(beg, end)
#     assert len(timeline) == len(expected_ranges)
#     for observed_range, expected_range in zip(timeline, expected_ranges):
#       assert observed_range == expected_range

#   #################################### check_overlap ####################################

#   @pytest.mark.parametrize('beg, end', [(float('nan'), 0), (0, float('nan')),
#                                         (float('nan'), float('nan'))])
#   def test_check_overlap_with_invalid_values_should_throw(beg, end):
#     timeline = FragmentedTimeline()
#     with pytest.raises(AssertionError):
#       timeline.check_overlap(beg, end)

#   def test_check_overlap_with_empty_set_should_return_false():
#     timeline = FragmentedTimeline()
#     assert not timeline.check_overlap(beg=0, end=1)

#   @pytest.mark.parametrize('beg, end', [(-1, 0), (1, 2), (3, 6)])
#   def test_check_overlap_with_non_overlapping_range_should_return_false(beg, end):
#     timeline = FragmentedTimeline((0, 1))

#     assert not timeline.check_overlap(beg, end)

#   @pytest.mark.parametrize('beg, end, expected_result', [
#       (-1, 2, True),
#       (0, 0.5, True),
#       (0.25, 0.75, True),
#       (0.5, 0.5, True),
#       (0.0, 0.0, False),
#       (1, 1, False),
#       (-1, 0, False),
#       (1, 2, False),
#       (3, 6, False),
#   ])
#   def test_check_overlap_with_overlapping_range__one_range(beg, end, expected_result):
#     timeline = FragmentedTimeline((0, 1))

#     assert timeline.check_overlap(beg, end) == expected_result

#   @pytest.mark.parametrize('beg, end, expected_result', [
#       (-1, 2, True),
#       (0, 0.5, True),
#       (0.25, 0.75, True),
#       (4, 5, True),
#       (4.5, 5, True),
#       (-2, -1, False),
#       (-1, 0, False),
#       (2, 3, False),
#       (6, 7, False),
#   ])
#   def test_check_overlap_with_overlapping_range__many_ranges(beg, end, expected_result):
#     timeline = FragmentedTimeline((0, 1), (4, 5))

#     assert timeline.check_overlap(beg, end) == expected_result

#   #################################### sub ####################################

#   @pytest.mark.parametrize('beg, end', [(1, 0), (float('nan'), 1), (0, float('nan'))])
#   def test_subtracting_invalid_range_to_empty_set_should_throw(beg, end):
#     timeline = FragmentedTimeline()

#     with pytest.raises(AssertionError):
#       timeline.sub(beg, end)
#     assert len(timeline) == 0

#   def test_subtracting_valid_range_from_empty_set_should_do_nothing():
#     timeline = FragmentedTimeline()

#     timeline.sub(beg=0, end=1)
#     assert len(timeline) == 0

#   @pytest.mark.parametrize(
#       'beg, end, expected_ranges',
#       [
#           # overlapping
#           [-1, 2, []],
#           [-1, 1, []],
#           [0, 2, []],
#           [0, 1, []],
#           [-1, 0.5, [(0.5, 1)]],
#           [0.5, 2, [(0, 0.5)]],
#           [0.25, 0.75, [(0, 0.25), (0.75, 1)]],

#           # non-overlapping
#           [-2, -1, [(0, 1)]],
#           [-1, 0, [(0, 1)]],
#           [1, 2, [(0, 1)]],
#           [2, 3, [(0, 1)]],

#           # points
#           [0, 0, [(0, 1)]],
#           [0.5, 0.5, [(0, 1)]],
#           [1, 1, [(0, 1)]],
#       ])
#   def test_sub__one_range(beg, end, expected_ranges):
#     timeline = FragmentedTimeline((0, 1))

#     timeline.sub(beg, end)
#     assert len(timeline) == len(expected_ranges)
#     for observed_range, expected_range in zip(timeline, expected_ranges):
#       assert observed_range == expected_range

#   @pytest.mark.parametrize(
#       'beg, end, expected_ranges',
#       [
#           # overlapping
#           [-1, 4, []],
#           [-1, 3, []],
#           [0, 6, []],
#           [0.5, 2.5, [(0, 0.5), (2.5, 3)]],
#           [0, 2, [(2, 3)]],
#           [1, 3, [(0, 1)]],
#           [0.5, 1.5, [(0, 0.5), (2, 3)]],
#           [1.5, 2.5, [(0, 1), (2.5, 3)]],

#           # non-overlapping
#           [-2, -1, [(0, 1), (2, 3)]],
#           [-1, 0, [(0, 1), (2, 3)]],
#           [1, 2, [(0, 1), (2, 3)]],
#           [1.25, 1.75, [(0, 1), (2, 3)]],
#           [3, 4, [(0, 1), (2, 3)]],
#           [4, 5, [(0, 1), (2, 3)]],

#           # points
#           [0, 0, [(0, 1), (2, 3)]],
#           [0.5, 0.5, [(0, 1), (2, 3)]],
#           [1, 1, [(0, 1), (2, 3)]],
#           [3, 3, [(0, 1), (2, 3)]],
#       ])
#   def test_sub__many_ranges(beg, end, expected_ranges):
#     timeline = FragmentedTimeline((0, 1), (2, 3))

#     timeline.sub(beg, end)
#     assert len(timeline) == len(expected_ranges)
#     for observed_range, expected_range in zip(timeline, expected_ranges):
#       assert observed_range == expected_range

#   @pytest.mark.parametrize('init_ranges, min_val, max_val, expected_ranges', [
#       [[(0, 1)], -math.inf, math.inf, [(-math.inf, 0), (1, math.inf)]],
#       [[(0, 1)], 0, math.inf, [(1, math.inf)]],
#       [[(0, 1), (2, 3)], 0, math.inf, [(1, 2), (3, math.inf)]],
#       [[(0, 1), (2, 3)], 0, math.inf, [(1, 2), (3, math.inf)]],
#       [[(0, 1), (2, math.inf)], 0, math.inf, [(1, 2)]],
#   ])
#   def test_complement(init_ranges, min_val, max_val, expected_ranges):
#     timeline = FragmentedTimeline(*init_ranges)

#     timeline_comp = timeline.complement(min_val, max_val)
#     assert len(timeline_comp) == len(expected_ranges)
#     for observed_range, expected_range in zip(timeline_comp, expected_ranges):
#       assert observed_range == expected_range
