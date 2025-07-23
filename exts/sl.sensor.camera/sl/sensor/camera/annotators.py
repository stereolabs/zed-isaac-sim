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

def get_resolution(camera_resolution: str):
        """Get the resolution of the camera

        Args:
            camera_resolution (str): the resolution name of the camera

        Returns:
            list: the resolution of the camera
        """
        if camera_resolution == "HD1200":
            result = [1920, 1200]
        elif camera_resolution == "HD1080":
            result = [1920, 1080]
        elif camera_resolution == "SVGA":
            result = [960, 600]
        else:
            result = None
        return result

def get_focal_length(camera_resolution):
        f = 741.6
        if camera_resolution[1] == 1200:
            f = 741.6
        elif camera_resolution[1] == 1080:
            f = 741.6
        elif camera_resolution[1] == 600:
            f = 370.8
        return f

class ZEDAnnotator:
    """
    Captures camera data and streams it to the ZED SDK.

    This class creates annotators for RGB from a zed camera,
    and streams this data to the ZED SDK. It can operate in two modes:
    - OGN node mode (C++ implementation)
    """

    def __init__(
        self,
        camera_prim : str,
        camera_model = "ZED_X",
        streaming_port = 30000,
        resolution = "HD1200",
        fps = 30,
        ipc = True
        ):
        """
        Initializes a ZEDAnnotator object.
        """

        # Get stage and synthetic data interface
        self.stage = omni.usd.get_context().get_stage()

        self.camera_prim_path = camera_prim
        self.camera_model = camera_model
        self.port = streaming_port
        self.resolution = get_resolution(resolution)
        self.fps = fps
        self.ipc = ipc

        self.nodes = []
        self.zed_ = None

        self.build_annotators()
        print(f"[Port: {self.port}] Constructed annotator.")


    def init_camera(self, camera_prim_path : str, resolution):
        result = False

        if is_prim_path_valid(camera_prim_path) == True:
                cam_prim = get_prim_at_path(prim_path=camera_prim_path)
                pixel_size = 3 * 1e-3
                f_stop = 0 # disable focusing
                f = get_focal_length(resolution)

                horizontal_aperture = pixel_size * resolution[0]
                vertical_aperture = pixel_size * resolution[1]
                focal_length = f * pixel_size

                cam_prim.GetAttribute("focalLength").Set(focal_length)
                cam_prim.GetAttribute("horizontalAperture").Set(horizontal_aperture)
                cam_prim.GetAttribute("verticalAperture").Set(vertical_aperture)
                cam_prim.GetAttribute("fStop").Set(f_stop)
                result = True
        return result

    def check_frame_rate(camera_frame_rate: int):
        if camera_frame_rate not in [15, 30, 60]:
            carb.log_warn(f"Invalid frame rate passed: {camera_frame_rate}. Defaulting to 30.")
            return 30
        return camera_frame_rate

    def build_annotators(self) -> None:

        # Set device based on mode (CUDA for OGN nodes)
        device = "cuda"

        # Create render product for the camera
        left_path = "/base_link/" + self.camera_model + "/CameraLeft"
        right_path = "/base_link/" + self.camera_model + "/CameraRight"

        left_full_path = self.camera_prim_path[0].pathString + left_path
        right_full_path = self.camera_prim_path[0].pathString + right_path

        res = self.init_camera(left_full_path, self.resolution)
        res = res and self.init_camera(left_full_path, self.resolution)
        if not res:
            carb.log_warn(f"[{self.camera_prim_path[0].pathString}] Invalid or non existing zed camera, try to re-import your camera prim.")

        self.annotators = {}

        # Left Camera
        name_left = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_left_rp"
        self._left_rp = viewport_manager.get_render_product(left_full_path, self.resolution, False, name_left)
        self.left_rp = self._left_rp.hydra_texture.get_render_product_path()
        # Right Camera
        name_right = f"{self.camera_prim_path[0].pathString.split('/')[-1]}_right_rp"
        self._right_rp = viewport_manager.get_render_product(right_full_path, self.resolution, False, name_right)
        self.right_rp = self._right_rp.hydra_texture.get_render_product_path()

        self.left_rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=device)
        self.left_rgb_annot.attach(self.left_rp)
        self.annotators["Left"] = self.left_rgb_annot

        self.right_rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb", device=device)
        self.right_rgb_annot.attach(self.right_rp)
        self.annotators["Right"] = self.right_rgb_annot

        self.init_graph()
        self.build_graph(name_left, name_right)

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

    def build_graph(self, left_rp_name: str, right_rp_name: str) -> None:
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

        cams = [["Left", left_rp_name], ["Right", right_rp_name]]

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
        self.zed_.get_attribute("inputs:cameraModel").set(self.camera_model)

        imu_path = "/base_link/" + self.camera_model + "/Imu_Sensor"
        imu_full_path = self.camera_prim_path[0].pathString + imu_path

        # connect sync node to zed node to trigger the stream
        self.sim_gate.get_attribute("outputs:execOut").connect(self.sync_node.get_attribute("inputs:execIn"), True)
        self.sync_node.get_attribute("outputs:execOut").connect(self.imu.get_attribute("inputs:execIn"), True)

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

        self.left_rgb_annot.detach(self.left_rp)
        self.right_rgb_annot.detach(self.right_rp)

        self._left_rp.destroy()
        self._right_rp.destroy()

        print(f"[port {self.port}] Annotators destroyed.")