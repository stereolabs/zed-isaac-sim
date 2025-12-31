r"""Support for simplified access to data on nodes of type sl.sensor.camera.ZED_Camera_One

 __   ___ .  .  ___  __       ___  ___  __      __   __   __   ___
/ _` |__  |\ | |__  |__)  /\   |  |__  |  \    /  ` /  \ |  \ |__
\__| |___ | \| |___ |  \ /--\  |  |___ |__/    \__, \__/ |__/ |___

 __   __     .  .  __  ___     .  .  __   __     ___
|  \ /  \    |\ | /  \  |      |\/| /  \ |  \ | |__  \ /
|__/ \__/    | \| \__/  |      |  | \__/ |__/ | |     |

Streams ZED mono camera data to the ZED SDK
"""

import sys
import traceback
import usdrt

import omni.graph.core as og
import omni.graph.core._omni_graph_core as _og
import omni.graph.tools.ogn as ogn



class SlCameraOneStreamerDatabase(og.Database):
    """Helper class providing simplified access to data on nodes of type sl.sensor.camera.ZED_Camera_One

    Class Members:
        node: Node being evaluated

    Attribute Value Properties:
        Inputs:
            inputs.bitrate
            inputs.cameraModel
            inputs.chunkSize
            inputs.execIn
            inputs.fps
            inputs.leftCameraPrim
            inputs.resolution
            inputs.rightCameraPrim
            inputs.serialNumber
            inputs.streamingPort
            inputs.transportLayerMode

    Predefined Tokens:
        tokens.ZED_XONE_UHD
        tokens.ZED_XONE_GS
        tokens.ZED_XONE_GS_4MM
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
    GENERATOR_VERSION = (1, 79, 2)
    TARGET_VERSION = (0, 0, 0)

    # This is an internal object that provides per-class storage of a per-node data dictionary
    PER_NODE_DATA = {}

    # This is an internal object that describes unchanging attributes in a generic way
    # The values in this list are in no particular order, as a per-attribute tuple
    #     Name, Type, ExtendedTypeIndex, UiName, Description, Metadata,
    #     Is_Required, DefaultValue, Is_Deprecated, DeprecationMsg
    # You should not need to access any of this data directly, use the defined database interfaces
    INTERFACE = og.Database._get_interface([
        ('inputs:bitrate', 'uint', 0, 'Bitrate', 'Streaming bitrate (Kbps).', {'uiGroup': 'Streaming', ogn.MetadataKeys.DEFAULT: '8000'}, True, 8000, False, ''),
        ('inputs:cameraModel', 'token', 0, 'Camera Model', 'ZED Mono Camera model.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'ZED_XONE_UHD,ZED_XONE_GS,ZED_XONE_GS_4MM', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["ZED_XONE_UHD", "ZED_XONE_GS", "ZED_XONE_GS_4MM"]', ogn.MetadataKeys.DEFAULT: '"ZED_XONE_GS"'}, True, "ZED_XONE_GS", False, ''),
        ('inputs:chunkSize', 'uint', 0, 'Chunk Size', 'Streaming chunk size (bytes).', {'uiGroup': 'Streaming', ogn.MetadataKeys.DEFAULT: '4096'}, True, 4096, False, ''),
        ('inputs:execIn', 'execution', 0, 'ExecIn', 'Triggers execution', {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:fps', 'uint', 0, 'FPS', 'Camera stream frame rate.', {'uiGroup': 'Configuration', ogn.MetadataKeys.DEFAULT: '30'}, True, 30, False, ''),
        ('inputs:leftCameraPrim', 'target', 0, 'Left Camera Prim', 'Main monocular camera', {ogn.MetadataKeys.LITERAL_ONLY: '1', ogn.MetadataKeys.ALLOW_MULTI_INPUTS: '0', 'uiGroup': 'Camera Selection'}, True, None, False, ''),
        ('inputs:resolution', 'token', 0, 'Resolution', 'Camera stream resolution.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'HD4K,QHDPLUS,HD1200,HD1080,SVGA', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["HD4K", "QHDPLUS", "HD1200", "HD1080", "SVGA"]', ogn.MetadataKeys.DEFAULT: '"HD1200"'}, True, "HD1200", False, ''),
        ('inputs:rightCameraPrim', 'target', 0, 'Right Camera Prim (Optional)', '(optional) Used to create a virtual stereo camera from two ZED X Ones.', {ogn.MetadataKeys.LITERAL_ONLY: '1', ogn.MetadataKeys.ALLOW_MULTI_INPUTS: '0', 'uiGroup': 'Camera Selection'}, False, None, False, ''),
        ('inputs:serialNumber', 'string', 0, 'Serial Number', 'Serial number of the stereo cam. Only used for virtual ZED X cameras.', {'uiGroup': 'Configuration', ogn.MetadataKeys.DEFAULT: '"119999999"'}, True, "119999999", False, ''),
        ('inputs:streamingPort', 'uint', 0, 'Streaming Port', 'Unique port per camera.', {'uiGroup': 'Streaming', ogn.MetadataKeys.DEFAULT: '30000'}, True, 30000, False, ''),
        ('inputs:transportLayerMode', 'token', 0, 'Transport layer mode', 'Communication protocol used to send data to the ZED SDK. IPC (Only available on Linux)improves streaming performances when streaming to the same machine', {ogn.MetadataKeys.ALLOWED_TOKENS: 'BOTH,NETWORK,IPC', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["BOTH", "NETWORK", "IPC"]', ogn.MetadataKeys.DEFAULT: '"BOTH"'}, True, "BOTH", False, ''),
    ])

    class tokens:
        ZED_XONE_UHD = "ZED_XONE_UHD"
        ZED_XONE_GS = "ZED_XONE_GS"
        ZED_XONE_GS_4MM = "ZED_XONE_GS_4MM"
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
        LOCAL_PROPERTY_NAMES = {"bitrate", "cameraModel", "chunkSize", "execIn", "fps", "resolution", "serialNumber", "streamingPort", "transportLayerMode", "_setting_locked", "_batchedReadAttributes", "_batchedReadValues"}
        """Helper class that creates natural hierarchical access to input attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)
            self._batchedReadAttributes = [self._attributes.bitrate, self._attributes.cameraModel, self._attributes.chunkSize, self._attributes.execIn, self._attributes.fps, self._attributes.resolution, self._attributes.serialNumber, self._attributes.streamingPort, self._attributes.transportLayerMode]
            self._batchedReadValues = [8000, "ZED_XONE_GS", 4096, 0, 30, "HD1200", "119999999", 30000, "BOTH"]

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
        def bitrate(self):
            return self._batchedReadValues[0]

        @bitrate.setter
        def bitrate(self, value):
            self._batchedReadValues[0] = value

        @property
        def cameraModel(self):
            return self._batchedReadValues[1]

        @cameraModel.setter
        def cameraModel(self, value):
            self._batchedReadValues[1] = value

        @property
        def chunkSize(self):
            return self._batchedReadValues[2]

        @chunkSize.setter
        def chunkSize(self, value):
            self._batchedReadValues[2] = value

        @property
        def execIn(self):
            return self._batchedReadValues[3]

        @execIn.setter
        def execIn(self, value):
            self._batchedReadValues[3] = value

        @property
        def fps(self):
            return self._batchedReadValues[4]

        @fps.setter
        def fps(self, value):
            self._batchedReadValues[4] = value

        @property
        def resolution(self):
            return self._batchedReadValues[5]

        @resolution.setter
        def resolution(self, value):
            self._batchedReadValues[5] = value

        @property
        def serialNumber(self):
            return self._batchedReadValues[6]

        @serialNumber.setter
        def serialNumber(self, value):
            self._batchedReadValues[6] = value

        @property
        def streamingPort(self):
            return self._batchedReadValues[7]

        @streamingPort.setter
        def streamingPort(self, value):
            self._batchedReadValues[7] = value

        @property
        def transportLayerMode(self):
            return self._batchedReadValues[8]

        @transportLayerMode.setter
        def transportLayerMode(self, value):
            self._batchedReadValues[8] = value

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
        og.register_node_type(SlCameraOneStreamerDatabase.abi, 2)

    @staticmethod
    def deregister():
        og.deregister_node_type("sl.sensor.camera.ZED_Camera_One")
