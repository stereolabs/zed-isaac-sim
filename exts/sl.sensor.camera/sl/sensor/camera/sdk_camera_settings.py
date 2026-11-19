"""Camera settings of a streamed simulated ZED (``enable_camera_settings_control``, sl_zed 5.5.1+).

A receiver sets the camera's settings with ``Camera::setCameraSettings()`` as on a real camera.
The streamer hands those requests to the simulator, which applies the ones it declared, and it
reports the exposure the simulator renders with (``set_frame_state``), so a receiver reads the
exposure time and gains of each frame and keeps them in its SVO recordings. Receivers refuse the
settings the simulator did not declare.

The camera's auto exposure (auto_exposure.py) applies the exposure settings, the way a ZED X's
ISP does: a manual exposure time or gain pins that value inside the auto exposure's ranges
(the others stay automatic), AEC_AGC = 0 holds the current exposure, and
EXPOSURE_COMPENSATION moves the target by (value - 50) / 25 EV.

Kit-free: ctypes only, so the mapping imports and tests outside Kit.
"""
from __future__ import annotations

import ctypes
import dataclasses
from typing import Optional

from .auto_exposure import AeLimits, AeState
from .sdk_virtual_camera import _library_path

# sl::VIDEO_SETTINGS (SDK sl_zed/defines.hpp)
AEC_AGC = 8
EXPOSURE_TIME = 13
ANALOG_GAIN = 14
DIGITAL_GAIN = 15
AUTO_EXPOSURE_TIME_RANGE = 16
AUTO_ANALOG_GAIN_RANGE = 17
AUTO_DIGITAL_GAIN_RANGE = 18
EXPOSURE_COMPENSATION = 19

# The settings the auto exposure applies. Not the metering region (it meters the full frame), nor
# the percentage EXPOSURE / GAIN or the image settings (white balance, denoising, ...).
SUPPORTED = (AEC_AGC, EXPOSURE_TIME, ANALOG_GAIN, DIGITAL_GAIN, AUTO_EXPOSURE_TIME_RANGE,
             AUTO_ANALOG_GAIN_RANGE, AUTO_DIGITAL_GAIN_RANGE, EXPOSURE_COMPENSATION)
SUPPORTED_MASK = sum(1 << s for s in SUPPORTED)

AUTO = -1  # sl::VIDEO_SETTINGS_VALUE_AUTO: automatic, or the setting's default

_SUCCESS = 0
_STREAMER_NOT_OPENED = 9


class SimCameraSettings(ctypes.Structure):
    """Mirror of sl::SimCameraSettings (SDK sl_input/sim_streamer/types_c.h, ext include/types_c.h)."""
    _fields_ = [
        ("version", ctypes.c_int),
        ("revision", ctypes.c_uint),
        ("changed_mask", ctypes.c_uint),
        ("value", ctypes.c_int * 32),       # indexed by sl::VIDEO_SETTINGS, -1 = automatic / default
        ("value_max", ctypes.c_int * 32),   # maximum of the AUTO_*_RANGE settings
        ("roi_left", ctypes.c_int * 4),
        ("roi_right", ctypes.c_int * 4),
        ("reserved", ctypes.c_int * 4),
    ]


class SimFrameState(ctypes.Structure):
    """Mirror of sl::SimFrameState."""
    _fields_ = [
        ("version", ctypes.c_int),
        ("exposure_time_us", ctypes.c_int),
        ("analog_gain_mdb", ctypes.c_int),
        ("digital_gain", ctypes.c_int),
        ("reserved", ctypes.c_int * 4),
    ]


assert ctypes.sizeof(SimCameraSettings) == 316, "SimCameraSettings layout must match the SDK"
assert ctypes.sizeof(SimFrameState) == 32, "SimFrameState layout must match the SDK"


# ------------------------------------------------------------------ library loading
_LIB = None
_LOAD_TRIED = False


def _load():
    """The bundled sl_zed, by the same path as the streaming plugin: a second copy of the library
    would hold its own streamers and never see the plugin's."""
    global _LIB, _LOAD_TRIED
    if _LOAD_TRIED:
        return _LIB
    _LOAD_TRIED = True
    try:
        lib = ctypes.CDLL(str(_library_path()))
    except OSError:
        return None
    if not hasattr(lib, "enable_camera_settings_control"):
        return None
    lib.enable_camera_settings_control.restype = ctypes.c_int
    lib.enable_camera_settings_control.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.POINTER(SimCameraSettings)]
    lib.get_requested_camera_settings.restype = ctypes.c_int
    lib.get_requested_camera_settings.argtypes = [ctypes.c_int, ctypes.POINTER(SimCameraSettings)]
    lib.set_frame_state.restype = ctypes.c_int
    lib.set_frame_state.argtypes = [ctypes.c_int, ctypes.POINTER(SimFrameState)]
    _LIB = lib
    return _LIB


def available() -> bool:
    return _load() is not None


# ------------------------------------------------------------------ requests -> auto exposure
def _range(requested_min: int, requested_max: int, low: float, high: float, scale: float):
    """An AUTO_*_RANGE request inside the camera's own range; -1 or 0 gives the full range."""
    if requested_min <= 0 and requested_max <= 0:
        return low, high
    # the camera's own bounds come back rounded to the setting's unit (initial_settings)
    lo = low if requested_min <= 0 or requested_min == round(low / scale) else max(low, requested_min * scale)
    hi = high if requested_max <= 0 or requested_max == round(high / scale) else min(high, requested_max * scale)
    return (lo, hi) if lo <= hi else (low, high)


def _pin(value: int, low: float, high: float, scale: float):
    """A manual value, clamped to the range."""
    v = min(max(value * scale, low), high)
    return v, v


def limits_for(settings: SimCameraSettings, base: AeLimits, held: Optional[AeState] = None) -> AeLimits:
    """The auto exposure's limits under the requested settings.

    Args:
        settings: the current settings (get_requested_camera_settings)
        base: the camera's own limits, what the settings narrow down
        held: the exposure to hold when AEC_AGC is 0
    """
    v, vmax = settings.value, settings.value_max
    t_lo, t_hi = _range(v[AUTO_EXPOSURE_TIME_RANGE], vmax[AUTO_EXPOSURE_TIME_RANGE],
                        base.exposure_min_s, base.t_max, 1e-6)
    a_lo, a_hi = _range(v[AUTO_ANALOG_GAIN_RANGE], vmax[AUTO_ANALOG_GAIN_RANGE],
                        base.analog_gain_mdb[0], base.analog_gain_mdb[1], 1.0)
    d_lo, d_hi = _range(v[AUTO_DIGITAL_GAIN_RANGE], vmax[AUTO_DIGITAL_GAIN_RANGE],
                        base.digital_gain[0], base.digital_gain[1], 1.0)

    if v[AEC_AGC] == 0 and held is not None:
        t_lo, t_hi = _pin(held.exposure_s, t_lo, t_hi, 1.0)
        a_lo, a_hi = _pin(held.analog_gain_mdb, a_lo, a_hi, 1.0)
        d_lo, d_hi = _pin(held.digital_gain, d_lo, d_hi, 1.0)
    if v[EXPOSURE_TIME] > 0:
        t_lo, t_hi = _pin(v[EXPOSURE_TIME], base.exposure_min_s, base.t_max, 1e-6)
    if v[ANALOG_GAIN] > 0:
        a_lo, a_hi = _pin(v[ANALOG_GAIN], base.analog_gain_mdb[0], base.analog_gain_mdb[1], 1.0)
    if v[DIGITAL_GAIN] > 0:
        d_lo, d_hi = _pin(v[DIGITAL_GAIN], base.digital_gain[0], base.digital_gain[1], 1.0)

    if (t_lo, t_hi, a_lo, a_hi, d_lo, d_hi) == (base.exposure_min_s, base.t_max, *base.analog_gain_mdb, *base.digital_gain):
        return base
    return dataclasses.replace(base, exposure_min_s=t_lo, exposure_max_s=t_hi,
                               analog_gain_mdb=(a_lo, a_hi), digital_gain=(d_lo, d_hi))


def target_for(settings: SimCameraSettings, base_target: float) -> float:
    """The auto exposure's target under EXPOSURE_COMPENSATION (0-100, 50 = none, +-2 EV)."""
    comp = settings.value[EXPOSURE_COMPENSATION]
    if comp < 0:
        return base_target
    return base_target * 2.0 ** ((min(comp, 100) - 50) / 25.0)


def initial_settings(base: AeLimits) -> SimCameraSettings:
    """What a receiver reads when it opens the stream: automatic exposure over the camera's ranges."""
    s = SimCameraSettings()
    s.version = 1
    for i in range(32):
        s.value[i] = AUTO
        s.value_max[i] = AUTO
    s.value[AEC_AGC] = 1
    s.value[EXPOSURE_COMPENSATION] = 50
    s.value[AUTO_EXPOSURE_TIME_RANGE] = int(round(base.exposure_min_s * 1e6))
    s.value_max[AUTO_EXPOSURE_TIME_RANGE] = int(round(base.t_max * 1e6))
    s.value[AUTO_ANALOG_GAIN_RANGE] = int(round(base.analog_gain_mdb[0]))
    s.value_max[AUTO_ANALOG_GAIN_RANGE] = int(round(base.analog_gain_mdb[1]))
    s.value[AUTO_DIGITAL_GAIN_RANGE] = int(round(base.digital_gain[0]))
    s.value_max[AUTO_DIGITAL_GAIN_RANGE] = int(round(base.digital_gain[1]))
    return s


# ------------------------------------------------------------------ channel
class CameraSettingsChannel:
    """The camera settings of one streamer (the id the streaming node reports).

    Only one poller per streamer: each poll clears the list of changed settings.
    """

    def __init__(self, streamer_id: int, base: AeLimits):
        self.streamer_id = int(streamer_id)
        self._lib = _load()
        self._last_revision = 0  # nothing requested yet: the initial settings are the camera's own
        self._reported = None
        self.enabled = False
        if self._lib is not None:
            init = initial_settings(base)
            self.enabled = self._lib.enable_camera_settings_control(
                self.streamer_id, SUPPORTED_MASK, ctypes.byref(init)) == _SUCCESS

    def poll(self) -> Optional[SimCameraSettings]:
        """The settings when a receiver changed one since the previous poll, else None."""
        if not self.enabled:
            return None
        s = SimCameraSettings()
        if self._lib.get_requested_camera_settings(self.streamer_id, ctypes.byref(s)) != _SUCCESS:
            self.enabled = False
            return None
        if s.revision == self._last_revision:
            return None
        self._last_revision = s.revision
        return s

    def report(self, state: AeState) -> None:
        """The exposure the camera renders with, sent with the following frames."""
        if not self.enabled or state is None:
            return
        values = (int(round(state.exposure_s * 1e6)), int(round(state.analog_gain_mdb)),
                  int(round(state.digital_gain)))
        if values == self._reported:
            return
        f = SimFrameState()
        f.version = 1
        f.exposure_time_us, f.analog_gain_mdb, f.digital_gain = values
        if self._lib.set_frame_state(self.streamer_id, ctypes.byref(f)) == _SUCCESS:
            self._reported = values

    def close(self) -> None:
        """Stop applying settings and reporting an exposure: receivers refuse the settings again."""
        if not self.enabled:
            return
        base = initial_settings(AeLimits())
        self._lib.enable_camera_settings_control(self.streamer_id, 0, ctypes.byref(base))
        f = SimFrameState()
        f.version = 1
        self._lib.set_frame_state(self.streamer_id, ctypes.byref(f))
        self.enabled = False
