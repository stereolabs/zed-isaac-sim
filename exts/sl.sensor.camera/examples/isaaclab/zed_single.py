# ******************************************************************************
# File Name          : zed_single.py
# Description        : Isaac Lab example. Adds a ZED X camera to a scene (optionally
#                      parented to a robot link) and reads stereo RGB + render-based
#                      depth as in-process tensors each step. No ZED SDK.
#
# Render path: Isaac Lab's native Camera sensor (isaaclab.sensors.Camera), which is
# purpose-built to deliver annotator tensors in standalone/headless runs via the normal
# sim.step() render - unlike a raw replicator render product, which does not get driven
# off-screen. Camera paths, intrinsics tables and the script helpers all come from the
# sl.sensor.camera extension (utils / isaaclab_utils) - importable without enabling the
# extension.
#
# Usage (from an Isaac Lab install; rendering must be enabled):
#   # headless (cameras require the renderer to be explicitly enabled):
#   F:\IsaacLab\isaaclab.bat -p exts\sl.sensor.camera\examples\isaaclab\zed_single.py --enable_cameras --resolution SVGA --save_dir F:\zed_lab_out
#   # with a GUI window:
#   F:\IsaacLab\isaaclab.bat -p exts\sl.sensor.camera\examples\isaaclab\zed_single.py --enable_cameras --resolution SVGA --viz kit
#
#   Optional: attach to a robot (point --camera_prim at a path under the robot)
#   ... --robot_usd C:\path\to\robot.usd --camera_prim /World/Robot/wrist/ZED_X
#
# NOTE: the very first rendered frame compiles RTX shaders and can take minutes on a
# cold cache; subsequent runs are fast.
#
# Output: per-step shapes/stats for rgb_left, rgb_right, depth; optional frame dump.
# ******************************************************************************

import argparse
import os
import sys

# The ZED package (sl.sensor.camera) is importable without enabling the Kit extension;
# _bootstrap walks up to the extension root and puts it on sys.path (depth-independent).
_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.isfile(os.path.join(_d, "_bootstrap.py")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
import _bootstrap  # noqa: E402,F401  (adds the sl.sensor.camera extension root to sys.path)

from isaaclab.app import AppLauncher

from sl.sensor.camera.isaaclab_utils import add_zed_cli_args
from sl.sensor.camera.utils import get_resolution

parser = argparse.ArgumentParser(description="Add a ZED X to an Isaac Lab scene and read stereo RGB + ZED depth.")
add_zed_cli_args(parser)
parser.add_argument("--camera_prim", type=str, default="/World/ZED_X",
                    help="Prim path where the ZED USD is referenced (must be the model root).")
parser.add_argument("--robot_usd", type=str, default=None,
                    help="Optional robot USD to reference at /World/Robot (then set --camera_prim under it).")
# Adds --headless, --enable_cameras, --device, and --verbose (gates the per-frame log below).
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()

# --resolution choices are the union over all models; validate the pair.
if get_resolution(args.camera_model, args.resolution) is None:
    parser.error(f"--resolution {args.resolution} is not supported by {args.camera_model}")

# RGB/depth are render-based and this Isaac Lab build is headless-by-default with cameras
# OFF; force rendering on so the script works with or without --enable_cameras.
if not args.enable_cameras:
    print("[ZED] Enabling cameras (--enable_cameras) - required for RGB/depth rendering.")
args.enable_cameras = True

app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

# ---- Everything below runs after the Kit app exists ----
import functools

# Flush prints immediately so progress is visible during the (slow) first render.
print = functools.partial(print, flush=True)

import numpy as np

import isaaclab.sim as sim_utils
from isaaclab.sim import SimulationContext
from isaaclab.sensors import Camera

from sl.sensor.camera.isaaclab_utils import (  # noqa: E402
    depth_to_2d, make_camera_cfg, save_frame, unwrap_output, wait_for_camera_data,
)
from sl.sensor.camera.utils import get_baseline, get_camera_paths, get_camera_usd_path, is_stereo_camera  # noqa: E402

_ZED_USD = get_camera_usd_path(args.camera_model)


def _prop(path, cfg, translation):
    cfg.func(path, cfg, translation=translation)


def build_scene():
    """A small furnished scene so the camera FOV has content at varied depths, plus the
    ZED camera (and optional robot). Purely illustrative - on a real robot the framing
    comes from where the camera is mounted, not from this demo layout."""
    from pxr import UsdGeom, Gf
    import omni.usd

    ground = sim_utils.GroundPlaneCfg()
    ground.func("/World/ground", ground)
    # Dome for ambient fill + a tilted distant "sun" so nothing is crushed to black.
    light = sim_utils.DomeLightCfg(intensity=1500.0, color=(0.85, 0.88, 0.95))
    light.func("/World/Light", light)
    sun = sim_utils.DistantLightCfg(intensity=2500.0, color=(1.0, 1.0, 0.95))
    sun.func("/World/Sun", sun, orientation=(0.924, 0.0, -0.383, 0.0))  # ~45deg down

    def mat(c):
        return sim_utils.PreviewSurfaceCfg(diffuse_color=c)

    # Saturated walls so the color path is unmistakable in the captured image.
    _prop("/World/BackWall", sim_utils.CuboidCfg(size=(0.2, 8.0, 4.0), visual_material=mat((0.85, 0.7, 0.4))), (5.0, 0.0, 2.0))
    _prop("/World/WallL", sim_utils.CuboidCfg(size=(8.0, 0.2, 4.0), visual_material=mat((0.2, 0.75, 0.3))), (3.0, -3.0, 2.0))
    _prop("/World/WallR", sim_utils.CuboidCfg(size=(8.0, 0.2, 4.0), visual_material=mat((0.2, 0.35, 0.9))), (3.0, 3.0, 2.0))
    # A few objects at different distances/heights for stereo + depth structure.
    _prop("/World/Box1", sim_utils.CuboidCfg(size=(0.5, 0.5, 0.9), visual_material=mat((0.1, 0.4, 0.95))), (2.2, 0.7, 0.45))
    _prop("/World/Box2", sim_utils.CuboidCfg(size=(0.4, 0.4, 0.4), visual_material=mat((0.95, 0.35, 0.1))), (1.6, -0.2, 0.2))
    _prop("/World/Ball", sim_utils.SphereCfg(radius=0.35, visual_material=mat((0.9, 0.8, 0.1))), (3.0, -0.8, 0.35))

    if args.robot_usd:
        robot = sim_utils.UsdFileCfg(usd_path=args.robot_usd)
        robot.func("/World/Robot", robot)

    # Reference the ZED model at the requested prim and orient it to face the prop (+X).
    zed = sim_utils.UsdFileCfg(usd_path=_ZED_USD)
    zed.func(args.camera_prim, zed)
    stage = omni.usd.get_context().get_stage()
    xform = UsdGeom.Xformable(stage.GetPrimAtPath(args.camera_prim))
    # The USD's CameraLeft/CameraRight are authored looking +X (up +Z), baseline on Y.
    # So identity orientation already makes them look level down +X at the scene; just
    # lift the model to a sensible height. No rotation, no per-camera pose override -
    # the cameras are used exactly as authored, so the housing stays behind the lenses.
    xform.ClearXformOpOrder()
    xform.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.9))


def main():
    stereo = is_stereo_camera(args.camera_model)
    w, h = get_resolution(args.camera_model, args.resolution)
    # Authored camera prim paths inside the referenced ZED USD.
    paths = get_camera_paths(args.camera_prim, args.camera_model)

    sim = SimulationContext(sim_utils.SimulationCfg(dt=1.0 / 60.0, device=args.device))
    build_scene()

    # Camera sensors attached to the EXISTING USD camera prims (spawn=None).
    cam_left = Camera(make_camera_cfg(paths["left"], args.camera_model, args.resolution,
                                      data_types=["rgb", "distance_to_image_plane"]))
    cam_right = Camera(make_camera_cfg(paths["right"], args.camera_model, args.resolution,
                                       data_types=["rgb"])) if stereo else None

    sim.reset()
    dt = sim.get_physics_dt()
    print(f"[ZED] baseline = {get_baseline(args.camera_model) * 1e-3:.3f} m, stereo = {stereo}, {w}x{h}.")
    print("[ZED] Submitting first render - on a cold RTX shader cache this can take "
          "several minutes (compiling, not hung). Subsequent runs are fast.")

    # Step until the camera annotators deliver populated frames.
    if wait_for_camera_data(sim, [cam_left, cam_right], verbose=args.verbose) < 0:
        simulation_app.close()
        return

    if args.save_dir:
        os.makedirs(args.save_dir, exist_ok=True)

    # Optional ZED Sim2Real camera model on the RGB tensors (same calibrated look as the
    # streaming path). One auto-exposure state, shared by both eyes (left drives, right
    # follows). No-op if the sl_zed_sim2real library is unavailable.
    sim2real = None
    if args.apply_zed_sim2real:
        from sl.sensor.camera.zed_sim2real import ZedSim2Real
        sim2real = ZedSim2Real(num_states=1)
        if not sim2real.ok:
            print("[ZED] --apply_zed_sim2real set but sl_zed_sim2real is unavailable; RGB left unmodified.")

    # Without --save_dir this is a console-only run: stream until the app/window closes
    # (Ctrl-C), ignoring --num_frames. With --save_dir, capture exactly --num_frames.
    run_forever = args.save_dir is None
    if run_forever:
        print("[ZED] No --save_dir -> streaming indefinitely (ignoring --num_frames); stop with Ctrl-C / close the window.")
    i = 0
    while (run_forever or i < args.num_frames) and simulation_app.is_running():
        if sim.is_stopped():  # Kit tearing down: stop before touching released render products
            break
        try:
            sim.step()
            cam_left.update(dt)
            if cam_right is not None:
                cam_right.update(dt)
        except Exception as exc:  # noqa: BLE001 - benign if Kit is tearing down mid-step
            if simulation_app.is_running():
                raise
            print(f"[ZED] Kit shut down mid-step ({type(exc).__name__}) - exiting.")
            break

        rgb_l = unwrap_output(cam_left.data.output, "rgb", index=0)
        rgb_r = unwrap_output(cam_right.data.output, "rgb", index=0) if cam_right is not None else None
        depth = unwrap_output(cam_left.data.output, "distance_to_image_plane", index=0)
        if rgb_l is None or depth is None:
            if args.verbose:
                print(f"  frame {i}: no data this step")
            i += 1
            continue

        # Degrade the RGB in place with the sim2real (left drives auto-exposure, right reuses it).
        if sim2real is not None and sim2real.ok:
            sim2real.apply(rgb_l, scene_lux=args.zed_sim2real_scene_lux, advance=True)
            if rgb_r is not None:
                sim2real.apply(rgb_r, scene_lux=args.zed_sim2real_scene_lux, advance=False)

        d = depth_to_2d(depth)
        # Only pull depth to host when we actually need it (verbose stats or saving).
        d_np = d.detach().cpu().numpy() if (args.verbose or args.save_dir) else None

        if args.verbose:
            valid = np.isfinite(d_np) & (d_np > 0)
            vmin = float(d_np[valid].min()) if valid.any() else float("nan")
            vmax = float(d_np[valid].max()) if valid.any() else float("nan")
            rshape = None if rgb_r is None else tuple(rgb_r.shape)
            print(
                f"  frame {i}: rgb_l {tuple(rgb_l.shape)} | rgb_r {rshape} | "
                f"depth {tuple(d.shape)} [{vmin:.2f}, {vmax:.2f}] m"
            )

        if args.save_dir:
            save_frame(args.save_dir, i, rgb_l, rgb_r, d_np)
        i += 1

    if args.save_dir:
        print(f"[ZED] Saved {i} frame(s) to {args.save_dir}")
    if sim2real is not None:
        sim2real.close()
    simulation_app.close()
    print("[ZED] Done.")


if __name__ == "__main__":
    main()
