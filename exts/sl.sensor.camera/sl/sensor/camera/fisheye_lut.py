"""Lookup textures that render an OpenCV fisheye lens through RTX's OmniLensDistortionLutAPI.

RTX's own OpenCV fisheye schema renders nothing farther than half the image width from the optical
center, which leaves the corners of a ZED X One fisheye black. The lookup-table schema has no such
limit: these textures carry the same lens, computed here from its calibration. Both schemas also
stop at half the camera's legacy `fthetaMaxFov` attribute (200 degrees unless authored), which
optics.py raises to the lens's own field of view.

numpy only (no Kit), so it imports in standalone Isaac Sim / Isaac Lab scripts.
"""
import hashlib
import math
import os
import struct
import tempfile

import numpy as np

# Bump when the texture contents change, so stale cached files are not reused.
_FORMAT_VERSION = 2
_CACHE_DIR = os.path.join(tempfile.gettempdir(), "sl_zed_fisheye_lut")
_THETA_SAMPLES = 400001


def theta_max(k) -> float:
    """Largest field angle in radians the lens model images: where its theta_d stops growing, at most pi.

    A fitted Kannala-Brandt polynomial turns over past the angles its calibration saw, which a real
    lens cannot do; the image corners past that angle are left black.
    """
    theta = np.linspace(0.0, math.pi, _THETA_SAMPLES)
    falling = np.flatnonzero(np.diff(_theta_d(theta, k)) <= 0.0)
    return float(theta[falling[0]]) if falling.size else math.pi


def textures(width, height, fx, fy, cx, cy, k):
    """Paths of the (ray enter direction, ray exit position) EXR textures for a lens, written on first use.

    Args:
        width, height: Image size in pixels; the textures have the same size
        fx, fy, cx, cy: OpenCV intrinsics in pixels, pixel (0, 0) at the center of the first pixel
        k: OpenCV fisheye coefficients k1..k4

    Returns:
        (unproject_path, project_path), forward slashes
    """
    params = (_FORMAT_VERSION, int(width), int(height), *(float(v) for v in (fx, fy, cx, cy, *k)))
    key = hashlib.sha1(repr(params).encode()).hexdigest()[:16]
    paths = [os.path.join(_CACHE_DIR, f"{key}_{name}.exr") for name in ("unproject", "project")]
    if not all(os.path.isfile(p) for p in paths):
        os.makedirs(_CACHE_DIR, exist_ok=True)
        _write_exr(paths[0], ray_directions(width, height, fx, fy, cx, cy, k))
        _write_exr(paths[1], ray_positions(width, height, fx, fy, cx, cy, k))
    return tuple(p.replace("\\", "/") for p in paths)


def ray_directions(width, height, fx, fy, cx, cy, k) -> np.ndarray:
    """Unit view direction of every pixel (height x width x 3), USD camera frame (x right, y up, -z forward).

    Pixels past the lens's largest field angle get (0, 0, 1), which the renderer drops at the `fthetaMaxFov`
    optics.py authors. A dropped pixel shows the dome light as seen straight behind the camera, black without one.
    """
    theta_table = np.linspace(0.0, theta_max(k), _THETA_SAMPLES)
    theta_d_table = _theta_d(theta_table, k)
    # texel centers sit at pixel centers: OpenCV pixel (i, j) is texel (i + 0.5, j + 0.5) / size
    x = (np.arange(width) - cx) / fx
    y = (np.arange(height) - cy) / fy
    x, y = np.meshgrid(x, y)
    r = np.hypot(x, y)
    theta = np.interp(r, theta_d_table, theta_table, right=math.pi)
    sin_r = np.sin(theta) / np.where(r > 0.0, r, 1.0)
    directions = np.stack([x * sin_r, -y * sin_r, -np.cos(theta)], axis=-1)
    directions[theta >= math.pi] = (0.0, 0.0, 1.0)
    return directions.astype(np.float32)


def ray_positions(width, height, fx, fy, cx, cy, k) -> np.ndarray:
    """Image position in [0, 1], from the top-left corner, of every octahedral-encoded view direction (height x width x 2).

    Texel (u, v) in [-1, 1] decodes to a direction in a frame looking down +z with y up, unlike the
    direction texture's -z. The renderer reprojects moving images through this texture; with NVIDIA's
    sample convention (-z) a moving camera renders blurred, with this one it matches RTX's own fisheye.
    Directions the lens does not image map to (-1, -1), off screen.
    """
    u, v = np.meshgrid(np.linspace(-1.0, 1.0, width), np.linspace(-1.0, 1.0, height))
    z = 1.0 - np.abs(u) - np.abs(v)
    back = z <= 0.0
    x = np.where(back, (1.0 - np.abs(v)) * np.where(u >= 0.0, 1.0, -1.0), u)
    y = np.where(back, (1.0 - np.abs(u)) * np.where(v >= 0.0, 1.0, -1.0), v)
    norm = np.sqrt(x * x + y * y + z * z)
    x, y, z = x / norm, y / norm, z / norm
    sin_theta = np.hypot(x, y)
    theta = np.arctan2(sin_theta, z)
    scale = _theta_d(theta, k) / np.where(sin_theta > 0.0, sin_theta, 1.0)
    # +0.5: positions count from the corner of the first pixel, cx and cy from its center
    positions = np.stack([(cx + 0.5 + fx * x * scale) / width, (cy + 0.5 - fy * y * scale) / height], axis=-1)
    positions[theta > theta_max(k)] = (-1.0, -1.0)
    return positions.astype(np.float32)


def _theta_d(theta, k):
    t2 = theta * theta
    return theta * (1.0 + t2 * (k[0] + t2 * (k[1] + t2 * (k[2] + t2 * k[3]))))


def _write_exr(path, image) -> None:
    """Write a float32 image as an uncompressed scanline OpenEXR file (Kit's Python has no EXR writer)."""
    height, width, channels = image.shape
    names = "RGB"[:channels]
    order = sorted(range(channels), key=lambda c: names[c])   # EXR stores channels in name order

    def attribute(name, kind, value):
        return name.encode() + b"\0" + kind.encode() + b"\0" + struct.pack("<i", len(value)) + value

    channel_list = b"".join(names[c].encode() + b"\0" + struct.pack("<iB3xii", 2, 0, 1, 1) for c in order) + b"\0"
    window = struct.pack("<iiii", 0, 0, width - 1, height - 1)
    header = (b"\x76\x2f\x31\x01" + struct.pack("<i", 2)
              + attribute("channels", "chlist", channel_list)
              + attribute("compression", "compression", b"\0")
              + attribute("dataWindow", "box2i", window)
              + attribute("displayWindow", "box2i", window)
              + attribute("lineOrder", "lineOrder", b"\0")
              + attribute("pixelAspectRatio", "float", struct.pack("<f", 1.0))
              + attribute("screenWindowCenter", "v2f", struct.pack("<ff", 0.0, 0.0))
              + attribute("screenWindowWidth", "float", struct.pack("<f", 1.0))
              + b"\0")
    row_bytes = channels * width * 4
    first_row = len(header) + 8 * height
    offsets = first_row + np.arange(height, dtype="<u8") * (8 + row_bytes)
    rows = np.empty((height, 8 + row_bytes), dtype=np.uint8)
    rows[:, :4] = np.arange(height, dtype="<i4").view(np.uint8).reshape(height, 4)
    rows[:, 4:8] = np.frombuffer(struct.pack("<i", row_bytes), dtype=np.uint8)
    pixels = np.ascontiguousarray(image[:, :, order].transpose(0, 2, 1), dtype="<f4")
    rows[:, 8:] = pixels.reshape(height, row_bytes // 4).view(np.uint8)
    # write next to the target and rename, so a concurrent reader never sees half a file
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        f.write(header)
        f.write(offsets.tobytes())
        f.write(rows.tobytes())
    try:
        os.replace(tmp, path)
    except OSError:
        # another process wrote the same lens first and Windows keeps its open file in place
        os.remove(tmp)
        if not os.path.isfile(path):
            raise
