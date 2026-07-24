"""Stereolabs 3-camera ZED rig on a Unitree H1 humanoid walking a warehouse.

Registers an Isaac Examples entry. "Load & Run" builds the basic warehouse with a Unitree H1
that walks back-and-forth alongside the rack (RL locomotion policy + waypoint follower), with a
head-mounted 3-camera ZED rig streaming to the ZED SDK: a ZED Mini (stereo "eyes", port 30000)
plus two ZED X One fisheye peripherals (ports 30002 / 30004) for ~360° coverage. Each camera is a
light rigid body fixed-jointed to the head, so it rides along as the H1 walks and its IMU
resolves. Plus Stereolabs floor decals along the aisle.
"""
from __future__ import annotations

import asyncio
import math

import omni.usd
import omni.ui as ui
import omni.kit.app
import omni.timeline
from pxr import Usd, UsdGeom

from ._common import make_zed_graph, mount_zed_fixedjoint, add_floor_logos, add_physics_ground

import isaacsim.core.experimental.utils.stage as stage_utils
import isaacsim.core.experimental.utils.app as app_utils
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.core.simulation_manager.impl.isaac_events import IsaacEvents
from isaacsim.storage.native import get_assets_root_path

WP = [(-7.7, 11.0), (-7.7, -3.5)]                  # walk back-and-forth alongside the rack (x=-7.7)
LOGOS = [(-8.3, 10.5), (-8.3, 4.5), (-8.3, -1.5)]  # Stereolabs floor decals along the aisle
# Head-relative rig baked from h1_zed_3cam_linked.usd. Each entry:
# (prim name, stream cameraModel, port, resolution,
#  head-relative pos (x,y,z), head-relative quat (w,x,y,z)).
# The USD asset is resolved from cameraModel via get_camera_usd_path (ZED_XONE_S_FISHEYE -> ZED_XONE_S).
CAM_RIG = [
    ("ZED_M",         "ZED_M",              30000, "HD720",
     (0.041022, 0.013251, 0.026449),   (-0.474083, -0.524637, 0.524640, -0.474082)),
    ("ZED_XONE_S",    "ZED_XONE_S_FISHEYE", 30002, "SVGA",
     (-0.010944, 0.061256, -0.020550), (-0.253711, 0.058685, 0.912194, -0.316369)),
    ("ZED_XONE_S_01", "ZED_XONE_S_FISHEYE", 30004, "SVGA",
     (0.076406, 0.061256, -0.020550),  (0.316370, 0.912193, 0.058681, 0.253713)),
]
CAM_MASS = 0.1   # kg per camera, light so the H1 balance policy is unaffected
# Physics backend device. GPU ("cuda") carries a large fixed per-step cost (kernel dispatch +
# cudaStreamSynchronize) that only amortizes across many parallel envs; for this single-robot
# demo "cpu" is ~20x faster per PhysX step (11ms -> 0.5ms measured). Flip to "cuda" to A/B profile.
PHYSICS_DEVICE = "cpu"
# Physics steps per rendered frame (rendering_dt / physics_dt). Also the decimation at which the
# low-frequency waypoint steering is recomputed in _on_step (navigation doesn't need 200 Hz).
SUBSTEPS = 8


class ZedHumanoidDemo:
    """Builds the H1 warehouse scene and drives the walk; owns the Examples-browser UI."""

    def __init__(self) -> None:
        self._cb = None
        self._h1 = None
        self._state = None
        self._status = None
        self._torch = None
        self._wp = None
        self._world = None
        self._tl_sub = None
        self._need_reset = False
        self._resetting = False

    # ---------------- UI ----------------
    def build_ui(self) -> None:
        with ui.VStack(spacing=8, height=0):
            ui.Label("Stereolabs ZED 3-camera rig on Humanoid", height=0, style={"font_size": 18})
            ui.Label("A ZED Mini + two ZED X One fisheye peripherals head-mounted on the Unitree H1 "
                     "walking a warehouse (~360° coverage)", word_wrap=True, height=0)
            ui.Spacer(height=4)
            ui.Button("Load & Run", height=40, clicked_fn=self._on_load)
            ui.Button("Stop", height=30, clicked_fn=self._on_stop)
            with ui.HStack(height=0):
                ui.Label("Status:", width=60)
                self._status = ui.Label("Idle", width=ui.Fraction(1))

    def _set_status(self, msg: str) -> None:
        if self._status is not None:
            self._status.text = msg
        print(f"[ZED humanoid] {msg}")

    def _on_load(self) -> None:
        self._set_status(f"Loading ({PHYSICS_DEVICE.upper()} physics + RL policy)...")
        asyncio.ensure_future(self._load_and_run())

    def _on_stop(self) -> None:
        self.stop()
        self._set_status("Stopped")

    # ---------------- build + run ----------------
    async def _load_and_run(self) -> None:
        import torch
        import warp as wp
        from isaacsim.core.api import World
        from isaacsim.robot.policy.examples.robots import H1FlatTerrainPolicy
        self._torch, self._wp = torch, wp
        self.stop()
        for sib in getattr(self, "_siblings", ()):
            sib.stop()

        mgr = omni.kit.app.get_app().get_extension_manager()
        if not mgr.is_extension_enabled("sl.sensor.camera"):
            mgr.set_extension_enabled_immediate("sl.sensor.camera", True)
        root = get_assets_root_path()
        await stage_utils.create_new_stage_async()
        stage = omni.usd.get_context().get_stage()

        World.clear_instance()
        world = World(physics_dt=1.0/200.0, rendering_dt=SUBSTEPS/200.0,
                      stage_units_in_meters=1.0, backend="torch", device=PHYSICS_DEVICE)
        self._world = world
        await world.initialize_simulation_context_async()
        SimulationManager.set_backend("torch")
        SimulationManager.set_physics_sim_device(PHYSICS_DEVICE)

        # warehouse + invisible high-friction walking ground (policy trained for friction 1.0)
        stage_utils.add_reference_to_stage(
            root + "/Isaac/Environments/Simple_Warehouse/warehouse.usd", "/World/Warehouse")
        add_physics_ground(stage, "/World/WalkGround", scale=48, friction=1.0, z=-0.499)

        h1 = H1FlatTerrainPolicy(prim_path="/World/H1", position=[-7.7, -3.5, 1.05])
        self._h1 = h1

        # 3-camera ZED rig on the head: each camera is a light rigid body fixed-jointed to the head
        # link (excluded from the articulation) so it rides along as the H1 walks and its IMU
        # resolves. ZED Mini streams stereo; the two ZED X One peripherals stream fisheye.
        head = next((p for p in Usd.PrimRange(stage.GetPrimAtPath("/World/H1"))
                     if p.GetName() == "d435_rgb_module_link"), None)
        if head is None:
            self._set_status("Error: H1 head link 'd435_rgb_module_link' not found")
            return
        head_world = UsdGeom.XformCache().GetLocalToWorldTransform(head)
        for name, model, port, res, pos, quat in CAM_RIG:
            cam_path = mount_zed_fixedjoint(stage, f"/World/{name}", head.GetPath(), head_world,
                                            model=model, pos=pos, quat=quat, mass=CAM_MASS)
            make_zed_graph(stage, f"/World/ZEDGraph_{port}", cam_path, port, model=model, res=res)

        # Stereolabs floor decals (transparent-alpha) along the aisle
        demo_path = mgr.get_extension_path(mgr.get_enabled_extension_id("sl.sensor.camera.demo"))
        add_floor_logos(stage, demo_path, LOGOS)

        await world.reset_async()
        self._state = {"ready": False, "idx": 0}
        self._cb = SimulationManager.register_callback(self._on_step, IsaacEvents.POST_PHYSICS_STEP)
        # Sidebar Play after a sidebar Stop resumes physics without the world reset above, so
        # the balance policy restarts from an uninitialized articulation and the H1 falls.
        # Watch the timeline and replay the reset when that happens (Load & Run stays as-is).
        if self._tl_sub is None:
            self._tl_sub = (omni.timeline.get_timeline_interface().get_timeline_event_stream()
                            .create_subscription_to_pop(self._on_timeline))
        self._need_reset = False
        app_utils.play()
        self._set_status("Running - open ZED Studio at 127.0.0.1 ports 30000/30002/30004")

    def _on_timeline(self, e) -> None:
        if self._resetting:
            return   # world.reset_async stops+replays the timeline itself: ignore its own events
        if e.type == int(omni.timeline.TimelineEventType.STOP):
            self._need_reset = True
        elif e.type == int(omni.timeline.TimelineEventType.PLAY) and self._need_reset:
            self._need_reset = False
            if self._world is None or self._cb is None:
                return   # demo torn down: nothing drives the robot, don't touch the stage

            async def _replay_reset():
                self._resetting = True
                try:
                    await self._world.reset_async()
                    if self._state is not None:
                        self._state["ready"] = False   # re-initialize the policy on the next step
                        self._state["idx"] = 0         # robot is back at the start waypoint
                    app_utils.play()                   # make sure the reset ends in a playing state
                except Exception as e:
                    print(f"[ZED humanoid] play-reset failed: {e!r}")
                finally:
                    self._resetting = False

            asyncio.ensure_future(_replay_reset())

    def _yaw(self, q):
        w, x, y, z = q
        return math.atan2(2.0*(w*z + x*y), 1.0 - 2.0*(y*y + z*z))

    def _on_step(self, dt, context=None):
        h1, S, wp, torch = self._h1, self._state, self._wp, self._torch
        if h1 is None or S is None:
            return
        try:
            if not h1.robot.is_physics_tensor_entity_valid():
                S["ready"] = False
            if not S["ready"]:
                S["ready"] = True; h1.initialize(); h1.post_reset()
                S["cmd"] = torch.tensor([0.0, 0.0, 0.0], device=PHYSICS_DEVICE); S["n"] = 0
                return
            # POST_PHYSICS_STEP fires once per physics substep (SUBSTEPS x per rendered frame).
            # Waypoint steering is low-frequency navigation, so recompute + read back the pose only
            # once per frame and reuse the cached command in between; the RL policy still runs every
            # step (h1.forward self-decimates its own inference internally).
            if S["n"] % SUBSTEPS == 0:
                pos = wp.to_torch(h1.robot.get_world_poses()[0])[0].tolist()
                q = wp.to_torch(h1.robot.get_world_poses()[1])[0].tolist()
                tx, ty = WP[S["idx"]]; dx, dy = tx - pos[0], ty - pos[1]
                if (dx*dx + dy*dy) ** 0.5 < 0.7:
                    S["idx"] = (S["idx"] + 1) % len(WP); tx, ty = WP[S["idx"]]; dx, dy = tx - pos[0], ty - pos[1]
                err = (math.atan2(dy, dx) - self._yaw(q) + math.pi) % (2*math.pi) - math.pi
                fwd = 0.8 if abs(err) < 0.5 else 0.1
                wz = max(-0.9, min(0.9, 1.8*err))
                S["cmd"] = torch.tensor([fwd, 0.0, wz], device=PHYSICS_DEVICE)
            S["n"] += 1
            h1.forward(dt, S["cmd"])
        except Exception as e:
            print("[ZED humanoid] step error:", repr(e))

    def stop(self) -> None:
        if self._cb is not None:
            try:
                SimulationManager.deregister_callback(self._cb)
            except Exception:
                pass
            self._cb = None
        if self._tl_sub is not None:
            self._tl_sub.unsubscribe()
            self._tl_sub = None
        try:
            app_utils.stop()
        except Exception:
            pass
