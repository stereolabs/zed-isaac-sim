"""Unit tests for the shared camera optics in sl.sensor.camera.optics.

Runs on an in-memory stage: no renderer needed. The distortion schema is registered by the app
rather than by USD, so the fisheye cases skip in a bare kit-kernel test session.
"""
import omni.kit.test
from pxr import Usd, UsdGeom

from sl.sensor.camera.optics import apply_camera_optics

_FISHEYE_SCHEMA = "OmniLensDistortionOpenCvFisheyeAPI"
_SCHEMA_REGISTERED = Usd.SchemaRegistry().FindAppliedAPIPrimDefinition(_FISHEYE_SCHEMA) is not None
# ZED X One S at SVGA (960x600, 3 um pixels). The fisheye lens is the shorter of the two and
# is the one with distortion coefficients; its optical center sits at the image center.
_SVGA = [960, 600]
_PIXEL_MM = 3e-3
_WIDE_FOCAL_PX = 370.8
_FISHEYE_FOCAL_PX = 230.0


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

    def test_fisheye_model_authors_the_distortion_schema(self):
        if not _SCHEMA_REGISTERED:
            self.skipTest(f"{_FISHEYE_SCHEMA} is not registered in this app")
        apply_camera_optics(self._cam, "ZED_XONE_S_FISHEYE", "SVGA")

        self.assertIn(_FISHEYE_SCHEMA, self._cam.GetAppliedSchemas())
        self.assertEqual(self._attr("omni:lensdistortion:model"), "opencvFisheye")
        self.assertAlmostEqual(self._attr("omni:lensdistortion:opencvFisheye:fx"),
                               _FISHEYE_FOCAL_PX, places=3)
        self.assertAlmostEqual(self._attr("omni:lensdistortion:opencvFisheye:fy"),
                               _FISHEYE_FOCAL_PX, places=3)
        self.assertAlmostEqual(self._attr("omni:lensdistortion:opencvFisheye:cx"),
                               _SVGA[0] / 2, places=3)
        self.assertAlmostEqual(self._attr("omni:lensdistortion:opencvFisheye:cy"),
                               _SVGA[1] / 2, places=3)
        self.assertAlmostEqual(self._attr("omni:lensdistortion:opencvFisheye:k1"), 0.07, places=4)
        self.assertEqual(tuple(self._attr("omni:lensdistortion:opencvFisheye:imageSize")),
                         tuple(_SVGA))

    def test_pinhole_model_clears_a_previous_fisheye(self):
        """Switching a placed asset's lens back to Wide re-uses the same camera prim."""
        if not _SCHEMA_REGISTERED:
            self.skipTest(f"{_FISHEYE_SCHEMA} is not registered in this app")
        apply_camera_optics(self._cam, "ZED_XONE_S_FISHEYE", "SVGA")
        apply_camera_optics(self._cam, "ZED_XONE_S", "SVGA")

        self.assertNotIn(_FISHEYE_SCHEMA, self._cam.GetAppliedSchemas())
        self.assertFalse(self._cam.HasAttribute("omni:lensdistortion:model"))
