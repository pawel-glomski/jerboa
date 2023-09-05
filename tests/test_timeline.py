import math

import pytest

from jerboa.core.timeline import TMSection, FragmentedTimeline, RangeMappingResult


class TestTMSection:
    @pytest.mark.parametrize(
        "beg, end, modifier",
        [
            (0, 10, 1.0),
            (-10, 10, 2.0),
            (0, 0, 0.5),
        ],
    )
    def test_should_create_new_instance_when_valid_input(self, beg, end, modifier):
        section = TMSection(beg, end, modifier)

        assert section.beg == beg
        assert section.end == end
        assert section.modifier == modifier

    @pytest.mark.parametrize(
        "beg, end, modifier",
        [
            (10, 0, 1.0),
            (10, 0, -1.0),
            (0, 10, -1.0),
            (math.nan, 10, 1.0),
            (math.nan, 10, -1.0),
            (0, math.nan, 1.0),
            (0, math.nan, -1.0),
            (0, 10, math.nan),
        ],
    )
    def test_should_raise_assertion_error_when_invalid_input(self, beg, end, modifier):
        with pytest.raises(AssertionError):
            TMSection(beg, end, modifier)

    @pytest.mark.parametrize(
        "section1, section2, expected_section",
        [
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
        ],
    )
    def test_try_extending_with_should_extend_to_expected_section_when_is_direct_continuation(
        self, section1: TMSection, section2: TMSection, expected_section: TMSection
    ):
        assert section1.try_extending_with(section2) is True and section1 == expected_section

    @pytest.mark.parametrize(
        "section1, section2",
        [
            (TMSection(-10, 10, 1.0), TMSection(-10, 10, 1.0)),
            (TMSection(5, 10, 1.0), TMSection(5, 15, 1.0)),
            (TMSection(6, 10, 0.5), TMSection(11, 15, 1.0)),
            (TMSection(7, 10, 2.0), TMSection(10, 15, 0.5)),
            (TMSection(8, 10, 1.0), TMSection(10, 15, 0.0)),
            (TMSection(0, 10, 1.0), TMSection(-10, 0, 1.0)),
        ],
    )
    def test_try_extending_with_should_return_false_when_is_not_direct_continuation(
        self, section1: TMSection, section2: TMSection
    ):
        section1_before = TMSection(section1.beg, section1.end, section1.modifier)
        assert section1.try_extending_with(section2) is False and section1 == section1_before

    @pytest.mark.parametrize(
        "section, expected_duration",
        [
            (TMSection(0, 10, 1.0), 10),
            (TMSection(-10, 10, 2.0), 40),
            (TMSection(0, 100, 0.5), 50),
            (TMSection(0, 100, 0.0), 0),
            (TMSection(10, 10, 1.0), 0),
            (TMSection(0, math.inf, 0.0), 0),
            (TMSection(-math.inf, 0, 1.0), math.inf),
            (TMSection(0, math.inf, 0.5), math.inf),
            (TMSection(-math.inf, math.inf, 1.0), math.inf),
        ],
    )
    def test_duration_should_return_expected_duration(self, section, expected_duration):
        assert section.duration == expected_duration

    @pytest.mark.parametrize(
        "section, beg, end, expected_section",
        [
            (TMSection(0, 3, 2), 1, 2, TMSection(1, 2, 2)),
            (TMSection(1, 2, 2), 0, 3, TMSection(1, 2, 2)),
            (TMSection(1, 2, 1), 0, 3, TMSection(1, 2, 1)),
            (TMSection(0, 2, 1), 1, 3, TMSection(1, 2, 1)),
            (TMSection(0, 3, 1), 1, 2, TMSection(1, 2, 1)),
            (TMSection(1, 3, 1), 0, 2, TMSection(1, 2, 1)),
        ],
    )
    def test_overlap_should_return_expected_section_for_overlapping_range(
        self,
        section: TMSection,
        beg: float,
        end: float,
        expected_section: TMSection,
    ):
        result = section.overlap(beg, end)

        assert result == expected_section

    @pytest.mark.parametrize(
        "section, beg, end",
        [
            (TMSection(0, 1, 1), 2, 3),
            (TMSection(4, 5, 0.5), 2, 3),
        ],
    )
    def test_overlap_should_return_empty_section_for_non_overlapping_range(
        self,
        section: TMSection,
        beg: float,
        end: float,
    ):
        result = section.overlap(beg, end)

        assert result.beg == result.end


class TestFragmentedTimeline:
    def test_init_should_create_empty_timeline_when_no_args(self):
        tl = FragmentedTimeline()

        assert len(tl) == 0

    def test_init_should_raise_value_error_when_unordered_init_sections(self):
        with pytest.raises(ValueError):
            _ = FragmentedTimeline(TMSection(0, 1), TMSection(0, 1, 0.5), TMSection(-1, 4, 2.0))

    def test_init_should_create_filled_timeline_when_provided_ordered_init_sections(self):
        tl = FragmentedTimeline(TMSection(0, 1), TMSection(1, 2, 0.5), TMSection(3, 4, 2.0))

        assert len(tl) == 3

    def test_time_scope_setter_should_raise_value_error_when_new_is_not_greater(self):
        tl = FragmentedTimeline(TMSection(0, 5))

        with pytest.raises(ValueError):
            tl.time_scope = 4

    def test_append_section_should_raise_value_error_when_unordered_section(self):
        tl = FragmentedTimeline(TMSection(0, 5))

        with pytest.raises(ValueError):
            tl.append_section(TMSection(4, 6))

    def test_append_section_should_raise_value_error_when_section_precedes_scope(self):
        tl = FragmentedTimeline(TMSection(0, 5))

        tl.time_scope = 6

        with pytest.raises(ValueError):
            tl.append_section(TMSection(5, 6))

    def test_append_section_should_append_when_ordered(self):
        tl = FragmentedTimeline(TMSection(0, 1))

        tl.append_section(TMSection(2, 3, 0.5))

        assert list(tl) == [(TMSection(0, 1), 1.0), (TMSection(2, 3, 0.5), 1.5)]
        assert tl.time_scope == 3

    def test_append_section_should_extend_when_direct_continuation(self):
        tl = FragmentedTimeline(TMSection(0, 1, 0.5))

        tl.append_section(TMSection(1, 2, 0.5))

        assert list(tl) == [(TMSection(0, 2, 0.5), 1.0)]
        assert tl.time_scope == 2

    def test_append_section_should_not_append_when_modifier_is_0(self):
        tl = FragmentedTimeline(TMSection(0, 1))

        tl.append_section(TMSection(2, 3, 0))

        assert list(tl) == [(TMSection(0, 1), 1.0)]
        assert tl.time_scope == 3

    def test_append_section_should_clamp_section_beg_to_0_when_negative_beg(self):
        tl = FragmentedTimeline()

        tl.append_section(TMSection(-math.inf, math.inf))

        assert list(tl) == [(TMSection(0, math.inf), math.inf)]
        assert tl.time_scope == math.inf

    def test_unmap_timepoint_to_source_should_return_none_when_empty_timeline(self):
        tl = FragmentedTimeline()

        assert tl.unmap_timepoint_to_source(0.0) is None

    def test_unmap_timepoint_to_source_should_return_none_when_timepoint_out_of_scope(self):
        tl = FragmentedTimeline(TMSection(0, 1, 0.5))

        assert tl.unmap_timepoint_to_source(2) is None

    @pytest.mark.parametrize(
        "mapped_timepoint, expected_src_timepoint",
        [
            (0, 0),
            (1, 2),
            (2, 2.5),
            (3, 3),
        ],
    )
    def test_unmap_timepoint_to_source_should_return_correct_value(
        self, mapped_timepoint: float, expected_src_timepoint: float
    ):
        tl = FragmentedTimeline(TMSection(0, 2, 0.5), TMSection(2, 3, 2.0))

        assert tl.unmap_timepoint_to_source(mapped_timepoint) == expected_src_timepoint

    def test_unmap_timepoint_to_source_should_return_end_of_last_section_when_scope_is_inf_and_timepoint_is_out_of_scope(
        self,
    ):
        tl = FragmentedTimeline(TMSection(0, 1, 0.5))
        tl.time_scope = math.inf

        assert tl.unmap_timepoint_to_source(0.5) == 1
        assert tl.unmap_timepoint_to_source(2) == 1

    def test_map_time_range_should_raise_value_error_when_invalid_range(self):
        with pytest.raises(ValueError):
            FragmentedTimeline().map_time_range(1, 0)

    def test_map_time_range_should_raise_value_error_when_out_of_scope(self):
        with pytest.raises(ValueError):
            FragmentedTimeline(TMSection(0, 1)).map_time_range(0, 2)

    def test_map_time_range_should_return_empty_results_when_maps_to_nothing(self):
        tl = FragmentedTimeline(TMSection(1, 2))

        mapping_results, next_timepoint = tl.map_time_range(0, 1)

        assert mapping_results.beg == mapping_results.end
        assert mapping_results.sections == []
        assert next_timepoint == 1

    @pytest.mark.parametrize(
        "init_sections, range_to_map, expected_mapping_results, expected_next_timepoint",
        [
            (
                [TMSection(1, 3, 0.5), TMSection(4, 6)],
                (0, 2),
                RangeMappingResult(0, 0.5, [TMSection(1, 2, 0.5)]),
                2,
            ),
            (
                [TMSection(1, 3, 0.5), TMSection(4, 6)],
                (0, 5),
                RangeMappingResult(0, 2, [TMSection(1, 3, 0.5), TMSection(4, 5)]),
                5,
            ),
            (
                [TMSection(1, 3, 0.5), TMSection(4, 6)],
                (2, 7),
                RangeMappingResult(0.5, 3, [TMSection(2, 3, 0.5), TMSection(4, 6)]),
                math.inf,
            ),
            (
                [TMSection(-math.inf, math.inf)],
                (2, 7),
                RangeMappingResult(2, 7, [TMSection(2, 7)]),
                7,
            ),
        ],
    )
    def test_map_time_range_should_return_correct_results_when_valid_ranges(
        self,
        init_sections: list[TMSection],
        range_to_map: tuple[float, float],
        expected_mapping_results: RangeMappingResult,
        expected_next_timepoint: float,
    ):
        tl = FragmentedTimeline(*init_sections)
        tl.time_scope = math.inf  # mark the timeline as complete

        mapping_results, next_timepoint = tl.map_time_range(*range_to_map)

        assert mapping_results == expected_mapping_results
        assert next_timepoint == expected_next_timepoint
