"""Unit tests for the shared camera optics in sl.sensor.camera.optics.

Runs on an in-memory stage: no renderer needed. The distortion schema is registered by the app
rather than by USD, so the fisheye cases skip in a bare kit-kernel test session.
"""
import os

import omni.kit.test
from pxr import Usd, UsdGeom

from sl.sensor.camera.optics import apply_camera_optics

_FISHEYE_SCHEMA = "OmniLensDistortionLutAPI"
_SCHEMA_REGISTERED = Usd.SchemaRegistry().FindAppliedAPIPrimDefinition(_FISHEYE_SCHEMA) is not None
# ZED X One S at SVGA (960x600, 3 um pixels). The fisheye lens is the shorter of the two and
# is the one with distortion coefficients; its optical center sits at the image center.
_SVGA = [960, 600]
_PIXEL_MM = 3e-3
_WIDE_FOCAL_PX = 370.8
_FISHEYE_FOCAL_PX = 230.0
_FISHEYE_MAX_THETA_DEG = 121.98


# NOTE: the class must be named TestOgn - ogn/tests/__init__.py auto-imports test
# modules via omni.graph.tools and only registers each module's `TestOgn` attribute.
class TestOgn(omni.kit.test.AsyncTestCase):

    def setUp(self):
        self._stage = Usd.Stage.CreateInMemory()
        self._cam = UsdGeom.Camera.Define(self._stage, "/Camera").GetPrim()

    def _attr(self, name):
        return self._cam.GetAttribute(name).Get()

    def test_authors_the_model_field_of_view(self):
        self.assertTrue(apply_camera_optics(self._cam, "ZED_XONE_S", "SVGA"))

        self.assertAlmostEqual(self._attr("focalLength"), _WIDE_FOCAL_PX * _PIXEL_MM, places=4)
        self.assertAlmostEqual(self._attr("horizontalAperture"), _SVGA[0] * _PIXEL_MM, places=4)
        self.assertAlmostEqual(self._attr("verticalAperture"), _SVGA[1] * _PIXEL_MM, places=4)
        self.assertEqual(self._attr("fStop"), 0)

    def test_unknown_resolution_leaves_the_prim_alone(self):
        self.assertFalse(apply_camera_optics(self._cam, "ZED_XONE_S", "HD4K"))
        self.assertFalse(self._cam.GetAttribute("focalLength").HasAuthoredValue())

    def test_tick_rate_is_streaming_only(self):
        apply_camera_optics(self._cam, "ZED_XONE_S", "SVGA")
        self.assertFalse(self._cam.HasAttribute("omni:sensor:tickRate"))

        apply_camera_optics(self._cam, "ZED_XONE_S", "SVGA", fps=30)
        self.assertAlmostEqual(self._attr("omni:sensor:tickRate"), 30.0, places=3)

    def test_fisheye_model_authors_the_lookup_schema(self):
        if not _SCHEMA_REGISTERED:
            self.skipTest(f"{_FISHEYE_SCHEMA} is not registered in this app")
        apply_camera_optics(self._cam, "ZED_XONE_S_FISHEYE", "SVGA")

        self.assertAlmostEqual(self._attr("focalLength"), _FISHEYE_FOCAL_PX * _PIXEL_MM, places=4)
        self.assertIn(_FISHEYE_SCHEMA, self._cam.GetAppliedSchemas())
        self.assertEqual(self._attr("omni:lensdistortion:model"), "lut")
        self.assertAlmostEqual(self._attr("omni:lensdistortion:lut:nominalWidth"), _SVGA[0], places=3)
        self.assertAlmostEqual(self._attr("omni:lensdistortion:lut:nominalHeight"), _SVGA[1], places=3)
        # the textures carry the optical center
        self.assertEqual(tuple(self._attr("omni:lensdistortion:lut:opticalCenter")), (_SVGA[0] / 2, _SVGA[1] / 2))
        for name in ("rayEnterDirectionTexture", "rayExitPositionTexture"):
            self.assertTrue(os.path.isfile(self._attr(f"omni:lensdistortion:lut:{name}").path))
        # the lens polynomial turns over at 122 degrees off-axis
        self.assertAlmostEqual(self._attr("fthetaMaxFov"), 2 * _FISHEYE_MAX_THETA_DEG, delta=0.1)

    def test_fisheye_lens_stays_out_of_the_saved_scene(self):
        """The lens points at this machine's temp files, so it is authored for this run only."""
        if not _SCHEMA_REGISTERED:
            self.skipTest(f"{_FISHEYE_SCHEMA} is not registered in this app")
        apply_camera_optics(self._cam, "ZED_XONE_S_FISHEYE", "SVGA")

        root_spec = self._stage.GetRootLayer().GetPrimAtPath("/Camera")
        self.assertFalse(root_spec.HasInfo("apiSchemas"))
        self.assertFalse([name for name in root_spec.properties.keys()
                          if name.startswith("omni:lensdistortion:") or name == "fthetaMaxFov"])

    def test_fisheye_replaces_a_lens_saved_in_the_scene(self):
        """An OpenCV fisheye schema saved on the scene's own layer gives way to the lookup one."""
        if not _SCHEMA_REGISTERED:
            self.skipTest(f"{_FISHEYE_SCHEMA} is not registered in this app")
        self._cam.ApplyAPI("OmniLensDistortionOpenCvFisheyeAPI")
        self._cam.GetAttribute("omni:lensdistortion:model").Set("opencvFisheye")
        apply_camera_optics(self._cam, "ZED_XONE_S_FISHEYE", "SVGA")

        self.assertEqual(self._cam.GetAppliedSchemas(), [_FISHEYE_SCHEMA])
        self.assertEqual(self._attr("omni:lensdistortion:model"), "lut")
        root_spec = self._stage.GetRootLayer().GetPrimAtPath("/Camera")
        self.assertNotIn("OmniLensDistortionOpenCvFisheyeAPI", root_spec.GetInfo("apiSchemas").prependedItems)

    def test_pinhole_model_clears_a_previous_fisheye(self):
        """Switching a placed asset's lens back to Wide re-uses the same camera prim."""
        if not _SCHEMA_REGISTERED:
            self.skipTest(f"{_FISHEYE_SCHEMA} is not registered in this app")
        apply_camera_optics(self._cam, "ZED_XONE_S_FISHEYE", "SVGA")
        apply_camera_optics(self._cam, "ZED_XONE_S", "SVGA")

        self.assertNotIn(_FISHEYE_SCHEMA, self._cam.GetAppliedSchemas())
        self.assertFalse(self._cam.HasAttribute("omni:lensdistortion:model"))
        self.assertFalse(self._cam.HasAttribute("fthetaMaxFov"))
