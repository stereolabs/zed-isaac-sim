# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import carb
import omni.graph.core as og
import omni.usd
from pxr import Gf

try:
    import omni.replicator.core as rep
    from omni.replicator.core.scripts.utils import viewport_manager
    from isaacsim.core.utils.prims import is_prim_path_valid, get_prim_at_path
    from omni.syntheticdata import SyntheticData, SyntheticDataStage
except ImportError:
    rep = viewport_manager = is_prim_path_valid = get_prim_at_path = None
    SyntheticData = SyntheticDataStage = None

from .utils import (
    get_camera_subpaths,
    is_stereo_camera,
    get_camera_model,
    get_lens_type,
    get_sdk_model_id,
    get_sim_lens_type_id,
    MODEL_ID_VIRTUAL_ZED_X,
    get_resolution,
    get_focal_length,
    get_pixel_size,
    get_distortion_coefficients,
    get_optical_center,
    get_allowed_resolutions,
    is_resolution_valid,
)

# Shared across all streamer classes to ensure port uniqueness
used_ports = set()

# Depth streamed to the ZED SDK (ingestCustomDepth) is fixed at this resolution.
_STREAM_DEPTH_RESOLUTION = [896, 512]


def _set_motion_blur(enabled: bool) -> None:
    """RTX motion-vector motion blur, part of the sim2real look: real ZED X frames smear
    during fast camera/robot motion (rolling exposure over a fraction of the frame time).
    These are global RTX post settings, so they affect every render product including the
    viewport - acceptable, since the effect is only visible on motion. exposureFraction
    approximates the ZED X shutter (~40% of the 33 ms frame at indoor light levels)."""
    import carb.settings
    s = carb.settings.get_settings()
    s.set("/rtx/post/motionblur/enabled", bool(enabled))
    if enabled:
        s.set("/rtx/post/motionblur/maxBlurDiameterFraction", 0.03)
        s.set("/rtx/post/motionblur/exposureFraction", 0.65)
        s.set("/rtx/post/motionblur/numSamples", 8)

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
        apply_zed_sim2real = False,
        zed_sim2real_scene_lux = 0.0,
        zed_sim2real_ae_target = -1.0
        ):

        """
        Initializes a ZEDAnnotator object.
        camera_prim can be a list of:
          - a single prim (stereo or mono)
          - two prims (custom stereo made of two monos)
        """

        # Get stage and synthetic data interface
        self.stage = omni.usd.get_context().get_stage()

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

        # Guard against a resolution that the selected model does not support
        # (e.g. graphs authored via script, or the in-canvas node body which is
        # not filtered by the property panel template). Clamp to a valid value.
        if not is_resolution_valid(camera_model, resolution):
            allowed = get_allowed_resolutions(camera_model)
            fallback = allowed[0] if allowed else resolution
            carb.log_warn(
                f"[ZED] Resolution '{resolution}' is not supported by camera model "
                f"'{camera_model}'. Falling back to '{fallback}'."
            )
            resolution = fallback

        self.resolution = get_resolution(camera_model, resolution)
        self.fps = ZEDAnnotator.check_frame_rate(fps)
        self.bitrate = bitrate
        self.chunk_size = chunk_size
        self.transport_layer_mode = transport_layer_mode
        self.apply_zed_sim2real = bool(apply_zed_sim2real)
        self.zed_sim2real_scene_lux = float(zed_sim2real_scene_lux)
        self.zed_sim2real_ae_target = float(zed_sim2real_ae_target)

        # Stereo if model is stereo OR user provides 2 prims
        self.is_stereo = is_stereo_camera(camera_model) or self.custom_stereo

        self.stream_depth = stream_depth

        self.nodes = []
        self.zed_ = None

        self.build_annotators()
        mode_str = "left+depth" if self.stream_depth else ('custom stereo' if self.custom_stereo else ('stereo' if self.is_stereo else 'mono'))
        print(f"[Port: {self.port}] Constructed annotator for {mode_str} camera.")

    def init_camera(self, camera_prim_path : str, resolution, lens_type):
        result = False
        if is_prim_path_valid(camera_prim_path) == True:
                cam_prim = get_prim_at_path(prim_path=camera_prim_path)
                pixel_size = get_pixel_size(self.camera_model) * 1e-3
                f_stop = 0 # disable focusing
                f = get_focal_length(self.camera_model, resolution, lens_type)

                horizontal_aperture = pixel_size * resolution[0]
                vertical_aperture = pixel_size * resolution[1]
                focal_length = f * pixel_size

                cam_prim.GetAttribute("focalLength").Set(focal_length)
                cam_prim.GetAttribute("horizontalAperture").Set(horizontal_aperture)
                cam_prim.GetAttribute("verticalAperture").Set(vertical_aperture)
                cam_prim.GetAttribute("fStop").Set(f_stop)

                # Multi-tick rendering (Isaac Sim 6.0): render this camera only at the ZED's
                # target FPS instead of every app frame.
                cam_prim.ApplyAPI("OmniSensorAPI")
                cam_prim.GetAttribute("omni:sensor:tickRate").Set(float(self.fps))

                # Apply lens distortion for fisheye camera models
                distortion = get_distortion_coefficients(self.camera_model)
                if distortion is None:
                    # Revert to pinhole: remove any distortion schema left on the prim by a previous run
                    for schema in cam_prim.GetAppliedSchemas():
                        if schema.startswith("OmniLensDistortion"):
                            cam_prim.RemoveAppliedSchema(schema)
                    if cam_prim.HasAttribute("omni:lensdistortion:model"):
                        cam_prim.RemoveProperty("omni:lensdistortion:model")
                else:
                    cx, cy = get_optical_center(self.camera_model, resolution)
                    cam_prim.ApplyAPI("OmniLensDistortionOpenCvFisheyeAPI")
                    cam_prim.GetAttribute("omni:lensdistortion:model").Set("opencvFisheye")
                    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:k1").Set(distortion[0])
                    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:k2").Set(distortion[1])
                    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:k3").Set(distortion[2])
                    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:k4").Set(distortion[3])
                    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:cx").Set(cx)
                    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:cy").Set(cy)
                    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:fx").Set(f)
                    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:fy").Set(f)
                    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:imageSize").Set(Gf.Vec2i(resolution[0], resolution[1]))

                result = True
        else:
            carb.log_error(f"[ZED] Camera prim path {camera_prim_path} is not valid.")
        return result

    @staticmethod
    def check_frame_rate(camera_frame_rate: int):
        if camera_frame_rate not in [15, 30, 60, 120]:
            carb.log_warn(f"[ZED] Invalid frame rate passed: {camera_frame_rate}. Defaulting to 30.")
            return 30
        return camera_frame_rate

    def build_annotators(self) -> None:
        # Set device based on mode (CUDA for OGN nodes)
        device = "cuda"
        cams = []
        self.annotators = {}

        lens_type = get_lens_type(self.camera_model)
        subpaths = get_camera_subpaths(self.camera_model)
         # Case 1: user gave 2 prims (custom stereo)
        if self.custom_stereo:
            left_full_path = f"{self.camera_prim_path[0].pathString}/{subpaths['mono']}"
            right_full_path = f"{self.camera_prim_path[1].pathString}/{subpaths['mono']}"

            if self.init_camera(left_full_path, self.resolution, lens_type):
                name_left = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_left_rp"
                self._left_rp = viewport_manager.get_render_product(left_full_path, self.resolution, False, name_left)
                self.left_rp = self._left_rp.hydra_texture.get_render_product_path()
                self.left_rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=device)
                self.left_rgb_annot.attach(self.left_rp)
                self.annotators["Left"] = self.left_rgb_annot
                cams.append(["Left", name_left])

            if self.stream_depth:
                depth_res = _STREAM_DEPTH_RESOLUTION
                name_depth = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_depth_rp"
                self._depth_rp = viewport_manager.get_render_product(left_full_path, depth_res, False, name_depth)
                self.depth_rp = self._depth_rp.hydra_texture.get_render_product_path()
                self.depth_annot = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane", device=device)
                self.depth_annot.attach(self.depth_rp)
                self.annotators["Depth"] = self.depth_annot
                cams.append(["Depth", name_depth])
            elif self.init_camera(right_full_path, self.resolution, lens_type):
                name_right = f"{self.camera_prim_path[1].pathString.split('/')[-1]}_right_rp"
                self._right_rp = viewport_manager.get_render_product(right_full_path, self.resolution, False, name_right)
                self.right_rp = self._right_rp.hydra_texture.get_render_product_path()
                self.right_rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=device)
                self.right_rgb_annot.attach(self.right_rp)
                self.annotators["Right"] = self.right_rgb_annot
                cams.append(["Right", name_right])
        # Case 2: one prim (mono or stereo)
        else:
            # subpaths["left"] resolves to CameraLeft for stereo models, Camera for mono.
            left_full_path = f"{self.camera_prim_path[0].pathString}/{subpaths['left']}"
            # Init left camra (or mono camera)
            if self.init_camera(left_full_path, self.resolution, lens_type):
                name_left = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_left_rp"
                self._left_rp = viewport_manager.get_render_product(left_full_path, self.resolution, False, name_left)
                self.left_rp = self._left_rp.hydra_texture.get_render_product_path()
                self.left_rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=device)
                self.left_rgb_annot.attach(self.left_rp)
                self.annotators["Left"] = self.left_rgb_annot
                cams.append(["Left", name_left])
            else:
                carb.log_warn(f"[ZED] [{self.camera_prim_path[0].pathString}] Invalid or non existing zed camera, try to re-import your camera prim.")

            # Depth annotator - when stream_depth is enabled
            if self.stream_depth:
                depth_res = _STREAM_DEPTH_RESOLUTION
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
                if self.init_camera(right_full_path, self.resolution, lens_type):
                    name_right = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_right_rp"
                    self._right_rp = viewport_manager.get_render_product(right_full_path, self.resolution, False, name_right)
                    self.right_rp = self._right_rp.hydra_texture.get_render_product_path()
                    self.right_rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=device)
                    self.right_rgb_annot.attach(self.right_rp)
                    self.annotators["Right"] = self.right_rgb_annot
                    cams.append(["Right", name_right])
                else:
                    carb.log_warn(f"[ZED] [{self.camera_prim_path[0].pathString}] Invalid or non existing zed camera, try to re-import your camera prim.")


        self.init_graph()
        self.build_graph(cams)

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
            f"sys_time_{self.port}": {"node_type": "isaacsim.core.nodes.IsaacReadSystemTime", "node": None},
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

        # assign to vars for clarity
        self.sync_node = _physics_nodes[f"sync_{self.port}"]["node"]
        self.sim_time = _physics_nodes[f"sim_time_{self.port}"]["node"]
        self.sys_time = _physics_nodes[f"sys_time_{self.port}"]["node"]
        self.imu = _physics_nodes[f"imu_sensor_{self.port}"]["node"]

    def build_graph(self, cams) -> None:
        """
        Build the OGN graph for streaming camera data.

        This method creates the OGN nodes needed for streaming of camera data

        """
        # get the graph dispatcher node
        dispacher_node = self.graph.get_node(self._graph_path + "/PostProcessDispatcher")
        # connect dispacth to sync node
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
                ptr_node = self.annotators[side].get_node()
                ptr_node.get_attribute("outputs:exec").connect(self.sync_node.get_attribute("inputs:execIn"), True)
                for p in _params["attrs"]:
                    target_attr = self.zed_.get_attribute(f"inputs:{p}{side}{_params['attr_suffix']}")
                    ptr_node.get_attribute(f"outputs:{p}").connect(target_attr, True)

        self.sim_time.get_attribute("outputs:simulationTime").connect(self.zed_.get_attribute("inputs:simulationTime"), True)
        self.sys_time.get_attribute("outputs:systemTime").connect(self.zed_.get_attribute("inputs:systemTime"), True)

        self.zed_.get_attribute("inputs:stream").set(value=True)
        self.zed_.get_attribute("inputs:applyZedSim2Real").set(self.apply_zed_sim2real)
        self.zed_.get_attribute("inputs:zedSim2RealSceneLux").set(self.zed_sim2real_scene_lux)
        self.zed_.get_attribute("inputs:zedSim2RealAeTarget").set(self.zed_sim2real_ae_target)
        _set_motion_blur(self.apply_zed_sim2real)
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

        # connect sync node to zed node to trigger the stream
        self.sync_node.get_attribute("outputs:execOut").connect(self.imu.get_attribute("inputs:execIn"), True)
        self.sync_node.get_attribute("outputs:rationalTimeDenominator").connect(self.sim_time.get_attribute("inputs:referenceTimeDenominator"), True)
        self.sync_node.get_attribute("outputs:rationalTimeNumerator").connect(self.sim_time.get_attribute("inputs:referenceTimeNumerator"), True)

        imu_full_path = f"{self.camera_prim_path[0].pathString}/{get_camera_subpaths(self.camera_model)['imu']}"
        self.imu.get_attribute("inputs:imuPrim").set(imu_full_path)
        self.zed_.get_attribute("inputs:bitrate").set(self.bitrate)
        self.zed_.get_attribute("inputs:chunkSize").set(self.chunk_size)
        self.zed_.get_attribute("inputs:transportLayerMode").set(self.transport_layer_mode)
        self.imu.get_attribute("outputs:orientation").connect(self.zed_.get_attribute("inputs:orientation"), True)
        self.imu.get_attribute("outputs:linAcc").connect(self.zed_.get_attribute("inputs:linearAcceleration"), True)
        self.imu.get_attribute("outputs:execOut").connect(self.zed_.get_attribute("inputs:execIn"), True)

        self.nodes = [self.sync_node, self.sim_time, self.sys_time, self.imu, self.zed_]

    def set_sim2real(self, apply_zed_sim2real, zed_sim2real_scene_lux, zed_sim2real_ae_target=None) -> None:
        """Push a live sim2real-config change onto the streaming node.

        The C++ node reads these inputs every frame, so forwarding a changed value here takes
        effect immediately - no graph rebuild or stop/restart. Change-gated so the common
        no-change case costs only a few comparisons; safe no-op before the node exists.
        """
        if self.zed_ is None:
            return
        apply = bool(apply_zed_sim2real)
        lux = float(zed_sim2real_scene_lux)
        if apply != self.apply_zed_sim2real:
            self.zed_.get_attribute("inputs:applyZedSim2Real").set(apply)
            self.apply_zed_sim2real = apply
            _set_motion_blur(apply)
        if lux != self.zed_sim2real_scene_lux:
            self.zed_.get_attribute("inputs:zedSim2RealSceneLux").set(lux)
            self.zed_sim2real_scene_lux = lux
        if zed_sim2real_ae_target is not None:
            target = float(zed_sim2real_ae_target)
            if target != self.zed_sim2real_ae_target:
                self.zed_.get_attribute("inputs:zedSim2RealAeTarget").set(target)
                self.zed_sim2real_ae_target = target

    def destroy(self) -> None:
        """
        Clean up resources used by the annotator.

        This method detaches all annotators from the render product,
        destroys OGN nodes if they were created, and destroys the render product.
        """

        for node in self.nodes:
            try:
                if node.is_valid():
                    _p = node.get_prim_path()
                    self.graph.destroy_node(_p, True)
            except:
                carb.log_warn(f"[ZED] Node {node} not found")
        self.nodes = []

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