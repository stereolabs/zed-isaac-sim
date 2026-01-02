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
        from sl.sensor.camera.ogn.SlCameraStreamerDatabase import SlCameraStreamerDatabase
        test_file_name = "SlCameraStreamerTemplate.usda"
        usd_path = os.path.join(os.path.dirname(__file__), "usd", test_file_name)
        if not os.path.exists(usd_path):  # pragma: no cover
            self.assertTrue(False, f"{usd_path} not found for loading test")
        (result, error) = await ogts.load_test_file(usd_path)
        self.assertTrue(result, f'{error} on {usd_path}')
        test_node = og.Controller.node("/TestGraph/Template_sl_sensor_camera_ZED_Camera")
        database = SlCameraStreamerDatabase(test_node)
        self.assertTrue(test_node.is_valid())
        node_type_name = test_node.get_type_name()
        self.assertEqual(og.GraphRegistry().get_node_type_version(node_type_name), 2)

        def _attr_error(attribute: og.Attribute, usd_test: bool) -> str:  # pragma no cover
            test_type = "USD Load" if usd_test else "Database Access"
            return f"{node_type_name} {test_type} Test - {attribute.get_name()} value error"


        self.assertTrue(test_node.get_attribute_exists("inputs:bitrate"))
        attribute = test_node.get_attribute("inputs:bitrate")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.bitrate
        database.inputs.bitrate = db_value
        expected_value = 8000
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:cameraModel"))
        attribute = test_node.get_attribute("inputs:cameraModel")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.cameraModel
        database.inputs.cameraModel = db_value
        expected_value = "ZED_X"
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:cameraPrim"))
        attribute = test_node.get_attribute("inputs:cameraPrim")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.cameraPrim

        self.assertTrue(test_node.get_attribute_exists("inputs:chunkSize"))
        attribute = test_node.get_attribute("inputs:chunkSize")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.chunkSize
        database.inputs.chunkSize = db_value
        expected_value = 4096
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:execIn"))
        attribute = test_node.get_attribute("inputs:execIn")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.execIn
        database.inputs.execIn = db_value
        expected_value = 0
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:fps"))
        attribute = test_node.get_attribute("inputs:fps")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.fps
        database.inputs.fps = db_value
        expected_value = 30
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:resolution"))
        attribute = test_node.get_attribute("inputs:resolution")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.resolution
        database.inputs.resolution = db_value
        expected_value = "HD1200"
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:streamingPort"))
        attribute = test_node.get_attribute("inputs:streamingPort")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.streamingPort
        database.inputs.streamingPort = db_value
        expected_value = 30000
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))

        self.assertTrue(test_node.get_attribute_exists("inputs:transportLayerMode"))
        attribute = test_node.get_attribute("inputs:transportLayerMode")
        self.assertTrue(attribute.is_valid())
        db_value = database.inputs.transportLayerMode
        database.inputs.transportLayerMode = db_value
        expected_value = "BOTH"
        actual_value = og.Controller.get(attribute)
        ogts.verify_values(expected_value, actual_value, _attr_error(attribute, True))
        ogts.verify_values(expected_value, db_value, _attr_error(attribute, False))
        temp_setting = database.inputs._setting_locked
        database.inputs._testing_sample_value = True
        database.inputs._setting_locked = temp_setting
        self.assertTrue(database.inputs._testing_sample_value)
