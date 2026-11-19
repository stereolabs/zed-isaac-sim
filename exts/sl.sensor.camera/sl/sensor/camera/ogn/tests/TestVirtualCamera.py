"""Unit tests for SDK virtual cameras: calibration authoring (optics) and the camera registry.

The optics cases run on an in-memory stage with a hand-built calibration. The lens schemas are
registered by the app rather than by USD, so the intrinsics cases skip in a bare kit-kernel test
session. The registry cases need a bundled sl_zed with create_virtual_camera (5.6.0+).
"""
import ctypes
import math

import omni.kit.test
from pxr import Gf, Usd, UsdGeom

from sl.sensor.camera import sdk_virtual_camera
from sl.sensor.camera.optics import (apply_camera_optics, apply_virtual_camera_optics, author_right_eye_pose,
                                     right_eye_relative_matrix)
from sl.sensor.camera.sdk_virtual_camera import SimCalibration

_PINHOLE_SCHEMA = "OmniLensDistortionOpenCvPinholeAPI"
_SCHEMA_REGISTERED = Usd.SchemaRegistry().FindAppliedAPIPrimDefinition(_PINHOLE_SCHEMA) is not None
_PIXEL_MM = 3e-3
_OP_ATTR = "xformOp:transform:zedCalibration"


def _calibration(baseline=120.0, ty=0.0, tz=0.0, rotation=(0.0, 0.0, 0.0)):
    calib = SimCalibration()
    calib.version, calib.model, calib.lens_type, calib.width, calib.height = 1, 4, 0, 960, 600
    for eye, fx, cx in ((calib.left, 370.0, 480.0), (calib.right, 372.0, 470.0)):
        eye.fx, eye.fy, eye.cx, eye.cy = fx, fx * 1.001, cx, 305.0
    calib.baseline_mm, calib.ty_mm, calib.tz_mm = baseline, ty, tz
    calib.rx, calib.ry, calib.rz = rotation
    return calib


# The class must be named TestOgn: the OGN test loader registers only that name from each module.
class TestOgn(omni.kit.test.AsyncTestCase):

    def setUp(self):
        self._stage = Usd.Stage.CreateInMemory()
        UsdGeom.SetStageMetersPerUnit(self._stage, 1.0)
        rig = UsdGeom.Xform.Define(self._stage, "/Rig")
        rig.AddTranslateOp().Set(Gf.Vec3d(1.0, 2.0, 3.0))
        rig.AddRotateXYZOp().Set(Gf.Vec3f(0.0, 90.0, 0.0))
        self._left = UsdGeom.Camera.Define(self._stage, "/Rig/CameraLeft").GetPrim()
        self._right = UsdGeom.Camera.Define(self._stage, "/Rig/CameraRight").GetPrim()
        UsdGeom.Xformable(self._right).AddTranslateOp().Set(Gf.Vec3d(0.5, 0.0, 0.0))

    def _world(self, prim):
        return UsdGeom.XformCache().GetLocalToWorldTransform(prim)

    def test_struct_layout_matches_the_sdk(self):
        self.assertEqual(ctypes.sizeof(SimCalibration), 188)
        self.assertEqual(ctypes.sizeof(sdk_virtual_camera.SimVirtualCamera), 192)

    def test_fisheye_coefficients_come_from_slots_0_1_4_5(self):
        calib = _calibration()
        for i in range(12):
            calib.left.disto[i] = float(i)
        self.assertEqual(sdk_virtual_camera.fisheye_coefficients(calib.left), [0.0, 1.0, 4.0, 5.0])

    def test_right_eye_translation_goes_from_image_to_usd_frame(self):
        # OpenCV T = (-120, 1, 2) puts the right eye at (120, -1, -2) in the IMAGE frame (y down,
        # z forward), which is (120, 1, 2) in the USD camera frame (y up, z backward)
        m = right_eye_relative_matrix(_calibration(baseline=120.0, ty=1.0, tz=2.0), 1.0)
        self.assertTrue(Gf.IsClose(m.ExtractTranslation(), Gf.Vec3d(0.12, 0.001, 0.002), 1e-9))
        self.assertTrue(Gf.IsClose(m.ExtractRotationMatrix(), Gf.Matrix3d(1.0), 1e-9))

    def test_right_eye_translation_is_in_stage_units(self):
        m = right_eye_relative_matrix(_calibration(baseline=120.0), 0.01)   # centimeter stage
        self.assertAlmostEqual(m.ExtractTranslation()[0], 12.0, places=6)

    def test_right_eye_rotation_goes_from_image_to_usd_frame(self):
        # OpenCV R turns left-eye points by +0.01 rad about IMAGE y (down): the right eye itself is
        # turned by -0.01 rad about IMAGE y, i.e. +0.01 rad about USD y (up)
        m = right_eye_relative_matrix(_calibration(rotation=(0.0, 0.01, 0.0)), 1.0)
        rotation = m.ExtractRotation()
        self.assertTrue(Gf.IsClose(rotation.GetAxis(), Gf.Vec3d(0.0, 1.0, 0.0), 1e-6))
        self.assertAlmostEqual(rotation.GetAngle(), math.degrees(0.01), places=6)

    def test_right_eye_pose_inverts_the_opencv_map(self):
        # a left-eye point mapped by OpenCV's R, T lands where the right eye pose says it is
        calib = _calibration(baseline=120.0, ty=0.3, tz=-0.2, rotation=(0.002, -0.003, 0.001))
        pose_image = Gf.Matrix4d(1.0, 0, 0, 0, 0, -1.0, 0, 0, 0, 0, -1.0, 0, 0, 0, 0, 1.0)   # USD <-> IMAGE
        right_in_left = pose_image * right_eye_relative_matrix(calib, 1e-3) * pose_image   # IMAGE frame, mm
        r = Gf.Vec3d(calib.rx, calib.ry, calib.rz)
        opencv = Gf.Matrix4d().SetTransform(Gf.Rotation(r.GetNormalized(), math.degrees(r.GetLength())),
                                            Gf.Vec3d(-calib.baseline_mm, calib.ty_mm, calib.tz_mm))
        point_left = Gf.Vec3d(150.0, -40.0, 2000.0)
        point_right = opencv.Transform(point_left)
        self.assertTrue(Gf.IsClose(right_in_left.Transform(point_right), point_left, 1e-6))

    def test_right_eye_pose_is_relative_to_the_left_eye(self):
        calib = _calibration(baseline=120.0, ty=1.0, tz=2.0, rotation=(0.001, 0.002, 0.003))
        author_right_eye_pose(self._left, self._right, calib)

        expected = right_eye_relative_matrix(calib, 1.0) * self._world(self._left)
        self.assertTrue(Gf.IsClose(self._world(self._right), expected, 1e-9))

    def test_right_eye_pose_stays_out_of_the_scene_layer(self):
        author_right_eye_pose(self._left, self._right, _calibration())

        root_spec = self._stage.GetRootLayer().GetPrimAtPath(self._right.GetPath())
        self.assertNotIn(_OP_ATTR, root_spec.properties)
        session_spec = self._stage.GetSessionLayer().GetPrimAtPath(self._right.GetPath())
        self.assertIn(_OP_ATTR, session_spec.properties)

    def test_legacy_optics_give_the_asset_pose_back(self):
        authored = self._world(self._right)
        author_right_eye_pose(self._left, self._right, _calibration(baseline=110.0))
        self.assertFalse(Gf.IsClose(self._world(self._right), authored, 1e-9))

        apply_camera_optics(self._right, "ZED_X", "SVGA")
        self.assertTrue(Gf.IsClose(self._world(self._right), authored, 1e-9))

    def test_field_of_view_follows_each_eye(self):
        if not _SCHEMA_REGISTERED:
            self.skipTest(f"{_PINHOLE_SCHEMA} is not registered in this app")
        calib = _calibration()
        apply_virtual_camera_optics(self._left, self._right, calib, _PIXEL_MM)

        for prim, eye in ((self._left, calib.left), (self._right, calib.right)):
            focal = prim.GetAttribute("focalLength").Get()
            self.assertAlmostEqual(focal, eye.fx * _PIXEL_MM, places=5)
            self.assertAlmostEqual(960 * focal / prim.GetAttribute("horizontalAperture").Get(), eye.fx, places=2)
            self.assertAlmostEqual(600 * focal / prim.GetAttribute("verticalAperture").Get(), eye.fy, places=2)

    def test_pinhole_schema_carries_the_full_intrinsics(self):
        if not _SCHEMA_REGISTERED:
            self.skipTest(f"{_PINHOLE_SCHEMA} is not registered in this app")
        calib = _calibration()
        calib.right.disto[0] = -0.05
        apply_virtual_camera_optics(self._left, self._right, calib, _PIXEL_MM)

        self.assertIn(_PINHOLE_SCHEMA, self._right.GetAppliedSchemas())
        self.assertEqual(self._right.GetAttribute("omni:lensdistortion:model").Get(), "opencvPinhole")
        # cx, cy move from the pixel-center origin of the SDK to the pixel-corner one of the schema
        for name, offset in (("fx", 0.0), ("fy", 0.0), ("cx", 0.5), ("cy", 0.5)):
            self.assertAlmostEqual(self._right.GetAttribute(f"omni:lensdistortion:opencvPinhole:{name}").Get(),
                                   getattr(calib.right, name) + offset, places=3)
        self.assertAlmostEqual(self._right.GetAttribute("omni:lensdistortion:opencvPinhole:k1").Get(), -0.05, places=5)
        self.assertEqual(tuple(self._right.GetAttribute("omni:lensdistortion:opencvPinhole:imageSize").Get()),
                         (960, 600))

    def test_fisheye_calibration_renders_through_lookup_textures(self):
        if not _SCHEMA_REGISTERED:
            self.skipTest(f"{_PINHOLE_SCHEMA} is not registered in this app")
        calib = _calibration()
        calib.lens_type = sdk_virtual_camera.LENS_FISHEYE
        for eye in (calib.left, calib.right):
            eye.fx, eye.fy = 230.0, 231.0
            eye.disto[0], eye.disto[1], eye.disto[4], eye.disto[5] = 0.07, 0.0061, -0.0018, -0.00037
        apply_virtual_camera_optics(self._left, self._right, calib, _PIXEL_MM)

        for prim in (self._left, self._right):
            self.assertIn("OmniLensDistortionLutAPI", prim.GetAppliedSchemas())
            self.assertEqual(prim.GetAttribute("omni:lensdistortion:model").Get(), "lut")
            self.assertAlmostEqual(prim.GetAttribute("fthetaMaxFov").Get(), 243.96, delta=0.1)
        # each eye's optical center goes into its own textures
        left, right = (p.GetAttribute("omni:lensdistortion:lut:rayEnterDirectionTexture").Get().path
                       for p in (self._left, self._right))
        self.assertNotEqual(left, right)

    def test_lens_schema_raises_the_near_clip_for_this_run_only(self):
        if not _SCHEMA_REGISTERED:
            self.skipTest(f"{_PINHOLE_SCHEMA} is not registered in this app")
        clipping = UsdGeom.Camera(self._left).GetClippingRangeAttr()
        clipping.Set(Gf.Vec2f(0.012, 1000.0))
        calib = _calibration()
        apply_virtual_camera_optics(self._left, None, calib, _PIXEL_MM)

        # the ray to the farthest corner, (0, 0), is 1 / cos longer than its depth
        eye = calib.left
        corner_ray = math.sqrt(1.0 + (eye.cx / eye.fx) ** 2 + (eye.cy / eye.fy) ** 2)
        self.assertTrue(Gf.IsClose(clipping.Get(), Gf.Vec2f(0.012 * corner_ray, 1000.0), 1e-6))
        root_spec = self._stage.GetRootLayer().GetPrimAtPath(self._left.GetPath())
        self.assertTrue(Gf.IsClose(root_spec.properties["clippingRange"].default, Gf.Vec2f(0.012, 1000.0), 1e-6))

        apply_camera_optics(self._left, "ZED_X", "SVGA")   # no lens schema
        self.assertTrue(Gf.IsClose(clipping.Get(), Gf.Vec2f(0.012, 1000.0), 1e-6))

    def test_registry_gives_distinct_stable_cameras(self):
        if not sdk_virtual_camera.available():
            self.skipTest("the bundled sl_zed has no create_virtual_camera (needs 5.6.0+)")
        first = sdk_virtual_camera.acquire(4, 0, 960, 600)
        second = sdk_virtual_camera.acquire(4, 0, 960, 600)
        try:
            self.assertNotEqual(first.index, second.index)
            self.assertNotEqual(first.serial_number, second.serial_number)
            with self.assertRaises(sdk_virtual_camera.VirtualCameraError):
                sdk_virtual_camera.acquire(4, 0, 960, 600, camera_index=first.index)
        finally:
            sdk_virtual_camera.release(first)
            sdk_virtual_camera.release(second)

        again = sdk_virtual_camera.acquire(4, 0, 960, 600, camera_index=first.index)
        sdk_virtual_camera.release(again)
        self.assertEqual(again.serial_number, first.serial_number)
        self.assertAlmostEqual(again.calibration.left.fx, first.calibration.left.fx, places=6)

    def test_registry_rejects_an_unsupported_resolution(self):
        if not sdk_virtual_camera.available():
            self.skipTest("the bundled sl_zed has no create_virtual_camera (needs 5.6.0+)")
        with self.assertRaises(sdk_virtual_camera.VirtualCameraError):
            sdk_virtual_camera.acquire(4, 0, 1000, 600)
