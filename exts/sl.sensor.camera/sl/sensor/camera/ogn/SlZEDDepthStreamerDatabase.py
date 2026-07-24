r"""Support for simplified access to data on nodes of type sl.sensor.camera.ZED_Depth

GENERATED CODE. DO NOT MODIFY.

Captures RGB and simulated stereo depth from a ZED camera using Isaac Sim's renderer (no ZED SDK required).
"""

import sys
import traceback
import usdrt

import omni.graph.core as og
_og = og._omni_graph_core
import omni.graph.tools.ogn as ogn




class SlZEDDepthStreamerDatabase(og.Database):
    """Helper class providing simplified access to data on nodes of type sl.sensor.camera.ZED_Depth

    Class Members:
        node: Node being evaluated

    Attribute Value Properties:
        Inputs:
            inputs.cameraModel
            inputs.cameraPrim
            inputs.enableSave
            inputs.execIn
            inputs.lensType
            inputs.outputDir
            inputs.resolution

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
        ('inputs:cameraModel', 'token', 0, 'Camera Model', 'ZED Camera model. Determines intrinsics and stereo baseline.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'ZED_X,ZED_XM,ZED_X_Nano,ZED_M,ZED_2i', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["ZED_X", "ZED_XM", "ZED_X_Nano", "ZED_M", "ZED_2i"]', ogn.MetadataKeys.DEFAULT: '"ZED_X"'}, True, "ZED_X", False, ''),
        ('inputs:cameraPrim', 'target', 0, 'ZED Camera Prim', 'ZED Camera prim (e.g. /World/ZED_X).', {ogn.MetadataKeys.LITERAL_ONLY: '1', ogn.MetadataKeys.ALLOW_MULTI_INPUTS: '0', 'uiGroup': 'Camera Selection'}, True, None, False, ''),
        ('inputs:enableSave', 'bool', 0, 'Enable Save', 'Save RGB (PNG) and depth (EXR) to disk each frame.', {ogn.MetadataKeys.DEFAULT: 'false'}, True, False, False, ''),
        ('inputs:execIn', 'execution', 0, 'ExecIn', 'Triggers execution', {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:lensType', 'token', 0, 'Lens Type', 'Lens fitted to the camera. Options shown depend on the selected camera model.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'Wide,Narrow', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["Wide", "Narrow"]', ogn.MetadataKeys.DEFAULT: '"Wide"'}, True, "Wide", False, ''),
        ('inputs:outputDir', 'string', 0, 'Output Directory', 'Directory to save frames. Required when Enable Save is on.', {ogn.MetadataKeys.DEFAULT: '""'}, True, "", False, ''),
        ('inputs:resolution', 'token', 0, 'Resolution', 'Render resolution for RGB and depth.', {ogn.MetadataKeys.ALLOWED_TOKENS: 'HD2K,HD1200,HD1080,HD720,SVGA,VGA', 'uiGroup': 'Configuration', ogn.MetadataKeys.ALLOWED_TOKENS_RAW: '["HD2K", "HD1200", "HD1080", "HD720", "SVGA", "VGA"]', ogn.MetadataKeys.DEFAULT: '"SVGA"'}, True, "SVGA", False, ''),
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

    @classmethod
    def _populate_role_data(cls):
        """Populate a role structure with the non-default roles on this node type"""
        role_data = super()._populate_role_data()
        role_data.inputs.cameraPrim = og.AttributeRole.TARGET
        role_data.inputs.execIn = og.AttributeRole.EXECUTION
        role_data.inputs.outputDir = og.AttributeRole.TEXT
        return role_data

    class ValuesForInputs(og.DynamicAttributeAccess):
        LOCAL_PROPERTY_NAMES = {"cameraModel", "enableSave", "execIn", "lensType", "outputDir", "resolution", "_setting_locked", "_batchedReadAttributes", "_batchedReadValues"}
        """Helper class that creates natural hierarchical access to input attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)
            self._batchedReadAttributes = [self._attributes.cameraModel, self._attributes.enableSave, self._attributes.execIn, self._attributes.lensType, self._attributes.outputDir, self._attributes.resolution]
            self._batchedReadValues = ["ZED_X", False, 0, "Wide", "", "SVGA"]

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
        def cameraModel(self):
            return self._batchedReadValues[0]

        @cameraModel.setter
        def cameraModel(self, value):
            self._batchedReadValues[0] = value

        @property
        def enableSave(self):
            return self._batchedReadValues[1]

        @enableSave.setter
        def enableSave(self, value):
            self._batchedReadValues[1] = value

        @property
        def execIn(self):
            return self._batchedReadValues[2]

        @execIn.setter
        def execIn(self, value):
            self._batchedReadValues[2] = value

        @property
        def lensType(self):
            return self._batchedReadValues[3]

        @lensType.setter
        def lensType(self, value):
            self._batchedReadValues[3] = value

        @property
        def outputDir(self):
            return self._batchedReadValues[4]

        @outputDir.setter
        def outputDir(self, value):
            self._batchedReadValues[4] = value

        @property
        def resolution(self):
            return self._batchedReadValues[5]

        @resolution.setter
        def resolution(self, value):
            self._batchedReadValues[5] = value

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
        self.inputs = SlZEDDepthStreamerDatabase.ValuesForInputs(node, self.attributes.inputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_OUTPUT)
        self.outputs = SlZEDDepthStreamerDatabase.ValuesForOutputs(node, self.attributes.outputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_STATE)
        self.state = SlZEDDepthStreamerDatabase.ValuesForState(node, self.attributes.state, dynamic_attributes)

    class abi:
        """Class defining the ABI interface for the node type"""

        @staticmethod
        def get_node_type():
            get_node_type_function = getattr(SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS, 'get_node_type', None)
            if callable(get_node_type_function):  # pragma: no cover
                return get_node_type_function()
            return 'sl.sensor.camera.ZED_Depth'

        @staticmethod
        def compute(context, node):
            def database_valid():
                return True
            try:
                per_node_data = SlZEDDepthStreamerDatabase.PER_NODE_DATA[node.node_id()]
                db = per_node_data.get('_db')
                if db is None:
                    db = SlZEDDepthStreamerDatabase(node)
                    per_node_data['_db'] = db
                if not database_valid():
                    per_node_data['_db'] = None
                    return False
            except:
                db = SlZEDDepthStreamerDatabase(node)

            try:
                compute_function = getattr(SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS, 'compute', None)
                if callable(compute_function) and compute_function.__code__.co_argcount > 1:  # pragma: no cover
                    return compute_function(context, node)

                db.inputs._prefetch()
                db.inputs._setting_locked = True
                with og.in_compute():
                    return SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS.compute(db)
            except Exception as error:  # pragma: no cover
                stack_trace = "".join(traceback.format_tb(sys.exc_info()[2].tb_next))
                db.log_error(f'Assertion raised in compute - {error}\n{stack_trace}', add_context=False)
            finally:
                db.inputs._setting_locked = False
                db.outputs._commit()
            return False

        @staticmethod
        def initialize(context, node):
            SlZEDDepthStreamerDatabase._initialize_per_node_data(node)
            initialize_function = getattr(SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS, 'initialize', None)
            if callable(initialize_function):  # pragma: no cover
                initialize_function(context, node)

            per_node_data = SlZEDDepthStreamerDatabase.PER_NODE_DATA[node.node_id()]

            def on_connection_or_disconnection(*args):
                per_node_data['_db'] = None

            node.register_on_connected_callback(on_connection_or_disconnection)
            node.register_on_disconnected_callback(on_connection_or_disconnection)

        @staticmethod
        def initialize_nodes(context, nodes):
            for n in nodes:
                SlZEDDepthStreamerDatabase.abi.initialize(context, n)

        @staticmethod
        def release(node):
            release_function = getattr(SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS, 'release', None)
            if callable(release_function):  # pragma: no cover
                release_function(node)
            SlZEDDepthStreamerDatabase._release_per_node_data(node)

        @staticmethod
        def init_instance(node, graph_instance_id):
            init_instance_function = getattr(SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS, 'init_instance', None)
            if callable(init_instance_function):  # pragma: no cover
                init_instance_function(node, graph_instance_id)

        @staticmethod
        def release_instance(node, graph_instance_id):
            release_instance_function = getattr(SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS, 'release_instance', None)
            if callable(release_instance_function):  # pragma: no cover
                release_instance_function(node, graph_instance_id)
            SlZEDDepthStreamerDatabase._release_per_node_instance_data(node, graph_instance_id)

        @staticmethod
        def update_node_version(context, node, old_version, new_version):
            update_node_version_function = getattr(SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS, 'update_node_version', None)
            if callable(update_node_version_function):  # pragma: no cover
                return update_node_version_function(context, node, old_version, new_version)
            return False

        @staticmethod
        def initialize_type(node_type):
            initialize_type_function = getattr(SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS, 'initialize_type', None)
            needs_initializing = True
            if callable(initialize_type_function):  # pragma: no cover
                needs_initializing = initialize_type_function(node_type)
            if needs_initializing:
                node_type.set_metadata(ogn.MetadataKeys.EXTENSION, "sl.sensor.camera")
                node_type.set_metadata(ogn.MetadataKeys.UI_NAME, "ZED Depth")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORIES, "Stereolabs")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORY_DESCRIPTIONS, "Stereolabs,Nodes used with Stereolabs ZED cameras")
                node_type.set_metadata(ogn.MetadataKeys.DESCRIPTION, "Captures RGB and simulated stereo depth from a ZED camera using Isaac Sim's renderer (no ZED SDK required).")
                node_type.set_metadata(ogn.MetadataKeys.LANGUAGE, "Python")
                SlZEDDepthStreamerDatabase.INTERFACE.add_to_node_type(node_type)

        @staticmethod
        def on_connection_type_resolve(node):
            on_connection_type_resolve_function = getattr(SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS, 'on_connection_type_resolve', None)
            if callable(on_connection_type_resolve_function):  # pragma: no cover
                on_connection_type_resolve_function(node)

    NODE_TYPE_CLASS = None

    @staticmethod
    def register(node_type_class):
        SlZEDDepthStreamerDatabase.NODE_TYPE_CLASS = node_type_class
        og.register_node_type(SlZEDDepthStreamerDatabase.abi, 1)

    @staticmethod
    def deregister():
        og.deregister_node_type("sl.sensor.camera.ZED_Depth")
