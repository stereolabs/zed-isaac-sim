# ******************************************************************************
# File Name          : zed_depth_example.py
# Description        : Captures RGB + depth from a ZED camera using Isaac Sim's
#                      renderer (no ZED SDK required).
#
# Usage:
#   1. Open Isaac Sim and load a scene containing a ZED X or ZED X Mini camera.
#   2. Adjust CAMERA_PRIM_PATH, CAMERA_MODEL, and RESOLUTION below.
#   3. Open this file in the Script Editor and execute it.
#   4. Press PLAY. RGB + depth will be captured every CAPTURE_INTERVAL frames.
#   5. Press STOP to clean up.
#
# Set SAVE_DIR to a path to save RGB (.png) and depth (.exr) to disk.
# ******************************************************************************

import numpy as np
import omni.timeline
import omni.physx as _physx

from sl.sensor.camera.zed_depth import ZEDDepthCamera

# =============================================================================
#  CONFIG
# =============================================================================
CAMERA_PRIM_PATH = "/World/ZED_X"
CAMERA_MODEL = "ZED_X"          # ZED_X, ZED_XM, ZED_X_4MM, ZED_XM_4MM
RESOLUTION = "HD1200"           # HD1200, HD1080, SVGA
CAPTURE_INTERVAL = 60           # capture every N physics steps
SAVE_DIR = ""                   # set to a path to enable saving (e.g. "/tmp/zed_depth")

# =============================================================================
#  STATE
# =============================================================================
_camera = None
_step_count = 0
_physics_sub = None
_timeline_sub = None


def _on_physics_step(dt):
    global _step_count
    if _camera is None:
        return

    if not _camera.is_valid():
        _camera.try_initialize()
        return

    _step_count += 1
    if _step_count % CAPTURE_INTERVAL != 0:
        return

    rgba = _camera.get_rgba()
    depth = _camera.get_depth()

    if rgba is None or depth is None:
        print(f"[Depth] Step {_step_count}: waiting for first frame...")
        return

    if hasattr(rgba, 'numpy'):
        rgba = rgba.numpy()
    if hasattr(depth, 'numpy'):
        depth = depth.numpy()

    valid_depth = depth[np.isfinite(depth)]
    depth_min = valid_depth.min() if valid_depth.size > 0 else float('nan')
    depth_max = valid_depth.max() if valid_depth.size > 0 else float('nan')

    print(
        f"[Depth] Step {_step_count}: "
        f"rgba {rgba.shape} {rgba.dtype} | "
        f"depth {depth.shape} {depth.dtype} "
        f"range [{depth_min:.3f}, {depth_max:.3f}] m"
    )

    if SAVE_DIR:
        _camera.save_frame(SAVE_DIR)


def _on_timeline_event(event):
    global _camera, _step_count, _physics_sub
    if event.type == int(omni.timeline.TimelineEventType.PLAY):
        _step_count = 0
        _camera = ZEDDepthCamera(
            camera_prim_path=CAMERA_PRIM_PATH,
            camera_model=CAMERA_MODEL,
            resolution=RESOLUTION,
            device="cpu",
        )
        if _camera._init_failed:
            print("[Depth] Failed to set up. Check CAMERA_PRIM_PATH and camera model.")
            _camera = None
            return

        print(f"[Depth] Camera created, waiting for render pipeline...")
        if SAVE_DIR:
            print(f"[Depth] Will save to {SAVE_DIR}")

        _physics_sub = _physx.get_physx_interface().subscribe_physics_step_events(_on_physics_step)

    elif event.type == int(omni.timeline.TimelineEventType.STOP):
        if _physics_sub is not None:
            _physics_sub.unsubscribe()
            _physics_sub = None
        if _camera is not None:
            _camera.destroy()
            _camera = None
        print("[Depth] Cleaned up.")


# =============================================================================
#  ENTRY POINT
# =============================================================================
timeline = omni.timeline.get_timeline_interface()
_timeline_sub = timeline.get_timeline_event_stream().create_subscription_to_pop(_on_timeline_event)
print("[Depth] Script loaded. Press PLAY to start capturing.")
