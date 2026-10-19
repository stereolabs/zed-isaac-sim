import os
import omni.kit.test
import omni.graph.core as og
import omni.graph.core.tests as ogts
from omni.graph.core.tests.omnigraph_test_utils import _TestGraphAndNode
from omni.graph.core.tests.omnigraph_test_utils import _test_clear_scene
from omni.graph.core.tests.omnigraph_test_utils import _test_setup_scene
from omni.graph.core.tests.omnigraph_test_utils import _test_verify_scene


class TestOgn(ogts.OmniGraphTestCase):

    async def test_data_access(self):
        from sl.sensor.camera.ogn.SlHdrToSrgbDatabase import SlHdrToSrgbDatabase
        test_file_name = "SlHdrToSrgbTemplate.usda"
        usd_path = os.path.join(os.path.dirname(__file__), "usd", test_file_name)
        if not os.path.exists(usd_path):  # pragma: no cover
            self.assertTrue(False, f"{usd_path} not found for loading test")
        (result, error) = await ogts.load_test_file(usd_path)
        self.assertTrue(result, f'{error} on {usd_path}')
        test_node = og.Controller.node("/TestGraph/Template_sl_sensor_camera_ZED_HdrToSrgb")
        database = SlHdrToSrgbDatabase(test_node)
        self.assertTrue(test_node.is_valid())
        node_type_name = test_node.get_type_name()
        self.assertEqual(og.GraphRegistry().get_node_type_version(node_type_name), 1)

        def _attr_error(attribute: og.Attribute, usd_test: bool) -> str:  # pragma no cover
            test_type = "USD Load" if usd_test else "Database Access"
            return f"{node_type_name} {test_type} Test - {attribute.get_name()} value error"


        self.assertTrue(test_node.get_attribute_exists("inputs:blurScale"))
        attribute = test_node.get_attribute("inputs:blurScale")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.blurScale
        database.inputs.blurScale = db_value
        expected_value = 0.0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:bufferSize"))
        attribute = test_node.get_attribute("inputs:bufferSize")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.bufferSize
        database.inputs.bufferSize = db_value
        expected_value = 0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:cameraMtf"))
        attribute = test_node.get_attribute("inputs:cameraMtf")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.cameraMtf
        database.inputs.cameraMtf = db_value
        expected_value = False
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:cudaDeviceIndex"))
        attribute = test_node.get_attribute("inputs:cudaDeviceIndex")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.cudaDeviceIndex
        database.inputs.cudaDeviceIndex = db_value
        expected_value = -1
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:dataPtr"))
        attribute = test_node.get_attribute("inputs:dataPtr")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.dataPtr
        database.inputs.dataPtr = db_value
        expected_value = 0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:exec"))
        attribute = test_node.get_attribute("inputs:exec")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.exec
        database.inputs.exec = db_value

        self.assertTrue(test_node.get_attribute_exists("inputs:eye"))
        attribute = test_node.get_attribute("inputs:eye")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.eye
        database.inputs.eye = db_value
        expected_value = 0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:height"))
        attribute = test_node.get_attribute("inputs:height")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.height
        database.inputs.height = db_value
        expected_value = 0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:motionPtr"))
        attribute = test_node.get_attribute("inputs:motionPtr")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.motionPtr
        database.inputs.motionPtr = db_value
        expected_value = 0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:motionSize"))
        attribute = test_node.get_attribute("inputs:motionSize")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.motionSize
        database.inputs.motionSize = db_value
        expected_value = 0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:noiseGain"))
        attribute = test_node.get_attribute("inputs:noiseGain")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.noiseGain
        database.inputs.noiseGain = db_value
        expected_value = 0.0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:noiseSeed"))
        attribute = test_node.get_attribute("inputs:noiseSeed")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.noiseSeed
        database.inputs.noiseSeed = db_value
        expected_value = 0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:strides"))
        attribute = test_node.get_attribute("inputs:strides")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.strides
        database.inputs.strides = db_value
        expected_value = [0, 0]
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:vignetteInvFocal"))
        attribute = test_node.get_attribute("inputs:vignetteInvFocal")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.vignetteInvFocal
        database.inputs.vignetteInvFocal = db_value
        expected_value = 0.0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:whiteBalance"))
        attribute = test_node.get_attribute("inputs:whiteBalance")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.whiteBalance
        database.inputs.whiteBalance = db_value
        expected_value = [1.0, 1.0, 1.0]
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:width"))
        attribute = test_node.get_attribute("inputs:width")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.width
        database.inputs.width = db_value
        expected_value = 0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("outputs:bufferSize"))
        attribute = test_node.get_attribute("outputs:bufferSize")
        self.assertTrue(attribute.is_valid())
        db_value = database.outputs.bufferSize
        database.outputs.bufferSize = db_value

        self.assertTrue(test_node.get_attribute_exists("outputs:cudaDeviceIndex"))
        attribute = test_node.get_attribute("outputs:cudaDeviceIndex")
        self.assertTrue(attribute.is_valid())
        db_value = database.outputs.cudaDeviceIndex
        database.outputs.cudaDeviceIndex = db_value

        self.assertTrue(test_node.get_attribute_exists("outputs:dataPtr"))
        attribute = test_node.get_attribute("outputs:dataPtr")
        self.assertTrue(attribute.is_valid())
        db_value = database.outputs.dataPtr
        database.outputs.dataPtr = db_value

        self.assertTrue(test_node.get_attribute_exists("outputs:exec"))
        attribute = test_node.get_attribute("outputs:exec")
        self.assertTrue(attribute.is_valid())
        db_value = database.outputs.exec
        database.outputs.exec = db_value

        self.assertTrue(test_node.get_attribute_exists("outputs:height"))
        attribute = test_node.get_attribute("outputs:height")
        self.assertTrue(attribute.is_valid())
        db_value = database.outputs.height
        database.outputs.height = db_value

        self.assertTrue(test_node.get_attribute_exists("outputs:width"))
        attribute = test_node.get_attribute("outputs:width")
        self.assertTrue(attribute.is_valid())
        db_value = database.outputs.width
        database.outputs.width = db_value
        temp_setting = database.inputs._setting_locked
        database.inputs._testing_sample_value = True
        database.outputs._testing_sample_value = True
        database.inputs._setting_locked = temp_setting
        self.assertTrue(database.inputs._testing_sample_value)
        self.assertTrue(database.outputs._testing_sample_value)
