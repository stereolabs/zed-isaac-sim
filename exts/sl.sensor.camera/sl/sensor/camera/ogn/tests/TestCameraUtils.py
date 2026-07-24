"""Unit tests for the Kit-free camera model helpers in sl.sensor.camera.utils.

These cover the base-model / lens-type split used by the ZED camera helper node
property panels: base model enumeration, per-base lens filtering, default snapping
and composite-token recomposition (including the fisheye special case).
"""
import omni.kit.test
from pxr import Sdf, Usd

from sl.sensor.camera.utils import (
    LensType,
    MODEL_ID_VIRTUAL_ZED_X,
    compose_model,
    get_allowed_lens_types,
    get_base_models,
    get_default_lens_type,
    get_sdk_model_id,
    get_sim_lens_type_id,
    resolve_camera_model,
)


def _make_asset(base_model, lens=None, sl_camera_model=None):
    """Build an in-memory ZED asset stage: <root>/base_link/<base_model>.

    Optionally add a 'lens' variantSet (selection = ``lens``) and/or author
    ``sl:cameraModel``. Returns (stage, root_path) for resolve_camera_model.
    """
    stage = Usd.Stage.CreateInMemory()
    root_path = "/World/ZED"
    stage.DefinePrim(root_path, "Xform")
    model_path = f"{root_path}/base_link/{base_model}"
    model = stage.DefinePrim(model_path, "Xform")
    if lens is not None:
        vset = model.GetVariantSets().AddVariantSet("lens")
        for variant in ("Wide", "Narrow", "Fisheye"):
            vset.AddVariant(variant)
        vset.SetVariantSelection(lens)
    if sl_camera_model is not None:
        model.CreateAttribute("sl:cameraModel", Sdf.ValueTypeNames.Token).Set(sl_camera_model)
    return stage, root_path


# NOTE: the class must be named TestOgn - ogn/tests/__init__.py auto-imports test
# modules via omni.graph.tools and only registers each module's `TestOgn` attribute.
class TestOgn(omni.kit.test.AsyncTestCase):

    async def test_base_models_are_deduped_bases(self):
        stereo = get_base_models(stereo_only=True)
        self.assertEqual(stereo, ["ZED_X", "ZED_XM", "ZED_X_Nano", "ZED_M", "ZED_2i"])

        mono = [m for m in get_base_models() if m.startswith("ZED_XONE")]
        self.assertEqual(mono, ["ZED_XONE_UHD", "ZED_XONE_GS", "ZED_XONE_S"])

        # No composite tokens leak into the base list.
        self.assertNotIn("ZED_X_4MM", get_base_models())
        self.assertNotIn("ZED_XONE_S_FISHEYE", get_base_models())

    async def test_allowed_lens_types_per_base(self):
        self.assertEqual(get_allowed_lens_types("ZED_X"), ["Wide", "Narrow"])
        self.assertEqual(get_allowed_lens_types("ZED_X_Nano"), ["Wide"])
        self.assertEqual(get_allowed_lens_types("ZED_M"), ["Wide"])
        self.assertEqual(get_allowed_lens_types("ZED_XONE_UHD"), ["Wide"])
        self.assertEqual(get_allowed_lens_types("ZED_XONE_S"), ["Wide", "Narrow", "Fisheye"])
        # Unknown base falls back to Wide.
        self.assertEqual(get_allowed_lens_types("NOPE"), ["Wide"])

    async def test_default_lens_type_snaps_to_valid(self):
        # ogn default kept when supported.
        self.assertEqual(get_default_lens_type("ZED_X", "Narrow"), "Narrow")
        # ogn default dropped when the base does not offer it.
        self.assertEqual(get_default_lens_type("ZED_M", "Narrow"), "Wide")
        # no ogn default -> first supported.
        self.assertEqual(get_default_lens_type("ZED_XONE_S"), "Wide")

    async def test_compose_model_roundtrip(self):
        self.assertEqual(compose_model("ZED_X", "Wide"), "ZED_X")
        self.assertEqual(compose_model("ZED_X", "Narrow"), "ZED_X_4MM")
        self.assertEqual(compose_model("ZED_XONE_GS", "Narrow"), "ZED_XONE_GS_4MM")
        # Fisheye genuinely selects the distinct spec, not just the base.
        self.assertEqual(compose_model("ZED_XONE_S", "Fisheye"), "ZED_XONE_S_FISHEYE")

    async def test_compose_model_falls_back_on_invalid_pair(self):
        # base with an unsupported lens -> base token (keeps downstream lookups valid).
        self.assertEqual(compose_model("ZED_X", "Fisheye"), "ZED_X")
        # unparsable lens string -> base token.
        self.assertEqual(compose_model("ZED_X", "bogus"), "ZED_X")

    async def test_lens_enum_values(self):
        self.assertEqual(LensType.WIDE.value, "Wide")
        self.assertEqual(LensType.NARROW.value, "Narrow")
        self.assertEqual(LensType.FISHEYE.value, "Fisheye")

    async def test_sdk_model_id_matches_cpp_codes(self):
        # These must match the switch in OgnZEDSimCameraNode.cpp::simCameraModelKey.
        self.assertEqual(get_sdk_model_id("ZED_M"), 1)
        self.assertEqual(get_sdk_model_id("ZED_X"), 4)
        self.assertEqual(get_sdk_model_id("ZED_XM"), 5)
        self.assertEqual(get_sdk_model_id("ZED_X_Nano"), 9)
        self.assertEqual(get_sdk_model_id("ZED_XONE_UHD"), 31)
        # ZED X One S shares SDK model 30 with the GS (same serial pool).
        self.assertEqual(get_sdk_model_id("ZED_XONE_GS"), 30)
        self.assertEqual(get_sdk_model_id("ZED_XONE_S"), 30)
        # Unknown base falls back to ZED_X.
        self.assertEqual(get_sdk_model_id("NOPE"), 4)

    async def test_sim_lens_type_id_matches_enum_order(self):
        # Must match SIM_LENS_TYPE in types_c.h: WIDE=0, NARROW=1, FISHEYE=2.
        self.assertEqual(get_sim_lens_type_id(LensType.WIDE), 0)
        self.assertEqual(get_sim_lens_type_id(LensType.NARROW), 1)
        self.assertEqual(get_sim_lens_type_id(LensType.FISHEYE), 2)

    async def test_virtual_stereo_sentinel_is_not_a_real_model(self):
        self.assertEqual(MODEL_ID_VIRTUAL_ZED_X, -1)
        self.assertNotIn(MODEL_ID_VIRTUAL_ZED_X,
                         [get_sdk_model_id(b) for b in get_base_models()])

    async def test_resolve_from_lens_variant_stereo(self):
        # Narrow variant on a stereo asset composes the 4mm composite token.
        stage, root = _make_asset("ZED_X", lens="Narrow")
        self.assertEqual(resolve_camera_model(stage, root, "FALLBACK"), "ZED_X_4MM")
        # Wide is the plain base token.
        stage, root = _make_asset("ZED_2i", lens="Wide")
        self.assertEqual(resolve_camera_model(stage, root, "FALLBACK"), "ZED_2i")

    async def test_resolve_from_lens_variant_fisheye(self):
        stage, root = _make_asset("ZED_XONE_S", lens="Fisheye")
        self.assertEqual(resolve_camera_model(stage, root, "FALLBACK"), "ZED_XONE_S_FISHEYE")

    async def test_resolve_prefers_authored_sl_camera_model(self):
        # sl:cameraModel wins over the variant selection (explicit override).
        stage, root = _make_asset("ZED_XONE_S", lens="Wide", sl_camera_model="ZED_XONE_S_FISHEYE")
        self.assertEqual(resolve_camera_model(stage, root, "FALLBACK"), "ZED_XONE_S_FISHEYE")

    async def test_resolve_single_lens_asset_no_variant(self):
        # Single-lens body (no 'lens' variantSet) -> base token, Wide.
        stage, root = _make_asset("ZED_M")
        self.assertEqual(resolve_camera_model(stage, root, "FALLBACK"), "ZED_M")

    async def test_resolve_falls_back_when_unresolvable(self):
        self.assertEqual(resolve_camera_model(None, "/World/ZED", "FALLBACK"), "FALLBACK")
        stage, root = _make_asset("ZED_X", lens="Wide")
        self.assertEqual(resolve_camera_model(stage, "", "FALLBACK"), "FALLBACK")
        self.assertEqual(resolve_camera_model(stage, "/Nope", "FALLBACK"), "FALLBACK")
        # Fallback may be None (the UI uses None to mean "nothing detected").
        stage = Usd.Stage.CreateInMemory()
        stage.DefinePrim("/World/Foo", "Xform")
        self.assertIsNone(resolve_camera_model(stage, "/World/Foo", None))
