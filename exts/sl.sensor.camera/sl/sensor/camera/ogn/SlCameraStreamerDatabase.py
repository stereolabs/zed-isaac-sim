r"""Support for simplified access to data on nodes of type sl.sensor.camera.ZED_Camera

GENERATED CODE. DO NOT MODIFY.

Streams ZED camera data to the ZED SDK
"""

import sys
import traceback
import usdrt

import omni.graph.core as og
_og = og._omni_graph_core
import omni.graph.tools.ogn as ogn




class SlCameraStreamerDatabase(og.Database):
    """Helper class providing simplified access to data on nodes of type sl.sensor.camera.ZED_Camera

    Class Members:
        node: Node being evaluated

    Attribute Value Properties:
        Inputs:
            inputs.applyZedSim2Real
            inputs.bitrate
            inputs.cameraModel
            inputs.cameraPrim
            inputs.chunkSize
            inputs.execIn
            inputs.fps
            inputs.lensType
            inputs.resolution
            inputs.streamDepth
            inputs.streamingPort
            inputs.transportLayerMode
            inputs.zedSim2RealAeTarget
            inputs.zedSim2RealSceneLux

    Predefined Tokens:
        tokens.ZED_X
        tokens.ZED_XM
        tokens.ZED_X_Nano
        tokens.ZED_M
        tokens.ZED_2i
        tokens.Wide
        tokens.Narrow
        tokens.HD2K
        tokens.HD1200
        tokens.HD1080
        tokens.HD720
        tokens.SVGA
        tokens.VGA
        tokens.BOTH
        tokens.NETWORK
        tokens.IPC
    """

    # Imprint the generator and target ABI versions in the file for JIT generation
    GENERATOR_VERSION = (1, 81, 0)
    TARGET_VERSION = (0, 0, 0)

    # This is an internal object that provides per-class storage of a per-node data dictionary
    PER_NODE_DATA = {}

    # This is an internal object that describes unchanging attributes in a generic way
    # The values in this list are in no particular order, as a per-attribute tuple
    #     Name, Type, ExtendedTypeIndex, UiName, Description, Metadata,
    #     Is_Required, DefaultValue, Is_Deprecated, DeprecationMsg
    # You should not need to access any of this data directly, use the defined database interfaces
    INTERFACE = og.Database._get_interface([
        ('inputs:applyZedSim2Real', 'bool', 0, 'Apply', 'Post-process the streamed frames with the calibrated ZED Sim2Real camera model\nso the simulated image matches a real ZED X.\n\nModels: lens blur (MTF), vignetting, auto-exposure, white balance,\ntone curve, sharpening and gain-coupled sensor noise.\n\nCan be toggled live while playing.', {'uiGroup': 'ZED Sim2Real', ogn.MetadataKeys.DEFAULT: 'false'}, True, False, False, ''),
        ('inputs:bitrate', 'uint', 0, 'Streaming Bitrate', 'Bitrate in Kbps. (Used only if IPC is disabled)', {'uiGroup': 'Streaming', ogn.MetadataKeys.DEFAULT: '8000'}, True, 8000, False, ''),
        ('inputs:cameraModel', 'token', 0, 'Camera Model', 'ZED Camera model.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'ZED_X,ZED_XM,ZED_X_Nano,ZED_M,ZED_2i', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["ZED_X", "ZED_XM", "ZED_X_Nano", "ZED_M", "ZED_2i"]', ogn.MetadataKeys.DEFAULT: '"ZED_X"'}, True, "ZED_X", False, ''),
        ('inputs:cameraPrim', 'target', 0, 'ZED Camera Prim', 'ZED Camera prim used to stream data.', {ogn.MetadataKeys.LITERAL_ONLY: '1', ogn.MetadataKeys.ALLOW_MULTI_INPUTS: '0', 'uiGroup': 'Camera Selection'}, True, None, False, ''),
        ('inputs:chunkSize', 'uint', 0, 'Streaming Chunk Size', 'Chunk size in bytes. (Used only if IPC is disabled)', {'uiGroup': 'Streaming', ogn.MetadataKeys.DEFAULT: '4096'}, True, 4096, False, ''),
        ('inputs:execIn', 'execution', 0, 'ExecIn', 'Triggers execution', {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:fps', 'uint', 0, 'FPS', 'Camera stream frame rate.', {'uiGroup': 'Configuration', ogn.MetadataKeys.DEFAULT: '30'}, True, 30, False, ''),
        ('inputs:lensType', 'token', 0, 'Lens Type', 'Lens fitted to the camera. Options shown depend on the selected camera model.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'Wide,Narrow', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["Wide", "Narrow"]', ogn.MetadataKeys.DEFAULT: '"Wide"'}, True, "Wide", False, ''),
        ('inputs:resolution', 'token', 0, 'Resolution', 'Camera stream resolution.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'HD2K,HD1200,HD1080,HD720,SVGA,VGA', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["HD2K", "HD1200", "HD1080", "HD720", "SVGA", "VGA"]', ogn.MetadataKeys.DEFAULT: '"SVGA"'}, True, "SVGA", False, ''),
        ('inputs:streamDepth', 'bool', 0, 'Stream Depth', 'Enable Left+Depth streaming mode instead of Left+Right. Uses ground-truth depth from Isaac Sim.', {'uiGroup': 'Streaming', ogn.MetadataKeys.DEFAULT: 'false'}, True, False, False, ''),
        ('inputs:streamingPort', 'uint', 0, 'Streaming Port', 'Unique port per camera.', {'uiGroup': 'Streaming', ogn.MetadataKeys.DEFAULT: '30000'}, True, 30000, False, ''),
        ('inputs:transportLayerMode', 'token', 0, 'Transport layer mode', 'Communication protocol used to send data to the ZED SDK. IPC improves streaming performance when streaming to the same machine (Linux and Windows)', {ogn.MetadataKeys.ALLOWED_TOKENS: 'BOTH,NETWORK,IPC', 'uiGroup': 'Streaming', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["BOTH", "NETWORK", "IPC"]', ogn.MetadataKeys.DEFAULT: '"BOTH"'}, True, "BOTH", False, ''),
        ('inputs:zedSim2RealAeTarget', 'float', 0, 'ZED Sim2Real AE target', 'Override the ZED Sim2Real AE set-point (median display luma 0..1). <=0 = calibrated default (~0.45). Raise to brighten the modeled image.', {ogn.MetadataKeys.DEFAULT: '-1.0'}, True, -1.0, False, ''),
        ('inputs:zedSim2RealSceneLux', 'float', 0, 'Scene Lux', 'Assumed scene illuminance (lux) for low-light modeling.\nOnly used when Apply is on; tunable live while playing.\n\n0 or less = bright scene: no extra darkening or added noise.\nA positive value simulates a dimmer scene: the lower the lux,\nthe darker and noisier the image (gain-coupled sensor noise),\nmatching how a real ZED gains up in low light.', {'uiGroup': 'ZED Sim2Real', ogn.MetadataKeys.DEFAULT: '0.0'}, True, 0.0, False, ''),
    ])

    class tokens:
        ZED_X = "ZED_X"
        ZED_XM = "ZED_XM"
        ZED_X_Nano = "ZED_X_Nano"
        ZED_M = "ZED_M"
        ZED_2i = "ZED_2i"
        Wide = "Wide"
        Narrow = "Narrow"
        HD2K = "HD2K"
        HD1200 = "HD1200"
        HD1080 = "HD1080"
        HD720 = "HD720"
        SVGA = "SVGA"
        VGA = "VGA"
        BOTH = "BOTH"
        NETWORK = "NETWORK"
        IPC = "IPC"

    @classmethod
    def _populate_role_data(cls):
        """Populate a role structure with the non-default roles on this node type"""
        role_data = super()._populate_role_data()
        role_data.inputs.cameraPrim = og.AttributeRole.TARGET
        role_data.inputs.execIn = og.AttributeRole.EXECUTION
        return role_data

    class ValuesForInputs(og.DynamicAttributeAccess):
        LOCAL_PROPERTY_NAMES = {"applyZedSim2Real", "bitrate", "cameraModel", "chunkSize", "execIn", "fps", "lensType", "resolution", "streamDepth", "streamingPort", "transportLayerMode", "zedSim2RealAeTarget", "zedSim2RealSceneLux", "_setting_locked", "_batchedReadAttributes", "_batchedReadValues"}
        """Helper class that creates natural hierarchical access to input attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)
            self._batchedReadAttributes = [self._attributes.applyZedSim2Real, self._attributes.bitrate, self._attributes.cameraModel, self._attributes.chunkSize, self._attributes.execIn, self._attributes.fps, self._attributes.lensType, self._attributes.resolution, self._attributes.streamDepth, self._attributes.streamingPort, self._attributes.transportLayerMode, self._attributes.zedSim2RealAeTarget, self._attributes.zedSim2RealSceneLux]
            self._batchedReadValues = [False, 8000, "ZED_X", 4096, 0, 30, "Wide", "SVGA", False, 30000, "BOTH", -1.0, 0.0]

        @property
        def cameraPrim(self):
            data_view = og.AttributeValueHelper(self._attributes.cameraPrim)
            return data_view.get()

        @cameraPrim.setter
        def cameraPrim(self, value):
            if self._setting_locked:
                raise og.ReadOnlyError(self._attributes.cameraPrim)
            data_view = og.AttributeValueHelper(self._attributes.cameraPrim)
            data_view.set(value)
            self.cameraPrim_size = data_view.get_array_size()

        @property
        def applyZedSim2Real(self):
            return self._batchedReadValues[0]

        @applyZedSim2Real.setter
        def applyZedSim2Real(self, value):
            self._batchedReadValues[0] = value

        @property
        def bitrate(self):
            return self._batchedReadValues[1]

        @bitrate.setter
        def bitrate(self, value):
            self._batchedReadValues[1] = value

        @property
        def cameraModel(self):
            return self._batchedReadValues[2]

        @cameraModel.setter
        def cameraModel(self, value):
            self._batchedReadValues[2] = value

        @property
        def chunkSize(self):
            return self._batchedReadValues[3]

        @chunkSize.setter
        def chunkSize(self, value):
            self._batchedReadValues[3] = value

        @property
        def execIn(self):
            return self._batchedReadValues[4]

        @execIn.setter
        def execIn(self, value):
            self._batchedReadValues[4] = value

        @property
        def fps(self):
            return self._batchedReadValues[5]

        @fps.setter
        def fps(self, value):
            self._batchedReadValues[5] = value

        @property
        def lensType(self):
            return self._batchedReadValues[6]

        @lensType.setter
        def lensType(self, value):
            self._batchedReadValues[6] = value

        @property
        def resolution(self):
            return self._batchedReadValues[7]

        @resolution.setter
        def resolution(self, value):
            self._batchedReadValues[7] = value

        @property
        def streamDepth(self):
            return self._batchedReadValues[8]

        @streamDepth.setter
        def streamDepth(self, value):
            self._batchedReadValues[8] = value

        @property
        def streamingPort(self):
            return self._batchedReadValues[9]

        @streamingPort.setter
        def streamingPort(self, value):
            self._batchedReadValues[9] = value

        @property
        def transportLayerMode(self):
            return self._batchedReadValues[10]

        @transportLayerMode.setter
        def transportLayerMode(self, value):
            self._batchedReadValues[10] = value

        @property
        def zedSim2RealAeTarget(self):
            return self._batchedReadValues[11]

        @zedSim2RealAeTarget.setter
        def zedSim2RealAeTarget(self, value):
            self._batchedReadValues[11] = value

        @property
        def zedSim2RealSceneLux(self):
            return self._batchedReadValues[12]

        @zedSim2RealSceneLux.setter
        def zedSim2RealSceneLux(self, value):
            self._batchedReadValues[12] = value

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
        self.inputs = SlCameraStreamerDatabase.ValuesForInputs(node, self.attributes.inputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_OUTPUT)
        self.outputs = SlCameraStreamerDatabase.ValuesForOutputs(node, self.attributes.outputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_STATE)
        self.state = SlCameraStreamerDatabase.ValuesForState(node, self.attributes.state, dynamic_attributes)

    class abi:
        """Class defining the ABI interface for the node type"""

        @staticmethod
        def get_node_type():
            get_node_type_function = getattr(SlCameraStreamerDatabase.NODE_TYPE_CLASS, 'get_node_type', None)
            if callable(get_node_type_function):  # pragma: no cover
                return get_node_type_function()
            return 'sl.sensor.camera.ZED_Camera'

        @staticmethod
        def compute(context, node):
            def database_valid():
                return True
            try:
                per_node_data = SlCameraStreamerDatabase.PER_NODE_DATA[node.node_id()]
                db = per_node_data.get('_db')
                if db is None:
                    db = SlCameraStreamerDatabase(node)
                    per_node_data['_db'] = db
                if not database_valid():
                    per_node_data['_db'] = None
                    return False
            except:
                db = SlCameraStreamerDatabase(node)

            try:
                compute_function = getattr(SlCameraStreamerDatabase.NODE_TYPE_CLASS, 'compute', None)
                if callable(compute_function) and compute_function.__code__.co_argcount > 1:  # pragma: no cover
                    return compute_function(context, node)

                db.inputs._prefetch()
                db.inputs._setting_locked = True
                with og.in_compute():
                    return SlCameraStreamerDatabase.NODE_TYPE_CLASS.compute(db)
            except Exception as error:  # pragma: no cover
                stack_trace = "".join(traceback.format_tb(sys.exc_info()[2].tb_next))
                db.log_error(f'Assertion raised in compute - {error}\n{stack_trace}', add_context=False)
            finally:
                db.inputs._setting_locked = False
                db.outputs._commit()
            return False

        @staticmethod
        def initialize(context, node):
            SlCameraStreamerDatabase._initialize_per_node_data(node)
            initialize_function = getattr(SlCameraStreamerDatabase.NODE_TYPE_CLASS, 'initialize', None)
            if callable(initialize_function):  # pragma: no cover
                initialize_function(context, node)

            per_node_data = SlCameraStreamerDatabase.PER_NODE_DATA[node.node_id()]

            def on_connection_or_disconnection(*args):
                per_node_data['_db'] = None

            node.register_on_connected_callback(on_connection_or_disconnection)
            node.register_on_disconnected_callback(on_connection_or_disconnection)

        @staticmethod
        def initialize_nodes(context, nodes):
            for n in nodes:
                SlCameraStreamerDatabase.abi.initialize(context, n)

        @staticmethod
        def release(node):
            release_function = getattr(SlCameraStreamerDatabase.NODE_TYPE_CLASS, 'release', None)
            if callable(release_function):  # pragma: no cover
                release_function(node)
            SlCameraStreamerDatabase._release_per_node_data(node)

        @staticmethod
        def init_instance(node, graph_instance_id):
            init_instance_function = getattr(SlCameraStreamerDatabase.NODE_TYPE_CLASS, 'init_instance', None)
            if callable(init_instance_function):  # pragma: no cover
                init_instance_function(node, graph_instance_id)

        @staticmethod
        def release_instance(node, graph_instance_id):
            release_instance_function = getattr(SlCameraStreamerDatabase.NODE_TYPE_CLASS, 'release_instance', None)
            if callable(release_instance_function):  # pragma: no cover
                release_instance_function(node, graph_instance_id)
            SlCameraStreamerDatabase._release_per_node_instance_data(node, graph_instance_id)

        @staticmethod
        def update_node_version(context, node, old_version, new_version):
            update_node_version_function = getattr(SlCameraStreamerDatabase.NODE_TYPE_CLASS, 'update_node_version', None)
            if callable(update_node_version_function):  # pragma: no cover
                return update_node_version_function(context, node, old_version, new_version)
            return False

        @staticmethod
        def initialize_type(node_type):
            initialize_type_function = getattr(SlCameraStreamerDatabase.NODE_TYPE_CLASS, 'initialize_type', None)
            needs_initializing = True
            if callable(initialize_type_function):  # pragma: no cover
                needs_initializing = initialize_type_function(node_type)
            if needs_initializing:
                node_type.set_metadata(ogn.MetadataKeys.EXTENSION, "sl.sensor.camera")
                node_type.set_metadata(ogn.MetadataKeys.UI_NAME, "ZED Camera Helper")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORIES, "Stereolabs")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORY_DESCRIPTIONS, "Stereolabs,Nodes used with the Stereolabs ZED SDK")
                node_type.set_metadata(ogn.MetadataKeys.DESCRIPTION, "Streams ZED camera data to the ZED SDK")
                node_type.set_metadata(ogn.MetadataKeys.LANGUAGE, "Python")
                SlCameraStreamerDatabase.INTERFACE.add_to_node_type(node_type)

        @staticmethod
        def on_connection_type_resolve(node):
            on_connection_type_resolve_function = getattr(SlCameraStreamerDatabase.NODE_TYPE_CLASS, 'on_connection_type_resolve', None)
            if callable(on_connection_type_resolve_function):  # pragma: no cover
                on_connection_type_resolve_function(node)

    NODE_TYPE_CLASS = None

    @staticmethod
    def register(node_type_class):
        SlCameraStreamerDatabase.NODE_TYPE_CLASS = node_type_class
        og.register_node_type(SlCameraStreamerDatabase.abi, 4)

    @staticmethod
    def deregister():
        og.deregister_node_type("sl.sensor.camera.ZED_Camera")
