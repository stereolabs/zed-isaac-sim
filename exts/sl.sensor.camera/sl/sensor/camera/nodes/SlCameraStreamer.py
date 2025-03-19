"""
This is the implementation of the OGN node defined in SlCameraStreamer.ogn
"""
import carb
from dataclasses import dataclass
import omni.replicator.core as rep
from isaacsim.core.prims import SingleXFormPrim
from pxr import Vt
from isaacsim.core.utils.prims import is_prim_path_valid, get_prim_at_path
from isaacsim.core.nodes.bindings import _isaacsim_core_nodes
from isaacsim.sensors.physics import _sensor
from isaacsim.core.api import SimulationContext
from carb.events import IEvent
import omni.kit.commands

from sl.sensor.camera.pyzed_sim_streamer import ZEDSimStreamer, ZEDSimStreamerParams 
import time
import copy
from sl.sensor.camera.ogn.SlCameraStreamerDatabase import SlCameraStreamerDatabase

LEFT_CAMERA_PATH = "/base_link/ZED_X/CameraLeft"
RIGHT_CAMERA_PATH = "/base_link/ZED_X/CameraRight"
IMU_PRIM_PATH = "/base_link/ZED_X/Imu_Sensor"
CHANNELS = 3

class SlCameraStreamer:
    """
         Streams camera data to the ZED SDK
    """
    @dataclass
    class State:
        initialized: bool = False
        render_product_path_left = None
        render_product_path_right = None
        annotator_left = None
        annotator_right = None
        core_nodes_interface = None
        pyzed_streamer = None
        start_time = -1.0
        last_timestamp = 0.0
        target_fps = 30
        camera_prim_name = None
        override_simulation_time = False
        imu_sensor_interface = None
        imu_prim_path = ""
        imu_prim = None
        invalid_images_count = 0
        timeline_stop_sub = None
        timeline_start_sub = None
        pass

    @staticmethod
    def internal_state() -> State:
        return SlCameraStreamer.State()

    @staticmethod
    def get_render_product_path(camera_path :str, render_product_size = [1920, 1200], force_new=True):
        """Helper function to get render product path

        Args:
            camera_path (str): the path of the camera prim
            render_product_size (list, optional): the resolution of the image. Defaults to HD1200.
            force_new (bool, optional): forces the creation of a new render product. Defaults to True.

        Returns:
            str: the created render product 
        """
        render_product_path = ""
        render_product_path = rep.create.render_product(camera_path, render_product_size, force_new=force_new)
        print("create new render product")
        return render_product_path
    
    @staticmethod
    def get_image_data(annotator, data_shape: tuple):
        """Helper function to fetch image data.

        Args:
            annotator: the annotator to fetch the data

        Returns:
            3D array: the image data, or None if unsuccessful
            bool: True if successful, false otherwise
        """
        data = annotator.get_data()
        result = True
        try:
            if data is None:
                result = False
                return data, result
            data = data[:, :, :3]
            if not data.shape == data_shape:
                result = False
        except:
            return None, False
        return data, result
    
    @staticmethod
    def check_camera(camera_prim_path : str):
        """Check if the camera properties are valid. If not, set them to default values.

        Args:
            camera_prim_path (str): the path of the camera prim

        Returns:
            bool: True if the camera properties are valid, False otherwise
        """
        result = False
        default_fl, default_apt_h, default_apt_v = 2.208, 5.76, 3.24
        default_projection_type = "pinhole"
        allowed_error = 0.01
        if is_prim_path_valid(camera_prim_path) == True:
            cam_prim = get_prim_at_path(prim_path=camera_prim_path)
            fl = cam_prim.GetAttribute("focalLength")
            apt_h = cam_prim.GetAttribute("horizontalAperture")
            apt_v = cam_prim.GetAttribute("verticalAperture")
            projection = cam_prim.GetAttribute("cameraProjectionType")
            result = True
            projection_type = projection.Get()
            if projection_type and ((abs(fl.Get() - default_fl) >= allowed_error)
                or (abs(apt_h.Get() - default_apt_h) >= allowed_error)
                or (abs(apt_v.Get() - default_apt_v) >= allowed_error)):
                fl.Set(default_fl)
                apt_h.Set(default_apt_h)
                apt_v.Set(default_apt_v)
                projection.Set(Vt.Token(default_projection_type))
                carb.log_warn(f"Camera {camera_prim_path} properties are not valid. Setting them back to default value.")
                result = True
        return result
    
    @staticmethod
    def get_focal_length(camera_resolution):
        f = 741.6
        if camera_resolution[1] == 1200:
            f = 741.6
        elif camera_resolution[1] == 1080:
            f = 741.6
        elif camera_resolution[1] == 600:
            f = 370.8
        return f

    @staticmethod
    def init_camera(camera_prim_path : str, resolution):
        result = False

        if is_prim_path_valid(camera_prim_path) == True:
                cam_prim = get_prim_at_path(prim_path=camera_prim_path)
                pixel_size = 3 * 1e-3
                f_stop = 0 # disable focusing
                f = SlCameraStreamer.get_focal_length(resolution)

                horizontal_aperture = pixel_size * resolution[0]
                vertical_aperture = pixel_size * resolution[1]
                focal_length = f * pixel_size

                cam_prim.GetAttribute("focalLength").Set(focal_length)
                cam_prim.GetAttribute("horizontalAperture").Set(horizontal_aperture)
                cam_prim.GetAttribute("verticalAperture").Set(vertical_aperture)
                cam_prim.GetAttribute("fStop").Set(f_stop)
                result = True
        return result

    @staticmethod
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

    @staticmethod
    def check_frame_rate(camera_frame_rate: int):
        if camera_frame_rate not in [15, 30, 60]:
            carb.log_warn(f"Invalid frame rate passed: {camera_frame_rate}. Defaulting to 30.")
            return 30
        return camera_frame_rate

    @staticmethod
    def createStreamer(db) -> bool:
        db.internal_state.imu_sensor_interface = _sensor.acquire_imu_sensor_interface()
        db.internal_state.core_nodes_interface = _isaacsim_core_nodes.acquire_interface()

        if db.inputs.camera_prim is None:
            carb.log_error("Invalid Camera prim")
            print("invalid camera prim")
            return

        # Check port
        port = db.inputs.streaming_port
        if  port <= 0 or port %2 == 1:
            carb.log_warn("Invalid port passed! It must be a positive even number. Will default to 30000.")
            port = 30000
        
        db.internal_state.override_simulation_time = db.inputs.use_system_time
        if db.internal_state.override_simulation_time:
            carb.log_warn("Overriding simulation time by system time")
        
        if not len(db.inputs.camera_prim) == 1:
            print("please pass the corerct target")
            carb.log_error("Please pass the correct target to the omnigraph node")
            return False
        db.internal_state.camera_prim_name = db.inputs.camera_prim[0].name

        # Check resolution and retrieve width and height
        resolution = SlCameraStreamer.get_resolution(db.inputs.resolution)
        if resolution is None:
            resolution = [1920, 1200]
            carb.log_warn(f"Invalid resolution passed. Defaulting to HD1200.")

        left_cam_path = db.inputs.camera_prim[0].pathString + LEFT_CAMERA_PATH
        right_cam_path = db.inputs.camera_prim[0].pathString + RIGHT_CAMERA_PATH
        res = SlCameraStreamer.init_camera(left_cam_path, resolution)
        res = res and SlCameraStreamer.init_camera(right_cam_path, resolution)
        if not res:
            carb.log_warn(f"[{db.inputs.camera_prim[0].GetPrimPath()}] Invalid or non existing zed camera, try to re-import your camera prim.")

        # Check frame rate
        db.internal_state.target_fps = SlCameraStreamer.check_frame_rate(db.inputs.fps)

        if (db.internal_state.annotator_left is None):
            db.render_product_path_left = SlCameraStreamer.get_render_product_path(left_cam_path, render_product_size=resolution)
            db.internal_state.annotator_left = rep.AnnotatorRegistry.get_annotator("rgb", device="cuda", do_array_copy=False)
            db.internal_state.annotator_left.attach([db.render_product_path_left])

        if (db.internal_state.annotator_right is None):
            db.render_product_path_right = SlCameraStreamer.get_render_product_path(right_cam_path, render_product_size=resolution)
            db.internal_state.annotator_right = rep.AnnotatorRegistry.get_annotator("rgb", device="cuda", do_array_copy=False)
            db.internal_state.annotator_right.attach([db.render_product_path_right])

        db.internal_state.imu_prim_path = db.inputs.camera_prim[0].pathString + IMU_PRIM_PATH
        db.internal_state.imu_prim = SingleXFormPrim(prim_path=db.internal_state.imu_prim_path)

        # Setup streamer parameters
        db.internal_state.pyzed_streamer = ZEDSimStreamer()

        # Check serial number
        serial_number = db.inputs.serial_number
        camera_ids = db.internal_state.pyzed_streamer.getVirtualCameraIdentifiers()
        if serial_number not in camera_ids:
            serial_number = next(iter(camera_ids))
            carb.log_warn(f"Invalid serial number passed. Defaulting to: {serial_number}.")

        streamer_params = ZEDSimStreamerParams()
        streamer_params.image_width = resolution[0]
        streamer_params.image_height = resolution[1]
        streamer_params.fps = db.internal_state.target_fps
        streamer_params.alpha_channel_included = False
        streamer_params.rgb_encoded = True
        streamer_params.serial_number = serial_number
        streamer_params.port = port
        streamer_params.codec_type = 1
        init_error = db.internal_state.pyzed_streamer.init(streamer_params)
        if not init_error:
            carb.log_error(f"Failed to initialize the ZED SDK streamer with serial number {serial_number}.")
            return False

        # set state to initialized
        carb.log_info(f"Streaming camera {db.internal_state.camera_prim_name} at port {port} and using serial number {serial_number}.")
        db.internal_state.invalid_images_count = 0
        db.internal_state.last_timestamp = 0.0
        db.internal_state.data_shape = (resolution[1], resolution[0], CHANNELS)
        db.internal_state.initialized = True

    @staticmethod
    def compute(db) -> bool:
        """Compute the outputs from the current input"""
        if db.per_instance_state.initialized is False:
            # ZED Sim streamer cleanup on timeline stop
            def on_timeline_stop(event: carb.events.IEvent):
                SlCameraStreamer.release(db)

            #def on_timeline_start(event: carb.events.IEvent):
            #    SlCameraStreamer.createStreamer(db)
            #    print("play")

            SlCameraStreamer.createStreamer(db)

            timeline = omni.timeline.get_timeline_interface()
            db.per_instance_state.timeline_stop_sub = timeline.get_timeline_event_stream().create_subscription_to_pop_by_type(
                int(omni.timeline.TimelineEventType.STOP),
                on_timeline_stop
            )

            #db.per_instance_state.timeline_start_sub = timeline.get_timeline_event_stream().create_subscription_to_pop_by_type(
            #    int(omni.timeline.TimelineEventType.PLAY),
            #    on_timeline_start
            #)

        try:
            ts : int = 0
            if db.internal_state.initialized is True:
                left, right = None, None
                # Get simulation time in seconds
                current_time = db.internal_state.core_nodes_interface.get_sim_time()

                # Reset last_timestamp between different play sessions
                if db.internal_state.last_timestamp > current_time:
                    db.internal_state.last_timestamp = current_time

                delta_time = current_time - db.internal_state.last_timestamp

                # Skip data fetch if the time between frames is too short
                if delta_time < 1.0 / db.internal_state.target_fps:
                    return False
                
                # we fetch image data from annotators - we do it sequentially to avoid fetching both if one fails
                left, res = SlCameraStreamer.get_image_data(db.internal_state.annotator_left,
                                                            db.internal_state.data_shape)
                if res == False:
                    db.internal_state.invalid_images_count +=1
                    if db.internal_state.invalid_images_count >= 10:
                        carb.log_warn(f"{db.internal_state.camera_prim_name} - Left camera retrieved unexpected "
                                      "data shape, skipping frame.")
                    return False # no need to continue compute

                right, res = SlCameraStreamer.get_image_data(db.internal_state.annotator_right,
                                                             db.internal_state.data_shape)
                if res == False:
                    db.internal_state.invalid_images_count +=1
                    if db.internal_state.invalid_images_count >= 10:
                        carb.log_warn(f"{db.internal_state.camera_prim_name} - Right camera retrieved unexpected "
                                      "data shape, skipping frame.")
                    return False # no need to continue compute
                else:
                    db.internal_state.invalid_images_count = 0 # reset counter once both frame were grabbed

                # Fetch simulation time and change its reference point to (system time at start)
                if db.internal_state.start_time == -1:
                    carb.log_info(f"{db.internal_state.camera_prim_name} - Starting stream to the ZED SDK")
                if db.internal_state.start_time == -1 or current_time < db.internal_state.last_timestamp:
                    db.internal_state.start_time = int(time.time_ns())
                    carb.log_info(f"{db.internal_state.camera_prim_name} - Setting initial streaming time stamp to: {db.internal_state.start_time}")

                ts = int(db.internal_state.start_time + current_time * 1000000000)
                
                # override with system time
                if db.internal_state.override_simulation_time:
                    ts = int(time.time_ns())

                # fetch IMU data if the imu prim is there - this check allows user to basically delete
                # their IMUand still have access to the image functionality without issues in Isaac Sim
                lin_acc_x, lin_acc_y, lin_acc_z = 0, 0, 0
                orientation = [0]*4
                if is_prim_path_valid(db.internal_state.imu_prim_path) == True and db.internal_state.imu_prim is not None:
                    imu_prim = db.internal_state.imu_prim
                    temp_orientation = imu_prim.get_world_pose()[1]
                    swp = copy.deepcopy(temp_orientation)
                    orientation = [swp[0], -swp[1], -swp[3], -swp[2]]
                    if(orientation[0] == 0 and orientation[1] == 0 and  orientation[2] == 0 and orientation[3] == 0):
                        carb.log_warn(f"{db.internal_state.camera_prim_name} - Received invalid orientation, skipped frame !")
                        return False
                    if imu_prim.is_valid() == True:
                        if db.internal_state.imu_sensor_interface.is_imu_sensor(db.internal_state.imu_prim_path) == True:
                            imu_reading = db.internal_state.imu_sensor_interface.get_sensor_reading(db.internal_state.imu_prim_path)
                            if imu_reading.is_valid:
                                lin_acc_x = imu_reading.lin_acc_x
                                lin_acc_y = imu_reading.lin_acc_y
                                lin_acc_z = imu_reading.lin_acc_z

                # stream data
                if not (left is None) and not (right is None):
                    # Copy GPU image data to CPU and convert to bytes
                    left_bytes = left.numpy().tobytes()
                    right_bytes = right.numpy().tobytes()
                    res = db.internal_state.pyzed_streamer.stream(
                        left_bytes,
                        right_bytes,
                        ts,
                        orientation[0],
                        orientation[1],
                        orientation[2],
                        orientation[3],
                        lin_acc_x,
                        lin_acc_y,
                        lin_acc_z,
                    )
                    if not res == 0:
                        if db.internal_state.invalid_images_count >= 10:
                            carb.log_warn(f"{db.internal_state.camera_prim_name} - Streaming failed at timestamp {ts} with error code: {res}")
                        db.internal_state.invalid_images_count += 1
                    else:
                        carb.log_verbose(f"Streamed at {ts} 2 rgb images and orientation: {orientation} ")
                    db.internal_state.last_timestamp = current_time

        except Exception as error:
            # If anything causes your compute to fail report the error and return False
            db.log_error(str(error))
            return False

        # Even if inputs were edge cases like empty arrays, correct outputs mean success
        return True

    @staticmethod
    def release(db):
        carb.log_verbose("Releasing resources")
        print("release zsim streamer")
        try:
            state = db.per_instance_state
            if state is not None:
                # disabling this could fix the render product issue (return empty arrays) when the scene reloads
                # but could also create issues when attaching cameras to render products
                if state.annotator_left:
                    state.annotator_left.detach()
                    state.annotator_left = None
                    if state.render_product_path_left is not None:
                        #state.render_product_left.hydra_texture.set_updates_enabled(False)
                        state.render_product_path_left.detach()
                        state.render_product_path_left.destroy()
                if state.annotator_right:
                    state.annotator_right.detach()
                    state.annotator_right = None
                    if state.render_product_path_right is not None:
                        #state.render_product_right.hydra_texture.set_updates_enabled(False)
                        state.render_product_path_right.detach()
                        state.render_product_path_right.destroy()

                if state.pyzed_streamer:
                    print("close streamer")
                    state.pyzed_streamer.close()
                    # remove the streamer object when no longer needed
                    del state.pyzed_streamer

                _sensor.release_imu_sensor_interface(state.imu_sensor_interface)
                state.initialized = False
            
        except Exception:
            state = None
            pass