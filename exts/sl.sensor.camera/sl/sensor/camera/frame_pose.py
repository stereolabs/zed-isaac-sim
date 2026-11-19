"""The pose of a capture's camera at each physics step, for a pose writer to take at its frame's time.

Under multi-tick rendering a frame shows the physics state at its tick, which can fall inside an app update,
while the CameraParams annotator gives the camera's pose at the end of that update. This reads the PhysX pose
of the camera's rigid body after every physics step; the camera's pose at a frame's time follows from it and
the camera's fixed place on the body.
"""
from __future__ import annotations

import carb
import carb.settings
from pxr import Gf, UsdGeom

from . import frame_imu
from .imu_stream import _rigid_body_and_offset

# Post-step callbacks run by ascending order; the simulation time (order 0) is updated by then.
_STEP_ORDER = 10


def view_transform(camera_in_body: Gf.Matrix4d, orientation: Gf.Quatd, position: Gf.Vec3d) -> list[float]:
    """World-to-camera transform of a camera at ``camera_in_body`` on a rigid body at this world pose, as
    CameraParams' cameraViewTransform: 16 floats, row-major, for row vectors (translation in the last row)."""
    body_to_world = Gf.Matrix4d(Gf.Matrix3d(orientation), Gf.Vec3d(position))
    view = (camera_in_body * body_to_world).GetInverse()
    return [view[i][j] for i in range(4) for j in range(4)]


class CameraPoses:
    """The world pose of the rigid body carrying a camera at every physics step, looked up at a frame's time.

    ``available`` is False when PhysX poses are not read back, or when no rigid body carries the camera (its
    pose then changes only between app updates, and CameraParams gives it).
    """

    def __init__(self, camera_path: str):
        self.available = False
        self._history = frame_imu.ImuHistory()  # (time, orientation, position) per step
        self._sub = None
        self._missed_warned = False
        try:
            import omni.physics.core
            import omni.physx
            import omni.usd
            from isaacsim.core.simulation_manager import SimulationManager
        except ImportError as exc:
            carb.log_info(f"[ZED][Depth] [{camera_path}] Frames carry the CameraParams pose ({exc}).")
            return
        if carb.settings.get_settings().get_as_bool("/physics/suppressReadback"):
            carb.log_info(f"[ZED][Depth] [{camera_path}] GPU physics without readback: frames carry the "
                          "CameraParams pose, the camera's pose at the end of the app update.")
            return
        stage = omni.usd.get_context().get_stage()
        self._body_path, _ = _rigid_body_and_offset(stage, camera_path)
        if not self._body_path:
            carb.log_info(f"[ZED][Depth] [{camera_path}] No rigid body carries the camera: frames carry the "
                          "CameraParams pose, the camera's pose at the end of the app update.")
            return
        cache = UsdGeom.XformCache()
        self._camera_in_body = (cache.GetLocalToWorldTransform(stage.GetPrimAtPath(camera_path))
                                * cache.GetLocalToWorldTransform(stage.GetPrimAtPath(self._body_path))
                                .RemoveScaleShear().GetInverse())
        self._camera_path = camera_path
        self._sim_time = SimulationManager.get_simulation_time
        self._physx = omni.physx.get_physx_interface()
        self._sub = omni.physics.core.get_physics_simulation_interface().subscribe_physics_on_step_events(
            pre_step=False, order=_STEP_ORDER, on_update=self._on_step)
        self.available = True

    def _on_step(self, _dt, _context) -> None:
        pose = self._physx.get_rigidbody_transformation(self._body_path)
        if not pose or not pose["ret_val"]:
            return  # view_transform() misses the frame and says so
        x, y, z, w = pose["rotation"]
        self._history.push(self._sim_time(), Gf.Quatd(w, x, y, z), Gf.Vec3d(*pose["position"]))

    def view_transform(self, t: float) -> list[float] | None:
        """The camera's world-to-camera transform at simulation time ``t`` (cameraViewTransform layout), None
        when no physics step around ``t`` was recorded."""
        if not self.available:
            return None
        found, pose = self._history.at(t)
        if found != frame_imu.FOUND:
            if not self._missed_warned:
                self._missed_warned = True
                carb.log_warn(f"[ZED][Depth] [{self._camera_path}] No PhysX pose of {self._body_path} at a "
                              f"frame's time ({t:.6f} s): such frames carry the CameraParams pose instead.")
            return None
        return view_transform(self._camera_in_body, *pose)

    def destroy(self) -> None:
        self._sub = None
        self.available = False
