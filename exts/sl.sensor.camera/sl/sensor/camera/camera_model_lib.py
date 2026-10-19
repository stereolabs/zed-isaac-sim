# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""ctypes binding of the ZED X camera model in the ``sl_zed_sim2real`` library.

The camera model (the camera's sRGB output, its exposure meter, auto exposure and auto white
balance) is the ZED Sim2Real look. This module loads the library once and declares its signatures;
``lib()`` returns None when the library is missing or predates the camera model, and callers then
fall back to the render's plain image.
"""
import ctypes
import os
from pathlib import Path
from typing import List


def _candidate_paths() -> List[Path]:
    """Where to look for the shared library, most specific first: $SL_ZED_SIM2REAL_PATH (a file or its
    folder; no fallback then), the extension's bin/, the OS loader's default paths."""
    name = "sl_zed_sim2real.dll" if os.name == "nt" else "libsl_zed_sim2real.so"
    env = os.environ.get("SL_ZED_SIM2REAL_PATH")
    if env:
        p = Path(env)
        return [p / name if p.is_dir() else p]
    ext_root = Path(__file__).resolve().parents[3]  # exts/sl.sensor.camera (parents: camera, sensor, sl)
    return [ext_root / "bin" / name, Path(name)]


METER_BINS = 128
METER_LOG2_MIN = -16.0
METER_LOG2_MAX = 16.0

_F3 = ctypes.c_float * 3
_F2 = ctypes.c_float * 2
_D3 = ctypes.c_double * 3
_D2 = ctypes.c_double * 2
_F4 = ctypes.c_float * 4


class EncodeParams(ctypes.Structure):
    _fields_ = [("seed", ctypes.c_uint), ("gain", ctypes.c_float), ("vignette_inv_f", ctypes.c_float),
                ("blur_scale", ctypes.c_float), ("light_gain", ctypes.c_float), ("white_balance", _F3),
                ("sharpness", ctypes.c_int), ("edge_noise", ctypes.c_int),
                # ABI 2: which lens this is (0 left or a single camera, 1 right), for the faults a validation
                # scene sets through the environment (SL_SIM2REAL_*); an ABI 1 library ignores it
                ("eye", ctypes.c_int)]


class MeterImage(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("row_stride", ctypes.c_longlong), ("pixel_stride", ctypes.c_int),
                ("element_bytes", ctypes.c_int), ("w", ctypes.c_int), ("h", ctypes.c_int)]


class MeterView(ctypes.Structure):
    _fields_ = [("vignette_inv_f", ctypes.c_float), ("white_balance", _F3), ("neutral_ref", _F2), ("roi", _F4)]


class MeterStats(ctypes.Structure):
    _fields_ = [("frame", ctypes.c_longlong), ("samples", ctypes.c_int), ("dark_fraction", ctypes.c_double),
                ("mean_luminance", ctypes.c_double), ("log2_mean", ctypes.c_double), ("log2_median", ctypes.c_double),
                ("log2_p01", ctypes.c_double), ("log2_p99", ctypes.c_double), ("mean_encoded", ctypes.c_double),
                ("clip_fraction", ctypes.c_double), ("has_mean_rgb", ctypes.c_int), ("mean_rgb", _D3),
                ("has_neutral_rgb", ctypes.c_int), ("neutral_rgb", _D3), ("neutral_fraction", ctypes.c_double),
                ("histogram", ctypes.c_float * METER_BINS)]


class AeLimitsC(ctypes.Structure):
    _fields_ = [("fps", ctypes.c_double), ("exposure_min_s", ctypes.c_double), ("exposure_max_s", ctypes.c_double),
                ("analog_gain_mdb", _D2), ("digital_gain", _D2), ("allocation", ctypes.c_int)]


class AeStateC(ctypes.Structure):
    _fields_ = [("exposure_s", ctypes.c_double), ("analog_gain", ctypes.c_double), ("digital_gain", ctypes.c_double),
                ("error_ev", ctypes.c_double), ("converged", ctypes.c_int), ("saturated", ctypes.c_int),
                ("frame", ctypes.c_longlong)]


# C ABI versions of the library whose camera-model section this binding reads (1 = 0.3.0, 2 = 0.4.0 and 1.0.0)
ABI_VERSIONS = (1, 2)
_LIB = None
_TRIED = False


def _bind(lib) -> None:
    P = ctypes.c_void_p
    sigs = {
        "abi_version": ([], ctypes.c_int),
        "encoder_create": ([], P),
        "encoder_destroy": ([P], None),
        "encode_device": ([P, P, ctypes.c_longlong, ctypes.c_int, ctypes.c_int, ctypes.c_int, P, P,
                           ctypes.POINTER(EncodeParams), P], ctypes.c_int),
        "encode_host": ([P, P, ctypes.c_int, ctypes.c_int, P, P, ctypes.POINTER(EncodeParams)], ctypes.c_int),
        "light_flicker_gain": ([ctypes.c_double, ctypes.c_float, ctypes.c_float], ctypes.c_double),
        "meter_create": ([ctypes.c_int], P),
        "meter_destroy": ([P], None),
        "meter_update": ([P, ctypes.POINTER(MeterImage), ctypes.POINTER(MeterView), ctypes.c_longlong, P,
                          ctypes.POINTER(MeterStats)], ctypes.c_int),
        "meter_wait": ([P], ctypes.c_int),
        "ae_default_limits": ([ctypes.c_double, ctypes.POINTER(AeLimitsC)], None),
        "ae_create": ([ctypes.POINTER(AeLimitsC), ctypes.c_double], P),
        "ae_destroy": ([P], None),
        "ae_get_state": ([P, ctypes.POINTER(AeStateC)], None),
        "ae_update": ([P, ctypes.POINTER(MeterStats), ctypes.c_double, ctypes.POINTER(AeStateC)], ctypes.c_int),
        "ae_reconfigure": ([P, ctypes.POINTER(AeLimitsC), ctypes.c_double, ctypes.POINTER(AeStateC)], None),
        "ae_image_level": ([], ctypes.c_double),
        "responsivity": ([ctypes.c_double, ctypes.c_double], ctypes.c_double),
        "awb_create": ([], P),
        "awb_destroy": ([P], None),
        "awb_update": ([P, ctypes.POINTER(MeterStats), ctypes.c_double, ctypes.c_double, _F3], ctypes.c_int),
        "awb_get": ([P, _F3, _F2], ctypes.c_int),
        "awb_gains_for": ([_F3, _F3], None),
    }
    for name, (args, res) in sigs.items():
        f = getattr(lib, "sl_zed_sim2real_" + name)  # AttributeError: a library without the camera model
        f.argtypes, f.restype = args, res


def lib():
    """The loaded library with the camera model bound, or None (logged once)."""
    global _LIB, _TRIED
    if _TRIED:
        return _LIB
    _TRIED = True
    reason = "not found"
    for path in _candidate_paths():
        try:
            handle = ctypes.CDLL(str(path))
        except OSError:
            continue
        try:
            _bind(handle)
        except AttributeError:
            reason = f"{path} predates the ZED X camera model"
            continue
        abi = handle.sl_zed_sim2real_abi_version()
        if abi not in ABI_VERSIONS:
            reason = f"{path} has C ABI {abi}, this extension reads {ABI_VERSIONS[-1]}"
            continue
        if abi < ABI_VERSIONS[-1]:
            _log_warn(f"[ZED] {path} is an older sl_zed_sim2real (ABI {abi}); update it to 1.0.0.")
        _LIB = handle
        return _LIB
    _log_warn(f"[ZED] sl_zed_sim2real camera model unavailable ({reason}): images are streamed as plain sRGB, "
              "without the real camera's noise, sharpness, lens falloff, auto exposure or white balance.")
    return None


def available() -> bool:
    return lib() is not None


def _log_warn(msg: str) -> None:
    try:
        import carb
        carb.log_warn(msg)
    except ImportError:  # outside Kit
        print(msg)


def f3(values) -> "ctypes.Array":
    return _F3(*(float(v) for v in values))


def f2(values) -> "ctypes.Array":
    return _F2(*(float(v) for v in values))


def f4(values) -> "ctypes.Array":
    return _F4(*(float(v) for v in values))


def d2(values) -> "ctypes.Array":
    return _D2(*(float(v) for v in values))


def d3(values) -> "ctypes.Array":
    return _D3(*(float(v) for v in values))
