r"""Support for simplified access to data on nodes of type sl.sensor.camera.ZED_FrameImu

GENERATED CODE. DO NOT MODIFY.

Gives the ZED Stream node its frame's time and the IMU at that time. The time is IsaacReadSimulationTime's, the moment whose
physics state the frame shows. The IMU comes from the IMU of every physics step that the extension keeps for this node, instead
of IsaacReadIMU's latest reading: a frame is streamed a few physics steps after it was rendered. Falls back to the reading
it is given. A stream faster than the app updates passes on every n-th frame, the fewest that keep each in an app update
of its own, so the frames stay evenly spaced, and gives the ZED Stream node the rate it passes them on at. Linear acceleration
out in m/s^2.
"""

import numpy
import sys
import traceback

import omni.graph.core as og
_og = og._omni_graph_core
import omni.graph.tools.ogn as ogn




class SlFrameImuDatabase(og.Database):
    """Helper class providing simplified access to data on nodes of type sl.sensor.camera.ZED_FrameImu

    Class Members:
        node: Node being evaluated

    Attribute Value Properties:
        Inputs:
            inputs.execIn
            inputs.fps
            inputs.linAcc
            inputs.metersPerUnit
            inputs.orientation
            inputs.simulationTime
        Outputs:
            outputs.execOut
            outputs.fps
            outputs.frameTime
            outputs.linAcc
            outputs.orientation
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
        ('inputs:execIn', 'execution', 0, None, "Triggers the node (connect the IMU reader's execOut)", {}, True, None, False, ''),
        ('inputs:fps', 'uint', 0, None, "The stream's frame rate, the rate its camera renders at", {ogn.MetadataKeys.DEFAULT: '30'}, True, 30, False, ''),
        ('inputs:linAcc', 'vector3d', 0, None, 'IMU linear acceleration in stage units per second squared, the fallback', {ogn.MetadataKeys.DEFAULT: '[0.0, 0.0, 0.0]'}, True, [0.0, 0.0, 0.0], False, ''),
        ('inputs:metersPerUnit', 'double', 0, None, "The stage's meters per unit, to give the fallback's acceleration in m/s^2", {ogn.MetadataKeys.DEFAULT: '1.0'}, True, 1.0, False, ''),
        ('inputs:orientation', 'quatd', 0, None, 'IMU orientation (IJKR), the fallback', {ogn.MetadataKeys.DEFAULT: '[0.0, 0.0, 0.0, 1.0]'}, True, [0.0, 0.0, 0.0, 1.0], False, ''),
        ('inputs:simulationTime', 'double', 0, None, "IsaacReadSimulationTime's time of the frame being streamed, seconds", {ogn.MetadataKeys.DEFAULT: '0.0'}, True, 0.0, False, ''),
        ('outputs:execOut', 'execution', 0, None, 'Fires once the outputs are written', {}, True, None, False, ''),
        ('outputs:fps', 'uint', 0, None, "The rate frames are passed on at, which the ZED Stream node declares to receivers: inputs:fps, or the app's update rate when that is lower", {}, True, None, False, ''),
        ('outputs:frameTime', 'double', 0, None, 'Simulation time of the physics state the frame shows, seconds: its stamp', {}, True, None, False, ''),
        ('outputs:linAcc', 'vector3d', 0, None, "IMU linear acceleration at the frame's time, m/s^2", {}, True, None, False, ''),
        ('outputs:orientation', 'quatd', 0, None, "IMU orientation at the frame's time (IJKR)", {}, True, None, False, ''),
    ])

    @classmethod
    def _populate_role_data(cls):
        """Populate a role structure with the non-default roles on this node type"""
        role_data = super()._populate_role_data()
        role_data.inputs.execIn = og.AttributeRole.EXECUTION
        role_data.inputs.linAcc = og.AttributeRole.VECTOR
        role_data.inputs.orientation = og.AttributeRole.QUATERNION
        role_data.outputs.execOut = og.AttributeRole.EXECUTION
        role_data.outputs.linAcc = og.AttributeRole.VECTOR
        role_data.outputs.orientation = og.AttributeRole.QUATERNION
        return role_data

    class ValuesForInputs(og.DynamicAttributeAccess):
        LOCAL_PROPERTY_NAMES = {"execIn", "fps", "linAcc", "metersPerUnit", "orientation", "simulationTime", "_setting_locked", "_batchedReadAttributes", "_batchedReadValues"}
        """Helper class that creates natural hierarchical access to input attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)
            self._batchedReadAttributes = [self._attributes.execIn, self._attributes.fps, self._attributes.linAcc, self._attributes.metersPerUnit, self._attributes.orientation, self._attributes.simulationTime]
            self._batchedReadValues = [None, 30, [0.0, 0.0, 0.0], 1.0, [0.0, 0.0, 0.0, 1.0], 0.0]

        @property
        def execIn(self):
            return self._batchedReadValues[0]

        @execIn.setter
        def execIn(self, value):
            self._batchedReadValues[0] = value

        @property
        def fps(self):
            return self._batchedReadValues[1]

        @fps.setter
        def fps(self, value):
            self._batchedReadValues[1] = value

        @property
        def linAcc(self):
            return self._batchedReadValues[2]

        @linAcc.setter
        def linAcc(self, value):
            self._batchedReadValues[2] = value

        @property
        def metersPerUnit(self):
            return self._batchedReadValues[3]

        @metersPerUnit.setter
        def metersPerUnit(self, value):
            self._batchedReadValues[3] = value

        @property
        def orientation(self):
            return self._batchedReadValues[4]

        @orientation.setter
        def orientation(self, value):
            self._batchedReadValues[4] = value

        @property
        def simulationTime(self):
            return self._batchedReadValues[5]

        @simulationTime.setter
        def simulationTime(self, value):
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
        LOCAL_PROPERTY_NAMES = {"execOut", "fps", "frameTime", "linAcc", "orientation", "_batchedWriteValues"}
        """Helper class that creates natural hierarchical access to output attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)
            self._batchedWriteValues = { }

        @property
        def execOut(self):
            value = self._batchedWriteValues.get(self._attributes.execOut)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.execOut)
                return data_view.get()

        @execOut.setter
        def execOut(self, value):
            self._batchedWriteValues[self._attributes.execOut] = value

        @property
        def fps(self):
            value = self._batchedWriteValues.get(self._attributes.fps)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.fps)
                return data_view.get()

        @fps.setter
        def fps(self, value):
            self._batchedWriteValues[self._attributes.fps] = value

        @property
        def frameTime(self):
            value = self._batchedWriteValues.get(self._attributes.frameTime)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.frameTime)
                return data_view.get()

        @frameTime.setter
        def frameTime(self, value):
            self._batchedWriteValues[self._attributes.frameTime] = value

        @property
        def linAcc(self):
            value = self._batchedWriteValues.get(self._attributes.linAcc)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.linAcc)
                return data_view.get()

        @linAcc.setter
        def linAcc(self, value):
            self._batchedWriteValues[self._attributes.linAcc] = value

        @property
        def orientation(self):
            value = self._batchedWriteValues.get(self._attributes.orientation)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.orientation)
                return data_view.get()

        @orientation.setter
        def orientation(self, value):
            self._batchedWriteValues[self._attributes.orientation] = value

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
        self.inputs = SlFrameImuDatabase.ValuesForInputs(node, self.attributes.inputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_OUTPUT)
        self.outputs = SlFrameImuDatabase.ValuesForOutputs(node, self.attributes.outputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_STATE)
        self.state = SlFrameImuDatabase.ValuesForState(node, self.attributes.state, dynamic_attributes)

    class abi:
        """Class defining the ABI interface for the node type"""

        @staticmethod
        def get_node_type():
            get_node_type_function = getattr(SlFrameImuDatabase.NODE_TYPE_CLASS, 'get_node_type', None)
            if callable(get_node_type_function):  # pragma: no cover
                return get_node_type_function()
            return 'sl.sensor.camera.ZED_FrameImu'

        @staticmethod
        def compute(context, node):
            def database_valid():
                return True
            try:
                per_node_data = SlFrameImuDatabase.PER_NODE_DATA[node.node_id()]
                db = per_node_data.get('_db')
                if db is None:
                    db = SlFrameImuDatabase(node)
                    per_node_data['_db'] = db
                if not database_valid():
                    per_node_data['_db'] = None
                    return False
            except:
                db = SlFrameImuDatabase(node)

            try:
                compute_function = getattr(SlFrameImuDatabase.NODE_TYPE_CLASS, 'compute', None)
                if callable(compute_function) and compute_function.__code__.co_argcount > 1:  # pragma: no cover
                    return compute_function(context, node)

                db.inputs._prefetch()
                db.inputs._setting_locked = True
                with og.in_compute():
                    return SlFrameImuDatabase.NODE_TYPE_CLASS.compute(db)
            except Exception as error:  # pragma: no cover
                stack_trace = "".join(traceback.format_tb(sys.exc_info()[2].tb_next))
                db.log_error(f'Assertion raised in compute - {error}\n{stack_trace}', add_context=False)
            finally:
                db.inputs._setting_locked = False
                db.outputs._commit()
            return False

        @staticmethod
        def initialize(context, node):
            SlFrameImuDatabase._initialize_per_node_data(node)
            initialize_function = getattr(SlFrameImuDatabase.NODE_TYPE_CLASS, 'initialize', None)
            if callable(initialize_function):  # pragma: no cover
                initialize_function(context, node)

            per_node_data = SlFrameImuDatabase.PER_NODE_DATA[node.node_id()]

            def on_connection_or_disconnection(*args):
                per_node_data['_db'] = None

            node.register_on_connected_callback(on_connection_or_disconnection)
            node.register_on_disconnected_callback(on_connection_or_disconnection)

        @staticmethod
        def initialize_nodes(context, nodes):
            for n in nodes:
                SlFrameImuDatabase.abi.initialize(context, n)

        @staticmethod
        def release(node):
            release_function = getattr(SlFrameImuDatabase.NODE_TYPE_CLASS, 'release', None)
            if callable(release_function):  # pragma: no cover
                release_function(node)
            SlFrameImuDatabase._release_per_node_data(node)

        @staticmethod
        def init_instance(node, graph_instance_id):
            init_instance_function = getattr(SlFrameImuDatabase.NODE_TYPE_CLASS, 'init_instance', None)
            if callable(init_instance_function):  # pragma: no cover
                init_instance_function(node, graph_instance_id)

        @staticmethod
        def release_instance(node, graph_instance_id):
            release_instance_function = getattr(SlFrameImuDatabase.NODE_TYPE_CLASS, 'release_instance', None)
            if callable(release_instance_function):  # pragma: no cover
                release_instance_function(node, graph_instance_id)
            SlFrameImuDatabase._release_per_node_instance_data(node, graph_instance_id)

        @staticmethod
        def update_node_version(context, node, old_version, new_version):
            update_node_version_function = getattr(SlFrameImuDatabase.NODE_TYPE_CLASS, 'update_node_version', None)
            if callable(update_node_version_function):  # pragma: no cover
                return update_node_version_function(context, node, old_version, new_version)
            return False

        @staticmethod
        def initialize_type(node_type):
            initialize_type_function = getattr(SlFrameImuDatabase.NODE_TYPE_CLASS, 'initialize_type', None)
            needs_initializing = True
            if callable(initialize_type_function):  # pragma: no cover
                needs_initializing = initialize_type_function(node_type)
            if needs_initializing:
                node_type.set_metadata(ogn.MetadataKeys.EXTENSION, "sl.sensor.camera")
                node_type.set_metadata(ogn.MetadataKeys.UI_NAME, "ZED Frame IMU")
                node_type.set_metadata(ogn.MetadataKeys.HIDDEN, "true")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORIES, "Stereolabs")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORY_DESCRIPTIONS, "Stereolabs,Nodes used with Stereolabs ZED cameras")
                node_type.set_metadata(ogn.MetadataKeys.DESCRIPTION, "Gives the ZED Stream node its frame's time and the IMU at that time. The time is IsaacReadSimulationTime's, the moment whose physics state the frame shows. The IMU comes from the IMU of every physics step that the extension keeps for this node, instead of IsaacReadIMU's latest reading: a frame is streamed a few physics steps after it was rendered. Falls back to the reading it is given. A stream faster than the app updates passes on every n-th frame, the fewest that keep each in an app update of its own, so the frames stay evenly spaced, and gives the ZED Stream node the rate it passes them on at. Linear acceleration out in m/s^2.")
                node_type.set_metadata(ogn.MetadataKeys.LANGUAGE, "Python")
                SlFrameImuDatabase.INTERFACE.add_to_node_type(node_type)

        @staticmethod
        def on_connection_type_resolve(node):
            on_connection_type_resolve_function = getattr(SlFrameImuDatabase.NODE_TYPE_CLASS, 'on_connection_type_resolve', None)
            if callable(on_connection_type_resolve_function):  # pragma: no cover
                on_connection_type_resolve_function(node)

    NODE_TYPE_CLASS = None

    @staticmethod
    def register(node_type_class):
        SlFrameImuDatabase.NODE_TYPE_CLASS = node_type_class
        og.register_node_type(SlFrameImuDatabase.abi, 3)

    @staticmethod
    def deregister():
        og.deregister_node_type("sl.sensor.camera.ZED_FrameImu")
