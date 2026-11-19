r"""Support for simplified access to data on nodes of type sl.sensor.camera.ZED_ImuNoise

GENERATED CODE. DO NOT MODIFY.

Adds a real ZED X IMU's noise to an IMU reading before it is streamed: white accelerometer noise at the sensor's noise density
and output rate (the ZED SDK's own IMU parameters for a ZED X) and a small accelerometer bias drawn once per run. Orientation
noise is off by default. Pass-through when disabled.
"""

import numpy
import sys
import traceback

import omni.graph.core as og
_og = og._omni_graph_core
import omni.graph.tools.ogn as ogn




class SlImuNoiseDatabase(og.Database):
    """Helper class providing simplified access to data on nodes of type sl.sensor.camera.ZED_ImuNoise

    Class Members:
        node: Node being evaluated

    Attribute Value Properties:
        Inputs:
            inputs.accBias
            inputs.accNoise
            inputs.enabled
            inputs.execIn
            inputs.linAcc
            inputs.orientation
            inputs.orientationNoise
            inputs.seed
        Outputs:
            outputs.execOut
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
        ('inputs:accBias', 'float', 0, None, 'Standard deviation of the per-run accelerometer bias, m/s^2 per axis', {ogn.MetadataKeys.DEFAULT: '0.005'}, True, 0.005, False, ''),
        ('inputs:accNoise', 'float', 0, None, 'Accelerometer white noise per sample, m/s^2 (noise density x sqrt(output rate))', {ogn.MetadataKeys.DEFAULT: '0.019'}, True, 0.019, False, ''),
        ('inputs:enabled', 'bool', 0, None, 'Add the noise; off passes the reading through unchanged', {ogn.MetadataKeys.DEFAULT: 'true'}, True, True, False, ''),
        ('inputs:execIn', 'execution', 0, None, "Triggers the node (connect the IMU reader's execOut)", {}, True, None, False, ''),
        ('inputs:linAcc', 'vector3d', 0, None, 'IMU linear acceleration, m/s^2', {ogn.MetadataKeys.DEFAULT: '[0.0, 0.0, 0.0]'}, True, [0.0, 0.0, 0.0], False, ''),
        ('inputs:orientation', 'quatd', 0, None, 'IMU orientation (IJKR)', {ogn.MetadataKeys.DEFAULT: '[0.0, 0.0, 0.0, 1.0]'}, True, [0.0, 0.0, 0.0, 1.0], False, ''),
        ('inputs:orientationNoise', 'float', 0, None, "Orientation jitter per sample, degrees; 0 = none", {ogn.MetadataKeys.DEFAULT: '0.0'}, True, 0.0, False, ''),
        ('inputs:seed', 'uint', 0, None, "Decorrelates this IMU's noise from other cameras'", {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('outputs:execOut', 'execution', 0, None, 'Fires once the outputs are written', {}, True, None, False, ''),
        ('outputs:linAcc', 'vector3d', 0, None, 'IMU linear acceleration with the noise and bias, m/s^2', {}, True, None, False, ''),
        ('outputs:orientation', 'quatd', 0, None, 'IMU orientation with the noise (IJKR)', {}, True, None, False, ''),
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
        LOCAL_PROPERTY_NAMES = {"accBias", "accNoise", "enabled", "execIn", "linAcc", "orientation", "orientationNoise", "seed", "_setting_locked", "_batchedReadAttributes", "_batchedReadValues"}
        """Helper class that creates natural hierarchical access to input attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)
            self._batchedReadAttributes = [self._attributes.accBias, self._attributes.accNoise, self._attributes.enabled, self._attributes.execIn, self._attributes.linAcc, self._attributes.orientation, self._attributes.orientationNoise, self._attributes.seed]
            self._batchedReadValues = [0.005, 0.019, True, None, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0], 0.0, 0]

        @property
        def accBias(self):
            return self._batchedReadValues[0]

        @accBias.setter
        def accBias(self, value):
            self._batchedReadValues[0] = value

        @property
        def accNoise(self):
            return self._batchedReadValues[1]

        @accNoise.setter
        def accNoise(self, value):
            self._batchedReadValues[1] = value

        @property
        def enabled(self):
            return self._batchedReadValues[2]

        @enabled.setter
        def enabled(self, value):
            self._batchedReadValues[2] = value

        @property
        def execIn(self):
            return self._batchedReadValues[3]

        @execIn.setter
        def execIn(self, value):
            self._batchedReadValues[3] = value

        @property
        def linAcc(self):
            return self._batchedReadValues[4]

        @linAcc.setter
        def linAcc(self, value):
            self._batchedReadValues[4] = value

        @property
        def orientation(self):
            return self._batchedReadValues[5]

        @orientation.setter
        def orientation(self, value):
            self._batchedReadValues[5] = value

        @property
        def orientationNoise(self):
            return self._batchedReadValues[6]

        @orientationNoise.setter
        def orientationNoise(self, value):
            self._batchedReadValues[6] = value

        @property
        def seed(self):
            return self._batchedReadValues[7]

        @seed.setter
        def seed(self, value):
            self._batchedReadValues[7] = value

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
        LOCAL_PROPERTY_NAMES = {"execOut", "linAcc", "orientation", "_batchedWriteValues"}
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
        self.inputs = SlImuNoiseDatabase.ValuesForInputs(node, self.attributes.inputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_OUTPUT)
        self.outputs = SlImuNoiseDatabase.ValuesForOutputs(node, self.attributes.outputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_STATE)
        self.state = SlImuNoiseDatabase.ValuesForState(node, self.attributes.state, dynamic_attributes)

    class abi:
        """Class defining the ABI interface for the node type"""

        @staticmethod
        def get_node_type():
            get_node_type_function = getattr(SlImuNoiseDatabase.NODE_TYPE_CLASS, 'get_node_type', None)
            if callable(get_node_type_function):  # pragma: no cover
                return get_node_type_function()
            return 'sl.sensor.camera.ZED_ImuNoise'

        @staticmethod
        def compute(context, node):
            def database_valid():
                return True
            try:
                per_node_data = SlImuNoiseDatabase.PER_NODE_DATA[node.node_id()]
                db = per_node_data.get('_db')
                if db is None:
                    db = SlImuNoiseDatabase(node)
                    per_node_data['_db'] = db
                if not database_valid():
                    per_node_data['_db'] = None
                    return False
            except:
                db = SlImuNoiseDatabase(node)

            try:
                compute_function = getattr(SlImuNoiseDatabase.NODE_TYPE_CLASS, 'compute', None)
                if callable(compute_function) and compute_function.__code__.co_argcount > 1:  # pragma: no cover
                    return compute_function(context, node)

                db.inputs._prefetch()
                db.inputs._setting_locked = True
                with og.in_compute():
                    return SlImuNoiseDatabase.NODE_TYPE_CLASS.compute(db)
            except Exception as error:  # pragma: no cover
                stack_trace = "".join(traceback.format_tb(sys.exc_info()[2].tb_next))
                db.log_error(f'Assertion raised in compute - {error}\n{stack_trace}', add_context=False)
            finally:
                db.inputs._setting_locked = False
                db.outputs._commit()
            return False

        @staticmethod
        def initialize(context, node):
            SlImuNoiseDatabase._initialize_per_node_data(node)
            initialize_function = getattr(SlImuNoiseDatabase.NODE_TYPE_CLASS, 'initialize', None)
            if callable(initialize_function):  # pragma: no cover
                initialize_function(context, node)

            per_node_data = SlImuNoiseDatabase.PER_NODE_DATA[node.node_id()]

            def on_connection_or_disconnection(*args):
                per_node_data['_db'] = None

            node.register_on_connected_callback(on_connection_or_disconnection)
            node.register_on_disconnected_callback(on_connection_or_disconnection)

        @staticmethod
        def initialize_nodes(context, nodes):
            for n in nodes:
                SlImuNoiseDatabase.abi.initialize(context, n)

        @staticmethod
        def release(node):
            release_function = getattr(SlImuNoiseDatabase.NODE_TYPE_CLASS, 'release', None)
            if callable(release_function):  # pragma: no cover
                release_function(node)
            SlImuNoiseDatabase._release_per_node_data(node)

        @staticmethod
        def init_instance(node, graph_instance_id):
            init_instance_function = getattr(SlImuNoiseDatabase.NODE_TYPE_CLASS, 'init_instance', None)
            if callable(init_instance_function):  # pragma: no cover
                init_instance_function(node, graph_instance_id)

        @staticmethod
        def release_instance(node, graph_instance_id):
            release_instance_function = getattr(SlImuNoiseDatabase.NODE_TYPE_CLASS, 'release_instance', None)
            if callable(release_instance_function):  # pragma: no cover
                release_instance_function(node, graph_instance_id)
            SlImuNoiseDatabase._release_per_node_instance_data(node, graph_instance_id)

        @staticmethod
        def update_node_version(context, node, old_version, new_version):
            update_node_version_function = getattr(SlImuNoiseDatabase.NODE_TYPE_CLASS, 'update_node_version', None)
            if callable(update_node_version_function):  # pragma: no cover
                return update_node_version_function(context, node, old_version, new_version)
            return False

        @staticmethod
        def initialize_type(node_type):
            initialize_type_function = getattr(SlImuNoiseDatabase.NODE_TYPE_CLASS, 'initialize_type', None)
            needs_initializing = True
            if callable(initialize_type_function):  # pragma: no cover
                needs_initializing = initialize_type_function(node_type)
            if needs_initializing:
                node_type.set_metadata(ogn.MetadataKeys.EXTENSION, "sl.sensor.camera")
                node_type.set_metadata(ogn.MetadataKeys.UI_NAME, "ZED IMU Noise")
                node_type.set_metadata(ogn.MetadataKeys.HIDDEN, "true")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORIES, "Stereolabs")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORY_DESCRIPTIONS, "Stereolabs,Nodes used with Stereolabs ZED cameras")
                node_type.set_metadata(ogn.MetadataKeys.DESCRIPTION, "Adds a real ZED X IMU's noise to an IMU reading before it is streamed: white accelerometer noise at the sensor's noise density and output rate (the ZED SDK's own IMU parameters for a ZED X) and a small accelerometer bias drawn once per run. Orientation noise is off by default. Pass-through when disabled.")
                node_type.set_metadata(ogn.MetadataKeys.LANGUAGE, "Python")
                SlImuNoiseDatabase.INTERFACE.add_to_node_type(node_type)

        @staticmethod
        def on_connection_type_resolve(node):
            on_connection_type_resolve_function = getattr(SlImuNoiseDatabase.NODE_TYPE_CLASS, 'on_connection_type_resolve', None)
            if callable(on_connection_type_resolve_function):  # pragma: no cover
                on_connection_type_resolve_function(node)

    NODE_TYPE_CLASS = None

    @staticmethod
    def register(node_type_class):
        SlImuNoiseDatabase.NODE_TYPE_CLASS = node_type_class
        og.register_node_type(SlImuNoiseDatabase.abi, 1)

    @staticmethod
    def deregister():
        og.deregister_node_type("sl.sensor.camera.ZED_ImuNoise")
