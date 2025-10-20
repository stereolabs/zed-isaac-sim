from re import S
import omni.usd
import math
import configparser
from pxr import Gf, UsdGeom
import platform
import carb
import random
from typing import Tuple

def quat_to_rodrigues(quat: Gf.Quatd):
    """
    Converts a quaternion to a Rodrigues rotation vector (3D vector)
    """
    angle = 2.0 * math.acos(quat.GetReal())  # rotation angle
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


def get_camera_config(camera_model: str) -> Tuple[str, bool]:
    """
    Returns configuration parameters for a given camera model.

    Args:
        camera_model (str): The name of the camera model.

    Returns:
        Tuple[int, bool]: (fps, is_small_sensor)
    """
    camera_configs = {
        "ZED_XONE_GS": ("30", False),
        "ZED_XS_GS_4MM": ("30", True),
        "ZED_XONE_UHD": ("31", False),
    }

    if camera_model not in camera_configs:
        carb.log_warn(f"Unknown camera model '{camera_model}', defaulting to ZED_XONE_GS")
    
    # Use get() to gracefully handle unknown models
    return camera_configs.get(camera_model, camera_configs["ZED_XONE_GS"])

def write_stereo_calibration_file(left_prim_path: str, right_prim_path: str, serial_number: str, camera_model:str):
    """
    Computes the relative transform between left and right camera prims
    and writes a stereo calibration file.
    """
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        carb.log_warn("No stage loaded")
        return

    left_prim = stage.GetPrimAtPath(left_prim_path)
    right_prim = stage.GetPrimAtPath(right_prim_path)
    if not left_prim or not right_prim:
        carb.log_warn("Invalid prim paths")
        return

    is_camera = False
    if left_prim.IsA(UsdGeom.Camera) and right_prim.IsA(UsdGeom.Camera):
        is_camera = True

    # Choose conversion matrix based on prim type
    if is_camera:
        # Camera prim: -Z forward, Y up → image frame X right, Y down, Z forward
        sim_to_image = Gf.Matrix4d(
            1, 0, 0, 0,    # newX = oldX
            0, 0, -1, 0,   # newY = -oldZ
            0, 1, 0, 0,    # newZ = oldY
            0, 0, 0, 1
        )
    else:
        # Generic prim: X forward, Y left, Z up → image frame X right, Y down, Z forward
        sim_to_image = Gf.Matrix4d(
            0, -1, 0, 0,   # newX = -oldY  (USD Y left → image X right)
            0,  0, -1, 0,  # newY = -oldZ  (USD Z up   → image Y down)
            1,  0, 0, 0,   # newZ =  oldX  (USD X fwd → image Z fwd)
            0,  0, 0, 1
        )

    image_to_sim = sim_to_image.GetInverse()

    # Get transforms
    left_xform = UsdGeom.Xformable(left_prim).ComputeLocalToWorldTransform(0.0)  # time=0.0
    right_xform = UsdGeom.Xformable(right_prim).ComputeLocalToWorldTransform(0.0)

    relative = right_xform * left_xform.GetInverse()
    relative_img = sim_to_image * relative * sim_to_image.GetInverse()

    if left_xform is None or right_xform is None:
        carb.log_warn("Prims do not have transform attributes")
        return

    # Convert USD GfMatrix4d to translation + rotation (Euler)
    def decompose_gf_matrix(mat):
        # mat is a Gf.Matrix4d
        translation = mat.ExtractTranslation()
        rotation =  quat_to_rodrigues(mat.ExtractRotationQuat()) 
        return translation, rotation

    rel_trans, rel_rot = decompose_gf_matrix(relative_img)
    # Create config file
    cfg = configparser.ConfigParser()
    cfg['STEREO'] = {}
    cfg['STEREO']['Baseline'] = f"{(rel_trans[0] * 1000):.6f}"
    cfg['STEREO']['TY'] = f"{-rel_trans[1]:.6f}"
    cfg['STEREO']['TZ'] = f"{rel_trans[2]:.6f}"

    cfg['STEREO']['CV_FHD'] = f"{rel_rot[1]:.8f}"
    cfg['STEREO']['CV_SVGA'] = f"{rel_rot[1]:.8f}"
    cfg['STEREO']['CV_FHD1200'] = f"{rel_rot[1]:.8f}"
    cfg['STEREO']['CV_QHDPLUS'] = f"{rel_rot[1]:.8f}"

    cfg['STEREO']['RX_FHD'] = f"{rel_rot[0]:.8f}"
    cfg['STEREO']['RX_SVGA'] = f"{rel_rot[0]:.8f}"
    cfg['STEREO']['RX_FHD1200'] = f"{rel_rot[0]:.8f}"
    cfg['STEREO']['RX_QHDPLUS'] = f"{rel_rot[0]:.8f}"

    cfg['STEREO']['RZ_FHD'] = f"{rel_rot[2]:.8f}"
    cfg['STEREO']['RZ_SVGA'] = f"{rel_rot[2]:.8f}"
    cfg['STEREO']['RZ_FHD1200'] = f"{rel_rot[2]:.8f}"
    cfg['STEREO']['RZ_QHDPLUS'] = f"{rel_rot[2]:.8f}"

    # auto detect camera model based on prim path 

    cam_model, is_4mm = get_camera_config(camera_model)
    cfg['SIM'] = {}
    cfg['SIM']['is_4mm'] = "1" if is_4mm else "0"
    cfg['SIM']['camera_model'] = cam_model

    # Write to file
    full_path = get_calibration_file_path() + f"SN{serial_number}.conf"

    with open(full_path, 'w') as f:
        cfg.write(f)

    carb.log_warn(f"Stereo calibration file saved to {full_path}")
