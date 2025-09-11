from re import S
import omni.usd
import math
import configparser
from pxr import Gf, UsdGeom

import carb

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

def write_stereo_calibration_file(left_prim_path: str, right_prim_path: str, save_path: str):
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
        carb.log_warn("Both prims are cameras")

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

    cfg['STEREO']['RX_FHD'] = f"{rel_rot[0]:.8f}"
    cfg['STEREO']['RX_SVGA'] = f"{rel_rot[0]:.8f}"
    cfg['STEREO']['RX_FHD1200'] = f"{rel_rot[0]:.8f}"

    cfg['STEREO']['RZ_FHD'] = f"{rel_rot[2]:.8f}"
    cfg['STEREO']['RZ_SVGA'] = f"{rel_rot[2]:.8f}"
    cfg['STEREO']['RZ_FHD1200'] = f"{rel_rot[2]:.8f}"

    cfg['STEREO']['SIMU'] = "1"

    # Write to file
    with open(save_path, 'w') as f:
        cfg.write(f)

    carb.log_warn(f"Stereo calibration file saved to {save_path}")
