"""Version-migration helpers for the ZED camera OGN nodes."""
import omni.usd
from pxr import Sdf

from ..utils import get_camera_model, get_lens_type


def migrate_camera_model_to_base_lens(node) -> None:
    """v2 -> v3: split the composite ``inputs:cameraModel`` token into base + lens.

    Runs during OGN node version upgrade, where the OmniGraph runtime attributes
    are not valid yet (``og.Controller.get`` raises), so operate on the authored
    USD prim attributes instead. ``inputs:cameraModel`` keeps its name but now holds
    the base model; ``inputs:lensType`` is authored from the old composite's lens.
    """
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(node.get_prim_path())
    model_attr = prim.GetAttribute("inputs:cameraModel")
    old_model = model_attr.Get() if model_attr else None
    if old_model is None:
        return
    model_attr.Set(get_camera_model(old_model))
    lens_attr = prim.GetAttribute("inputs:lensType")
    if not lens_attr:
        lens_attr = prim.CreateAttribute("inputs:lensType", Sdf.ValueTypeNames.Token)
    lens_attr.Set(get_lens_type(old_model).value)
