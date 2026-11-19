"""Which reads of the SDK-free capture (ZEDDepthCamera.save_frame) reach the frame writer.

The render product and the annotators are stand-ins, so the test needs no renderer.
"""
from types import SimpleNamespace

import numpy as np
import omni.kit.test

from sl.sensor.camera import zed_depth
from sl.sensor.camera.frames import FrameWriter
from sl.sensor.camera.zed_depth import ZEDDepthCamera


class _Writer(FrameWriter):
    """Takes every frame, or with ``needs_pose`` skips a stamp it already took, as a pose writer does."""

    def __init__(self, needs_pose=False, refuse=0):
        self.needs_pose, self.refuse = needs_pose, refuse  # refuse: frames to skip next (e.g. data not ready)
        self.calls, self.taken, self._last = 0, [], None

    def write(self, frame):
        self.calls += 1
        if self.refuse:
            self.refuse -= 1
            return False
        if self.needs_pose and self._last is not None and frame.sim_time <= self._last:
            return False
        self._last = frame.sim_time
        self.taken.append((frame.index, frame.sim_time))
        return True


class _Render:
    """The frame number and simulation time the render product and its annotators hold; counts image reads."""

    def __init__(self, frame, stamp):
        self.frame, self.stamp, self.reads = frame, stamp, 0

    def image(self):
        self.reads += 1
        return np.zeros((2, 2, 4), np.uint8)


def _capture(writer, render):
    """A mono, linear, depth-free capture past its setup, reading ``render``."""
    cam = ZEDDepthCamera.__new__(ZEDDepthCamera)
    cam._valid, cam._output_dir, cam._encoding, cam._save_depth = True, "unused", "linear", False
    cam._frame_writer, cam._frame_count, cam._last_render_frame, cam._last_stamp = writer, 0, 0, None
    cam._frame_node_paths, cam._graph_frames, cam._graph_frame = [], 0, None
    cam._rp = SimpleNamespace(hydra_texture=SimpleNamespace(get_frame_info=lambda: {"frame_number": render.frame}))
    cam._rgb_annot = SimpleNamespace(get_data=render.image)
    cam._rgb_right_annot, cam._camera_params_annot, cam._camera_poses = None, None, None
    cam._sim_time_annot = SimpleNamespace(get_data=lambda: {"simulationTime": render.stamp})
    return cam


_NODE = "/Render/PostProcess/SDGPipeline/RenderProduct_capture_frame"


class TestOgn(omni.kit.test.AsyncTestCase):

    async def test_frame_number_ahead_of_its_data(self):
        writer, render = _Writer(needs_pose=True), _Render(frame=1, stamp=0.5)
        cam = _capture(writer, render)
        self.assertTrue(cam.save_frame())

        # Frame 2 has rendered but the annotators still hold frame 1: its images are not read.
        render.frame = 2
        self.assertFalse(cam.save_frame())
        self.assertEqual((render.reads, writer.calls), (1, 1))
        # On the next update frame 2's data has arrived: it is taken under the next index.
        render.stamp = 1.0
        self.assertTrue(cam.save_frame())
        self.assertEqual(writer.taken, [(0, 0.5), (1, 1.0)])
        # A frame the writer took is not read again.
        self.assertFalse(cam.save_frame())
        self.assertEqual((render.reads, writer.calls), (2, 2))

    async def test_skipped_frame_read_again(self):
        writer, render = _Writer(needs_pose=True, refuse=1), _Render(frame=1, stamp=0.5)
        cam = _capture(writer, render)
        self.assertFalse(cam.save_frame())
        self.assertTrue(cam.save_frame())
        self.assertFalse(cam.save_frame())
        self.assertEqual((writer.calls, writer.taken), (2, [(0, 0.5)]))

    async def test_skipped_frame_taken_under_the_next_frame_number(self):
        writer, render = _Writer(needs_pose=True), _Render(frame=1, stamp=0.5)
        cam = _capture(writer, render)
        self.assertTrue(cam.save_frame())
        render.frame, render.stamp, writer.refuse = 2, 1.0, 1
        self.assertFalse(cam.save_frame())
        # Frame 3 has rendered while the annotators still hold frame 2, which is taken now.
        render.frame = 3
        self.assertTrue(cam.save_frame())
        # Frame 3's data arrives with no new frame number: it is still taken.
        render.stamp = 1.5
        self.assertTrue(cam.save_frame())
        self.assertEqual(writer.taken, [(0, 0.5), (1, 1.0), (2, 1.5)])

    async def test_ticks_of_one_update_taken_each(self):
        # A camera rendering faster than the app updates: each tick shows the physics state at its own time.
        writer, render = _Writer(needs_pose=True), _Render(frame=1, stamp=0.51)
        cam = _capture(writer, render)
        self.assertTrue(cam.save_frame())
        render.frame, render.stamp = 2, 0.53
        self.assertTrue(cam.save_frame())
        self.assertEqual(writer.taken, [(0, 0.51), (1, 0.53)])

    async def test_frame_taken_once(self):
        writer, render = _Writer(), _Render(frame=1, stamp=0.5)
        cam = _capture(writer, render)
        for frame in (1, 1, 2, 2, 2, 3):
            render.frame = frame
            cam.save_frame()
        self.assertEqual((writer.calls, render.reads), (3, 3))


    # Frames the post-render graph hands over (ZED_CaptureFrame -> zed_depth.save_rendered_frame).

    def _hooked(self, writer, render):
        cam = _capture(writer, render)
        cam._frame_node_paths = [_NODE]
        zed_depth._frame_nodes[_NODE] = cam
        self.addCleanup(zed_depth._frame_nodes.pop, _NODE, None)
        return cam

    async def test_two_graph_frames_of_one_update_both_taken(self):
        # Both frames finish in one app update: the render product reports the same frame number for each.
        writer, render = _Writer(), _Render(frame=7, stamp=0.5)
        cam = self._hooked(writer, render)
        numbers = []
        write = writer.write
        writer.write = lambda frame: numbers.append(cam._frame_number(cam._rp)) or write(frame)
        self.assertTrue(zed_depth.save_rendered_frame(_NODE, (15, 30)))
        self.assertTrue(zed_depth.save_rendered_frame(_NODE, (16, 30)))
        self.assertEqual([i for i, _ in writer.taken], [0, 1])
        # Each frame has its own number (noise, light flicker, white balance) while it is saved.
        self.assertEqual(numbers, [1, 2])
        self.assertEqual(cam._frame_number(cam._rp), 7)

    async def test_graph_pose_frames_of_one_update_both_taken(self):
        writer, render = _Writer(needs_pose=True), _Render(frame=7, stamp=0.5)
        self._hooked(writer, render)
        self.assertTrue(zed_depth.save_rendered_frame(_NODE, (15, 30)))
        render.stamp = 0.55
        self.assertTrue(zed_depth.save_rendered_frame(_NODE, (16, 30)))
        self.assertEqual(writer.taken, [(0, 0.5), (1, 0.55)])

    async def test_graph_reference_time_taken_once(self):
        writer, render = _Writer(), _Render(frame=7, stamp=0.5)
        self._hooked(writer, render)
        self.assertTrue(zed_depth.save_rendered_frame(_NODE, (15, 30)))
        self.assertFalse(zed_depth.save_rendered_frame(_NODE, (15, 30)))
        # Without a reference time every frame handed over goes to the writer.
        self.assertTrue(zed_depth.save_rendered_frame(_NODE, (0, 0)))
        self.assertTrue(zed_depth.save_rendered_frame(_NODE, (0, 0)))
        self.assertEqual((writer.calls, render.reads), (3, 3))

    async def test_save_frame_reads_nothing_while_the_graph_saves(self):
        writer, render = _Writer(), _Render(frame=7, stamp=0.5)
        cam = self._hooked(writer, render)
        self.assertFalse(cam.save_frame())
        self.assertEqual((writer.calls, render.reads), (0, 0))

    async def test_unknown_graph_node_saves_nothing(self):
        self.assertFalse(zed_depth.save_rendered_frame("/Render/PostProcess/SDGPipeline/gone", (15, 30)))
