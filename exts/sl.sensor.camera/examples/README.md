# Examples

Standalone example scripts for the ZED Isaac Sim / Isaac Lab integration, grouped by data path:

- **[`isaaclab/`](isaaclab/README.md)** - stereo RGB + depth as in-process **GPU torch tensors** in
  Isaac Lab, for RL / imitation learning. Includes ports of flagship Isaac Lab demos with a
  robot-mounted ZED.
- **[`isaac_sim/`](isaac_sim/README.md)** - the same SDK-free RGB + depth, captured in plain Isaac
  Sim (no Isaac Lab) and saved to disk as **PNG/EXR**.
- **[`fusion_calibration/`](fusion_calibration/README.md)** - a ZED Fusion calibration helper for
  the **streaming** path (the OmniGraph nodes documented in the
  [extension reference](../docs/README.md)).

> "ZED depth" in these examples is *simulated* depth from the renderer
> (`distance_to_image_plane`) - **not** the ZED SDK's stereo-matched depth, which only comes from
> the streaming path. `isaaclab/` and `isaac_sim/` capture identical data and differ only in
> framework and delivery (Isaac Lab GPU tensors vs. numpy/disk).

The scripts run without installing the extension: each imports [`_bootstrap.py`](_bootstrap.py),
which locates the extension root and puts `sl.sensor.camera` on `sys.path`.

## Isaac Lab - tensor path

See [`isaaclab/README.md`](isaaclab/README.md) for requirements, arguments, commands, and output
formats. All scripts are launched through `isaaclab.bat` / `isaaclab.sh`; cameras are enabled
automatically.

| Script | What it shows |
| --- | --- |
| [`isaaclab/zed_single.py`](isaaclab/zed_single.py) | Single ZED X: reference the USD, attach sensors to its authored `CameraLeft`/`CameraRight`, read stereo RGB + depth tensors. Optional robot mount. |
| [`isaaclab/zed_multi_env.py`](isaaclab/zed_multi_env.py) | Vectorized capture: batched `(N, H, W, C)` tensors across N environments. |
| [`isaaclab/zed_quadruped.py`](isaaclab/zed_quadruped.py) | ANYmal-C on rough terrain with the ZED on the base link; batched stereo RGB + depth. |
| [`isaaclab/zed_franka_manipulation.py`](isaaclab/zed_franka_manipulation.py) | Autonomous Franka pick-and-lift (state machine) with a wrist-mounted ZED; fully headless-able. |
| [`isaaclab/zed_record_demos.py`](isaaclab/zed_record_demos.py) | Keyboard-teleop imitation-learning **HDF5 recording** with wrist-mounted ZED observations. |

## Isaac Sim - SDK-free depth capture

See [`isaac_sim/README.md`](isaac_sim/README.md) for arguments and usage.

| Script | What it shows |
| --- | --- |
| [`isaac_sim/zed_depth_standalone.py`](isaac_sim/zed_depth_standalone.py) | Standalone / CLI capture (`python.bat` / `python.sh`): opens a USD scene with a ZED, saves RGB + depth as PNG/EXR. |
| [`isaac_sim/zed_depth_example.py`](isaac_sim/zed_depth_example.py) | GUI Script Editor variant: captures every N physics steps while the timeline plays. |

## ZED Fusion calibration - streaming path

See [`fusion_calibration/README.md`](fusion_calibration/README.md) for the workflow.

| Script | What it shows |
| --- | --- |
| [`fusion_calibration/pose_to_zed_fusion.py`](fusion_calibration/pose_to_zed_fusion.py) | Writes a ZED Fusion calibration JSON from the camera prims' world poses, for multi-camera streaming setups. |
