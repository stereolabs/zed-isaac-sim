"""Per-frame IMU feeder (imu_stream.FrameImu): the history of every physics step it keeps for the
ZED_FrameImu node, units, the pose correction and the lever arm (the history and the node: TestFrameImuHistory).

The physics step callback is driven by hand with stand-ins for the IMU sensor and PhysX, so the test needs
neither a simulation nor a streamer.
"""
import math
from types import SimpleNamespace

import omni.kit.test
from pxr import Gf, Usd, UsdGeom, UsdPhysics

from sl.sensor.camera import frame_imu
from sl.sensor.camera.imu_stream import (FrameImu, _lever_arm, _lever_arm_acceleration, _rigid_body_and_offset,
                                         _scene_gravity)

_NODE = "/Render/PostProcess/SDGPipeline/zed_30000_frame_imu"


class _History(frame_imu.ImuHistory):
    """Records (t, qw, qx, qy, qz, ax, ay, az) of each push."""

    def __init__(self):
        super().__init__()
        self.pushed = []

    def push(self, t, orientation, linear_acceleration):
        self.pushed.append((t, orientation.GetReal(), *orientation.GetImaginary(), *linear_acceleration))
        super().push(t, orientation, linear_acceleration)


def _reading(gyro=(0.0, 0.0, 0.0), acc=(0.0, 0.0, 0.0), orientation=(1.0, 0.0, 0.0, 0.0)):
    """An IMU reading without gravity, as the feeder asks for it."""
    w, x, y, z = orientation
    return SimpleNamespace(is_valid=True,
                           angular_velocity_x=gyro[0], angular_velocity_y=gyro[1], angular_velocity_z=gyro[2],
                           linear_acceleration_x=acc[0], linear_acceleration_y=acc[1], linear_acceleration_z=acc[2],
                           orientation_w=w, orientation_x=x, orientation_y=y, orientation_z=z)


def _feeder(reading, body_rotation_xyzw=(0, 0, 0, 1), meters_per_unit=1.0, gravity=(0.0, 0.0, -9.81),
            lever_arm=(0.0, 0.0, 0.0)):
    """A FrameImu past its setup, reading `reading`, with the PhysX pose `body_rotation_xyzw`."""
    imu = FrameImu.__new__(FrameImu)
    imu._imu_path, imu._node_path, imu._port = "/World/ZED/Imu_Sensor", _NODE, 30000
    imu.history, imu._stopped = _History(), False
    imu._meters_per_unit, imu._gravity = meters_per_unit, Gf.Vec3d(*gravity)
    imu._lever_arm, imu._last_gyro, imu._last_gyro_t = Gf.Vec3d(*lever_arm), None, None
    imu._sensors = SimpleNamespace(get_sensor_reading=lambda path, gravity: reading, create_sensor=lambda path: True)
    imu.now = 0.0
    imu._sim_time = lambda: imu.now
    imu._body_path, imu._imu_in_body = "/World/ZED", Gf.Quatd(1.0)
    imu._physx = SimpleNamespace(
        get_rigidbody_transformation=lambda path: {"ret_val": True, "rotation": body_rotation_xyzw})
    return imu


def _run(imu, physics_hz, seconds=1.0):
    for k in range(1, int(round(physics_hz * seconds)) + 1):
        imu.now = k / physics_hz
        imu._on_step(1.0 / physics_hz, None)
    return imu.history.pushed


class TestOgn(omni.kit.test.AsyncTestCase):

    async def tearDown(self):
        frame_imu._histories.pop(_NODE, None)

    async def test_keeps_every_step_from_the_first(self):
        pushed = _run(_feeder(_reading()), physics_hz=200)
        self.assertEqual(len(pushed), 200)
        self.assertEqual((pushed[0][0], pushed[-1][0]), (0.005, 1.0))

    async def test_every_step_with_the_physx_pose(self):
        s = math.sqrt(0.5)
        imu = _feeder(_reading(orientation=(s, 0.0, 0.0, s)))
        pushed = _run(imu, physics_hz=600)
        self.assertEqual(len(pushed), 600)
        t, qw, qx, qy, qz, ax, ay, az = pushed[-1]
        self.assertEqual(t, 1.0)
        self.assertEqual((qw, qx, qy, qz), (1.0, 0.0, 0.0, 0.0))
        self.assertAlmostEqual(az, 9.81)

    async def test_stops_without_a_physx_pose(self):
        imu = _feeder(_reading())
        frame_imu.register(_NODE, imu.history)
        imu._physx = SimpleNamespace(get_rigidbody_transformation=lambda path: {"ret_val": False})
        self.assertEqual(_run(imu, physics_hz=200, seconds=0.01), [])
        self.assertIsNone(frame_imu.lookup(_NODE))

    async def test_rotates_the_accel_with_the_physx_pose(self):
        # 1 m/s^2 along world x, brought into the sensor frame with a pose 90 deg off about z, reads
        # (0, -1, 0). With the body's actual pose (identity) it reads (1, 0, 0).
        s = math.sqrt(0.5)
        imu = _feeder(_reading(acc=(0.0, -1.0, 0.0), orientation=(s, 0.0, 0.0, s)), gravity=(0.0, 0.0, 0.0))
        (*_, ax, ay, az), = _run(imu, physics_hz=200, seconds=0.005)
        for got, want in zip((ax, ay, az), (1.0, 0.0, 0.0)):
            self.assertAlmostEqual(got, want, places=6)

    async def test_accel_in_m_per_s2_on_a_cm_stage(self):
        imu = _feeder(_reading(acc=(100.0, 0.0, 0.0)), meters_per_unit=0.01)  # 1 m/s^2 forward, in cm/s^2
        (*_, ax, ay, az), = _run(imu, physics_hz=200, seconds=0.005)
        for got, want in zip((ax, ay, az), (1.0, 0.0, 9.81)):  # sensor frame: gravity's reaction up = +z
            self.assertAlmostEqual(got, want, places=4)

    async def test_scene_gravity_in_m_per_s2(self):
        stage = Usd.Stage.CreateInMemory()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        for got, want in zip(_scene_gravity(stage), (0.0, 0.0, -9.80665)):  # no scene: Earth's, down
            self.assertAlmostEqual(got, want, places=6)
        UsdGeom.SetStageMetersPerUnit(stage, 0.01)
        scene = UsdPhysics.Scene.Define(stage, "/PhysicsScene")
        scene.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -2))
        scene.CreateGravityMagnitudeAttr(981.0)  # cm/s^2
        for got, want in zip(_scene_gravity(stage), (0.0, 0.0, -9.81)):
            self.assertAlmostEqual(got, want, places=4)
        y_up = Usd.Stage.CreateInMemory()
        UsdGeom.SetStageUpAxis(y_up, UsdGeom.Tokens.y)
        UsdPhysics.Scene.Define(y_up, "/PhysicsScene")  # direction and magnitude unset
        for got, want in zip(_scene_gravity(y_up), (0.0, -9.80665, 0.0)):
            self.assertAlmostEqual(got, want, places=6)

    async def test_imu_mount_offset_in_its_rigid_body(self):
        stage = Usd.Stage.CreateInMemory()
        body = UsdGeom.Xform.Define(stage, "/World/Body")
        body.AddRotateZOp().Set(90.0)  # the body's own pose must not leak into the offset
        UsdPhysics.RigidBodyAPI.Apply(body.GetPrim())
        mount = UsdGeom.Xform.Define(stage, "/World/Body/Mount")
        mount.AddRotateYOp().Set(30.0)
        UsdPhysics.RigidBodyAPI.Apply(mount.GetPrim()).CreateRigidBodyEnabledAttr(False)  # skipped, as Isaac does
        UsdGeom.Xform.Define(stage, "/World/Body/Mount/Imu")
        path, offset = _rigid_body_and_offset(stage, "/World/Body/Mount/Imu")
        self.assertEqual(path, "/World/Body")
        half = math.radians(15.0)
        for got, want in zip((offset.GetReal(), *offset.GetImaginary()), (math.cos(half), 0.0, math.sin(half), 0.0)):
            self.assertAlmostEqual(got, want, places=6)

    async def test_imu_lever_arm_from_the_center_of_mass(self):
        stage = Usd.Stage.CreateInMemory()
        body = UsdGeom.Xform.Define(stage, "/World/Body")
        body.AddTranslateOp().Set(Gf.Vec3d(1.0, 2.0, 3.0))
        body.AddRotateZOp().Set(90.0)  # the body's own pose must not leak into the lever arm
        imu = UsdGeom.Xform.Define(stage, "/World/Body/Imu")
        imu.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.06, 0.0))
        imu.AddRotateYOp().Set(30.0)
        got = _lever_arm(stage, "/World/Body/Imu", "/World/Body", (0.01, 0.0, 0.0))
        want = Gf.Rotation(Gf.Vec3d(0, 1, 0), 30.0).GetInverse().TransformDir(Gf.Vec3d(-0.01, 0.06, 0.0))
        for g, w in zip(got, want):
            self.assertAlmostEqual(g, w, places=9)

    async def test_lever_arm_acceleration(self):
        # Turning at 2 rad/s about z and speeding up at 3 rad/s^2, 6 cm off the axis along y: centripetal
        # 2^2 * 0.06 toward the axis (-y), tangential 3 * 0.06 along -x.
        got = _lever_arm_acceleration(Gf.Vec3d(0, 0, 2.0), Gf.Vec3d(0, 0, 3.0), Gf.Vec3d(0, 0.06, 0))
        for g, w in zip(got, (-0.18, -0.24, 0.0)):
            self.assertAlmostEqual(g, w, places=12)

    async def test_accel_at_the_imu_not_the_center_of_mass(self):
        imu = _feeder(_reading(gyro=(0.0, 0.0, 2.0)), gravity=(0.0, 0.0, 0.0), lever_arm=(0.0, 0.06, 0.0))
        *_, ax, ay, az = _run(imu, physics_hz=200, seconds=0.01)[-1]
        for got, want in zip((ax, ay, az), (0.0, -0.24, 0.0)):  # centripetal, toward the axis
            self.assertAlmostEqual(got, want, places=6)
