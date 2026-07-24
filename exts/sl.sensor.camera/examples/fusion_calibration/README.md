# ZED Fusion calibration from camera poses

[ZED Fusion](https://www.stereolabs.com/docs/fusion) combines several ZED cameras into one coordinate
frame - for wide-area body tracking, multi-view perception, and similar multi-camera setups. It needs a
calibration file describing where each camera sits in the world and how to reach its stream. This script
generates that file directly from the camera prim poses in your Isaac Sim stage, so a simulated
multi-camera rig can be fused exactly like a real one.

This belongs to the **streaming path**: the cameras stream to the ZED SDK via the OmniGraph nodes (see
the [extension reference](../../docs/README.md)), and ZED Fusion ingests those streams using the JSON
this script writes.

## `pose_to_zed_fusion.py`

Run it inside Isaac Sim (Script Editor) on a stage containing camera prims named
`/World/ZED_X_01` ... `/World/ZED_X_07`. For each valid prim it:

1. Reads the prim's world transform.
2. Converts the translation and rotation into ZED's coordinate convention (rotation as a Rodrigues
   vector).
3. Emits a per-camera entry keyed by serial number, with a `STREAM` input on `127.0.0.1` (ports
   `30000`, `30002`, `30004`, ... - one even port per camera), `INTRA_PROCESS` fusion, and the world
   rotation/translation.

The result is written to `/tmp/zed_fusion_poses.json` and printed to the console.

## Usage

1. Build your multi-camera scene with prims `/World/ZED_X_01..07` and wire each to a **ZED Camera Helper**
   node streaming on a unique even port (`30000`, `30002`, ...), matching the ports in the script.
2. Paste `pose_to_zed_fusion.py` into the Isaac Sim **Script Editor** and run it.
3. Feed the generated JSON to the [ZED Fusion API](https://www.stereolabs.com/docs/fusion) alongside the
   running streams.

> The prim names, serial numbers, and output path are hard-coded near the top of the script - adjust
> them to match your stage and target ZED Fusion configuration.
