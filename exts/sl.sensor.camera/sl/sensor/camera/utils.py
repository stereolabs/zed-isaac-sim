# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import carb
from typing import Optional, Tuple, List

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

# Camera configuration mapping
_CAMERA_CONFIGS = {
    "ZED_X": {"base_model": "ZED_X", "is_4mm": False, "is_stereo": True, "pixel_size": 3},
    "ZED_X_4MM": {"base_model": "ZED_X", "is_4mm": True, "is_stereo": True, "pixel_size": 3},
    "ZED_XM": {"base_model": "ZED_XM", "is_4mm": False, "is_stereo": True, "pixel_size": 3},
    "ZED_XM_4MM": {"base_model": "ZED_XM", "is_4mm": True, "is_stereo": True, "pixel_size": 3},
    "ZED_XONE_UHD": {"base_model": "ZED_XONE_UHD", "is_4mm": False, "is_stereo": False, "pixel_size": 2},
    "ZED_XONE_GS": {"base_model": "ZED_XONE_GS", "is_4mm": False, "is_stereo": False, "pixel_size": 3},
    "ZED_XONE_GS_4MM": {"base_model": "ZED_XONE_GS", "is_4mm": True, "is_stereo": False, "pixel_size": 3},
}

def get_resolution(camera_model: str, camera_resolution: str) -> Optional[List[int]]:
    """Get the resolution of the camera.

    Args:
        camera_resolution: The resolution name of the camera

    Returns:
        The resolution as [width, height] or None if not recognized
    """
    if camera_model in ["ZED_XONE_UHD"]:
        spec = _ZED_XONE_UHD_SPECIFICATIONS.get(camera_resolution)
    else:
        spec = _ZEDX_SPECIFICATIONS.get(camera_resolution)

    if spec is None:
        carb.log_warn(f"Unknown resolution '{camera_resolution}' for camera model '{camera_model}'")
    return spec["resolution"] if spec else None

def get_focal_length(camera_model: str, camera_resolution: List[int], is_4mm: bool) -> float:
    """Get the focal length for the given resolution and lens type.

    Args:
        camera_resolution: The camera resolution as [width, height]
        is_4mm: True if using 4mm lens, False for standard lens

    Returns:
        The focal length value, defaults to 741.6 if resolution not found
    """
    height = camera_resolution[1]
    
    if camera_model in ["ZED_XONE_UHD"]:
        _CAMERA_SPEC = _ZED_XONE_UHD_SPECIFICATIONS
    else:
        _CAMERA_SPEC = _ZEDX_SPECIFICATIONS

    # Find the specification by matching height
    for spec in _CAMERA_SPEC.values():
        if spec["resolution"][1] == height:
            return spec["focal_length"]["4mm" if is_4mm else "standard"]
    
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

def is_4mm_camera(camera_model: str) -> bool:
    """Check if the camera model is a 4mm variant.
    
    Args:
        camera_model: The camera model name
        
    Returns:
        True if the camera is a 4mm variant, False otherwise
    """
    config = _CAMERA_CONFIGS.get(camera_model)

    return config["is_4mm"] if config else False

def is_stereo_camera(camera_model: str) -> bool:
    """Check if the camera model supports stereo vision.
    
    Args:
        camera_model: The camera model name
        
    Returns:
        True if the camera supports stereo vision, False otherwise
    """
    config = _CAMERA_CONFIGS.get(camera_model)

    return config["is_stereo"] if config else True  # Default to stereo for unknown models

def get_pixel_size(camera_model: str) -> bool:
    """Gets the pixel size of the camera model in micrometers.
    
    Args:
        camera_model: The camera model name
        
    Returns:
        The pixel size in micrometers, defaults to 3 if not recognized
    """
    config = _CAMERA_CONFIGS.get(camera_model)

    return config["pixel_size"] if config else 3  # Default to stereo for unknown models