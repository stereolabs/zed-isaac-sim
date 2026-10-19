# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""GPU exposure meter on a render product's linear HDR color.

A real ZED meters the image it captures (reflected light), picks exposure time and gain
from that, and derives SCENE_ILLUMINANCE as a by-product. This module is the metering
half of that loop for a simulated camera: it hands the render product's ``HdrColor`` AOV
(pre-tonemap, linear) to the ZED X camera model's meter (``sl_zed_sim2real``,
camera_model_lib.py), which reduces it on the GPU to the few hundred bytes of statistics
the auto exposure and white balance need.

Real-time constraints drive the design:
- zero-copy: the annotator hands over a view of the renderer's buffer;
- no full-frame readback: only the statistics leave the GPU;
- no stall: results are read back asynchronously and consumed one update later (a real
  AE also acts on the previous frame), so ``update()`` never waits on the GPU.
"""
import ctypes
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import warp as wp

from . import camera_model_lib


@dataclass
class ExposureStats:
    """Metering result for one frame. Luminances are in renderer units."""

    frame: int
    samples: int
    dark_fraction: float           # samples with zero / invalid luminance
    mean_luminance: float          # arithmetic mean over lit samples
    log2_mean: float               # log2 of the geometric mean
    log2_median: float
    log2_p01: float
    log2_p99: float
    histogram: np.ndarray = field(repr=False)
    mean_rgb: Optional[tuple] = None  # mean linear (R, G, B) of the white balance samples, None if none
    mean_encoded: Optional[float] = None  # mean encoded (sRGB) luma of the camera's output, all samples
    clip_fraction: Optional[float] = None  # share of the samples clipped in the camera's output
    neutral_rgb: Optional[tuple] = None  # mean linear (R, G, B) of the near-neutral samples, None if none
    neutral_fraction: Optional[float] = None  # their share of the white balance samples
    _c: object = field(default=None, repr=False, compare=False)  # the camera model's own copy

    @staticmethod
    def from_c(c) -> "ExposureStats":
        copy = camera_model_lib.MeterStats()
        ctypes.pointer(copy)[0] = c
        return ExposureStats(int(c.frame), int(c.samples), float(c.dark_fraction), float(c.mean_luminance),
                             float(c.log2_mean), float(c.log2_median), float(c.log2_p01), float(c.log2_p99),
                             np.ctypeslib.as_array(copy.histogram).copy(),
                             mean_rgb=tuple(float(v) for v in c.mean_rgb) if c.has_mean_rgb else None,
                             mean_encoded=float(c.mean_encoded), clip_fraction=float(c.clip_fraction),
                             neutral_rgb=tuple(float(v) for v in c.neutral_rgb) if c.has_neutral_rgb else None,
                             neutral_fraction=float(c.neutral_fraction), _c=copy)


class HdrExposureMeter:
    """Meters one render product's HdrColor on the GPU.

    Args:
        render_product_path: render product to attach to (e.g. a ZED left eye).
        stride: sample every ``stride``-th pixel in x and y (8 -> 36k samples at 1920x1200).
        roi: optional (x0, y0, x1, y1) in normalized [0, 1] image coordinates, like the
            SDK's AEC_AGC_ROI. Defaults to the full frame.
        device: CUDA device holding the render product.
        annotator: an HdrColor annotator (device "cuda") already attached to the render product,
            e.g. the one feeding the sRGB stream encoder; it is shared, never detached here.
            None attaches a private one.
    """

    def __init__(self, render_product_path: str, stride: int = 8, roi=None, device: str = "cuda:0",
                 annotator=None):
        self._lib = camera_model_lib.lib()
        self._handle = None
        if self._lib is None:
            raise RuntimeError("the ZED X camera model (sl_zed_sim2real) is unavailable")
        self.render_product_path = render_product_path
        self.stride = max(1, int(stride))
        self.roi = roi
        self.device = wp.get_device(device)
        self.latest: Optional[ExposureStats] = None
        # the camera the output statistics see through, set by the loops before each update: 1 / the focal
        # length in pixels for the lens falloff (0 = none), the white balance gains, and the colour a grey
        # comes out at (for the near-neutral samples)
        self.vignette_inv_f = 0.0
        self.wb = (1.0, 1.0, 1.0)
        self.neutral_ref = (1.0, 1.0)

        self._owns_annot = annotator is None
        if self._owns_annot:
            import omni.replicator.core as rep

            annotator = rep.AnnotatorRegistry.get_annotator("HdrColor", device="cuda", do_array_copy=False)
            annotator.attach([render_product_path])
        self._annot = annotator
        self._handle = self._lib.sl_zed_sim2real_meter_create(self.stride)
        self._stats = camera_model_lib.MeterStats()
        self._latest_frame = None

    def _view(self, data) -> Optional[wp.array]:
        """Return the annotator output as an (H, W, C) Warp array, or None if not ready."""
        if isinstance(data, dict):
            data = data.get("data")
        if data is None or not hasattr(data, "shape") or data.size == 0:
            return None
        if not isinstance(data, wp.array):
            data = wp.array(np.ascontiguousarray(data), device=self.device)
        if data.ndim == 3:
            return data
        # Vector dtype (e.g. vec4h) over (H, W): reinterpret the same memory as scalars.
        if data.ndim == 2 and hasattr(data.dtype, "_length_"):
            scalar = data.dtype._wp_scalar_type_
            return wp.array(ptr=data.ptr, dtype=scalar, shape=(*data.shape, data.dtype._length_),
                            device=data.device, copy=False)
        return None

    def update(self, frame_id: Optional[int] = None) -> Optional[ExposureStats]:
        """Meter the current frame; return the most recent completed statistics.

        Never blocks on the GPU: the returned stats are from the previous call whose
        copy has finished (normally one update old). Pass the render product's frame
        number as ``frame_id`` to skip app updates that delivered no new camera frame
        (the app usually updates faster than the camera's tick rate); stats then carry
        that frame number.
        """
        img = self._view(self._annot.get_data(device="cuda")) if self._annot is not None else None
        image = None
        if img is not None and img.shape[2] >= 3 and img.dtype in (wp.float16, wp.float32):
            eb = 2 if img.dtype == wp.float16 else 4
            image = camera_model_lib.MeterImage(img.ptr, int(img.strides[0]), int(img.strides[1]), eb,
                                                int(img.shape[1]), int(img.shape[0]))
        view = camera_model_lib.MeterView(float(self.vignette_inv_f or 0.0), camera_model_lib.f3(self.wb),
                                          camera_model_lib.f2(self.neutral_ref),
                                          camera_model_lib.f4(self.roi or (0.0, 0.0, 0.0, 0.0)))
        stream = wp.get_stream(img.device if img is not None else self.device).cuda_stream
        fid = -1 if frame_id is None else int(frame_id)
        if self._lib.sl_zed_sim2real_meter_update(self._handle, ctypes.byref(image) if image is not None else None,
                                                  ctypes.byref(view), fid, stream, ctypes.byref(self._stats)):
            if self._latest_frame != (self._stats.frame, self._stats.samples) or self.latest is None:
                self.latest = ExposureStats.from_c(self._stats)
                self._latest_frame = (self._stats.frame, self._stats.samples)
        return self.latest

    def wait(self) -> None:
        """Wait for the queued metering (a capture that needs its first result at once)."""
        if self._handle:
            self._lib.sl_zed_sim2real_meter_wait(self._handle)

    def destroy(self) -> None:
        if self._annot is not None and self._owns_annot:
            try:
                self._annot.detach([self.render_product_path])
            except Exception:
                pass
        self._annot = None
        handle, self._handle = self._handle, None
        if handle:
            self._lib.sl_zed_sim2real_meter_destroy(handle)

    def __del__(self):
        handle, self._handle = getattr(self, "_handle", None), None
        if handle and getattr(self, "_lib", None) is not None:
            self._lib.sl_zed_sim2real_meter_destroy(handle)
