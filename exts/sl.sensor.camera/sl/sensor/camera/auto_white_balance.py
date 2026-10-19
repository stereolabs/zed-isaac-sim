# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""Auto white balance of a real ZED X, for the streamed sRGB image.

The renderer's image is colorimetric: a grey card under a warm lamp comes out orange, under a white
light neutral. A real camera's AWB estimates the light and applies per-channel gains before its colour
processing. The ZED X's comes from the ZED X camera model of the ``sl_zed_sim2real`` library
(camera_model_lib.py): like the real camera, it estimates the light from the near-neutral surfaces of
the image, leaves a warm cast under warm lamps, and settles in about a second after a lighting change.
Gains are relative to green (green gain 1) and applied in linear light before the lens falloff and
the noise.
"""
import ctypes

from . import camera_model_lib


class ZedAutoWhiteBalance:
    """Per-camera AWB state: the real camera's gains and dynamics."""

    def __init__(self):
        self._lib = camera_model_lib.lib()
        self._handle = None
        if self._lib is None:
            raise RuntimeError("the ZED X camera model (sl_zed_sim2real) is unavailable")
        self._handle = self._lib.sl_zed_sim2real_awb_create()
        self.gains = None  # (R, G, B); None until the first metered frame
        self.neutral = (1.0, 1.0)  # (R/G, B/G) a grey comes out at with these gains (selects the near-neutral samples)

    def __del__(self):
        handle, self._handle = getattr(self, "_handle", None), None
        if handle and getattr(self, "_lib", None) is not None:
            self._lib.sl_zed_sim2real_awb_destroy(handle)

    def update_stats(self, stats, dt: float, ae_error_ev: float = 0.0):
        """Advance by one camera frame of ``dt`` seconds from the meter's statistics; returns the gains."""
        from .auto_exposure import stats_to_c

        gains = camera_model_lib.f3((1, 1, 1))
        c = stats_to_c(stats) if stats is not None else None
        self._lib.sl_zed_sim2real_awb_update(self._handle, ctypes.byref(c) if c is not None else None, float(dt),
                                             float(ae_error_ev or 0.0), gains)
        neutral = camera_model_lib.f2((1, 1))
        self._lib.sl_zed_sim2real_awb_get(self._handle, camera_model_lib.f3((1, 1, 1)), neutral)
        self.gains = tuple(float(v) for v in gains)
        self.neutral = tuple(float(v) for v in neutral)
        return self.gains

    def update(self, mean_rgb, dt: float, ae_error_ev: float = 0.0, neutral_rgb=None, neutral_fraction: float = 0.0):
        """Advance by one camera frame of ``dt`` seconds; returns the gains to apply. ``mean_rgb``: the mean
        linear colour of the image, ``neutral_rgb``: of its near-neutral samples (``neutral_fraction`` of them)."""
        stats = camera_model_lib.MeterStats(frame=-1, samples=1, neutral_fraction=float(neutral_fraction or 0.0))
        stats.has_mean_rgb = 1 if mean_rgb is not None else 0
        if mean_rgb is not None:
            stats.mean_rgb = camera_model_lib.d3(mean_rgb)
        stats.has_neutral_rgb = 1 if neutral_rgb is not None else 0
        if neutral_rgb is not None:
            stats.neutral_rgb = camera_model_lib.d3(neutral_rgb)
        return self.update_stats(stats, dt, ae_error_ev)


class CameraWhiteBalanceLoop:
    """Auto white balance of one ZED camera: meters the left eye's HdrColor every camera frame and
    hands the gains to ``on_apply(gains)`` (both eyes share them, as on the real camera).

    Args:
        annotator: HdrColor annotator (device "cuda") attached to the left render product (shared).
        render_product: the left render product object (with ``hydra_texture``).
        fps: camera frame rate (the AWB steps once per camera frame).
        on_apply: callback(gains) after each update.
        ae_error: optional callable returning the auto exposure's current error in EV (the AWB holds
            while the exposure is far off), or None.
    """

    def __init__(self, annotator, render_product, fps: float, on_apply, ae_error=None):
        import omni.kit.app

        from .hdr_meter import HdrExposureMeter

        self._hydra = getattr(render_product, "hydra_texture", None)
        rp_path = self._hydra.get_render_product_path() if self._hydra is not None else None
        self.controller = ZedAutoWhiteBalance()
        self.meter = HdrExposureMeter(rp_path, annotator=annotator)
        self._dt = 1.0 / float(fps or 30)
        self._on_apply = on_apply
        self._ae_error = ae_error
        self._last_frame = None
        self._sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            self._on_update, name="zed_auto_white_balance")

    @property
    def gains(self):
        return self.controller.gains

    def _frame_id(self):
        try:
            return self._hydra.get_frame_info().get("frame_number") if self._hydra is not None else None
        except Exception:
            return None

    def _on_update(self, _event):
        import carb

        try:
            # the near-neutral samples are the ones that come out grey with the current gains
            self.meter.wb = self.controller.gains or (1.0, 1.0, 1.0)
            self.meter.neutral_ref = self.controller.neutral
            stats = self.meter.update(self._frame_id())
            if stats is None or stats.frame == self._last_frame:
                return
            self._last_frame = stats.frame
            ae = self._ae_error() if self._ae_error is not None else 0.0
            gains = self.controller.update_stats(stats, self._dt, ae)
            if self._on_apply is not None:
                self._on_apply(gains)
        except Exception as exc:  # per-frame: never take the app update down
            carb.log_error(f"[ZED] Auto white balance update failed, stopping it: {exc!r}")
            self.destroy()

    def destroy(self):
        self._sub = None
        self._on_apply = None
        if self.meter is not None:
            self.meter.destroy()
            self.meter = None
