"""Stereolabs ZED Warehouse Pick-Place demo.

Registers an Isaac Examples entry. "Load & Run" builds a warehouse pick-and-place cell (Franka on a
wood bench, 2 cubes, a KLT bin, studio lighting) with a wrist-mounted ZED X Nano streaming to the ZED
SDK, then runs a continuous pick-place loop.
"""
from __future__ import annotations

import asyncio
import random

import numpy as np
import omni.usd
import omni.ui as ui
import omni.kit.app
import omni.kit.commands
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, UsdLux, Gf, Sdf

from ._common import (make_zed_graph, mount_zed_nested, make_logo_material, add_logo_quad,
                      hide_asset_camera, kit_at_least, KIT_ISAAC_61)
import isaacsim.core.experimental.utils.stage as stage_utils
import isaacsim.core.experimental.utils.app as app_utils
from isaacsim.core.simulation_manager import SimulationManager
from isaacsim.core.simulation_manager.impl.isaac_events import IsaacEvents
from isaacsim.storage.native import get_assets_root_path

TABLE_H = 0.75
Z0 = TABLE_H + 0.0258
BIN_XY = (0.0, 0.34)
BIN_TARGET = [BIN_XY[0], BIN_XY[1], TABLE_H + 0.25]
HOME = [0.012, -0.568, 0.0, -2.811, 0.0, 3.037, 0.741, 0.04, 0.04]
HOME_ARM = np.array(HOME[:7])
WAREHOUSE = "/World/WarehouseRot"
PICK_XY = [(0.50, -0.15), (0.48, 0.12)]


# ---------------- Franka pick-place driver ----------------
# Isaac Sim 6.1 removed isaacsim.robot.experimental.manipulators.examples; its replacement,
# isaacsim.robot_motion.examples, plans with cuMotion and owns the pick-place sequencing itself.
# The two share no API, so each sits behind the same small driver: place the robot and cubes,
# start once the timeline is playing, and advance on every physics step.


class _ArmTask:
    """Franka pick-place on isaacsim.robot_motion.examples (Isaac Sim 6.1)."""

    def __init__(self) -> None:
        from isaacsim.robot_motion.examples.manipulation import PickPlaceTask
        # Positions are bench-relative: the task offsets the robot and both cubes by TABLE_H.
        self._task = PickPlaceTask(
            robot_path="/World/robot", cube_path="/World/Cube",
            offset=(0.0, 0.0, TABLE_H),
            cube_positions=[(x, y, Z0 - TABLE_H) for x, y in PICK_XY],
            place_position=(BIN_XY[0], BIN_XY[1], BIN_TARGET[2] - TABLE_H),
        )

    @property
    def cube_paths(self) -> list[str]:
        return self._task.cube_paths

    def setup_scene(self) -> None:
        self._task.setup_scene()

    def start(self) -> None:
        # cuMotion's collision world is built from whatever geometry is on the stage, so this runs
        # last. The warehouse shell is metres away from the cell and only slows the query down; the
        # KLT bin has to go because cuMotion rejects a collider under a non-uniformly scaled
        # ancestor, which is how the asset is authored. The bench stays, and the release pose sits
        # well above the bin, so the arm never needs to plan around it.
        self._task.initialize(exclude_prim_paths=[WAREHOUSE, "/World/KLT"])

    def step(self, dt: float) -> None:
        # Releasing over the bin drops the cube ~17 cm, which the task's place-settle check reads
        # as a failure, so a finished round trip shows up as either done or failed. Restart on both
        # to keep the cell moving for the camera, and rotate the cube list because a restarted task
        # always picks its first one.
        if self._task.is_done or self._task.failed:
            self._task.reset()
            for cube in self._task.cubes:                  # lift them back out of the bin
                cube.reset_to_default_state()
            self._task.cubes.append(self._task.cubes.pop(0))
            self._task.cube_paths.append(self._task.cube_paths.pop(0))
        else:
            self._task.step(dt)

    def stop(self) -> None:
        self._task.cleanup()


class _ArmLegacy:
    """Franka pick-place on isaacsim.robot.experimental.manipulators.examples (Isaac Sim 6.0)."""

    def __init__(self) -> None:
        self._pp = None
        self._cubes = None
        self._state = None

    @property
    def cube_paths(self) -> list[str]:
        return ["/World/Cube", "/World/Cube_1"]

    def setup_scene(self) -> None:
        from isaacsim.robot.experimental.manipulators.examples.franka import FrankaPickPlace
        from isaacsim.core.experimental.objects import Cube
        from isaacsim.core.experimental.prims import GeomPrim, RigidPrim
        pp = FrankaPickPlace(events_dt=[90, 60, 30, 60, 120, 30, 40])
        pp.setup_scene()
        self._pp = pp
        pp.robot.set_world_poses(positions=[0.0, 0.0, TABLE_H], orientations=[1.0, 0.0, 0.0, 0.0])
        pp.target_position = np.array(BIN_TARGET)
        pp.cube_initial_position = np.array([PICK_XY[0][0], PICK_XY[0][1], Z0])
        pp.cube.set_world_poses(positions=[PICK_XY[0][0], PICK_XY[0][1], Z0])
        c1 = Cube(paths=self.cube_paths[1], positions=np.array([PICK_XY[1][0], PICK_XY[1][1], Z0]),
                  orientations=np.array([1, 0, 0, 0]), sizes=1.0,
                  scales=np.array([0.0515, 0.0515, 0.0515]), colors="gray")
        GeomPrim(paths=c1.paths, apply_collision_apis=True)
        RigidPrim(paths=c1.paths)

    def start(self) -> None:
        from isaacsim.core.experimental.prims import RigidPrim
        stage = omni.usd.get_context().get_stage()
        self._cubes = [{"rigid": RigidPrim(p),
                        "img": UsdGeom.Imageable(stage.GetPrimAtPath(p)),
                        "path": p} for p in self.cube_paths]
        self._pp.reset_robot()
        self._state = {"phase": "run", "timer": 0, "idx": self._choose()}

    def step(self, dt: float) -> None:
        pp, S = self._pp, self._state
        if S["phase"] == "run":
            if pp.is_done():
                c = self._cubes[S["idx"]]
                c["img"].MakeInvisible()
                c["rigid"].set_world_poses(positions=self._new_pos(c["path"]))
                c["img"].MakeVisible()
                pp.robot.set_dof_position_targets(HOME)
                S["phase"] = "homing"; S["timer"] = 0
            else:
                pp.forward("damped-least-squares")
        elif S["phase"] == "homing":
            pp.robot.set_dof_position_targets(HOME)
            S["timer"] += 1
            try:
                near = np.abs(self._arm_q() - HOME_ARM).max() < 0.06
            except Exception:
                near = False
            if near or S["timer"] > 220:
                S["idx"] = self._choose(); S["phase"] = "run"

    def stop(self) -> None:
        pass

    def _choose(self) -> int:
        i = random.randrange(len(self._cubes))
        self._pp.cube = self._cubes[i]["rigid"]
        self._pp._event = 0; self._pp._step = 0
        return i

    def _arm_q(self):
        q = self._pp.robot.get_current_state()[0]
        q = q.numpy() if hasattr(q, "numpy") else np.asarray(q)
        return np.asarray(q).reshape(-1)[:7]

    def _new_pos(self, exclude_path):
        others = [self._cubes[k]["rigid"].get_world_poses()[0].numpy()[0][:2]
                  for k in range(len(self._cubes)) if self._cubes[k]["path"] != exclude_path]
        x, y = 0.48, -0.05
        for _ in range(40):
            x = random.uniform(0.40, 0.58); y = random.uniform(-0.25, 0.15)
            if all(np.hypot(x - ox, y - oy) >= 0.13 for ox, oy in others):
                break
        return np.array([x, y, Z0])


def _make_arm():
    """Build the pick-place driver for the example extension this Isaac Sim ships."""
    # 6.1 keeps the 6.0 extension as a shim that raises only when constructed, so picking by
    # version rather than by what is installed is what keeps 6.1 off the dead one.
    if kit_at_least(KIT_ISAAC_61):
        ext, driver = "isaacsim.robot_motion.examples", _ArmTask
    else:
        ext, driver = "isaacsim.robot.experimental.manipulators.examples", _ArmLegacy
    mgr = omni.kit.app.get_app().get_extension_manager()
    if not mgr.set_extension_enabled_immediate(ext, True):
        raise RuntimeError(f"the pick-place demo needs {ext}, which this Isaac Sim does not have")
    return driver()


class ZedPickPlaceDemo:
    """Builds the scene and runs the pick-place loop; owns the Examples-browser UI."""

    def __init__(self) -> None:
        self._cb = None
        self._arm = None
        self._status = None

    # ---------------- UI ----------------
    def build_ui(self) -> None:
        with ui.VStack(spacing=8, height=0):
            ui.Label("Stereolabs ZED X Nano on Robotic Arm", height=0,
                     style={"font_size": 18})
            ui.Label("A ZED X Nano camera wrist-mounted on the Franka pick-and-place robotic arm",
                     word_wrap=True, height=0)
            ui.Spacer(height=4)
            ui.Button("Load & Run", height=40, clicked_fn=self._on_load)
            ui.Button("Stop", height=30, clicked_fn=self._on_stop)
            with ui.HStack(height=0):
                ui.Label("Status:", width=60)
                self._status = ui.Label("Idle", width=ui.Fraction(1))

    def _set_status(self, msg: str) -> None:
        if self._status is not None:
            self._status.text = msg
        print(f"[ZED][demo] {msg}")

    def _on_load(self) -> None:
        self._set_status("Loading...")
        asyncio.ensure_future(self._load_and_run())

    def _on_stop(self) -> None:
        self.stop()
        self._set_status("Stopped")

    # ---------------- build + run ----------------
    async def _load_and_run(self) -> None:
        # tear down our own prior run (and the siblings') before rebuilding, else a stale step
        # callback fires against removed prims during the stage rebuild
        self.stop()
        for sib in getattr(self, "_siblings", ()):
            sib.stop()
        await self._build_scene()
        await self._arm_loop()
        self._set_status("Running - open ZED Explorer/Depth Viewer at 127.0.0.1")

    async def _build_scene(self) -> None:
        mgr = omni.kit.app.get_app().get_extension_manager()
        await stage_utils.create_new_stage_async()
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        # CPU physics: the experimental API defaults to GPU, but for a single Franka the fixed
        # per-step GPU overhead never amortizes and dominates the frame (see humanoid demo). Set
        # before any experimental prim / physics view is created below.
        SimulationManager.set_physics_sim_device("cpu")
        root = get_assets_root_path()

        # warehouse rotated 180 so the rack faces the robot (parent rotate -> no ref xformOp clash)
        wrot = stage.DefinePrim(WAREHOUSE, "Xform")
        UsdGeom.Xformable(wrot).AddRotateXYZOp().Set(Gf.Vec3f(0, 0, 180))
        stage.DefinePrim(WAREHOUSE + "/WH", "Xform").GetReferences().AddReference(
            root + "/Isaac/Environments/Simple_Warehouse/warehouse.usd")
        hide_asset_camera(stage, WAREHOUSE + "/WH")
        stage.DefinePrim("/World/ground_plane", "Xform")   # stub: skip setup_scene ground+dome

        # workbench + wood material
        bench = UsdGeom.Cube.Define(stage, "/World/Bench"); bench.GetSizeAttr().Set(1.0)
        bp = bench.GetPrim(); bxf = UsdGeom.Xformable(bp)
        bxf.AddTranslateOp().Set(Gf.Vec3d(0.25, 0.08, TABLE_H/2))
        bxf.AddScaleOp().Set(Gf.Vec3f(1.4, 1.1, TABLE_H))
        UsdPhysics.CollisionAPI.Apply(bp)
        omni.kit.commands.execute("CreateMdlMaterialPrim",
            mtl_url=root + "/NVIDIA/Materials/Base/Wood/Ash_Planks.mdl",
            mtl_name="Ash_Planks", mtl_path="/World/Looks/BenchWood")
        bsh = UsdShade.Shader(stage.GetPrimAtPath("/World/Looks/BenchWood/Shader"))
        bsh.CreateInput("project_uvw", Sdf.ValueTypeNames.Bool).Set(True)
        bsh.CreateInput("world_or_object", Sdf.ValueTypeNames.Bool).Set(False)
        bsh.CreateInput("texture_scale", Sdf.ValueTypeNames.Float2).Set((0.6, 0.6))
        UsdShade.MaterialBindingAPI.Apply(bp)
        UsdShade.MaterialBindingAPI(bp).Bind(UsdShade.Material(stage.GetPrimAtPath("/World/Looks/BenchWood")))

        # Franka + cubes on the bench
        self._arm = _make_arm()
        self._arm.setup_scene()
        cube_paths = self._arm.cube_paths

        # the Franka ships a blue status-LED material (EmissiveBlue, intensity 29k) that
        # reads as a lamp on camera - swap it for black matte. The robot's geometry scopes
        # are instanceable, so deinstance first to make the shader prims editable.
        robot_root = stage.GetPrimAtPath("/World/robot")
        for prim in Usd.PrimRange(robot_root):
            if prim.IsInstanceable():
                prim.SetInstanceable(False)
        for prim in Usd.PrimRange(robot_root):
            if prim.GetTypeName() == "Shader" and prim.GetParent().GetName() == "EmissiveBlue":
                sh = UsdShade.Shader(prim)
                sh.CreateInput("enable_emission", Sdf.ValueTypeNames.Bool).Set(False)
                sh.CreateInput("emissive_intensity", Sdf.ValueTypeNames.Float).Set(0.0)
                sh.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.02, 0.02, 0.02))
                sh.CreateInput("reflection_roughness_constant", Sdf.ValueTypeNames.Float).Set(0.85)
                sh.CreateInput("metallic_constant", Sdf.ValueTypeNames.Float).Set(0.0)

        def matte(path, color, roughness=0.8):
            omni.kit.commands.execute("CreateMdlMaterialPrim", mtl_url="OmniPBR.mdl",
                                      mtl_name="OmniPBR", mtl_path=path)
            sh = UsdShade.Shader(stage.GetPrimAtPath(path + "/Shader"))
            sh.CreateInput("diffuse_color_constant", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
            sh.CreateInput("reflection_roughness_constant", Sdf.ValueTypeNames.Float).Set(roughness)
            sh.CreateInput("metallic_constant", Sdf.ValueTypeNames.Float).Set(0.0)
            return UsdShade.Material(stage.GetPrimAtPath(path))

        # brand colours: cube 0 = green (RGB 187,255,36), cube 1 = near-black; matte
        # materials (unbound prims get the default glossy response and read too shiny)
        for path, color in zip(cube_paths, ((0.733, 1.0, 0.141), (0.02, 0.02, 0.02))):
            cp = stage.GetPrimAtPath(path)
            UsdGeom.Gprim(cp).GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
            m = matte("/World/Looks/CubeMatte" + path.rsplit("/", 1)[-1], color, roughness=0.8)
            UsdShade.MaterialBindingAPI.Apply(cp).Bind(m)

        # high-friction material (cubes + gripper fingers) reduces slip
        UsdShade.Material.Define(stage, "/World/PMat_HF")
        pm = UsdPhysics.MaterialAPI.Apply(stage.GetPrimAtPath("/World/PMat_HF"))
        pm.CreateStaticFrictionAttr(1.5); pm.CreateDynamicFrictionAttr(1.2); pm.CreateRestitutionAttr(0.0)
        for path in cube_paths + ["/World/robot/panda_leftfinger", "/World/robot/panda_rightfinger"]:
            pr = stage.GetPrimAtPath(path)
            if pr.IsValid():
                UsdShade.MaterialBindingAPI.Apply(pr).Bind(
                    UsdShade.Material(stage.GetPrimAtPath("/World/PMat_HF")),
                    UsdShade.Tokens.weakerThanDescendants, "physics")

        # KLT bin (static, hollow triangle-mesh collider)
        binp = stage.DefinePrim("/World/KLT", "Xform")
        binp.GetReferences().AddReference(root + "/Isaac/Props/KLT_Bin/small_KLT_visual_collision.usd")
        bx = UsdGeom.Xformable(binp); pos = Gf.Vec3d(BIN_XY[0], BIN_XY[1], TABLE_H + 0.073)
        tops = [op for op in bx.GetOrderedXformOps() if op.GetOpType() == UsdGeom.XformOp.TypeTranslate]
        (tops[0].Set(pos) if tops else bx.AddTranslateOp().Set(pos))
        for pr in Usd.PrimRange(binp):
            if pr.HasAPI(UsdPhysics.RigidBodyAPI):
                UsdPhysics.RigidBodyAPI(pr).GetRigidBodyEnabledAttr().Set(False)
            if pr.IsA(UsdGeom.Mesh) and pr.HasAPI(UsdPhysics.MeshCollisionAPI):
                UsdPhysics.MeshCollisionAPI(pr).GetApproximationAttr().Set("none")
        # the asset's magenta box texture -> mid-gray matte (labels/stickers keep theirs)
        box_mesh = stage.GetPrimAtPath("/World/KLT/Visuals/FOF_Mesh_Magenta_Box")
        if box_mesh.IsValid():
            UsdShade.MaterialBindingAPI.Apply(box_mesh).Bind(
                matte("/World/Looks/KLTGray", (0.45, 0.45, 0.45), roughness=0.85))

        camera_model = "ZED_X_Nano"
        # ZED X Nano on the wrist + streaming graph
        zed_target = mount_zed_nested(stage, "/World/robot/panda_hand/ZED_X_Rig",
                                      (0.018, 0.0, 0.034), rotate=(0, -90, -180), model=camera_model)
        make_zed_graph(stage, "/World/ZEDGraph", zed_target, 30000, model=camera_model)

        # lighting: kill scene lights, then sublayer the light rig from data/pickplace_lights.usd
        # (edit that file to change the lighting; its /World/* prims merge into the scene)
        for prim in stage.Traverse():
            if prim.HasAPI(UsdLux.LightAPI) or prim.GetTypeName() in (
                "DistantLight", "DomeLight", "RectLight", "SphereLight", "DiskLight",
                "CylinderLight", "GeometryLight"):
                UsdGeom.Imageable(prim).MakeInvisible()
        demo_path = mgr.get_extension_path(mgr.get_enabled_extension_id("sl.sensor.camera.demo"))
        stage.GetRootLayer().subLayerPaths.append(
            (demo_path + "/data/pickplace_lights.usd").replace("\\", "/"))

        # Stereolabs logo decal (transparent background, alpha cutout), laid on the bench front edge
        mat = make_logo_material(stage, demo_path + "/data/sl_logo_alpha.png")
        W, H, X, Yc = 0.74, 0.10, -0.42, 0.08
        pts = [(X, Yc-W/2, TABLE_H), (X, Yc+W/2, TABLE_H), (X, Yc+W/2, TABLE_H+H), (X, Yc-W/2, TABLE_H+H)]
        st = [(1, 0), (0, 0), (0, 1), (1, 1)]
        add_logo_quad(stage, "/World/LogoSign", pts, st, (-1, 0, 0), (0.1, 0.0, 0.331), (0, 90, 0), mat)

        await app_utils.update_app_async(steps=30)

    async def _arm_loop(self) -> None:
        if self._cb is not None:
            SimulationManager.deregister_callback(self._cb)   # drop any previous subscription
            self._cb = None
        if not app_utils.is_playing():
            app_utils.play(); await app_utils.update_app_async(steps=30)
        self._arm.start()
        await app_utils.update_app_async(steps=5)
        self._cb = SimulationManager.register_callback(self._on_step, IsaacEvents.POST_PHYSICS_STEP)

    def _on_step(self, dt, context=None) -> None:
        if self._arm is None:
            return
        try:
            self._arm.step(dt)
        except Exception as e:
            print("[ZED][demo] loop error:", repr(e))

    def stop(self) -> None:
        if self._cb is not None:
            try:
                SimulationManager.deregister_callback(self._cb)
            except Exception:
                pass
            self._cb = None
        if self._arm is not None:
            try:
                self._arm.stop()
            except Exception:
                pass
            self._arm = None
        try:
            app_utils.stop()
        except Exception:
            pass
