"""Stereolabs ZED Warehouse Pick-Place demo.

Registers an Isaac Examples entry. "Load & Run" builds a warehouse pick-and-place cell (Franka on a
wood bench, 2 cubes, a KLT bin, studio lighting) with a wrist-mounted ZED X streaming to the ZED
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

from ._common import make_zed_graph, mount_zed_nested, make_logo_material, add_logo_quad
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
CUBE_PATHS = ["/World/Cube", "/World/Cube_1"]


class ZedPickPlaceDemo:
    """Builds the scene and runs the pick-place loop; owns the Examples-browser UI."""

    def __init__(self) -> None:
        self._cb = None
        self._pp = None
        self._cubes = None
        self._state = None
        self._status = None

    # ---------------- UI ----------------
    def build_ui(self) -> None:
        with ui.VStack(spacing=8, height=0):
            ui.Label("Stereolabs ZED X on Robotic Arm", height=0,
                     style={"font_size": 18})
            ui.Label("A ZED X camera wrist-mounted on the Franka pick-and-place robotic arm",
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
        print(f"[ZED demo] {msg}")

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
        wrot = stage.DefinePrim("/World/WarehouseRot", "Xform")
        UsdGeom.Xformable(wrot).AddRotateXYZOp().Set(Gf.Vec3f(0, 0, 180))
        stage.DefinePrim("/World/WarehouseRot/WH", "Xform").GetReferences().AddReference(
            root + "/Isaac/Environments/Simple_Warehouse/warehouse.usd")
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

        # Franka pick-place on the bench
        from isaacsim.robot.experimental.manipulators.examples.franka import FrankaPickPlace
        from isaacsim.core.experimental.objects import Cube
        from isaacsim.core.experimental.prims import GeomPrim, RigidPrim
        pp = FrankaPickPlace(events_dt=[90, 60, 30, 60, 120, 30, 40])
        pp.setup_scene()
        self._pp = pp
        pp.robot.set_world_poses(positions=[0.0, 0.0, TABLE_H], orientations=[1.0, 0.0, 0.0, 0.0])
        pp.target_position = np.array(BIN_TARGET)
        pp.cube_initial_position = np.array([0.50, -0.15, Z0])

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

        # 2 cubes
        cs = np.array([0.0515, 0.0515, 0.0515])
        pp.cube.set_world_poses(positions=[0.50, -0.15, Z0])
        c1 = Cube(paths="/World/Cube_1", positions=np.array([0.48, 0.12, Z0]),
                  orientations=np.array([1, 0, 0, 0]), sizes=1.0, scales=cs, colors="gray")
        GeomPrim(paths=c1.paths, apply_collision_apis=True); RigidPrim(paths=c1.paths)
        # brand colours: cube 0 = green (RGB 187,255,36), cube 1 = near-black; matte
        # materials (unbound prims get the default glossy response and read too shiny)
        for path, color in (("/World/Cube", (0.733, 1.0, 0.141)), ("/World/Cube_1", (0.02, 0.02, 0.02))):
            cp = stage.GetPrimAtPath(path)
            UsdGeom.Gprim(cp).GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
            m = matte("/World/Looks/CubeMatte" + path.rsplit("/", 1)[-1], color, roughness=0.8)
            UsdShade.MaterialBindingAPI.Apply(cp).Bind(m)

        # high-friction material (cubes + gripper fingers) reduces slip
        UsdShade.Material.Define(stage, "/World/PMat_HF")
        pm = UsdPhysics.MaterialAPI.Apply(stage.GetPrimAtPath("/World/PMat_HF"))
        pm.CreateStaticFrictionAttr(1.5); pm.CreateDynamicFrictionAttr(1.2); pm.CreateRestitutionAttr(0.0)
        for path in CUBE_PATHS + ["/World/robot/panda_leftfinger", "/World/robot/panda_rightfinger"]:
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
        # ZED X on the wrist + streaming graph
        zed_target = mount_zed_nested(stage, "/World/robot/panda_hand/ZED_X_Rig",
                                      (0.018, 0.0, 0.034), rotate=(0, -90, -180), model=camera_model)
        # raise the camera model's AE set-point in this scene so toggling ZED Sim2Real
        # doesn't step the brightness so hard vs the (bright) raw viewport tone mapping
        make_zed_graph(stage, "/World/ZEDGraph", zed_target, 30000, sim2real_ae_target=0.62, model=camera_model)

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
        from isaacsim.core.experimental.prims import RigidPrim
        self.stop()  # drop any previous subscription
        stage = omni.usd.get_context().get_stage()
        self._cubes = [{"rigid": RigidPrim(p),
                        "img": UsdGeom.Imageable(stage.GetPrimAtPath(p)),
                        "path": p} for p in CUBE_PATHS]
        if not app_utils.is_playing():
            app_utils.play(); await app_utils.update_app_async(steps=30)
        self._pp.reset_robot()
        await app_utils.update_app_async(steps=5)
        self._state = {"phase": "run", "timer": 0, "idx": self._choose()}
        self._cb = SimulationManager.register_callback(self._on_step, IsaacEvents.POST_PHYSICS_STEP)

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

    def _on_step(self, dt, context=None) -> None:
        pp, S = self._pp, self._state
        try:
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
        except Exception as e:
            print("[ZED demo] loop error:", repr(e))

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
