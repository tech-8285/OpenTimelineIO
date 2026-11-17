#!/usr/bin/env python
#
# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the OpenTimelineIO project

"""Test file for the stack algorithms library."""

import unittest
import os
import opentimelineio as otio
import opentimelineio.test_utils as otio_test_utils


SAMPLE_DATA_DIR = os.path.join(os.path.dirname(__file__), "sample_data")
MULTITRACK_EXAMPLE_PATH = os.path.join(SAMPLE_DATA_DIR, "multitrack.otio")
PREFLATTENED_EXAMPLE_PATH = os.path.join(SAMPLE_DATA_DIR, "preflattened.otio")

RATE = 24


def _rt(value):
    return otio.opentime.RationalTime(value, RATE)


def _time_range(start, duration):
    return otio.opentime.TimeRange(_rt(start), _rt(duration))


def _clip(name, duration, start=0, media_reference=None, enabled=True):
    clip = otio.schema.Clip(
        name=name,
        source_range=_time_range(start, duration),
        media_reference=media_reference,
    )
    clip.enabled = enabled
    return clip


def _gap(duration):
    return otio.schema.Gap(source_range=_time_range(0, duration))


def _transition(name, in_offset, out_offset):
    return otio.schema.Transition(
        name=name,
        in_offset=_rt(in_offset),
        out_offset=_rt(out_offset),
    )


def _track(name, children, enabled=True):
    track = otio.schema.Track(name=name, children=children)
    track.enabled = enabled
    return track


class StackAlgoTests(unittest.TestCase, otio_test_utils.OTIOAssertions):
    """ test harness for stack algo functions """

    def setUp(self):
        self.trackZ = otio.adapters.read_from_string("""
        {
            "OTIO_SCHEMA": "Track.1",
            "children": [
                {
                    "OTIO_SCHEMA": "Clip.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "metadata": {},
                    "name": "Z",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 150
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                }
            ],
            "effects": [],
            "kind": "Video",
            "markers": [],
            "metadata": {},
            "name": "Sequence1",
            "source_range": null
        }
        """, "otio_json")

        self.trackZd = otio.adapters.read_from_string("""
        {
            "OTIO_SCHEMA": "Track.1",
            "children": [
                {
                    "OTIO_SCHEMA": "Clip.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "enabled": false,
                    "metadata": {},
                    "name": "Z",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 150
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                }
            ],
            "effects": [],
            "kind": "Video",
            "markers": [],
            "metadata": {},
            "name": "Sequence1",
            "source_range": null
        }
        """, "otio_json")

        self.track_d = otio.adapters.read_from_string("""
        {
            "OTIO_SCHEMA": "Track.1",
            "children": [
                {
                    "OTIO_SCHEMA": "Clip.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "enabled": true,
                    "metadata": {},
                    "name": "Z",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 150
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                }
            ],
            "effects": [],
            "kind": "Video",
            "markers": [],
            "enabled": false,
            "metadata": {},
            "name": "Sequence1",
            "source_range": null
        }
        """, "otio_json")

        self.trackABC = otio.adapters.read_from_string("""
        {
            "OTIO_SCHEMA": "Track.1",
            "children": [
                {
                    "OTIO_SCHEMA": "Clip.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "metadata": {},
                    "name": "A",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 50
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                },
                {
                    "OTIO_SCHEMA": "Clip.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "metadata": {},
                    "name": "B",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 50
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                },
                {
                    "OTIO_SCHEMA": "Clip.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "metadata": {},
                    "name": "C",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 50
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                }
            ],
            "effects": [],
            "kind": "Video",
            "markers": [],
            "metadata": {},
            "name": "Sequence1",
            "source_range": null
        }
        """, "otio_json")

        self.trackDgE = otio.adapters.read_from_string("""
        {
            "OTIO_SCHEMA": "Track.1",
            "children": [
                {
                    "OTIO_SCHEMA": "Clip.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "metadata": {},
                    "name": "D",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 50
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                },
                {
                    "OTIO_SCHEMA": "Gap.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "metadata": {},
                    "name": "g",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 50
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                },
                {
                    "OTIO_SCHEMA": "Clip.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "metadata": {},
                    "name": "E",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 50
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                }
            ],
            "effects": [],
            "kind": "Video",
            "markers": [],
            "metadata": {},
            "name": "Sequence1",
            "source_range": null
        }
        """, "otio_json")

        self.trackgFg = otio.adapters.read_from_string("""
        {
            "OTIO_SCHEMA": "Track.1",
            "children": [
                {
                    "OTIO_SCHEMA": "Gap.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "metadata": {},
                    "name": "g1",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 50
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                },
                {
                    "OTIO_SCHEMA": "Clip.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "metadata": {},
                    "name": "F",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 50
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                },
                {
                    "OTIO_SCHEMA": "Gap.1",
                    "effects": [],
                    "markers": [],
                    "media_reference": null,
                    "metadata": {},
                    "name": "g2",
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "duration": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 50
                        },
                        "start_time": {
                            "OTIO_SCHEMA": "RationalTime.1",
                            "rate": 24,
                            "value": 0.0
                        }
                    }
                }
            ],
            "effects": [],
            "kind": "Video",
            "markers": [],
            "metadata": {},
            "name": "Sequence1",
            "source_range": null
        }
        """, "otio_json")

    def test_flatten_single_track(self):
        stack = otio.schema.Stack(children=[
            self.trackABC
        ])
        flat_track = otio.algorithms.flatten_stack(stack)
        # the result should be equivalent
        self.assertJsonEqual(
            flat_track[:],
            self.trackABC[:]
        )
        # but not the same actual objects
        self.assertIsNot(
            flat_track[0],
            self.trackABC[0]
        )
        self.assertIsNot(
            flat_track[1],
            self.trackABC[1]
        )
        self.assertIsNot(
            flat_track[2],
            self.trackABC[2]
        )

    def test_flatten_obscured_track(self):
        stack = otio.schema.Stack(children=[
            self.trackABC,
            self.trackZ
        ])
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertJsonEqual(
            flat_track[:],
            self.trackZ[:]
        )

        # It is an error to add an item to composition if it is already in
        # another composition.  This clears out the old test composition
        # (and also clears out its parent pointers).
        del stack
        stack = otio.schema.Stack(
            children=[
                self.trackZ,
                self.trackABC,
            ]
        )
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertJsonEqual(
            flat_track[:],
            self.trackABC[:]
        )

    def test_flatten_disabled_clip(self):
        stack = otio.schema.Stack(children=[
            self.trackABC,
            self.trackZ
        ])
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertJsonEqual(
            flat_track[:],
            self.trackZ[:]
        )
        del stack
        stack = otio.schema.Stack(children=[
            self.trackABC,
            self.trackZd
        ])
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertJsonEqual(
            flat_track[:],
            self.trackABC[:]
        )

    def test_flatten_disabled_track(self):
        stack = otio.schema.Stack(children=[
            self.trackABC,
            self.trackZ
        ])
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertJsonEqual(
            flat_track[:],
            self.trackZ[:]
        )
        del stack
        stack = otio.schema.Stack(children=[
            self.trackABC,
            self.track_d
        ])
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertJsonEqual(
            flat_track[:],
            self.trackABC[:]
        )

    def test_flatten_gaps(self):
        stack = otio.schema.Stack(children=[
            self.trackABC,
            self.trackDgE
        ])
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertIsOTIOEquivalentTo(flat_track[0], self.trackDgE[0])
        self.assertIsOTIOEquivalentTo(flat_track[1], self.trackABC[1])
        self.assertIsOTIOEquivalentTo(flat_track[2], self.trackDgE[2])
        self.assertIsNot(flat_track[0], self.trackDgE[0])
        self.assertIsNot(flat_track[1], self.trackABC[1])
        self.assertIsNot(flat_track[2], self.trackDgE[2])

        # create a new stack out of the old parts, delete the old stack first
        del stack
        stack = otio.schema.Stack(children=[
            self.trackABC,
            self.trackgFg
        ])
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertIsOTIOEquivalentTo(flat_track[0], self.trackABC[0])
        self.assertIsOTIOEquivalentTo(flat_track[1], self.trackgFg[1])
        self.assertIsOTIOEquivalentTo(flat_track[2], self.trackABC[2])
        self.assertIsNot(flat_track[0], self.trackABC[0])
        self.assertIsNot(flat_track[1], self.trackgFg[1])
        self.assertIsNot(flat_track[2], self.trackABC[2])

    def test_flatten_gaps_with_trims(self):
        stack = otio.schema.Stack(children=[
            self.trackZ,
            self.trackDgE
        ])
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertIsOTIOEquivalentTo(flat_track[0], self.trackDgE[0])
        self.assertEqual(flat_track[1].name, "Z")
        self.assertEqual(
            flat_track[1].source_range,
            otio.opentime.TimeRange(
                otio.opentime.RationalTime(50, 24),
                otio.opentime.RationalTime(50, 24)
            )
        )
        self.assertIsOTIOEquivalentTo(flat_track[2], self.trackDgE[2])

        del stack
        stack = otio.schema.Stack(children=[
            self.trackZ,
            self.trackgFg
        ])
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertEqual(flat_track[0].name, "Z")
        self.assertEqual(
            flat_track[0].source_range,
            otio.opentime.TimeRange(
                otio.opentime.RationalTime(0, 24),
                otio.opentime.RationalTime(50, 24)
            )
        )
        self.assertIsOTIOEquivalentTo(flat_track[1], self.trackgFg[1])
        self.assertEqual(flat_track[2].name, "Z")
        self.assertEqual(
            flat_track[2].source_range,
            otio.opentime.TimeRange(
                otio.opentime.RationalTime(100, 24),
                otio.opentime.RationalTime(50, 24)
            )
        )

    def test_flatten_list_of_tracks(self):
        tracks = [
            self.trackABC,
            self.trackDgE
        ]
        flat_track = otio.algorithms.flatten_stack(tracks)
        self.assertIsOTIOEquivalentTo(flat_track[0], self.trackDgE[0])
        self.assertIsOTIOEquivalentTo(flat_track[1], self.trackABC[1])
        self.assertIsOTIOEquivalentTo(flat_track[2], self.trackDgE[2])

        tracks = [
            self.trackABC,
            self.trackgFg
        ]
        flat_track = otio.algorithms.flatten_stack(tracks)
        self.assertIsOTIOEquivalentTo(flat_track[0], self.trackABC[0])
        self.assertIsOTIOEquivalentTo(flat_track[1], self.trackgFg[1])
        self.assertIsOTIOEquivalentTo(flat_track[2], self.trackABC[2])

    def test_flatten_example_code(self):
        timeline = otio.adapters.read_from_file(MULTITRACK_EXAMPLE_PATH)
        preflattened = otio.adapters.read_from_file(PREFLATTENED_EXAMPLE_PATH)
        preflattened_track = preflattened.video_tracks()[0]
        flattened_track = otio.algorithms.flatten_stack(
            timeline.video_tracks()
        )

        # the names will be different, so clear them both
        preflattened_track.name = ""
        flattened_track.name = ""

        self.assertOTIOEqual(
            preflattened_track,
            flattened_track
        )

    def assertOTIOEqual(self, a, b):
        self.maxDiff = None
        self.assertMultiLineEqual(
            otio.adapters.write_to_string(a, 'otio_json'),
            otio.adapters.write_to_string(b, 'otio_json')
        )

    def test_flatten_with_transition(self):
        stack = otio.schema.Stack(
            children=[
                self.trackABC,
                self.trackDgE,
            ]
        )
        stack[1].insert(
            1,
            otio.schema.Transition(
                name="test_transition",
                in_offset=otio.opentime.RationalTime(10, 24),
                out_offset=otio.opentime.RationalTime(15, 24)
            )
        )
        flat_track = otio.algorithms.flatten_stack(stack)
        self.assertEqual(3, len(self.trackABC))
        self.assertEqual(4, len(stack[1]))
        self.assertEqual(4, len(flat_track))
        self.assertEqual(flat_track[1].name, "test_transition")

    def assertFlattenedLayout(self, flat_track, expected):
        """Assert flattened items, timeline positions and source ranges.

        ``expected`` entries are ``(schema_name, name, position, duration,
        source_range)`` where ``source_range`` is ``(start, duration)`` or
        ``None`` for composables that cannot carry a source range, such as
        transitions.
        """
        self.assertEqual(len(flat_track), len(expected))
        for index, entry in enumerate(expected):
            (
                schema_name,
                name,
                position,
                duration,
                source_range,
            ) = entry
            child = flat_track[index]
            self.assertEqual(child.schema_name(), schema_name)
            self.assertEqual(child.name, name)

            child_range = flat_track.range_of_child_at_index(index)
            self.assertEqual(child_range.start_time, _rt(position))
            self.assertEqual(child_range.duration, _rt(duration))

            if source_range is None:
                self.assertFalse(hasattr(child, "source_range"))
            else:
                self.assertEqual(child.source_range, _time_range(*source_range))

    def assertVisibleClipNamesAt(self, flat_track, samples):
        """Assert which clips a point sample resolves to on a flat track."""
        for position, expected_names in samples.items():
            found = [
                child.name
                for child in flat_track.find_clips(
                    otio.opentime.TimeRange(_rt(position), _rt(0))
                )
            ]
            self.assertEqual(
                found,
                expected_names,
                "unexpected visible material at time {}".format(position),
            )

    def assertTransitionBoundariesConsistent(self, flat_track):
        """Transition visibilities must line up with neighbouring materials.

        The overlap of a transition with its neighbours is defined by its
        in/out offsets, so the boundary between the outgoing and incoming
        material must agree with the transition's range.
        """
        for index, child in enumerate(flat_track):
            if child.schema_name() != "Transition":
                continue
            # a transition inside a flattened track always has neighbours on
            # both sides, which the flatten algorithm relies on for its
            # overlap bookkeeping
            self.assertGreater(index, 0)
            self.assertLess(index, len(flat_track) - 1)
            transition_range = flat_track.range_of_child_at_index(index)
            left_range = flat_track.range_of_child_at_index(index - 1)
            right_range = flat_track.range_of_child_at_index(index + 1)
            self.assertEqual(
                transition_range.start_time,
                left_range.end_time_exclusive() - child.in_offset,
            )
            self.assertEqual(
                transition_range.end_time_exclusive(),
                right_range.start_time + child.out_offset,
            )

    def test_flatten_upper_gap_reveals_lower_material(self):
        """An upper gap must not mask the material below it.

        upper: [  gap 0-50  | X 50-100 | gap 100-150 ]
        lower: [   A 0-50   | B 50-100 |   C 100-150 ]
        flat:  [   A 0-50   | X 50-100 |   C 100-150 ]
        """
        lower = _track("lower", [
            _clip("A", 50),
            _clip("B", 50),
            _clip("C", 50),
        ])
        upper = _track("upper", [
            _gap(50),
            _clip("X", 50, start=10),
            _gap(50),
        ])
        flat_track = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[lower, upper])
        )

        self.assertFlattenedLayout(flat_track, [
            ("Clip", "A", 0, 50, (0, 50)),
            ("Clip", "X", 50, 50, (10, 50)),
            ("Clip", "C", 100, 50, (0, 50)),
        ])
        # the upper gaps contribute no items of their own
        self.assertEqual(
            [child.schema_name() for child in flat_track],
            ["Clip", "Clip", "Clip"],
        )
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["A"],
            49: ["A"],
            50: ["X"],
            99: ["X"],
            100: ["C"],
            149: ["C"],
        })
        # flattening is non-destructive: the inputs keep their own layout
        self.assertEqual(
            [child.name for child in lower],
            ["A", "B", "C"],
        )
        self.assertEqual(
            [child.schema_name() for child in upper],
            ["Gap", "Clip", "Gap"],
        )
        self.assertEqual(lower.duration(), _rt(150))
        self.assertEqual(upper.duration(), _rt(150))

    def test_flatten_gap_below_upper_gap_stays_a_hole(self):
        """A hole is only kept when no lower material covers it.

        upper: [ gap 0-150 (three 50 frame gaps) ]
        lower: [ A 0-50 | gap 50-100 | B 100-150 ]
        flat:  [ A 0-50 | gap 50-100 | B 100-150 ]
        """
        lower = _track("lower", [
            _clip("A", 50),
            _gap(50),
            _clip("B", 50),
        ])
        upper = _track("upper", [
            _gap(50),
            _gap(50),
            _gap(50),
        ])
        flat_track = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[lower, upper])
        )

        self.assertFlattenedLayout(flat_track, [
            ("Clip", "A", 0, 50, (0, 50)),
            ("Gap", "", 50, 50, (0, 50)),
            ("Clip", "B", 100, 50, (0, 50)),
        ])
        self.assertFalse(flat_track[1].visible())
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["A"],
            49: ["A"],
            50: [],
            60: [],
            99: [],
            100: ["B"],
        })

    def test_flatten_disabled_clip_reveals_lower_material(self):
        """A disabled clip must not obscure lower material.

        upper: [ gap 0-25 |      X 25-85 (disabled)      | gap 85-150 ]
        lower: [   A 0-50 |        B 50-100              |  C 100-150 ]
        flat:  [ A 0-25 | A 25-50 | B 50-85 | B 85-100   |  C 100-150 ]
        """
        lower = _track("lower", [
            _clip("A", 50),
            _clip("B", 50),
            _clip("C", 50),
        ])
        upper = _track("upper", [
            _gap(25),
            _clip("X", 60, enabled=False),
            _gap(65),
        ])
        stack = otio.schema.Stack(children=[lower, upper])
        flat_track = otio.algorithms.flatten_stack(stack)

        self.assertFlattenedLayout(flat_track, [
            ("Clip", "A", 0, 25, (0, 25)),
            ("Clip", "A", 25, 25, (25, 25)),
            ("Clip", "B", 50, 35, (0, 35)),
            ("Clip", "B", 85, 15, (35, 15)),
            ("Clip", "C", 100, 50, (0, 50)),
        ])
        # the disabled clip is not part of the output, and the flattened
        # pieces still cover the source range of the lower material exactly
        self.assertNotIn("X", [child.name for child in flat_track])
        self.assertTrue(all(child.visible() for child in flat_track))
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["A"],
            24: ["A"],
            25: ["A"],
            49: ["A"],
            50: ["B"],
            84: ["B"],
            85: ["B"],
            99: ["B"],
            100: ["C"],
            149: ["C"],
        })
        # flattening is non-destructive for the inputs
        self.assertFalse(stack[1][1].enabled)

    def test_flatten_disabled_track_between_visible_tracks(self):
        """A disabled track contributes neither clips nor transitions.

        top:    [ gap 0-20 |  T 20-80  | gap 80-150 ]
        middle: [ M 0-50   | TM 40-65  | N 50-100  ]  (disabled)
        bottom: [ A 0-50   |  B 50-100 |  C 100-150 ]
        flat:   [ A 0-20   |  T 20-80  |  B 80-100 | C 100-150 ]
        """
        bottom = _track("bottom", [
            _clip("A", 50),
            _clip("B", 50),
            _clip("C", 50),
        ])
        middle = _track("middle", [
            _clip("M", 50, start=7),
            _transition("TM", 10, 15),
            _clip("N", 50),
        ], enabled=False)
        top = _track("top", [
            _gap(20),
            _clip("T", 60, start=4),
            _gap(70),
        ])
        flat_track = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[bottom, middle, top])
        )

        self.assertFlattenedLayout(flat_track, [
            ("Clip", "A", 0, 20, (0, 20)),
            ("Clip", "T", 20, 60, (4, 60)),
            ("Clip", "B", 80, 20, (30, 20)),
            ("Clip", "C", 100, 50, (0, 50)),
        ])
        self.assertEqual(
            [child.name for child in flat_track],
            ["A", "T", "B", "C"],
        )
        self.assertNotIn(
            "Transition",
            [child.schema_name() for child in flat_track],
        )
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["A"],
            19: ["A"],
            20: ["T"],
            79: ["T"],
            80: ["B"],
            99: ["B"],
            100: ["C"],
        })

    def test_flatten_transition_overlap_matches_material_attribution(self):
        """Transition ranges must agree with the clips they join.

        upper: [ D 0-50 |     T 40-65      | E 50-100 ]
        lower: [ A 0-50 |     B 50-100     | C 100-150 ]
        flat:  [ D 0-50 | T 40-65 | E 50-100 | C 100-150 ]

        D and E are adjacent on the upper track; T's 10 frame in-offset and
        15 frame out-offset make it overlap D's tail and E's head, so the
        flattened T range starts at 40 and ends at 65.
        """
        lower = _track("lower", [
            _clip("A", 50),
            _clip("B", 50),
            _clip("C", 50),
        ])
        upper = _track("upper", [
            _clip("D", 50),
            _transition("T", 10, 15),
            _clip("E", 50),
        ])
        flat_track = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[lower, upper])
        )

        self.assertFlattenedLayout(flat_track, [
            ("Clip", "D", 0, 50, (0, 50)),
            ("Transition", "T", 40, 25, None),
            ("Clip", "E", 50, 50, (0, 50)),
            ("Clip", "C", 100, 50, (0, 50)),
        ])
        transition = flat_track[1]
        self.assertEqual(transition.in_offset, _rt(10))
        self.assertEqual(transition.out_offset, _rt(15))
        self.assertTransitionBoundariesConsistent(flat_track)
        # the visible material changes at the incoming clip's start, inside
        # the transition overlap, and the transition keeps its own attribution
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["D"],
            39: ["D"],
            49: ["D"],
            50: ["E"],
            64: ["E"],
            65: ["E"],
            99: ["E"],
            100: ["C"],
        })

    def test_flatten_upper_gap_over_lower_transition(self):
        """A gap above a transition must preserve that transition intact.

        upper: [ X 0-30 |        gap 30-100        | Y 100-150 ]
        lower: [ A 0-50 | TL 40-60 | B 50-100      |    --     ]
        flat:  [ X 0-30 | A 30-50 | TL 40-60 | B 50-100 | Y 100-150 ]
        """
        lower = _track("lower", [
            _clip("A", 50),
            _transition("TL", 10, 10),
            _clip("B", 50),
        ])
        upper = _track("upper", [
            _clip("X", 30),
            _gap(70),
            _clip("Y", 50),
        ])
        flat_track = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[lower, upper])
        )

        self.assertFlattenedLayout(flat_track, [
            ("Clip", "X", 0, 30, (0, 30)),
            ("Clip", "A", 30, 20, (30, 20)),
            ("Transition", "TL", 40, 20, None),
            ("Clip", "B", 50, 50, (0, 50)),
            ("Clip", "Y", 100, 50, (0, 50)),
        ])
        transition = flat_track[2]
        # the overlap window is retained even though a gap covers it
        self.assertEqual(transition.in_offset, _rt(10))
        self.assertEqual(transition.out_offset, _rt(10))
        self.assertTransitionBoundariesConsistent(flat_track)
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["X"],
            29: ["X"],
            30: ["A"],
            49: ["A"],
            50: ["B"],
            99: ["B"],
            100: ["Y"],
            149: ["Y"],
        })

    def test_flatten_normalize_lengths_keeps_time_mapping(self):
        """Length normalization must not shift material within the result.

        lower: [ A (100, source 5) ]
        upper: [ B (20, source 2)  ]
        flat:  [ B | A trimmed from source 25 ]
        """
        lower = _track("lower", [_clip("A", 100, start=5)])
        upper = _track("upper", [_clip("B", 20, start=2)])
        flat_track = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[lower, upper])
        )

        self.assertEqual(flat_track.duration(), _rt(100))
        self.assertFlattenedLayout(flat_track, [
            ("Clip", "B", 0, 20, (2, 20)),
            # source continuity: 5 + 20 = 25
            ("Clip", "A", 20, 80, (25, 80)),
        ])
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["B"],
            19: ["B"],
            20: ["A"],
            99: ["A"],
        })

        # padding a short lower track must expose the whole upper track
        lower = _track("lower", [_clip("A", 50)])
        upper = _track("upper", [
            _clip("X", 50, start=10),
            _clip("Y", 50, start=20),
        ])
        flat_track = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[lower, upper])
        )

        self.assertEqual(flat_track.duration(), _rt(100))
        self.assertFlattenedLayout(flat_track, [
            ("Clip", "X", 0, 50, (10, 50)),
            ("Clip", "Y", 50, 50, (20, 50)),
        ])
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["X"],
            49: ["X"],
            50: ["Y"],
            99: ["Y"],
        })

    def test_flatten_equal_duration_is_not_content_equivalence(self):
        """Equal total durations do not imply equivalent flattened content.

        All three stacks flatten to 100 frames.  The first two place the
        upper material at different times; the third reaches the same total
        duration only because normalization pads its short upper track.
        """
        def build_stack(lower_children, upper_children):
            return otio.schema.Stack(children=[
                _track("lower", lower_children),
                _track("upper", upper_children),
            ])

        flat_x_first = otio.algorithms.flatten_stack(build_stack(
            [_clip("A", 50), _clip("B", 50)],
            [_clip("X", 50, start=10), _gap(50)],
        ))
        flat_y_last = otio.algorithms.flatten_stack(build_stack(
            [_clip("A", 50), _clip("B", 50)],
            [_gap(50), _clip("Y", 50, start=20)],
        ))
        # the upper track is only 20 frames long here and gets padded
        flat_padded = otio.algorithms.flatten_stack(build_stack(
            [_clip("A", 100, start=5)],
            [_clip("B", 20, start=2)],
        ))

        self.assertEqual(flat_x_first.duration(), flat_y_last.duration())
        self.assertEqual(flat_x_first.duration(), flat_padded.duration())
        self.assertEqual(flat_x_first.duration(), _rt(100))
        self.assertFalse(flat_x_first.is_equivalent_to(flat_y_last))
        self.assertFalse(flat_x_first.is_equivalent_to(flat_padded))

        self.assertFlattenedLayout(flat_x_first, [
            ("Clip", "X", 0, 50, (10, 50)),
            ("Clip", "B", 50, 50, (0, 50)),
        ])
        self.assertFlattenedLayout(flat_y_last, [
            ("Clip", "A", 0, 50, (0, 50)),
            ("Clip", "Y", 50, 50, (20, 50)),
        ])
        # padding adds time, not material: only the upper clip contributes
        self.assertFlattenedLayout(flat_padded, [
            ("Clip", "B", 0, 20, (2, 20)),
            ("Clip", "A", 20, 80, (25, 80)),
        ])

    def test_flatten_missing_references_survive_occlusion(self):
        """Missing media references do not affect visibility bookkeeping."""
        missing_lower = otio.schema.MissingReference(name="missing_lower")
        missing_upper = otio.schema.MissingReference(name="missing_upper")
        lower = _track("lower", [
            _clip("A", 50, media_reference=missing_lower),
            _clip("B", 50, media_reference=missing_lower),
        ])
        upper = _track("upper", [
            _gap(50),
            _clip("M", 50, start=9, media_reference=missing_upper),
        ])
        flat_track = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[lower, upper])
        )

        self.assertFlattenedLayout(flat_track, [
            ("Clip", "A", 0, 50, (0, 50)),
            ("Clip", "M", 50, 50, (9, 50)),
        ])
        # B is fully obscured by M, so its missing reference does not surface
        self.assertEqual([child.name for child in flat_track], ["A", "M"])
        references = [
            (child.name,
             type(child.media_reference).__name__,
             child.media_reference.name)
            for child in flat_track
        ]
        self.assertEqual(references, [
            ("A", "MissingReference", "missing_lower"),
            ("M", "MissingReference", "missing_upper"),
        ])
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["A"],
            49: ["A"],
            50: ["M"],
            99: ["M"],
        })

    def test_flatten_successive_upper_gaps_reveal_lower_layers(self):
        """Each empty region resolves to the highest material that fills it.

        top:    [   gap 0-100   | T 100-150 ]
        middle: [ gap 0-50 | M 50-100 | gap 100-150 ]
        bottom: [  A 0-50  |  B 50-100 |  C 100-150  ]
        flat:   [  A 0-50  |  M 50-100 |  T 100-150  ]
        """
        bottom = _track("bottom", [
            _clip("A", 50),
            _clip("B", 50),
            _clip("C", 50),
        ])
        middle = _track("middle", [
            _gap(50),
            _clip("M", 50, start=5),
            _gap(50),
        ])
        top = _track("top", [
            _gap(100),
            _clip("T", 50, start=7),
        ])
        flat_track = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[bottom, middle, top])
        )

        self.assertFlattenedLayout(flat_track, [
            ("Clip", "A", 0, 50, (0, 50)),
            ("Clip", "M", 50, 50, (5, 50)),
            ("Clip", "T", 100, 50, (7, 50)),
        ])
        self.assertEqual(
            [child.name for child in flat_track],
            ["A", "M", "T"],
        )
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["A"],
            49: ["A"],
            50: ["M"],
            99: ["M"],
            100: ["T"],
            149: ["T"],
        })

    def test_flatten_fully_obscured_transition_is_dropped(self):
        """A transition hidden by an upper clip leaves no trace.

        upper: [         X 0-100         ]
        lower: [ A 0-50 | TL 40-60 | B 50-100 ]
        flat:  [         X 0-100         ]
        """
        lower = _track("lower", [
            _clip("A", 50),
            _transition("TL", 10, 10),
            _clip("B", 50),
        ])
        upper = _track("upper", [_clip("X", 100)])
        flat_track = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[lower, upper])
        )

        self.assertFlattenedLayout(flat_track, [
            ("Clip", "X", 0, 100, (0, 100)),
        ])
        self.assertNotIn(
            "Transition",
            [child.schema_name() for child in flat_track],
        )
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["X"],
            49: ["X"],
            50: ["X"],
            99: ["X"],
        })

    def test_flatten_combined_occlusion_transition_and_missing_media(self):
        """Stable mapping when occlusion, transitions and missing media mix.

        top:    [ X 0-30 | gap 30-80 | Y 80-110 ]
        middle: [ M 0-80 (disabled)              ]
        bottom: [ A 0-40 | TL 35-45 | B 40-80    ]
        flat:   [ X 0-30 | A 30-40 | TL 35-45 | B 40-80 | Y 80-110 ]

        The middle track is disabled, so it never hides the bottom track or
        the transition it carries.  The top track's gap exposes the bottom
        transition, which keeps its 5 frame overlap on each side.
        """
        missing = otio.schema.MissingReference(name="missing_A")
        missing_middle = otio.schema.MissingReference(name="missing_middle")
        bottom = _track("bottom", [
            _clip("A", 40, media_reference=missing),
            _transition("TL", 5, 5),
            _clip("B", 40, start=100, media_reference=missing),
        ])
        middle = _track("middle", [
            _clip("M", 80, start=7, media_reference=missing_middle,
                  enabled=False),
        ])
        top = _track("top", [
            _clip("X", 30, start=3),
            _gap(50),
            _clip("Y", 30, start=9),
        ])
        stack = otio.schema.Stack(children=[bottom, middle, top])
        flat_track = otio.algorithms.flatten_stack(stack)

        self.assertEqual(flat_track.duration(), _rt(110))
        self.assertFlattenedLayout(flat_track, [
            ("Clip", "X", 0, 30, (3, 30)),
            ("Clip", "A", 30, 10, (30, 10)),
            ("Transition", "TL", 35, 10, None),
            ("Clip", "B", 40, 40, (100, 40)),
            ("Clip", "Y", 80, 30, (9, 30)),
        ])
        self.assertEqual(
            [child.name for child in flat_track],
            ["X", "A", "TL", "B", "Y"],
        )
        transition = flat_track[2]
        self.assertEqual(transition.in_offset, _rt(5))
        self.assertEqual(transition.out_offset, _rt(5))
        self.assertTransitionBoundariesConsistent(flat_track)
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["X"],
            29: ["X"],
            30: ["A"],
            34: ["A"],
            35: ["A"],
            39: ["A"],
            40: ["B"],
            44: ["B"],
            79: ["B"],
            80: ["Y"],
            109: ["Y"],
        })
        self.assertEqual(flat_track.trimmed_range(), _time_range(0, 110))
        self.assertEqual(len(flat_track.range_of_all_children()), 5)

        # the output mapping must be stable across repeated runs and
        # survive serialization round trips
        serialized = otio.adapters.write_to_string(flat_track, "otio_json")
        self.assertEqual(
            serialized,
            otio.adapters.write_to_string(
                otio.algorithms.flatten_stack(stack),
                "otio_json",
            ),
        )
        self.assertEqual(
            serialized,
            otio.adapters.write_to_string(
                otio.adapters.read_from_string(serialized, "otio_json"),
                "otio_json",
            ),
        )

    def test_flatten_single_track_read_contract(self):
        """A single track round trips and keeps the usual reader contract."""
        original = _track("original", [
            _clip("A", 40),
            _transition("T", 5, 5),
            _clip("B", 40),
            _gap(20),
        ])
        stack = otio.schema.Stack(children=[original])
        flat_track = otio.algorithms.flatten_stack(stack)

        self.assertJsonEqual(flat_track[:], original[:])
        self.assertEqual(flat_track.duration(), _rt(100))
        self.assertEqual(flat_track.trimmed_range(), _time_range(0, 100))
        self.assertEqual(
            [(child.schema_name(), child.name) for child in flat_track],
            [
                ("Clip", "A"),
                ("Transition", "T"),
                ("Clip", "B"),
                ("Gap", ""),
            ],
        )
        self.assertVisibleClipNamesAt(flat_track, {
            0: ["A"],
            39: ["A"],
            40: ["B"],
            79: ["B"],
            80: [],
            99: [],
        })
        self.assertFalse(flat_track[3].visible())

        # flattening is idempotent and the track-list entry point agrees
        refolded = otio.algorithms.flatten_stack(
            otio.schema.Stack(children=[flat_track])
        )
        self.assertJsonEqual(refolded[:], flat_track[:])
        from_list = otio.algorithms.flatten_stack([original])
        self.assertEqual(
            otio.adapters.write_to_string(from_list, "otio_json"),
            otio.adapters.write_to_string(flat_track, "otio_json"),
        )

    def test_top_child_at_time(self):
        stack = otio.schema.Stack(
            children=[
                self.trackABC,
                self.trackDgE,
            ]
        )

        top_child = otio.algorithms.top_clip_at_time(
            stack,
            otio.opentime.RationalTime(0, 24)
        )
        self.assertEqual(top_child, self.trackDgE[0])

        stack.append(
            otio.schema.Track(
                children=[
                    otio.schema.Gap(
                        source_range=otio.opentime.TimeRange(
                            otio.opentime.RationalTime(0, 24),
                            otio.opentime.RationalTime(10, 24)
                        )
                    )
                ]
            )
        )

        top_child = otio.algorithms.top_clip_at_time(
            stack,
            otio.opentime.RationalTime(0, 24)
        )
        self.assertEqual(top_child, self.trackDgE[0])


if __name__ == '__main__':
    unittest.main()
