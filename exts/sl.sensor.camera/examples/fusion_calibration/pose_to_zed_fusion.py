import numpy as np
import cv2
import json
import omni.usd
from pxr import Usd, UsdGeom, Gf

# Get stage
stage = omni.usd.get_context().get_stage()
print("get stage")

# Get all camera prims
prim_names = [f"/World/ZED_X_{i:02}" for i in range(1, 8)]
print("prim_names:", prim_names)
output_data = {}

for i, prim_path in enumerate(prim_names):
    print("Processing prim:", prim_path)
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        continue

    xform = UsdGeom.Xformable(prim)
    local_to_world = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())

    translation = local_to_world.ExtractTranslation()
    rotation_matrix = local_to_world.ExtractRotationMatrix()
    print("Translation:", translation)
    print("Rotation Matrix:", rotation_matrix)

    rotation, _ = cv2.Rodrigues(np.array(rotation_matrix))
    print("Rotation Vector:", rotation)

    # Get dummy serial number
    serial = f"1234567{prim_path[-1]}"

    output_data[serial] = {
        "input": {
            "zed": {
                "type": "STREAM",
                "configuration": f"127.0.0.1:3000{i * 2}"
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

print("Fusion JSON configuration:")
print(json.dumps(output_data, indent=4))

# Save to JSON
with open("/tmp/zed_fusion_poses.json", "w") as f:
    json.dump(output_data, f, indent=4)

print("ZED Fusion JSON configuration saved to /tmp/zed_fusion_poses.json")
