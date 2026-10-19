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
import traceback

import omni.usd
import omni.ui as ui
import omni.kit.app
import omni.timeline
from pxr import Usd, UsdGeom

from ._common import (make_zed_graph, mount_zed_fixedjoint, add_floor_logos, add_physics_ground,
                      hide_asset_camera, kit_at_least, steer_to_waypoint, AISLE_LOGOS, KIT_ISAAC_61)

import isaacsim.core.experimental.utils.stage as stage_utils
import isaacsim.core.experimental.utils.app as app_utils
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.core.simulation_manager.impl.isaac_events import IsaacEvents
from isaacsim.storage.native import get_assets_root_path

WP = [(-7.7, 11.0), (-7.7, -3.5)]                  # walk back-and-forth alongside the rack (x=-7.7)
# Head-relative rig baked from h1_zed_3cam_linked.usd. Each entry:
# (prim name, stream cameraModel, port, resolution,
#  head-relative pos (x,y,z), head-relative quat (w,x,y,z)).
# The USD asset is resolved from cameraModel via get_camera_usd_path (ZED_XONE_S_FISHEYE -> ZED_XONE_S).
CAM_RIG = [
    ("ZED_M",         "ZED_M",              30000, "HD720",
     (0.025986, 0.013251, 0.026449),   (-0.474083, -0.524637, 0.524640, -0.474082)),
    ("ZED_XONE_S",    "ZED_XONE_S_FISHEYE", 30002, "SVGA",
     (-0.010944, 0.061256, -0.020550), (-0.253711, 0.058685, 0.912194, -0.316369)),
    ("ZED_XONE_S_01", "ZED_XONE_S_FISHEYE", 30004, "SVGA",
     (0.076406, 0.061256, -0.020550),  (0.316370, 0.912193, 0.058681, 0.253713)),
]
CAM_MASS = 0.1   # kg per camera, light so the H1 balance policy is unaffected
# Rate the cameras render at, and so the rate anything reading them sees.
#
# A ZED runs at one of a fixed set of rates. Stick to 15, 30, 60 or 120; anything else is
# rejected and falls back to 30.
#
# This is also what the streams declare to the SDK, so it has to be the rate the cameras are
# actually rendered at: a stream that announces more frames than the scene produces plays back
# wrong at the receiver.
#
# This is simulation time, not wall-clock: frame timestamps come from the simulator's own clock,
# so asking for 60 here yields a true 60 fps even on a machine that can only push a few frames a
# second. It just takes longer.
RENDER_FPS = 30
# Physics backend device. GPU ("cuda") carries a large fixed per-step cost (kernel dispatch +
# cudaStreamSynchronize) that only amortizes across many parallel envs; for this single-robot
# demo "cpu" is ~20x faster per PhysX step (11ms -> 0.5ms measured). Flip to "cuda" to A/B profile.
PHYSICS_DEVICE = "cpu"
# Physics rate to aim for. The actual rate is snapped to a whole number of steps per rendered
# frame below, because the renderer can only tick on a physics step: asking for a rate that is
# not a divisor of the physics rate would silently give a different one.
PHYSICS_HZ_TARGET = 200.0
# Physics steps per rendered frame, chosen to land the physics rate near PHYSICS_HZ_TARGET while
# keeping the render rate exactly RENDER_FPS. Also the decimation at which the low-frequency
# waypoint steering is recomputed in _on_step (navigation doesn't need the full physics rate).
SUBSTEPS = max(1, round(PHYSICS_HZ_TARGET / RENDER_FPS))
# Derived, not chosen: this is what makes RENDER_FPS come out exact.
PHYSICS_HZ = float(RENDER_FPS * SUBSTEPS)
# Derive the render step by MULTIPLYING the physics step, never as SUBSTEPS / PHYSICS_HZ.
PHYSICS_DT = 1.0 / PHYSICS_HZ
RENDERING_DT = SUBSTEPS * PHYSICS_DT


# ---------------- H1 locomotion policy driver ----------------
# Isaac Sim 6.1 (isaacsim.robot.policy.examples 7.0) removed H1FlatTerrainPolicy in favour of the
# generic RobotPolicyRunner. Both spawn the same robot and take the same [vx, vy, wz] command but
# differ in how the policy is started and stepped, so each sits behind the same small driver.


class _H1Runner:
    """H1 flat-terrain locomotion on isaacsim.robot.policy.examples 7.x (Isaac Sim 6.1)."""

    def __init__(self, prim_path, position) -> None:
        from isaacsim.robot.policy.examples import RobotPolicyRunner, get_h1_spec
        # The demo runs PhysX, and only the PhysX artifact ships the d435 head link the camera rig
        # mounts to, so pin the engine rather than following whichever one happens to be active.
        self._runner = RobotPolicyRunner(get_h1_spec(), prim_path=prim_path,
                                         position=position, training_engine="physx")
        self._runner.spawn()

    @property
    def articulation(self):
        return self._runner.articulation

    def start(self, cmd) -> None:
        self._runner.restart_from_default_state(cmd)

    def step(self, dt, cmd) -> None:
        self._runner.step(dt, cmd)

    def close(self) -> None:
        self._runner.close()


class _H1Legacy:
    """H1 flat-terrain locomotion on isaacsim.robot.policy.examples 6.x (Isaac Sim 6.0)."""

    def __init__(self, prim_path, position) -> None:
        import torch
        from isaacsim.robot.policy.examples.robots import H1FlatTerrainPolicy
        self._torch = torch
        self._policy = H1FlatTerrainPolicy(prim_path=prim_path, position=position)

    @property
    def articulation(self):
        return self._policy.robot

    def start(self, cmd) -> None:
        self._policy.initialize()
        self._policy.post_reset()

    def step(self, dt, cmd) -> None:
        self._policy.forward(dt, self._torch.tensor(cmd, device=PHYSICS_DEVICE))

    def close(self) -> None:
        pass


def _make_h1(prim_path, position):
    """Spawn the H1 and its locomotion policy through the API this Isaac Sim ships."""
    ext = "isaacsim.robot.policy.examples"   # same name either side of 6.1, different contents
    mgr = omni.kit.app.get_app().get_extension_manager()
    if not mgr.set_extension_enabled_immediate(ext, True):
        raise RuntimeError(f"the humanoid demo needs {ext}, which this Isaac Sim does not have")
    driver = _H1Runner if kit_at_least(KIT_ISAAC_61) else _H1Legacy
    return driver(prim_path, position)


class ZedHumanoidDemo:
    """Builds the H1 warehouse scene and drives the walk; owns the Examples-browser UI."""

    def __init__(self) -> None:
        self._cb = None
        self._h1 = None
        self._state = None
        self._status = None
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
        print(f"[ZED][humanoid] {msg}")

    def _on_load(self) -> None:
        self._set_status(f"Loading ({PHYSICS_DEVICE.upper()} physics + RL policy)...")
        # ensure_future drops whatever the build raises unless someone asks the task for it, and
        # a scene that silently never appears is the hardest kind of failure to chase.
        asyncio.ensure_future(self._load_and_run()).add_done_callback(self._report_load)

    def _report_load(self, task) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._set_status(f"Error: build failed - {error!r} (traceback in the console)")
            traceback.print_exception(type(error), error, error.__traceback__)

    def _on_stop(self) -> None:
        self.stop()
        self._set_status("Stopped")

    # ---------------- build + run ----------------
    async def _load_and_run(self) -> None:
        from isaacsim.core.api import World
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
        world = World(physics_dt=PHYSICS_DT, rendering_dt=RENDERING_DT,
                      stage_units_in_meters=1.0, backend="torch", device=PHYSICS_DEVICE)
        self._world = world
        await world.initialize_simulation_context_async()
        SimulationManager.set_backend("torch")
        SimulationManager.set_physics_sim_device(PHYSICS_DEVICE)

        # warehouse + invisible high-friction walking ground (policy trained for friction 1.0)
        stage_utils.add_reference_to_stage(
            root + "/Isaac/Environments/Simple_Warehouse/warehouse.usd", "/World/Warehouse")
        hide_asset_camera(stage, "/World/Warehouse")
        add_physics_ground(stage, "/World/WalkGround", scale=48, friction=1.0, z=-0.499)

        h1 = _make_h1("/World/H1", [-7.7, -3.5, 1.05])
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
            make_zed_graph(stage, f"/World/ZEDGraph_{port}", cam_path, port,
                           model=model, res=res, fps=RENDER_FPS)

        # Stereolabs floor decals (transparent-alpha) along the aisle
        demo_path = mgr.get_extension_path(mgr.get_enabled_extension_id("sl.sensor.camera.demo"))
        add_floor_logos(stage, demo_path, AISLE_LOGOS)

        await world.reset_async()
        self._state = {"ready": False, "failed": False, "idx": 0}
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
                        self._state["failed"] = False
                        self._state["idx"] = 0         # robot is back at the start waypoint
                    app_utils.play()                   # make sure the reset ends in a playing state
                except Exception as e:
                    print(f"[ZED][humanoid] play-reset failed: {e!r}")
                finally:
                    self._resetting = False

            asyncio.ensure_future(_replay_reset())

    def _on_step(self, dt, context=None):
        h1, S = self._h1, self._state
        if h1 is None or S is None or S["failed"]:
            return
        try:
            art = h1.articulation
            if art is None or not art.is_physics_tensor_entity_valid():
                S["ready"] = False
            if not S["ready"]:
                S["cmd"] = [0.0, 0.0, 0.0]; S["n"] = 0
                h1.start(S["cmd"])
                S["ready"] = True
                return
            # POST_PHYSICS_STEP fires once per physics substep (SUBSTEPS x per rendered frame).
            # Waypoint steering is low-frequency navigation, so recompute + read back the pose only
            # once per frame and reuse the cached command in between; the RL policy still runs every
            # step (the driver self-decimates its own inference internally).
            if S["n"] % SUBSTEPS == 0:
                p, q = art.get_world_poses()
                S["idx"], err = steer_to_waypoint(p.numpy()[0], q.numpy()[0], WP, S["idx"], 0.7)
                fwd = 0.8 if abs(err) < 0.5 else 0.1
                wz = max(-0.9, min(0.9, 1.8*err))
                S["cmd"] = [fwd, 0.0, wz]
            S["n"] += 1
            h1.step(dt, S["cmd"])
        except Exception as e:
            # Latched: a policy that cannot start would otherwise raise on every physics step.
            S["failed"] = True
            self._set_status(f"Error: policy step failed - {e!r}")

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
        if self._h1 is not None:
            try:
                self._h1.close()
            except Exception:
                pass
            self._h1 = None
        try:
            app_utils.stop()
        except Exception:
            pass
