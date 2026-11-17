#!/usr/bin/env python
#
# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the OpenTimelineIO project

"""Tests for trimming nested timelines.

These tests exercise ``timeline_trimmed_to_range`` /
``track_trimmed_to_range`` on timelines where a track contains another
track whose media runs at a different rate.  They combine:

* media (clip) frame rate differing from the (outer) track frame rate,
* clip source ranges that do not start at zero,
* transitions whose handles reach into the same media, and
* trim points that land inside a transition.

For every trimmed clip the same piece of media is asserted through three
independent views that must agree:

1. the clip's ``source_range`` (media time, half open
   ``[start_time, end_time_exclusive)``),
2. its position in every ancestor (``range_of_child`` /
   ``trimmed_range_of_child`` and ``transformed_time``), and
3. the transition handles (``handles_of_child`` and the transition's
   ``in_offset`` / ``out_offset``).

RationalTime is a half open interval abstraction: ``end_time_exclusive``
is excluded while ``end_time_inclusive`` is included, and the tests below
never substitute one for the other.
"""

import unittest

import opentimelineio as otio
import opentimelineio.test_utils as otio_test_utils


# Rates chosen so that one frame in the outer (24fps) space is not an
# integer number of frames of the nested media (25fps): rescaling forces
# fractional frame values, which is what the precision assertions look at.
MEDIA_RATE = 25
TRACK_RATE = 24


def _rational(value, rate):
    return otio.opentime.RationalTime(value, rate)


def _range(start, duration, rate):
    return otio.opentime.TimeRange(
        otio.opentime.RationalTime(start, rate),
        otio.opentime.RationalTime(duration, rate),
    )


def _clip(name, source_start, duration, rate):
    return otio.schema.Clip(
        name=name,
        source_range=_range(source_start, duration, rate),
    )


class NestedTimelineTrimmingTests(
    unittest.TestCase, otio_test_utils.OTIOAssertions
):
    """Trim a 24fps track that owns a nested track made of 25fps media."""

    def _build_nested_timeline(self, with_inner_transition=False,
                               with_outer_transition=False):
        """
        Layout of the nested 25fps track::

            A (source [100, 140) @25, 40 frames)
            [optional Transition AtoB, in=5 / out=8 @25]
            B (source [200, 240) @25, 40 frames)

        The nested track lasts 80 frames @25.  It is placed inside a 24fps
        track behind a 12 frame gap and (optionally) followed by a 24fps
        clip C with a transition between them::

            lead gap (12 @24) | inner25 (80 @25) | [nestToC] | C (24 @24)
        """
        clip_a = _clip("A", source_start=100, duration=40, rate=MEDIA_RATE)
        clip_b = _clip("B", source_start=200, duration=40, rate=MEDIA_RATE)

        inner_children = [clip_a]
        inner_transition = None
        if with_inner_transition:
            inner_transition = otio.schema.Transition(
                name="AtoB",
                transition_type=otio.schema.TransitionTypes.SMPTE_Dissolve,
                in_offset=_rational(5, MEDIA_RATE),
                out_offset=_rational(8, MEDIA_RATE),
            )
            inner_children.append(inner_transition)
        inner_children.append(clip_b)
        inner_track = otio.schema.Track(
            name="inner25",
            children=inner_children,
        )

        lead_gap = otio.schema.Gap(
            name="lead",
            source_range=_range(0, 12, TRACK_RATE),
        )
        clip_c = _clip("C", source_start=10, duration=24, rate=TRACK_RATE)

        outer_children = [lead_gap, inner_track]
        outer_transition = None
        if with_outer_transition:
            # in_offset reaches into the outgoing nested track (6 frames),
            # out_offset reaches into the incoming clip C (4 frames).
            outer_transition = otio.schema.Transition(
                name="nestToC",
                transition_type=otio.schema.TransitionTypes.SMPTE_Dissolve,
                in_offset=_rational(6, TRACK_RATE),
                out_offset=_rational(4, TRACK_RATE),
            )
            outer_children.append(outer_transition)
        outer_children.append(clip_c)

        outer_track = otio.schema.Track(
            name="outer24",
            children=outer_children,
        )
        timeline = otio.schema.Timeline(
            name="nested_timeline",
            tracks=[outer_track],
        )

        return {
            "timeline": timeline,
            "outer": outer_track,
            "inner": inner_track,
            "clip_a": clip_a,
            "clip_b": clip_b,
            "clip_c": clip_c,
            "gap": lead_gap,
            "inner_transition": inner_transition,
            "outer_transition": outer_transition,
        }

    # ------------------------------------------------------------------
    # fixture sanity: the three views agree before any trimming happens
    # ------------------------------------------------------------------
    def test_fixture_three_views_agree_before_trim(self):
        parts = self._build_nested_timeline(with_inner_transition=True)
        outer = parts["outer"]
        inner = parts["inner"]
        clip_a = parts["clip_a"]
        clip_b = parts["clip_b"]
        transition = parts["inner_transition"]

        # the nested track occupies outer time [12 @24, 12 @24 + 80 @25)
        self.assertEqual(
            outer.range_of_child(inner),
            otio.opentime.TimeRange(
                _rational(12, TRACK_RATE),
                _rational(80, MEDIA_RATE),
            ),
        )

        # view 1: media space source ranges keep their non zero origin
        self.assertEqual(
            clip_a.source_range,
            _range(100, 40, MEDIA_RATE),
        )
        self.assertEqual(
            clip_b.source_range,
            _range(200, 40, MEDIA_RATE),
        )

        # view 2: the clips' parent positions, expressed from the outer
        # track, start at 12 @24 == 12.5 @25 and 52.5 @25 respectively
        self.assertEqual(
            outer.range_of_child(clip_a),
            _range(12.5, 40, MEDIA_RATE),
        )
        self.assertEqual(
            outer.range_of_child(clip_b),
            _range(52.5, 40, MEDIA_RATE),
        )

        # view 3: the transition handles reach into the same media.
        # A's tail handle is the transition's out_offset (8 @25),
        # B's head handle is the transition's in_offset (5 @25).
        head_a, tail_a = inner.handles_of_child(clip_a)
        head_b, tail_b = inner.handles_of_child(clip_b)
        self.assertIsNone(head_a)
        self.assertEqual(tail_a, transition.out_offset)
        self.assertEqual(head_b, transition.in_offset)
        self.assertIsNone(tail_b)

        # visible_range extends the trimmed (source) range by exactly the
        # transition handles, so the visible media stays one contiguous
        # piece: A exposes [100, 148) @25, B exposes [195, 240) @25.
        self.assertEqual(
            clip_a.visible_range(),
            _range(100, 48, MEDIA_RATE),
        )
        self.assertEqual(
            clip_b.visible_range(),
            _range(195, 45, MEDIA_RATE),
        )

        # the transition itself spans outer time [47.5 @25, 60.5 @25),
        # i.e. the last 8 frames of A and first 5 frames of B overlap.
        # Its rate follows the 25fps media even though an ancestor runs at
        # 24fps.
        self.assertEqual(
            inner.range_of_child(transition),
            _range(35, 13, MEDIA_RATE),
        )
        self.assertEqual(
            outer.range_of_child(transition),
            _range(47.5, 13, MEDIA_RATE),
        )

    # ------------------------------------------------------------------
    # cross-rate precision: a 24fps trim amount is rescaled into 25fps
    # ------------------------------------------------------------------
    def test_front_trim_rescales_between_rates(self):
        parts = self._build_nested_timeline()
        timeline = parts["timeline"]
        outer = parts["outer"]
        inner = parts["inner"]
        clip_a = parts["clip_a"]
        clip_b = parts["clip_b"]

        # trim away the 12 frame gap plus 12 more outer frames (half a
        # second) of the nested track
        trimmed_timeline = otio.algorithms.timeline_trimmed_to_range(
            timeline,
            _range(24, 60, TRACK_RATE),
        )
        trimmed_outer = trimmed_timeline.tracks[0]
        trimmed_inner = trimmed_outer[0]

        # gap and clip C are fully outside: only the nested track remains
        self.assertEqual(
            [child.name for child in trimmed_outer],
            ["inner25"],
        )

        # 12 frames @24 == 12.5 frames @25.  The nested track's source
        # range is expressed in its own (25fps) rate, so the rescaled
        # amount is what must appear there.
        self.assertEqual(
            trimmed_inner.source_range,
            otio.opentime.TimeRange(
                _rational(12.5, MEDIA_RATE),
                _rational(62.5, MEDIA_RATE),
            ),
        )

        # the inner clips themselves are not re-sourced: trimming stops at
        # the nested track boundary, so A and B keep their original media
        # ranges (including the non zero start).
        self.assertEqual(
            trimmed_inner[0].source_range,
            clip_a.source_range,
        )
        self.assertEqual(
            trimmed_inner[1].source_range,
            clip_b.source_range,
        )

        # cross-coordinate check: the nested track now starts at zero in
        # the outer track but its own source range starts at 12.5 @25.
        self.assertEqual(
            trimmed_outer.range_of_child(trimmed_inner),
            _range(0, 62.5, MEDIA_RATE),
        )

        # clip A is partially hidden by the nested track's source range:
        # range_of_child still reports its full layout (40 frames) while
        # trimmed_range_of_child reports the visible 27.5 frame window.
        self.assertEqual(
            trimmed_outer.range_of_child(trimmed_inner[0]),
            _range(0, 40, MEDIA_RATE),
        )
        self.assertEqual(
            trimmed_outer.trimmed_range_of_child(trimmed_inner[0]),
            _range(12.5, 27.5, MEDIA_RATE),
        )

        # transformed_time must land on the same physical instant in
        # either coordinate: the first media frame still visible through
        # the nested source range is 100 + 12.5 = 112.5 @25, and it maps
        # onto outer time zero after trimming.
        first_visible_media = (
            trimmed_inner[0].source_range.start_time
            + trimmed_inner.source_range.start_time
        )
        self.assertEqual(first_visible_media, _rational(112.5, MEDIA_RATE))
        self.assertEqual(
            trimmed_inner[0].transformed_time(
                first_visible_media,
                trimmed_outer,
            ),
            _rational(0, MEDIA_RATE),
        )
        # conversely, outer zero maps back to that same media frame
        self.assertEqual(
            trimmed_outer.transformed_time(
                _rational(0, MEDIA_RATE),
                trimmed_inner[0],
            ),
            first_visible_media,
        )

        # the input timeline must not have been mutated.
        self.assertIsNone(inner.source_range)
        self.assertEqual(
            outer.range_of_child(inner).start_time,
            _rational(12, TRACK_RATE),
        )

    def test_double_trim_keeps_nested_media_rate(self):
        parts = self._build_nested_timeline()
        timeline = parts["timeline"]

        # outer window [18 @24, 66 @24): 6 frames into the nested track at
        # the front, 22.8 outer frames off the back
        trimmed_timeline = otio.algorithms.timeline_trimmed_to_range(
            timeline,
            _range(18, 48, TRACK_RATE),
        )
        trimmed_inner = trimmed_timeline.tracks[0][0]

        # the source range stays in media rate (25fps), even though the
        # trim was expressed at 24fps
        self.assertEqual(trimmed_inner.source_range.start_time.rate,
                         MEDIA_RATE)
        self.assertEqual(trimmed_inner.source_range.duration.rate,
                         MEDIA_RATE)

        front_amount = _rational(6, TRACK_RATE).rescaled_to(MEDIA_RATE)
        back_amount = (
            _rational(88.8, TRACK_RATE) - _rational(66, TRACK_RATE)
        ).rescaled_to(MEDIA_RATE)
        # the nested track originally has no source range, so its
        # trimmed_range starts at zero: the new range start is purely the
        # rescaled front trim amount (the outer gap offset is not part of
        # the child's own source coordinates).
        expected = otio.opentime.TimeRange(
            start_time=front_amount,
            duration=(
                _rational(80, MEDIA_RATE) - front_amount - back_amount
            ),
        )
        self.assertEqual(
            trimmed_inner.source_range.start_time,
            expected.start_time,
        )
        self.assertEqual(
            trimmed_inner.source_range.duration,
            expected.duration,
        )
        # the duration works out to an exact 50 media frames
        self.assertEqual(
            trimmed_inner.source_range.duration,
            _rational(50, MEDIA_RATE),
        )

        # precision probe: the back amount is an irreducible fraction at
        # 25fps (23.74999...), documenting the floating point behavior of
        # cross-rate subtraction instead of hiding it behind an integer.
        self.assertNotEqual(back_amount.value, round(back_amount.value))

    # ------------------------------------------------------------------
    # inclusive vs exclusive endpoints at a rate-boundary trim
    # ------------------------------------------------------------------
    def test_endpoint_aligned_trim_keeps_whole_nested_track(self):
        parts = self._build_nested_timeline()
        timeline = parts["timeline"]

        # the nested track ends at outer time 12 @24 + 80 @25 == 88.8 @24.
        # A trim whose exclusive end equals that boundary must keep the
        # whole nested track (the end point is excluded from trimming).
        boundary_trim = _range(0, 88.8, TRACK_RATE)
        nested_layout = parts["outer"].range_of_child(parts["inner"])
        # endpoint semantics, asserted directly: equal boundaries intersect
        # but are not strictly contained (contains requires strict
        # inequality on both ends), and an exclusive-end boundary never
        # counts as an overlap.
        self.assertTrue(boundary_trim.intersects(nested_layout))
        self.assertFalse(boundary_trim.contains(nested_layout))
        # a trim whose exclusive end equals the nested track's start
        # (12 @24) does not intersect it at all: the boundary frame is
        # excluded, so such a trim removes only the gap.
        gap_only_trim = _range(0, 12, TRACK_RATE)
        self.assertFalse(gap_only_trim.intersects(nested_layout))
        trimmed = otio.algorithms.timeline_trimmed_to_range(
            timeline,
            boundary_trim,
        )
        outer = trimmed.tracks[0]
        self.assertEqual(
            [child.name for child in outer],
            ["lead", "inner25"],
        )
        nested = outer[1]
        # TimeRange.contains() is strict containment: the other range
        # must start strictly after, and end strictly before, this range.
        # Because the nested track's exclusive end equals the trim's
        # exclusive end, it is not "contained" and the intersect branch
        # materializes an equivalent source range rather than leaving it
        # unset -- same media, zero origin, full duration, nothing removed.
        self.assertEqual(
            nested.source_range,
            _range(0, 80, MEDIA_RATE),
        )

        # one outer frame earlier intersects the nested track's end, so the
        # exclusive endpoint now removes one frame of media: the nested
        # track gets an end trim of 1 @24 == 1.04166... @25
        trimmed_short = otio.algorithms.timeline_trimmed_to_range(
            timeline,
            _range(0, 87.8, TRACK_RATE),
        )
        nested_short = trimmed_short.tracks[0][1]
        self.assertEqual(
            nested_short.source_range,
            otio.opentime.TimeRange(
                start_time=_rational(0, MEDIA_RATE),
                duration=(
                    _rational(80, MEDIA_RATE)
                    - _rational(1, TRACK_RATE).rescaled_to(MEDIA_RATE)
                ),
            ),
        )

    def test_front_trim_exactly_on_nested_start(self):
        parts = self._build_nested_timeline()
        timeline = parts["timeline"]

        # trim start equals the nested track's outer start (12 @24): the
        # gap is dropped and, although no media is removed, the intersect
        # branch materializes a source range identical to the track's full
        # extent -- the media itself is untouched.
        trimmed = otio.algorithms.timeline_trimmed_to_range(
            timeline,
            _range(12, 80, TRACK_RATE),
        )
        outer = trimmed.tracks[0]
        self.assertEqual(
            [child.name for child in outer],
            ["inner25", "C"],
        )
        self.assertEqual(
            outer[0].source_range,
            _range(0, 80, MEDIA_RATE),
        )
        self.assertIsOTIOEquivalentTo(
            outer[0][0], parts["clip_a"]
        )
        self.assertIsOTIOEquivalentTo(
            outer[0][1], parts["clip_b"]
        )

    # ------------------------------------------------------------------
    # non-zero source start survives trimming and coordinate transforms
    # ------------------------------------------------------------------
    def test_nonzero_source_start_survives_trim_and_transform(self):
        parts = self._build_nested_timeline()
        timeline = parts["timeline"]
        clip_a = parts["clip_a"]

        trimmed = otio.algorithms.timeline_trimmed_to_range(
            timeline,
            _range(24, 60, TRACK_RATE),
        )
        outer = trimmed.tracks[0]
        inner = outer[0]
        trimmed_a = inner[0]

        # the media origin (100 @25) is untouched
        self.assertEqual(
            trimmed_a.source_range.start_time,
            _rational(100, MEDIA_RATE),
        )

        # the first media frame that is actually visible through the
        # nested source range is frame 112.5 @25 of the media; mapping it
        # through the hierarchy lands on outer time zero.
        first_visible_media = (
            trimmed_a.source_range.start_time
            + inner.source_range.start_time
        )
        self.assertEqual(first_visible_media, _rational(112.5, MEDIA_RATE))
        self.assertEqual(
            trimmed_a.transformed_time(first_visible_media, outer),
            _rational(0, MEDIA_RATE),
        )

        # and the reverse mapping of outer zero gives the same media frame
        self.assertEqual(
            outer.transformed_time(_rational(0, MEDIA_RATE), trimmed_a),
            first_visible_media,
        )

        # sanity: an untouched clip from the original timeline still maps
        # media frame 100 onto its original outer position (12.5 @25)
        self.assertEqual(
            clip_a.transformed_time(
                _rational(100, MEDIA_RATE), parts["outer"]
            ),
            _rational(12.5, MEDIA_RATE),
        )

    # ------------------------------------------------------------------
    # trimming inside a transition
    # ------------------------------------------------------------------
    def test_trim_inside_outer_transition_raises(self):
        parts = self._build_nested_timeline(
            with_outer_transition=True
        )
        timeline = parts["timeline"]
        outer = parts["outer"]
        transition = parts["outer_transition"]

        # the transition occupies outer time [82.8 @24, 92.8 @24): the
        # nested track (after the 12 frame gap) ends at 88.8 @24 and the
        # in_offset of 6 outer frames starts the transition earlier, while
        # the 4 frame out_offset extends it past the cut onto clip C.
        # The stored range keeps the 25fps rate inherited from the nested
        # media, so its start is 86.25 @25.
        self.assertEqual(
            transition.range_in_parent(),
            otio.opentime.TimeRange(
                _rational(86.25, MEDIA_RATE),
                _rational(10, TRACK_RATE),
            ),
        )
        self.assertEqual(
            transition.range_in_parent().start_time.rescaled_to(
                TRACK_RATE
            ),
            _rational(82.8, TRACK_RATE),
        )
        self.assertEqual(
            transition.range_in_parent().end_time_exclusive(),
            _rational(92.8, TRACK_RATE),
        )

        # handles still describe the same media before trimming:
        # nested track loses 6 frames at its tail, clip C loses 4 at head
        head_nested, tail_nested = outer.handles_of_child(parts["inner"])
        self.assertIsNone(head_nested)
        self.assertEqual(tail_nested, transition.out_offset)
        head_c, tail_c = outer.handles_of_child(parts["clip_c"])
        self.assertEqual(head_c, transition.in_offset)
        self.assertIsNone(tail_c)

        # a trim starting strictly before the transition but ending inside
        # it must fail rather than silently severing the handles.  70 @24
        # is before the transition start (82.8 @24), yet its 20 frame
        # window reaches into the transition.
        with self.assertRaises(otio.exceptions.CannotTrimTransitionsError):
            otio.algorithms.timeline_trimmed_to_range(
                timeline,
                _range(70, 20, TRACK_RATE),
            )

        # starting on the transition's inclusive start boundary fails too:
        # the ranges intersect but neither contains the other.
        with self.assertRaises(otio.exceptions.CannotTrimTransitionsError):
            otio.algorithms.timeline_trimmed_to_range(
                timeline,
                otio.opentime.TimeRange(
                    _rational(82.8, TRACK_RATE),
                    _rational(8, TRACK_RATE),
                ),
            )

        # starting exactly at the exclusive end of the transition
        # (92.8 @24) no longer intersects it: the whole transition is
        # discarded together with the nested track, clip C remains.
        trimmed = otio.algorithms.timeline_trimmed_to_range(
            timeline,
            otio.opentime.TimeRange(
                _rational(92.8, TRACK_RATE),
                _rational(20, TRACK_RATE),
            ),
        )
        self.assertEqual(
            [child.name for child in trimmed.tracks[0]],
            ["C"],
        )

    def test_nested_transition_is_opaque_to_outer_trim(self):
        # An outer-level trim cannot see transitions nested inside a child
        # track, because trimming stops at the child's source range.  The
        # inner handles therefore survive an outer trim that would cut the
        # same media if the tracks were flattened.
        parts = self._build_nested_timeline(with_inner_transition=True)
        timeline = parts["timeline"]
        inner = parts["inner"]
        transition = parts["inner_transition"]

        # inner transition spans inner time [35 @25, 48 @25), which in
        # outer space is [47.5 @25, 60.5 @25)
        self.assertEqual(
            inner.range_of_child(transition),
            _range(35, 13, MEDIA_RATE),
        )

        # outer trim [40 @24, ...) maps to 41.667 @25: inside the inner
        # transition's media window, yet the outer algorithm only trims
        # the nested track's source range -- no exception is raised and
        # the transition and its handles are preserved verbatim.
        trimmed = otio.algorithms.timeline_trimmed_to_range(
            timeline,
            _range(40, 40, TRACK_RATE),
        )
        trimmed_outer = trimmed.tracks[0]
        trimmed_inner = trimmed_outer[0]
        self.assertEqual(
            [type(child).__name__ for child in trimmed_inner],
            ["Clip", "Transition", "Clip"],
        )
        kept_transition = trimmed_inner[1]
        self.assertEqual(kept_transition.in_offset, transition.in_offset)
        self.assertEqual(kept_transition.out_offset, transition.out_offset)

        # the nested source range absorbs both cuts: relative to the nested
        # track's own start at outer 12 @24, the front cut removes 28 outer
        # frames (29.1666... media frames) and the back cut removes 8.8
        # outer frames (9.1666... media frames), since the trim window ends
        # at 80 @24, before the nested track end at 88.8 @24.  The gap
        # offset is not part of the nested source coordinates.  The
        # rescaled values are irreducible fractions at 25fps.
        nested_trim_amount = (
            _rational(40, TRACK_RATE) - _rational(12, TRACK_RATE)
        ).rescaled_to(MEDIA_RATE)
        nested_back_amount = (
            _rational(88.8, TRACK_RATE) - _rational(80, TRACK_RATE)
        ).rescaled_to(MEDIA_RATE)
        self.assertTrue(
            nested_trim_amount.almost_equal(
                _rational(29.1667, MEDIA_RATE), 1e-4
            )
        )
        self.assertTrue(
            nested_back_amount.almost_equal(
                _rational(9.1667, MEDIA_RATE), 1e-4
            )
        )
        self.assertNotEqual(
            nested_trim_amount.value, round(nested_trim_amount.value)
        )
        self.assertNotEqual(
            nested_back_amount.value, round(nested_back_amount.value)
        )
        self.assertEqual(
            trimmed_inner.source_range,
            otio.opentime.TimeRange(
                start_time=nested_trim_amount,
                duration=(
                    _rational(80, MEDIA_RATE)
                    - nested_trim_amount
                    - nested_back_amount
                ),
            ),
        )

        # the surviving clips still reference the same non-zero media
        # origins, and the handle-derived visible ranges are unchanged
        self.assertEqual(
            trimmed_inner[0].source_range.start_time,
            _rational(100, MEDIA_RATE),
        )
        self.assertEqual(
            trimmed_inner[2].source_range.start_time,
            _rational(200, MEDIA_RATE),
        )
        self.assertEqual(
            trimmed_inner[0].visible_range(),
            parts["clip_a"].visible_range(),
        )
        self.assertEqual(
            trimmed_inner[2].visible_range(),
            parts["clip_b"].visible_range(),
        )

    # ------------------------------------------------------------------
    # existing single-rate track behavior must remain intact
    # ------------------------------------------------------------------
    def test_flat_track_trim_behavior_unchanged(self):
        # same shape as the flat TimelineTrimmingTests fixture, rebuilt at
        # a single rate to lock the existing semantics next to the new
        # nested ones.
        clips = [
            _clip(name, 0, 50, TRACK_RATE) for name in ("A", "B", "C")
        ]
        track = otio.schema.Track(name="flat", children=clips)
        timeline = otio.schema.Timeline(tracks=[track])

        trimmed = otio.algorithms.timeline_trimmed_to_range(
            timeline,
            _range(60, 90, TRACK_RATE),
        )
        trimmed_track = trimmed.tracks[0]
        self.assertEqual(len(trimmed_track), 2)
        self.assertEqual(trimmed_track[0].name, "B")
        self.assertEqual(
            trimmed_track[0].trimmed_range(),
            _range(10, 40, TRACK_RATE),
        )
        self.assertIsOTIOEquivalentTo(trimmed_track[1], clips[2])

        # trimming inside a transition on the flat track still raises
        transition = otio.schema.Transition(
            in_offset=_rational(12, TRACK_RATE),
            out_offset=_rational(20, TRACK_RATE),
        )
        track.insert(1, transition)
        with self.assertRaises(otio.exceptions.CannotTrimTransitionsError):
            otio.algorithms.timeline_trimmed_to_range(
                timeline,
                _range(45, 50, TRACK_RATE),
            )


if __name__ == '__main__':
    unittest.main()
