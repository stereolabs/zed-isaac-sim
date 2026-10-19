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

Frame writing and the camera optics come from ``frames`` and ``optics``, shared with the
ZED Capture node.
"""

import os
from typing import Optional

from .frames import depth_to_2d, to_numpy, write_depth, write_rgb  # noqa: F401 (re-exported)
from .utils import (
    get_camera_paths,
    get_camera_usd_path,
    get_pinhole_parameters,
    get_supported_models,
    get_supported_resolutions,
)


def add_zed_cli_args(parser, default_model: str = "ZED_X",
                     default_resolution: str = "SVGA", stereo_only: bool = True,
                     capture: bool = True, sim2real: bool = True):
    """Add the ZED demo arguments shared by the example scripts to a parser.

    Adds --camera_model / --resolution (choices derived from the spec tables,
    so new models are picked up automatically), and the --num_frames / --save_dir
    and --apply_zed_sim2real options a script can turn off when it does not use them.
    Validate the model/resolution pair
    after parsing with ``get_resolution(args.camera_model, args.resolution)``
    (the resolution choices are the union over all models).

    Args:
        parser: an ``argparse.ArgumentParser``
        default_model: default for --camera_model
        default_resolution: default for --resolution
        stereo_only: restrict --camera_model to stereo models
        capture: add --num_frames and --save_dir
        sim2real: add --apply_zed_sim2real

    Returns:
        The parser, for chaining.
    """
    parser.add_argument("--camera_model", type=str, default=default_model,
                        choices=get_supported_models(stereo_only=stereo_only),
                        help="ZED camera model.")
    parser.add_argument("--resolution", type=str, default=default_resolution,
                        choices=get_supported_resolutions(),
                        help="RGB/depth capture resolution.")
    if capture:
        parser.add_argument("--num_frames", type=int, default=10,
                            help="Frames to capture when --save_dir is set; ignored (streams indefinitely) if omitted.")
        parser.add_argument("--save_dir", type=str, default=None,
                            help="Dir to save per-frame stereo+depth. If omitted, streams to console only (no files).")
    if sim2real:
        parser.add_argument("--apply_zed_sim2real", action="store_true",
                            help="Apply ZED Sim2Real, the ZED X camera model, to the RGB tensors: the cameras "
                                 "render HDR (rgb_hdr) and get the real camera's auto exposure, white balance, "
                                 "noise, vignetting and sharpness (needs the sl_zed_sim2real library; see "
                                 "zed_sim2real.py).")
    return parser


# Kit extensions the ZED cameras need that Isaac Lab's apps do not start: the lens is authored with
# the OmniLensDistortion USD schema, which full Isaac Sim loads through its RTX sensor extensions. A
# schema extension only registers its schemas when it starts with the app, so enabling it from the
# script is too late.
_KIT_EXTENSIONS = ("omni.usd.schema.omni_lens_distortion",)


def add_zed_kit_args(args):
    """Have ``AppLauncher(args)`` start the Kit extensions the ZED cameras need.

    Call on the parsed arguments, before ``AppLauncher(args)``. Keeps any ``--kit_args`` given.

    Returns:
        ``args``, for chaining.
    """
    kit_args = (getattr(args, "kit_args", None) or "").split()
    for ext in _KIT_EXTENSIONS:
        if ext not in kit_args:
            kit_args += ["--enable", ext]
    args.kit_args = " ".join(kit_args)
    return args


def make_camera_cfg(prim_path: str, camera_model: str, camera_resolution: str,
                    data_types=("rgb",), update_period: float = 0.0):
    """Build an ``isaaclab.sensors.CameraCfg`` for a ZED USD's authored camera prim.

    The sensor attaches to the existing prim (``spawn=None``) - the real ZED camera, with its
    real baseline - so pair it with :func:`apply_zed_optics`. Sized from the ZED spec tables.

    Args:
        prim_path: sensor prim path (regex env paths supported by Isaac Lab work).
        camera_model: ZED camera model name.
        camera_resolution: resolution name (e.g. "SVGA").
        data_types: annotators to attach (e.g. ["rgb", "distance_to_image_plane"]).
        update_period: sensor update period in seconds (0.0 = every step).

    Returns:
        The CameraCfg; wrap it in ``Camera(cfg)`` to create the sensor.

    Raises:
        ValueError: if the resolution is unknown for the camera model.
    """
    from isaaclab.sensors import CameraCfg

    params = get_pinhole_parameters(camera_model, camera_resolution)
    if params is None:
        raise ValueError(f"Unknown resolution '{camera_resolution}' for camera model '{camera_model}'")

    return CameraCfg(prim_path=prim_path, update_period=update_period,
                     height=int(params["height"]), width=int(params["width"]),
                     data_types=list(data_types), spawn=None)


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


def apply_zed_optics(stage, zed_prim_path: str, camera_model: str, camera_resolution: str) -> bool:
    """Author the ZED model's optics on the authored cameras of a ZED USD placed in the stage.

    The assets ship one nominal lens for every variant, so the prims need the model's real focal
    length and lens; this is the same call the streaming and capture paths make
    (``optics.apply_camera_optics``).

    Call once the ZED USD is on the stage and before the ``Camera`` sensors initialize - Isaac Lab
    reads focal length and aperture off the prim when the sensor starts, so authoring afterwards
    changes the image but not the reported intrinsics.

    Args:
        stage: the USD stage holding the placed ZED.
        zed_prim_path: prim path the ZED USD was referenced at (one env; not a regex).
        camera_model / camera_resolution: ZED spec selectors.

    Returns:
        True if every camera of the model was authored.
    """
    from .optics import apply_camera_optics   # pxr; kept out of this module's import-time deps

    paths = get_camera_paths(zed_prim_path, camera_model)
    eyes = [paths[key] for key in ("left", "right") if key in paths]
    authored = True
    for path in eyes:
        prim = stage.GetPrimAtPath(path)
        if not prim.IsValid():
            print(f"[ZED] No camera prim at {path}; its optics are left as authored.")
            authored = False
            continue
        authored = apply_camera_optics(prim, camera_model, camera_resolution) and authored
    return authored


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
    from isaaclab.utils.math import quat_from_euler_xyz

    from .mounting import author_fixed_joint

    rx, ry, rz = (float(v) * math.pi / 180.0 for v in euler_deg)
    # Isaac Lab returns (x, y, z, w); author_fixed_joint takes (w, x, y, z).
    x, y, z, w = quat_from_euler_xyz(torch.tensor(rx), torch.tensor(ry), torch.tensor(rz)).reshape(-1).tolist()
    return author_fixed_joint(stage, link_prim_path, zed_prim_path, local_pos, (w, x, y, z),
                              joint_name=joint_name)


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


def _write_set(out_dir: str, suffix: str, left, right, depth) -> None:
    """One frame's files: left_/right_<suffix>.png + depth_<suffix>.exr."""
    write_rgb(os.path.join(out_dir, f"left_{suffix}.png"), left)
    if right is not None:
        write_rgb(os.path.join(out_dir, f"right_{suffix}.png"), right)
    if depth is not None:
        write_depth(os.path.join(out_dir, f"depth_{suffix}"), depth)


def save_frame(out_dir: str, index: int, rgb_left, rgb_right=None, depth_2d=None) -> None:
    """Save one frame: left_/right_{index:06d}.png + depth_{index:06d}.exr.

    Accepts torch tensors (CPU or GPU) or numpy arrays; RGB is (H, W, C>=3),
    depth is (H, W) in meters. Written by the shared writer in ``frames``.
    """
    os.makedirs(out_dir, exist_ok=True)
    _write_set(out_dir, f"{index:06d}", rgb_left, rgb_right, depth_2d)


def save_batch_frames(out_dir: str, rgb_left, rgb_right=None, depth_nhw=None,
                      name_fmt: str = "env{:02d}") -> None:
    """Save one file set per batch entry: left_env00.png, depth_env00.exr, ...

    Accepts torch tensors or numpy arrays; RGB is (N, H, W, C>=3), depth is
    (N, H, W) in meters.
    """
    os.makedirs(out_dir, exist_ok=True)
    left = to_numpy(rgb_left)
    right = to_numpy(rgb_right)
    depth = to_numpy(depth_nhw)
    for e in range(left.shape[0]):
        _write_set(out_dir, name_fmt.format(e), left[e],
                   None if right is None else right[e],
                   None if depth is None else depth[e])
