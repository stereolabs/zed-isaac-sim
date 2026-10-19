"""ZED Sim2Real for Isaac Lab: the ZED X camera model on camera tensors.

The same camera model the streamed images get (the ``sl_zed_sim2real`` library, see camera_model_lib.py),
for in-process frames: from Isaac Lab's linear HDR output (``"rgb_hdr"``) to the image a real ZED X
outputs, with its auto exposure, auto white balance, sensor noise at the chosen gain, lens vignetting
and sharpness. One auto exposure and white balance per env; both eyes of an env share them (the left
drives, as on the real camera).

The cameras render at a fixed reference exposure (:meth:`ZedSim2Real.prepare_cameras`, once, before
the sensors start) and each env's exposure is applied to its linear image as a gain: the renderer's
HDR image scales linearly with exposure, so this matches rendering each env at its own exposure.

Kit-free (ctypes, and torch at call time)::

    from sl.sensor.camera.zed_sim2real import ZedSim2Real
    cam_cfg = make_camera_cfg(paths["left"], "ZED_X", "SVGA", data_types=["rgb_hdr"])
    sim2real = ZedSim2Real(num_envs, camera_model="ZED_X", resolution="SVGA")
    sim2real.prepare_cameras(stage, left_and_right_prim_paths)   # before sim.reset()
    ...
    rgb_l, rgb_r = sim2real.apply(cam_l.data.output["rgb_hdr"], cam_r.data.output["rgb_hdr"], dt=1 / 30)

Faults set through the environment (SL_SIM2REAL_SOIL, SL_SIM2REAL_EYE_EV, ...; see the library's
header) apply here too.
"""
from __future__ import annotations

import ctypes
from typing import Iterable, Optional

from . import camera_model_lib

# Exposure the cameras render at (exposure:time, s; gain 1); each env's auto exposure scales from it.
REFERENCE_EXPOSURE_S = 1e-3


def _torch(t):
    """A torch tensor from a tensor or an Isaac Lab output (ProxyArray, ``.torch``)."""
    return t.torch if hasattr(t, "torch") else t


def _srgb8(linear):
    """Plain sRGB of a linear (..., 3) float tensor, as uint8 (no camera model)."""
    import torch

    v = linear.float().clamp(0.0, 1.0)
    v = torch.where(v <= 0.0031308, 12.92 * v, 1.055 * v.clamp(min=0.0031308) ** (1 / 2.4) - 0.055)
    return (v * 255.0 + 0.5).clamp(0, 255).to(torch.uint8)


class ZedSim2Real:
    """The ZED X camera model on batches of Isaac Lab camera frames.

    Args:
        num_envs: frames per batch (one auto exposure / white balance each).
        camera_model, resolution: the ZED camera and resolution the sensors render (for the lens falloff).
        fps: the camera's frame rate (auto exposure ranges and dynamics).
        auto_exposure, auto_white_balance, sensor_noise, vignetting, camera_sharpness: the camera
            model's effects, as on the ZED Camera Helper node.
        seed: decorrelates this instance's noise from other instances'.
    """

    def __init__(self, num_envs: int = 1, camera_model: str = "ZED_X", resolution: str = "SVGA",
                 fps: float = 30.0, *, auto_exposure: bool = True, auto_white_balance: bool = True,
                 sensor_noise: bool = True, vignetting: bool = True, camera_sharpness: bool = True, seed: int = 0):
        self._lib = camera_model_lib.lib()
        self.num_envs = int(num_envs)
        self.fps = float(fps)
        self.auto_exposure = bool(auto_exposure)
        self.auto_white_balance = bool(auto_white_balance)
        self.sensor_noise = bool(sensor_noise)
        self.camera_sharpness = bool(camera_sharpness)
        self.seed = int(seed)
        self._frame = 0
        self._inv_f = 0.0
        if vignetting:
            from .utils import LensType, get_lens_type, get_pinhole_parameters

            params = get_pinhole_parameters(camera_model, resolution) or {}
            if params.get("focal_length_px") and get_lens_type(camera_model) != LensType.FISHEYE:
                self._inv_f = 1.0 / float(params["focal_length_px"])
        self._encoder = None
        self._meters, self._ae, self._awb = [], [], []
        self._buf = self._out = None
        from .auto_exposure import AeLimits, Photometry, ZedAutoExposure, zedx_image_level

        self._photometry = Photometry()
        self._target = zedx_image_level()
        if self._lib is None:
            return
        from .auto_white_balance import ZedAutoWhiteBalance

        self._encoder = self._lib.sl_zed_sim2real_encoder_create()
        limits = AeLimits(fps=self.fps)
        for _ in range(self.num_envs):
            self._meters.append(self._lib.sl_zed_sim2real_meter_create(0))
            self._ae.append(ZedAutoExposure(limits, photometry=self._photometry))
            self._awb.append(ZedAutoWhiteBalance())

    @property
    def ok(self) -> bool:
        """False when the library is unavailable: apply() then returns plain sRGB."""
        return self._encoder is not None

    def prepare_cameras(self, stage, camera_prim_paths: Iterable[str], fstop: Optional[float] = None) -> int:
        """Render the cameras at the reference exposure, with the ZED X's responsivity (so the auto exposure
        picks the real camera's exposure time and gain for the scene's light). Call once, before the sensors
        start. Returns the number of camera prims set."""
        from pxr import Sdf

        from .auto_exposure import RTX_AUTO_EXPOSURE_ATTR, zedx_responsivity

        n = 0
        for path in camera_prim_paths:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue
            f_attr = prim.GetAttribute("exposure:fStop")
            f = float(fstop or (f_attr.Get() if f_attr and f_attr.Get() else 5.0))
            values = {"exposure:time": REFERENCE_EXPOSURE_S, "exposure:iso": 100.0,
                      "exposure:responsivity": zedx_responsivity(self._target, f)}
            for name, value in values.items():
                attr = prim.GetAttribute(name) or prim.CreateAttribute(name, Sdf.ValueTypeNames.Float)
                attr.Set(float(value))
            rtx_ae = prim.GetAttribute(RTX_AUTO_EXPOSURE_ATTR) or prim.CreateAttribute(RTX_AUTO_EXPOSURE_ATTR,
                                                                                         Sdf.ValueTypeNames.Bool)
            rtx_ae.Set(False)
            self._photometry.fstop = f
            self._photometry.responsivity = values["exposure:responsivity"]
            n += 1
        return n

    def exposure(self, env: int = 0):
        """An env's auto exposure state (exposure_s, analog_gain, digital_gain, scene_lux, ...); None without
        the library."""
        return self._ae[env].state if self.ok else None

    def white_balance(self, env: int = 0):
        """An env's white balance gains (R, G, B); None before the first metered frame or without the library."""
        return self._awb[env].gains if self.ok else None

    def apply(self, hdr_left, hdr_right=None, dt: Optional[float] = None):
        """Encode one batch. ``hdr_left`` / ``hdr_right``: Isaac Lab ``"rgb_hdr"`` outputs, (N, H, W, 3 or 4)
        float on the GPU, rendered at the reference exposure. ``dt``: time since the previous batch (the
        camera's frame period by default). Returns ``(rgb_left, rgb_right)``, (N, H, W, 3) uint8 on the same
        device (``rgb_right`` None without ``hdr_right``)."""
        import torch

        left = _torch(hdr_left)
        right = _torch(hdr_right) if hdr_right is not None else None
        if left.dim() == 3:
            left = left.unsqueeze(0)
            right = right.unsqueeze(0) if right is not None else None
        n, h, w = int(left.shape[0]), int(left.shape[1]), int(left.shape[2])
        if n != self.num_envs:
            raise ValueError(f"ZedSim2Real was made for {self.num_envs} envs, got a batch of {n}")
        dt = float(dt) if dt else 1.0 / self.fps
        if self.ok and self.auto_exposure:
            scale = torch.tensor([ae.state.total / REFERENCE_EXPOSURE_S for ae in self._ae], device=left.device,
                                 dtype=torch.float32)
        else:
            scale = torch.ones(n, device=left.device, dtype=torch.float32)
        outs = []
        for eye, hdr in enumerate((left, right)):
            if hdr is None:
                outs.append(None)
                continue
            buf = self._scaled(hdr, scale, eye)
            if not self.ok:
                outs.append(_srgb8(buf[..., :3]))
                continue
            outs.append(self._encode(buf, eye, n, h, w))
            if eye == 0:
                self._meter(buf, n, h, w, dt)
        self._frame += 1
        return outs[0], outs[1]

    # ---- internals ---------------------------------------------------------------------------
    def _scaled(self, hdr, scale, eye):
        """The eye's frames at each env's exposure, as the RGBA float16 the library reads."""
        import torch

        n, h, w = int(hdr.shape[0]), int(hdr.shape[1]), int(hdr.shape[2])
        if self._buf is None or tuple(self._buf.shape[1:4]) != (n, h, w) or self._buf.device != hdr.device:
            self._buf = torch.empty((2, n, h, w, 4), dtype=torch.float16, device=hdr.device)
            self._buf[..., 3] = 1.0
            self._out = torch.empty((2, n, h, w, 4), dtype=torch.uint8, device=hdr.device)
        buf = self._buf[eye]
        buf[..., :3] = (hdr[..., :3].float() * scale.view(n, 1, 1, 1)).clamp_(0.0, 65000.0)
        return buf

    @staticmethod
    def _stream(t):
        import torch

        return ctypes.c_void_p(torch.cuda.current_stream(t.device).cuda_stream)

    def _encode(self, buf, eye, n, h, w):
        out = self._out[eye]
        stream = self._stream(buf)
        for i in range(n):
            ae, awb = self._ae[i].state, self._awb[i].gains
            if not self.sensor_noise:
                gain = 0.0
            else:
                gain = ae.analog_gain * ae.digital_gain if self.auto_exposure else 1.0
            wb = awb if (self.auto_white_balance and awb) else (0.0, 0.0, 0.0)
            p = camera_model_lib.EncodeParams(
                seed=(self._frame * 7919 + (self.seed * 4096 + i * 2 + eye) * 104729) & 0x7FFFFFFF,
                gain=float(gain), vignette_inv_f=float(self._inv_f), blur_scale=0.0, light_gain=1.0,
                white_balance=camera_model_lib.f3(wb), sharpness=1 if self.camera_sharpness else 0, edge_noise=1,
                eye=eye)
            ok = self._lib.sl_zed_sim2real_encode_device(self._encoder, buf[i].data_ptr(), w * 8, 8, w, h,
                                                         out[i].data_ptr(), None, ctypes.byref(p), stream)
            if not ok:
                raise RuntimeError("ZED X camera model: GPU encode failed")
        return out[..., :3].contiguous()

    def _meter(self, buf, n, h, w, dt):
        """Meter the left eye's frames; the auto exposure and white balance act on the previous batch's."""
        stream = self._stream(buf)
        for i in range(n):
            awb = self._awb[i]
            wb = awb.gains if (self.auto_white_balance and awb.gains) else (0.0, 0.0, 0.0)
            view = camera_model_lib.MeterView(vignette_inv_f=float(self._inv_f), white_balance=camera_model_lib.f3(wb),
                                              neutral_ref=camera_model_lib.f2(awb.neutral),
                                              roi=camera_model_lib.f4((0.0, 0.0, 0.0, 0.0)))
            img = camera_model_lib.MeterImage(data=buf[i].data_ptr(), row_stride=w * 8, pixel_stride=8,
                                              element_bytes=2, w=w, h=h)
            stats = camera_model_lib.MeterStats()
            if not self._lib.sl_zed_sim2real_meter_update(self._meters[i], ctypes.byref(img), ctypes.byref(view),
                                                          self._frame, stream, ctypes.byref(stats)):
                continue  # the first result arrives one batch later
            if self.auto_exposure:
                self._ae[i].update(stats, dt)
            if self.auto_white_balance:
                awb.update_stats(stats, dt, self._ae[i].state.error_ev or 0.0)

    def close(self) -> None:
        """Free the library's buffers (also on garbage collection)."""
        if self._encoder is None:
            return
        for m in self._meters:
            self._lib.sl_zed_sim2real_meter_destroy(m)
        self._meters = []
        self._lib.sl_zed_sim2real_encoder_destroy(self._encoder)
        self._encoder = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
