# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""Per-camera auto exposure for a streamed ZED: meter -> controller -> renderer exposure.

Runs on every app update, but meters and steers only when the left render product delivers a
new frame (its hydra-texture frame number), i.e. at the camera rate. One loop per camera: both
eyes get the same exposure, as on the real camera, and the left eye is metered.

The camera behaves like a real ZED X: its auto exposure is the ZED X camera model's
(auto_exposure.py), and exposure:responsivity is authored so that a scene of a given luminance
gets the real camera's exposure time and gain. All edits go to the session
layer and are removed by destroy().
"""
import time

import carb
import omni.kit.app
import omni.usd

from .auto_exposure import AeConfig, AeLimits, RenderExposureActuator, ZedAutoExposure, zedx_responsivity
from .hdr_meter import HdrExposureMeter


class CameraExposureLoop:
    """Auto exposure of one ZED camera.

    Args:
        annotator: HdrColor annotator (device "cuda") attached to the left render product.
        render_product: the left render product object (with ``hydra_texture``).
        camera_paths: camera prims driven together (left, and right for stereo models).
        fps: camera frame rate, sets the frame period (exposure-time ceiling) and the loop step.
        on_apply: optional callback(state) after each exposure update (e.g. the sensor noise,
            which follows the gain).
        view: optional callable returning (1 / the focal length in pixels, or 0 for no lens falloff,
            the white balance gains) of the camera's output, which the meter sees through.
    """

    def __init__(self, annotator, render_product, camera_paths, fps: float, on_apply=None, view=None):
        stage = omni.usd.get_context().get_stage()
        self._hydra = getattr(render_product, "hydra_texture", None)
        rp_path = self._hydra.get_render_product_path() if self._hydra is not None else None
        self.meter = HdrExposureMeter(rp_path, annotator=annotator)
        fstop_attr = stage.GetPrimAtPath(camera_paths[0]).GetAttribute("exposure:fStop")
        fstop = float(fstop_attr.Get()) if fstop_attr and fstop_attr.Get() else 5.0
        config = AeConfig()
        self.actuator = RenderExposureActuator(stage, camera_paths,
                                               responsivity=zedx_responsivity(config.target_mean, fstop))
        self.controller = ZedAutoExposure(AeLimits(fps=float(fps)), config, photometry=self.actuator.photometry())
        self._on_apply = on_apply
        self._view = view
        self._camera = camera_paths[0]
        self._saturated_since = None  # (limit, wall time) while the exposure range binds
        self._warned = set()
        self.actuator.apply(self.controller.state)
        self._sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            self._on_update, name=f"zed_auto_exposure_{camera_paths[0]}")

    @property
    def state(self):
        """Current AeState: exposure_s, analog/digital gain, error_ev, scene_luminance, scene_lux."""
        return self.controller.state

    def _frame_id(self):
        try:
            return self._hydra.get_frame_info().get("frame_number") if self._hydra is not None else None
        except Exception:
            return None

    def _on_update(self, _event):
        try:
            if self._view is not None:
                self.meter.vignette_inv_f, self.meter.wb = self._view()
            state = self.controller.update(self.meter.update(self._frame_id()))
            self.actuator.apply(state)
            if self._on_apply is not None:
                self._on_apply(state)
            self._check_scene_light(state)
        except Exception as exc:  # per-frame: never take the app update down
            carb.log_error(f"[ZED] Auto exposure update failed, stopping it: {exc!r}")
            self.destroy()

    # The exposure range runs out below ~0.3 lux and above ~120,000 lux for an average scene
    # (direct sun is ~100,000 lux). Only a limit held this long is reported.
    _HOLD_S = 2.0

    def _check_scene_light(self, state):
        """Warn once per limit when the scene stays too dark or too bright for a real ZED X.

        Sim scenes often use arbitrary light units (a DistantLight's intensity gives ~pi x that
        in lux, not lux); a camera pinned at its exposure limits usually means the scene's light
        is off by orders of magnitude, and a real camera would show a black or blown-out image.
        """
        limit = state.saturated
        if not limit:
            self._saturated_since = None
            return
        now = time.monotonic()
        if self._saturated_since is None or self._saturated_since[0] != limit:
            self._saturated_since = (limit, now)
            return
        if now - self._saturated_since[1] < self._HOLD_S or limit in self._warned:
            return
        self._warned.add(limit)
        lux = state.scene_lux
        lux_txt = f" (estimated scene illuminance {lux:.3g} lux)" if lux else ""
        if limit == "max":
            carb.log_warn(f"[ZED] {self._camera}: the scene is too dark for a real ZED X{lux_txt}: the camera is at its "
                          "longest exposure and highest gain, so its image is dark and noisy. If this is not meant to be "
                          "a night scene, check the lights' intensities (a DistantLight of intensity I gives ~3.1 x I lux; "
                          "an indoor room is 200-800 lux).")
        else:
            carb.log_warn(f"[ZED] {self._camera}: the scene is too bright for a real ZED X{lux_txt}: the camera is at its "
                          "shortest exposure and lowest gain, so its image is blown out. Check the lights' intensities "
                          "(a DistantLight of intensity I gives ~3.1 x I lux; direct sunlight is ~100,000 lux).")

    def destroy(self):
        self._sub = None
        self._on_apply = None
        if self.actuator is not None:
            self.actuator.release()
            self.actuator = None
        if self.meter is not None:
            self.meter.destroy()
            self.meter = None
