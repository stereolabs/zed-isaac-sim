# ******************************************************************************
# File Name          : zed_multi_env.py
# Description        : Vectorized Isaac Lab example. Places a ZED X in N environments
#                      and reads batched stereo RGB + render-based depth as
#                      (N, H, W, C) tensors via regex-matched Camera sensors. No ZED SDK.
#
# Why not InteractiveScene's cloner here: in this Isaac Lab build the cloner replicates
# a referenced USD as an instanceable reference, so camera prims embedded inside the
# cloned ZED model are not individually enumerable (only env_0's camera is found). To
# keep using the ZED USD's authored CameraLeft/CameraRight (correct +X / +Z, 0.12 m
# baseline), this script references the ZED USD N times as real (non-instanceable) prims
# laid out in a grid, then attaches a single Camera sensor per eye with a regex prim_path
# matching all envs; the sensor tiles them into one render product and returns (N,H,W,C).
# (`Camera` is the vectorized renderer in this version; TiledCamera is a deprecated alias.)
#
# Usage (rendering must be enabled):
#   F:\IsaacLab\isaaclab.bat -p exts\sl.sensor.camera\examples\isaaclab\zed_multi_env.py --enable_cameras --num_envs 4 --resolution SVGA --save_dir F:\zed_lab_multi
#
# NOTE: the first rendered frame compiles RTX shaders and can take minutes on a cold
# cache; subsequent runs are fast.
# ******************************************************************************

import argparse
import math
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

parser = argparse.ArgumentParser(description="Place a ZED X in N Isaac Lab envs; read batched stereo RGB + depth.")
add_zed_cli_args(parser)
parser.add_argument("--num_envs", type=int, default=4, help="Number of environments (laid out in a grid).")
# AppLauncher adds --verbose (gates the per-frame log below), --enable_cameras, --device, etc.
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

print = functools.partial(print, flush=True)  # flush so progress shows during slow renders

import numpy as np

import isaaclab.sim as sim_utils
from isaaclab.sim import SimulationContext
from isaaclab.sensors import Camera

from sl.sensor.camera.isaaclab_utils import (  # noqa: E402
    depth_to_2d, make_camera_cfg, save_batch_frames, unwrap_output, wait_for_camera_data,
)
from sl.sensor.camera.utils import get_baseline, get_camera_subpaths, get_camera_usd_path, is_stereo_camera  # noqa: E402

_ZED_USD = get_camera_usd_path(args.camera_model)
_STEREO = is_stereo_camera(args.camera_model)
_W, _H = get_resolution(args.camera_model, args.resolution)
# Authored camera subpaths inside the ZED USD (left resolves to Camera for mono models).
_SUBPATHS = get_camera_subpaths(args.camera_model)
# Cameras look straight down, so each env only ever sees its own cell: the ground
# footprint of the ZED X wide FOV from 2 m is ~5.7 x 3.4 m, well under the 5 m pitch.
_ENV_SPACING = 5.0  # meters, grid pitch in X and Y
_CAM_HEIGHT = 2.0  # meters, ZED mount height


def _mat(c):
    return sim_utils.PreviewSurfaceCfg(diffuse_color=c)


def _spawn(path, cfg, translation):
    cfg.func(path, cfg, translation=translation)


def build_scene():
    """Global ground + lights, then N envs in a centered grid. Each env gets its own ZED
    (referenced as a real prim) at _CAM_HEIGHT, looking straight down at a few colored
    objects (see the isolation note on _ENV_SPACING above)."""
    from pxr import UsdGeom, Gf
    import omni.usd

    ground = sim_utils.GroundPlaneCfg()
    ground.func("/World/ground", ground)
    sim_utils.DomeLightCfg(intensity=1500.0, color=(0.85, 0.88, 0.95)).func(
        "/World/Light", sim_utils.DomeLightCfg(intensity=1500.0, color=(0.85, 0.88, 0.95)))
    sim_utils.DistantLightCfg(intensity=2500.0, color=(1.0, 1.0, 0.95)).func(
        "/World/Sun", sim_utils.DistantLightCfg(intensity=2500.0, color=(1.0, 1.0, 0.95)))

    num_cols = math.ceil(math.sqrt(args.num_envs))
    num_rows = math.ceil(args.num_envs / num_cols)

    stage = omni.usd.get_context().get_stage()
    for i in range(args.num_envs):
        # Near-square grid centered on the origin.
        row, col = divmod(i, num_cols)
        ox = (row - (num_rows - 1) / 2.0) * _ENV_SPACING
        oy = (col - (num_cols - 1) / 2.0) * _ENV_SPACING

        # ZED model (real, non-instanceable reference), mounted at _CAM_HEIGHT and pitched
        # 90 deg about Y so the authored +X-looking cameras point straight down.
        zed_path = f"/World/envs/env_{i}/ZED_X"
        zed = sim_utils.UsdFileCfg(usd_path=_ZED_USD)
        zed.func(zed_path, zed)
        xform = UsdGeom.Xformable(stage.GetPrimAtPath(zed_path))
        xform.ClearXformOpOrder()
        xform.AddTranslateOp().Set(Gf.Vec3d(ox, oy, _CAM_HEIGHT))
        xform.AddRotateXYZOp().Set(Gf.Vec3f(0.0, 90.0, 0.0))

        # A few colored objects under this env's camera.
        b = f"/World/envs/env_{i}"
        _spawn(f"{b}/Box1", sim_utils.CuboidCfg(size=(0.5, 0.5, 0.9), visual_material=_mat((0.1, 0.4, 0.95))), (ox + 0.6, oy + 0.9, 0.45))
        _spawn(f"{b}/Box2", sim_utils.CuboidCfg(size=(0.4, 0.4, 0.4), visual_material=_mat((0.95, 0.35, 0.1))), (ox - 0.5, oy - 0.6, 0.2))
        _spawn(f"{b}/Ball", sim_utils.SphereCfg(radius=0.35, visual_material=_mat((0.9, 0.8, 0.1))), (ox + 0.4, oy - 1.0, 0.35))


def _make_regex_camera(eye, data_types):
    """One Camera sensor whose regex prim_path matches that eye across all envs."""
    return Camera(make_camera_cfg(
        prim_path=f"/World/envs/env_.*/ZED_X/{_SUBPATHS[eye]}",
        camera_model=args.camera_model, camera_resolution=args.resolution,
        data_types=data_types,
    ))


def main():
    sim = SimulationContext(sim_utils.SimulationCfg(dt=1.0 / 60.0, device=args.device))
    build_scene()

    cam_left = _make_regex_camera("left", ["rgb", "distance_to_image_plane"])
    cam_right = _make_regex_camera("right", ["rgb"]) if _STEREO else None

    sim.reset()
    dt = sim.get_physics_dt()
    print(f"[ZED] {args.num_envs} envs, baseline = {get_baseline(args.camera_model) * 1e-3:.3f} m, "
          f"stereo = {_STEREO}, {_W}x{_H}.")
    print("[ZED] Submitting first render - on a cold RTX shader cache this can take several "
          "minutes (compiling, not hung). Subsequent runs are fast.")

    if wait_for_camera_data(sim, [cam_left, cam_right], verbose=args.verbose) < 0:
        simulation_app.close()
        return
    print(f"[ZED] rgb batch = {tuple(unwrap_output(cam_left.data.output, 'rgb').shape)}")

    if args.save_dir:
        os.makedirs(args.save_dir, exist_ok=True)

    # Optional ZED Sim2Real camera model, one independent auto-exposure state per env (both
    # eyes of an env share it: left drives, right follows). No-op if sl_zed_sim2real is
    # unavailable. The engine's GPU scratch is reused across envs, so memory stays flat.
    sim2real = None
    if args.apply_zed_sim2real:
        from sl.sensor.camera.zed_sim2real import ZedSim2Real
        sim2real = ZedSim2Real(num_states=args.num_envs)
        if not sim2real.ok:
            print("[ZED] --apply_zed_sim2real set but sl_zed_sim2real is unavailable; RGB left unmodified.")

    # Without --save_dir this is a console-only run: stream until the app/window closes
    # (Ctrl-C), ignoring --num_frames. With --save_dir, capture --num_frames (saving one
    # frame per env on the first good step).
    run_forever = args.save_dir is None
    if run_forever:
        print("[ZED] No --save_dir: streaming indefinitely (ignoring --num_frames); stop with Ctrl-C / close the window.")
    saved = False
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

        rgb_l = unwrap_output(cam_left.data.output, "rgb")                        # (N, H, W, 3)
        rgb_r = unwrap_output(cam_right.data.output, "rgb") if cam_right else None
        depth = unwrap_output(cam_left.data.output, "distance_to_image_plane")     # (N, H, W, 1)
        if rgb_l is None or depth is None:
            if args.verbose:
                print(f"  frame {i}: no data this step")
            i += 1
            continue

        # Degrade every env's RGB in place with the sim2real (per-env exposure; right follows left).
        if sim2real is not None and sim2real.ok:
            sim2real.apply(rgb_l, scene_lux=args.zed_sim2real_scene_lux, advance=True)
            if rgb_r is not None:
                sim2real.apply(rgb_r, scene_lux=args.zed_sim2real_scene_lux, advance=False)

        # Only pull depth to host when we actually need it (verbose stats or saving).
        d = depth_to_2d(depth).detach().cpu().numpy() if (args.verbose or args.save_dir) else None  # (N, H, W)

        if args.verbose:
            valid = np.isfinite(d) & (d > 0)
            per_env = " ".join(f"env{e}:{100.0 * valid[e].mean():.0f}%" for e in range(d.shape[0]))
            print(f"  frame {i}: rgb_l {tuple(rgb_l.shape)} | "
                  f"rgb_r {None if rgb_r is None else tuple(rgb_r.shape)} | "
                  f"depth {tuple(depth.shape)} | valid[{per_env}]")

        if args.save_dir and not saved:
            save_batch_frames(args.save_dir, rgb_l, rgb_r, d)
            saved = True
        i += 1

    if args.save_dir:
        print(f"[ZED] Saved one frame per env to {args.save_dir}")
    if sim2real is not None:
        sim2real.close()
    simulation_app.close()
    print("[ZED] Done.")


if __name__ == "__main__":
    main()
