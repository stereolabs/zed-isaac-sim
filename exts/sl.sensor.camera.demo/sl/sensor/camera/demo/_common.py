"""Shared scene-building helpers for the Stereolabs ZED warehouse demos.

Everything here runs at scene-build time inside Isaac Sim (Kit is loaded), so Kit/USD imports at module scope are fine.

Asset paths and stereo/mono selection come from the core `sl.sensor.camera` ext (its `utils` module
imports without Kit and is guaranteed loaded first via the extension dependency), so the demos never
hardcode `data/usd/*.usdc` paths or the `ZED_Camera` vs `ZED_Camera_One` split.
"""
from __future__ import annotations

import omni.kit.commands
import omni.graph.core as og
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, Gf, Sdf

from sl.sensor.camera.utils import (get_camera_model, get_camera_usd_path,
                                     get_lens_type, get_lens_variant, is_stereo_camera)


def _asset(model: str) -> str:
    """Absolute ZED USD path for a model, normalised to forward slashes for USD references."""
    path = get_camera_usd_path(model)
    return path.replace("\\", "/") if path else path


def _select_lens(stage, ref_prim_path: str, model: str) -> None:
    """Select the 'lens' variant matching `model` on a referenced shared-body ZED asset.

    No-op for single-lens assets (no variant mapping / no 'lens' variantSet).
    """
    variant = get_lens_variant(model)
    if not variant:
        return
    model_prim = stage.GetPrimAtPath(ref_prim_path + "/base_link/" + get_camera_model(model))
    if model_prim and model_prim.IsValid():
        vsets = model_prim.GetVariantSets()
        if "lens" in vsets.GetNames():
            vsets.GetVariantSet("lens").SetVariantSelection(variant)


# ---------------- streaming graph ----------------

def make_zed_graph(stage, graph_path, cam_path, port, *, model="ZED_X", res="SVGA", fps=30,
                   sim2real_ae_target=-1.0):
    """Author an `OnPlaybackTick -> ZED_*` streaming graph targeting `cam_path` on `port`.

    Stereo models use the `ZED_Camera` node (`inputs:cameraPrim`); mono models (ZED X One) use
    `ZED_Camera_One` (`inputs:leftCameraPrim`). The split is derived from the camera spec, not
    hardcoded, so the humanoid's mixed ZED Mini + ZED X One rig works from one call site.

    sim2real_ae_target overrides the camera model's AE set-point (median display luma 0..1)
    for this stream when the ZED Sim2Real toggle is on; <=0 keeps the calibrated default.
    """
    stereo = is_stereo_camera(model)
    node_type = "sl.sensor.camera.ZED_Camera" if stereo else "sl.sensor.camera.ZED_Camera_One"
    rel_attr = "inputs:cameraPrim" if stereo else "inputs:leftCameraPrim"
    keys = og.Controller.Keys
    og.Controller.edit(
        {"graph_path": graph_path, "evaluator_name": "execution"},
        {keys.CREATE_NODES: [("OnTick", "omni.graph.action.OnPlaybackTick"), ("ZED", node_type)],
         keys.SET_VALUES: [("ZED.inputs:cameraModel", get_camera_model(model)),
                           ("ZED.inputs:lensType", get_lens_type(model).value),
                           ("ZED.inputs:resolution", res),
                           ("ZED.inputs:fps", fps), ("ZED.inputs:streamingPort", port),
                           ("ZED.inputs:zedSim2RealAeTarget", float(sim2real_ae_target))],
         keys.CONNECT: [("OnTick.outputs:tick", "ZED.inputs:execIn")]})
    stage.GetPrimAtPath(graph_path + "/ZED").GetRelationship(rel_attr).SetTargets([Sdf.Path(cam_path)])
    # Select the matching 'lens' variant on the target so the node (which now derives
    # model+lens from the asset) streams the intended lens even if the caller mounted
    # the asset without going through mount_zed_*. No-op for single-lens models.
    _select_lens(stage, cam_path, model)


# ---------------- Stereolabs logo decals ----------------

def make_logo_material(stage, logo_png, mtl_path="/World/Looks/LogoMat"):
    """OmniPBR material with the Stereolabs logo as an alpha-cutout decal. Returns `mtl_path`."""
    omni.kit.commands.execute("CreateMdlMaterialPrim", mtl_url="OmniPBR.mdl",
                              mtl_name="OmniPBR", mtl_path=mtl_path)
    sh = UsdShade.Shader(stage.GetPrimAtPath(mtl_path + "/Shader"))
    sh.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(logo_png))
    sh.CreateInput("enable_opacity", Sdf.ValueTypeNames.Bool).Set(True)
    sh.CreateInput("enable_opacity_texture", Sdf.ValueTypeNames.Bool).Set(True)
    sh.CreateInput("opacity_texture", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(logo_png))
    sh.CreateInput("opacity_mode", Sdf.ValueTypeNames.Int).Set(0)
    sh.CreateInput("opacity_threshold", Sdf.ValueTypeNames.Float).Set(0.5)
    return mtl_path


def add_logo_quad(stage, path, points, st, normal, translate, rotate, mtl_path):
    """Define a single double-sided textured quad bound to `mtl_path`."""
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr([Gf.Vec3f(*p) for p in points])
    m.CreateFaceVertexCountsAttr([4]); m.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    m.CreateNormalsAttr([Gf.Vec3f(*normal)] * 4); m.SetNormalsInterpolation("vertex")
    m.CreateDoubleSidedAttr(True)
    stp = UsdGeom.PrimvarsAPI(m).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, "faceVarying")
    stp.Set([Gf.Vec2f(*uv) for uv in st])
    mxf = UsdGeom.Xformable(m.GetPrim())
    mxf.AddTranslateOp().Set(Gf.Vec3d(*translate)); mxf.AddRotateXYZOp().Set(Gf.Vec3f(*rotate))
    UsdShade.MaterialBindingAPI.Apply(m.GetPrim())
    UsdShade.MaterialBindingAPI(m.GetPrim()).Bind(UsdShade.Material(stage.GetPrimAtPath(mtl_path)))
    return m


def add_floor_logos(stage, demo_path, placements, *, w=1.5, h=0.201, z=0.01, rot_z=90.0,
                    mtl_path="/World/Looks/LogoMat"):
    """Lay flat Stereolabs floor decals at each (x, y) in `placements` (humanoid + amr aisle)."""
    logo = demo_path + "/data/sl_logo_alpha.png"
    make_logo_material(stage, logo, mtl_path)
    points = [(-w/2, -h/2, 0), (w/2, -h/2, 0), (w/2, h/2, 0), (-w/2, h/2, 0)]
    st = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for i, (lx, ly) in enumerate(placements):
        add_logo_quad(stage, f"/World/LogoSign_{i}", points, st, (0, 0, 1),
                      (lx, ly, z), (0, 0, rot_z), mtl_path)


# ---------------- physics ground ----------------

def add_physics_ground(stage, path, *, scale, friction, z=-0.5):
    """Invisible high-friction collider slab under the robot. Returns the Cube."""
    gp = UsdGeom.Cube.Define(stage, path); gp.GetSizeAttr().Set(1.0)
    gxf = UsdGeom.Xformable(gp.GetPrim())
    gxf.AddTranslateOp().Set(Gf.Vec3d(0, 0, z)); gxf.AddScaleOp().Set(Gf.Vec3f(scale, scale, 1.0))
    UsdPhysics.CollisionAPI.Apply(gp.GetPrim())
    gm = UsdShade.Material.Define(stage, path + "/PhysMat")
    pm = UsdPhysics.MaterialAPI.Apply(gm.GetPrim())
    pm.CreateStaticFrictionAttr().Set(friction)
    pm.CreateDynamicFrictionAttr().Set(friction)
    pm.CreateRestitutionAttr().Set(0.0)
    UsdShade.MaterialBindingAPI.Apply(gp.GetPrim()).Bind(
        gm, UsdShade.Tokens.weakerThanDescendants, "physics")
    UsdGeom.Imageable(gp.GetPrim()).MakeInvisible()
    return gp


# ---------------- camera rig mounting ----------------

def mount_zed_nested(stage, rig_path, translate, *, rotate=None, orient=None, model="ZED_X"):
    """Nest a ZED model under a robot link as a passive viewpoint (pick-place wrist, AMR deck).

    Creates `rig_path` (Xform placed by translate + rotate/orient), references the ZED asset at
    `rig_path/ZED_X`, and DISABLES (never removes) the asset's authored rigid body + collision so it
    rides the parent link without perturbing physics - and so the ZED's IMU still resolves in the
    physics-tensor view (see the demo memory on disable-not-remove). Returns the ZED asset-root path
    (the streaming target).
    """
    rig = stage.DefinePrim(rig_path, "Xform"); xf = UsdGeom.Xformable(rig)
    xf.AddTranslateOp().Set(Gf.Vec3d(*translate))
    if orient is not None:
        xf.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(
            Gf.Quatd(orient[0], Gf.Vec3d(orient[1], orient[2], orient[3])))
    elif rotate is not None:
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*rotate))
    cam_path = rig_path + "/" + model
    zedx = stage.DefinePrim(cam_path, "Xform")
    zedx.GetReferences().AddReference(_asset(model))
    _select_lens(stage, cam_path, model)
    for pr in Usd.PrimRange(zedx):
        if pr.HasAPI(UsdPhysics.RigidBodyAPI):
            UsdPhysics.RigidBodyAPI(pr).CreateRigidBodyEnabledAttr().Set(False)
        if pr.HasAPI(UsdPhysics.CollisionAPI):
            UsdPhysics.CollisionAPI(pr).GetCollisionEnabledAttr().Set(False)
    return cam_path


def mount_zed_fixedjoint(stage, cam_path, link_path, link_world, *, model, pos, quat, mass=0.1):
    """Mount a ZED as a light rigid body fixed-jointed to a moving link (H1 head rig).

    Places the ZED at its baked head-relative pose (composed against `link_world`), applies a light
    rigid body + nominal inertia, disables collision, and authors a `UsdPhysics.FixedJoint` back to
    `link_path` (excluded from the articulation) so the camera and its IMU ride the link cleanly
    without destabilising a balancing robot. Returns `cam_path` (the streaming target).
    """
    rel = Gf.Matrix4d(1.0)
    rel.SetRotateOnly(Gf.Quatd(quat[0], Gf.Vec3d(quat[1], quat[2], quat[3])))
    rel.SetTranslateOnly(Gf.Vec3d(*pos))
    wpose = Gf.Transform(rel * link_world)
    cam = stage.DefinePrim(cam_path, "Xform")
    cam.GetReferences().AddReference(_asset(model))
    _select_lens(stage, cam_path, model)
    cxf = UsdGeom.Xformable(cam)
    cxf.ClearXformOpOrder()   # asset root ships its own xformOps; override them
    cxf.AddTranslateOp().Set(wpose.GetTranslation())
    cxf.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(wpose.GetRotation().GetQuat())
    body = next((p for p in Usd.PrimRange(cam) if p.HasAPI(UsdPhysics.RigidBodyAPI)), cam)
    UsdPhysics.RigidBodyAPI.Apply(body).CreateRigidBodyEnabledAttr(True)
    mm = UsdPhysics.MassAPI.Apply(body)
    mm.CreateMassAttr(mass); mm.CreateDiagonalInertiaAttr(Gf.Vec3f(0.001, 0.001, 0.001))
    for pr in Usd.PrimRange(cam):
        if pr.HasAPI(UsdPhysics.CollisionAPI):
            UsdPhysics.CollisionAPI(pr).CreateCollisionEnabledAttr(False)
    j = UsdPhysics.FixedJoint.Define(stage, cam_path + "/FixedJointToLink")
    j.CreateBody0Rel().SetTargets([link_path])
    j.CreateBody1Rel().SetTargets([body.GetPath()])
    j.CreateLocalPos0Attr(Gf.Vec3f(*pos))
    j.CreateLocalRot0Attr(Gf.Quatf(quat[0], Gf.Vec3f(quat[1], quat[2], quat[3])))
    j.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0)); j.CreateLocalRot1Attr(Gf.Quatf(1, 0, 0, 0))
    try:
        j.CreateExcludeFromArticulationAttr(True)
    except Exception:
        pass
    return cam_path
