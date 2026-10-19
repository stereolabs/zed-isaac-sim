import numpy as np
import cv2
import json
import os
import tempfile
import omni.usd
from pxr import Usd, UsdGeom, Gf
from sl.sensor.camera.utils import get_camera_paths, resolve_camera_model

# ZED asset prims to export, in streaming-port order: the i-th one streams on BASE_PORT + 2 * i.
PRIM_NAMES = [f"/World/ZED_X_{i:02}" for i in range(1, 8)]
BASE_PORT = 30000
# ZED Fusion matches each entry to its stream by serial number: replace these with the serial
# numbers the cameras actually stream (logged when streaming starts).
SERIALS = {prim_path: f"1234567{prim_path[-1]}" for prim_path in PRIM_NAMES}
OUTPUT_PATH = os.path.join(tempfile.gettempdir(), "zed_fusion_poses.json")
# ZED Fusion takes the pose of the ZED SDK camera frame, which sits on the left camera. USD cameras look
# down -Z with +Y up: this (Gf row-vector) matrix re-expresses the camera prim's frame as X forward,
# Y left, Z up, the body frame the conversion to ZED's IMAGE coordinate system below expects.
BODY_TO_CAMERA = Gf.Matrix4d(0, 0, -1, 0,
                             -1, 0, 0, 0,
                             0, 1, 0, 0,
                             0, 0, 0, 1)

stage = omni.usd.get_context().get_stage()
print("[ZED] get stage")
print("[ZED] prim_names:", PRIM_NAMES)
output_data = {}

for i, prim_path in enumerate(PRIM_NAMES):
    print("[ZED] Processing prim:", prim_path)
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        continue

    # Left camera of a stereo model, the single camera of a ZED X One.
    camera_model = resolve_camera_model(stage, prim_path, "ZED_X")
    camera_path = get_camera_paths(prim_path, camera_model)["left"]
    camera_prim = stage.GetPrimAtPath(camera_path)
    if not camera_prim.IsValid():
        print("[ZED] No left camera prim at:", camera_path)
        continue

    xform = UsdGeom.Xformable(camera_prim)
    # The ZED X Mini's model prim carries a 0.01 scale: keep only rotation and translation.
    local_to_world = BODY_TO_CAMERA * xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default()).RemoveScaleShear()

    # ZED Fusion reads meters; the stage may use other units.
    translation = local_to_world.ExtractTranslation() * UsdGeom.GetStageMetersPerUnit(stage)
    rotation_matrix = local_to_world.ExtractRotationMatrix()
    print("[ZED] Translation:", translation)
    print("[ZED] Rotation Matrix:", rotation_matrix)

    rotation, _ = cv2.Rodrigues(np.array(rotation_matrix))
    print("[ZED] Rotation Vector:", rotation.ravel())

    output_data[SERIALS[prim_path]] = {
        "input": {
            "zed": {
                "type": "STREAM",
                "configuration": f"127.0.0.1:{BASE_PORT + 2 * i}"
            },
            "fusion": {
                "type": "INTRA_PROCESS"
            }
        },
        "world": {
            "rotation": [
                rotation[1][0],
                rotation[2][0],
                -rotation[0][0]
            ],
            "translation": [
                -translation[1],
                -translation[2],
                translation[0],
            ],
            "override_gravity": True,
        }
    }

print(f"[ZED] Fusion JSON configuration: {json.dumps(output_data)}")

with open(OUTPUT_PATH, "w") as f:
    json.dump(output_data, f, indent=4)

print(f"[ZED] Fusion JSON configuration saved to {OUTPUT_PATH}")
