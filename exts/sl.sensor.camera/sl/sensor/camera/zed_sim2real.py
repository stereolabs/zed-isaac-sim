"""Python binding for the ZED Sim2Real camera model (the ``sl_zed_sim2real`` shared library).

Applies the same calibrated "ZED X look" the streaming path uses, but to in-process
frames: GPU torch tensors (Isaac Lab tensor path) or host numpy arrays (dataset capture).
It is a thin ctypes wrapper over the library's C ABI (``include/sl_zed_sim2real.h``); the
heavy lifting (CUDA kernels, auto-exposure) lives in the library, so this is the same
implementation the C++ streaming plugin runs, not a reimplementation.

Kit-free: depends only on ctypes (+ torch or numpy at call time), so it imports in
standalone Isaac Lab / Isaac Sim scripts.

Typical use (Isaac Lab, one independent auto-exposure state per env)::

    from sl.sensor.camera.zed_sim2real import ZedSim2Real
    sim2real = ZedSim2Real(num_states=num_envs)      # None -> library unavailable, calls no-op
    ...
    rgb = unwrap_output(cam.data.output, "rgb")   # (N, H, W, C) uint8 cuda tensor
    sim2real.apply(rgb, scene_lux=0.0)                # degrades rgb in place
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import List, Optional

# Must match SL_ZED_SIM2REAL_ABI_VERSION in include/sl_zed_sim2real.h. Bump both together when
# the C ABI changes; the loader refuses a library that reports a different value.
_ABI_VERSION = 1

# ------------------------------------------------------------------ library loading
_LIB = None
_LOAD_TRIED = False
_WARNED_FAILURE = False


def _candidate_paths() -> List[Path]:
    """Where to look for the shared library, most specific first."""
    if os.name == "nt":
        name = "sl_zed_sim2real.dll"
    else:
        name = "libsl_zed_sim2real.so"
    env = os.environ.get("SL_ZED_SIM2REAL_PATH")
    cands: List[Path] = []
    if env:
        p = Path(env)
        cands.append(p / name if p.is_dir() else p)
    # exts/sl.sensor.camera/bin/  (parents: camera, sensor, sl, sl.sensor.camera)
    ext_root = Path(__file__).resolve().parents[3]
    cands.append(ext_root / "bin" / name)
    cands.append(Path(name))  # let the OS loader search its default paths
    return cands


def _load():
    """Load the library once; return the CDLL handle or None if unavailable."""
    global _LIB, _LOAD_TRIED
    if _LOAD_TRIED:
        return _LIB
    _LOAD_TRIED = True
    for path in _candidate_paths():
        try:
            lib = ctypes.CDLL(str(path))
        except OSError:
            continue
        _bind(lib)
        abi = lib.sl_zed_sim2real_abi_version()
        if abi != _ABI_VERSION:
            print(f"[ZED] sl_zed_sim2real ABI mismatch (lib {abi}, expected {_ABI_VERSION}) "
                  f"at {path}; ZED Sim2Real disabled")
            continue
        _LIB = lib
        return _LIB
    return None


def _bind(lib) -> None:
    """Declare the C ABI signatures (see include/sl_zed_sim2real.h)."""
    P = ctypes.c_void_p
    lib.sl_zed_sim2real_abi_version.restype = ctypes.c_int
    lib.sl_zed_sim2real_engine_create.restype = P
    lib.sl_zed_sim2real_engine_destroy.argtypes = [P]
    lib.sl_zed_sim2real_state_create.restype = P
    lib.sl_zed_sim2real_state_create.argtypes = [ctypes.c_uint]
    lib.sl_zed_sim2real_state_destroy.argtypes = [P]
    lib.sl_zed_sim2real_process_device.restype = ctypes.c_int
    lib.sl_zed_sim2real_process_device.argtypes = [
        P, P, P, ctypes.c_int, ctypes.c_int, P, ctypes.c_int, ctypes.c_float, ctypes.c_int]
    lib.sl_zed_sim2real_process_host.restype = ctypes.c_int
    lib.sl_zed_sim2real_process_host.argtypes = [
        P, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_float, ctypes.c_int]
    # per-stream overrides (v0.2.0, additive; absent in older libraries)
    if hasattr(lib, "sl_zed_sim2real_state_set_ae_target"):
        lib.sl_zed_sim2real_state_set_ae_target.argtypes = [P, ctypes.c_float]
        lib.sl_zed_sim2real_state_set_noise.argtypes = [P] + [ctypes.c_float] * 3


def available() -> bool:
    """True if the shared library loaded and can process frames."""
    return _load() is not None


# ------------------------------------------------------------------ high-level API
class ZedSim2Real:
    """Holds the GPU engine (shared scratch) and one auto-exposure state per stream/env.

    If the library is unavailable, every method is a safe no-op and :pyattr:`ok` is False,
    so callers can wire it in unconditionally.
    """

    def __init__(self, num_states: int = 1):
        self._lib = _load()
        self._engine = None
        self._states: List[Optional[ctypes.c_void_p]] = []
        if self._lib is None:
            return
        self._engine = self._lib.sl_zed_sim2real_engine_create()
        # Seed each state with its index so per-env sensor noise is decorrelated.
        self._states = [self._lib.sl_zed_sim2real_state_create(i) for i in range(max(1, num_states))]

    @property
    def ok(self) -> bool:
        return self._lib is not None and self._engine is not None

    def _ensure_states(self, n: int) -> None:
        while len(self._states) < n:
            self._states.append(self._lib.sl_zed_sim2real_state_create(len(self._states)))

    def set_ae_target(self, target01: float, state_index: int = 0) -> None:
        """Override the AE set-point (median display luma 0..1) for one stream,
        e.g. to match a real capture whose metering differs from the calibrated
        default. <=0 restores the default. No-op on libraries older than v0.2.0."""
        if not self.ok or not hasattr(self._lib, "sl_zed_sim2real_state_set_ae_target"):
            return
        self._ensure_states(state_index + 1)
        self._lib.sl_zed_sim2real_state_set_ae_target(self._states[state_index], float(target01))

    def set_noise(self, noise_gain: float = -1.0, salt_p: float = -1.0,
                  salt_amp: float = -1.0, state_index: int = 0) -> None:
        """Override the noise block for one stream (base gain on the sensor-noise
        tables, residue-speckle probability/amplitude). <=0 keeps each default.
        No-op on libraries older than v0.2.0."""
        if not self.ok or not hasattr(self._lib, "sl_zed_sim2real_state_set_noise"):
            return
        self._ensure_states(state_index + 1)
        self._lib.sl_zed_sim2real_state_set_noise(
            self._states[state_index], float(noise_gain), float(salt_p), float(salt_amp))

    def apply(self, rgb, scene_lux: float = 0.0, advance: bool = True, stream=None):
        """Apply the sim2real to a GPU uint8 RGB(A) tensor, in place.

        rgb: torch.Tensor, ``(H, W, C)`` or ``(N, H, W, C)``, ``uint8``, on CUDA, C in {3, 4}.
             One state per leading env is used (created on demand). A 3-channel tensor is
             padded to RGBA internally and the RGB result copied back.
        advance: update auto-exposure from this frame (False to reuse, e.g. a stereo right
                 eye sharing the left eye's state).
        Returns rgb (unchanged object) for convenience; no-op if the library is unavailable.
        """
        if not self.ok or rgb is None:
            return rgb
        import torch  # local import keeps this module importable without torch

        if rgb.dtype != torch.uint8 or not rgb.is_cuda:
            raise ValueError("ZedSim2Real.apply expects a uint8 CUDA tensor")
        batched = rgb.ndim == 4
        frames = rgb if batched else rgb.unsqueeze(0)
        n, h, w, c = frames.shape
        if c not in (3, 4):
            raise ValueError(f"ZedSim2Real.apply expects 3 or 4 channels, got {c}")
        # We write the result back into `rgb`; a non-contiguous tensor can't be updated in place
        # correctly here. Fail loud rather than silently degrade the wrong memory.
        if not rgb.is_contiguous():
            raise ValueError("ZedSim2Real.apply expects a contiguous tensor; call .contiguous() first")
        self._ensure_states(n)
        # The kernels run on the caller's current CUDA stream, i.e. the same stream Isaac Lab's
        # renderer/tensor path uses in these single-stream scripts. If you drive rendering on a
        # separate stream, pass its handle explicitly to avoid a read-before-write hazard.
        if stream is None:
            stream = torch.cuda.current_stream(rgb.device).cuda_stream

        for i in range(n):
            frame = frames[i]                                   # (H, W, C) view (contiguous)
            if c == 4:
                ok = self._lib.sl_zed_sim2real_process_device(
                    self._engine, self._states[i], ctypes.c_void_p(frame.data_ptr()),
                    w, h, ctypes.c_void_p(stream), 1, float(scene_lux), int(advance))
            else:                                               # pad RGB -> RGBA, copy back
                rgba = torch.empty((h, w, 4), dtype=torch.uint8, device=frame.device)
                rgba[..., :3] = frame
                rgba[..., 3] = 255
                ok = self._lib.sl_zed_sim2real_process_device(
                    self._engine, self._states[i], ctypes.c_void_p(rgba.data_ptr()),
                    w, h, ctypes.c_void_p(stream), 1, float(scene_lux), int(advance))
                if ok:
                    frame.copy_(rgba[..., :3])
            if not ok:
                self._warn_failure_once()
        return rgb

    @staticmethod
    def _warn_failure_once() -> None:
        global _WARNED_FAILURE
        if not _WARNED_FAILURE:
            _WARNED_FAILURE = True
            print("[ZED] sl_zed_sim2real GPU processing failed; frames pass through unmodified")

    def apply_numpy(self, rgba, scene_lux: float = 0.0, advance: bool = True, state_index: int = 0):
        """Apply the sim2real to a host numpy uint8 array ``(H, W, 4)`` (RGBA), in place (CPU path)."""
        if not self.ok or rgba is None:
            return rgba
        import numpy as np

        if rgba.dtype != np.uint8 or rgba.ndim != 3 or rgba.shape[2] != 4:
            raise ValueError("ZedSim2Real.apply_numpy expects a (H, W, 4) uint8 array")
        rgba = np.ascontiguousarray(rgba)
        h, w = rgba.shape[0], rgba.shape[1]
        self._ensure_states(state_index + 1)
        ptr = rgba.ctypes.data_as(ctypes.c_char_p)
        self._lib.sl_zed_sim2real_process_host(
            self._states[state_index], ptr, w, h, 1, float(scene_lux), int(advance))
        return rgba

    def close(self) -> None:
        if self._lib is None:
            return
        for s in self._states:
            if s:
                self._lib.sl_zed_sim2real_state_destroy(s)
        self._states = []
        if self._engine:
            self._lib.sl_zed_sim2real_engine_destroy(self._engine)
            self._engine = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
