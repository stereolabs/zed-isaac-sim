# ******************************************************************************
# File Name          : zed_depth_standalone.py
# Description        : Standalone script that captures RGB + depth from a ZED
#                      camera using Isaac Sim's renderer (no ZED SDK required).
#
# Usage:
#   # Zero-config: builds a minimal scene and spawns a ZED_X camera
#   ./python.sh exts/sl.sensor.camera/examples/isaac_sim/zed_depth_standalone.py
#
#   # Full control: load your own scene and/or use a camera already placed in it
#   ./python.sh exts/sl.sensor.camera/examples/isaac_sim/zed_depth_standalone.py \
#       --usd_path /path/to/your/scene.usd \
#       --camera_prim /World/ZED_X \
#       --camera_model ZED_X \
#       --resolution HD1200 \
#       --num_frames 10 \
#       --output_dir /tmp/zed_depth
#
# --usd_path omitted   -> a minimal ground + dome-light scene is built.
# --camera_prim omitted -> the ZED model USD is spawned automatically.
#
# On Windows, use python.bat instead of ./python.sh
# For headless rendering (no GUI), add --headless
#
# Output (when --output_dir is set):
#   rgb_000000.png   - left RGB image
#   depth_000000.exr - depth map (float32, meters)
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


# Where the ZED model USD is spawned when --camera_prim is not given.
DEFAULT_CAMERA_PRIM = "/World/ZED_X"
# Default pose for the auto-spawned camera. Authored ZED cameras look +X, so identity
# is horizontal; lift it off the ground and pitch down about +Y so the ground fills the view.
DEFAULT_CAMERA_POSITION_M = (0.0, 0.0, 1.5)  # meters, world frame
DEFAULT_CAMERA_PITCH_DEG = 30.0              # downward tilt about +Y (single axis -> unambiguous)


def parse_args():
    parser = argparse.ArgumentParser(description="Capture RGB + depth from a ZED ZED depth camera")
    parser.add_argument("--usd_path", type=str, default=None,
                        help="Environment USD to load. If omitted, a minimal ground + dome-light scene is built.")
    parser.add_argument("--camera_prim", type=str, default=None,
                        help="Prim path of an existing ZED camera in the scene. "
                             "If omitted, the ZED model USD is spawned at " + DEFAULT_CAMERA_PRIM + ".")
    parser.add_argument("--camera_model", type=str, default="ZED_X",
                        choices=["ZED_X", "ZED_XM", "ZED_X_4MM", "ZED_XM_4MM"],
                        help="ZED camera model")
    parser.add_argument("--resolution", type=str, default="HD1200",
                        choices=["HD1200", "HD1080", "SVGA"],
                        help="Capture resolution")
    parser.add_argument("--num_frames", type=int, default=10, help="Number of frames to capture")
    parser.add_argument("--output_dir", type=str, default=None, help="Directory to save RGB (.png) + depth (.exr)")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    return parser.parse_args()


args = parse_args()

# SimulationApp must be created before any omni imports
from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": args.headless})

import numpy as np
from isaacsim.core.api import World
from isaacsim.core.experimental.objects import DomeLight, GroundPlane
from isaacsim.core.experimental.prims import XformPrim
from isaacsim.core.experimental.utils.stage import add_reference_to_stage, define_prim
from isaacsim.core.experimental.utils.transform import euler_angles_to_quaternion
from isaacsim.core.utils.stage import is_stage_loading, open_stage

from sl.sensor.camera.utils import get_camera_usd_path
from sl.sensor.camera.zed_depth import ZEDDepthCamera


def _build_minimal_scene():
    """Ground plane + dome light, matching NVIDIA's standalone camera example."""
    DomeLight("/World/DomeLight").set_intensities(500)
    GroundPlane("/World/defaultGroundPlane", sizes=100.0)


def _spawn_zed(prim_path):
    """Reference the shipped ZED model USD into the stage at prim_path.

    Uses the authored model (not a bare pinhole) so the stereo intrinsics/baseline
    match real hardware, and places it at a small default pose (see DEFAULT_CAMERA_*).
    Move the prim in the stage, or pass --camera_prim, to use your own placement.
    """
    usd_path = get_camera_usd_path(args.camera_model)
    if usd_path is None:
        return False
    define_prim(prim_path)
    add_reference_to_stage(usd_path, prim_path)
    orientation = euler_angles_to_quaternion(
        np.array([0.0, DEFAULT_CAMERA_PITCH_DEG, 0.0]), degrees=True, extrinsic=False
    ).numpy()
    XformPrim(prim_path, positions=DEFAULT_CAMERA_POSITION_M,
              orientations=orientation, reset_xform_op_properties=True)
    return True


def main():
    # Open the stage before constructing World: World binds to the current stage on
    # creation, so swapping the stage out from under it afterwards leaves it stale.
    if args.usd_path:
        print(f"[Depth] Loading scene: {args.usd_path}")
        open_stage(args.usd_path)
        while is_stage_loading():
            simulation_app.update()
    else:
        print("[Depth] No --usd_path given; building a minimal ground + dome-light scene.")
        _build_minimal_scene()

    # Use the camera already in the scene if --camera_prim is given; otherwise spawn one.
    if args.camera_prim:
        camera_prim = args.camera_prim
    else:
        camera_prim = DEFAULT_CAMERA_PRIM
        print(f"[Depth] No --camera_prim given; spawning {args.camera_model} at {camera_prim}.")
        if not _spawn_zed(camera_prim):
            print(f"[Depth] No USD asset for model '{args.camera_model}'.")
            simulation_app.close()
            sys.exit(1)

    world = World(stage_units_in_meters=1.0)
    world.reset()

    camera = ZEDDepthCamera(
        camera_prim_path=camera_prim,
        camera_model=args.camera_model,
        resolution=args.resolution,
        device="cpu",
    )

    if camera._init_failed:
        print("[Depth] Failed to set up camera. Check prim path and model.")
        camera.destroy()
        simulation_app.close()
        sys.exit(1)

    MAX_INIT_FRAMES = 120
    print(f"[Depth] Stepping simulation, waiting for depth sensor to initialize...")
    for i in range(MAX_INIT_FRAMES):
        world.step(render=True)
        if camera.try_initialize():
            print(f"[Depth] Depth sensor ready after {i + 1} frames")
            break
    else:
        print(f"[Depth] Failed to initialize depth sensor after {MAX_INIT_FRAMES} frames.")
        camera.destroy()
        simulation_app.close()
        sys.exit(1)

    print(f"[Depth] Capturing {args.num_frames} frames...")
    # The render pipeline delivers empty buffers for the first few ticks after the sensor
    # reports ready, so count captured frames (not steps) and allow slack for that warmup.
    WARMUP_SLACK_STEPS = 60
    captured = 0
    for _ in range(args.num_frames + WARMUP_SLACK_STEPS):
        if captured >= args.num_frames:
            break
        world.step(render=True)

        rgba = camera.get_rgba()
        depth = camera.get_depth()
        if rgba is None or depth is None:
            continue

        if hasattr(rgba, "numpy"):
            rgba = rgba.numpy()
        if hasattr(depth, "numpy"):
            depth = depth.numpy()

        if rgba.size == 0 or depth.size == 0:
            continue

        valid_mask = np.isfinite(depth) & (depth > 0)
        valid_depth = depth[valid_mask]
        valid_pct = 100.0 * valid_mask.sum() / depth.size if depth.size > 0 else 0.0
        depth_min = valid_depth.min() if valid_depth.size > 0 else float("nan")
        depth_max = valid_depth.max() if valid_depth.size > 0 else float("nan")

        print(
            f"  Frame {captured}: rgba {rgba.shape} {rgba.dtype} | "
            f"depth {depth.shape} {depth.dtype} [{depth_min:.3f}, {depth_max:.3f}] m "
            f"({valid_pct:.1f}% valid)"
        )

        if args.output_dir:
            camera.save_frame(args.output_dir)
        captured += 1

    if captured < args.num_frames:
        print(f"[Depth] Warning: only captured {captured}/{args.num_frames} frames "
              f"(render pipeline never delivered enough data).")
    if args.output_dir:
        print(f"[Depth] Saved {captured} frames to {args.output_dir}")

    camera.destroy()
    simulation_app.close()
    print("[Depth] Done.")


if __name__ == "__main__":
    main()
