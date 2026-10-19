# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import carb
import omni.graph.core as og
import omni.usd

# Prims are looked up with plain USD calls: isaacsim.core.utils is not in Isaac Lab's app.
try:
    import omni.replicator.core as rep
    from omni.replicator.core.scripts.utils import viewport_manager
    from omni.syntheticdata import SyntheticData, SyntheticDataStage
except ImportError:
    rep = viewport_manager = None
    SyntheticData = SyntheticDataStage = None

from . import camera_model_lib
from .optics import apply_camera_optics
from .utils import (
    get_camera_subpaths,
    is_stereo_camera,
    get_camera_model,
    get_lens_type,
    get_sdk_model_id,
    get_sim_lens_type_id,
    MODEL_ID_VIRTUAL_ZED_X,
    get_resolution,
    get_pinhole_parameters,
    resolve_resolution_token,
    LensType,
)

# Shared across all streamer classes to ensure port uniqueness
used_ports = set()

# Width of the depth map streamed to the ZED SDK (ingestCustomDepth). Its height follows the image's
# aspect ratio, since the SDK stretches the map over the whole image and the renderer only draws
# square pixels.
_STREAM_DEPTH_WIDTH = 896


def _stream_depth_resolution(image_resolution) -> list:
    """[w, h] of the streamed depth map for an image of `image_resolution`; h is a multiple of 8."""
    width, height = image_resolution
    return [_STREAM_DEPTH_WIDTH, 8 * round(_STREAM_DEPTH_WIDTH * height / width / 8)]


# Stream image encoding. "srgb": encoded on the GPU from the linear HdrColor (see
# stream_encoding.py), matching a real ZED X's output. "linear": the legacy LdrColor ("rgb"
# annotator) buffer - despite the name, the RTX tonemapped image (ACES approximation + sRGB with
# the default settings), which turns into 255 * clamp(HDR) as soon as anything requests
# HdrColor on the same render product.
STREAM_ENCODINGS = ("srgb", "linear")


class ZEDAnnotator:
    """
    Captures camera data and streams it to the ZED SDK.

    This class creates annotators for RGB from a zed camera,
    and streams this data to the ZED SDK. It can operate in two modes:
    - OGN node mode (C++ implementation)
    """

    def __init__(
        self,
        camera_prim,
        camera_model = "ZED_X",
        streaming_port = 30000,
        resolution = "SVGA",
        fps = 30,
        bitrate = 10000,
        chunk_size = 4096,
        transport_layer_mode = "BOTH",
        virtual_serial_number = None,
        stream_depth = False,
        apply_zed_sim2real = True,
        stream_encoding = "srgb",
        auto_exposure = True,
        sensor_noise = True,
        motion_blur = True,
        vignetting = True,
        camera_sharpness = True,
        auto_white_balance = True
        ):

        """
        Initializes a ZEDAnnotator object.
        camera_prim can be a list of:
          - a single prim (stereo or mono)
          - two prims (custom stereo made of two monos)
        apply_zed_sim2real is the master switch of the ZED X camera model: off, none of the real-camera
        effects below applies (the render streams as is), whatever their own switch.
        """

        self.stage = omni.usd.get_context().get_stage()
        self._imu_gate_checked = False

        # Normalize input
        if len(camera_prim) == 1:
            self.custom_stereo = False
        elif len(camera_prim) == 2:
            carb.log_info("[ZED] Two prims provided, assuming custom stereo setup.")
            self.custom_stereo = True
        else:
            carb.log_error(f"[ZED] Expected 1 or 2 camera prims, got {len(camera_prim)}")
            self.camera_prim_path = []
            self.custom_stereo = False
            self.is_stereo = False
            self.nodes = []
            self.zed_ = None
            self.graph = None
            self.port = streaming_port
            return

        self.camera_prim_path = camera_prim
        self.serial_number = virtual_serial_number
        self.camera_model = camera_model
        self.port = streaming_port

        # Guard against a resolution that the selected model does not support (e.g. graphs
        # authored via script, or the in-canvas node body which is not filtered by the
        # property panel template). Shared with the ZED Capture node, so both clamp alike.
        self.resolution_token = resolve_resolution_token(camera_model, resolution)
        resolution = self.resolution_token
        self.resolution = get_resolution(camera_model, resolution)
        self.fps = ZEDAnnotator.check_frame_rate(fps)
        self.bitrate = bitrate
        self.chunk_size = chunk_size
        self.transport_layer_mode = transport_layer_mode
        self.apply_zed_sim2real = bool(apply_zed_sim2real)
        if stream_encoding not in STREAM_ENCODINGS:
            carb.log_warn(f"[ZED] Unknown stream encoding '{stream_encoding}', using sRGB.")
            stream_encoding = "srgb"
        self.stream_encoding = stream_encoding
        # Real-camera auto exposure (exposure_loop.py). It meters the HdrColor the sRGB encoder
        # already reads; with the legacy stream it is unavailable (requesting HdrColor would
        # also turn that stream's LdrColor linear).
        self.auto_exposure = bool(auto_exposure)
        self.exposure_loop = None
        self._image_camera_paths = []
        if self.auto_exposure and self.stream_encoding != "srgb":
            carb.log_warn("[ZED] Auto exposure needs the sRGB stream encoding; it stays off.")
        # Real-camera sensor noise, added by the sRGB encoders at the cameras' gain.
        self.sensor_noise = bool(sensor_noise)
        self._srgb_nodes = []
        self._noise_gain_pushed = None
        # Motion blur over each frame's exposure time, from the render products' motion vectors.
        self.motion_blur = bool(motion_blur)
        self._motion_annots = []
        self._blur_scale_pushed = None
        # Lens vignetting of a ZED X wide lens, scaled by field angle (not for fisheye lenses).
        self.vignetting = bool(vignetting)
        # A real ZED X's sharpness (lens/demosaic blur + ISP sharpening) instead of the render's.
        self.camera_sharpness = bool(camera_sharpness)
        # A real ZED X's auto white balance (auto_white_balance.py), gains shared by both eyes.
        self.auto_white_balance = bool(auto_white_balance)
        self.white_balance_loop = None
        self._wb_pushed = None

        # Stereo if model is stereo OR user provides 2 prims
        self.is_stereo = is_stereo_camera(camera_model) or self.custom_stereo

        self.stream_depth = stream_depth
        self.depth_resolution = _stream_depth_resolution(self.resolution) if stream_depth else None

        self.nodes = []
        self.zed_ = None

        self.build_annotators()
        mode_str = "left+depth" if self.stream_depth else ('custom stereo' if self.custom_stereo else ('stereo' if self.is_stereo else 'mono'))
        print(f"[ZED][port {self.port}] Constructed annotator for {mode_str} camera.")

    def init_camera(self, camera_prim_path : str):
        """Author the ZED model's optics on a camera prim before it is rendered.

        Shared with the SDK-free capture path (see optics.apply_camera_optics), so a streamed
        camera and a captured one of the same model render the same image. Streaming also caps
        the render rate at the ZED's target FPS, which a capture does not.
        """
        prim = self.stage.GetPrimAtPath(camera_prim_path)
        if not prim.IsValid():
            carb.log_error(f"[ZED] Camera prim path {camera_prim_path} is not valid.")
            return False
        return apply_camera_optics(prim, self.camera_model, self.resolution_token, fps=self.fps)

    @staticmethod
    def check_frame_rate(camera_frame_rate: int):
        if camera_frame_rate not in [15, 30, 60, 120]:
            carb.log_warn(f"[ZED] Invalid frame rate passed: {camera_frame_rate}. Defaulting to 30.")
            return 30
        return camera_frame_rate

    def _image_annotator(self, device):
        """Per-eye image source: linear HdrColor for the sRGB encoder, or the legacy tonemapped LdrColor."""
        return rep.AnnotatorRegistry.get_annotator("HdrColor" if self.stream_encoding == "srgb" else "rgb",
                                                   device=device)

    def _image_source_node(self, side):
        """Node whose dataPtr/bufferSize feed the ZED node for this eye.

        For the sRGB stream this is a ZED_HdrToSrgb node fed by the eye's HdrColor annotator;
        otherwise the annotator node itself (legacy LdrColor).
        """
        annot_node = self.annotators[side].get_node()
        if self.stream_encoding != "srgb":
            return annot_node
        path = f"{self._graph_path}/zed_{self.port}_srgb_{side.lower()}"
        node = self.graph.get_node(path)
        if not node.is_valid():
            stage = omni.usd.get_context().get_stage()
            if stage.GetPrimAtPath(path):
                stage.RemovePrim(path)
            node = self.graph.create_node(path, "sl.sensor.camera.ZED_HdrToSrgb", True)
        for name in ("exec", "dataPtr", "bufferSize", "width", "height", "strides", "cudaDeviceIndex"):
            annot_node.get_attribute(f"outputs:{name}").connect(node.get_attribute(f"inputs:{name}"), True)
        # Independent noise per eye and per camera; the lens an eye fault (SL_SIM2REAL_*) aims at.
        node.get_attribute("inputs:noiseSeed").set(self.port * 2 + (side == "Right"))
        node.get_attribute("inputs:eye").set(1 if side == "Right" else 0)
        # Motion vectors of the same render product, for the exposure-time motion blur. Attached
        # whatever motion_blur is, so it can be toggled live (the blur scale is 0 when off).
        rp_path = self.left_rp if side == "Left" else getattr(self, "right_rp", None)
        if rp_path:
            try:
                mv = rep.AnnotatorRegistry.get_annotator("MotionVectors", device="cuda")
                mv.attach(rp_path)
                mv_node = mv.get_node()
                mv_node.get_attribute("outputs:dataPtr").connect(node.get_attribute("inputs:motionPtr"), True)
                mv_node.get_attribute("outputs:bufferSize").connect(node.get_attribute("inputs:motionSize"), True)
                self._motion_annots.append((mv, rp_path))
            except Exception as exc:
                carb.log_warn(f"[ZED][port {self.port}] Motion blur unavailable for the {side} eye: {exc!r}")
        self.nodes.append(node)
        self._srgb_nodes.append(node)
        return node

    def build_annotators(self) -> None:
        # Set device based on mode (CUDA for OGN nodes)
        device = "cuda"
        cams = []
        self.annotators = {}

        subpaths = get_camera_subpaths(self.camera_model)
         # Case 1: user gave 2 prims (custom stereo)
        if self.custom_stereo:
            left_full_path = f"{self.camera_prim_path[0].pathString}/{subpaths['mono']}"
            right_full_path = f"{self.camera_prim_path[1].pathString}/{subpaths['mono']}"

            if self.init_camera(left_full_path):
                name_left = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_left_rp"
                self._left_rp = viewport_manager.get_render_product(left_full_path, self.resolution, False, name_left)
                self.left_rp = self._left_rp.hydra_texture.get_render_product_path()
                self.left_rgb_annot = self._image_annotator(device)
                self._image_camera_paths.insert(0, left_full_path)
                self.left_rgb_annot.attach(self.left_rp)
                self.annotators["Left"] = self.left_rgb_annot
                cams.append(["Left", name_left])

            if self.stream_depth:
                depth_res = self.depth_resolution
                name_depth = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_depth_rp"
                self._depth_rp = viewport_manager.get_render_product(left_full_path, depth_res, False, name_depth)
                self.depth_rp = self._depth_rp.hydra_texture.get_render_product_path()
                self.depth_annot = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane", device=device)
                self.depth_annot.attach(self.depth_rp)
                self.annotators["Depth"] = self.depth_annot
                cams.append(["Depth", name_depth])
            elif self.init_camera(right_full_path):
                name_right = f"{self.camera_prim_path[1].pathString.split('/')[-1]}_right_rp"
                self._right_rp = viewport_manager.get_render_product(right_full_path, self.resolution, False, name_right)
                self.right_rp = self._right_rp.hydra_texture.get_render_product_path()
                self.right_rgb_annot = self._image_annotator(device)
                self._image_camera_paths.append(right_full_path)
                self.right_rgb_annot.attach(self.right_rp)
                self.annotators["Right"] = self.right_rgb_annot
                cams.append(["Right", name_right])
        # Case 2: one prim (mono or stereo)
        else:
            # subpaths["left"] resolves to CameraLeft for stereo models, Camera for mono.
            left_full_path = f"{self.camera_prim_path[0].pathString}/{subpaths['left']}"
            if self.init_camera(left_full_path):
                name_left = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_left_rp"
                self._left_rp = viewport_manager.get_render_product(left_full_path, self.resolution, False, name_left)
                self.left_rp = self._left_rp.hydra_texture.get_render_product_path()
                self.left_rgb_annot = self._image_annotator(device)
                self._image_camera_paths.insert(0, left_full_path)
                self.left_rgb_annot.attach(self.left_rp)
                self.annotators["Left"] = self.left_rgb_annot
                cams.append(["Left", name_left])
            else:
                carb.log_warn(f"[ZED] [{self.camera_prim_path[0].pathString}] Invalid or non existing zed camera, try to re-import your camera prim.")

            # Depth annotator - when stream_depth is enabled
            if self.stream_depth:
                depth_res = self.depth_resolution
                name_depth = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_depth_rp"
                self._depth_rp = viewport_manager.get_render_product(left_full_path, depth_res, False, name_depth)
                self.depth_rp = self._depth_rp.hydra_texture.get_render_product_path()
                self.depth_annot = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane", device=device)
                self.depth_annot.attach(self.depth_rp)
                self.annotators["Depth"] = self.depth_annot
                cams.append(["Depth", name_depth])
            # Right Camera - Only for stereo cameras when not in depth mode
            elif self.is_stereo:
                right_full_path = f"{self.camera_prim_path[0].pathString}/{subpaths['right']}"
                if self.init_camera(right_full_path):
                    name_right = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_right_rp"
                    self._right_rp = viewport_manager.get_render_product(right_full_path, self.resolution, False, name_right)
                    self.right_rp = self._right_rp.hydra_texture.get_render_product_path()
                    self.right_rgb_annot = self._image_annotator(device)
                    self._image_camera_paths.append(right_full_path)
                    self.right_rgb_annot.attach(self.right_rp)
                    self.annotators["Right"] = self.right_rgb_annot
                    cams.append(["Right", name_right])
                else:
                    carb.log_warn(f"[ZED] [{self.camera_prim_path[0].pathString}] Invalid or non existing zed camera, try to re-import your camera prim.")


        self.init_graph()
        self.build_graph(cams)
        self._update_exposure_loop()
        self._update_white_balance_loop()

    def init_graph(self) -> None:

        # we are extending the already existing synthetic data data graph
        self._graph_path = SyntheticData._get_graph_path(SyntheticDataStage.ON_DEMAND)
        self.graph = None
        if omni.usd.get_context().get_stage().GetPrimAtPath(self._graph_path):
            self.graph = og.Controller.graph(self._graph_path)
        else:
            SyntheticData.Get().activate_node_template("PostProcessDispatch")
            self.graph = og.Controller.graph(self._graph_path)


        frame_gate_node_path = f"{self._graph_path}/DispatchSync"
        frame_gate_node = og.Controller.node(frame_gate_node_path)
        frame_gate_node.get_attribute("inputs:enabled").set(True)

        # create/assign sync and time nodes (unique per camera using port)
        _physics_nodes = {
            f"sync_{self.port}": {"node_type": "omni.graph.action.RationalTimeSyncGate", "node": None},
            f"sim_time_{self.port}": {"node_type": "isaacsim.core.nodes.IsaacReadSimulationTime", "node": None},
            f"imu_sensor_{self.port}": {"node_type": "isaacsim.sensors.physics.IsaacReadIMU", "node": None}
        }

        stage = omni.usd.get_context().get_stage()
        for node_name, _ in _physics_nodes.items():
            node_path = self._graph_path + f"/{node_name}"
            node = self.graph.get_node(node_path)
            if not node.is_valid():
                # Remove stale prim if it exists from a previous session
                if stage.GetPrimAtPath(node_path):
                    stage.RemovePrim(node_path)
                node = self.graph.create_node(node_path, _["node_type"], True)
            _["node"] = node

        self.sync_node = _physics_nodes[f"sync_{self.port}"]["node"]
        self.sim_time = _physics_nodes[f"sim_time_{self.port}"]["node"]
        self.imu = _physics_nodes[f"imu_sensor_{self.port}"]["node"]

    def build_graph(self, cams) -> None:
        """Build the OGN graph for streaming camera data."""
        dispacher_node = self.graph.get_node(self._graph_path + "/PostProcessDispatcher")
        dispacher_node.get_attribute("outputs:referenceTimeDenominator").connect(
            self.sync_node.get_attribute("inputs:rationalTimeDenominator"), True
        )
        dispacher_node.get_attribute("outputs:referenceTimeNumerator").connect(
            self.sync_node.get_attribute("inputs:rationalTimeNumerator"), True
        )

        # create ZED node
        zed_path = self._graph_path + f"/zed_{self.port}"
        self.zed_ = self.graph.get_node(zed_path)
        if not self.zed_.is_valid():
            stage = omni.usd.get_context().get_stage()
            if stage.GetPrimAtPath(zed_path):
                stage.RemovePrim(zed_path)
            self.zed_ = self.graph.create_node(zed_path, "sl.sensor.camera.OgnZEDSimCameraNode", True)
        self.zed_.get_attribute("inputs:port").set(self.port)
        self.zed_.get_attribute("inputs:width").set(self.resolution[0])
        self.zed_.get_attribute("inputs:height").set(self.resolution[1])
        self.zed_.get_attribute("inputs:fps").set(self.fps)

        for cam in cams:
            # get the annotator nodes and connect them to the zed node
            annot_var_mapping = {}
            if self.annotators.get(cam[0]):
                annot_var_mapping[cam[0]] = {
                    "attr_suffix": "",
                    "attrs": ["bufferSize", "dataPtr"],
                }

            for side, _params in annot_var_mapping.items():
                # Depth keeps its float buffer; image eyes go through the stream encoder.
                ptr_node = self.annotators[side].get_node() if side == "Depth" else self._image_source_node(side)
                ptr_node.get_attribute("outputs:exec").connect(self.sync_node.get_attribute("inputs:execIn"), True)
                for p in _params["attrs"]:
                    target_attr = self.zed_.get_attribute(f"inputs:{p}{side}{_params['attr_suffix']}")
                    ptr_node.get_attribute(f"outputs:{p}").connect(target_attr, True)

        self.sim_time.get_attribute("outputs:simulationTime").connect(self.zed_.get_attribute("inputs:simulationTime"), True)

        self.zed_.get_attribute("inputs:stream").set(value=True)
        # Feed the C++ node the two primitives (SDK MODEL code + SIM_LENS_TYPE); it
        # rebuilds the serial-pool key from them. Custom (two-mono) stereo uses the
        # virtual-stereo sentinel instead of a real model.
        if self.custom_stereo:
            self.zed_.get_attribute("inputs:simCameraModel").set(MODEL_ID_VIRTUAL_ZED_X)
            self.zed_.get_attribute("inputs:simLensType").set(0)
        else:
            self.zed_.get_attribute("inputs:simCameraModel").set(get_sdk_model_id(get_camera_model(self.camera_model)))
            self.zed_.get_attribute("inputs:simLensType").set(get_sim_lens_type_id(get_lens_type(self.camera_model)))
        self.zed_.get_attribute("inputs:serialNumber").set(self.serial_number if self.serial_number else "-1")
        self.zed_.get_attribute("inputs:streamDepth").set(self.stream_depth)
        if self.stream_depth:
            self.zed_.get_attribute("inputs:depthWidth").set(self.depth_resolution[0])
            self.zed_.get_attribute("inputs:depthHeight").set(self.depth_resolution[1])

        # connect sync node to zed node to trigger the stream
        self.sync_node.get_attribute("outputs:execOut").connect(self.imu.get_attribute("inputs:execIn"), True)
        self.sync_node.get_attribute("outputs:rationalTimeDenominator").connect(self.sim_time.get_attribute("inputs:referenceTimeDenominator"), True)
        self.sync_node.get_attribute("outputs:rationalTimeNumerator").connect(self.sim_time.get_attribute("inputs:referenceTimeNumerator"), True)

        self._imu_path = f"{self.camera_prim_path[0].pathString}/{get_camera_subpaths(self.camera_model)['imu']}"
        self.imu.get_attribute("inputs:imuPrim").set(self._imu_path)
        self.zed_.get_attribute("inputs:bitrate").set(self.bitrate)
        self.zed_.get_attribute("inputs:chunkSize").set(self.chunk_size)
        self.zed_.get_attribute("inputs:transportLayerMode").set(self.transport_layer_mode)
        self.imu.get_attribute("outputs:orientation").connect(self.zed_.get_attribute("inputs:orientation"), True)
        self.imu.get_attribute("outputs:linAcc").connect(self.zed_.get_attribute("inputs:linearAcceleration"), True)
        self.imu.get_attribute("outputs:execOut").connect(self.zed_.get_attribute("inputs:execIn"), True)

        # Keep the per-eye sRGB encoders created above so destroy() removes them too.
        self.nodes = [self.sync_node, self.sim_time, self.imu, self.zed_] + self.nodes
        self._push_noise_gain()
        self._push_blur_scale()
        self._push_vignetting()

    def warn_if_imu_blocks_stream(self) -> None:
        """Warn once if the IMU node keeps running without ever starting the ZED node.

        The ZED node runs only on the IMU node's execOut. The IMU node (IsaacReadIMU) leaves that off,
        and logs nothing, while its sensor gives no reading.
        """
        imu = getattr(self, "imu", None)
        if self._imu_gate_checked or imu is None or not imu.is_valid() or imu.get_compute_count() < 30:
            return
        self._imu_gate_checked = True
        if self.zed_ is not None and self.zed_.is_valid() and self.zed_.get_compute_count() == 0:
            carb.log_warn(
                f"[ZED][port {self.port}] Not streaming: the IMU at {self._imu_path} gives no reading. It needs "
                "its Enabled attribute on and an enabled rigid body on the camera or a parent prim. To hold the "
                "camera still, tick Kinematic Enabled instead of unticking Rigid Body Enabled. Then Stop and Play.")

    @property
    def _auto_exposure_active(self) -> bool:
        return self.apply_zed_sim2real and self.auto_exposure and self.stream_encoding == "srgb"

    def _update_exposure_loop(self) -> None:
        """Start or stop the camera's auto exposure to match the current settings."""
        want = self._auto_exposure_active and hasattr(self, "left_rgb_annot") and bool(self._image_camera_paths)
        want = want and camera_model_lib.available()  # it logs once when the library is missing
        if want and self.exposure_loop is None:
            try:
                from .exposure_loop import CameraExposureLoop
                def view(_self=self):  # the output the real camera meters: lens falloff, white balance
                    return getattr(_self, "_vignette_inv_f", 0.0), getattr(_self, "_wb_pushed", None) or (1.0, 1.0, 1.0)

                self.exposure_loop = CameraExposureLoop(self.left_rgb_annot, self._left_rp,
                                                        self._image_camera_paths, self.fps,
                                                        on_apply=self._on_exposure,
                                                        view=view)
                carb.log_info(f"[ZED][port {self.port}] Auto exposure on for {self._image_camera_paths}")
            except Exception as exc:
                carb.log_error(f"[ZED][port {self.port}] Auto exposure unavailable: {exc!r}")
                self.exposure_loop = None
        elif not want and self.exposure_loop is not None:
            self.exposure_loop.destroy()
            self.exposure_loop = None

    @property
    def _auto_white_balance_active(self) -> bool:
        """The AWB meters the HdrColor the sRGB encoder reads."""
        return self.apply_zed_sim2real and self.auto_white_balance and self.stream_encoding == "srgb"

    def _update_white_balance_loop(self) -> None:
        """Start or stop the camera's auto white balance to match the current settings."""
        want = self._auto_white_balance_active and hasattr(self, "left_rgb_annot") and bool(self._srgb_nodes)
        want = want and camera_model_lib.available()
        if want and self.white_balance_loop is None:
            try:
                from .auto_white_balance import CameraWhiteBalanceLoop

                def ae_error(_self=self):
                    loop = _self.exposure_loop
                    return float(loop.state.error_ev or 0.0) if loop is not None else 0.0

                self.white_balance_loop = CameraWhiteBalanceLoop(self.left_rgb_annot, self._left_rp, self.fps,
                                                                 on_apply=self._push_white_balance, ae_error=ae_error)
                carb.log_info(f"[ZED][port {self.port}] Auto white balance on")
            except Exception as exc:
                carb.log_error(f"[ZED][port {self.port}] Auto white balance unavailable: {exc!r}")
                self.white_balance_loop = None
        elif not want and self.white_balance_loop is not None:
            self.white_balance_loop.destroy()
            self.white_balance_loop = None
        if not want:
            self._push_white_balance((1.0, 1.0, 1.0))

    def _push_white_balance(self, gains) -> None:
        """Hand the encoders the white balance gains (change-gated: the AWB calls this every frame)."""
        if not getattr(self, "_srgb_nodes", None) or gains is None:
            return
        gains = tuple(float(g) for g in gains)
        last = self._wb_pushed
        if last is not None and all(abs(g / l - 1) < 0.002 for g, l in zip(gains, last)):
            return
        for node in self._srgb_nodes:
            if node.is_valid():
                node.get_attribute("inputs:whiteBalance").set(list(gains))
        self._wb_pushed = gains

    def set_auto_white_balance(self, enabled) -> None:
        """Live toggle of the auto white balance (change-gated). Off streams the render's own colours."""
        enabled = bool(enabled)
        if enabled != getattr(self, "auto_white_balance", enabled):
            self.auto_white_balance = enabled
            self._update_white_balance_loop()

    def set_auto_exposure(self, enabled) -> None:
        """Live toggle (change-gated). Off restores the scene's own camera exposure."""
        enabled = bool(enabled)
        if enabled == self.auto_exposure:
            return
        self.auto_exposure = enabled
        self._update_exposure_loop()
        self._push_noise_gain()
        self._push_blur_scale()

    def set_sensor_noise(self, enabled) -> None:
        """Live toggle of the real-camera sensor noise (change-gated)."""
        enabled = bool(enabled)
        if enabled != getattr(self, "sensor_noise", enabled):
            self.sensor_noise = enabled
            self._push_noise_gain()

    def set_vignetting(self, enabled) -> None:
        """Live toggle of the lens vignetting (change-gated)."""
        enabled = bool(enabled)
        if enabled != getattr(self, "vignetting", enabled):
            self.vignetting = enabled
            self._push_vignetting()

    def _push_vignetting(self) -> None:
        """Hand the encoders the lens settings. Vignetting: 1 / the focal length in pixels, or 0 =
        none: when off, and for fisheye lenses (fitted on a rectilinear lens). Camera sharpness: on
        unless off. Neither without Apply ZED Sim2Real."""
        if not getattr(self, "_srgb_nodes", None):
            return
        inv_f = 0.0
        if self.apply_zed_sim2real and self.vignetting and get_lens_type(self.camera_model) != LensType.FISHEYE:
            params = get_pinhole_parameters(self.camera_model, self.resolution_token)
            if params and params.get("focal_length_px"):
                inv_f = 1.0 / float(params["focal_length_px"])
        mtf = bool(self.apply_zed_sim2real and self.camera_sharpness)
        self._vignette_inv_f = inv_f
        for node in self._srgb_nodes:
            if node.is_valid():
                node.get_attribute("inputs:vignetteInvFocal").set(inv_f)
                node.get_attribute("inputs:cameraMtf").set(mtf)

    def set_camera_sharpness(self, enabled) -> None:
        """Live toggle of the real-camera sharpness (change-gated)."""
        enabled = bool(enabled)
        if enabled != getattr(self, "camera_sharpness", enabled):
            self.camera_sharpness = enabled
            self._push_vignetting()

    def set_motion_blur(self, enabled) -> None:
        """Live toggle of the exposure-time motion blur (change-gated)."""
        enabled = bool(enabled)
        if enabled != getattr(self, "motion_blur", enabled):
            self.motion_blur = enabled
            self._push_blur_scale()

    def _on_exposure(self, state) -> None:
        self._push_noise_gain(state.analog_gain * state.digital_gain)
        self._push_blur_scale(state.exposure_s)

    def _camera_exposure_time(self) -> float:
        """Exposure time the camera renders with (exposure:time; the render product default 0.02 s)."""
        prim = self.stage.GetPrimAtPath(self._image_camera_paths[0]) if self._image_camera_paths else None
        attr = prim.GetAttribute("exposure:time") if prim else None
        value = attr.Get() if attr else None
        return float(value) if value else 0.02

    def _push_blur_scale(self, exposure_s=None) -> None:
        """Hand the encoders the fraction of each motion vector to smear along: exposure time over
        the vectors' time step (one camera frame); 0 = no blur.
        """
        if not getattr(self, "_srgb_nodes", None) or not self._motion_annots:
            return
        if not (self.apply_zed_sim2real and self.motion_blur):
            scale = 0.0
        else:
            if exposure_s is None:
                exposure_s = self.exposure_loop.state.exposure_s if self.exposure_loop is not None                     else self._camera_exposure_time()
            scale = min(max(exposure_s * float(self.fps), 0.0), 1.0)
        last = self._blur_scale_pushed
        if last is not None and (scale == last or (scale > 0 and last > 0 and abs(scale / last - 1) < 0.01)):
            return
        for node in self._srgb_nodes:
            if node.is_valid():
                node.get_attribute("inputs:blurScale").set(float(scale))
        self._blur_scale_pushed = scale

    def _camera_gain(self) -> float:
        """Total gain the camera renders with: exposure:iso / 100 (1 when unset)."""
        prim = self.stage.GetPrimAtPath(self._image_camera_paths[0]) if self._image_camera_paths else None
        attr = prim.GetAttribute("exposure:iso") if prim else None
        iso = attr.Get() if attr else None
        return float(iso) / 100.0 if iso else 1.0

    def _push_noise_gain(self, gain=None) -> None:
        """Hand the encoders the gain whose sensor noise they add; 0 = none. Change-gated, as the
        auto exposure calls this every update.
        """
        if not getattr(self, "_srgb_nodes", None):
            return
        if not (self.apply_zed_sim2real and self.sensor_noise):
            gain = 0.0
        elif gain is None:
            gain = self.exposure_loop.state.analog_gain * self.exposure_loop.state.digital_gain                 if self.exposure_loop is not None else self._camera_gain()
        last = self._noise_gain_pushed
        if last is not None and (gain == last or (gain > 0 and last > 0 and abs(gain / last - 1) < 0.005)):
            return
        for node in self._srgb_nodes:
            if node.is_valid():
                node.get_attribute("inputs:noiseGain").set(float(gain))
        self._noise_gain_pushed = gain

    def set_apply_zed_sim2real(self, enabled) -> None:
        """Live toggle of the camera model's master switch (change-gated): every real-camera effect
        follows it, each still under its own switch."""
        enabled = bool(enabled)
        if enabled == self.apply_zed_sim2real:
            return
        self.apply_zed_sim2real = enabled
        self._update_exposure_loop()
        self._update_white_balance_loop()
        self._push_noise_gain()
        self._push_blur_scale()
        self._push_vignetting()

    def destroy(self) -> None:
        """Clean up resources used by the annotator.

        Detaches all annotators from the render product, destroys OGN nodes if they
        were created, and destroys the render product.
        """

        # Before the annotators go: the exposure and white balance loops meter the left eye's HdrColor.
        if getattr(self, "exposure_loop", None) is not None:
            self.exposure_loop.destroy()
            self.exposure_loop = None
        if getattr(self, "white_balance_loop", None) is not None:
            self.white_balance_loop.destroy()
            self.white_balance_loop = None

        for node in self.nodes:
            try:
                if node.is_valid():
                    _p = node.get_prim_path()
                    self.graph.destroy_node(_p, True)
            except:
                carb.log_warn(f"[ZED] Node {node} not found")
        self.nodes = []
        self._srgb_nodes = []

        # Only once the sRGB encoders reading them are gone: SyntheticData silently skips detaching
        # a node that still has downstream connections, and the render product's destroy then leaves
        # it cached as a dead node, which breaks the next attach to the same path (Stop, then Play).
        for mv, rp_path in getattr(self, "_motion_annots", []):
            try:
                mv.detach(rp_path)
            except Exception:
                pass
        self._motion_annots = []

        if hasattr(self, "left_rgb_annot"):
            self.left_rgb_annot.detach(self.left_rp)
            self._left_rp.destroy()

        if self.is_stereo and not self.stream_depth and hasattr(self, "right_rgb_annot"):
            self.right_rgb_annot.detach(self.right_rp)
            self._right_rp.destroy()

        if self.stream_depth and hasattr(self, "depth_annot"):
            self.depth_annot.detach(self.depth_rp)
            self._depth_rp.destroy()

        carb.log_info(f"[ZED][port {self.port}] Annotators destroyed.")