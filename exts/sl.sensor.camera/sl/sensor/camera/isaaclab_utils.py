# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""Helpers for using ZED cameras from Isaac Lab standalone scripts.

Everything here works with Isaac Lab's native ``isaaclab.sensors.Camera``
sensor attached to (or spawned to match) the ZED USD's authored cameras:
argument parsing, CameraCfg construction from the ZED spec tables, annotator
output unwrapping, warmup, and frame saving.

Import-safe without a Kit app: only stdlib + numpy at module level. ``torch``,
``cv2`` and ``isaaclab`` are imported lazily inside the functions that need
them, so this module never makes them dependencies of the extension.
"""

import os
from typing import Optional

import numpy as np

from .utils import (
    get_camera_paths,
    get_camera_usd_path,
    get_pinhole_parameters,
    get_supported_models,
    get_supported_resolutions,
)


def add_zed_cli_args(parser, default_model: str = "ZED_X",
                     default_resolution: str = "SVGA", stereo_only: bool = True):
    """Add the ZED demo arguments shared by the example scripts to a parser.

    Adds --camera_model / --resolution (choices derived from the spec tables,
    so new models are picked up automatically), --num_frames and --save_dir.
    Validate the model/resolution pair
    after parsing with ``get_resolution(args.camera_model, args.resolution)``
    (the resolution choices are the union over all models).

    Args:
        parser: an ``argparse.ArgumentParser``
        default_model: default for --camera_model
        default_resolution: default for --resolution
        stereo_only: restrict --camera_model to stereo models

    Returns:
        The parser, for chaining.
    """
    parser.add_argument("--camera_model", type=str, default=default_model,
                        choices=get_supported_models(stereo_only=stereo_only),
                        help="ZED camera model.")
    parser.add_argument("--resolution", type=str, default=default_resolution,
                        choices=get_supported_resolutions(),
                        help="RGB/depth capture resolution.")
    parser.add_argument("--num_frames", type=int, default=10,
                        help="Frames to capture when --save_dir is set; ignored (streams indefinitely) if omitted.")
    parser.add_argument("--save_dir", type=str, default=None,
                        help="Dir to save per-frame stereo+depth. If omitted, streams to console only (no files).")
    parser.add_argument("--apply_zed_sim2real", action="store_true",
                        help="Apply the calibrated ZED Sim2Real camera model to the RGB tensors "
                             "(needs the sl_zed_sim2real library; see zed_sim2real.py).")
    parser.add_argument("--zed_sim2real_scene_lux", type=float, default=0.0,
                        help="Scene illuminance for the sim2real model; <=0 means a bright scene "
                             "(no gain ceiling / noise boost).")
    return parser


def make_camera_cfg(prim_path: str, camera_model: str, camera_resolution: str,
                    data_types=("rgb",), spawn_pinhole: bool = False,
                    clipping_range=(0.03, 20.0), offset=None, update_period: float = 0.0):
    """Build an ``isaaclab.sensors.CameraCfg`` sized from the ZED spec tables.

    Args:
        prim_path: sensor prim path (regex env paths supported by Isaac Lab work).
        camera_model: ZED camera model name.
        camera_resolution: resolution name (e.g. "SVGA").
        data_types: annotators to attach (e.g. ["rgb", "distance_to_image_plane"]).
        spawn_pinhole: False attaches to an EXISTING USD camera prim (spawn=None,
            e.g. the ZED USD's authored CameraLeft/CameraRight); True spawns a new
            pinhole camera with the ZED focal length / aperture (both in mm).
        clipping_range: near/far clip in meters (spawned pinhole only).
        offset: optional ``CameraCfg.OffsetCfg`` mount pose (spawned pinhole only).
        update_period: sensor update period in seconds (0.0 = every step).

    Returns:
        The CameraCfg; wrap it in ``Camera(cfg)`` to create the sensor.

    Raises:
        ValueError: if the resolution is unknown for the camera model.
    """
    import isaaclab.sim as sim_utils
    from isaaclab.sensors import CameraCfg

    params = get_pinhole_parameters(camera_model, camera_resolution)
    if params is None:
        raise ValueError(f"Unknown resolution '{camera_resolution}' for camera model '{camera_model}'")

    spawn = None
    if spawn_pinhole:
        spawn = sim_utils.PinholeCameraCfg(
            focal_length=params["focal_length_mm"],
            horizontal_aperture=params["horizontal_aperture_mm"],
            clipping_range=clipping_range,
        )
    kwargs = dict(prim_path=prim_path, update_period=update_period,
                  height=int(params["height"]), width=int(params["width"]),
                  data_types=list(data_types), spawn=spawn)
    if offset is not None:
        kwargs["offset"] = offset
    return CameraCfg(**kwargs)


def make_stereo_camera_cfgs(prim_base: str, camera_model: str, camera_resolution: str,
                            offset_pos, offset_rot, data_types=("rgb",),
                            depth_on_left: bool = True, **kwargs):
    """Build a (left_cfg, right_cfg) spawned-pinhole pair separated by the ZED baseline.

    Both eyes are spawned pinhole cameras (``make_camera_cfg(spawn_pinhole=True)``)
    so they track a joint-driven robot link via the fabric body pose - a
    ``spawn=None`` camera pointed at prims inside a referenced USD stays frozen at
    the authored pose. The pair is offset by +/-baseline/2 along the mount's local Y
    (the ZED stereo axis), matching the real camera geometry.

    Args:
        prim_base: prim path without the _left/_right suffix
            (e.g. "{ENV_REGEX_NS}/Robot/base/zed").
        camera_model: ZED camera model name.
        camera_resolution: resolution name (e.g. "SVGA").
        offset_pos: (x, y, z) mount position of the stereo center; the pair is
            offset +/-baseline/2 on Y from this point.
        offset_rot: (w, x, y, z) mount rotation, ROS convention.
        data_types: annotators to attach to both eyes (e.g. ["rgb"]).
        depth_on_left: add "distance_to_image_plane" to the left camera's data_types.
        **kwargs: forwarded to :func:`make_camera_cfg` (e.g. clipping_range,
            update_period).

    Returns:
        A (left_cfg, right_cfg) tuple of CameraCfg objects.
    """
    from isaaclab.sensors import CameraCfg

    baseline = get_pinhole_parameters(camera_model, camera_resolution)["baseline_m"]
    x, y, z = offset_pos
    left_types = list(data_types)
    if depth_on_left and "distance_to_image_plane" not in left_types:
        left_types.append("distance_to_image_plane")

    left_cfg = make_camera_cfg(
        f"{prim_base}_left", camera_model, camera_resolution, data_types=left_types,
        spawn_pinhole=True,
        offset=CameraCfg.OffsetCfg(pos=(x, y + baseline / 2.0, z), rot=offset_rot, convention="ros"),
        **kwargs)
    right_cfg = make_camera_cfg(
        f"{prim_base}_right", camera_model, camera_resolution, data_types=list(data_types),
        spawn_pinhole=True,
        offset=CameraCfg.OffsetCfg(pos=(x, y - baseline / 2.0, z), rot=offset_rot, convention="ros"),
        **kwargs)
    return left_cfg, right_cfg


def make_zed_usd_link_mount(zed_prim_path: str, camera_model: str, camera_resolution: str,
                            spawn_init_pos=(0.0, 0.0, 0.0), data_types=("rgb",),
                            depth_on_left: bool = True, mass: float = 0.05):
    """Build the cfgs to mount the real ZED USD model on a robot link and read its cameras.

    Returns ``(model_cfg, left_cam_cfg, right_cam_cfg)``:

    - ``model_cfg`` (``AssetBaseCfg``): the ``ZED_X.usdc`` model spawned as a rigid body at
      ``zed_prim_path``. Pair it with :func:`author_zed_link_joint` (a fixed joint to the link)
      so the model + its authored cameras track the moving link.
    - ``left_cam_cfg`` / ``right_cam_cfg`` (``CameraCfg``): sensors attached (spawn=None) to the
      model's authored ``CameraLeft`` / ``CameraRight`` prims - the real ZED cameras, no pinhole.

    Args:
        zed_prim_path: prim path for the ZED model (e.g. "{ENV_REGEX_NS}/zed"). Its authored
            cameras are at ``get_camera_paths(zed_prim_path, model)``.
        camera_model / camera_resolution: ZED spec selectors.
        spawn_init_pos: initial spawn position (env-local); the fixed joint snaps it to the link.
        data_types: annotators for both eyes; ``depth_on_left`` adds depth to the left eye.
        mass: rigid-body mass (kg); the body is held by the fixed joint, so the value is nominal.
    """
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg

    model_cfg = AssetBaseCfg(
        prim_path=zed_prim_path,
        spawn=sim_utils.UsdFileCfg(
            usd_path=get_camera_usd_path(camera_model),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(),
            mass_props=sim_utils.MassPropertiesCfg(mass=mass)),
        init_state=AssetBaseCfg.InitialStateCfg(pos=tuple(spawn_init_pos)))
    paths = get_camera_paths(zed_prim_path, camera_model)
    left_types = list(data_types)
    if depth_on_left and "distance_to_image_plane" not in left_types:
        left_types.append("distance_to_image_plane")
    left_cfg = make_camera_cfg(paths["left"], camera_model, camera_resolution, data_types=left_types)
    right_cfg = make_camera_cfg(paths["right"], camera_model, camera_resolution, data_types=list(data_types))
    return model_cfg, left_cfg, right_cfg


def author_zed_link_joint(stage, link_prim_path: str, zed_prim_path: str,
                          local_pos, euler_deg, joint_name: str = "fixjoint") -> bool:
    """Author a ``UsdPhysics.FixedJoint`` fixing the ZED rigid body to a robot link.

    Places the ZED at ``local_pos`` (translate) + ``euler_deg`` (``RotateXYZ`` degrees) in the
    link frame - the same placement convention as the Stereolabs Isaac-Sim demo. Idempotent
    and safe if the prim is missing (returns False). Call once per env before physics starts
    (a ``prestartup`` event in manager-based tasks, or before ``sim.reset()`` in standalone).

    Returns True if the joint was authored (or already existed).
    """
    import math
    import torch
    from pxr import Gf, Sdf, UsdPhysics
    from isaaclab.utils.math import quat_from_euler_xyz

    if not stage.GetPrimAtPath(zed_prim_path).IsValid():
        return False
    jpath = Sdf.Path(f"{zed_prim_path}/{joint_name}")
    if stage.GetPrimAtPath(jpath).IsValid():
        return True
    rx, ry, rz = (float(v) * math.pi / 180.0 for v in euler_deg)
    q = quat_from_euler_xyz(torch.tensor(rx), torch.tensor(ry), torch.tensor(rz)).reshape(-1).tolist()
    joint = UsdPhysics.FixedJoint.Define(stage, jpath)
    joint.CreateBody0Rel().SetTargets([link_prim_path])
    joint.CreateBody1Rel().SetTargets([zed_prim_path])
    joint.CreateLocalPos0Attr().Set(Gf.Vec3f(*[float(v) for v in local_pos]))
    joint.CreateLocalRot0Attr().Set(Gf.Quatf(*[float(v) for v in q]))
    joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
    joint.CreateLocalRot1Attr().Set(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
    return True


def unwrap_output(output, key: str, index: Optional[int] = None):
    """Get a torch tensor from ``Camera.data.output[key]``.

    The output values are ProxyArrays; ``.torch`` gives the real tensor.

    Args:
        output: ``camera.data.output`` (may be None).
        key: annotator name, e.g. "rgb" or "distance_to_image_plane".
        index: None returns the full batch (N, H, W, C); an int returns that
            camera/env's frame (H, W, C).

    Returns:
        The tensor, or None if the key is absent or the buffer is empty.
    """
    arr = output.get(key) if output is not None else None
    if arr is None:
        return None
    t = arr.torch if hasattr(arr, "torch") else arr
    if t.numel() == 0:
        return None
    return t if index is None else t[index]


def wait_for_camera_data(sim, cameras, keys=("rgb", "distance_to_image_plane"),
                         max_frames: int = 180, verbose: bool = False) -> int:
    """Step the sim until the first camera's annotators deliver populated frames.

    The first rendered frame compiles RTX shaders and can take minutes on a
    cold cache (compiling, not hung); annotator buffers also take a few frames
    to fill after that.

    Args:
        sim: the ``SimulationContext`` (uses ``sim.step()`` / ``get_physics_dt()``).
        cameras: sensors to update each frame; ``cameras[0]`` is polled for data.
            None entries are skipped.
        keys: annotator outputs that must all be present on ``cameras[0]``.
        max_frames: give up after this many frames.
        verbose: print progress every 10 frames.

    Returns:
        The number of frames stepped, or -1 if data never arrived (usually
        the renderer is off - is --enable_cameras set?).
    """
    cameras = [cam for cam in cameras if cam is not None]
    dt = sim.get_physics_dt()
    for i in range(max_frames):
        sim.step()
        for cam in cameras:
            cam.update(dt)
        if verbose and (i + 1) % 10 == 0:
            print(f"[ZED] warmup frame {i + 1} ...", flush=True)
        if all(unwrap_output(cameras[0].data.output, key) is not None for key in keys):
            print(f"[ZED] Streaming data after {i + 1} frames.", flush=True)
            return i + 1
    print("[ZED] Camera annotators never delivered data (is --enable_cameras set?).", flush=True)
    return -1


def depth_to_2d(depth):
    """Strip a trailing 1-channel: (..., H, W, 1) -> (..., H, W); pass through otherwise.

    Works on numpy arrays and torch tensors; returns None for None.
    """
    if depth is None:
        return None
    if len(depth.shape) >= 3 and depth.shape[-1] == 1:
        return depth[..., 0]
    return depth


def _to_numpy(x):
    if x is None:
        return None
    if hasattr(x, "detach"):  # torch tensor (possibly on GPU)
        x = x.detach().cpu().numpy()
    return np.asarray(x)


def _import_cv2():
    # Some OpenCV builds gate the EXR writer behind this env var.
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    try:
        import cv2
        return cv2
    except ImportError:
        return None


def _write_frame(cv2, out_dir, suffix, left, right, depth):
    """Write one frame's files; numpy fallback when cv2 is unavailable."""
    if cv2 is None:
        np.save(os.path.join(out_dir, f"left_{suffix}.npy"), left)
        if right is not None:
            np.save(os.path.join(out_dir, f"right_{suffix}.npy"), right)
        if depth is not None:
            np.save(os.path.join(out_dir, f"depth_{suffix}.npy"), depth.astype(np.float32))
        return
    cv2.imwrite(os.path.join(out_dir, f"left_{suffix}.png"),
                cv2.cvtColor(left[:, :, :3], cv2.COLOR_RGB2BGR))
    if right is not None:
        cv2.imwrite(os.path.join(out_dir, f"right_{suffix}.png"),
                    cv2.cvtColor(right[:, :, :3], cv2.COLOR_RGB2BGR))
    if depth is not None:
        try:
            cv2.imwrite(os.path.join(out_dir, f"depth_{suffix}.exr"), depth.astype(np.float32))
        except cv2.error:
            np.save(os.path.join(out_dir, f"depth_{suffix}.npy"), depth.astype(np.float32))
            print("[ZED] OpenCV EXR writer unavailable, depth saved as .npy instead.", flush=True)


def save_frame(out_dir: str, index: int, rgb_left, rgb_right=None, depth_2d=None) -> None:
    """Save one frame: left_/right_{index:06d}.png + depth_{index:06d}.exr.

    Accepts torch tensors (CPU or GPU) or numpy arrays; RGB is (H, W, C>=3),
    depth is (H, W) in meters. Falls back to .npy files when cv2 is missing.
    """
    os.makedirs(out_dir, exist_ok=True)
    _write_frame(_import_cv2(), out_dir, f"{index:06d}",
                 _to_numpy(rgb_left), _to_numpy(rgb_right), _to_numpy(depth_2d))


def save_batch_frames(out_dir: str, rgb_left, rgb_right=None, depth_nhw=None,
                      name_fmt: str = "env{:02d}") -> None:
    """Save one file set per batch entry: left_env00.png, depth_env00.exr, ...

    Accepts torch tensors or numpy arrays; RGB is (N, H, W, C>=3), depth is
    (N, H, W) in meters. Falls back to .npy files when cv2 is missing.
    """
    os.makedirs(out_dir, exist_ok=True)
    cv2 = _import_cv2()
    left = _to_numpy(rgb_left)
    right = _to_numpy(rgb_right)
    depth = _to_numpy(depth_nhw)
    for e in range(left.shape[0]):
        _write_frame(cv2, out_dir, name_fmt.format(e),
                     left[e], None if right is None else right[e],
                     None if depth is None else depth[e])
