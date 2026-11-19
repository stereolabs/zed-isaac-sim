"""The app update a frame's tick fell in (update_clock), and the ZED_FrameImu node stamping each frame with its
tick, sending one frame per app update and giving the rate it sends at.

The clock is fed step by step and the node runs with a stand-in database: no simulation needed.
"""
from types import SimpleNamespace

import numpy as np
import omni.graph.core as og
import omni.kit.test

from sl.sensor.camera import update_clock
from sl.sensor.camera.nodes.SlFrameImu import SlFrameImu

_NODE = "/Render/PostProcess/SDGPipeline/zed_30000_frame_imu"


def _run(clock, render_fps, substeps, updates):
    """Steps a clock as Isaac Sim does: two warm-up physics steps, then ``substeps`` per app update."""
    dt = 1.0 / render_fps / substeps
    t = 0.0
    for _ in range(2):
        t += dt
        clock.step(0, t)
    for update in range(1, updates + 1):
        for _ in range(substeps):
            t += dt
            clock.step(update, t)
    return dt


def _compute(simulation_time, state, fps=30):
    db = SimpleNamespace(
        inputs=SimpleNamespace(orientation=np.array((0.0, 0.0, 0.0, 1.0)), linAcc=np.array((0.0, 0.0, 9.81)),
                               metersPerUnit=1.0, simulationTime=simulation_time, fps=fps),
        outputs=SimpleNamespace(), per_instance_state=state, node=SimpleNamespace(get_prim_path=lambda: _NODE))
    SlFrameImu.compute(db)
    return db.outputs


class TestOgn(omni.kit.test.AsyncTestCase):

    async def setUp(self):
        update_clock._clock.clear()

    async def tearDown(self):
        update_clock._clock.clear()

    async def test_first_end_at_or_after(self):
        ends = [0.1, 0.2, 0.3]
        self.assertEqual(update_clock.first_end_at_or_after(0.15, ends), 0.2)  # inside an update: its end
        self.assertEqual(update_clock.first_end_at_or_after(0.2 - 1e-9, ends), 0.2)
        self.assertEqual(update_clock.first_end_at_or_after(0.2 + 1e-9, ends), 0.2)  # an end, give or take float noise
        self.assertIsNone(update_clock.first_end_at_or_after(0.35, ends))
        self.assertIsNone(update_clock.first_end_at_or_after(0.1, []))

    async def test_tick_inside_an_update(self):
        # 15 fps, 14 steps of 1/210 s: the warm-up puts each update's end 2 steps past a tick.
        clock = update_clock.UpdateClock()
        dt = _run(clock, 15.0, 14, 30)
        for k in range(1, 30):
            self.assertAlmostEqual(clock.update_end(k / 15.0), k / 15.0 + 2 * dt, places=12)

    async def test_tick_on_an_update_end(self):
        # 60 Hz updates of 2 steps at 120 Hz, a 30 fps camera: the ticks are update ends.
        clock = update_clock.UpdateClock()
        _run(clock, 60.0, 2, 60)
        for k in range(1, 30):
            self.assertAlmostEqual(clock.update_end(k / 30.0), k / 30.0, places=12)

    async def test_running_update_counts_and_a_new_run_clears(self):
        clock = update_clock.UpdateClock()
        clock.step(1, 0.1)
        clock.step(1, 0.2)  # the update still running: its latest step is its end so far
        self.assertEqual(clock.update_end(0.15), 0.2)
        clock.step(2, 0.3)
        self.assertEqual(clock.update_end(0.15), 0.2)
        clock.step(1, 0.05)  # time went back: Stop and Play
        self.assertIsNone(clock.update_end(0.15))
        self.assertEqual(clock.update_end(0.01), 0.05)

    async def test_update_period(self):
        clock = update_clock.UpdateClock()
        clock.step(1, 0.1)
        clock.step(2, 0.2)
        self.assertIsNone(clock.update_period())  # one finished update: no period yet
        _run(clock, 15.0, 4, 30)
        self.assertAlmostEqual(clock.update_period(), 1 / 15.0, places=12)

    async def test_stream_rate(self):
        self.assertEqual(update_clock.stream_rate(30, 1 / 15.0), 15)  # two ticks per update: one sent
        self.assertEqual(update_clock.stream_rate(60, 1 / 15.0), 15)
        self.assertEqual(update_clock.stream_rate(30, 1 / 20.0), 15)  # every other tick: 20 would be uneven
        self.assertEqual(update_clock.stream_rate(30, 1 / 12.0), 10)
        self.assertEqual(update_clock.stream_rate(15, 1 / 10.0), 7)  # 7.5 a second, rounded down
        self.assertEqual(update_clock.stream_rate(15, 1 / 15.0), 15)
        self.assertEqual(update_clock.stream_rate(15, 1 / 60.0), 15)  # several updates per tick
        self.assertEqual(update_clock.stream_rate(30, None), 30)

    async def test_node_stamps_the_tick_and_sends_one_frame_per_update(self):
        # A 30 fps stream over 15 Hz updates of 4 steps at 60 Hz: ticks 16/15 and 16/15 + 1/30 fall in the update
        # ending at 16/15 + 2/60, the second on its end.
        _run(update_clock._clock, 15.0, 4, 30)
        state = SlFrameImu.State()
        out = _compute(16 / 15.0, state)
        self.assertEqual((out.frameTime, out.execOut), (16 / 15.0, og.ExecutionAttributeState.ENABLED))
        self.assertEqual(out.fps, 15)  # what the ZED Stream node declares
        out = _compute(16 / 15.0 + 1 / 30.0, state)
        self.assertFalse(hasattr(out, "execOut"))
        self.assertTrue(state.repeat_warned)
        out = _compute(17 / 15.0, state)
        self.assertEqual((out.frameTime, out.execOut), (17 / 15.0, og.ExecutionAttributeState.ENABLED))

    async def test_frame_stride(self):
        self.assertEqual(update_clock.frame_stride(30, 1 / 30.0), 1)
        self.assertEqual(update_clock.frame_stride(30, 1 / 60.0), 1)
        self.assertEqual(update_clock.frame_stride(30, 1 / 20.0), 2)
        self.assertEqual(update_clock.frame_stride(30, 1 / 15.0), 2)
        self.assertEqual(update_clock.frame_stride(30, 1 / 12.0), 3)
        self.assertEqual(update_clock.frame_stride(120, 1 / 60.0), 2)
        self.assertEqual(update_clock.frame_stride(30, None), 1)

    async def test_node_sends_evenly_spaced_frames_over_slower_updates(self):
        # A 30 fps stream over 20 Hz updates of 3 steps at 60 Hz: the first tick of each update would be 33 then
        # 67 ms apart; every other tick is 67 ms apart, each in an update of its own.
        _run(update_clock._clock, 20.0, 3, 60)
        state = SlFrameImu.State()
        sent = []
        for k in range(30, 80):
            out = _compute(k / 30.0, state)
            if hasattr(out, "execOut"):
                sent.append(out.frameTime)
                self.assertEqual(out.fps, 15)
        gaps = np.round(np.diff(sent) * 1e3, 3)
        self.assertEqual(set(gaps.tolist()), {66.667})
        self.assertEqual(len(sent), 25)

    async def test_node_waits_for_the_update_rate(self):
        # A stream started mid-run: the ZED node opens on its first frame, so that frame must carry the rate.
        sub, update_clock._sub = update_clock._sub, object()
        try:
            update_clock._clock.step(1, 2.0)
            state = SlFrameImu.State()
            self.assertFalse(hasattr(_compute(2.0, state), "execOut"))  # no finished update yet
            for update in (2, 3):
                for k in range(1, 5):
                    update_clock._clock.step(update, 2.0 + (update - 2) / 15.0 + k / 60.0)
            out = _compute(2.0 + 2 / 15.0, state)
            self.assertEqual((out.fps, out.execOut), (15, og.ExecutionAttributeState.ENABLED))
        finally:
            update_clock._sub = sub

    async def test_node_sends_every_frame_without_the_clock(self):
        state = SlFrameImu.State()
        for t in (1.0, 1.0 + 1 / 30.0):
            out = _compute(t, state)
            self.assertEqual((out.frameTime, out.execOut, out.fps), (t, og.ExecutionAttributeState.ENABLED, 30))

    async def test_node_passes_an_unstamped_frame(self):
        out = _compute(0.0, SlFrameImu.State())
        self.assertEqual(out.frameTime, 0.0)
        self.assertEqual(out.execOut, og.ExecutionAttributeState.ENABLED)
