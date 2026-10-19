# SPDX-FileCopyrightText: Copyright (c) 2023-2026 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
import omni.usd
import math
import configparser
from pxr import Gf, UsdGeom
import platform
import carb
import random

from sl.sensor.camera.utils import (LensType, get_base_models, get_camera_model, get_distortion_coefficients,
                                    get_lens_type, get_sdk_model_id, get_sim_lens_type_id, is_stereo_camera)


def quat_to_rodrigues(quat: Gf.Quatd):
    """
    Converts a quaternion to a Rodrigues rotation vector (3D vector)
    """
    # q and -q are the same rotation; the one with a non-negative real part gives the short angle
    if quat.GetReal() < 0.0:
        quat = -quat
    angle = 2.0 * math.acos(min(1.0, quat.GetReal()))
    sin_half_angle = math.sqrt(1 - quat.GetReal()**2)

    # If angle is very small, rotation axis is undefined, use zero
    if sin_half_angle < 1e-8:
        return Gf.Vec3d(0, 0, 0)

    axis = Gf.Vec3d(quat.GetImaginary()[0], quat.GetImaginary()[1], quat.GetImaginary()[2])
    rodrigues = axis * (angle / sin_half_angle)
    return rodrigues

def get_calibration_file_path():
    system = platform.system()

    if system == "Windows":
        path = "C:/ProgramData/Stereolabs/settings/"
    elif system == "Linux":
        path = "/usr/local/zed/settings/"
    else:
        path = ""

    return path

RANDOM_SN_START_VALUE = 110_000_001
RANDOM_SN_STOP_VALUE = 119_999_999

def generate_virtual_sn() -> int:
    """Generate a random serial number within the defined range."""
    return random.randint(RANDOM_SN_START_VALUE, RANDOM_SN_STOP_VALUE)


def get_mono_base_models() -> list:
    """The base camera models the exporter offers: the mono ZED X One family, in display order."""
    return [base for base in get_base_models() if not is_stereo_camera(base)]


def write_stereo_calibration_file(left_prim_path: str, right_prim_path: str, serial_number: str, camera_model:str):
    """
    Computes the relative transform between left and right camera prims
    and writes a stereo calibration file.
    """
    # Real cameras' calibrations live in the same folder, so only a virtual serial is accepted.
    serial_number = str(serial_number).strip()
    if not serial_number.isdigit() or not RANDOM_SN_START_VALUE <= int(serial_number) <= RANDOM_SN_STOP_VALUE:
        carb.log_error(f"[ZED] Invalid serial number '{serial_number}': a virtual stereo camera needs one "
                       f"from {RANDOM_SN_START_VALUE} to {RANDOM_SN_STOP_VALUE}.")
        return

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        carb.log_warn("[ZED] No stage loaded")
        return

    left_prim = stage.GetPrimAtPath(left_prim_path)
    right_prim = stage.GetPrimAtPath(right_prim_path)
    if not left_prim or not right_prim:
        carb.log_warn("[ZED] Invalid prim paths")
        return

    # Rows are the image frame axes (x right, y down, z forward) expressed in the prim's frame.
    if left_prim.IsA(UsdGeom.Camera) and right_prim.IsA(UsdGeom.Camera):
        # USD camera: x right, y up, looking down -z
        image_to_prim = Gf.Matrix4d(
            1, 0, 0, 0,
            0, -1, 0, 0,
            0, 0, -1, 0,
            0, 0, 0, 1
        )
    else:
        # generic prim: x forward, y left, z up
        image_to_prim = Gf.Matrix4d(
            0, -1, 0, 0,
            0, 0, -1, 0,
            1, 0, 0, 0,
            0, 0, 0, 1
        )

    # rigid part only, so an asset's scale does not scale the baseline
    left_xform = UsdGeom.Xformable(left_prim).ComputeLocalToWorldTransform(0.0).RemoveScaleShear()
    right_xform = UsdGeom.Xformable(right_prim).ComputeLocalToWorldTransform(0.0).RemoveScaleShear()

    # pose of the right eye in the left eye's image frame
    right_in_left = image_to_prim * (right_xform * left_xform.GetInverse()) * image_to_prim.GetInverse()

    # The SDK reads the file as OpenCV's stereo extrinsics, T = (-Baseline, TY, TZ) and
    # R = (RX, CV, RZ), which map a point from the left eye frame into the right one: the
    # inverse of the right eye's pose. Baseline, TY and TZ are in millimeters.
    left_to_right = right_in_left.GetInverse()
    rel_trans = left_to_right.ExtractTranslation() * UsdGeom.GetStageMetersPerUnit(stage) * 1000.0
    rel_rot = quat_to_rodrigues(left_to_right.ExtractRotationQuat())

    cfg = configparser.ConfigParser()
    cfg['STEREO'] = {}
    cfg['STEREO']['Baseline'] = f"{-rel_trans[0]:.6f}"
    cfg['STEREO']['TY'] = f"{rel_trans[1]:.6f}"
    cfg['STEREO']['TZ'] = f"{rel_trans[2]:.6f}"

    cfg['STEREO']['CV_FHD'] = f"{rel_rot[1]:.8f}"
    cfg['STEREO']['CV_SVGA'] = f"{rel_rot[1]:.8f}"
    cfg['STEREO']['CV_FHD1200'] = f"{rel_rot[1]:.8f}"
    cfg['STEREO']['CV_QHDPLUS'] = f"{rel_rot[1]:.8f}"
    cfg['STEREO']['CV_4K'] = f"{rel_rot[1]:.8f}"

    cfg['STEREO']['RX_FHD'] = f"{rel_rot[0]:.8f}"
    cfg['STEREO']['RX_SVGA'] = f"{rel_rot[0]:.8f}"
    cfg['STEREO']['RX_FHD1200'] = f"{rel_rot[0]:.8f}"
    cfg['STEREO']['RX_QHDPLUS'] = f"{rel_rot[0]:.8f}"
    cfg['STEREO']['RX_4K'] = f"{rel_rot[0]:.8f}"

    cfg['STEREO']['RZ_FHD'] = f"{rel_rot[2]:.8f}"
    cfg['STEREO']['RZ_SVGA'] = f"{rel_rot[2]:.8f}"
    cfg['STEREO']['RZ_FHD1200'] = f"{rel_rot[2]:.8f}"
    cfg['STEREO']['RZ_QHDPLUS'] = f"{rel_rot[2]:.8f}"
    cfg['STEREO']['RZ_4K'] = f"{rel_rot[2]:.8f}"

    lens_type = get_lens_type(camera_model)
    cfg['SIM'] = {}
    cfg['SIM']['lens_type'] = str(get_sim_lens_type_id(lens_type))
    cfg['SIM']['camera_model'] = str(get_sdk_model_id(get_camera_model(camera_model)))

    # Fisheye cameras carry OpenCV fisheye distortion coefficients
    if lens_type == LensType.FISHEYE:
        disto = get_distortion_coefficients(camera_model)
        if disto:
            cfg['LEFT_DISTO'] = {}
            cfg['LEFT_DISTO']['k1'] = f"{disto[0]}"
            cfg['LEFT_DISTO']['k2'] = f"{disto[1]}"
            cfg['LEFT_DISTO']['k3'] = f"{disto[2]}"
            cfg['LEFT_DISTO']['k4'] = f"{disto[3]}"

            cfg['RIGHT_DISTO'] = {}
            cfg['RIGHT_DISTO']['k1'] = f"{disto[0]}"
            cfg['RIGHT_DISTO']['k2'] = f"{disto[1]}"
            cfg['RIGHT_DISTO']['k3'] = f"{disto[2]}"
            cfg['RIGHT_DISTO']['k4'] = f"{disto[3]}"
        else:
            carb.log_warn(f"[ZED] No fisheye distortion coefficients for model '{camera_model}'")

    full_path = get_calibration_file_path() + f"SN{serial_number}.conf"

    try:
        with open(full_path, 'w') as f:
            cfg.write(f)
    except OSError as exc:
        carb.log_error(f"[ZED] Could not write the stereo calibration file {full_path}: {exc}")
        return

    carb.log_warn(f"[ZED] Stereo calibration file saved to {full_path}")
