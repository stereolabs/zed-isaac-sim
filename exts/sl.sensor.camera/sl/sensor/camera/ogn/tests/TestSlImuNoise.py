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
        from sl.sensor.camera.ogn.SlImuNoiseDatabase import SlImuNoiseDatabase
        test_file_name = "SlImuNoiseTemplate.usda"
        usd_path = os.path.join(os.path.dirname(__file__), "usd", test_file_name)
        if not os.path.exists(usd_path):  # pragma: no cover
            self.assertTrue(False, f"{usd_path} not found for loading test")
        (result, error) = await ogts.load_test_file(usd_path)
        self.assertTrue(result, f'{error} on {usd_path}')
        test_node = og.Controller.node("/TestGraph/Template_sl_sensor_camera_ZED_ImuNoise")
        database = SlImuNoiseDatabase(test_node)
        self.assertTrue(test_node.is_valid())
        node_type_name = test_node.get_type_name()
        self.assertEqual(og.GraphRegistry().get_node_type_version(node_type_name), 1)

        def _attr_error(attribute: og.Attribute, usd_test: bool) -> str:  # pragma no cover
            test_type = "USD Load" if usd_test else "Database Access"
            return f"{node_type_name} {test_type} Test - {attribute.get_name()} value error"


        self.assertTrue(test_node.get_attribute_exists("inputs:accBias"))
        attribute = test_node.get_attribute("inputs:accBias")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.accBias
        database.inputs.accBias = db_value
        expected_value = 0.005
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:accNoise"))
        attribute = test_node.get_attribute("inputs:accNoise")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.accNoise
        database.inputs.accNoise = db_value
        expected_value = 0.019
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:enabled"))
        attribute = test_node.get_attribute("inputs:enabled")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.enabled
        database.inputs.enabled = db_value
        expected_value = True
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:execIn"))
        attribute = test_node.get_attribute("inputs:execIn")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.execIn
        database.inputs.execIn = db_value

        self.assertTrue(test_node.get_attribute_exists("inputs:linAcc"))
        attribute = test_node.get_attribute("inputs:linAcc")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.linAcc
        database.inputs.linAcc = db_value
        expected_value = [0.0, 0.0, 0.0]
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:orientation"))
        attribute = test_node.get_attribute("inputs:orientation")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.orientation
        database.inputs.orientation = db_value
        expected_value = [0.0, 0.0, 0.0, 1.0]
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:orientationNoise"))
        attribute = test_node.get_attribute("inputs:orientationNoise")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.orientationNoise
        database.inputs.orientationNoise = db_value
        expected_value = 0.0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:seed"))
        attribute = test_node.get_attribute("inputs:seed")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.seed
        database.inputs.seed = db_value
        expected_value = 0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("outputs:execOut"))
        attribute = test_node.get_attribute("outputs:execOut")
        self.assertTrue(attribute.is_valid())
        db_value = database.outputs.execOut
        database.outputs.execOut = db_value

        self.assertTrue(test_node.get_attribute_exists("outputs:linAcc"))
        attribute = test_node.get_attribute("outputs:linAcc")
        self.assertTrue(attribute.is_valid())
        db_value = database.outputs.linAcc
        database.outputs.linAcc = db_value

        self.assertTrue(test_node.get_attribute_exists("outputs:orientation"))
        attribute = test_node.get_attribute("outputs:orientation")
        self.assertTrue(attribute.is_valid())
        db_value = database.outputs.orientation
        database.outputs.orientation = db_value
        temp_setting = database.inputs._setting_locked
        database.inputs._testing_sample_value = True
        database.outputs._testing_sample_value = True
        database.inputs._setting_locked = temp_setting
        self.assertTrue(database.inputs._testing_sample_value)
        self.assertTrue(database.outputs._testing_sample_value)
