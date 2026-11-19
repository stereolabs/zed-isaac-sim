"""A capture camera's pose at a frame's time (frame_pose), from its rigid body's pose at each physics step and the
camera's place on the body. No simulation: the history is fed by hand."""
import omni.kit.test
from pxr import Gf, Usd, UsdGeom

from sl.sensor.camera import frame_imu, frame_pose


def _flat(m):
    return [m[i][j] for i in range(4) for j in range(4)]


def _poses(camera_in_body):
    """A CameraPoses past its setup, fed by hand."""
    poses = frame_pose.CameraPoses.__new__(frame_pose.CameraPoses)
    poses.available, poses._missed_warned = True, False
    poses._history, poses._camera_in_body = frame_imu.ImuHistory(), camera_in_body
    poses._camera_path, poses._body_path = "/World/ZED/CameraLeft", "/World/ZED"
    return poses


class TestOgn(omni.kit.test.AsyncTestCase):

    async def test_view_transform_matches_the_stage(self):
        stage = Usd.Stage.CreateInMemory()
        body = UsdGeom.Xform.Define(stage, "/World/ZED")
        translate, rotate = body.AddTranslateOp(), body.AddRotateXYZOp()
        camera = UsdGeom.Camera.Define(stage, "/World/ZED/CameraLeft")
        camera.AddTranslateOp().Set(Gf.Vec3d(0.06, 0.0, 0.02))
        camera.AddRotateYOp().Set(-90.0)

        # The offset is read with the body anywhere: its pose must not leak into it.
        translate.Set(Gf.Vec3d(5.0, -1.0, 0.3))
        rotate.Set(Gf.Vec3f(0.0, 0.0, 40.0))
        cache = UsdGeom.XformCache()
        camera_in_body = (cache.GetLocalToWorldTransform(camera.GetPrim())
                          * cache.GetLocalToWorldTransform(body.GetPrim()).RemoveScaleShear().GetInverse())

        translate.Set(Gf.Vec3d(1.0, 2.0, 0.5))
        rotate.Set(Gf.Vec3f(10.0, -20.0, 75.0))
        body_to_world = UsdGeom.XformCache().GetLocalToWorldTransform(body.GetPrim())
        expected = UsdGeom.XformCache().GetLocalToWorldTransform(camera.GetPrim()).GetInverse()
        got = frame_pose.view_transform(camera_in_body, body_to_world.ExtractRotationQuat(),
                                        body_to_world.ExtractTranslation())
        for g, e in zip(got, _flat(expected)):
            self.assertAlmostEqual(g, e, places=9)

    async def test_view_transform_layout(self):
        # Row vectors: a point maps as p * M, the translation sits in the last row.
        got = frame_pose.view_transform(Gf.Matrix4d(1.0), Gf.Quatd(1.0), Gf.Vec3d(1.0, 2.0, 3.0))
        self.assertEqual(got[12:16], [-1.0, -2.0, -3.0, 1.0])
        self.assertEqual([got[3], got[7], got[11]], [0.0, 0.0, 0.0])

    async def test_pose_at_the_frame_time(self):
        poses = _poses(Gf.Matrix4d(1.0))
        poses._history.push(1.0, Gf.Quatd(1.0), Gf.Vec3d(0.0, 0.0, 0.0))
        poses._history.push(1.1, Gf.Quatd(1.0), Gf.Vec3d(1.0, 0.0, 0.0))
        self.assertAlmostEqual(poses.view_transform(1.05)[12], -0.5, places=12)  # between two steps
        self.assertEqual(poses.view_transform(1.1)[12], -1.0)
        self.assertIsNone(poses.view_transform(1.2))  # past the last step: CameraParams instead
        self.assertTrue(poses._missed_warned)

    async def test_no_body_gives_no_pose(self):
        poses = _poses(Gf.Matrix4d(1.0))
        poses.available = False
        self.assertIsNone(poses.view_transform(1.0))
