# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [5.2.0]
### New features
- Added the calibrated **ZED Sim2Real camera model**, an optional post-process that makes simulated RGB resemble a real ZED X camera (lens blur, vignetting, temporal auto-exposure, color grading, sensor noise). Enable it via the **ZED Sim2Real Apply** option on the ZED Camera Helper node, or pass `--apply_zed_sim2real` to the Isaac Lab examples (`zed_single.py`, `zed_multi_env.py`).
- Added the **ZED Cameras panel**: an at-a-glance list of every ZED camera in the stage (thumbnail, prim name, and model) with one-click lens switching. The panel opens automatically at startup and can be toggled from the **Stereolabs** menu.
- Added the **ZED Depth** node: SDK-free RGB + depth capture from a ZED camera using Isaac Sim's renderer, with optional PNG/EXR saving.
- Added support for streaming depth from Isaac Sim into the ZED SDK. Enable the "Stream Depth" option on the OmniGraph node to stream the left RGB image along with the depth map instead of the left + right RGB pair. Uses the `ingestCustomDepth` feature introduced in ZED SDK 5.4.0.
- Added Isaac Lab integration helpers (`isaaclab_utils`): mount the real ZED USD on a robot link, build camera configs from ZED spec tables, and import as a utilities-only package (no Kit app required). Standalone examples are now organized under `examples/`.
- Added new example scripts demonstrating how to integrate ZED cameras in Isaac Sim and Isaac Lab.
- Added support for ZED2i, ZED Mini, and ZED X One Fisheye cameras.
- Added support for IPC streaming on Windows.

### Performance
- Changed the default stream frame rate from 60 to 30 FPS for better out-of-the-box performance.
- ZED cameras now render only at their target FPS instead of every app frame (Isaac Sim 6.0 multi-tick rendering), reducing GPU cost in multi-camera scenes.

### UI and usability
- The **camera model and lens are now detected automatically** from the connected ZED USD asset (its name and its **Lens** selection: Wide, Narrow, or Fisheye). When a camera is connected, the Camera Model and Lens Type inputs are replaced by a read-only summary, so there is nothing to set by hand.
- Grouped the ZED Camera Helper node inputs into **Camera Selection / Configuration / Streaming / ZED Sim2Real** sections for easier navigation in the property panel.
- Improved visual quality of USD files for all ZED camera models.

### Compatibility
- Updated Kit version to 110.1.2.

## [5.1.0]
- Added support for the ZED X Nano camera.
- Changed the default camera resolution to SVGA for better out-of-the-box performance.

## [5.0.1]
- Fix error when using ZED Camera One Helper node.
- Fix encoder issue when using latest Nvidia drivers (590+).
- Fix IMU data when using multiple cameras in the scene. Previously it was re-using the same IMU node for all the cameras.

## [5.0.0]
- Add Isaac SIM 6.0 support

## [4.2.2]
- Fix error when using ZED Camera One Helper node.
- Fix encoder issue when using latest Nvidia drivers (590+).
- Fix IMU data when using multiple cameras in the scene. Previously it was re-using the same IMU node for all the cameras.

## [4.2.1]
- Fix streaming of 4mm camera models (ZED X and ZED XM).

## [4.2.0]
- Add the option to change streaming bitrate and chunksize when streaming over network.
- Add the option to stream over both IPC and network simultaneously.
- The C++ omnigraph node and the python nodes are now implemented in a single extension, simplifying installation and usage.
- Set default FPS to 60 for better user experience.

## [4.1.1]
- Fix IPC streaming issue when using multiple ZED cameras on the same machine.

## [4.1.0] - 2025-10-27
- Add support for new camera models (ZED X One GS, ZED X One UHD) and virtual ZED X cameras.

## [4.0.0] - 2025-07-22
- Add new extension rework for Isaac Sim 5.0

## [3.2.0] - 2025-07-22
- Add new extension rework for Isaac Sim 4.5
- Improve extension's overall performance
- Add IPC support for better streaming performance (enabled by default, only on Linux)

## [3.1.1] - 2025-07-15
- Fix crash on Windows

## [3.1.0] - 2025-06-26
- Add support for ZED X Mini camera
- Add new ZED X and ZED X Mini USD models

## [3.0.0] - 2025-03-20
- Add support for Isaac Sim 4.5.0
- Add support for ZED SDK 5.0.0
- Updated ZED X camera resolutions to match real resolutions: HD1200, HD1080, SVGA
- Release streamer on stop button press, allowing to change camera parameters between start/stop without reloading the scene

## [2.0.1] - 2025-02-25
- Fix ZED Camera extension compatibility with Stereolabs ZED SDK 4.2.5

## [2.0.0] - 2024-08-29
- Add support for Isaac Sim 4.0

## [1.1.0] - 2024-04-04
- Add support for ZED SDK 4.1

## [1.0.3] - 2024-02-16
- Add FPS and resolution parameters in Isaac Sim GUI
- Add throttling of data fetch to improve performance on low FPS

## [1.0.2] - 2024-02-16
- Improve ZED Camera extension streaming performance

## [1.0.1] - 2023-12-19
- Update Stereolabs logo

## [1.0.0] - 2023-02-03
- Initial version of the ZED Camera extension
