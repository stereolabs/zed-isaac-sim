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
from . import frame_pose, sdk_virtual_camera
from .optics import apply_camera_optics, setup_virtual_camera
from .utils import (LensType, get_camera_subpaths, get_lens_type, get_pinhole_parameters, get_resolution,
                    is_stereo_camera, resolve_resolution_token)

_WARMUP_FRAMES = 10
# exposure:time when the camera prim does not author it: the render product's default
_DEFAULT_EXPOSURE_S = 0.02
# Frames the colour annotator may compute before the post-render graph hands one over; past that, frames
# are read on each app update instead.
_FIRST_GRAPH_FRAME_WAIT = 30
# Annotator node outputs that fire once the node holds a frame (IsaacReadSimulationTime's is execOut).
_EXEC_OUTPUTS = ("outputs:exec", "outputs:execOut")

# ZED_CaptureFrame node path -> the capture it hands frames to
_frame_nodes = {}


def save_rendered_frame(node_path, frame_id):
    """Save the frame the post-render graph just produced for the capture that owns ``node_path``.

    Called by its ZED_CaptureFrame node, once per frame the camera renders, while the annotators hold that
    frame. ``frame_id`` is the frame's (numerator, denominator) reference time. Returns whether it was written.
    """
    capture = _frame_nodes.get(node_path)
    return capture._save_rendered_frame(frame_id) if capture is not None else False


class ZEDDepthCamera:
    """
    SDK-free capture from a ZED camera using Isaac Sim's renderer.

    Uses CameraLeft directly for color and, on a stereo model with ``save_depth`` set,
    ``distance_to_image_plane`` for depth. For stereo models the right image is captured too
    (depth stays left-referenced). Color is sRGB-encoded from the linear ``HdrColor`` on the GPU,
    like the streamed images (see stream_encoding.py); ``encoding="linear"`` keeps the legacy
    ``rgb`` (LdrColor) annotator, which is the RTX tonemapped image. ``apply_zed_sim2real`` is the
    camera model's master switch, as on the ZED Camera Helper node: off, the render is encoded as
    plain sRGB with none of the effects below. With ``sensor_noise`` the sRGB images carry a real
    ZED X's sensor noise at the camera's gain (exposure:iso / 100), with ``vignetting`` its lens
    falloff, with ``camera_sharpness`` its sharpness and with ``auto_white_balance`` its white
    balance, as the stream does. The auto white balance and auto exposure meter the right eye of a
    stereo camera and apply to both eyes.
    With ``motion_blur`` and ``fps`` the images also carry the stream's motion blur over the exposure time
    (exposure:time). ``fps`` is the rate the camera renders at (e.g. 1 / rendering_dt, or its
    omni:sensor:tickRate): the motion vectors span one rendered frame, so a wrong rate scales the
    blur by the same ratio. Without ``fps`` the camera's own ``omni:sensor:tickRate`` is used, and
    without that the app's update rate, which a camera without a tick rate renders at; an app that
    updates on the wall clock has none, and the images are then neither blurred nor auto-exposed.
    Given ``fps`` the camera also renders at that rate, as a streamed one does. Without ``auto_exposure``
    the blur follows whatever exposure:time the camera prim carries, which is the render product's
    0.02 s unless the scene authors one: that is most of a frame at 30 fps, far longer than a real
    ZED X holds a lit scene. With ``auto_exposure`` (the default) the camera runs the stream's ZED X
    auto exposure (exposure_loop.py): it sets both eyes' exposure:time and exposure:iso, which the
    noise and the blur follow; ``auto_exposure_limits`` (an auto_exposure.AeLimits) narrows its
    ranges, and ``exposure_state`` says when it has converged. Off, the camera keeps its prims' own
    exposure. With ``focus_blur`` the lens's fixed focus blurs what is closer (ZED X, X Mini and
    X One GS / S lenses only; off by default, as on the stream), which renders a depth image per eye
    while it is on. The scene lights' flicker follows the ``lightFlickerStd`` setting, as it does on
    the stream, and is off unless that setting is set. On a mono model ``save_depth`` is ignored.
    Whenever depth is off the annotator is never attached, ``get_depth()`` returns None, and this is
    an image-only capture. No additional camera prim is created.

    Frames go wherever ``frame_writer`` sends them; the default writes numbered PNGs. A writer
    owns the file names and may skip a frame, so this class stays out of that decision.

    With ``enable_save`` every frame the camera renders is saved from the post-render graph, as the
    stream's frames are sent, also when one app update finishes two frames. A script that calls
    save_frame() itself gets the frame the annotators hold at that moment, so of two frames finished
    in one update it saves the second only.

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
        camera_index=-1,
        auto_white_balance=True,
        motion_blur=True,
        fps=None,
        auto_exposure=True,
        auto_exposure_limits=None,
        focus_blur=False,
        apply_zed_sim2real=True,
    ):
        self._camera_prim_path = camera_prim_path
        self._camera_model = camera_model
        self._device = device
        if encoding not in ("srgb", "linear"):
            carb.log_warn(f"[ZED][Depth] Unknown encoding '{encoding}', using sRGB.")
            encoding = "srgb"
        self._encoding = encoding
        # The camera model's master switch, as on the ZED Camera Helper node: off, the render is
        # encoded as plain sRGB with none of the effects below.
        self._apply_sim2real = bool(apply_zed_sim2real) and encoding == "srgb"
        self._sensor_noise = bool(sensor_noise) and self._apply_sim2real
        self._vignetting = bool(vignetting) and self._apply_sim2real
        self._camera_sharpness = bool(camera_sharpness) and self._apply_sim2real
        self._auto_white_balance = bool(auto_white_balance) and self._apply_sim2real
        self._wb_meter = None
        self._wb = None
        self._wb_frame = None
        if fps is not None and not fps > 0:
            carb.log_warn(f"[ZED][Depth] fps must be the camera's render rate in frames per second, "
                          f"got {fps!r}; the camera's own tick rate is used instead.")
            fps = None
        # fps drives the motion blur (the vectors span one rendered frame) and the auto exposure's
        # ranges, and caps the render rate as it does on a streamed camera. Without it, a camera that
        # already carries omni:sensor:tickRate (one a streamer or an earlier capture set up) lends it,
        # and a camera without one renders once per app update.
        self._fps_given = float(fps) if fps else None
        self._fps = self._fps_given or self._tick_rate(camera_prim_path, camera_model)
        if self._fps is None and self._apply_sim2real and (motion_blur or auto_exposure):
            self._fps = self._app_update_rate()
            if self._fps is None:
                carb.log_warn("[ZED][Depth] Auto exposure and motion blur are off: they need the camera's render "
                              "rate. Pass fps, give the camera an omni:sensor:tickRate, or run the app at a fixed "
                              "update rate.")
            else:
                carb.log_info(f"[ZED][Depth] {camera_prim_path} renders once per app update, at {self._fps:g} "
                              "frames a second, for its auto exposure and motion blur.")
        self._motion_blur = bool(motion_blur) and self._apply_sim2real and self._fps is not None
        self._motion_annot = None
        self._motion_right_annot = None
        self._auto_exposure = bool(auto_exposure) and self._apply_sim2real and self._fps is not None
        self._exposure_limits = auto_exposure_limits
        self._exposure_loop = None
        self._focus_blur = bool(focus_blur) and self._apply_sim2real
        self._focus_annot = None
        self._focus_right_annot = None
        self._focus_params = None
        self._focus_warned = False
        self._light_frame = None
        self._light_value = 1.0
        self._noise_reads = 0
        self._valid = False
        self._init_failed = False
        self._enable_save = enable_save
        self._output_dir = output_dir
        self._frame_count = 0
        self._last_render_frame = 0
        self._last_stamp = None
        # The post-render graph nodes that hand over each rendered frame (sync gate, ZED_CaptureFrame);
        # none when frames are read on each app update.
        self._frame_graph = None
        self._frame_node_paths = []
        self._graph_frames = 0  # frames the graph handed over so far
        self._graph_frame = None  # number of the frame being saved from the graph
        self._color_computes = None  # the colour annotator's compute count when the graph was hooked
        # Depth is the expensive part of a capture (an extra annotator on the render product plus a
        # float32 EXR per frame, which dominates I/O), so save_depth can turn it off.
        self._save_depth = bool(save_depth) and is_stereo_camera(camera_model)
        if save_depth and not self._save_depth:
            carb.log_info(f"[ZED][Depth] '{camera_model}' is a mono camera and has no depth; "
                          f"capturing images only.")

        self._frame_writer = frame_writer if frame_writer is not None else PngFrameWriter()
        self._sim_time_annot = None
        self._camera_params_annot = None
        self._camera_poses = None
        self._fallback_clock0 = None
        # SDK virtual camera (virtual mode), rendered with the calibration the SDK generates
        self._camera_index = camera_index
        self._virtual_camera = None

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
            except sdk_virtual_camera.VirtualCameraError as e:
                carb.log_error(f"[ZED][Depth] [{self._camera_prim_path}] {e}")
                self._init_failed = True
                return False
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
            self._hook_frame_node()
            # Reads the frames when the graph does not hand them over, and watches that it does.
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
            apply_camera_optics(prim, self._camera_model, self._resolution_token, fps=self._fps_given)

    def _color_annotator(self):
        # sRGB: HdrColor is fetched on the GPU whatever the capture device: the encode runs
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

    @staticmethod
    def _tick_rate(camera_prim_path, camera_model):
        """The camera's authored render rate (omni:sensor:tickRate), None when it has none."""
        try:
            left = f"{camera_prim_path}/{get_camera_subpaths(camera_model)['left']}"
            prim = omni.usd.get_context().get_stage().GetPrimAtPath(left)
            attr = prim.GetAttribute("omni:sensor:tickRate") if prim else None
            rate = attr.Get() if attr else None
            return float(rate) if rate and float(rate) > 0 else None
        except Exception:
            return None

    @staticmethod
    def _app_update_rate():
        """The app's update rate (Hz), None when it updates on the wall clock."""
        try:
            from .retime import current_timing
            return current_timing()[1]
        except Exception as exc:
            carb.log_warn(f"[ZED][Depth] Could not read the app's update rate: {exc!r}")
            return None

    def _exposure_time(self):
        """The exposure time the left camera renders with (exposure:time; the render product's 0.02 s)."""
        prim = omni.usd.get_context().get_stage().GetPrimAtPath(self._cam_left_path)
        attr = prim.GetAttribute("exposure:time") if prim else None
        exposure_s = attr.Get() if attr else None
        return float(exposure_s or _DEFAULT_EXPOSURE_S)

    def _frame_number(self, rp):
        """Number of the frame the annotators hold, 0 when unknown. For a frame the post-render graph hands
        over, the graph's count of frames: two frames finished in one app update share the render product's
        frame number."""
        if self._graph_frame is not None:
            return self._graph_frame
        try:
            return int(rp.hydra_texture.get_frame_info().get("frame_number") or 0)
        except Exception:
            return 0

    def _light_gain(self):
        """This frame's light flicker gain, over the frame's exposure, as the stream applies it.

        Held for the rendered frame so both eyes get the same gain, as they do on the real camera.
        """
        if not self._apply_sim2real:
            return 1.0
        frame = self._frame_number(self._rp) or None
        if frame is None or frame != self._light_frame:
            from .stream_encoding import light_gain_now
            try:
                self._light_value = light_gain_now(self._exposure_time())
            except Exception:
                self._light_value = 1.0
            self._light_frame = frame
        return self._light_value

    def _focus_annotator(self, rp_path):
        """An eye's depth for the lens's focus blur; None when it is off or unavailable."""
        from . import camera_model_lib
        from .stream_encoding import focus_lens
        if not self._focus_blur:
            return None
        if focus_lens(self._camera_model) == camera_model_lib.LENS_NONE:
            if not self._focus_warned:
                self._focus_warned = True
                carb.log_warn(f"[ZED][Depth] Focus blur: no lens figures for {self._camera_model} "
                              "(ZED X, X Mini and X One GS / S lenses only); it stays off.")
            return None
        if not camera_model_lib.has_focus_blur():
            if not self._focus_warned:
                self._focus_warned = True
                carb.log_warn("[ZED][Depth] Focus blur needs sl_zed_sim2real 0.5.0 or later; it stays off.")
            return None
        try:
            # On the GPU whatever the capture device, like HdrColor: the encode runs there.
            annot = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane", device="cuda")
            annot.attach(rp_path)
            return annot
        except Exception as exc:
            carb.log_warn(f"[ZED][Depth] Focus blur unavailable for {rp_path}: {exc!r}")
            return None

    def _focus(self):
        """The lens figures the focus blur uses (camera_model_lib.DefocusParams), built once."""
        if self._focus_params is None:
            from pxr import UsdGeom
            from . import camera_model_lib
            from .stream_encoding import FOCUS_DISTANCE_SETTING, FOCUS_F_NUMBER_SETTING, focus_lens
            settings = carb.settings.get_settings()
            params = get_pinhole_parameters(self._camera_model, self._resolution_token) or {}
            stage = omni.usd.get_context().get_stage()
            self._focus_params = camera_model_lib.DefocusParams(
                int(focus_lens(self._camera_model)), float(params.get("focal_length_px") or 0.0),
                float(settings.get(FOCUS_F_NUMBER_SETTING) or 0.0),
                float(settings.get(FOCUS_DISTANCE_SETTING) or 0.0),
                float(UsdGeom.GetStageMetersPerUnit(stage) or 1.0))
        return self._focus_params

    def _blur_scale(self):
        """Share of each motion vector (one rendered frame's motion) the exposure smears along:
        exposure:time of the left camera x the render rate, as the stream does."""
        return min(max(self._exposure_time() * self._fps, 0.0), 1.0)

    def _motion_annotator(self, rp_path):
        """MotionVectors of a render product, for the motion blur; None when the blur is off.

        Without the camera model library the encoder cannot blur, so the vectors would be
        rendered and read back for nothing: leave them out, as the auto exposure does.
        """
        from . import camera_model_lib
        if not self._motion_blur or not camera_model_lib.available():  # it logs once why
            return None
        try:
            # On the GPU whatever the capture device, like HdrColor: the encode runs there.
            annot = rep.AnnotatorRegistry.get_annotator("MotionVectors", device="cuda")
            annot.attach(rp_path)
            return annot
        except Exception as exc:
            carb.log_warn(f"[ZED][Depth] Motion blur unavailable for {rp_path}: {exc!r}")
            return None

    def _noise_seed(self, eye):
        """Per rendered frame and eye: re-reading a frame keeps its noise, a new frame gets new
        noise (the frame counter advances only on saved frames)."""
        frame = self._frame_number(self._rp if eye == 0 else self._rp_right)
        if not frame:  # no frame info: fall back to one new pattern per read
            self._noise_reads += 1
            frame = self._noise_reads
        return frame * 2 + eye

    def _metered_eye(self):
        """(annotator, render product, render product path) of the eye the camera meters: the right
        one of a stereo camera, as a real ZED X (annotators.ZEDAnnotator._metered_eye), else the left."""
        if self._rgb_right_annot is not None:
            return self._rgb_right_annot, self._rp_right, self._rp_right_path
        return self._rgb_annot, self._rp, self._rp_path

    def _white_balance(self):
        """The white balance gains for the frame the metered eye holds, None when off.

        The stream's auto white balance (auto_white_balance.py), metered on the right image of a
        stereo camera (the only one of a mono camera) and applied to both eyes: it follows
        the scene from frame to frame, and the first frame read is balanced at once. It steps at the
        camera's rate (``fps``, 30 without it) and follows the auto exposure's error, as the stream's
        does (auto_white_balance.CameraWhiteBalanceLoop)."""
        from . import camera_model_lib
        if not self._auto_white_balance or self._rgb_annot is None or not camera_model_lib.available():
            return None
        from .auto_white_balance import ZedAutoWhiteBalance
        from .hdr_meter import HdrExposureMeter
        annot, rp, rp_path = self._metered_eye()
        if self._wb_meter is None:
            self._wb_meter = HdrExposureMeter(rp_path, annotator=annot)
            self._wb = ZedAutoWhiteBalance()
        frame = self._frame_number(rp) or None
        self._wb_meter.wb = self._wb.gains or (1.0, 1.0, 1.0)
        self._wb_meter.neutral_ref = self._wb.neutral
        stats = self._wb_meter.update(frame)
        if stats is None:  # the meter answers one read late: for the first one, wait for it
            self._wb_meter.wait()
            stats = self._wb_meter.update(frame)
        if stats is not None and stats.frame != self._wb_frame:
            self._wb_frame = stats.frame
            ae = self._exposure_loop.state.error_ev if self._exposure_loop is not None else 0.0
            self._wb.update_stats(stats, 1.0 / (self._fps or 30.0), float(ae or 0.0))
        return self._wb.gains

    def _color(self, annot, eye=0):
        data = annot.get_data()
        if self._encoding != "srgb":
            return data
        from .stream_encoding import encode_srgb
        kw = dict(focal_px=self._vignette_focal_px(), mtf=self._camera_sharpness, wb=self._white_balance(), eye=eye,
                  light_gain=self._light_gain())
        if self._sensor_noise:
            kw.update(gain=self._camera_gain(), seed=self._noise_seed(eye))
        motion = self._motion_annot if eye == 0 else self._motion_right_annot
        if motion is not None:
            kw.update(motion=motion.get_data(), blur_scale=self._blur_scale())
        focus = self._focus_annot if eye == 0 else self._focus_right_annot
        if focus is not None:
            kw.update(depth=focus.get_data(), focus=self._focus())
        return encode_srgb(data, self._device, **kw)

    def _vignette_focal_px(self):
        """Focal length in pixels for the lens vignetting; None when off or for fisheye lenses."""
        if not self._vignetting or get_lens_type(self._camera_model) == LensType.FISHEYE:
            return None
        params = get_pinhole_parameters(self._camera_model, self._resolution_token)
        return float(params["focal_length_px"]) if params and params.get("focal_length_px") else None

    def _do_init(self):
        # Match the images to the intrinsics before any render product is built from them.
        if sdk_virtual_camera.get_mode() == sdk_virtual_camera.MODE_VIRTUAL:
            stage = omni.usd.get_context().get_stage()
            self._virtual_camera = setup_virtual_camera(
                stage.GetPrimAtPath(self._cam_left_path),
                stage.GetPrimAtPath(self._cam_right_path) if self._is_stereo else None,
                self._camera_model, self._resolution_token, self._camera_index, fps=self._fps_given)
            carb.log_info(f"[ZED][Depth] [{self._camera_prim_path}] virtual camera index "
                          f"{self._virtual_camera.index}, SN {self._virtual_camera.serial_number}")
        else:
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
        self._motion_annot = self._motion_annotator(self._rp_path)
        self._focus_annot = self._focus_annotator(self._rp_path)

        if self._save_depth:
            self._depth_annot = rep.AnnotatorRegistry.get_annotator(
                "distance_to_image_plane", device=self._device
            )
            self._depth_annot.attach(self._rp_path)

        if self._frame_writer.needs_pose:
            # The time of the rendered frame, not of the current app tick: a plain World.current_time
            # read would be offset from the image by the render pipeline latency. Under multi-tick
            # rendering it is the frame's tick, and the image shows the physics state at that time.
            self._sim_time_annot = rep.AnnotatorRegistry.get_annotator("IsaacReadSimulationTime")
            self._sim_time_annot.initialize(resetOnStop=True)
            self._sim_time_annot.attach(self._rp_path)
            # The camera's pose at that time, from its rigid body's pose at each physics step. CameraParams,
            # the fallback, gives the pose at the end of the update that rendered the frame; the stage itself
            # has moved on by the time a frame is read back.
            self._camera_poses = frame_pose.CameraPoses(self._cam_left_path)
            self._camera_params_annot = rep.AnnotatorRegistry.get_annotator("CameraParams")
            self._camera_params_annot.attach(self._rp_path)

        if self._is_stereo:
            self._rp_right = viewport_manager.get_render_product(
                self._cam_right_path, self._resolution, False, f"{prim_name}_zed_depth_rp_right"
            )
            self._rp_right_path = self._rp_right.hydra_texture.get_render_product_path()
            self._rgb_right_annot = self._color_annotator()
            self._rgb_right_annot.attach(self._rp_right_path)
            self._motion_right_annot = self._motion_annotator(self._rp_right_path)
            self._focus_right_annot = self._focus_annotator(self._rp_right_path)

        if self._auto_exposure:
            self._start_auto_exposure()

    def _start_auto_exposure(self):
        """The stream's ZED X auto exposure on this camera; logs and leaves it off when unavailable."""
        from . import camera_model_lib
        if not camera_model_lib.available():  # it logs once why
            return
        from .exposure_loop import CameraExposureLoop

        def view():  # the output the real camera meters: lens falloff, white balance
            focal_px = self._vignette_focal_px()
            wb = self._wb.gains if self._wb is not None else None
            return (1.0 / focal_px if focal_px else 0.0), wb or (1.0, 1.0, 1.0)

        annot, rp, _ = self._metered_eye()
        paths = [self._cam_left_path] + ([self._cam_right_path] if self._is_stereo else [])
        try:
            self._exposure_loop = CameraExposureLoop(annot, rp, paths, self._fps, view=view,
                                                     limits=self._exposure_limits)
        except Exception as exc:
            carb.log_error(f"[ZED][Depth] [{self._camera_prim_path}] Auto exposure unavailable: {exc!r}")
            self._exposure_loop = None

    @property
    def exposure_state(self):
        """The auto exposure's current AeState (exposure_s, gains, scene_lux...), None when it is off.

        A real ZED X takes about half a second to reach a new scene's exposure, so the first
        frames of a capture are over- or under-exposed: wait for ``exposure_state.converged``
        before saving if the recording should not start on them.
        """
        return self._exposure_loop.state if self._exposure_loop is not None else None

    def _on_update(self, event):
        if not (self._valid and self._enable_save):
            return
        if not self._frame_node_paths:
            self.save_frame()
        elif not self._graph_frames:
            try:
                rendered = self._rgb_annot.get_node().get_compute_count() - self._color_computes
            except Exception:
                rendered = 0
            if rendered >= _FIRST_GRAPH_FRAME_WAIT:
                carb.log_warn(f"[ZED][Depth] [{self._camera_prim_path}] The post-render graph handed over none of "
                              f"the first {rendered} frames: frames are read once per app update instead, which "
                              "saves only the second of two frames finished in one update.")
                self._unhook_frame_node()

    def _frame_annotators(self):
        """The attached annotators a saved frame reads."""
        return [a for a in (self._rgb_annot, self._rgb_right_annot, self._depth_annot, self._sim_time_annot,
                            self._camera_params_annot, self._motion_annot, self._motion_right_annot,
                            self._focus_annot, self._focus_right_annot) if a is not None]

    def _hook_frame_node(self):
        """Have the post-render graph hand over each frame the camera renders, as it does to a stream's ZED node.

        An app update can finish two frames, and by the end of the update the annotators hold the second
        only. A sync gate on the annotators' outputs fires once all of them hold a frame, and triggers a
        ZED_CaptureFrame node that saves it. Returns False, leaving no node behind, when the graph cannot
        be wired; frames are then read on each app update.
        """
        try:
            import omni.graph.core as og
            from omni.syntheticdata import SyntheticData, SyntheticDataStage
            from pxr import Sdf

            graph_path = SyntheticData._get_graph_path(SyntheticDataStage.ON_DEMAND)
            graph = og.Controller.graph(graph_path)
            dispatcher = graph.get_node(f"{graph_path}/PostProcessDispatcher")
            if not dispatcher.is_valid():
                raise RuntimeError(f"no PostProcessDispatcher in {graph_path}")
            ready = []
            for annot in self._frame_annotators():
                node = annot.get_node()
                name = next((n for n in _EXEC_OUTPUTS if node.get_attribute_exists(n)), None)
                if name is None:
                    raise RuntimeError(f"{node.get_type_name()} at {node.get_prim_path()} has no execution output")
                ready.append(node.get_attribute(name))

            self._frame_graph = graph
            stem = f"{graph_path}/{Sdf.Path(self._rp_path).name}"
            stage = omni.usd.get_context().get_stage()
            nodes = []
            for path, node_type in ((f"{stem}_capture_sync", "omni.graph.action.RationalTimeSyncGate"),
                                    (f"{stem}_capture_frame", "sl.sensor.camera.ZED_CaptureFrame")):
                if graph.get_node(path).is_valid():  # left by a capture that was not destroyed
                    graph.destroy_node(path, True)
                if stage.GetPrimAtPath(path):
                    stage.RemovePrim(path)
                nodes.append(graph.create_node(path, node_type, True))
                self._frame_node_paths.append(path)
            gate, frame = nodes
            for part in ("Numerator", "Denominator"):
                dispatcher.get_attribute(f"outputs:referenceTime{part}").connect(
                    gate.get_attribute(f"inputs:rationalTime{part}"), True)
                gate.get_attribute(f"outputs:rationalTime{part}").connect(
                    frame.get_attribute(f"inputs:rationalTime{part}"), True)
            for attr in ready:
                attr.connect(gate.get_attribute("inputs:execIn"), True)
            gate.get_attribute("outputs:execOut").connect(frame.get_attribute("inputs:execIn"), True)
            self._color_computes = self._rgb_annot.get_node().get_compute_count()
            _frame_nodes[frame.get_prim_path()] = self
            return True
        except Exception as exc:
            carb.log_warn(f"[ZED][Depth] [{self._camera_prim_path}] Frames are read once per app update, which "
                          f"saves only the second of two frames finished in one update: the post-render graph "
                          f"cannot hand them over ({exc!r}).")
            self._unhook_frame_node()
            return False

    def _unhook_frame_node(self):
        """Remove the post-render graph nodes _hook_frame_node made."""
        for path in self._frame_node_paths:
            _frame_nodes.pop(path, None)
            try:
                if self._frame_graph.get_node(path).is_valid():
                    self._frame_graph.destroy_node(path, True)
            except Exception:
                carb.log_warn(f"[ZED][Depth] Could not remove {path} from the post-render graph.")
        self._frame_node_paths = []
        self._frame_graph = None

    def _save_rendered_frame(self, frame_id):
        """Save the frame the post-render graph hands over; ``frame_id`` is its (numerator, denominator)
        reference time."""
        self._graph_frames += 1
        self._graph_frame = self._graph_frames
        try:
            return self._save(None, tuple(frame_id) if frame_id[1] else None)
        finally:
            self._graph_frame = None

    def _render_view_transform(self, sim_time):
        """World-to-camera of the frame the annotators hold, rendered at ``sim_time`` (None: unknown), or None
        when it is unavailable."""
        if self._camera_poses is not None and sim_time is not None:
            view = self._camera_poses.view_transform(sim_time)
            if view is not None:
                return view
        if self._camera_params_annot is None:
            return None
        data = self._camera_params_annot.get_data()
        view = data.get("cameraViewTransform") if data else None
        return view if view is not None and len(view) == 16 else None

    def _rendered_time(self):
        """Simulation time of the physics state shown by the frame the annotators hold, in seconds; None
        while the annotator reports none or 0."""
        data = self._sim_time_annot.get_data() if self._sim_time_annot is not None else None
        sim_time = float(data["simulationTime"]) if data else 0.0
        return sim_time if sim_time > 0.0 else None

    def _sim_time(self):
        """Simulation time of the physics state shown by the frame the annotators hold, in seconds, on the
        clock the IMU is stamped with.

        Falls back to a monotonic clock when the annotator reports 0, as some Isaac builds do;
        OgnZEDSimCameraNode.cpp carries the same workaround. Without it every frame would
        be stamped with the same time.
        """
        sim_time = self._rendered_time()
        if sim_time is not None:
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
        """Save the frame the annotators hold now; returns whether one was written.

        With ``enable_save`` the post-render graph saves every rendered frame, and this returns False.
        """
        if self._frame_node_paths:
            return False
        return self._save(output_dir, None)

    def _save(self, output_dir, frame_id):
        if not self._valid:
            return False

        out = output_dir or self._output_dir
        if not out:
            return False

        # Read on each app update, a rendered frame is read again until the writer takes it: the render
        # product can render less often than the app updates (its camera's omni:sensor:tickRate). A pose
        # writer's frame is told by the time it shows, as the frame number can advance an update before
        # the annotators hold that frame; other frames by the frame number, or the reference time of the
        # frame the post-render graph hands over. Without either, every call goes to the writer.
        rendered = frame_id if frame_id is not None else self._frame_number(self._rp)
        stamp = self._rendered_time() if self._frame_writer.needs_pose else None
        if stamp is not None:
            if stamp == self._last_stamp:
                return False
        elif rendered and rendered == self._last_render_frame:
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
            frame.view_transform = self._render_view_transform(stamp)

        try:
            written = self._frame_writer.write(frame)
        except Exception:
            # Per-frame code: never take the capture loop down with the writer. The frame is not
            # retried, so a failing writer logs once per frame, not once per update.
            self._last_render_frame, self._last_stamp = rendered, stamp
            import traceback
            carb.log_error(f"[ZED][Depth] Saving the frame failed:\n{traceback.format_exc()}")
            return False

        # A skipped frame leaves its index unspent, so the numbering stays gap-free.
        if written:
            self._last_render_frame, self._last_stamp = rendered, stamp
            self._frame_count += 1
        return bool(written)

    def is_valid(self):
        return self._valid

    @property
    def virtual_camera(self):
        """The SDK virtual camera (serial number + calibration) rendered, or None in legacy mode."""
        return self._virtual_camera

    def destroy(self):
        # First: no frame may arrive while the writer closes, and SyntheticData does not detach an
        # annotator whose outputs still feed a node (the next Play on the same render product then fails).
        self._unhook_frame_node()
        sdk_virtual_camera.release(self._virtual_camera)
        self._virtual_camera = None

        if self._frame_writer is not None:
            try:
                self._frame_writer.close()
            except Exception:
                import traceback
                carb.log_error(f"[ZED][Depth] Closing the frame writer failed:\n{traceback.format_exc()}")
            self._frame_writer = None

        if self._camera_poses is not None:
            self._camera_poses.destroy()
            self._camera_poses = None
        for annot, rp_path in (("_sim_time_annot", self._rp_path), ("_camera_params_annot", self._rp_path),
                               ("_motion_annot", self._rp_path), ("_motion_right_annot", self._rp_right_path),
                               ("_focus_annot", self._rp_path), ("_focus_right_annot", self._rp_right_path)):
            if getattr(self, annot) is not None:
                try:
                    getattr(self, annot).detach(rp_path)
                except Exception:
                    pass
                setattr(self, annot, None)

        if self._update_sub is not None:
            self._update_sub.unsubscribe()
            self._update_sub = None

        # Before the colour annotators go: the loop meters one of them.
        if self._exposure_loop is not None:
            try:
                self._exposure_loop.destroy()
            except Exception:
                pass
            self._exposure_loop = None

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
