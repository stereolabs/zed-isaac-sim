"""The IMU history of every physics step (frame_imu) and the ZED_FrameImu node's lookup in it at each streamed
frame's time.

The node's compute runs with a stand-in database, so the test needs neither a graph nor a simulation.
"""
import math
from types import SimpleNamespace

import numpy as np
import omni.graph.core as og
import omni.kit.test
from pxr import Gf

from sl.sensor.camera import frame_imu
from sl.sensor.camera.nodes.SlFrameImu import SlFrameImu

_NODE = "/Render/PostProcess/SDGPipeline/zed_30000_frame_imu"


def _compute(simulation_time, orientation=(0.0, 0.0, 0.0, 1.0), lin_acc=(0.0, 0.0, 9.81), meters_per_unit=1.0,
             state=None):
    """ZED_FrameImu's outputs for these inputs."""
    db = SimpleNamespace(
        inputs=SimpleNamespace(orientation=np.array(orientation), linAcc=np.array(lin_acc),
                               metersPerUnit=meters_per_unit, simulationTime=simulation_time, fps=30),
        outputs=SimpleNamespace(), per_instance_state=state or SlFrameImu.State(),
        node=SimpleNamespace(get_prim_path=lambda: _NODE))
    SlFrameImu.compute(db)
    return db.outputs


class TestOgn(omni.kit.test.AsyncTestCase):

    async def tearDown(self):
        frame_imu._histories.pop(_NODE, None)

    async def test_history_lookup(self):
        history, s = frame_imu.ImuHistory(), math.sqrt(0.5)

        def at(t):
            found, imu = history.at(t)
            if imu is None:
                return found, None
            q, acc = imu
            return found, [q.GetReal(), *q.GetImaginary(), *acc]

        self.assertEqual(at(1.0), (frame_imu.NO_HISTORY, None))
        history.push(1.000, Gf.Quatd(1.0), Gf.Vec3d(0.0, 0.0, 1.0))
        history.push(1.005, Gf.Quatd(s, 0.0, 0.0, s), Gf.Vec3d(0.0, 0.0, 3.0))  # 90 deg about z
        found, v = at(1.0025)  # halfway: slerp and lerp
        self.assertEqual(found, frame_imu.FOUND)
        for got, want in zip(v, (math.cos(math.pi / 8), 0.0, 0.0, math.sin(math.pi / 8), 0.0, 0.0, 2.0)):
            self.assertAlmostEqual(got, want, places=6)
        found, v = at(1.005)
        self.assertEqual((found, v[6]), (frame_imu.FOUND, 3.0))
        self.assertEqual(at(0.9), (frame_imu.FOUND, [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]))  # before it: the first
        self.assertEqual(at(1.01)[0], frame_imu.MISSED)  # newer than the newest step
        history.push(0.5, Gf.Quatd(1.0), Gf.Vec3d(0.0, 0.0, 5.0))  # time went back: a new run
        self.assertEqual(at(1.0025)[0], frame_imu.MISSED)
        self.assertEqual(at(0.5), (frame_imu.FOUND, [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 5.0]))

        full = frame_imu.ImuHistory()
        for k in range(121):  # 1.2 s at 100 Hz: the oldest 0.2 s leave the 1 s history
            full.push(k * 0.01, Gf.Quatd(1.0), Gf.Vec3d(0.0, 0.0, 1.0))
        self.assertEqual(full.at(0.1)[0], frame_imu.MISSED)
        self.assertEqual(full.at(0.5)[0], frame_imu.FOUND)

    async def test_unregister_only_its_own(self):
        old, new = frame_imu.ImuHistory(), frame_imu.ImuHistory()
        frame_imu.register(_NODE, old)
        frame_imu.register(_NODE, new)  # the next Play's feeder, before the old one is destroyed
        frame_imu.unregister(_NODE, old)
        self.assertIs(frame_imu.lookup(_NODE), new)
        frame_imu.unregister(_NODE, new)
        self.assertIsNone(frame_imu.lookup(_NODE))

    async def test_node_passes_the_reading_through_in_m_per_s2(self):
        out = _compute(1.0, orientation=(0.0, 0.0, 0.6, 0.8), lin_acc=(0.0, 0.0, 981.0), meters_per_unit=0.01)
        self.assertEqual(list(out.orientation), [0.0, 0.0, 0.6, 0.8])
        for got, want in zip(out.linAcc, (0.0, 0.0, 9.81)):
            self.assertAlmostEqual(got, want, places=9)
        self.assertEqual(out.execOut, og.ExecutionAttributeState.ENABLED)

    async def test_node_takes_the_imu_at_the_frame_time(self):
        history, s = frame_imu.ImuHistory(), math.sqrt(0.5)
        history.push(1.000, Gf.Quatd(1.0), Gf.Vec3d(0.0, 0.0, 1.0))
        history.push(1.005, Gf.Quatd(s, 0.0, 0.0, s), Gf.Vec3d(0.0, 0.0, 3.0))
        frame_imu.register(_NODE, history)
        out = _compute(1.005, meters_per_unit=0.01)  # the history is already in m/s^2
        for got, want in zip(out.orientation, (0.0, 0.0, s, s)):  # IJKR
            self.assertAlmostEqual(got, want, places=12)
        self.assertEqual(list(out.linAcc), [0.0, 0.0, 3.0])
        out = _compute(0.0)  # not stamped from simulation time: the reading
        self.assertEqual(list(out.linAcc), [0.0, 0.0, 9.81])
        self.assertEqual(out.execOut, og.ExecutionAttributeState.ENABLED)

    async def test_node_warns_once_and_falls_back(self):
        history = frame_imu.ImuHistory()
        history.push(1.0, Gf.Quatd(1.0), Gf.Vec3d(0.0, 0.0, 1.0))
        frame_imu.register(_NODE, history)
        state = SlFrameImu.State()
        out = _compute(2.0, state=state)
        self.assertTrue(state.warned)
        self.assertEqual(list(out.linAcc), [0.0, 0.0, 9.81])

    async def test_node_never_stops_the_stream(self):
        frame_imu.register(_NODE, SimpleNamespace(at=lambda t: 1 / 0))
        state = SlFrameImu.State()
        out = _compute(1.0, state=state)
        self.assertTrue(state.warned)
        self.assertEqual(list(out.linAcc), [0.0, 0.0, 9.81])
        self.assertEqual(out.execOut, og.ExecutionAttributeState.ENABLED)
