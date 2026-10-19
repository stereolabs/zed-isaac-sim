r"""Support for simplified access to data on nodes of type sl.sensor.camera.ZED_Camera_One

GENERATED CODE. DO NOT MODIFY.

Streams ZED mono camera data to the ZED SDK
"""

import sys
import traceback
import usdrt

import omni.graph.core as og
_og = og._omni_graph_core
import omni.graph.tools.ogn as ogn




class SlCameraOneStreamerDatabase(og.Database):
    """Helper class providing simplified access to data on nodes of type sl.sensor.camera.ZED_Camera_One

    Class Members:
        node: Node being evaluated

    Attribute Value Properties:
        Inputs:
            inputs.applyZedSim2Real
            inputs.autoExposure
            inputs.autoWhiteBalance
            inputs.bitrate
            inputs.cameraModel
            inputs.cameraSharpness
            inputs.chunkSize
            inputs.execIn
            inputs.fps
            inputs.leftCameraPrim
            inputs.lensType
            inputs.motionBlur
            inputs.resolution
            inputs.rightCameraPrim
            inputs.sensorNoise
            inputs.serialNumber
            inputs.streamDepth
            inputs.streamingPort
            inputs.transportLayerMode
            inputs.vignetting

    Predefined Tokens:
        tokens.ZED_XONE_UHD
        tokens.ZED_XONE_GS
        tokens.ZED_XONE_S
        tokens.Wide
        tokens.Narrow
        tokens.Fisheye
        tokens.HD4K
        tokens.QHDPLUS
        tokens.HD1200
        tokens.HD1080
        tokens.SVGA
        tokens.BOTH
        tokens.NETWORK
        tokens.IPC
    """

    # Imprint the generator and target ABI versions in the file for JIT generation
    GENERATOR_VERSION = (1, 81, 0)
    TARGET_VERSION = (3, 1, 2)

    # This is an internal object that provides per-class storage of a per-node data dictionary
    PER_NODE_DATA = {}

    # This is an internal object that describes unchanging attributes in a generic way
    # The values in this list are in no particular order, as a per-attribute tuple
    #     Name, Type, ExtendedTypeIndex, UiName, Description, Metadata,
    #     Is_Required, DefaultValue, Is_Deprecated, DeprecationMsg
    # You should not need to access any of this data directly, use the defined database interfaces
    INTERFACE = og.Database._get_interface([
        ('inputs:applyZedSim2Real', 'bool', 0, 'Apply ZED Sim2Real', "Apply the ZED X camera model: the camera's auto exposure and auto white balance, sensor noise, motion blur, lens vignetting and sharpness, each with its own switch below. Off streams the render as is (the scene's own camera exposure, plain sRGB). Can be toggled live.", {'uiGroup': 'ZED Sim2Real', ogn.MetadataKeys.DEFAULT: 'true'}, True, True, False, ''),
        ('inputs:autoExposure', 'bool', 0, 'Auto exposure', "Real-camera auto exposure: meters the rendered HDR image and drives the cameras' exposure time and gain (exposure:time / exposure:iso) like a real ZED X. Off keeps the scene's own camera exposure. Needs the sRGB stream. Can be toggled live. Needs Apply ZED Sim2Real.", {'uiGroup': 'ZED Sim2Real', ogn.MetadataKeys.DEFAULT: 'true'}, True, True, False, ''),
        ('inputs:autoWhiteBalance', 'bool', 0, 'Auto white balance', "Real-camera auto white balance: estimates the light's colour from the rendered image and balances it like a real ZED X, including its limits (warm lights such as tungsten keep part of their orange cast). Off streams the render's own colours. Needs the sRGB stream. Can be toggled live. Needs Apply ZED Sim2Real.", {'uiGroup': 'ZED Sim2Real', ogn.MetadataKeys.DEFAULT: 'true'}, True, True, False, ''),
        ('inputs:bitrate', 'uint', 0, 'Streaming Bitrate', 'Streaming bitrate (Kbps).', {'uiGroup': 'Streaming', ogn.MetadataKeys.DEFAULT: '8000'}, True, 8000, False, ''),
        ('inputs:cameraModel', 'token', 0, 'Camera Model', 'ZED Mono Camera model.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'ZED_XONE_UHD,ZED_XONE_GS,ZED_XONE_S', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["ZED_XONE_UHD", "ZED_XONE_GS", "ZED_XONE_S"]', ogn.MetadataKeys.DEFAULT: '"ZED_XONE_GS"'}, True, "ZED_XONE_GS", False, ''),
        ('inputs:cameraSharpness', 'bool', 0, 'Camera sharpness', "Sharpness of a real ZED X instead of the renderer's: the render is much crisper than the camera, which softens fine detail and sharpens edges with light halos. Needs the sRGB stream. Can be toggled live. Needs Apply ZED Sim2Real.", {'uiGroup': 'ZED Sim2Real', ogn.MetadataKeys.DEFAULT: 'true'}, True, True, False, ''),
        ('inputs:chunkSize', 'uint', 0, 'Streaming Chunk Size', 'Streaming chunk size (bytes).', {'uiGroup': 'Streaming', ogn.MetadataKeys.DEFAULT: '4096'}, True, 4096, False, ''),
        ('inputs:execIn', 'execution', 0, 'ExecIn', 'Triggers execution', {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:fps', 'uint', 0, 'FPS', 'Camera stream frame rate.', {'uiGroup': 'Configuration', ogn.MetadataKeys.DEFAULT: '30'}, True, 30, False, ''),
        ('inputs:leftCameraPrim', 'target', 0, 'Left Camera Prim', 'Main monocular camera', {ogn.MetadataKeys.LITERAL_ONLY: '1', ogn.MetadataKeys.ALLOW_MULTI_INPUTS: '0', 'uiGroup': 'Camera Selection'}, True, None, False, ''),
        ('inputs:lensType', 'token', 0, 'Lens Type', 'Lens fitted to the camera. Options shown depend on the selected camera model.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'Wide,Narrow,Fisheye', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["Wide", "Narrow", "Fisheye"]', ogn.MetadataKeys.DEFAULT: '"Wide"'}, True, "Wide", False, ''),
        ('inputs:motionBlur', 'bool', 0, 'Motion blur', "Motion blur over each frame's exposure time, as on a real ZED X: sharp in daylight (sub-millisecond exposures), smeared indoors and in the dark (up to the full frame time). Follows the auto exposure, or the camera's exposure:time when it is off, per camera and per frame. Needs the sRGB stream. Can be toggled live. Needs Apply ZED Sim2Real.", {'uiGroup': 'ZED Sim2Real', ogn.MetadataKeys.DEFAULT: 'true'}, True, True, False, ''),
        ('inputs:resolution', 'token', 0, 'Resolution', 'Camera stream resolution.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'HD4K,QHDPLUS,HD1200,HD1080,SVGA', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["HD4K", "QHDPLUS", "HD1200", "HD1080", "SVGA"]', ogn.MetadataKeys.DEFAULT: '"SVGA"'}, True, "SVGA", False, ''),
        ('inputs:rightCameraPrim', 'target', 0, 'Right Camera Prim (Optional)', '(optional) Used to create a virtual stereo camera from two ZED X Ones.', {ogn.MetadataKeys.LITERAL_ONLY: '1', ogn.MetadataKeys.ALLOW_MULTI_INPUTS: '0', 'uiGroup': 'Camera Selection'}, False, None, False, ''),
        ('inputs:sensorNoise', 'bool', 0, 'Sensor noise', "Sensor noise of a real ZED X, following the camera's gain (exposure:iso): nearly clean in daylight, visible grain in dim scenes, snow at maximum gain in the dark. Needs the sRGB stream. Can be toggled live. Needs Apply ZED Sim2Real.", {'uiGroup': 'ZED Sim2Real', ogn.MetadataKeys.DEFAULT: 'true'}, True, True, False, ''),
        ('inputs:serialNumber', 'string', 0, 'Serial Number', 'Serial number of the stereo cam. Only used for virtual ZED X cameras.', {'uiGroup': 'Configuration', ogn.MetadataKeys.DEFAULT: '"119999999"'}, True, "119999999", False, ''),
        ('inputs:streamDepth', 'bool', 0, 'Stream Depth', 'Enable Left+Depth streaming mode instead of Left+Right. Uses ground-truth depth from Isaac Sim.', {'uiGroup': 'Configuration', ogn.MetadataKeys.DEFAULT: 'false'}, True, False, False, ''),
        ('inputs:streamingPort', 'uint', 0, 'Streaming Port', 'Unique port per camera.', {'uiGroup': 'Streaming', ogn.MetadataKeys.DEFAULT: '30000'}, True, 30000, False, ''),
        ('inputs:transportLayerMode', 'token', 0, 'Transport layer mode', 'Communication protocol used to send data to the ZED SDK. IPC improves streaming performance when streaming to the same machine (Linux and Windows)', {ogn.MetadataKeys.ALLOWED_TOKENS: 'BOTH,NETWORK,IPC', 'uiGroup': 'Streaming', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["BOTH", "NETWORK", "IPC"]', ogn.MetadataKeys.DEFAULT: '"BOTH"'}, True, "BOTH", False, ''),
        ('inputs:vignetting', 'bool', 0, 'Vignetting', 'Lens vignetting of a real ZED X: the image darkens towards its edges. Scaled by field angle, so narrower lenses darken less; not applied to fisheye lenses. Needs the sRGB stream. Can be toggled live. Needs Apply ZED Sim2Real.', {'uiGroup': 'ZED Sim2Real', ogn.MetadataKeys.DEFAULT: 'true'}, True, True, False, ''),
    ])

    class tokens:
        ZED_XONE_UHD = "ZED_XONE_UHD"
        ZED_XONE_GS = "ZED_XONE_GS"
        ZED_XONE_S = "ZED_XONE_S"
        Wide = "Wide"
        Narrow = "Narrow"
        Fisheye = "Fisheye"
        HD4K = "HD4K"
        QHDPLUS = "QHDPLUS"
        HD1200 = "HD1200"
        HD1080 = "HD1080"
        SVGA = "SVGA"
        BOTH = "BOTH"
        NETWORK = "NETWORK"
        IPC = "IPC"

    @classmethod
    def _populate_role_data(cls):
        """Populate a role structure with the non-default roles on this node type"""
        role_data = super()._populate_role_data()
        role_data.inputs.execIn = og.AttributeRole.EXECUTION
        role_data.inputs.leftCameraPrim = og.AttributeRole.TARGET
        role_data.inputs.rightCameraPrim = og.AttributeRole.TARGET
        role_data.inputs.serialNumber = og.AttributeRole.TEXT
        return role_data

    class ValuesForInputs(og.DynamicAttributeAccess):
        LOCAL_PROPERTY_NAMES = {"applyZedSim2Real", "autoExposure", "autoWhiteBalance", "bitrate", "cameraModel", "cameraSharpness", "chunkSize", "execIn", "fps", "lensType", "motionBlur", "resolution", "sensorNoise", "serialNumber", "streamDepth", "streamingPort", "transportLayerMode", "vignetting", "_setting_locked", "_batchedReadAttributes", "_batchedReadValues"}
        """Helper class that creates natural hierarchical access to input attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)
            self._batchedReadAttributes = [self._attributes.applyZedSim2Real, self._attributes.autoExposure, self._attributes.autoWhiteBalance, self._attributes.bitrate, self._attributes.cameraModel, self._attributes.cameraSharpness, self._attributes.chunkSize, self._attributes.execIn, self._attributes.fps, self._attributes.lensType, self._attributes.motionBlur, self._attributes.resolution, self._attributes.sensorNoise, self._attributes.serialNumber, self._attributes.streamDepth, self._attributes.streamingPort, self._attributes.transportLayerMode, self._attributes.vignetting]
            self._batchedReadValues = [True, True, True, 8000, "ZED_XONE_GS", True, 4096, 0, 30, "Wide", True, "SVGA", True, "119999999", False, 30000, "BOTH", True]

        @property
        def leftCameraPrim(self):
            data_view = og.AttributeValueHelper(self._attributes.leftCameraPrim)
            return data_view.get()

        @leftCameraPrim.setter
        def leftCameraPrim(self, value):
            if self._setting_locked:
                raise og.ReadOnlyError(self._attributes.leftCameraPrim)
            data_view = og.AttributeValueHelper(self._attributes.leftCameraPrim)
            data_view.set(value)
            self.leftCameraPrim_size = data_view.get_array_size()

        @property
        def rightCameraPrim(self):
            data_view = og.AttributeValueHelper(self._attributes.rightCameraPrim)
            return data_view.get()

        @rightCameraPrim.setter
        def rightCameraPrim(self, value):
            if self._setting_locked:
                raise og.ReadOnlyError(self._attributes.rightCameraPrim)
            data_view = og.AttributeValueHelper(self._attributes.rightCameraPrim)
            data_view.set(value)
            self.rightCameraPrim_size = data_view.get_array_size()

        @property
        def applyZedSim2Real(self):
            return self._batchedReadValues[0]

        @applyZedSim2Real.setter
        def applyZedSim2Real(self, value):
            self._batchedReadValues[0] = value

        @property
        def autoExposure(self):
            return self._batchedReadValues[1]

        @autoExposure.setter
        def autoExposure(self, value):
            self._batchedReadValues[1] = value

        @property
        def autoWhiteBalance(self):
            return self._batchedReadValues[2]

        @autoWhiteBalance.setter
        def autoWhiteBalance(self, value):
            self._batchedReadValues[2] = value

        @property
        def bitrate(self):
            return self._batchedReadValues[3]

        @bitrate.setter
        def bitrate(self, value):
            self._batchedReadValues[3] = value

        @property
        def cameraModel(self):
            return self._batchedReadValues[4]

        @cameraModel.setter
        def cameraModel(self, value):
            self._batchedReadValues[4] = value

        @property
        def cameraSharpness(self):
            return self._batchedReadValues[5]

        @cameraSharpness.setter
        def cameraSharpness(self, value):
            self._batchedReadValues[5] = value

        @property
        def chunkSize(self):
            return self._batchedReadValues[6]

        @chunkSize.setter
        def chunkSize(self, value):
            self._batchedReadValues[6] = value

        @property
        def execIn(self):
            return self._batchedReadValues[7]

        @execIn.setter
        def execIn(self, value):
            self._batchedReadValues[7] = value

        @property
        def fps(self):
            return self._batchedReadValues[8]

        @fps.setter
        def fps(self, value):
            self._batchedReadValues[8] = value

        @property
        def lensType(self):
            return self._batchedReadValues[9]

        @lensType.setter
        def lensType(self, value):
            self._batchedReadValues[9] = value

        @property
        def motionBlur(self):
            return self._batchedReadValues[10]

        @motionBlur.setter
        def motionBlur(self, value):
            self._batchedReadValues[10] = value

        @property
        def resolution(self):
            return self._batchedReadValues[11]

        @resolution.setter
        def resolution(self, value):
            self._batchedReadValues[11] = value

        @property
        def sensorNoise(self):
            return self._batchedReadValues[12]

        @sensorNoise.setter
        def sensorNoise(self, value):
            self._batchedReadValues[12] = value

        @property
        def serialNumber(self):
            return self._batchedReadValues[13]

        @serialNumber.setter
        def serialNumber(self, value):
            self._batchedReadValues[13] = value

        @property
        def streamDepth(self):
            return self._batchedReadValues[14]

        @streamDepth.setter
        def streamDepth(self, value):
            self._batchedReadValues[14] = value

        @property
        def streamingPort(self):
            return self._batchedReadValues[15]

        @streamingPort.setter
        def streamingPort(self, value):
            self._batchedReadValues[15] = value

        @property
        def transportLayerMode(self):
            return self._batchedReadValues[16]

        @transportLayerMode.setter
        def transportLayerMode(self, value):
            self._batchedReadValues[16] = value

        @property
        def vignetting(self):
            return self._batchedReadValues[17]

        @vignetting.setter
        def vignetting(self, value):
            self._batchedReadValues[17] = value

        def __getattr__(self, item: str):
            if item in self.LOCAL_PROPERTY_NAMES:
                return object.__getattribute__(self, item)
            else:
                return super().__getattr__(item)

        def __setattr__(self, item: str, new_value):
            if item in self.LOCAL_PROPERTY_NAMES:
                object.__setattr__(self, item, new_value)
            else:
                super().__setattr__(item, new_value)

        def _prefetch(self):
            readAttributes = self._batchedReadAttributes
            newValues = _og._prefetch_input_attributes_data(readAttributes)
            if len(readAttributes) == len(newValues):
                self._batchedReadValues = newValues

    class ValuesForOutputs(og.DynamicAttributeAccess):
        LOCAL_PROPERTY_NAMES = { }
        """Helper class that creates natural hierarchical access to output attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)
            self._batchedWriteValues = { }

        def _commit(self):
            _og._commit_output_attributes_data(self._batchedWriteValues)
            self._batchedWriteValues = { }

    class ValuesForState(og.DynamicAttributeAccess):
        """Helper class that creates natural hierarchical access to state attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)

    def __init__(self, node):
        super().__init__(node)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_INPUT)
        self.inputs = SlCameraOneStreamerDatabase.ValuesForInputs(node, self.attributes.inputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_OUTPUT)
        self.outputs = SlCameraOneStreamerDatabase.ValuesForOutputs(node, self.attributes.outputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_STATE)
        self.state = SlCameraOneStreamerDatabase.ValuesForState(node, self.attributes.state, dynamic_attributes)

    class abi:
        """Class defining the ABI interface for the node type"""

        @staticmethod
        def get_node_type():
            get_node_type_function = getattr(SlCameraOneStreamerDatabase.NODE_TYPE_CLASS, 'get_node_type', None)
            if callable(get_node_type_function):  # pragma: no cover
                return get_node_type_function()
            return 'sl.sensor.camera.ZED_Camera_One'

        @staticmethod
        def compute(context, node):
            def database_valid():
                return True
            try:
                per_node_data = SlCameraOneStreamerDatabase.PER_NODE_DATA[node.node_id()]
                db = per_node_data.get('_db')
                if db is None:
                    db = SlCameraOneStreamerDatabase(node)
                    per_node_data['_db'] = db
                if not database_valid():
                    per_node_data['_db'] = None
                    return False
            except:
                db = SlCameraOneStreamerDatabase(node)

            try:
                compute_function = getattr(SlCameraOneStreamerDatabase.NODE_TYPE_CLASS, 'compute', None)
                if callable(compute_function) and compute_function.__code__.co_argcount > 1:  # pragma: no cover
                    return compute_function(context, node)

                db.inputs._prefetch()
                db.inputs._setting_locked = True
                with og.in_compute():
                    return SlCameraOneStreamerDatabase.NODE_TYPE_CLASS.compute(db)
            except Exception as error:  # pragma: no cover
                stack_trace = "".join(traceback.format_tb(sys.exc_info()[2].tb_next))
                db.log_error(f'Assertion raised in compute - {error}\n{stack_trace}', add_context=False)
            finally:
                db.inputs._setting_locked = False
                db.outputs._commit()
            return False

        @staticmethod
        def initialize(context, node):
            SlCameraOneStreamerDatabase._initialize_per_node_data(node)
            initialize_function = getattr(SlCameraOneStreamerDatabase.NODE_TYPE_CLASS, 'initialize', None)
            if callable(initialize_function):  # pragma: no cover
                initialize_function(context, node)

            per_node_data = SlCameraOneStreamerDatabase.PER_NODE_DATA[node.node_id()]

            def on_connection_or_disconnection(*args):
                per_node_data['_db'] = None

            node.register_on_connected_callback(on_connection_or_disconnection)
            node.register_on_disconnected_callback(on_connection_or_disconnection)

        @staticmethod
        def initialize_nodes(context, nodes):
            for n in nodes:
                SlCameraOneStreamerDatabase.abi.initialize(context, n)

        @staticmethod
        def release(node):
            release_function = getattr(SlCameraOneStreamerDatabase.NODE_TYPE_CLASS, 'release', None)
            if callable(release_function):  # pragma: no cover
                release_function(node)
            SlCameraOneStreamerDatabase._release_per_node_data(node)

        @staticmethod
        def init_instance(node, graph_instance_id):
            init_instance_function = getattr(SlCameraOneStreamerDatabase.NODE_TYPE_CLASS, 'init_instance', None)
            if callable(init_instance_function):  # pragma: no cover
                init_instance_function(node, graph_instance_id)

        @staticmethod
        def release_instance(node, graph_instance_id):
            release_instance_function = getattr(SlCameraOneStreamerDatabase.NODE_TYPE_CLASS, 'release_instance', None)
            if callable(release_instance_function):  # pragma: no cover
                release_instance_function(node, graph_instance_id)
            SlCameraOneStreamerDatabase._release_per_node_instance_data(node, graph_instance_id)

        @staticmethod
        def update_node_version(context, node, old_version, new_version):
            update_node_version_function = getattr(SlCameraOneStreamerDatabase.NODE_TYPE_CLASS, 'update_node_version', None)
            if callable(update_node_version_function):  # pragma: no cover
                return update_node_version_function(context, node, old_version, new_version)
            return False

        @staticmethod
        def initialize_type(node_type):
            initialize_type_function = getattr(SlCameraOneStreamerDatabase.NODE_TYPE_CLASS, 'initialize_type', None)
            needs_initializing = True
            if callable(initialize_type_function):  # pragma: no cover
                needs_initializing = initialize_type_function(node_type)
            if needs_initializing:
                node_type.set_metadata(ogn.MetadataKeys.EXTENSION, "sl.sensor.camera")
                node_type.set_metadata(ogn.MetadataKeys.UI_NAME, "ZED Camera One Helper")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORIES, "Stereolabs")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORY_DESCRIPTIONS, "Stereolabs,Nodes used with the Stereolabs ZED SDK")
                node_type.set_metadata(ogn.MetadataKeys.DESCRIPTION, "Streams ZED mono camera data to the ZED SDK")
                node_type.set_metadata(ogn.MetadataKeys.LANGUAGE, "Python")
                SlCameraOneStreamerDatabase.INTERFACE.add_to_node_type(node_type)

        @staticmethod
        def on_connection_type_resolve(node):
            on_connection_type_resolve_function = getattr(SlCameraOneStreamerDatabase.NODE_TYPE_CLASS, 'on_connection_type_resolve', None)
            if callable(on_connection_type_resolve_function):  # pragma: no cover
                on_connection_type_resolve_function(node)

    NODE_TYPE_CLASS = None

    @staticmethod
    def register(node_type_class):
        SlCameraOneStreamerDatabase.NODE_TYPE_CLASS = node_type_class
        og.register_node_type(SlCameraOneStreamerDatabase.abi, 5)

    @staticmethod
    def deregister():
        og.deregister_node_type("sl.sensor.camera.ZED_Camera_One")
