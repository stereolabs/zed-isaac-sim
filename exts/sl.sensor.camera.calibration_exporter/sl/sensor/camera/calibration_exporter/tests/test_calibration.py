"""The exported [STEREO] section must be what the ZED SDK reads: OpenCV's stereo extrinsics,
T = (-Baseline, TY, TZ) in millimeters and R = (RX, CV, RZ), mapping a point from the left eye
frame into the right one."""
import configparser
import math
import os
import tempfile

import omni.kit.test
import omni.usd
from pxr import Gf, UsdGeom

from .. import calibration

# right eye pose in the left eye's image frame (x right, y down, z forward), meters: 120 mm to
# the side, 10 mm higher, 4 mm forward, toed in by 1.5 degrees
_TOED_IN = (Gf.Rotation(Gf.Vec3d(0.2, 1.0, 0.1).GetNormalized(), 1.5), Gf.Vec3d(0.12, -0.010, 0.004))
_PARALLEL = (Gf.Rotation().SetIdentity(), Gf.Vec3d(0.05, 0.0, 0.0))

# rows are the image frame axes in the prim's frame
_CAMERA_FRAME = Gf.Matrix4d(1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1)
_GENERIC_FRAME = Gf.Matrix4d(0, -1, 0, 0, 0, 0, -1, 0, 1, 0, 0, 0, 0, 0, 0, 1)
_KEYS = ("baseline", "ty", "tz", "rx_fhd", "cv_fhd", "rz_fhd", "rx_4k", "cv_4k", "rz_4k")


def _expected(rig):
    rotation, position = rig
    left_to_right = rotation.GetInverse()
    t = -left_to_right.TransformDir(position) * 1000.0
    r = left_to_right.GetAxis() * math.radians(left_to_right.GetAngle())
    return dict(zip(_KEYS, (-t[0], t[1], t[2], r[0], r[1], r[2], r[0], r[1], r[2])))


class TestCalibration(omni.kit.test.AsyncTestCase):

    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self._stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageMetersPerUnit(self._stage, 1.0)
        self._dir = tempfile.TemporaryDirectory()
        self._path_fn = calibration.get_calibration_file_path
        calibration.get_calibration_file_path = lambda: self._dir.name + "/"

    async def tearDown(self):
        calibration.get_calibration_file_path = self._path_fn
        self._dir.cleanup()

    def _export(self, rig, define, frame):
        rotation, position = rig
        left, right = define(self._stage, "/Left"), define(self._stage, "/Right")
        left_world = Gf.Matrix4d().SetTransform(Gf.Rotation(Gf.Vec3d(0, 0, 1), 30), Gf.Vec3d(1, 2, 3))
        left.AddTransformOp().Set(left_world)
        pose = Gf.Matrix4d().SetTransform(rotation, position)
        right.AddTransformOp().Set(frame.GetInverse() * pose * frame * left_world)

        calibration.write_stereo_calibration_file("/Left", "/Right", "110000042", "ZED_XONE_GS")
        cfg = configparser.ConfigParser()
        cfg.read(self._dir.name + "/SN110000042.conf")
        return {key: float(cfg["STEREO"][key]) for key in _KEYS}

    def _assert_exports(self, rig, define, frame):
        exported = self._export(rig, define, frame)
        for key, value in _expected(rig).items():
            self.assertAlmostEqual(exported[key], value, places=5, msg=key)

    async def test_camera_prims_export_the_sdk_extrinsics(self):
        self._assert_exports(_TOED_IN, UsdGeom.Camera.Define, _CAMERA_FRAME)

    async def test_generic_prims_export_the_sdk_extrinsics(self):
        self._assert_exports(_TOED_IN, UsdGeom.Xform.Define, _GENERIC_FRAME)

    async def test_sim_section_names_the_model_and_lens(self):
        UsdGeom.Camera.Define(self._stage, "/Left")
        UsdGeom.Camera.Define(self._stage, "/Right")
        for model, code, lens in (("ZED_XONE_GS", "30", "0"), ("ZED_XONE_GS_4MM", "30", "1"),
                                  ("ZED_XONE_UHD", "31", "0"), ("ZED_XONE_S_FISHEYE", "30", "2")):
            calibration.write_stereo_calibration_file("/Left", "/Right", "110000042", model)
            cfg = configparser.ConfigParser()
            cfg.read(self._dir.name + "/SN110000042.conf")
            self.assertEqual((cfg["SIM"]["camera_model"], cfg["SIM"]["lens_type"]), (code, lens), model)
            self.assertEqual("LEFT_DISTO" in cfg, model == "ZED_XONE_S_FISHEYE", model)

    async def test_serial_outside_the_virtual_range_writes_nothing(self):
        for serial in ("", "40976320", "120000000", "SNC:/tmp"):
            calibration.write_stereo_calibration_file("/Left", "/Right", serial, "ZED_XONE_GS")
        self.assertEqual(os.listdir(self._dir.name), [])

    async def test_parallel_rig_exports_only_a_baseline(self):
        exported = self._export(_PARALLEL, UsdGeom.Camera.Define, _CAMERA_FRAME)
        self.assertAlmostEqual(exported["baseline"], 50.0, places=5)
        for key in _KEYS[1:]:
            self.assertAlmostEqual(exported[key], 0.0, places=6, msg=key)
