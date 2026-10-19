# ZED Fusion calibration from camera poses

[ZED Fusion](https://www.stereolabs.com/docs/fusion) combines several ZED cameras into one coordinate
frame, for wide-area body tracking, multi-view perception, and similar multi-camera setups. It needs a
calibration file describing where each camera sits in the world and how to reach its stream. This script
generates that file directly from the camera prim poses in your Isaac Sim stage, so a simulated
multi-camera rig can be fused exactly like a real one.

This belongs to the **streaming path**: the cameras stream to the ZED SDK via the OmniGraph nodes (see
the [extension reference](../../docs/README.md)), and ZED Fusion ingests those streams using the JSON
this script writes.

## `pose_to_zed_fusion.py`

Run it inside Isaac Sim (Script Editor, with the `sl.sensor.camera` extension enabled) on a stage
containing ZED assets placed at `/World/ZED_X_01` ... `/World/ZED_X_07`. For each valid prim it:

1. Reads the world transform of the asset's left camera (`CameraLeft`, or `Camera` on a ZED X One):
   ZED Fusion expects the pose of the ZED SDK camera frame, which sits on the left camera, not the
   pose of the asset's root.
2. Converts the translation and rotation into ZED's `IMAGE` coordinate system in meters (rotation as a
   Rodrigues vector), the convention ZED Fusion reads the file in.
3. Emits a per-camera entry keyed by serial number, with a `STREAM` input on `127.0.0.1` (one
   even port per camera: `30000`, `30002`, `30004`, ...), `INTRA_PROCESS` fusion, and the world
   rotation/translation.

The result is written to `zed_fusion_poses.json` in the system temp folder (`/tmp` on Linux, `%TEMP%` on
Windows) and printed to the console.

## Usage

1. Build your multi-camera scene with ZED assets `/World/ZED_X_01..07` and wire each to a **ZED Camera Helper**
   node streaming on a unique even port (`30000`, `30002`, ...), matching the ports in the script.
   Only four ZED X with the same lens stream at once
   ([reserved serial numbers](../../docs/README.md#simulated-camera-serial-numbers)): with more, give
   some of them the narrow lens.
2. Paste `pose_to_zed_fusion.py` into the Isaac Sim **Script Editor** and run it.
3. Feed the generated JSON to the [ZED Fusion API](https://www.stereolabs.com/docs/fusion) alongside the
   running streams.

> The prim names, serial numbers, base port and output path are set at the top of the script; adjust
> them to match your stage. The serial numbers must be the ones the cameras stream (logged when
> streaming starts): ZED Fusion matches each entry to its stream by serial number.
