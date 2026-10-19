r"""Support for simplified access to data on nodes of type sl.sensor.camera.ZED_HdrToSrgb

GENERATED CODE. DO NOT MODIFY.

Encodes a render product's linear HdrColor (float16 RGBA, on the GPU) into the sRGB RGBA8 image streamed by the ZED node,
as a real ZED X outputs it: its sharpness, lens vignetting, motion blur over the exposure time, white balance and sensor
noise. Inputs mirror the HdrColor annotator's pointer outputs; outputs mirror the rgb annotator's, so it slots in front of
the ZED Stream node. The output buffer is complete when the node's exec fires.
"""

import numpy
import sys
import traceback

import omni.graph.core as og
_og = og._omni_graph_core
import omni.graph.tools.ogn as ogn




class SlHdrToSrgbDatabase(og.Database):
    """Helper class providing simplified access to data on nodes of type sl.sensor.camera.ZED_HdrToSrgb

    Class Members:
        node: Node being evaluated

    Attribute Value Properties:
        Inputs:
            inputs.blurScale
            inputs.bufferSize
            inputs.cameraMtf
            inputs.cudaDeviceIndex
            inputs.dataPtr
            inputs.exec
            inputs.eye
            inputs.height
            inputs.motionPtr
            inputs.motionSize
            inputs.noiseGain
            inputs.noiseSeed
            inputs.strides
            inputs.vignetteInvFocal
            inputs.whiteBalance
            inputs.width
        Outputs:
            outputs.bufferSize
            outputs.cudaDeviceIndex
            outputs.dataPtr
            outputs.exec
            outputs.height
            outputs.width
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
        ('inputs:blurScale', 'float', 0, None, "Exposure time over the motion vectors' time step: the fraction of each vector the image is smeared along; 0 or less = no motion blur", {ogn.MetadataKeys.DEFAULT: '0.0'}, True, 0.0, False, ''),
        ('inputs:bufferSize', 'uint64', 0, None, 'Size of the HdrColor buffer in bytes', {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:cameraMtf', 'bool', 0, None, "Apply a real ZED X's sharpness instead of the renderer's", {ogn.MetadataKeys.DEFAULT: 'false'}, True, False, False, ''),
        ('inputs:cudaDeviceIndex', 'int', 0, None, 'CUDA device holding the buffer; negative means host memory (unsupported)', {ogn.MetadataKeys.DEFAULT: '-1'}, True, -1, False, ''),
        ('inputs:dataPtr', 'uint64', 0, None, 'Device pointer to the HdrColor buffer (float16 RGBA)', {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:exec', 'execution', 0, None, "Triggers the encode (connect the HdrColor annotator's exec)", {}, True, None, False, ''),
        ('inputs:eye', 'uint', 0, None, 'Which lens this encoder images: 0 left (or a single camera), 1 right', {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:height', 'uint', 0, None, 'Image height in pixels', {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:motionPtr', 'uint64', 0, None, "Device pointer to the render product's MotionVectors buffer (float32 RGBA, pixels towards each pixel's previous position); 0 = no motion blur", {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:motionSize', 'uint64', 0, None, 'Size of the MotionVectors buffer in bytes', {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:noiseGain', 'float', 0, None, "Total sensor gain (analog x digital, i.e. the camera's exposure:iso / 100) whose sensor noise is added before the encode; 0 or less adds no noise", {ogn.MetadataKeys.DEFAULT: '0.0'}, True, 0.0, False, ''),
        ('inputs:noiseSeed', 'uint', 0, None, "Decorrelates this encoder's noise from other encoders' (e.g. the other eye); the noise also changes every frame", {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('inputs:strides', 'int2', 0, None, 'Byte strides of the HdrColor buffer: (pixel, row); zeros for contiguous', {ogn.MetadataKeys.DEFAULT: '[0, 0]'}, True, [0, 0], False, ''),
        ('inputs:vignetteInvFocal', 'float', 0, None, '1 / the focal length in pixels at this resolution, for the lens vignetting; 0 or less = no vignetting', {ogn.MetadataKeys.DEFAULT: '0.0'}, True, 0.0, False, ''),
        ('inputs:whiteBalance', 'float3', 0, None, "White balance gains (R, G, B) applied in linear light before the lens falloff and the noise, e.g. from the camera's auto white balance; (1, 1, 1) = none", {ogn.MetadataKeys.DEFAULT: '[1.0, 1.0, 1.0]'}, True, [1.0, 1.0, 1.0], False, ''),
        ('inputs:width', 'uint', 0, None, 'Image width in pixels', {ogn.MetadataKeys.DEFAULT: '0'}, True, 0, False, ''),
        ('outputs:bufferSize', 'uint64', 0, None, 'Size of the sRGB buffer in bytes (width * height * 4)', {}, True, None, False, ''),
        ('outputs:cudaDeviceIndex', 'int', 0, None, 'CUDA device holding the output buffer', {}, True, None, False, ''),
        ('outputs:dataPtr', 'uint64', 0, None, 'Device pointer to the sRGB RGBA8 buffer', {}, True, None, False, ''),
        ('outputs:exec', 'execution', 0, None, 'Fires once the sRGB buffer is written', {}, True, None, False, ''),
        ('outputs:height', 'uint', 0, None, 'Image height in pixels', {}, True, None, False, ''),
        ('outputs:width', 'uint', 0, None, 'Image width in pixels', {}, True, None, False, ''),
    ])

    @classmethod
    def _populate_role_data(cls):
        """Populate a role structure with the non-default roles on this node type"""
        role_data = super()._populate_role_data()
        role_data.inputs.exec = og.AttributeRole.EXECUTION
        role_data.outputs.exec = og.AttributeRole.EXECUTION
        return role_data

    class ValuesForInputs(og.DynamicAttributeAccess):
        LOCAL_PROPERTY_NAMES = {"blurScale", "bufferSize", "cameraMtf", "cudaDeviceIndex", "dataPtr", "exec", "eye", "height", "motionPtr", "motionSize", "noiseGain", "noiseSeed", "strides", "vignetteInvFocal", "whiteBalance", "width", "_setting_locked", "_batchedReadAttributes", "_batchedReadValues"}
        """Helper class that creates natural hierarchical access to input attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)
            self._batchedReadAttributes = [self._attributes.blurScale, self._attributes.bufferSize, self._attributes.cameraMtf, self._attributes.cudaDeviceIndex, self._attributes.dataPtr, self._attributes.exec, self._attributes.eye, self._attributes.height, self._attributes.motionPtr, self._attributes.motionSize, self._attributes.noiseGain, self._attributes.noiseSeed, self._attributes.strides, self._attributes.vignetteInvFocal, self._attributes.whiteBalance, self._attributes.width]
            self._batchedReadValues = [0.0, 0, False, -1, 0, None, 0, 0, 0, 0, 0.0, 0, [0, 0], 0.0, [1.0, 1.0, 1.0], 0]

        @property
        def blurScale(self):
            return self._batchedReadValues[0]

        @blurScale.setter
        def blurScale(self, value):
            self._batchedReadValues[0] = value

        @property
        def bufferSize(self):
            return self._batchedReadValues[1]

        @bufferSize.setter
        def bufferSize(self, value):
            self._batchedReadValues[1] = value

        @property
        def cameraMtf(self):
            return self._batchedReadValues[2]

        @cameraMtf.setter
        def cameraMtf(self, value):
            self._batchedReadValues[2] = value

        @property
        def cudaDeviceIndex(self):
            return self._batchedReadValues[3]

        @cudaDeviceIndex.setter
        def cudaDeviceIndex(self, value):
            self._batchedReadValues[3] = value

        @property
        def dataPtr(self):
            return self._batchedReadValues[4]

        @dataPtr.setter
        def dataPtr(self, value):
            self._batchedReadValues[4] = value

        @property
        def exec(self):
            return self._batchedReadValues[5]

        @exec.setter
        def exec(self, value):
            self._batchedReadValues[5] = value

        @property
        def eye(self):
            return self._batchedReadValues[6]

        @eye.setter
        def eye(self, value):
            self._batchedReadValues[6] = value

        @property
        def height(self):
            return self._batchedReadValues[7]

        @height.setter
        def height(self, value):
            self._batchedReadValues[7] = value

        @property
        def motionPtr(self):
            return self._batchedReadValues[8]

        @motionPtr.setter
        def motionPtr(self, value):
            self._batchedReadValues[8] = value

        @property
        def motionSize(self):
            return self._batchedReadValues[9]

        @motionSize.setter
        def motionSize(self, value):
            self._batchedReadValues[9] = value

        @property
        def noiseGain(self):
            return self._batchedReadValues[10]

        @noiseGain.setter
        def noiseGain(self, value):
            self._batchedReadValues[10] = value

        @property
        def noiseSeed(self):
            return self._batchedReadValues[11]

        @noiseSeed.setter
        def noiseSeed(self, value):
            self._batchedReadValues[11] = value

        @property
        def strides(self):
            return self._batchedReadValues[12]

        @strides.setter
        def strides(self, value):
            self._batchedReadValues[12] = value

        @property
        def vignetteInvFocal(self):
            return self._batchedReadValues[13]

        @vignetteInvFocal.setter
        def vignetteInvFocal(self, value):
            self._batchedReadValues[13] = value

        @property
        def whiteBalance(self):
            return self._batchedReadValues[14]

        @whiteBalance.setter
        def whiteBalance(self, value):
            self._batchedReadValues[14] = value

        @property
        def width(self):
            return self._batchedReadValues[15]

        @width.setter
        def width(self, value):
            self._batchedReadValues[15] = value

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
        LOCAL_PROPERTY_NAMES = {"bufferSize", "cudaDeviceIndex", "dataPtr", "exec", "height", "width", "_batchedWriteValues"}
        """Helper class that creates natural hierarchical access to output attributes"""
        def __init__(self, node: og.Node, attributes, dynamic_attributes: og.DynamicAttributeInterface):
            """Initialize simplified access for the attribute data"""
            context = node.get_graph().get_default_graph_context()
            super().__init__(context, node, attributes, dynamic_attributes)
            self._batchedWriteValues = { }

        @property
        def bufferSize(self):
            value = self._batchedWriteValues.get(self._attributes.bufferSize)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.bufferSize)
                return data_view.get()

        @bufferSize.setter
        def bufferSize(self, value):
            self._batchedWriteValues[self._attributes.bufferSize] = value

        @property
        def cudaDeviceIndex(self):
            value = self._batchedWriteValues.get(self._attributes.cudaDeviceIndex)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.cudaDeviceIndex)
                return data_view.get()

        @cudaDeviceIndex.setter
        def cudaDeviceIndex(self, value):
            self._batchedWriteValues[self._attributes.cudaDeviceIndex] = value

        @property
        def dataPtr(self):
            value = self._batchedWriteValues.get(self._attributes.dataPtr)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.dataPtr)
                return data_view.get()

        @dataPtr.setter
        def dataPtr(self, value):
            self._batchedWriteValues[self._attributes.dataPtr] = value

        @property
        def exec(self):
            value = self._batchedWriteValues.get(self._attributes.exec)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.exec)
                return data_view.get()

        @exec.setter
        def exec(self, value):
            self._batchedWriteValues[self._attributes.exec] = value

        @property
        def height(self):
            value = self._batchedWriteValues.get(self._attributes.height)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.height)
                return data_view.get()

        @height.setter
        def height(self, value):
            self._batchedWriteValues[self._attributes.height] = value

        @property
        def width(self):
            value = self._batchedWriteValues.get(self._attributes.width)
            if value:
                return value
            else:
                data_view = og.AttributeValueHelper(self._attributes.width)
                return data_view.get()

        @width.setter
        def width(self, value):
            self._batchedWriteValues[self._attributes.width] = value

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
        self.inputs = SlHdrToSrgbDatabase.ValuesForInputs(node, self.attributes.inputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_OUTPUT)
        self.outputs = SlHdrToSrgbDatabase.ValuesForOutputs(node, self.attributes.outputs, dynamic_attributes)
        dynamic_attributes = self.dynamic_attribute_data(node, og.AttributePortType.ATTRIBUTE_PORT_TYPE_STATE)
        self.state = SlHdrToSrgbDatabase.ValuesForState(node, self.attributes.state, dynamic_attributes)

    class abi:
        """Class defining the ABI interface for the node type"""

        @staticmethod
        def get_node_type():
            get_node_type_function = getattr(SlHdrToSrgbDatabase.NODE_TYPE_CLASS, 'get_node_type', None)
            if callable(get_node_type_function):  # pragma: no cover
                return get_node_type_function()
            return 'sl.sensor.camera.ZED_HdrToSrgb'

        @staticmethod
        def compute(context, node):
            def database_valid():
                return True
            try:
                per_node_data = SlHdrToSrgbDatabase.PER_NODE_DATA[node.node_id()]
                db = per_node_data.get('_db')
                if db is None:
                    db = SlHdrToSrgbDatabase(node)
                    per_node_data['_db'] = db
                if not database_valid():
                    per_node_data['_db'] = None
                    return False
            except:
                db = SlHdrToSrgbDatabase(node)

            try:
                compute_function = getattr(SlHdrToSrgbDatabase.NODE_TYPE_CLASS, 'compute', None)
                if callable(compute_function) and compute_function.__code__.co_argcount > 1:  # pragma: no cover
                    return compute_function(context, node)

                db.inputs._prefetch()
                db.inputs._setting_locked = True
                with og.in_compute():
                    return SlHdrToSrgbDatabase.NODE_TYPE_CLASS.compute(db)
            except Exception as error:  # pragma: no cover
                stack_trace = "".join(traceback.format_tb(sys.exc_info()[2].tb_next))
                db.log_error(f'Assertion raised in compute - {error}\n{stack_trace}', add_context=False)
            finally:
                db.inputs._setting_locked = False
                db.outputs._commit()
            return False

        @staticmethod
        def initialize(context, node):
            SlHdrToSrgbDatabase._initialize_per_node_data(node)
            initialize_function = getattr(SlHdrToSrgbDatabase.NODE_TYPE_CLASS, 'initialize', None)
            if callable(initialize_function):  # pragma: no cover
                initialize_function(context, node)

            per_node_data = SlHdrToSrgbDatabase.PER_NODE_DATA[node.node_id()]

            def on_connection_or_disconnection(*args):
                per_node_data['_db'] = None

            node.register_on_connected_callback(on_connection_or_disconnection)
            node.register_on_disconnected_callback(on_connection_or_disconnection)

        @staticmethod
        def initialize_nodes(context, nodes):
            for n in nodes:
                SlHdrToSrgbDatabase.abi.initialize(context, n)

        @staticmethod
        def release(node):
            release_function = getattr(SlHdrToSrgbDatabase.NODE_TYPE_CLASS, 'release', None)
            if callable(release_function):  # pragma: no cover
                release_function(node)
            SlHdrToSrgbDatabase._release_per_node_data(node)

        @staticmethod
        def init_instance(node, graph_instance_id):
            init_instance_function = getattr(SlHdrToSrgbDatabase.NODE_TYPE_CLASS, 'init_instance', None)
            if callable(init_instance_function):  # pragma: no cover
                init_instance_function(node, graph_instance_id)

        @staticmethod
        def release_instance(node, graph_instance_id):
            release_instance_function = getattr(SlHdrToSrgbDatabase.NODE_TYPE_CLASS, 'release_instance', None)
            if callable(release_instance_function):  # pragma: no cover
                release_instance_function(node, graph_instance_id)
            SlHdrToSrgbDatabase._release_per_node_instance_data(node, graph_instance_id)

        @staticmethod
        def update_node_version(context, node, old_version, new_version):
            update_node_version_function = getattr(SlHdrToSrgbDatabase.NODE_TYPE_CLASS, 'update_node_version', None)
            if callable(update_node_version_function):  # pragma: no cover
                return update_node_version_function(context, node, old_version, new_version)
            return False

        @staticmethod
        def initialize_type(node_type):
            initialize_type_function = getattr(SlHdrToSrgbDatabase.NODE_TYPE_CLASS, 'initialize_type', None)
            needs_initializing = True
            if callable(initialize_type_function):  # pragma: no cover
                needs_initializing = initialize_type_function(node_type)
            if needs_initializing:
                node_type.set_metadata(ogn.MetadataKeys.EXTENSION, "sl.sensor.camera")
                node_type.set_metadata(ogn.MetadataKeys.UI_NAME, "ZED HDR to sRGB")
                node_type.set_metadata(ogn.MetadataKeys.HIDDEN, "true")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORIES, "Stereolabs")
                node_type.set_metadata(ogn.MetadataKeys.CATEGORY_DESCRIPTIONS, "Stereolabs,Nodes used with Stereolabs ZED cameras")
                node_type.set_metadata(ogn.MetadataKeys.DESCRIPTION, "Encodes a render product's linear HdrColor (float16 RGBA, on the GPU) into the sRGB RGBA8 image streamed by the ZED node, as a real ZED X outputs it: its sharpness, lens vignetting, motion blur over the exposure time, white balance and sensor noise. Inputs mirror the HdrColor annotator's pointer outputs; outputs mirror the rgb annotator's, so it slots in front of the ZED Stream node. The output buffer is complete when the node's exec fires.")
                node_type.set_metadata(ogn.MetadataKeys.LANGUAGE, "Python")
                SlHdrToSrgbDatabase.INTERFACE.add_to_node_type(node_type)

        @staticmethod
        def on_connection_type_resolve(node):
            on_connection_type_resolve_function = getattr(SlHdrToSrgbDatabase.NODE_TYPE_CLASS, 'on_connection_type_resolve', None)
            if callable(on_connection_type_resolve_function):  # pragma: no cover
                on_connection_type_resolve_function(node)

    NODE_TYPE_CLASS = None

    @staticmethod
    def register(node_type_class):
        SlHdrToSrgbDatabase.NODE_TYPE_CLASS = node_type_class
        og.register_node_type(SlHdrToSrgbDatabase.abi, 1)

    @staticmethod
    def deregister():
        og.deregister_node_type("sl.sensor.camera.ZED_HdrToSrgb")
