# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import carb
from isaacsim.core.api.world import World
import omni.graph.core as og
import omni.replicator.core as rep
from omni.replicator.core.scripts.utils import viewport_manager
from isaacsim.core.utils.prims import is_prim_path_valid, get_prim_at_path
import omni.usd
from omni.syntheticdata import SyntheticData, SyntheticDataStage
from typing import Optional, Tuple, List

# Camera specifications mapping
_CAMERA_SPECIFICATIONS = {
    "HD4K": {
        "resolution": [3840, 2180],
        "focal_length": {"standard": 1483.2, "4mm": 2545}
    },
    "HD1200": {
        "resolution": [1920, 1200],
        "focal_length": {"standard": 741.6, "4mm": 1272.5}
    },
    "HD1080": {
        "resolution": [1920, 1080],
        "focal_length": {"standard": 741.6, "4mm": 1272.5}
    },
    "SVGA": {
        "resolution": [960, 600],
        "focal_length": {"standard": 370.8, "4mm": 636.25}
    }
}

# Camera configuration mapping
_CAMERA_CONFIGS = {
    "ZED_X": {"base_model": "ZED_X", "is_4mm": False, "is_stereo": True},
    "ZED_X_4MM": {"base_model": "ZED_X", "is_4mm": True, "is_stereo": True},
    "ZED_XM": {"base_model": "ZED_XM", "is_4mm": False, "is_stereo": True},
    "ZED_XM_4MM": {"base_model": "ZED_XM", "is_4mm": True, "is_stereo": True},
    "ZED_XONE_UHD": {"base_model": "ZED_XONE_UHD", "is_4mm": False, "is_stereo": False},
    "ZED_XONE_GS": {"base_model": "ZED_XONE_GS", "is_4mm": False, "is_stereo": False},
    "ZED_XONE_GS_4MM": {"base_model": "ZED_XONE_GS", "is_4mm": True, "is_stereo": False},
}

def get_resolution(camera_resolution: str) -> Optional[List[int]]:
    """Get the resolution of the camera.

    Args:
        camera_resolution: The resolution name of the camera

    Returns:
        The resolution as [width, height] or None if not recognized
    """
    spec = _CAMERA_SPECIFICATIONS.get(camera_resolution)
    return spec["resolution"] if spec else None

def get_focal_length(camera_resolution: List[int], is_4mm: bool) -> float:
    """Get the focal length for the given resolution and lens type.

    Args:
        camera_resolution: The camera resolution as [width, height]
        is_4mm: True if using 4mm lens, False for standard lens

    Returns:
        The focal length value, defaults to 741.6 if resolution not found
    """
    height = camera_resolution[1]
    
    # Find the specification by matching height
    for spec in _CAMERA_SPECIFICATIONS.values():
        if spec["resolution"][1] == height:
            return spec["focal_length"]["4mm" if is_4mm else "standard"]
    
    # Default fallback
    return 741.6

def get_camera_specifications(camera_resolution: str) -> Optional[dict]:
    """Get complete camera specifications for a given resolution.

    Args:
        camera_resolution: The resolution name of the camera

    Returns:
        Dictionary containing resolution and focal length data, or None if not found
    """
    return _CAMERA_SPECIFICATIONS.get(camera_resolution)

def get_camera_model(camera_model: str) -> str:
    """Get the base camera model name from the full camera model name.
    
    Args:
        camera_model: The full camera model name
        
    Returns:
        The base camera model, defaults to "ZED_X" if not recognized
    """
    config = _CAMERA_CONFIGS.get(camera_model)
    if config is None:
        carb.log_warn(f"Camera model {camera_model} not recognized, defaulting to ZED_X.")
        return "ZED_X"
    return config["base_model"]

def is_4mm_camera(camera_model: str) -> bool:
    """Check if the camera model is a 4mm variant.
    
    Args:
        camera_model: The camera model name
        
    Returns:
        True if the camera is a 4mm variant, False otherwise
    """
    config = _CAMERA_CONFIGS.get(camera_model)
    return config["is_4mm"] if config else False

def is_stereo_camera(camera_model: str) -> bool:
    """Check if the camera model supports stereo vision.
    
    Args:
        camera_model: The camera model name
        
    Returns:
        True if the camera supports stereo vision, False otherwise
    """
    config = _CAMERA_CONFIGS.get(camera_model)
    return config["is_stereo"] if config else True  # Default to stereo for unknown models

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
        serial_number = None,
        camera_model = "ZED_X",
        streaming_port = 30000,
        resolution = "HD1200",
        fps = 30,
        ipc = True
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
            carb.log_info("Single prim provided, assuming mono or stereo camera based on model.")
            self.camera_prim_path = camera_prim
            self.custom_stereo = False
        elif len(camera_prim) == 2:
            carb.log_info("Two prims provided, assuming custom stereo setup.")
            self.camera_prim_path = camera_prim
            self.custom_stereo = True
        else:
            carb.log_error(f"Expected 1 or 2 camera prims, got {len(camera_prim)}")
            return

        self.camera_prim_path = camera_prim
        self.serial_number = serial_number
        self.camera_model = camera_model
        self.port = streaming_port
        self.resolution = get_resolution(resolution)
        self.fps = fps
        self.ipc = ipc

        # Stereo if model is stereo OR user provides 2 prims
        self.is_stereo = is_stereo_camera(camera_model) or self.custom_stereo

        self.nodes = []
        self.zed_ = None

        self.build_annotators()
        print(
            f"[Port: {self.port}] Constructed annotator for "
            f"{'custom stereo' if self.custom_stereo else ('stereo' if self.is_stereo else 'mono')} camera."
        )


    def init_camera(self, camera_prim_path : str, resolution, is_4mm):
        result = False
        if is_prim_path_valid(camera_prim_path) == True:
                cam_prim = get_prim_at_path(prim_path=camera_prim_path)
                pixel_size = 3 * 1e-3
                f_stop = 0 # disable focusing
                f = get_focal_length(resolution, is_4mm)

                horizontal_aperture = pixel_size * resolution[0]
                vertical_aperture = pixel_size * resolution[1]
                focal_length = f * pixel_size

                cam_prim.GetAttribute("focalLength").Set(focal_length)
                cam_prim.GetAttribute("horizontalAperture").Set(horizontal_aperture)
                cam_prim.GetAttribute("verticalAperture").Set(vertical_aperture)
                cam_prim.GetAttribute("fStop").Set(f_stop)
                result = True
        else:
            carb.log_error(f"Camera prim path {camera_prim_path} is not valid.")
        return result

    def check_frame_rate(camera_frame_rate: int):
        if camera_frame_rate not in [15, 30, 60, 120]:
            carb.log_warn(f"Invalid frame rate passed: {camera_frame_rate}. Defaulting to 30.")
            return 30
        return camera_frame_rate

    def build_annotators(self) -> None:

        # Set device based on mode (CUDA for OGN nodes)
        device = "cuda"
        cams = []     
        self.annotators = {}

        is_4mm = is_4mm_camera(self.camera_model)
        base_camera_model = get_camera_model(self.camera_model)
         # Case 1: user gave 2 prims (custom stereo)
        if self.custom_stereo:
            cam_path = "/base_link/" + base_camera_model + "/Camera"
            left_full_path = self.camera_prim_path[0].pathString + cam_path
            right_full_path = self.camera_prim_path[1].pathString + cam_path

            if self.init_camera(left_full_path, self.resolution, is_4mm):
                name_left = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_left_rp"
                self._left_rp = viewport_manager.get_render_product(left_full_path, self.resolution, False, name_left)
                self.left_rp = self._left_rp.hydra_texture.get_render_product_path()
                self.left_rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=device)
                self.left_rgb_annot.attach(self.left_rp)
                self.annotators["Left"] = self.left_rgb_annot
                cams.append(["Left", name_left])

            if self.init_camera(right_full_path, self.resolution, is_4mm):
                name_right = f"{self.camera_prim_path[1].pathString.split('/')[-1]}_right_rp"
                self._right_rp = viewport_manager.get_render_product(right_full_path, self.resolution, False, name_right)
                self.right_rp = self._right_rp.hydra_texture.get_render_product_path()
                self.right_rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=device)
                self.right_rgb_annot.attach(self.right_rp)
                self.annotators["Right"] = self.right_rgb_annot
                cams.append(["Right", name_right])
         # Case 2: one prim (mono or stereo)
        else:
            if self.is_stereo is True:
                left_path = "/base_link/" + base_camera_model + "/CameraLeft"
            else:
                left_path = "/base_link/" + base_camera_model + "/Camera"          

            left_full_path = self.camera_prim_path[0].pathString + left_path
            # Init left camra (or mono camera)
            if self.init_camera(left_full_path, self.resolution, is_4mm):
                name_left = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_left_rp"
                self._left_rp = viewport_manager.get_render_product(left_full_path, self.resolution, False, name_left)
                self.left_rp = self._left_rp.hydra_texture.get_render_product_path()
                self.left_rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=device)
                self.left_rgb_annot.attach(self.left_rp)
                self.annotators["Left"] = self.left_rgb_annot
                cams.append(["Left", name_left])
            else:
                carb.log_warn(f"[{self.camera_prim_path[0].pathString}] Invalid or non existing zed camera, try to re-import your camera prim.")

            # Right Camera - Only for stereo cameras
            if self.is_stereo:
                right_path = "/base_link/" + base_camera_model + "/CameraRight"
                right_full_path = self.camera_prim_path[0].pathString + right_path
                if self.init_camera(right_full_path, self.resolution, is_4mm):
                    name_right = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_right_rp"
                    self._right_rp = viewport_manager.get_render_product(right_full_path, self.resolution, False, name_right)
                    self.right_rp = self._right_rp.hydra_texture.get_render_product_path()
                    self.right_rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=device)
                    self.right_rgb_annot.attach(self.right_rp)
                    self.annotators["Right"] = self.right_rgb_annot
                    cams.append(["Right", name_right])
            else:
                carb.log_warn(f"[{self.camera_prim_path[0].pathString}] Invalid or non existing zed camera, try to re-import your camera prim.")

        self.init_graph()
        self.build_graph(cams)

    def init_graph(self) -> None:

        # we are extanding the already existing synthetic data data graph
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

        # create/assign sync and time nodes
        _physics_nodes = {
            "sim_gate": {"node_type": "isaacsim.core.nodes.IsaacSimulationGate", "node": None},
            "sync": {"node_type": "omni.graph.action.RationalTimeSyncGate", "node": None},
            "sim_time": {"node_type": "isaacsim.core.nodes.IsaacReadSimulationTime", "node": None},
            "sys_time": {"node_type": "isaacsim.core.nodes.IsaacReadSystemTime", "node": None},
            "imu_sensor": {"node_type": "isaacsim.sensors.physics.IsaacReadIMU", "node": None}
        }

        for node_name, _ in _physics_nodes.items():
            node_path = self._graph_path + f"/{node_name}"
            node = self.graph.get_node(node_path)
            if not node:
                node = self.graph.create_node(node_path, _["node_type"], True)
            # else:
            #     carb.log_warn(f"{node_name} node already exists")
            _["node"] = node

        # assign to vars for clarity
        self.sim_gate = _physics_nodes["sim_gate"]["node"]
        self.sync_node = _physics_nodes["sync"]["node"]
        self.sim_time = _physics_nodes["sim_time"]["node"]
        self.sys_time = _physics_nodes["sys_time"]["node"]
        self.imu = _physics_nodes["imu_sensor"]["node"]

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
        self.zed_ = self.graph.create_node(self._graph_path + f"/zed_{self.port}", "sl.sensor.camera.bridge.OgnZEDSimCameraNode", True)
        self.zed_.get_attribute("inputs:port").set(self.port)
        self.zed_.get_attribute("inputs:width").set(self.resolution[0])
        self.zed_.get_attribute("inputs:height").set(self.resolution[1])
        self.zed_.get_attribute("inputs:fps").set(self.fps)

        for cam in cams:
            # get the annotator nodes and connect them to the zed node
            pfx = f"/{cam[1]}_"
            sufx = "buffPtr"

            annot_var_mapping = {}
            if self.annotators.get(cam[0]):
                annot_var_mapping[cam[0]] = {
                    "node_name": f"{pfx}LdrColorSD{sufx}",
                    "attr_suffix": "",
                    "attrs": ["bufferSize", "dataPtr"],
                }

            for an, _params in annot_var_mapping.items():
                ptr_node = self.annotators[cam[0]].get_node()
                ptr_node.get_attribute("outputs:exec").connect(self.sim_gate.get_attribute("inputs:execIn"), True)
                for p in _params["attrs"]:
                    target_attr = self.zed_.get_attribute(f"inputs:{p}{cam[0]}{_params['attr_suffix']}")
                    ptr_node.get_attribute(f"outputs:{p}").connect(target_attr, True)

        self.sim_time.get_attribute("outputs:simulationTime").connect(self.zed_.get_attribute("inputs:simulationTime"), True)
        self.sys_time.get_attribute("outputs:systemTime").connect(self.zed_.get_attribute("inputs:systemTime"), True)

        self.zed_.get_attribute("inputs:stream").set(value=True)
        self.zed_.get_attribute("inputs:cameraModel").set("VIRTUAL_ZED_X" if self.custom_stereo else self.camera_model)
        self.zed_.get_attribute("inputs:serialNumber").set(self.serial_number if self.serial_number else "-1")

        # connect sync node to zed node to trigger the stream
        self.sim_gate.get_attribute("outputs:execOut").connect(self.sync_node.get_attribute("inputs:execIn"), True)
        self.sync_node.get_attribute("outputs:execOut").connect(self.imu.get_attribute("inputs:execIn"), True)

        imu_path = "/base_link/" + self.camera_model + "/Imu_Sensor"
        imu_full_path = self.camera_prim_path[0].pathString + imu_path
        self.imu.get_attribute("inputs:imuPrim").set(imu_full_path)
        self.zed_.get_attribute("inputs:ipc").set(self.ipc)
        self.imu.get_attribute("outputs:orientation").connect(self.zed_.get_attribute("inputs:orientation"), True)
        self.imu.get_attribute("outputs:linAcc").connect(self.zed_.get_attribute("inputs:linearAcceleration"), True)
        self.imu.get_attribute("outputs:execOut").connect(self.zed_.get_attribute("inputs:execIn"), True)

        self.nodes = [self.sim_gate, self.sync_node, self.sim_time, self.sys_time, self.imu, self.zed_]

    def destroy(self) -> None:
        """
        Clean up resources used by the annotator.

        This method detaches all annotators from the render product,
        destroys OGN nodes if they were created, and destroys the render product.
        """
        self.zed_.get_attribute("inputs:stream").set(value=False)
        for node in self.nodes:
            try:
                if node.is_valid():
                    _p = node.get_prim_path()
                    self.graph.destroy_node(_p, True)
            except:
                carb.log_warn("Node {} not found".format(node))
        self.nodes = []

        if hasattr(self, "left_rgb_annot"):
            self.left_rgb_annot.detach(self.left_rp)
            self._left_rp.destroy()

        if self.is_stereo and hasattr(self, "right_rgb_annot"):
            self.right_rgb_annot.detach(self.right_rp)
            self._right_rp.destroy()


        self._left_rp.destroy()
        self._right_rp.destroy()

        print(f"[port {self.port}] Annotators destroyed.")