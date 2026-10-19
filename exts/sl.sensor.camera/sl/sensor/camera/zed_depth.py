import os
import time
from datetime import datetime

import carb
import omni.kit.app
import omni.usd

# Prims are looked up with plain USD calls: isaacsim.core.utils is not in Isaac Lab's app.
try:
    import omni.replicator.core as rep
    from omni.replicator.core.scripts.utils import viewport_manager
except ImportError:
    rep = viewport_manager = None

from .frames import CapturedFrame, PngFrameWriter, depth_to_2d, to_numpy
from .optics import apply_camera_optics
from .utils import (LensType, get_camera_subpaths, get_lens_type, get_pinhole_parameters, get_resolution,
                    is_stereo_camera, resolve_resolution_token)

_WARMUP_FRAMES = 10


class ZEDDepthCamera:
    """
    SDK-free capture from a ZED camera using Isaac Sim's renderer.

    Uses CameraLeft directly for color and, on a stereo model with ``save_depth`` set,
    ``distance_to_image_plane`` for depth. For stereo models the right image is captured too
    (depth stays left-referenced). Color is sRGB-encoded from the linear ``HdrColor`` on the GPU,
    exactly like the streamed images (see stream_encoding.py); ``encoding="linear"`` keeps the
    legacy ``rgb`` (LdrColor) annotator, which is the RTX tonemapped image. With ``sensor_noise``
    the sRGB images carry a real ZED X's sensor noise at the camera's gain (exposure:iso / 100),
    with ``vignetting`` its lens falloff, with ``camera_sharpness`` its sharpness and with
    ``auto_white_balance`` its white balance (both eyes share the left image's), as the stream does (the
    stream's exposure-time motion blur is not applied here). Depth is a stereo
    feature: on a mono model ``save_depth`` is ignored. Whenever depth is off the annotator is
    never attached, ``get_depth()`` returns None, and this is an image-only capture. No
    additional camera prim is created.
    Independent of the ZED SDK streaming pipeline.

    Frames go wherever ``frame_writer`` sends them; the default writes numbered PNGs. A writer
    owns the file names and may skip a frame, so this class stays out of that decision.

    Call try_initialize() each frame until it returns True.
    """

    def __init__(
        self,
        camera_prim_path,
        camera_model="ZED_X",
        resolution="HD1200",
        device="cuda",
        enable_save=False,
        output_dir="",
        save_depth=True,
        frame_writer=None,
        encoding="srgb",
        sensor_noise=True,
        vignetting=True,
        camera_sharpness=True,
        auto_white_balance=True,
    ):
        self._camera_prim_path = camera_prim_path
        self._camera_model = camera_model
        self._device = device
        if encoding not in ("srgb", "linear"):
            carb.log_warn(f"[ZED][Depth] Unknown encoding '{encoding}', using sRGB.")
            encoding = "srgb"
        self._encoding = encoding
        self._sensor_noise = bool(sensor_noise)
        self._vignetting = bool(vignetting)
        self._camera_sharpness = bool(camera_sharpness)
        self._auto_white_balance = bool(auto_white_balance) and encoding == "srgb"
        self._wb_meter = None
        self._wb = None
        self._wb_frame = None
        self._noise_reads = 0
        self._valid = False
        self._init_failed = False
        self._enable_save = enable_save
        self._output_dir = output_dir
        self._frame_count = 0
        self._last_render_frame = 0
        # Depth is a stereo feature: a mono ZED X One has no depth, so save_depth is ignored for
        # mono models. It is also the expensive part of a capture (an extra annotator on the
        # render product plus a float32 EXR per frame, which dominates I/O), so it can be turned
        # off for stereo too. Either way the annotator is then never attached, and get_depth()
        # returns None.
        self._save_depth = bool(save_depth) and is_stereo_camera(camera_model)
        if save_depth and not self._save_depth:
            carb.log_info(f"[ZED][Depth] '{camera_model}' is a mono camera and has no depth; "
                          f"capturing images only.")

        self._frame_writer = frame_writer if frame_writer is not None else PngFrameWriter()
        self._sim_time_annot = None
        self._camera_params_annot = None
        self._fallback_clock0 = None

        self._tick = 0
        self._update_sub = None
        self._rgb_annot = None
        self._depth_annot = None
        self._rp = None
        self._rp_path = None
        # Right eye (stereo models only).
        self._is_stereo = is_stereo_camera(camera_model)
        self._cam_right_path = None
        self._rgb_right_annot = None
        self._rp_right = None
        self._rp_right_path = None

        # Kept alongside the resolved [w, h]: the spec tables are keyed by the token.
        self._resolution_token = resolve_resolution_token(camera_model, resolution)
        self._resolution = get_resolution(camera_model, self._resolution_token)
        if self._resolution is None:
            carb.log_error(f"[ZED][Depth] Unknown resolution '{resolution}' for model '{camera_model}'")
            self._init_failed = True
            return

        # "left" resolves to CameraLeft for stereo models, Camera for mono.
        subpaths = get_camera_subpaths(camera_model)
        self._cam_left_path = f"{camera_prim_path}/{subpaths['left']}"
        stage = omni.usd.get_context().get_stage()

        if not stage.GetPrimAtPath(self._cam_left_path).IsValid():
            carb.log_error(f"[ZED][Depth] Camera prim not found at {self._cam_left_path}")
            self._init_failed = True
            return

        if self._is_stereo:
            self._cam_right_path = f"{camera_prim_path}/{subpaths['right']}"
            if not stage.GetPrimAtPath(self._cam_right_path).IsValid():
                carb.log_error(f"[ZED][Depth] Right camera prim not found at {self._cam_right_path}")
                self._init_failed = True
                return

        carb.log_info(
            f"[ZED][Depth] Created for {camera_prim_path} "
            f"({camera_model}, {self._resolution[0]}x{self._resolution[1]})"
        )

    def try_initialize(self):
        if self._valid:
            return True
        if self._init_failed:
            return False

        self._tick += 1

        if self._tick < _WARMUP_FRAMES:
            return False

        if self._tick == _WARMUP_FRAMES:
            try:
                self._do_init()
            except Exception as e:
                import traceback
                carb.log_error(f"[ZED][Depth] Init failed: {e}\n{traceback.format_exc()}")
                self._init_failed = True
                return False

        self._valid = True

        if self._enable_save and self._output_dir:
            if not self._frame_writer.owns_output_dir:
                date_folder = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                self._output_dir = os.path.join(self._output_dir, date_folder)
                os.makedirs(self._output_dir, exist_ok=True)
            self._update_sub = (
                omni.kit.app.get_app()
                .get_update_event_stream()
                .create_subscription_to_pop(self._on_update)
            )
            carb.log_info(f"[ZED][Depth] Saving frames under {self._output_dir}")

        carb.log_info(
            f"[ZED][Depth] Ready at frame {self._tick}: "
            f"{self._resolution[0]}x{self._resolution[1]} from {self._cam_left_path}"
        )
        return True

    def _apply_optics(self, cam_path):
        """Author the ZED model's field of view and lens on a camera prim.

        The same call the streaming path makes (ZEDAnnotator.init_camera).
        """
        prim = omni.usd.get_context().get_stage().GetPrimAtPath(cam_path)
        if prim and prim.IsValid():
            apply_camera_optics(prim, self._camera_model, self._resolution_token)

    def _color_annotator(self):
        # sRGB: HdrColor is fetched on the GPU whatever the capture device - the encode runs
        # there and only the 8-bit result is read back (see get_rgba).
        if self._encoding == "srgb":
            return rep.AnnotatorRegistry.get_annotator("HdrColor", device="cuda")
        return rep.AnnotatorRegistry.get_annotator("rgb", device=self._device)

    def _camera_gain(self):
        """Total sensor gain the left camera renders with (exposure:iso / 100), for the noise."""
        prim = omni.usd.get_context().get_stage().GetPrimAtPath(self._cam_left_path)
        attr = prim.GetAttribute("exposure:iso") if prim else None
        iso = attr.Get() if attr else None
        return float(iso) / 100.0 if iso else 1.0

    def _noise_seed(self, eye):
        """Per rendered frame and eye: re-reading a frame keeps its noise, a new frame gets new
        noise (the frame counter advances only on saved frames)."""
        rp = self._rp if eye == 0 else self._rp_right
        try:
            frame = int(rp.hydra_texture.get_frame_info().get("frame_number") or 0)
        except Exception:
            frame = 0
        if not frame:  # no frame info: fall back to one new pattern per read
            self._noise_reads += 1
            frame = self._noise_reads
        return frame * 2 + eye

    def _white_balance(self):
        """The white balance gains for the frame the left annotator holds, None when off.

        The stream's auto white balance (auto_white_balance.py), metered on the left image: it follows
        the scene from frame to frame, and the first frame read is balanced at once."""
        from . import camera_model_lib
        if not self._auto_white_balance or self._rgb_annot is None or not camera_model_lib.available():
            return None
        from .auto_white_balance import ZedAutoWhiteBalance
        from .hdr_meter import HdrExposureMeter
        if self._wb_meter is None:
            self._wb_meter = HdrExposureMeter(self._rp_path, annotator=self._rgb_annot)
            self._wb = ZedAutoWhiteBalance()
        try:
            frame = int(self._rp.hydra_texture.get_frame_info().get("frame_number") or 0) or None
        except Exception:
            frame = None
        self._wb_meter.wb = self._wb.gains or (1.0, 1.0, 1.0)
        self._wb_meter.neutral_ref = self._wb.neutral
        stats = self._wb_meter.update(frame)
        if stats is None:  # the meter answers one read late: for the first one, wait for it
            self._wb_meter.wait()
            stats = self._wb_meter.update(frame)
        if stats is not None and stats.frame != self._wb_frame:
            self._wb_frame = stats.frame
            self._wb.update_stats(stats, 1.0 / 30.0, 0.0)
        return self._wb.gains

    def _color(self, annot, eye=0):
        data = annot.get_data()
        if self._encoding != "srgb":
            return data
        from .stream_encoding import encode_srgb
        focal_px, mtf, wb = self._vignette_focal_px(), self._camera_sharpness, self._white_balance()
        if not self._sensor_noise:
            return encode_srgb(data, self._device, focal_px=focal_px, mtf=mtf, wb=wb, eye=eye)
        return encode_srgb(data, self._device, gain=self._camera_gain(), seed=self._noise_seed(eye), focal_px=focal_px,
                           mtf=mtf, wb=wb, eye=eye)

    def _vignette_focal_px(self):
        """Focal length in pixels for the lens vignetting; None when off or for fisheye lenses."""
        if not self._vignetting or get_lens_type(self._camera_model) == LensType.FISHEYE:
            return None
        params = get_pinhole_parameters(self._camera_model, self._resolution_token)
        return float(params["focal_length_px"]) if params and params.get("focal_length_px") else None

    def _do_init(self):
        # Match the images to the intrinsics before any render product is built from them.
        self._apply_optics(self._cam_left_path)
        if self._is_stereo:
            self._apply_optics(self._cam_right_path)

        prim_name = self._camera_prim_path.split("/")[-1]
        self._rp = viewport_manager.get_render_product(
            self._cam_left_path, self._resolution, False, f"{prim_name}_zed_depth_rp"
        )
        self._rp_path = self._rp.hydra_texture.get_render_product_path()

        self._rgb_annot = self._color_annotator()
        self._rgb_annot.attach(self._rp_path)

        if self._save_depth:
            self._depth_annot = rep.AnnotatorRegistry.get_annotator(
                "distance_to_image_plane", device=self._device
            )
            self._depth_annot.attach(self._rp_path)

        if self._frame_writer.needs_pose:
            # Reports the simulation time OF THE RENDERED FRAME, not of the current app
            # tick. ZED cameras render at their target FPS under Isaac Sim's multi-tick
            # rendering, so a plain World.current_time read would be offset from the image
            # being saved by the render pipeline latency.
            self._sim_time_annot = rep.AnnotatorRegistry.get_annotator("IsaacReadSimulationTime")
            self._sim_time_annot.initialize(resetOnStop=True)
            self._sim_time_annot.attach(self._rp_path)
            # Pose of the frame the annotators hold. The stage has already moved on by the time
            # a frame is read back, so it would place the camera a frame ahead of its image.
            self._camera_params_annot = rep.AnnotatorRegistry.get_annotator("CameraParams")
            self._camera_params_annot.attach(self._rp_path)

        if self._is_stereo:
            self._rp_right = viewport_manager.get_render_product(
                self._cam_right_path, self._resolution, False, f"{prim_name}_zed_depth_rp_right"
            )
            self._rp_right_path = self._rp_right.hydra_texture.get_render_product_path()
            self._rgb_right_annot = self._color_annotator()
            self._rgb_right_annot.attach(self._rp_right_path)

    def _on_update(self, event):
        if self._valid and self._enable_save:
            self.save_frame()

    def _render_view_transform(self):
        """World-to-camera of the frame the annotators hold, or None when it is unavailable."""
        if self._camera_params_annot is None:
            return None
        data = self._camera_params_annot.get_data()
        view = data.get("cameraViewTransform") if data else None
        return view if view is not None and len(view) == 16 else None

    def _sim_time(self):
        """Simulation time of the frame the annotators currently hold, in seconds.

        Falls back to a monotonic clock when the annotator reports 0 - some Isaac builds do,
        and OgnZEDSimCameraNode.cpp carries the same workaround. Without it every frame would
        be stamped with the same time.
        """
        if self._sim_time_annot is not None:
            data = self._sim_time_annot.get_data()
            if data:
                sim_time = float(data["simulationTime"])
                if sim_time > 0.0:
                    return sim_time
        if self._fallback_clock0 is None:
            self._fallback_clock0 = time.monotonic()
            carb.log_warn("[ZED][Depth] Simulation time reads 0; frame timestamps fall "
                          "back to wall-clock elapsed time.")
        return time.monotonic() - self._fallback_clock0

    def get_rgba(self):
        if not self._valid:
            return None
        return self._color(self._rgb_annot)

    def get_rgba_right(self):
        if not self._valid or self._rgb_right_annot is None:
            return None
        return self._color(self._rgb_right_annot, eye=1)

    def get_depth(self):
        """Renderer depth, or None when depth is off (save_depth=False, or a mono model)."""
        if not self._valid or self._depth_annot is None:
            return None
        return self._depth_annot.get_data()

    def save_frame(self, output_dir=None):
        if not self._valid:
            return False

        out = output_dir or self._output_dir
        if not out:
            return False

        # The render product can render less often than the app updates (its camera's
        # omni:sensor:tickRate): each rendered frame goes to the writer once. Without frame info,
        # every call does.
        try:
            rendered = int(self._rp.hydra_texture.get_frame_info().get("frame_number") or 0)
        except Exception:
            rendered = 0
        if rendered and rendered == self._last_render_frame:
            return False

        rgba = to_numpy(self.get_rgba())
        if rgba is None or rgba.ndim != 3:
            return False

        # None throughout when save_depth is off; every depth step below is then skipped.
        depth = depth_to_2d(to_numpy(self.get_depth())) if self._save_depth else None
        if self._save_depth and (depth is None or depth.ndim != 2):
            return False

        # Right eye (stereo only). Skipped if not yet ready.
        rgba_right = to_numpy(self.get_rgba_right())
        if rgba_right is not None and rgba_right.ndim != 3:
            rgba_right = None

        frame = CapturedFrame(
            index=self._frame_count,
            output_dir=out,
            left=rgba,
            right=rgba_right,
            depth=depth,
        )
        if self._frame_writer.needs_pose:
            frame.sim_time = self._sim_time()
            frame.view_transform = self._render_view_transform()

        self._last_render_frame = rendered
        try:
            written = self._frame_writer.write(frame)
        except Exception:
            # Per-frame code: never take the capture loop down with the writer.
            import traceback
            carb.log_error(f"[ZED][Depth] Saving the frame failed:\n{traceback.format_exc()}")
            return False

        # A skipped frame leaves its index unspent, so the numbering stays gap-free.
        if written:
            self._frame_count += 1
        return bool(written)

    def is_valid(self):
        return self._valid

    def destroy(self):
        if self._frame_writer is not None:
            try:
                self._frame_writer.close()
            except Exception:
                import traceback
                carb.log_error(f"[ZED][Depth] Closing the frame writer failed:\n{traceback.format_exc()}")
            self._frame_writer = None

        for annot in ("_sim_time_annot", "_camera_params_annot"):
            if getattr(self, annot) is not None:
                try:
                    getattr(self, annot).detach(self._rp_path)
                except Exception:
                    pass
                setattr(self, annot, None)

        if self._update_sub is not None:
            self._update_sub.unsubscribe()
            self._update_sub = None

        if self._wb_meter is not None:
            try:
                self._wb_meter.destroy()
            except Exception:
                pass
            self._wb_meter = None

        if self._rgb_annot is not None:
            try:
                self._rgb_annot.detach(self._rp_path)
            except Exception:
                pass
            self._rgb_annot = None

        if self._depth_annot is not None:
            try:
                self._depth_annot.detach(self._rp_path)
            except Exception:
                pass
            self._depth_annot = None

        if self._rgb_right_annot is not None:
            try:
                self._rgb_right_annot.detach(self._rp_right_path)
            except Exception:
                pass
            self._rgb_right_annot = None

        if self._rp is not None:
            try:
                self._rp.destroy()
            except Exception:
                pass
            self._rp = None

        if self._rp_right is not None:
            try:
                self._rp_right.destroy()
            except Exception:
                pass
            self._rp_right = None

        self._rp_path = None
        self._rp_right_path = None
        self._valid = False
        carb.log_info(f"[ZED][Depth] Destroyed for {self._camera_prim_path}")
