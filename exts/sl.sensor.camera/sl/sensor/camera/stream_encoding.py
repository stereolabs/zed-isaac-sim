# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""sRGB encoding of the streamed ZED images, on the GPU.

The "linear" (legacy) stream encoding takes the render product's LdrColor ("rgb" annotator).
Measured on Isaac Sim 6.0 / Real-Time 2.0 through the ZED SDK receiver, that is the RTX tonemapped
image (the ACES approximation followed by sRGB), but it silently becomes 255 * clamp(HdrColor)
(linear) once anything requests HdrColor on the same render product (e.g. an exposure meter). A
real ZED X matches neither: its output is sRGB of the scene's linear light. So the stream is
encoded here from HdrColor (linear, already exposed by the camera's exposure:* attributes),
independent of the tonemapper and of whatever else reads the render product.

The encoding is the ZED X camera model of the ``sl_zed_sim2real`` library (camera_model_lib.py): the
real camera's sharpness, motion blur over its exposure time, the scene lights' flicker, its white
balance, lens falloff and sensor noise at its gain, then sRGB; with the eye's depth, first the lens's
focus blur (library 0.5.0). Without the library the image is encoded as plain sRGB, with none of these.
"""
import ctypes
import math

import warp as wp

from . import camera_model_lib
from .utils import LensType, get_camera_model, get_lens_type

# Light flicker: mains-powered lamps make a real frame's brightness vary by a global gain, the same
# in both eyes. It depends on the scene's lights, so it is off unless this setting is set: the std of
# the lamps' light swing (linear fraction, as a very short exposure sees it), or a preset name.
LIGHT_FLICKER_SETTING = "/exts/sl.sensor.camera/lightFlickerStd"  # fraction or preset; 0 / "" = off
LIGHT_FLICKER_MAINS_SETTING = "/exts/sl.sensor.camera/lightFlickerMainsHz"  # 50 or 60; 0 = 50
# legacy: a fixed flicker frequency as seen by the camera, without the exposure's integration; 0 = unused
LIGHT_FLICKER_HZ_SETTING = "/exts/sl.sensor.camera/lightFlickerHz"
# measured on real ZED X recordings: office LED panels ~0.6 %, the lamps of a light booth (halogen,
# fluorescent, LED) ~2 %
LIGHT_FLICKER_PRESETS = {"office_led": 0.006, "lamps": 0.02}


def light_flicker_std(value) -> float:
    """The lightFlickerStd setting as a fraction: a number, or a preset name (LIGHT_FLICKER_PRESETS); 0 = off."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, str):
        key = value.strip().lower()
        if key in LIGHT_FLICKER_PRESETS:
            return LIGHT_FLICKER_PRESETS[key]
    try:
        std = float(value)
    except (TypeError, ValueError):
        return 0.0
    return std if math.isfinite(std) and std > 0 else 0.0


def light_flicker_gain(sim_time: float, std: float, hz: float = 0.0, exposure_s: float = 0.0,
                      mains_hz: float = 0.0) -> float:
    """Global light gain of the frame at ``sim_time`` (s) for lamps swinging by ``std`` (fraction); 1 when off.

    The lamps' light swings at twice the mains frequency (``mains_hz``, 0 = 50 Hz); the frame's exposure
    (``exposure_s``) integrates the swing, so long exposures flicker less, and sampling at the camera's frame
    times gives the beat a real camera shows (10 Hz at 30 fps under 50 Hz mains). ``hz`` > 0 instead imposes a
    fixed beat frequency without the exposure's integration.
    """
    if not std or std <= 0 or not math.isfinite(sim_time):
        return 1.0
    lib = camera_model_lib.lib()
    if lib is None:
        return 1.0
    exact = getattr(lib, "sl_zed_sim2real_light_flicker_gain_exposure", None)
    if exact is None or (hz and hz > 0):
        return float(lib.sl_zed_sim2real_light_flicker_gain(float(sim_time), float(std), float(hz or 0.0)))
    return float(exact(float(sim_time), float(std), float(mains_hz or 0.0), float(exposure_s or 0.0)))


# Lenses with the focus blur's figures: the ZED X family's 2.2 mm and 4 mm (AR0234 sensor).
_FOCUS_BLUR_BASES = ("ZED_X", "ZED_XM", "ZED_XONE_GS", "ZED_XONE_S")
# Overrides of the lens figures for every focus-blurring camera (e.g. a unit focused nearer); 0 = the lens's.
FOCUS_F_NUMBER_SETTING = "/exts/sl.sensor.camera/focusBlurFNumber"
FOCUS_DISTANCE_SETTING = "/exts/sl.sensor.camera/focusBlurDistance"  # metres


def focus_lens(camera_model: str) -> int:
    """The focus blur's lens (camera_model_lib.LENS_*) for a camera model; LENS_NONE when it has no figures."""
    try:
        base, lens = get_camera_model(camera_model), get_lens_type(camera_model)
    except Exception:
        return camera_model_lib.LENS_NONE
    if base not in _FOCUS_BLUR_BASES:
        return camera_model_lib.LENS_NONE
    return {LensType.WIDE: camera_model_lib.LENS_2_2MM, LensType.NARROW: camera_model_lib.LENS_4MM}.get(
        lens, camera_model_lib.LENS_NONE)


def noise_seed(value: int) -> int:
    """Fold any integer into the encoder's seed."""
    return int(value) & 0x7FFFFFFF


@wp.func
def _srgb_oetf(v: float) -> float:
    if not (v > 0.0):  # also catches NaN
        return 0.0
    if v >= 1.0:
        return 1.0
    if v <= 0.0031308:
        return 12.92 * v
    return 1.055 * wp.pow(v, 1.0 / 2.4) - 0.055


@wp.kernel
def _plain_srgb8(src: wp.array3d(dtype=wp.float16), dst: wp.array3d(dtype=wp.uint8)):
    """Linear RGBA float16 -> sRGB RGBA8, nothing else (used without the camera model)."""
    y, x = wp.tid()
    for c in range(3):
        dst[y, x, c] = wp.uint8(wp.int32(_srgb_oetf(wp.float32(src[y, x, c])) * 255.0 + 0.5))
    dst[y, x, 3] = wp.uint8(255)


def light_gain_now(exposure_s: float) -> float:
    """This frame's light flicker gain, from the settings, the timeline and the frame's exposure time.

    The same gain for both eyes of a camera, and 1.0 (no flicker) unless LIGHT_FLICKER_SETTING is
    set. Kit-only, so the imports are local: the rest of this module runs without Kit.
    """
    import carb.settings

    settings = carb.settings.get_settings()
    std = light_flicker_std(settings.get(LIGHT_FLICKER_SETTING))
    if not std:
        return 1.0
    import omni.timeline

    t = omni.timeline.get_timeline_interface().get_current_time()
    return light_flicker_gain(t, std, float(settings.get(LIGHT_FLICKER_HZ_SETTING) or 0.0), exposure_s,
                              float(settings.get(LIGHT_FLICKER_MAINS_SETTING) or 0.0))


class StreamEncoder:
    """One camera eye's encoder: the camera model's scratch buffers, reused every frame."""

    def __init__(self):
        self._lib = camera_model_lib.lib()
        self._handle = self._lib.sl_zed_sim2real_encoder_create() if self._lib is not None else None

    @property
    def has_camera_model(self) -> bool:
        return self._handle is not None

    def encode(self, src: wp.array, dst: wp.array, *, seed: int = 0, gain: float = None, motion: wp.array = None,
               blur_scale: float = 0.0, vignette_inv_f: float = 0.0, sharpness: bool = False,
               light_gain: float = 1.0, wb=None, eye: int = 0, depth: wp.array = None,
               focus: "camera_model_lib.DefocusParams" = None) -> bool:
        """Encode ``src`` (linear RGBA float16 (H, W, 4), may be strided) into ``dst`` (RGBA8 (H, W, 4),
        packed), both on the same CUDA device, ordered on Warp's stream for that device.

        ``gain`` (analog x digital) adds the real camera's sensor noise at that gain; None = none.
        ``seed`` must differ per frame (and per eye). ``motion`` (the MotionVectors annotator output,
        packed float32 (H, W, 4)) with ``blur_scale`` (exposure time over the vectors' time step) adds
        the motion blur. ``vignette_inv_f`` (1 / the focal length in pixels) adds the lens falloff.
        ``sharpness``: the real camera's instead of the render's. ``light_gain``: this frame's light
        flicker. ``wb``: white balance gains (R, G, B); None = none. ``eye``: 0 left (or a single camera),
        1 right, the lens a fault set through the environment (SL_SIM2REAL_*) aims at. ``depth`` (the eye's
        distance_to_image_plane, float32 (H, W), may have a row stride) with ``focus`` (lens, focal length in
        pixels, overrides, metres per depth unit) adds the lens's focus blur, when the library has it.
        """
        h, w = int(src.shape[0]), int(src.shape[1])
        stream = wp.get_stream(src.device)
        if self._handle is None:
            wp.launch(_plain_srgb8, dim=(h, w), inputs=[src, dst], device=src.device, stream=stream)
            return True
        params = camera_model_lib.EncodeParams(
            seed=noise_seed(seed), gain=float(gain or 0.0), vignette_inv_f=float(max(vignette_inv_f or 0.0, 0.0)),
            blur_scale=float(blur_scale if motion is not None else 0.0), light_gain=float(light_gain or 1.0),
            white_balance=camera_model_lib.f3(wb or (0.0, 0.0, 0.0)), sharpness=1 if sharpness else 0, edge_noise=1,
            eye=1 if eye == 1 else 0)
        mv = motion.ptr if motion is not None and blur_scale > 0 and tuple(motion.shape) == (h, w, 4) else None
        if (depth is not None and focus is not None and focus.lens != camera_model_lib.LENS_NONE
                and tuple(depth.shape) == (h, w) and camera_model_lib.has_focus_blur()):
            return bool(self._lib.sl_zed_sim2real_encode_device_depth(
                self._handle, src.ptr, int(src.strides[0]), int(src.strides[1]), w, h, dst.ptr, mv, depth.ptr,
                int(depth.strides[0]), ctypes.byref(params), ctypes.byref(focus), stream.cuda_stream))
        return bool(self._lib.sl_zed_sim2real_encode_device(
            self._handle, src.ptr, int(src.strides[0]), int(src.strides[1]), w, h, dst.ptr, mv, ctypes.byref(params),
            stream.cuda_stream))

    def encode_host(self, hdr, *, seed: int = 0, gain: float = None, motion=None, blur_scale: float = 0.0,
                    vignette_inv_f: float = 0.0, sharpness: bool = False, light_gain: float = 1.0, wb=None, eye: int = 0):
        """encode() from host memory (numpy (H, W, 4) float16 -> numpy (H, W, 4) uint8), through the GPU."""
        import numpy as np

        hdr = np.ascontiguousarray(hdr, dtype=np.float16)
        h, w = hdr.shape[:2]
        if self._handle is None:
            src = wp.array(hdr, dtype=wp.float16, device="cpu")
            dst = wp.empty((h, w, 4), dtype=wp.uint8, device="cpu")
            wp.launch(_plain_srgb8, dim=(h, w), inputs=[src, dst], device="cpu")
            return dst.numpy()
        out = np.empty((h, w, 4), np.uint8)
        mot = np.ascontiguousarray(motion, dtype=np.float32) if motion is not None and blur_scale > 0 else None
        params = camera_model_lib.EncodeParams(
            seed=noise_seed(seed), gain=float(gain or 0.0), vignette_inv_f=float(max(vignette_inv_f or 0.0, 0.0)),
            blur_scale=float(blur_scale if mot is not None else 0.0), light_gain=float(light_gain or 1.0),
            white_balance=camera_model_lib.f3(wb or (0.0, 0.0, 0.0)), sharpness=1 if sharpness else 0, edge_noise=1,
            eye=1 if eye == 1 else 0)
        ok = self._lib.sl_zed_sim2real_encode_host(self._handle, hdr.ctypes.data, w, h, out.ctypes.data,
                                                   None if mot is None else mot.ctypes.data, ctypes.byref(params))
        return out if ok else None

    def destroy(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            self._lib.sl_zed_sim2real_encoder_destroy(handle)

    def __del__(self):
        self.destroy()


_ENCODERS = {}


def _shared_encoder(device) -> StreamEncoder:
    key = str(device)
    if key not in _ENCODERS:
        _ENCODERS[key] = StreamEncoder()
    return _ENCODERS[key]


def encode_srgb(hdr, device: str = None, gain: float = None, seed: int = 0, motion=None, blur_scale: float = 0.0,
                focal_px: float = None, mtf: bool = False, light_gain: float = 1.0, wb=None, eye: int = 0,
                depth=None, focus=None):
    """Encode an HdrColor annotator output ((H, W, 4) float16, Warp or numpy) to sRGB RGBA8.

    A CUDA Warp array is encoded on its GPU and returns a new Warp array there, or a numpy array
    when ``device`` is "cpu" (the readback is then 8-bit, half the float16 bytes); host data is
    encoded through the GPU and returns numpy. Returns None when the annotator has not delivered
    an image yet. ``gain`` (analog x digital, i.e. exposure:iso / 100) adds the sensor noise of a
    real ZED X at that gain; None = no noise. ``seed`` must differ per frame (and per eye) for the
    noise to be temporal. ``motion`` (the MotionVectors annotator output, same device) with
    ``blur_scale`` (exposure time over the vectors' time step) adds the camera's motion blur.
    ``focal_px`` (focal length in pixels at this resolution) adds the lens vignetting; None = none.
    ``mtf`` applies the real camera's sharpness. ``light_gain`` scales the scene's light for this
    frame (light flicker, see light_gain_now). ``wb``: white balance gains (R, G, B); None = none.
    ``eye``: 0 left (or a single camera), 1 right (see StreamEncoder.encode). ``depth`` (the eye's
    distance_to_image_plane as a CUDA Warp array, float32 (H, W)) with ``focus``
    (camera_model_lib.DefocusParams) adds the lens's focus blur; it needs the GPU path, so host data
    is encoded without it.
    """
    import numpy as np

    if hdr is None or getattr(hdr, "ndim", 0) != 3 or hdr.shape[2] != 4:
        return None
    kw = dict(seed=seed, gain=gain, blur_scale=blur_scale, vignette_inv_f=1.0 / focal_px if focal_px else 0.0,
              sharpness=mtf, light_gain=light_gain, wb=wb, eye=eye)
    if isinstance(hdr, wp.array) and hdr.device.is_cuda and hdr.dtype == wp.float16:
        if motion is not None and blur_scale > 0 and not isinstance(motion, wp.array):
            motion = wp.array(np.ascontiguousarray(motion, dtype=np.float32), device=hdr.device)
        out = wp.empty(hdr.shape, dtype=wp.uint8, device=hdr.device)
        # the focus blur reads the depth on the device: only a Warp array there can be handed over
        if depth is not None and not (isinstance(depth, wp.array) and depth.device.is_cuda):
            depth = None
        if not _shared_encoder(hdr.device).encode(hdr, out, motion=motion, depth=depth, focus=focus, **kw):
            return None
        return out.numpy() if device is not None and str(device).lower() == "cpu" else out
    host = hdr.numpy() if isinstance(hdr, wp.array) else np.asarray(hdr)
    if motion is not None and isinstance(motion, wp.array):
        motion = motion.numpy()
    return _shared_encoder("host").encode_host(host, motion=motion, **kw)
