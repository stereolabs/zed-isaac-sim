"""Unit tests for the rule in :mod:`sl.sensor.camera.retime`: the physics and app update rates at which ZED
streams send every frame, and putting the timing back at Stop.

Each timing is checked against a model of Isaac Sim's multi-tick rendering: the camera is drawn in the first
app update whose physics reaches each tick k/fps, and PhysX runs the physics steps that fit in the time an
update advances. A stream sends one frame per app update, so it sends every frame when no update draws two.
"""
import struct
from collections import Counter
from fractions import Fraction
from typing import List

import carb.settings
import omni.kit.test

from sl.sensor.camera.retime import (GONE, TIMING_FIT, TIMING_FRAME, TIMING_OFF, TIMING_SETTING, Change, Probe,
                                     changes_since, fits, retimed, set_stream_timing, snapshot, stream_timing,
                                     undo, whole_hz)
from sl.sensor.camera.utils import STREAM_FRAME_RATES, stream_frame_rate

# Isaac Sim's warm-up at Play: 2 physics steps before the first app update
_WARM_UP_STEPS = 2
# A stream's first frames come a few frames after Play, past the ticks the warm-up already reached
_FIRST_TICK = 10


def _ticks_per_update(physics_hz: int, update_hz: int, fps: int, frames: int = 40) -> List[int]:
    """How many ticks of a camera at ``fps`` each app update that draws any draws, from the model above."""
    ends, drawn_in = [], []
    update = 0
    for k in range(_FIRST_TICK, _FIRST_TICK + frames):
        tick = Fraction(k * physics_hz, fps)
        while not ends or ends[-1] < tick:
            update += 1
            ends.append(_WARM_UP_STEPS + update * physics_hz // update_hz)
        drawn_in.append(update)
    return list(Counter(drawn_in).values())


def _set(app: dict, name: str, value):
    if value is None:
        app.pop(name, None)
    else:
        app[name] = value


def _probes(app: dict, *names: str) -> List[Probe]:
    """Probes over ``app``, a dict standing in for the app's timing values: a missing key is unset."""
    return [Probe(name, lambda name=name: app.get(name), lambda value, name=name: _set(app, name, value))
            for name in names]


def _retime(app: dict, probes: List[Probe], **new):
    """Set ``new`` in ``app`` as a retime would, and return what changed."""
    before = snapshot(probes)
    for name, value in new.items():
        _set(app, name, value)
    return changes_since(before)


class TestOgn(omni.kit.test.AsyncTestCase):
    async def test_model_shows_the_frames_retiming_saves(self):
        # 30 fps over 15 Hz updates: two ticks in every update, one of them sent
        self.assertEqual(set(_ticks_per_update(60, 15, 30)), {2})
        # 50 Hz updates, whole (200 Hz physics) or not (60 Hz): one tick per update at most, as measured in Isaac Sim
        self.assertEqual(set(_ticks_per_update(200, 50, 30)), {1})
        self.assertEqual(set(_ticks_per_update(60, 50, 30)), {1})

    async def test_timing_that_fits_is_kept(self):
        for physics_hz, update_hz, rates in ((60, 60, [30]), (60, 60, [15]), (60, 60, [60]), (120, 60, [30]),
                                             (210, 15, [15]), (240, 120, [30, 60]), (60, 30, [15, 30]),
                                             (200, 50, [30]), (60, 50, [30]), (61, 60, [30]), (200, 100, [15, 60])):
            with self.subTest(physics_hz=physics_hz, update_hz=update_hz, rates=rates):
                self.assertEqual(retimed(physics_hz, update_hz, rates), (physics_hz, update_hz))

    async def test_updates_that_do_not_fit_go_to_the_highest_multiple_at_or_below(self):
        self.assertEqual(retimed(50, 40, [30]), (60, 30))  # up to 2 steps, 40 ms, in an update
        self.assertEqual(retimed(100, 70, [60]), (120, 60))
        self.assertEqual(retimed(209, 30, [30]), (210, 30))
        self.assertEqual(retimed(50, 40, [15, 30]), (60, 30))

    async def test_updates_slower_than_the_stream_go_up_to_its_rate(self):
        self.assertEqual(retimed(60, 20, [30]), (60, 30))
        self.assertEqual(retimed(60, None, [30]), (60, 30))
        self.assertEqual(retimed(60, 59.94, [30]), (60, 30))

    async def test_physics_never_gets_slower(self):
        self.assertEqual(retimed(10, 30, [30]), (30, 30))
        self.assertEqual(retimed(50, 60, [60]), (60, 60))

    async def test_rejects_what_it_cannot_retime(self):
        for physics_hz, rates in ((0, [30]), (60, []), (60, [0])):
            with self.subTest(physics_hz=physics_hz, rates=rates):
                with self.assertRaises(ValueError):
                    retimed(physics_hz, 60, rates)

    async def test_every_retimed_timing_sends_every_frame_without_adding_updates(self):
        for fps in STREAM_FRAME_RATES:
            for physics_hz in range(20, 250, 7):
                for update_hz in range(10, 260, 9):
                    physics, update = retimed(physics_hz, update_hz, [fps])
                    with self.subTest(physics_hz=physics_hz, update_hz=update_hz, fps=fps):
                        self.assertTrue(fits(physics, update, fps))
                        if fits(physics_hz, update_hz, fps):
                            self.assertEqual((physics, update), (physics_hz, update_hz))
                        else:
                            self.assertEqual(update, max(update_hz // fps, 1) * fps)
                        self.assertTrue(physics_hz <= physics < physics_hz + update)
                        self.assertEqual(set(_ticks_per_update(physics, update, fps)), {1})

    async def test_one_update_per_frame_updates_at_the_stream_rate_even_when_the_timing_fits(self):
        self.assertEqual(retimed(60, 60, [30], one_per_frame=True), (60, 30))
        self.assertEqual(retimed(60, 60, [15], one_per_frame=True), (60, 15))
        self.assertEqual(retimed(60, 30, [30], one_per_frame=True), (60, 30))
        self.assertEqual(retimed(200, 50, [30], one_per_frame=True), (210, 30))
        self.assertEqual(retimed(200, 100, [30], one_per_frame=True), (210, 30))
        self.assertEqual(retimed(60, None, [30], one_per_frame=True), (60, 30))
        self.assertEqual(retimed(60, 60, [120], one_per_frame=True), (120, 120))
        self.assertEqual(retimed(240, 120, [15, 60], one_per_frame=True), (240, 60))

    async def test_every_one_per_frame_timing_draws_each_frame_on_its_own_update(self):
        for fps in STREAM_FRAME_RATES:
            for physics_hz in range(20, 250, 7):
                for update_hz in (None, *range(10, 260, 9)):
                    physics, update = retimed(physics_hz, update_hz, [fps], one_per_frame=True)
                    with self.subTest(physics_hz=physics_hz, update_hz=update_hz, fps=fps):
                        self.assertEqual(update, fps)
                        self.assertTrue(physics_hz <= physics < physics_hz + update)
                        self.assertEqual(set(_ticks_per_update(physics, update, fps)), {1})

    async def test_stream_timing_setting(self):
        settings = carb.settings.get_settings()
        saved = settings.get(TIMING_SETTING)
        try:
            settings.destroy_item(TIMING_SETTING)
            self.assertEqual(stream_timing(), TIMING_FIT)
            for timing in (TIMING_FIT, TIMING_FRAME, TIMING_OFF):
                set_stream_timing(timing)
                self.assertEqual(stream_timing(), timing)
            # a command line can give any case, or a value Kit parses as a bool
            settings.set(TIMING_SETTING, " Frame ")
            self.assertEqual(stream_timing(), TIMING_FRAME)
            for unknown in ("everyFrame", False):
                settings.set(TIMING_SETTING, unknown)
                self.assertEqual(stream_timing(), TIMING_FIT)
            with self.assertRaises(ValueError):
                set_stream_timing("everyFrame")
        finally:
            if saved is None:
                settings.destroy_item(TIMING_SETTING)
            else:
                settings.set(TIMING_SETTING, saved)

    async def test_every_stream_of_a_mixed_stage_sends_every_frame(self):
        rates = [15, 60]
        physics, update = retimed(50, 40, rates)
        self.assertEqual((physics, update), (60, 60))
        for fps in rates:
            with self.subTest(fps=fps):
                self.assertTrue(fits(physics, update, fps))
                self.assertEqual(set(_ticks_per_update(physics, update, fps)), {1})

    async def test_an_invalid_stream_rate_counts_as_the_one_the_stream_runs_at(self):
        self.assertEqual(stream_frame_rate(25), 30)
        self.assertEqual(stream_frame_rate(60), 60)

    async def test_whole_rate_from_a_step_read_back(self):
        self.assertEqual(whole_hz(1.0 / (1.0 / 15.0)), 15)
        self.assertEqual(whole_hz(1.0 / (14 * (1.0 / 210.0))), 15)
        self.assertEqual(whole_hz(1.0 / (13 * (1.0 / 195.0))), 15)
        self.assertIsNone(whole_hz(59.94))
        self.assertIsNone(whole_hz(None))
        self.assertIsNone(whole_hz(0.0))
        self.assertFalse(fits(60, 59.94, 30))

    async def test_stop_puts_back_what_the_retime_changed(self):
        app = {"physics": 200, "updates": 50, "minFrameRate": 100}
        changes = _retime(app, _probes(app, "physics", "updates", "minFrameRate", "timeCodes"),
                          physics=210, updates=30, minFrameRate=30, timeCodes=30)
        restored, kept = undo(changes)
        # a value the retime authored where there was none is unset again
        self.assertEqual(app, {"physics": 200, "updates": 50, "minFrameRate": 100})
        self.assertEqual(kept, [])
        self.assertIn("physics 210 -> 200", restored)
        self.assertIn("timeCodes 30 -> unset", restored)

    async def test_a_value_the_retime_left_alone_is_not_written(self):
        app = {"physics": 120, "updates": 60}
        probes = _probes(app, "physics", "updates")
        changes = _retime(app, probes, physics=120, updates=30)
        self.assertEqual([change.probe.what for change in changes], ["updates"])
        app["physics"] = 180
        self.assertEqual(undo(changes), (["updates 30 -> 60"], []))
        self.assertEqual(app, {"physics": 180, "updates": 60})

    async def test_a_value_changed_since_play_is_kept(self):
        app = {"physics": 200, "updates": 50}
        changes = _retime(app, _probes(app, "physics", "updates"), physics=210, updates=30)
        app["updates"] = 15
        self.assertEqual(undo(changes), (["physics 210 -> 200"], ["updates at 15"]))
        self.assertEqual(app, {"physics": 200, "updates": 15})

    async def test_a_value_gone_by_stop_is_skipped(self):
        app = {"updates": 50}
        probes = _probes(app, "updates") + [Probe("closed stage", lambda: GONE, lambda value: self.fail("written"))]
        changes = [*_retime(app, probes[:1], updates=30), Change(probes[1], 15, 30)]
        self.assertEqual(undo(changes), (["updates 30 -> 50"], []))

    async def test_two_retimes_before_a_stop_go_back_to_the_first_timing(self):
        # Play then Play again before a physics step: both retimes are undone, latest first
        app = {"updates": 50}
        probes = _probes(app, "updates")
        changes = _retime(app, probes, updates=30) + _retime(app, probes, updates=60)
        undo(changes)
        self.assertEqual(app, {"updates": 50})

    async def test_a_value_already_back_by_stop_is_left_alone(self):
        # Kit puts the rate limit back itself at Stop
        app = {"rateLimit": 120.0}
        changes = _retime(app, _probes(app, "rateLimit"), rateLimit=30.0)
        app["rateLimit"] = 120.0
        self.assertEqual(undo(changes), ([], []))

    async def test_a_float_read_back_in_single_precision_is_the_same_value(self):
        def single(value: float) -> float:
            return struct.unpack("f", struct.pack("f", value))[0]

        app = {"step": 1.0 / 40}
        probes = _probes(app, "step")
        self.assertEqual(_retime(app, probes, step=single(1.0 / 40)), [])
        changes = _retime(app, probes, step=1.0 / 30)
        app["step"] = single(1.0 / 30)
        undo(changes)
        self.assertEqual(app, {"step": single(1.0 / 40)})

    async def test_the_value_before_a_retime_can_be_read_elsewhere(self):
        # the root layer's time codes per second still holds 60 while the timeline's 40 is in effect
        app = {"rootLayer": 60.0}
        probe = _probes(app, "rootLayer")[0]._replace(before=lambda: 40.0)
        undo(_retime(app, [probe], rootLayer=30.0))
        self.assertEqual(app, {"rootLayer": 40.0})

    async def test_a_retime_that_changes_nothing_leaves_nothing_to_undo(self):
        app = {"updates": 30}
        changes = _retime(app, _probes(app, "updates"), updates=30)
        self.assertEqual(changes, [])
        self.assertEqual(undo(changes), ([], []))
