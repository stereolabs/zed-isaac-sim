"""Lifecycle of the ZED Camera Helper node across Play, Stop and Play, and the graph migrations.

The kit-kernel test app has no renderer or Isaac Sim nodes, so the annotator the node builds is
replaced by a stand-in; what is checked is the node's own setup, port reservation and teardown.
"""
import omni.graph.core as og
import omni.kit.app
import omni.kit.test
import omni.timeline
import omni.usd
from pxr import Sdf

from sl.sensor.camera.annotators import used_ports
from sl.sensor.camera.nodes import _streamer
from sl.sensor.camera.nodes._migration import migrate_camera_model_to_base_lens, migrate_sim2real_to_master_switch

_PORT = 31000


class _FakeAnnotator:
    """Stands in for ZEDAnnotator: records what the node does with it."""

    instances = []

    def __init__(self, camera_prims, model, port, *args, **kwargs):
        self.port, self.model, self.destroyed = port, model, False
        _FakeAnnotator.instances.append(self)

    def warn_if_imu_blocks_stream(self):
        pass

    def warn_if_timing_drops_frames(self):
        pass

    def destroy(self):
        self.destroyed = True

    def __getattr__(self, name):
        if name.startswith("set_"):
            return lambda _value: None
        raise AttributeError(name)


class _NodeAtPath:
    """The one call the migrations make on their node argument."""

    def __init__(self, path):
        self._path = path

    def get_prim_path(self):
        return self._path


# The class must be named TestOgn: the OGN test loader registers only that name from each module.
class TestOgn(omni.kit.test.AsyncTestCase):

    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self._stage = omni.usd.get_context().get_stage()
        self._timeline = omni.timeline.get_timeline_interface()
        self._real_annotator = _streamer.ZEDAnnotator
        _streamer.ZEDAnnotator = _FakeAnnotator
        _FakeAnnotator.instances = []

    async def tearDown(self):
        self._timeline.stop()
        await self._updates(3)
        _streamer.ZEDAnnotator = self._real_annotator
        used_ports.difference_update({_PORT, _PORT + 2})

    async def _updates(self, count):
        for _ in range(count):
            await omni.kit.app.get_app().next_update_async()

    async def test_stop_releases_and_play_sets_up_again(self):
        self._stage.DefinePrim("/World/ZED_X", "Xform")
        keys = og.Controller.Keys
        og.Controller.edit(
            {"graph_path": "/World/Graph", "evaluator_name": "execution"},
            {keys.CREATE_NODES: [("OnTick", "omni.graph.action.OnPlaybackTick"),
                                 ("ZED", "sl.sensor.camera.ZED_Camera")],
             keys.SET_VALUES: [("ZED.inputs:streamingPort", _PORT)],
             keys.CONNECT: [("OnTick.outputs:tick", "ZED.inputs:execIn")]})
        self._stage.GetPrimAtPath("/World/Graph/ZED").GetRelationship("inputs:cameraPrim").SetTargets(
            [Sdf.Path("/World/ZED_X")])

        self._timeline.play()
        await self._updates(5)
        self.assertEqual(len(_FakeAnnotator.instances), 1, "Play should set the stream up once")
        first = _FakeAnnotator.instances[0]
        self.assertEqual(first.port, _PORT)
        self.assertIn(_PORT, used_ports)

        self._timeline.stop()
        await self._updates(3)
        self.assertTrue(first.destroyed, "Stop should destroy the annotator")
        self.assertNotIn(_PORT, used_ports, "Stop should free the port")
        self.assertEqual(len(_FakeAnnotator.instances), 1, "nothing should be set up while stopped")

        self._timeline.play()
        await self._updates(5)
        self.assertEqual(len(_FakeAnnotator.instances), 2, "Play after Stop should set the stream up again")
        self.assertFalse(_FakeAnnotator.instances[1].destroyed)
        self.assertIn(_PORT, used_ports)

    async def test_taken_port_moves_to_the_next_even_one(self):
        self._stage.DefinePrim("/World/ZED_X", "Xform")
        keys = og.Controller.Keys
        og.Controller.edit(
            {"graph_path": "/World/Graph", "evaluator_name": "execution"},
            {keys.CREATE_NODES: [("OnTick", "omni.graph.action.OnPlaybackTick"),
                                 ("ZED_A", "sl.sensor.camera.ZED_Camera"),
                                 ("ZED_B", "sl.sensor.camera.ZED_Camera")],
             keys.SET_VALUES: [("ZED_A.inputs:streamingPort", _PORT), ("ZED_B.inputs:streamingPort", _PORT)],
             keys.CONNECT: [("OnTick.outputs:tick", "ZED_A.inputs:execIn"),
                            ("OnTick.outputs:tick", "ZED_B.inputs:execIn")]})
        for name in ("ZED_A", "ZED_B"):
            self._stage.GetPrimAtPath(f"/World/Graph/{name}").GetRelationship("inputs:cameraPrim").SetTargets(
                [Sdf.Path("/World/ZED_X")])

        def authored_ports():
            return sorted(self._stage.GetPrimAtPath(f"/World/Graph/{name}").GetAttribute("inputs:streamingPort").Get()
                          for name in ("ZED_A", "ZED_B"))

        self._timeline.play()
        await self._updates(5)
        self.assertEqual(sorted(a.port for a in _FakeAnnotator.instances), [_PORT, _PORT + 2])
        self.assertIn(_PORT, used_ports)
        self.assertIn(_PORT + 2, used_ports)
        self.assertEqual(authored_ports(), [_PORT, _PORT + 2], "the moved camera's node should get its new port")

        self._timeline.stop()
        await self._updates(3)
        self.assertNotIn(_PORT, used_ports, "Stop should free both ports")
        self.assertNotIn(_PORT + 2, used_ports, "Stop should free both ports")

        self._timeline.play()
        await self._updates(5)
        self.assertEqual(sorted(a.port for a in _FakeAnnotator.instances[2:]), [_PORT, _PORT + 2])
        self.assertEqual(authored_ports(), [_PORT, _PORT + 2])

    async def test_v2_camera_model_splits_into_base_and_lens(self):
        prim = self._stage.DefinePrim("/World/OldNode")
        prim.CreateAttribute("inputs:cameraModel", Sdf.ValueTypeNames.Token).Set("ZED_X_4MM")
        migrate_camera_model_to_base_lens(_NodeAtPath("/World/OldNode"))
        self.assertEqual(prim.GetAttribute("inputs:cameraModel").Get(), "ZED_X")
        self.assertEqual(prim.GetAttribute("inputs:lensType").Get(), "Narrow")

    async def test_v4_sim2real_becomes_the_master_switch(self):
        prim = self._stage.DefinePrim("/World/OldNode")
        prim.CreateAttribute("inputs:applyZedSim2Real", Sdf.ValueTypeNames.Bool).Set(False)
        prim.CreateAttribute("inputs:zedSim2RealSceneLux", Sdf.ValueTypeNames.Float).Set(300.0)
        migrate_sim2real_to_master_switch(_NodeAtPath("/World/OldNode"))
        self.assertTrue(prim.GetAttribute("inputs:applyZedSim2Real").Get())
        self.assertFalse(prim.HasAttribute("inputs:zedSim2RealSceneLux"))
