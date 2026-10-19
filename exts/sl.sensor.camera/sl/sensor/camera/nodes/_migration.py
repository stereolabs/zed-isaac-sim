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


# Inputs of the older ZED Sim2Real post-process, removed in v5.
_SIM2REAL_V4_INPUTS = ("inputs:zedSim2RealSceneLux", "inputs:zedSim2RealAeTarget", "inputs:zedSim2RealExposureGain",
                       "inputs:zedSim2RealToneMode", "inputs:zedSim2RealVignetteStrength",
                       "inputs:zedSim2RealPhotometricOnly")


def migrate_sim2real_to_master_switch(node) -> None:
    """v4 -> v5: ``inputs:applyZedSim2Real`` turned from the older post-process's toggle into the camera
    model's master switch. Before v5 the camera model's effects ran whatever that toggle said, so switch it
    on: the graph keeps the camera model it had (and a graph that applied the post-process gets its
    replacement). The removed post-process inputs are dropped from the prim.
    """
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(node.get_prim_path())
    attr = prim.GetAttribute("inputs:applyZedSim2Real")
    if not attr:
        attr = prim.CreateAttribute("inputs:applyZedSim2Real", Sdf.ValueTypeNames.Bool)
    attr.Set(True)
    for name in _SIM2REAL_V4_INPUTS:
        if prim.GetAttribute(name):
            prim.RemoveProperty(name)
