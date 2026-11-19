"""The IMU of each streamed frame, read at the frame's own time.

IsaacReadIMU gives the streaming node the IMU of the latest physics step, while the frame it streams was
rendered a varying number of steps before (2 to 10 at 240 Hz physics), and it rotates that reading with a
pose from Fabric that lags by up to a render frame. This reads the camera's IMU after every physics step,
rotated with the rigid body's PhysX pose of that step, into the history the camera's ZED_FrameImu node
looks each frame's time up in (frame_imu).
"""
from __future__ import annotations

import math

import carb
import carb.settings
from pxr import Gf, UsdGeom, UsdPhysics

from . import frame_imu

# Post-step callbacks run by ascending order. The simulation time (order 0) and the IMU sensor
# (order 1) are updated by then, so the reading belongs to the step that just ran.
_STEP_ORDER = 10


def _rigid_body_and_offset(stage, imu_path: str):
    """The rigid body the IMU reads (its first ancestor with an enabled rigid body, as Isaac's IMU
    picks it) and the IMU's orientation in that body's frame. (None, None) without one."""
    imu = stage.GetPrimAtPath(imu_path)
    body = imu.GetParent() if imu else None
    while body and not body.IsPseudoRoot():
        if body.HasAPI(UsdPhysics.RigidBodyAPI) and UsdPhysics.RigidBodyAPI(body).GetRigidBodyEnabledAttr().Get() is not False:
            cache = UsdGeom.XformCache()
            imu_in_body = cache.GetLocalToWorldTransform(imu) * cache.GetLocalToWorldTransform(body).GetInverse()
            return body.GetPath().pathString, imu_in_body.RemoveScaleShear().ExtractRotationQuat()
        body = body.GetParent()
    return None, None


def _lever_arm(stage, imu_path: str, body_path: str, center_of_mass) -> Gf.Vec3d:
    """The IMU's position relative to its rigid body's center of mass (in the body's frame), in the IMU's
    frame, in stage units."""
    cache = UsdGeom.XformCache()
    body_to_world = cache.GetLocalToWorldTransform(stage.GetPrimAtPath(body_path)).RemoveScaleShear()
    world_to_imu = cache.GetLocalToWorldTransform(stage.GetPrimAtPath(imu_path)).RemoveScaleShear().GetInverse()
    return -world_to_imu.Transform(body_to_world.Transform(Gf.Vec3d(*center_of_mass)))


def _lever_arm_acceleration(gyro: Gf.Vec3d, angular_acceleration: Gf.Vec3d, lever_arm: Gf.Vec3d) -> Gf.Vec3d:
    """What a point at ``lever_arm`` from a rigid body's center of mass accelerates by on top of the center
    of mass, the body turning at ``gyro``: tangential and centripetal. Units follow the inputs."""
    return Gf.Cross(angular_acceleration, lever_arm) + Gf.Cross(gyro, Gf.Cross(gyro, lever_arm))


def _center_of_mass(stage_id: int, body_path: str):
    """The rigid body's center of mass in its frame, as PhysX has it (authored, or from its colliders), in
    stage units. None when PhysX cannot say."""
    import omni.physx
    from omni.physx.bindings._physx import PhysxPropertyQueryMode, PhysxPropertyQueryResult
    from pxr import PhysicsSchemaTools

    found = []
    omni.physx.get_physx_property_query_interface().query_prim(
        stage_id, PhysicsSchemaTools.sdfPathToInt(body_path),
        query_mode=PhysxPropertyQueryMode.QUERY_RIGID_BODY_WITH_COLLIDERS, timeout_ms=2000,
        rigid_body_fn=found.append)
    if found and found[0].result == PhysxPropertyQueryResult.VALID:
        return Gf.Vec3d(*found[0].center_of_mass)
    return None


def _scene_gravity(stage) -> Gf.Vec3d:
    """The physics scene's gravity in m/s^2, world frame, as the USD Physics schema defines it: an unset
    direction points down the stage's up axis, an unset magnitude is Earth's, a set one is in stage units."""
    up = {UsdGeom.Tokens.x: Gf.Vec3d(1, 0, 0), UsdGeom.Tokens.y: Gf.Vec3d(0, 1, 0)}.get(
        UsdGeom.GetStageUpAxis(stage), Gf.Vec3d(0, 0, 1))
    direction, magnitude = -up, 9.80665
    scene = next((UsdPhysics.Scene(p) for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)), None)
    if scene:
        authored = Gf.Vec3d(scene.GetGravityDirectionAttr().Get() or Gf.Vec3f(0.0))
        if authored.GetLength() > 1e-10:
            direction = authored.GetNormalized()
        authored = scene.GetGravityMagnitudeAttr().Get()
        if authored is not None and math.isfinite(authored) and authored != 0:
            magnitude = abs(authored) * UsdGeom.GetStageMetersPerUnit(stage)
    return direction * magnitude


class FrameImu:
    """Keeps one camera's IMU of every physics step for its ZED_FrameImu node.

    Args:
        imu_path: the camera's IMU prim
        node_path: the camera's ZED_FrameImu node
        port: the camera's streaming port, for the logs
    """

    def __init__(self, imu_path: str, node_path: str, port: int):
        self._imu_path = imu_path
        self._node_path = node_path
        self._port = port
        self.history = frame_imu.ImuHistory()
        self._stopped = False
        self._sub = None
        try:
            import omni.physics.core
            import omni.physx
            import omni.usd
            from isaacsim.core.simulation_manager import SimulationManager
            from isaacsim.sensors.experimental.physics import get_imu_sensor_interface
        except ImportError as exc:
            carb.log_info(f"[ZED][port {port}] Frames carry IsaacReadIMU's latest reading ({exc}).")
            return
        self._sensors = get_imu_sensor_interface()
        if self._sensors is None:
            carb.log_info(f"[ZED][port {port}] No Isaac Sim IMU sensor interface: frames carry IsaacReadIMU's "
                          "latest reading.")
            return
        if carb.settings.get_settings().get_as_bool("/physics/suppressReadback"):
            # The PhysX pose of each step is not read back either.
            carb.log_info(f"[ZED][port {port}] GPU physics without readback: frames carry IsaacReadIMU's latest "
                          "reading.")
            return
        stage = omni.usd.get_context().get_stage()
        self._body_path, self._imu_in_body = _rigid_body_and_offset(stage, imu_path)
        if not self._body_path:
            return
        self._sim_time = SimulationManager.get_simulation_time
        self._physx = omni.physx.get_physx_interface()
        self._meters_per_unit = UsdGeom.GetStageMetersPerUnit(stage)  # Isaac's IMU accelerations are in stage units
        self._gravity = _scene_gravity(stage)
        # Isaac's IMU reads its rigid body's center of mass. The IMU's lever arm to it is found on the first
        # physics step, once PhysX has the body's mass properties.
        self._lever_arm = None
        self._last_gyro, self._last_gyro_t = None, None
        self._sub = omni.physics.core.get_physics_simulation_interface().subscribe_physics_on_step_events(
            pre_step=False, order=_STEP_ORDER, on_update=self._on_step)
        frame_imu.register(node_path, self.history)

    def destroy(self) -> None:
        self._sub = None
        frame_imu.unregister(self._node_path, self.history)

    def _find_lever_arm(self) -> Gf.Vec3d:
        """The IMU's position relative to its rigid body's center of mass, in the IMU's frame, in meters."""
        import omni.usd

        context = omni.usd.get_context()
        center_of_mass = _center_of_mass(context.get_stage_id(), self._body_path)
        if center_of_mass is None:
            carb.log_warn(f"[ZED][port {self._port}] PhysX gives no center of mass for {self._body_path}: the IMU "
                          "takes its origin's, so its accelerometer can be off while the body turns.")
            center_of_mass = Gf.Vec3d(0.0)
        return _lever_arm(context.get_stage(), self._imu_path, self._body_path, center_of_mass) * self._meters_per_unit

    def _on_step(self, dt: float, _context) -> None:
        if self._stopped:
            return
        # Without Isaac's gravity term: on a stage not in meters it scales the scene's gravity, already in
        # stage units, by the units again. The accelerometer's gravity is added below from the scene.
        reading = self._sensors.get_sensor_reading(self._imu_path, False)
        if not reading.is_valid:
            self._sensors.create_sensor(self._imu_path)  # as IsaacReadIMU does; a no-op while it exists
            return
        pose = self._physx.get_rigidbody_transformation(self._body_path)
        if not pose or not pose["ret_val"]:
            carb.log_warn(f"[ZED][port {self._port}] No PhysX pose for {self._body_path}: frames carry "
                          "IsaacReadIMU's latest reading.")
            # Subscriptions cannot change inside their callback: destroy() releases it.
            self._stopped = True
            frame_imu.unregister(self._node_path, self.history)
            return

        t = self._sim_time()
        gyro = Gf.Vec3d(reading.angular_velocity_x, reading.angular_velocity_y, reading.angular_velocity_z)
        acc = Gf.Vec3d(reading.linear_acceleration_x, reading.linear_acceleration_y,
                       reading.linear_acceleration_z) * self._meters_per_unit
        orientation = Gf.Quatd(reading.orientation_w, reading.orientation_x, reading.orientation_y, reading.orientation_z)
        # Isaac's IMU rotates its readings into the sensor frame with the sensor pose from Fabric, which
        # physics writes once per app update. Rotate them again with the rigid body's PhysX pose of the step.
        x, y, z, w = pose["rotation"]
        fresh = Gf.Quatd(w, x, y, z) * self._imu_in_body
        correction = fresh.GetInverse() * orientation
        gyro, acc = correction.Transform(gyro), correction.Transform(acc)
        orientation = fresh
        if self._lever_arm is None:
            self._lever_arm = self._find_lever_arm()
        # Rigid body: the sensor-frame gyro's derivative is the angular acceleration in the sensor frame.
        angular_acc = ((gyro - self._last_gyro) / (t - self._last_gyro_t)
                       if self._last_gyro is not None and t > self._last_gyro_t else Gf.Vec3d(0.0))
        self._last_gyro, self._last_gyro_t = gyro, t
        acc += _lever_arm_acceleration(gyro, angular_acc, self._lever_arm)
        acc -= orientation.GetInverse().Transform(self._gravity)  # specific force: +g up at rest
        self.history.push(t, orientation, acc)
