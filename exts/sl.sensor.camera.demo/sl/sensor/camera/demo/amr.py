"""Stereolabs ZED X on an Idealworks iw.hub AMR patrolling a warehouse aisle.

Registers an Isaac Examples entry. "Load & Run" builds the basic warehouse with an Idealworks
iw.hub autonomous mobile robot that drives back-and-forth along the rack aisle (differential-drive
waypoint follower), with a ZED X mounted front and rear. The panel selects which camera streams to the ZED SDK:
Front or Rear (single stream on 30000), or Both (front on 30000 + rear on 30002). Plus Stereolabs floor decals.
"""
from __future__ import annotations

import asyncio
import math

import numpy as np
import omni.usd
import omni.ui as ui
import omni.kit.app
from pxr import UsdGeom, Gf

from ._common import make_zed_graph, mount_zed_nested, add_floor_logos, add_physics_ground

import isaacsim.core.experimental.utils.stage as stage_utils
import isaacsim.core.experimental.utils.app as app_utils
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.core.simulation_manager.impl.isaac_events import IsaacEvents
from isaacsim.storage.native import get_assets_root_path

# ---- drive path (rack on -X at face ~x=-8.61; lane keeps the swept rear clear; top stays below the pink-box pallet at y>8.6) ----
AISLE_X = -6.6
WP = [(AISLE_X, 7.5), (AISLE_X, -2.5)]          # drive up/down the aisle alongside the rack
START = (AISLE_X, -2.5, 0.10)                    # rests wheels-on-ground at z~0.08
START_YAW = 90.0                                 # face +Y (up the aisle) at spawn
R, L = 0.08, 0.58                                # iw.hub wheel radius, wheel base
CRUISE, SLOW = 1.1, 0.06                         # near in-place end turns -> minimal drift toward the rack
KANG, AMAX = 2.2, 1.3
WP_TOL = 0.7

# ZED X placements relative to the chassis link (identity => look +X/up +Z, same as the ZED_X asset frame)
RIGS = {
    "FRONT": {"t": (0.380, 0.0, 0.016), "r": (0.0, 0.0, 0.0)},     # front deck, looks forward +X
    "BACK":  {"t": (-1.014, 0.0, 0.032), "r": (0.0, 0.0, 180.0)},  # tail, looks backward -X
}
FRONT_PORT, BACK_PORT = 30000, 30002              # single-cam streams use 30000; "Both" adds 30002 for the rear
STREAM_OPTIONS = ["FRONT", "BACK", "BOTH"]
LOGOS = [(-8.3, 10.5), (-8.3, 4.5), (-8.3, -1.5)]  # Stereolabs floor decals (exact transforms from the humanoid scene)


class ZedAmrDemo:
    """Builds the iw.hub warehouse scene and drives the patrol; owns the Examples-browser UI."""

    def __init__(self) -> None:
        self._cb = None
        self._art = None
        self._state = None
        self._status = None
        self._world = None
        self._rig_cams = {}          # name -> ZED_X asset-root path (the streaming target)
        self._stream_combo = None

    # ---------------- UI ----------------
    def build_ui(self) -> None:
        with ui.VStack(spacing=8, height=0):
            ui.Label("Stereolabs ZED X on AMR", height=0, style={"font_size": 18})
            ui.Label("ZED X cameras (front + rear) on an Idealworks iw.hub AMR patrolling a warehouse aisle",
                     word_wrap=True, height=0)
            ui.Spacer(height=4)
            with ui.HStack(height=0, spacing=6):
                ui.Label("Streaming camera:", width=110)
                self._stream_combo = ui.ComboBox(0, "Front", "Rear", "Both")
                self._stream_combo.model.add_item_changed_fn(self._on_stream_changed)
            ui.Button("Load & Run", height=40, clicked_fn=self._on_load)
            ui.Button("Stop", height=30, clicked_fn=self._on_stop)
            with ui.HStack(height=0):
                ui.Label("Status:", width=60)
                self._status = ui.Label("Idle", width=ui.Fraction(1))

    def _set_status(self, msg: str) -> None:
        if self._status is not None:
            self._status.text = msg
        print(f"[ZED amr] {msg}")

    def _selected_stream(self) -> str:
        if self._stream_combo is None:
            return "FRONT"
        idx = self._stream_combo.model.get_item_value_model().get_value_as_int()
        return STREAM_OPTIONS[idx]

    def _on_stream_changed(self, *args) -> None:
        # streaming layout (which cameras / ports) is applied on Load & Run
        if self._rig_cams:
            self._set_status(f"Streaming set to {self._selected_stream().title()} - click Load & Run to apply")

    def _on_load(self) -> None:
        self._set_status("Loading...")
        asyncio.ensure_future(self._load_and_run())

    def _on_stop(self) -> None:
        self.stop()
        self._set_status("Stopped")

    # ---------------- build + run ----------------
    async def _load_and_run(self) -> None:
        from isaacsim.core.api import World
        from isaacsim.core.experimental.prims import Articulation
        self.stop()
        for sib in getattr(self, "_siblings", ()):
            sib.stop()

        mgr = omni.kit.app.get_app().get_extension_manager()
        if not mgr.is_extension_enabled("sl.sensor.camera"):
            mgr.set_extension_enabled_immediate("sl.sensor.camera", True)
        root = get_assets_root_path()

        await stage_utils.create_new_stage_async()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)

        World.clear_instance()
        # CPU physics: single robot, so GPU's fixed per-step overhead never amortizes (see humanoid demo).
        world = World(physics_dt=1.0/60.0, rendering_dt=1.0/60.0, stage_units_in_meters=1.0, device="cpu")
        self._world = world
        await world.initialize_simulation_context_async()

        # warehouse + invisible high-friction drive ground at z~0
        stage_utils.add_reference_to_stage(
            root + "/Isaac/Environments/Simple_Warehouse/warehouse.usd", "/World/Warehouse")
        add_physics_ground(stage, "/World/DriveGround", scale=60, friction=0.9)

        # iw.hub AMR at the start of the aisle, facing up it
        iw = stage.DefinePrim("/World/iw_hub", "Xform")
        iw.GetReferences().AddReference(root + "/Isaac/Robots/Idealworks/iwhub/iw_hub.usd")
        ixf = UsdGeom.Xformable(iw)
        ixf.AddTranslateOp().Set(Gf.Vec3d(*START))
        hy = math.radians(START_YAW) * 0.5
        ixf.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Quatd(math.cos(hy), Gf.Vec3d(0, 0, math.sin(hy))))
        await omni.kit.app.get_app().next_update_async()

        # two ZED X cameras (front + rear) nested under the chassis link as passive viewpoints
        # (rigid body disabled, not removed, so the IMU still resolves; see mount_zed_nested)
        self._rig_cams = {}
        for name, cfg in RIGS.items():
            rp = "/World/iw_hub/chassis/ZED_X_Rig_" + name
            self._rig_cams[name] = mount_zed_nested(stage, rp, cfg["t"], rotate=cfg["r"])

        # streaming graph(s) -> ZED SDK at 127.0.0.1. Single-cam selections stream on FRONT_PORT;
        # "Both" runs two graphs (front on FRONT_PORT, rear on BACK_PORT).
        which = self._selected_stream()
        if which == "BOTH":
            plan = [("Front", "FRONT", FRONT_PORT), ("Back", "BACK", BACK_PORT)]
        else:
            plan = [(which.title(), which, FRONT_PORT)]
        for suffix, cam_name, port in plan:
            make_zed_graph(stage, "/World/ZEDGraph_" + suffix, self._rig_cams[cam_name], port)

        # Stereolabs floor decals (transparent-alpha) along the lane
        demo_path = mgr.get_extension_path(mgr.get_enabled_extension_id("sl.sensor.camera.demo"))
        add_floor_logos(stage, demo_path, LOGOS)

        self._art = Articulation("/World/iw_hub")
        await world.reset_async()
        self._state = {"ready": False, "idx": 0, "widx": None}
        self._cb = SimulationManager.register_callback(self._on_step, IsaacEvents.POST_PHYSICS_STEP)
        app_utils.play()
        if which == "BOTH":
            self._set_status(f"Running - Front:{FRONT_PORT} + Rear:{BACK_PORT}. Open ZED Studio/Depth Viewer at 127.0.0.1")
        else:
            self._set_status(f"Running - {which.title()} on {FRONT_PORT}. Open ZED Studio/Depth Viewer at 127.0.0.1")

    def _yaw(self, q):
        w, x, y, z = [float(v) for v in q]
        return math.atan2(2.0*(w*z + x*y), 1.0 - 2.0*(y*y + z*z))

    def _on_step(self, dt, context=None):
        art, S = self._art, self._state
        if art is None or S is None:
            return
        try:
            if not art.is_physics_tensor_entity_valid():
                S["ready"] = False; return
            if not S["ready"]:
                S["widx"] = art.get_dof_indices(["left_wheel_joint", "right_wheel_joint"])
                S["ready"] = True; return
            p, q = art.get_world_poses()
            pos = p.numpy()[0]; quat = q.numpy()[0]
            tx, ty = WP[S["idx"]]; dx, dy = tx - float(pos[0]), ty - float(pos[1])
            if (dx*dx + dy*dy) ** 0.5 < WP_TOL:
                S["idx"] = (S["idx"] + 1) % len(WP); tx, ty = WP[S["idx"]]; dx, dy = tx - float(pos[0]), ty - float(pos[1])
            err = (math.atan2(dy, dx) - self._yaw(quat) + math.pi) % (2*math.pi) - math.pi
            lin = CRUISE if abs(err) < 0.5 else SLOW
            ang = max(-AMAX, min(AMAX, KANG * err))
            vL = (lin - ang * L / 2.0) / R
            vR = (lin + ang * L / 2.0) / R
            art.set_dof_velocity_targets(np.array([[vL, vR]]), dof_indices=S["widx"])
        except Exception as e:
            print("[ZED amr] step error:", repr(e))

    def stop(self) -> None:
        if self._cb is not None:
            try:
                SimulationManager.deregister_callback(self._cb)
            except Exception:
                pass
            self._cb = None
        try:
            app_utils.stop()
        except Exception:
            pass
