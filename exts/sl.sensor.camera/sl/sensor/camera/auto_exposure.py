# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""ZED-like auto exposure driven by the exposure meter.

Closes the loop the real camera runs: meter the captured signal -> choose exposure time
and gain -> the next frames are captured with them. Here the "sensor" is the RTX render
product: ``HdrColor`` already includes the per-camera exposure (``exposure:time``,
``exposure:iso``), so the meter sees what a sensor would, and the actuator writes those two
attributes on both eyes. Stereo eyes share one state, as on the real camera.

The controller is the real ZED X's (how it splits exposure between time and gain, its ranges and
its dynamics), from the ZED X camera model of the ``sl_zed_sim2real`` library (camera_model_lib.py);
``ZedAutoExposure`` wraps it. ``RenderExposureActuator`` is the only part that touches USD.

Photometric calibration of the renderer (grey card, Isaac 6.0 / Kit 110.1, Real-Time 2.0,
measured against the path-traced illuminance AOV):

    HdrColor = K * L[cd/m^2] * t * (iso / 100) / fStop^2 * responsivity

with K = 1.000 (distant light), 0.987 (sphere light), 0.956 (dome light: Real-Time 2.0
renders environment light ~4 % below the path tracer). A UsdLux DistantLight of intensity I
delivers 3.116 * I lux (~pi * I, independent of its angle); sphere/dome intensities are nits as
UsdLux defines. Creating a render product authors exposure:time 0.02, fStop 5, responsivity
1.1027 on the camera, so these must be read from the prim, not assumed.
"""
import ctypes
import math
from dataclasses import dataclass
from typing import Optional, Sequence

from . import camera_model_lib

RTX_SIGNAL_PER_NIT = 0.99       # K above, direct-light dominated scenes (+-1 %; dome-lit -3.5 %)
MEAN_REFLECTANCE = 0.18         # reflected-light metering assumption ("18 % grey")

# The ZED SDK's documented ranges, used only when the camera model is unavailable (the model
# carries the real camera's own ranges).
_SDK_EXPOSURE_MIN_S = 28e-6
_SDK_ANALOG_GAIN_MDB = (1000.0, 16000.0)
_SDK_DIGITAL_GAIN = (1.0, 256.0)
_FALLBACK_IMAGE_LEVEL = 0.18


def zedx_image_level() -> float:
    """The real ZED X's linear image level: the auto exposure's default target."""
    lib = camera_model_lib.lib()
    return float(lib.sl_zed_sim2real_ae_image_level()) if lib is not None else _FALLBACK_IMAGE_LEVEL


def zedx_responsivity(target_mean: float, fstop: float = 5.0) -> float:
    """exposure:responsivity making the sim ZED X choose the real camera's exposure x gain."""
    lib = camera_model_lib.lib()
    if lib is None:
        return 1.0
    return float(lib.sl_zed_sim2real_responsivity(float(target_mean), float(fstop)))


@dataclass
class Photometry:
    """Converts the metered signal to luminance for a given total exposure (t x gain)."""

    fstop: float = 5.0
    responsivity: float = 1.0
    iso_base: float = 100.0
    k: float = RTX_SIGNAL_PER_NIT

    def signal_per_nit(self, total_exposure_s: float) -> float:
        return self.k * total_exposure_s * (self.iso_base / 100.0) / self.fstop ** 2 * self.responsivity

    def nits(self, signal: float, total_exposure_s: float) -> float:
        return signal / self.signal_per_nit(total_exposure_s)

    @staticmethod
    def lux_from_nits(nits: float, reflectance: float = MEAN_REFLECTANCE) -> float:
        """Reflected-light estimate E = pi * L / rho: what a camera ISP can infer."""
        return math.pi * nits / reflectance


def _default_limits(fps: float):
    lib = camera_model_lib.lib()
    if lib is None:
        return camera_model_lib.AeLimitsC(fps=fps, exposure_min_s=_SDK_EXPOSURE_MIN_S,
                                          analog_gain_mdb=camera_model_lib.d2(_SDK_ANALOG_GAIN_MDB),
                                          digital_gain=camera_model_lib.d2(_SDK_DIGITAL_GAIN))
    out = camera_model_lib.AeLimitsC()
    lib.sl_zed_sim2real_ae_default_limits(float(fps), ctypes.byref(out))
    return out


@dataclass
class AeLimits:
    """Actuator ranges. Fields left None take the real ZED X's (the camera model's) at ``fps``:
    exposure from 28 us up to the frame period, and its analog and digital gain ranges."""

    fps: float = 30.0
    exposure_min_s: Optional[float] = None
    exposure_max_s: Optional[float] = None  # None -> frame period, 1 / fps
    analog_gain_mdb: Optional[Sequence[float]] = None
    digital_gain: Optional[Sequence[float]] = None
    # "zedx": the real camera's split of each EV between time and gain; "time_first": classic priority.
    allocation: str = "zedx"

    def __post_init__(self):
        if self.exposure_min_s is None or self.analog_gain_mdb is None or self.digital_gain is None:
            defaults = _default_limits(self.fps)
            if self.exposure_min_s is None:
                self.exposure_min_s = float(defaults.exposure_min_s)
            if self.analog_gain_mdb is None:
                self.analog_gain_mdb = tuple(float(v) for v in defaults.analog_gain_mdb)
            if self.digital_gain is None:
                self.digital_gain = tuple(float(v) for v in defaults.digital_gain)

    def to_c(self):
        return camera_model_lib.AeLimitsC(
            fps=float(self.fps), exposure_min_s=float(self.exposure_min_s),
            exposure_max_s=float(self.exposure_max_s or 0.0), analog_gain_mdb=camera_model_lib.d2(self.analog_gain_mdb),
            digital_gain=camera_model_lib.d2(self.digital_gain), allocation=0 if self.allocation == "zedx" else 1)


@dataclass
class AeConfig:
    """Controller settings a caller may change: the target linear image level (a receiver's
    EXPOSURE_COMPENSATION scales it). None = the real camera's."""

    target_mean: Optional[float] = None

    def __post_init__(self):
        if self.target_mean is None:
            self.target_mean = zedx_image_level()


_SATURATED = {0: "", 1: "min", 2: "max"}


@dataclass
class AeState:
    exposure_s: float
    analog_gain: float
    digital_gain: float
    error_ev: float = 0.0
    converged: bool = False
    saturated: str = ""             # "", "min" or "max" when the ranges bind
    scene_luminance: Optional[float] = None  # metered mean luminance, cd/m^2 (exposure-independent)
    frame: int = -1

    @property
    def total(self) -> float:
        return self.exposure_s * self.analog_gain * self.digital_gain

    @property
    def scene_lux(self) -> Optional[float]:
        """Reflected-light illuminance estimate, like the SDK's SCENE_ILLUMINANCE (x10 there)."""
        return None if self.scene_luminance is None else Photometry.lux_from_nits(self.scene_luminance)

    @property
    def analog_gain_mdb(self) -> float:
        return 20000.0 * math.log10(self.analog_gain)

    @staticmethod
    def from_c(c) -> "AeState":
        return AeState(float(c.exposure_s), float(c.analog_gain), float(c.digital_gain), error_ev=float(c.error_ev),
                       converged=bool(c.converged), saturated=_SATURATED.get(int(c.saturated), ""), frame=int(c.frame))


def stats_to_c(stats):
    """The meter statistics as the camera model takes them (ExposureStats, or any object with its fields)."""
    if isinstance(stats, camera_model_lib.MeterStats):
        return stats
    c = getattr(stats, "_c", None)  # ExposureStats keeps the camera model's own
    if c is not None:
        return c
    c = camera_model_lib.MeterStats()
    c.frame = int(getattr(stats, "frame", -1))
    c.samples = int(getattr(stats, "samples", 0))
    for name in ("dark_fraction", "mean_luminance", "log2_mean", "log2_median", "log2_p01", "log2_p99",
                 "mean_encoded", "clip_fraction", "neutral_fraction"):
        value = getattr(stats, name, None)
        setattr(c, name, float(value) if value is not None else 0.0)
    for name in ("mean_rgb", "neutral_rgb"):
        value = getattr(stats, name, None)
        setattr(c, "has_" + name, 1 if value is not None else 0)
        if value is not None:
            setattr(c, name, camera_model_lib.d3(value))
    return c


class ZedAutoExposure:
    """The real ZED X's auto exposure. Feed it the meter's ExposureStats once per new camera frame."""

    def __init__(self, limits: AeLimits = None, config: AeConfig = None,
                 initial_exposure_s: Optional[float] = None, photometry: Photometry = None):
        self._lib = camera_model_lib.lib()
        self._handle = None
        if self._lib is None:
            raise RuntimeError("the ZED X camera model (sl_zed_sim2real) is unavailable")
        self.limits = limits or AeLimits()
        self.config = config or AeConfig()
        # Pass RenderExposureActuator.photometry() so f-stop/responsivity match the camera.
        self.photometry = photometry or Photometry()
        self._handle = self._lib.sl_zed_sim2real_ae_create(ctypes.byref(self.limits.to_c()),
                                                          float(initial_exposure_s or 0.0))
        c = camera_model_lib.AeStateC()
        self._lib.sl_zed_sim2real_ae_get_state(self._handle, ctypes.byref(c))
        self.state = AeState.from_c(c)
        if abs(self.config.target_mean - zedx_image_level()) > 1e-9:
            self._lib.sl_zed_sim2real_ae_reconfigure(self._handle, ctypes.byref(self.limits.to_c()),
                                                     float(self.config.target_mean), ctypes.byref(c))
            self.state = AeState.from_c(c)

    def __del__(self):
        handle, self._handle = getattr(self, "_handle", None), None
        if handle and getattr(self, "_lib", None) is not None:
            self._lib.sl_zed_sim2real_ae_destroy(handle)

    def update(self, stats, dt: Optional[float] = None) -> AeState:
        """Advance one camera frame. Stats from an already-seen frame are ignored."""
        if stats is None:
            return self.state
        prev = self.state
        c = camera_model_lib.AeStateC()
        if not self._lib.sl_zed_sim2real_ae_update(self._handle, ctypes.byref(stats_to_c(stats)), float(dt or 0.0),
                                                   ctypes.byref(c)):
            return self.state
        new = AeState.from_c(c)
        mean = getattr(stats, "mean_luminance", None)
        # The metered frame was captured with (approximately) the previous exposure.
        new.scene_luminance = self.photometry.nits(mean, prev.total) if mean else None
        self.state = new
        return new


RTX_AUTO_EXPOSURE_ATTR = "omni:rtx:autoExposure:enabled"


def _log_warn(msg: str) -> None:
    try:
        import carb
        carb.log_warn(msg)
    except ImportError:  # outside Kit (offline tests)
        print(msg)


class RenderExposureActuator:
    """Writes an AeState to RTX per-camera exposure on one or more camera prims.

    ``exposure:time`` = exposure time, ``exposure:iso`` = iso_base x total gain. Edits go to
    the session layer so the user's scene file is never dirtied, and are change-gated so a
    converged loop authors nothing. RTX's own per-camera auto exposure
    (``omni:rtx:autoExposure:enabled``, e.g. switched on in a camera's property panel) is held
    off while this drives the camera: it rescales the image after the exposure, so the loop
    would chase it to its limits.
    """

    def __init__(self, stage, camera_paths: Sequence[str], iso_base: float = 100.0, min_rel_change: float = 1e-3,
                 responsivity: Optional[float] = None):
        """``responsivity``: also author exposure:responsivity (e.g. zedx_responsivity(target))
        so the chosen exposure time and gain match the real camera; None keeps the prim's."""
        from pxr import Sdf

        self.stage = stage
        self.iso_base = iso_base
        self.min_rel_change = min_rel_change
        self.writes = 0
        self._attrs = []
        self._resp_attrs = []
        self._rtx_ae_attrs = []
        with self._session():
            for path in camera_paths:
                prim = stage.GetPrimAtPath(path)
                if not prim:
                    raise ValueError(f"camera prim not found: {path}")
                t = prim.GetAttribute("exposure:time") or prim.CreateAttribute("exposure:time", Sdf.ValueTypeNames.Float)
                iso = prim.GetAttribute("exposure:iso") or prim.CreateAttribute("exposure:iso", Sdf.ValueTypeNames.Float)
                self._attrs.append((t, iso))
                rtx_ae = prim.GetAttribute(RTX_AUTO_EXPOSURE_ATTR)
                if rtx_ae and rtx_ae.Get():
                    _log_warn(f"[ZED] {path}: RTX auto exposure is on for this camera; it is held off while the "
                              "camera's auto exposure runs (it would override the exposure).")
                self._rtx_ae_attrs.append(rtx_ae or prim.CreateAttribute(RTX_AUTO_EXPOSURE_ATTR, Sdf.ValueTypeNames.Bool))
                if responsivity is not None:
                    self._resp_attrs.append(prim.GetAttribute("exposure:responsivity") or
                                            prim.CreateAttribute("exposure:responsivity", Sdf.ValueTypeNames.Float))
        self._responsivity = responsivity
        self._applied = None
        self._resp_applied = False
        self._primary = stage.GetPrimAtPath(camera_paths[0])
        self._author_responsivity()

    def _author_responsivity(self) -> None:
        # A render product authors its default exposure attributes (responsivity 1.1027) when it
        # first renders, which can come after this actuator authored its own: check the value is
        # still ours, or the loop compensates with ~20x the exposure x gain (same image, wrong noise).
        if self._resp_applied and self._resp_attrs:
            value = self._resp_attrs[0].Get()
            if value is None or abs(float(value) - float(self._responsivity)) > 1e-6 * abs(float(self._responsivity)):
                self._resp_applied = False
        if not self._resp_applied:
            with self._session():
                for r in self._resp_attrs:
                    r.Set(float(self._responsivity))
                for a in self._rtx_ae_attrs:
                    a.Set(False)
            self._resp_applied = True

    def photometry(self, k: float = RTX_SIGNAL_PER_NIT) -> Photometry:
        """The camera's exposure terms the actuator does not drive (f-stop, responsivity)."""
        def get(name, default):
            attr = self._primary.GetAttribute(name)
            value = attr.Get() if attr else None
            return float(value) if value is not None else default
        return Photometry(fstop=get("exposure:fStop", 5.0), responsivity=get("exposure:responsivity", 1.0),
                          iso_base=self.iso_base, k=k)

    def _session(self):
        from pxr import Usd

        return Usd.EditContext(self.stage, self.stage.GetSessionLayer())

    def apply(self, state: AeState) -> bool:
        self._author_responsivity()  # photometry() assumes it; restore it after a release()
        t, iso = state.exposure_s, self.iso_base * state.analog_gain * state.digital_gain
        if self._applied is not None:
            t0, iso0 = self._applied
            if abs(t / t0 - 1) < self.min_rel_change and abs(iso / iso0 - 1) < self.min_rel_change:
                return False
        with self._session():
            for t_attr, iso_attr in self._attrs:
                t_attr.Set(float(t))
                iso_attr.Set(float(iso))
        self._applied = (t, iso)
        self.writes += 1
        return True

    def release(self) -> None:
        """Remove the session-layer opinions, restoring the scene's own exposure."""
        with self._session():
            for t_attr, iso_attr in self._attrs:
                t_attr.Clear()
                iso_attr.Clear()
            for r in self._resp_attrs:
                r.Clear()
            for a in self._rtx_ae_attrs:
                a.Clear()
        self._applied = None
        self._resp_applied = False
