# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import os
from enum import Enum
from typing import Dict, List, Optional

# carb is only available inside a Kit app; fall back to logging so this module
# stays importable in utilities-only mode (Isaac Lab standalone, unit tests).
try:
    import carb
    _log_warn = carb.log_warn
except ImportError:
    import logging
    _log_warn = logging.getLogger(__name__).warning


class LensType(Enum):
    """Lens fitted to a camera model.

    - WIDE: standard wide-angle lens (formerly ``is_4mm == False``)
    - NARROW: 4mm narrow-angle lens (formerly ``is_4mm == True``)
    - FISHEYE: fisheye lens (OpenCV fisheye distortion model)
    """
    WIDE = "Wide"
    NARROW = "Narrow"
    FISHEYE = "Fisheye"

# Camera specifications mapping for ZED X, ZED XM and ZED X ONE GS
_ZEDX_SPECIFICATIONS = {
    "HD1200": {
        "resolution": [1920, 1200],
        "focal_length": {"standard": 741.6, "4mm": 1272.5}
    },
    "HD1080": {
        "resolution": [1920, 1080],
        "focal_length": {"standard": 741.6, "4mm": 1272.5}
    },
    "SVGA": {
        "resolution": [960, 600],
        "focal_length": {"standard": 370.8, "4mm": 636.25}
    }
}

_ZED_XONE_S_FISHEYE_SPECIFICATIONS = {
    "HD1200": {
        "resolution": [1920, 1200],
        "focal_length": {"standard": 460},
        "optical_center": [960, 600]
    },
    "HD1080": {
        "resolution": [1920, 1080],
        "focal_length": {"standard": 460},
        "optical_center": [960, 480]
    },
    "SVGA": {
        "resolution": [960, 600],
        "focal_length": {"standard": 230},
        "optical_center": [480, 300]
    }
}

# OpenCV fisheye distortion coefficients [k1, k2, k3, k4] per camera model
_DISTORTION_COEFFICIENTS = {
    "ZED_XONE_S_FISHEYE": [0.07, 0.0061, -0.0018, -0.00037],
}

_ZED_XONE_UHD_SPECIFICATIONS = {
    "HD4K": {
        "resolution": [3856, 2180],
        "focal_length": {"standard": 1550}
    },
    "QHDPLUS": {
        "resolution": [3856, 2180],
        "focal_length": {"standard": 1550}
    },
    "HD1200": {
        "resolution": [1920, 1200],
        "focal_length": {"standard": 1550}
    },
    "HD1080": {
        "resolution": [1920, 1080],
        "focal_length": {"standard": 775}
    }
}

# ZED Mini specifications. Classic ZED SDK resolution family (HD2K/HD1080/HD720/VGA).
# Focal lengths are the rectified (pinhole) fx values from factory calibration; HD2K and
# HD1080 share fx because FHD is a crop of 2K, while HD720/VGA are downscales.
_ZED_M_SPECIFICATIONS = {
    "HD2K": {
        "resolution": [2208, 1242],
        "focal_length": {"standard": 1059.6}
    },
    "HD1080": {
        "resolution": [1920, 1080],
        "focal_length": {"standard": 1059.6}
    },
    "HD720": {
        "resolution": [1280, 720],
        "focal_length": {"standard": 529.8}
    },
    "VGA": {
        "resolution": [672, 376],
        "focal_length": {"standard": 264.9}
    }
}

# ZED 2i specifications. Classic ZED SDK resolution family (HD2K/HD1080/HD720/VGA), 120mm
# baseline, 2 um pixels. The 2.1mm (standard/Wide) lens is the same optics class as the ZED
# Mini, so its rectified fx values match the ZED_M factory values; the 4mm (Narrow) fx scales
# by the focal ratio 4.0/2.1. HD2K and HD1080 share fx (FHD is a crop of 2K); HD720/VGA are
# downscales.
_ZED_2I_SPECIFICATIONS = {
    "HD2K": {
        "resolution": [2208, 1242],
        "focal_length": {"standard": 1059.6, "4mm": 2018.5}
    },
    "HD1080": {
        "resolution": [1920, 1080],
        "focal_length": {"standard": 1059.6, "4mm": 2018.5}
    },
    "HD720": {
        "resolution": [1280, 720],
        "focal_length": {"standard": 529.8, "4mm": 1009.3}
    },
    "VGA": {
        "resolution": [672, 376],
        "focal_length": {"standard": 264.9, "4mm": 504.6}
    }
}

# Camera configuration mapping
_CAMERA_CONFIGS = {
    "ZED_X": {"base_model": "ZED_X", "lens_type": LensType.WIDE, "is_stereo": True, "pixel_size": 3, "baseline_mm": 120.0},
    "ZED_X_4MM": {"base_model": "ZED_X", "lens_type": LensType.NARROW, "is_stereo": True, "pixel_size": 3, "baseline_mm": 120.0},
    "ZED_XM": {"base_model": "ZED_XM", "lens_type": LensType.WIDE, "is_stereo": True, "pixel_size": 3, "baseline_mm": 50.0},
    "ZED_XM_4MM": {"base_model": "ZED_XM", "lens_type": LensType.NARROW, "is_stereo": True, "pixel_size": 3, "baseline_mm": 50.0},
    "ZED_X_Nano": {"base_model": "ZED_X_Nano", "lens_type": LensType.WIDE, "is_stereo": True, "pixel_size": 3, "baseline_mm": 18.0},
    # ZED X One products are separate body assets. GS and S carry a 'lens' variantSet
    # (Wide/Narrow, +Fisheye for S); each lens authors sl:cameraModel on the prim.
    # UHD has a fixed lens (no variant) and authors sl:cameraModel directly.
    "ZED_XONE_UHD": {"base_model": "ZED_XONE_UHD", "lens_type": LensType.WIDE, "is_stereo": False, "pixel_size": 2, "baseline_mm": 0.0},
    "ZED_XONE_GS": {"base_model": "ZED_XONE_GS", "lens_type": LensType.WIDE, "is_stereo": False, "pixel_size": 3, "baseline_mm": 0.0},
    "ZED_XONE_GS_4MM": {"base_model": "ZED_XONE_GS", "lens_type": LensType.NARROW, "is_stereo": False, "pixel_size": 3, "baseline_mm": 0.0},
    "ZED_XONE_S": {"base_model": "ZED_XONE_S", "lens_type": LensType.WIDE, "is_stereo": False, "pixel_size": 3, "baseline_mm": 0.0},
    "ZED_XONE_S_4MM": {"base_model": "ZED_XONE_S", "lens_type": LensType.NARROW, "is_stereo": False, "pixel_size": 3, "baseline_mm": 0.0},
    "ZED_XONE_S_FISHEYE": {"base_model": "ZED_XONE_S", "lens_type": LensType.FISHEYE, "is_stereo": False, "pixel_size": 3, "baseline_mm": 0.0},
    "ZED_M": {"base_model": "ZED_M", "lens_type": LensType.WIDE, "is_stereo": True, "pixel_size": 2, "baseline_mm": 63.0},
    # ZED 2i: fixed stereo bar, 120mm baseline. Wide (2.1mm) is standard; 4mm is the tele option.
    "ZED_2i": {"base_model": "ZED_2i", "lens_type": LensType.WIDE, "is_stereo": True, "pixel_size": 2, "baseline_mm": 120.0},
    "ZED_2i_4MM": {"base_model": "ZED_2i", "lens_type": LensType.NARROW, "is_stereo": True, "pixel_size": 2, "baseline_mm": 120.0},
}

# Resolutions supported by each camera model, in the order they should appear in
# the Resolution dropdown. This is the single source of truth shared by the OGN
# node property templates (UI filtering) and the runtime validation in annotators.py.
# It mirrors the model dispatch in get_resolution()/get_focal_length() below.
# When adding a new camera model, add its supported resolutions here.
_MODEL_ALLOWED_RESOLUTIONS = {
    "ZED_X":               ["HD1200", "HD1080", "SVGA"],
    "ZED_XM":              ["HD1200", "HD1080", "SVGA"],
    "ZED_X_4MM":           ["HD1200", "HD1080", "SVGA"],
    "ZED_XM_4MM":          ["HD1200", "HD1080", "SVGA"],
    "ZED_X_Nano":          ["HD1200", "HD1080", "SVGA"],
    "ZED_XONE_GS":         ["HD1200", "HD1080", "SVGA"],
    "ZED_XONE_GS_4MM":     ["HD1200", "HD1080", "SVGA"],
    "ZED_XONE_UHD":        ["HD4K", "QHDPLUS", "HD1200", "HD1080"],
    "ZED_XONE_S":          ["HD1200", "HD1080", "SVGA"],
    "ZED_XONE_S_4MM":      ["HD1200", "HD1080", "SVGA"],
    "ZED_XONE_S_FISHEYE":  ["HD1200", "HD1080", "SVGA"],
    "ZED_M":               ["HD2K", "HD1080", "HD720", "VGA"],
    "ZED_2i":              ["HD2K", "HD1080", "HD720", "VGA"],
    "ZED_2i_4MM":          ["HD2K", "HD1080", "HD720", "VGA"],
}

# Fallback for unknown models: the union of all known resolutions.
_DEFAULT_RESOLUTIONS = ["HD4K", "QHDPLUS", "HD1200", "HD1080", "SVGA"]

# Reverse of _CAMERA_CONFIGS: (base_model, lens_type) -> full composite token.
# Lets the UI expose base model and lens as two separate dropdowns and recompose
# the composite token (the join key used everywhere downstream) via compose_model().
_MODEL_BY_BASE_LENS = {
    (config["base_model"], config["lens_type"]): model
    for model, config in _CAMERA_CONFIGS.items()
}

# ── SDK MODEL / SIM_LENS_TYPE bridge to the C++ streaming node ────────────────
# The C++ node (OgnZEDSimCameraNode) keys its serial-number pools by the SDK
# MODEL code + SIM_LENS_TYPE reported in SimCameraInfo. The annotator sends those
# two primitives (not a composite token); the C++ simCameraModelKey() is the
# single source of truth that turns them back into a pool key. The values below
# must stay in lock-step with OgnZEDSimCameraNode.cpp (simCameraModelKey + the
# MODEL_ID_* constants) and types_c.h (SIM_LENS_TYPE).

# Sentinel model id for a custom (two-mono) virtual stereo pair. Not a real SDK
# MODEL; the C++ node routes it to the VIRTUAL_ZED_X serial path.
MODEL_ID_VIRTUAL_ZED_X = -1

# base_model -> SDK MODEL code (mirrors the switch in C++ simCameraModelKey).
_SDK_MODEL_ID = {
    "ZED_M":         1,
    "ZED_2i":        3,
    "ZED_X":         4,
    "ZED_XM":        5,
    "ZED_X_Nano":    9,
    "ZED_XONE_GS":   30,
    "ZED_XONE_S":    30,   # shares SDK MODEL 30 with the GS (same serial pool)
    "ZED_XONE_UHD":  31,
}

# LensType -> SIM_LENS_TYPE int (order must match types_c.h / the C++ enum:
# WIDE=0, NARROW=1, FISHEYE=2).
_SIM_LENS_TYPE_ID = {
    LensType.WIDE:    0,
    LensType.NARROW:  1,
    LensType.FISHEYE: 2,
}

# Preferred default resolution per camera model. Used to pick a valid value when
# a node is created or its model is changed to one that does not support the
# currently selected resolution. Any model not listed here defaults to the default
#  value of the resolution attribute in the OGN node property template (``ogn_default``).
_MODEL_DEFAULT_RESOLUTION = {
    "ZED_XONE_UHD": "HD1200",
    "ZED_M": "HD720",
    "ZED_2i": "HD720",
    "ZED_2i_4MM": "HD720",
}


def get_allowed_resolutions(camera_model: str) -> List[str]:
    """Get the list of resolutions supported by a camera model.

    Args:
        camera_model: The camera model name

    Returns:
        Supported resolution names, in display order. Falls back to the union of
        all known resolutions for unrecognized models.
    """
    return _MODEL_ALLOWED_RESOLUTIONS.get(camera_model, _DEFAULT_RESOLUTIONS)


def is_resolution_valid(camera_model: str, resolution: str) -> bool:
    """Check whether a resolution is supported by a camera model.

    Args:
        camera_model: The camera model name
        resolution: The resolution name to check

    Returns:
        True if the resolution is supported by the model, False otherwise
    """
    return resolution in get_allowed_resolutions(camera_model)


def get_default_resolution(camera_model: str, ogn_default: Optional[str] = None) -> Optional[str]:
    """Get the preferred default resolution for a camera model.

    Resolution order of preference:
      1. An explicit entry in _MODEL_DEFAULT_RESOLUTION for the model.
      2. The node's OGN-authored default (``ogn_default``), if it is supported by
         the model.
      3. The first supported resolution for the model.

    Args:
        camera_model: The camera model name
        ogn_default: The resolution attribute's OGN default value, if known

    Returns:
        The chosen default resolution, or None if the model has none.
    """
    explicit = _MODEL_DEFAULT_RESOLUTION.get(camera_model)
    if explicit is not None:
        return explicit
    allowed = get_allowed_resolutions(camera_model)
    if ogn_default and ogn_default in allowed:
        return ogn_default
    return allowed[0] if allowed else None


def get_base_models(stereo_only: bool = False) -> List[str]:
    """Get the distinct base camera model names, in declaration order.

    Base models are what the "Camera Model" dropdown offers once the lens is
    split out into its own input (e.g. ZED_X, ZED_XM, ZED_XONE_S), as opposed to
    the composite tokens returned by :func:`get_supported_models` (e.g. ZED_X_4MM).

    Args:
        stereo_only: When True, return only stereo base models

    Returns:
        The base model names, de-duplicated, preserving _CAMERA_CONFIGS order
    """
    bases = []
    for config in _CAMERA_CONFIGS.values():
        if stereo_only and not config["is_stereo"]:
            continue
        base = config["base_model"]
        if base not in bases:
            bases.append(base)
    return bases


def get_allowed_lens_types(base_model: str) -> List[str]:
    """Get the lens types available for a base camera model, in display order.

    Args:
        base_model: The base camera model name (see :func:`get_base_models`)

    Returns:
        The supported lens type values (LensType.value strings). Falls back to
        [LensType.WIDE.value] for unrecognized base models.
    """
    lenses = [
        config["lens_type"].value
        for config in _CAMERA_CONFIGS.values()
        if config["base_model"] == base_model
    ]
    return lenses if lenses else [LensType.WIDE.value]


def get_default_lens_type(base_model: str, ogn_default: Optional[str] = None) -> str:
    """Get the preferred default lens type for a base camera model.

    Used to snap the lens selection to a valid value when a node is created or its
    base model changes to one that does not offer the currently selected lens.

    Args:
        base_model: The base camera model name
        ogn_default: The lens attribute's OGN default value, if known

    Returns:
        The OGN default when the model supports it, else its first supported lens
    """
    allowed = get_allowed_lens_types(base_model)
    if ogn_default and ogn_default in allowed:
        return ogn_default
    return allowed[0]


def compose_model(base_model: str, lens_type: str) -> str:
    """Recompose the composite camera model token from a base model and lens.

    Inverse of :func:`get_camera_model` / :func:`get_lens_type`. The composite
    token is the join key used by the spec/config lookups, annotators.py and the
    C++ node, so the split base/lens UI inputs are recombined through this before
    reaching that layer.

    Args:
        base_model: The base camera model name (e.g. "ZED_X")
        lens_type: The lens type value (LensType.value, e.g. "Narrow")

    Returns:
        The composite token (e.g. "ZED_X_4MM"). Falls back to base_model when the
        (base, lens) pair is unknown, so a transiently invalid lens stays usable.
    """
    try:
        lens_enum = LensType(lens_type)
    except ValueError:
        return base_model
    return _MODEL_BY_BASE_LENS.get((base_model, lens_enum), base_model)


# Maps a camera model to its resolution/focal-length specification dictionary.
# Models not listed use the ZED X family specs (_ZEDX_SPECIFICATIONS). Keyed on the
# full model token (not base_model) because ZED_XONE_S_FISHEYE and ZED_XONE_S share a
# base_model but need different specs. Add new families (e.g. ZED 2i) here.
_SPECIFICATIONS_BY_MODEL = {
    "ZED_XONE_UHD":       _ZED_XONE_UHD_SPECIFICATIONS,
    "ZED_XONE_S_FISHEYE": _ZED_XONE_S_FISHEYE_SPECIFICATIONS,
    "ZED_M":              _ZED_M_SPECIFICATIONS,
    "ZED_2i":             _ZED_2I_SPECIFICATIONS,
    "ZED_2i_4MM":         _ZED_2I_SPECIFICATIONS,
}


def _get_spec_dict(camera_model: str) -> dict:
    """Get the specification dictionary for a camera model (defaults to ZED X family)."""
    return _SPECIFICATIONS_BY_MODEL.get(camera_model, _ZEDX_SPECIFICATIONS)


def get_resolution(camera_model: str, camera_resolution: str) -> Optional[List[int]]:
    """Get the resolution of the camera.

    Args:
        camera_resolution: The resolution name of the camera

    Returns:
        The resolution as [width, height] or None if not recognized
    """
    spec = _get_spec_dict(camera_model).get(camera_resolution)

    if spec is None:
        _log_warn(f"Unknown resolution '{camera_resolution}' for camera model '{camera_model}'")
    return spec["resolution"] if spec else None

def get_focal_length(camera_model: str, camera_resolution: List[int], lens_type: LensType) -> float:
    """Get the focal length for the given resolution and lens type.

    Args:
        camera_resolution: The camera resolution as [width, height]
        lens_type: The lens fitted to the camera (see LensType)

    Returns:
        The focal length value, defaults to 741.6 if resolution not found
    """
    height = camera_resolution[1]

    # Only the narrow (4mm) lens uses the dedicated "4mm" focal length; the wide
    # and fisheye lenses use the "standard" focal length of their spec.
    focal_key = "4mm" if lens_type == LensType.NARROW else "standard"

    # Find the specification by matching height
    for spec in _get_spec_dict(camera_model).values():
        if spec["resolution"][1] == height:
            return spec["focal_length"][focal_key]

    # Default fallback
    return 741.6

def get_camera_model(camera_model: str) -> str:
    """Get the base camera model name from the full camera model name.

    Args:
        camera_model: The full camera model name

    Returns:
        The base camera model, defaults to "ZED_X" if not recognized
    """
    config = _CAMERA_CONFIGS.get(camera_model)
    if config is None:
        return "ZED_X"

    return config["base_model"]

# Attribute authored by the ZED_XONE 'lens' variantSet to name the selected lens.
# Lets a single placed asset drive the streamed camera model from its lens variant.
SL_CAMERA_MODEL_ATTR = "sl:cameraModel"

# Maps a camera model to the 'lens' variant that selects its optic + sl:cameraModel
# on a shared-body variant asset. Only models served by a variant asset appear here;
# single-lens assets (ZED_M, ZED_X, ...) are absent and need no selection.
_LENS_VARIANT = {
    "ZED_XONE_S":         "Wide",
    "ZED_XONE_S_4MM":     "Narrow",
    "ZED_XONE_S_FISHEYE": "Fisheye",
    "ZED_XONE_GS":        "Wide",
    "ZED_XONE_GS_4MM":    "Narrow",
    # ZED_XONE_UHD is a fixed-lens product (no variantSet) -> absent here.
}

def get_lens_variant(camera_model: str) -> Optional[str]:
    """Get the 'lens' variant name that a shared-body asset should select for a model.

    Args:
        camera_model: The camera model name

    Returns:
        The variant name (e.g. "Fisheye"), or None if the model uses a single-lens asset
    """
    return _LENS_VARIANT.get(camera_model)

def resolve_camera_model(stage, target_prim_path: str, fallback):
    """Resolve the effective composite camera model for a placed ZED asset.

    Derives the model + lens from the asset itself so the user never has to set
    them by hand, using (in priority order):

    1. An authored ``sl:cameraModel`` anywhere in the subtree - the ZED X One lens
       variants author this, so it stays the explicit source of truth.
    2. The first prim carrying a ``lens`` variantSet: the base model is that prim's
       name (``base_link/<base>``) and the lens is the variant selection
       (Wide/Narrow/Fisheye). This is what makes the stereo lens functional.
    3. The first prim whose name is a known base model, for single-lens assets that
       have no ``lens`` variantSet (ZED_M, ZED_X_Nano, ZED_XONE_UHD) -> Wide.
    4. ``fallback`` when nothing resolves.

    Args:
        stage: The USD stage
        target_prim_path: The prim the streamer node targets (the placed asset root)
        fallback: Model to return when the asset yields nothing (may be None)

    Returns:
        The resolved composite camera model token, or ``fallback``
    """
    if stage is None or not target_prim_path:
        return fallback
    from pxr import Usd
    root = stage.GetPrimAtPath(target_prim_path)
    if not root or not root.IsValid():
        return fallback

    # 1) Explicit sl:cameraModel wins (ZED X One variants author it).
    for prim in Usd.PrimRange(root):
        attr = prim.GetAttribute(SL_CAMERA_MODEL_ATTR)
        if attr and attr.HasAuthoredValue():
            value = attr.Get()
            if value:
                return str(value)

    base_models = set(get_base_models())

    # 2) Derive base (prim name) + lens (variant selection) from the asset. Must
    #    run before the bare name match (3) so the variantSet-carrying
    #    base_link/<base> prim wins over any same-named ancestor.
    for prim in Usd.PrimRange(root):
        if prim.GetName() not in base_models:
            continue
        vsets = prim.GetVariantSets()
        if "lens" not in vsets.GetNames():
            continue
        lens = vsets.GetVariantSet("lens").GetVariantSelection() or LensType.WIDE.value
        composite = compose_model(prim.GetName(), lens)
        if composite in _CAMERA_CONFIGS:
            return composite

    # 3) Single-lens asset (no variantSet): the prim name is the model, Wide only.
    for prim in Usd.PrimRange(root):
        if prim.GetName() in base_models:
            return compose_model(prim.GetName(), LensType.WIDE.value)

    return fallback

def get_lens_type(camera_model: str) -> LensType:
    """Get the lens type fitted to the camera model.

    Args:
        camera_model: The camera model name

    Returns:
        The LensType of the model, defaults to LensType.WIDE if not recognized
    """
    config = _CAMERA_CONFIGS.get(camera_model)

    return config["lens_type"] if config else LensType.WIDE

def get_sdk_model_id(base_model: str) -> int:
    """SDK MODEL code for a base camera model, sent to the C++ streaming node.

    Args:
        base_model: The base camera model name (see :func:`get_base_models`)

    Returns:
        The SDK MODEL code; defaults to ZED_X (4) for unrecognized models.
    """
    return _SDK_MODEL_ID.get(base_model, _SDK_MODEL_ID["ZED_X"])

def get_sim_lens_type_id(lens_type: LensType) -> int:
    """SIM_LENS_TYPE int for a lens, sent to the C++ streaming node.

    Args:
        lens_type: The LensType fitted to the camera

    Returns:
        0 (Wide), 1 (Narrow) or 2 (Fisheye); defaults to Wide.
    """
    return _SIM_LENS_TYPE_ID.get(lens_type, 0)

def is_stereo_camera(camera_model: str) -> bool:
    """Check if the camera model supports stereo vision.

    Args:
        camera_model: The camera model name

    Returns:
        True if the camera supports stereo vision, False otherwise
    """
    config = _CAMERA_CONFIGS.get(camera_model)

    return config["is_stereo"] if config else True  # Default to stereo for unknown models

def get_distortion_coefficients(camera_model: str) -> Optional[List[float]]:
    """Get the OpenCV fisheye distortion coefficients of the camera model.

    Args:
        camera_model: The camera model name

    Returns:
        The [k1, k2, k3, k4] coefficients, or None for undistorted (pinhole) models
    """
    return _DISTORTION_COEFFICIENTS.get(camera_model)

def get_optical_center(camera_model: str, camera_resolution: List[int]) -> List[float]:
    """Get the optical center (cx, cy) for the given camera model and resolution.

    Args:
        camera_model: The camera model name
        camera_resolution: The camera resolution as [width, height]

    Returns:
        The optical center as [cx, cy], defaults to the image center
    """
    for spec in _get_spec_dict(camera_model).values():
        if spec["resolution"][1] == camera_resolution[1] and "optical_center" in spec:
            return spec["optical_center"]

    return [camera_resolution[0] / 2, camera_resolution[1] / 2]

def get_pixel_size(camera_model: str) -> int:
    """Gets the pixel size of the camera model in micrometers.

    Args:
        camera_model: The camera model name

    Returns:
        The pixel size in micrometers, defaults to 3 if not recognized
    """
    config = _CAMERA_CONFIGS.get(camera_model)

    return config["pixel_size"] if config else 3

def get_baseline(camera_model: str) -> float:
    """Gets the stereo baseline of the camera model in millimeters.

    Args:
        camera_model: The camera model name

    Returns:
        The baseline in millimeters, defaults to 120.0 if not recognized
    """
    config = _CAMERA_CONFIGS.get(camera_model)

    return config["baseline_mm"] if config else 120.0

def get_supported_models(stereo_only: bool = False) -> List[str]:
    """Get the supported camera model names.

    Args:
        stereo_only: When True, return only stereo models

    Returns:
        The camera model names (keys of the camera configuration mapping)
    """
    return [model for model, config in _CAMERA_CONFIGS.items()
            if config["is_stereo"] or not stereo_only]

def get_supported_resolutions(camera_model: Optional[str] = None) -> List[str]:
    """Get the supported resolution names.

    Args:
        camera_model: The camera model name, or None for the union of all models

    Returns:
        The resolution names accepted by :func:`get_resolution` for that model
    """
    if camera_model is not None:
        return list(_get_spec_dict(camera_model).keys())

    resolutions = []
    for spec in (*_SPECIFICATIONS_BY_MODEL.values(), _ZEDX_SPECIFICATIONS):
        for name in spec:
            if name not in resolutions:
                resolutions.append(name)
    return resolutions

def get_camera_subpaths(camera_model: str = "ZED_X") -> Dict[str, str]:
    """Get the camera/IMU prim subpaths inside the ZED USD, relative to the model root.

    Args:
        camera_model: The camera model name

    Returns:
        A dict with keys:
        - "left": the left camera for stereo models, the mono camera otherwise
        - "right": the right camera (stereo models only)
        - "mono": the mono camera path ("base_link/<base>/Camera")
        - "imu": the IMU sensor
    """
    base = get_camera_model(camera_model)
    root = f"base_link/{base}"
    subpaths = {"mono": f"{root}/Camera", "imu": f"{root}/Imu_Sensor"}
    if is_stereo_camera(camera_model):
        subpaths["left"] = f"{root}/CameraLeft"
        subpaths["right"] = f"{root}/CameraRight"
    else:
        subpaths["left"] = subpaths["mono"]
    return subpaths

def get_camera_paths(root_prim_path: str, camera_model: str = "ZED_X") -> Dict[str, str]:
    """Get the absolute camera/IMU prim paths of a ZED model referenced in a stage.

    Pure string joining - regex roots such as "/World/envs/env_.*/ZED_X" work too.

    Args:
        root_prim_path: The prim path where the ZED USD is referenced (the model root)
        camera_model: The camera model name

    Returns:
        A dict with the same keys as :func:`get_camera_subpaths`, as absolute paths
    """
    root = root_prim_path.rstrip("/")
    return {key: f"{root}/{subpath}" for key, subpath in get_camera_subpaths(camera_model).items()}

def get_camera_usd_path(camera_model: str = "ZED_X") -> Optional[str]:
    """Get the absolute path of the USD asset shipped for a camera model.

    Args:
        camera_model: The camera model name

    Returns:
        The absolute path to data/usd/<base_model>.usdc, or None if the model
        has no USD asset
    """
    base = get_camera_model(camera_model)
    ext_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    usd_path = os.path.join(ext_root, "data", "usd", f"{base}.usdc")
    if not os.path.isfile(usd_path):
        _log_warn(f"No USD asset for camera model '{camera_model}' (expected {usd_path})")
        return None
    return usd_path

def get_camera_thumbnail_path(camera_model: str = "ZED_X") -> Optional[str]:
    """Get the absolute path of the thumbnail shipped for a camera model.

    Args:
        camera_model: The camera model name

    Returns:
        The absolute path to data/usd/.thumbs/256x256/<base_model>.usdc.png, or
        None if the model has no thumbnail
    """
    base = get_camera_model(camera_model)
    ext_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    thumb_path = os.path.join(ext_root, "data", "usd", ".thumbs", "256x256", f"{base}.usdc.png")
    return thumb_path if os.path.isfile(thumb_path) else None

def find_placed_zed_cameras(stage) -> List[Dict]:
    """Find the ZED cameras placed in a stage.

    A placed ZED asset is identified by the streaming contract: it exposes
    ``<root>/base_link/<base_model>/...``, so any prim named after a known base
    model whose parent is ``base_link`` is a placed camera's model prim (the prim
    that hosts the ``lens`` variantSet on interchangeable-lens assets).

    Args:
        stage: The USD stage to scan

    Returns:
        One dict per placed camera, in stage traversal order, with keys:
        - "root_path": the asset root prim path (the streamer's target prim)
        - "model_prim_path": the ``base_link/<base_model>`` prim path
        - "base_model": the base camera model name (e.g. "ZED_XONE_S")
        - "lens_variants": the 'lens' variant names, [] for fixed-lens assets
        - "current_lens": the current 'lens' variant selection, None if fixed
        - "is_stereo": whether the model is a stereo camera
    """
    if stage is None:
        return []
    base_models = set(get_base_models())
    cameras = []
    for prim in stage.Traverse():
        if prim.GetName() not in base_models:
            continue
        parent = prim.GetParent()
        if not parent or parent.GetName() != "base_link":
            continue
        root = parent.GetParent()
        variants, current = [], None
        vsets = prim.GetVariantSets()
        if "lens" in vsets.GetNames():
            vset = vsets.GetVariantSet("lens")
            variants = vset.GetVariantNames()
            current = vset.GetVariantSelection() or None
        cameras.append({
            "root_path": root.GetPath().pathString if root else parent.GetPath().pathString,
            "model_prim_path": prim.GetPath().pathString,
            "base_model": prim.GetName(),
            "lens_variants": variants,
            "current_lens": current,
            "is_stereo": is_stereo_camera(prim.GetName()),
        })
    return cameras

def get_pinhole_parameters(camera_model: str, camera_resolution: str) -> Optional[Dict]:
    """Get the pinhole camera parameters for a model + resolution name.

    Bundles the spec tables into the quantities a render camera needs (e.g.
    Isaac Lab's PinholeCameraCfg takes focal length and apertures in mm).

    Args:
        camera_model: The camera model name
        camera_resolution: The resolution name (see :func:`get_supported_resolutions`)

    Returns:
        A dict with width, height, focal_length_px, pixel_size_mm, focal_length_mm,
        horizontal_aperture_mm, vertical_aperture_mm, baseline_m and optical_center
        [cx, cy], or None if the resolution is unknown for that model
    """
    resolution = get_resolution(camera_model, camera_resolution)
    if resolution is None:
        return None
    width, height = resolution
    focal_px = get_focal_length(camera_model, resolution, get_lens_type(camera_model))
    pixel_mm = get_pixel_size(camera_model) * 1e-3
    return {
        "width": width,
        "height": height,
        "focal_length_px": focal_px,
        "pixel_size_mm": pixel_mm,
        "focal_length_mm": focal_px * pixel_mm,
        "horizontal_aperture_mm": pixel_mm * width,
        "vertical_aperture_mm": pixel_mm * height,
        "baseline_m": get_baseline(camera_model) * 1e-3,
        "optical_center": get_optical_center(camera_model, resolution),
    }