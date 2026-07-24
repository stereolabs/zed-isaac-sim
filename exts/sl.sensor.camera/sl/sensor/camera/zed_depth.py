import os
from datetime import datetime

import carb
import numpy as np
import omni.kit.app
import omni.usd

try:
    import omni.replicator.core as rep
    from omni.replicator.core.scripts.utils import viewport_manager
    from isaacsim.core.utils.prims import is_prim_path_valid
except ImportError:
    rep = viewport_manager = is_prim_path_valid = None

from .utils import get_camera_subpaths, get_resolution, is_stereo_camera

_WARMUP_FRAMES = 10


class ZEDDepthCamera:
    """
    Captures RGB and depth from a ZED camera using Isaac Sim's renderer.

    Uses CameraLeft directly with ``distance_to_image_plane`` for depth
    and ``rgb`` for color. For stereo models the right ``rgb`` is captured too
    (depth stays left-referenced). No additional camera prim is created.
    Independent of the ZED SDK streaming pipeline.

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
    ):
        self._camera_prim_path = camera_prim_path
        self._camera_model = camera_model
        self._device = device
        self._valid = False
        self._init_failed = False
        self._enable_save = enable_save
        self._output_dir = output_dir
        self._frame_count = 0

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

        self._resolution = get_resolution(camera_model, resolution)
        if self._resolution is None:
            carb.log_error(f"[ZED Depth] Unknown resolution '{resolution}' for model '{camera_model}'")
            self._init_failed = True
            return

        # "left" resolves to CameraLeft for stereo models, Camera for mono.
        subpaths = get_camera_subpaths(camera_model)
        self._cam_left_path = f"{camera_prim_path}/{subpaths['left']}"

        if not is_prim_path_valid(self._cam_left_path):
            carb.log_error(f"[ZED Depth] Camera prim not found at {self._cam_left_path}")
            self._init_failed = True
            return

        if self._is_stereo:
            self._cam_right_path = f"{camera_prim_path}/{subpaths['right']}"
            if not is_prim_path_valid(self._cam_right_path):
                carb.log_error(f"[ZED Depth] Right camera prim not found at {self._cam_right_path}")
                self._init_failed = True
                return

        carb.log_info(
            f"[ZED Depth] Created for {camera_prim_path} "
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
                carb.log_error(f"[ZED Depth] Init failed: {e}")
                import traceback
                carb.log_error(traceback.format_exc())
                self._init_failed = True
                return False

        self._valid = True

        if self._enable_save and self._output_dir:
            date_folder = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self._output_dir = os.path.join(self._output_dir, date_folder)
            os.makedirs(self._output_dir, exist_ok=True)
            self._update_sub = (
                omni.kit.app.get_app()
                .get_update_event_stream()
                .create_subscription_to_pop(self._on_update)
            )
            carb.log_info(f"[ZED Depth] Saving frames to {self._output_dir}")

        carb.log_info(
            f"[ZED Depth] Ready at frame {self._tick}: "
            f"{self._resolution[0]}x{self._resolution[1]} from {self._cam_left_path}"
        )
        return True

    def _do_init(self):
        prim_name = self._camera_prim_path.split("/")[-1]
        self._rp = viewport_manager.get_render_product(
            self._cam_left_path, self._resolution, False, f"{prim_name}_zed_depth_rp"
        )
        self._rp_path = self._rp.hydra_texture.get_render_product_path()

        self._rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=self._device)
        self._rgb_annot.attach(self._rp_path)

        self._depth_annot = rep.AnnotatorRegistry.get_annotator(
            "distance_to_image_plane", device=self._device
        )
        self._depth_annot.attach(self._rp_path)

        if self._is_stereo:
            self._rp_right = viewport_manager.get_render_product(
                self._cam_right_path, self._resolution, False, f"{prim_name}_zed_depth_rp_right"
            )
            self._rp_right_path = self._rp_right.hydra_texture.get_render_product_path()
            self._rgb_right_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=self._device)
            self._rgb_right_annot.attach(self._rp_right_path)

    def _on_update(self, event):
        if self._valid and self._enable_save:
            self.save_frame()

    def get_rgba(self):
        if not self._valid:
            return None
        return self._rgb_annot.get_data()

    def get_rgba_right(self):
        if not self._valid or self._rgb_right_annot is None:
            return None
        return self._rgb_right_annot.get_data()

    def get_depth(self):
        if not self._valid:
            return None
        return self._depth_annot.get_data()

    def save_frame(self, output_dir=None):
        if not self._valid:
            return False

        out = output_dir or self._output_dir
        if not out:
            return False

        rgba = self.get_rgba()
        depth = self.get_depth()
        if rgba is None or depth is None:
            return False

        if hasattr(rgba, "numpy"):
            rgba = rgba.numpy()
        if hasattr(depth, "numpy"):
            depth = depth.numpy()

        if rgba.ndim != 3:
            return False
        if depth.ndim == 3:
            depth = depth[:, :, 0]
        if depth.ndim != 2:
            return False

        # Right eye (stereo only); saved alongside as rgb_right_. Skipped if not yet ready.
        rgba_right = self.get_rgba_right()
        if rgba_right is not None:
            if hasattr(rgba_right, "numpy"):
                rgba_right = rgba_right.numpy()
            if rgba_right.ndim != 3:
                rgba_right = None

        os.makedirs(out, exist_ok=True)
        idx = self._frame_count
        self._frame_count += 1

        try:
            import cv2
            cv2.imwrite(os.path.join(out, f"rgb_left_{idx:06d}.png"),
                        cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2BGR))
            cv2.imwrite(os.path.join(out, f"depth_{idx:06d}.exr"), depth.astype(np.float32))
            if rgba_right is not None:
                cv2.imwrite(os.path.join(out, f"rgb_right_{idx:06d}.png"),
                            cv2.cvtColor(rgba_right[:, :, :3], cv2.COLOR_RGB2BGR))
        except ImportError:
            from PIL import Image
            Image.fromarray(rgba[:, :, :3]).save(os.path.join(out, f"rgb_left_{idx:06d}.png"))
            np.save(os.path.join(out, f"depth_{idx:06d}.npy"), depth.astype(np.float32))
            if rgba_right is not None:
                Image.fromarray(rgba_right[:, :, :3]).save(os.path.join(out, f"rgb_right_{idx:06d}.png"))
            carb.log_warn("[ZED Depth] OpenCV not available, depth saved as .npy instead of .exr")

        return True

    def is_valid(self):
        return self._valid

    def destroy(self):
        if self._update_sub is not None:
            self._update_sub.unsubscribe()
            self._update_sub = None

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
        carb.log_info(f"[ZED Depth] Destroyed for {self._camera_prim_path}")
