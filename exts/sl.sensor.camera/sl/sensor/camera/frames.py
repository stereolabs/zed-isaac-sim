"""Turn captured camera buffers into files on disk.

Used by the ZED Capture node (``zed_depth``) and the Isaac Lab tensor helpers
(``isaaclab_utils``). Callers own the file names - the two paths name their frames differently
on purpose - and this module owns the encoding, the fallbacks and the array plumbing.

:class:`CapturedFrame` and the writer protocol let a caller send a capture somewhere other than
numbered PNGs without ``zed_depth`` knowing where: a writer owns the naming, whether to write a
given frame at all, and any sidecar it keeps.

stdlib + numpy only, so it imports in standalone Isaac Sim / Isaac Lab scripts.
"""
from __future__ import annotations

import os
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import numpy as np

try:
    import carb
    _log_warn = carb.log_warn
    _log_error = carb.log_error
except ImportError:
    import logging
    _log_warn = logging.getLogger(__name__).warning
    _log_error = logging.getLogger(__name__).error

_warned_no_cv2 = False


def import_cv2():
    """OpenCV, or None when it is not installed.

    Sets OPENCV_IO_ENABLE_OPENEXR before the import: some builds register the EXR codec only
    when it is set, and ``imwrite`` on a .exr then returns False rather than raising.
    """
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    try:
        import cv2
        return cv2
    except ImportError:
        return None


def to_numpy(array):
    """A numpy view of a torch tensor (CPU or GPU), a warp array, or a numpy array."""
    if array is None:
        return None
    if hasattr(array, "detach"):        # torch tensor, possibly on the GPU
        array = array.detach().cpu().numpy()
    elif hasattr(array, "numpy"):       # warp array from a replicator annotator
        array = array.numpy()
    return np.asarray(array)


def depth_to_2d(depth):
    """Strip a trailing 1-channel: (..., H, W, 1) -> (..., H, W); pass through otherwise."""
    if depth is None:
        return None
    if len(depth.shape) >= 3 and depth.shape[-1] == 1:
        return depth[..., 0]
    return depth


def write_rgb(path: str, rgba) -> None:
    """Write an (H, W, C>=3) RGB(A) buffer as PNG. Alpha is dropped."""
    rgb = to_numpy(rgba)[:, :, :3]
    cv2 = import_cv2()
    if cv2 is None:
        from PIL import Image
        Image.fromarray(rgb).save(path)
        return
    cv2.imwrite(path, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def write_depth(path_stem: str, depth) -> str:
    """Write an (H, W) float depth map in meters as ``<path_stem>.exr``, PIZ-compressed (lossless).

    Falls back to ``<path_stem>.npy`` when OpenCV is missing or its EXR writer is unavailable,
    warning once. Returns the path written.
    """
    global _warned_no_cv2
    array = to_numpy(depth_to_2d(depth)).astype(np.float32)
    cv2 = import_cv2()
    if cv2 is not None:
        # PIZ over OpenCV's default ZIP: faster and smaller on depth maps. Builds without the
        # flag write their default.
        params = ([cv2.IMWRITE_EXR_COMPRESSION, cv2.IMWRITE_EXR_COMPRESSION_PIZ]
                  if hasattr(cv2, "IMWRITE_EXR_COMPRESSION_PIZ") else [])
        try:
            if cv2.imwrite(path_stem + ".exr", array, params):
                return path_stem + ".exr"
            reason = "the OpenCV EXR writer is unavailable"
        except cv2.error:
            reason = "the OpenCV EXR writer failed"
    else:
        reason = "OpenCV is not installed"
    np.save(path_stem + ".npy", array)
    if not _warned_no_cv2:
        _warned_no_cv2 = True
        _log_warn(f"[ZED] Depth saved as .npy instead of .exr: {reason}.")
    return path_stem + ".npy"


@dataclass
class CapturedFrame:
    """One rendered frame, as handed to a :class:`FrameWriter`.

    ``sim_time`` and ``view_transform`` describe the frame that was rendered, not the stage as
    it stands now, and are only filled in when the writer asks for them (``needs_pose``).
    """

    index: int
    output_dir: str
    left: Any
    right: Optional[Any] = None
    depth: Optional[Any] = None
    sim_time: float = 0.0
    view_transform: Optional[Sequence[float]] = None


class FrameWriter:
    """Where a capture goes. Subclass to send frames somewhere other than numbered PNGs.

    ``needs_pose`` asks the capture for the rendered frame's simulation time and camera
    transform, which costs two extra annotators on the render product.

    ``owns_output_dir`` says the writer resolves the output folder itself, so the capture hands
    over the path it was given untouched instead of putting a timestamped folder under it.
    """

    needs_pose = False
    owns_output_dir = False

    def write(self, frame: CapturedFrame) -> bool:
        """Consume one frame. Return False to skip it, leaving the frame index unspent."""
        raise NotImplementedError

    def close(self) -> None:
        """Finish the recording. Called once, on capture teardown."""


class PngFrameWriter(FrameWriter):
    """Numbered PNG frames, with the depth map as EXR next to them.

    Each file is encoded on a pool of ``workers`` threads (OpenCV releases the GIL while it
    encodes), so ``write()`` returns once the frame is queued and ``close()`` waits for every
    file. ``write()`` blocks while ``max_pending`` files are queued: a capture that outpaces the
    encoders slows the app down rather than dropping frames. A file that fails to write is
    logged and keeps its index.
    """

    def __init__(self, workers: Optional[int] = None, max_pending: Optional[int] = None):
        self._workers = workers or min(8, max(2, (os.cpu_count() or 4) // 2))
        self._max_pending = max_pending or 2 * self._workers
        self._pool = None
        self._slots = None

    def write(self, frame: CapturedFrame) -> bool:
        os.makedirs(frame.output_dir, exist_ok=True)
        self._submit(write_rgb, os.path.join(frame.output_dir, f"rgb_left_{frame.index:06d}.png"), frame.left)
        if frame.depth is not None:
            self._submit(write_depth, os.path.join(frame.output_dir, f"depth_{frame.index:06d}"), frame.depth)
        if frame.right is not None:
            self._submit(write_rgb, os.path.join(frame.output_dir, f"rgb_right_{frame.index:06d}.png"), frame.right)
        return True

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True)
            self._pool = None

    def _submit(self, write, path, array) -> None:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(self._workers, thread_name_prefix="zed_frame_writer")
            self._slots = threading.BoundedSemaphore(self._max_pending)
        # A copy: annotator buffers (get_data without do_array_copy) are reused by the next frame.
        array = np.array(to_numpy(array), copy=True)
        self._slots.acquire()
        self._pool.submit(self._write_file, write, path, array)

    def _write_file(self, write, path, array) -> None:
        try:
            write(path, array)
        except Exception:
            _log_error(f"[ZED] Writing {path} failed:\n{traceback.format_exc()}")
        finally:
            self._slots.release()
