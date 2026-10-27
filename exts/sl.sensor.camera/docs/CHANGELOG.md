# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [5.3.1]
### Fixes
- **Fixed GEN_1 positional tracking with IMU fusion inverting the camera's pitch** in streams and in SVOs recorded from them: a camera pitching down was tracked pitching up. A live receiver also reported `camera_imu_transform` as a 180° turn about the optical axis. It is now the identity, as in SVO recordings of the stream: `getSensorsData()` reports the same IMU orientation live and recorded.
- **Fixed the ZED Mini and ZED 2i IMU being turned relative to the camera**: it had the left camera's optical axes instead of the camera body's, so a level camera at rest reported gravity sideways and a tilted orientation, in streams and in Isaac Sim's own IMU readings. The other cameras were not affected.

## [5.3.0]
### New features
- **ZED Sim2Real is now a model of the ZED X camera**, replacing the 5.2.0 post-process. It turns the rendered HDR image into what a real ZED X outputs: auto exposure, auto white balance, sensor noise, motion blur, vignetting and sharpness. Depth the SDK computes from the stream gets frame-to-frame noise close to a real ZED X's. **Apply ZED Sim2Real**, now on by default, is the master switch, with a live switch per effect in the *ZED Sim2Real* group of the ZED Camera Helper and ZED Camera One Helper. The ZED Capture node applies it without auto exposure and motion blur, Isaac Lab (`--apply_zed_sim2real`) without motion blur. See [ZED Sim2Real camera model](README.md#zed-sim2real-camera-model).
- Added **Save Depth** to the ZED Capture node, on by default. Turn it off to record left and right images only: the float32 depth EXR per frame dominates capture I/O. Mono cameras no longer capture depth.

### UI and usability
- **A warning when a scene is too dark or too bright for a real camera**, with its estimated illuminance. It usually means the lights use the wrong units: a DistantLight of intensity I gives about 3.1 × I lux, a room 200-800 lux, direct sun about 100,000 lux.
- When a camera fails to start streaming, the console names the cause (for example a port in use, an odd port number, an unavailable hardware encoder or an invalid virtual serial number) and what to do about it, instead of `Streamer initialization failed`. A per-frame streaming error is reported once it lasts 3 frames: Play no longer logs a red `ENCODING_FAILED` for the first frame of a network stereo or Stream Depth stream.
- **A warning when a camera does not stream because its IMU gives no reading**, instead of streaming nothing without a word. This happens when **Rigid Body Enabled** is unticked on a camera that is not under another rigid body, or when its *Imu_Sensor* is disabled. To hold a camera still, tick **Kinematic Enabled** instead.
- Setup errors of the ZED Camera Helper, ZED Camera One Helper and ZED Capture nodes (a port already in use, no camera prim, a capture that cannot start) are logged once instead of on every frame. A ZED Capture node that failed to start tries again when one of its inputs changes, or at the next Play.

### Fixes
- **Cameras sit at their lens's FOV cone vertex** on every model and lens except the ZED X One Core fisheye. They were up to 1 cm off along the optical axis, which offset the simulated depth by as much, and some about 1 mm off sideways.
- **Fixed the ZED X One UHD rendering at 3856x2180 in HD4K and QHDPLUS**: it now renders at the ZED SDK's 3840x2160 and 3200x1800.
- **Fixed the ZED 2i Narrow's field of view and the ZED X One fisheye's optical center at HD1080**: the 2i Narrow's focal length was 3.4% longer than the ZED SDK's, and the fisheye's HD1080 image was 60 px too high. Both now match the ZED SDK.
- **Fixed the ZED X One UHD model's housing**: it had the smaller ZED X One S body and now has the real one, the same as the ZED X One GS. The camera moved 9.3 mm back and 3.8 mm up relative to the asset's origin, so a mount tuned to the old model may need adjusting.
- **Fixed the ZED Mini model being upside down.**
- **Fisheye cameras now render distorted in captures and Isaac Lab**: only streams applied the lens, so elsewhere a ZED X One set to **Fisheye** came out as an undistorted pinhole image. A stream, a capture and an Isaac Lab read of the same camera now produce the same image.
- **Fixed SDK-free capture rendering with the wrong field of view**: it used whatever focal length and aperture the USD asset carried instead of the camera model's.
- **Fixed Isaac Lab examples rendering with the wrong field of view**: the ZED USD assets ship one nominal lens for every variant. Call `apply_zed_optics()` after placing a ZED USD in your own Isaac Lab scene, as the examples now do.
- **Fixed streamed depth not lining up with the left image at HD1200 and SVGA**: it was rendered at 896x512 whatever the image's aspect ratio, and the ZED SDK stretches it over the whole image. Rows near the top and bottom were up to 51 px off at HD1200. It now has the image's aspect ratio: 896x560 at HD1200 and SVGA, 896x504 at the 16:9 resolutions.
- **Fixed `author_zed_link_joint()` mounting the ZED at the wrong angle**: it read Isaac Lab's (x, y, z, w) quaternion as (w, x, y, z), so (0, 0, 0) turned the camera by 180°. The angles are now `RotateXYZ` degrees, as documented. Re-tune the angles of a mount set up with the old behavior. The examples are updated and keep their camera views.
- The streaming nodes and the ZED Capture node no longer need `isaacsim.core.utils`, which Isaac Lab's app does not have. Without it they failed on every frame with `'NoneType' object is not callable`.
- `zed_record_demos.py` no longer wipes the demos of an earlier run: Isaac Lab's recorder empties the dataset file it opens. It now stops and asks for another `--dataset_file` when the file exists.
- The Isaac Lab examples only accept the options they use: `--apply_zed_sim2real` is for `zed_single.py` and `zed_multi_env.py`, and `zed_record_demos.py` no longer takes `--save_dir` or `--num_frames`. Passing an option an example would ignore is now an error.
- `zed_depth_example.py` no longer starts a second capture when resumed from Pause.
- The ZED Fusion example writes camera positions in meters whatever the stage's units. On a centimeter stage they were 100 times too large.
- **Fixed the Humanoid demo's streams declaring 30 fps while rendering 15**, which made the receiver pace for twice the frames it got. A stream now always declares the rate its camera actually renders at. The demo also renders at 30 fps, which halves how far the head-mounted cameras swing between frames while walking (up to 6.5° at 15 fps, enough to make the side ZED X One images look shaky).
- The ZED Capture node falls back to a supported resolution, and reports it, instead of refusing to start on one the camera model does not support.
- Depth no longer goes silently missing from captures on OpenCV builds that gate the EXR writer: it falls back to `.npy` with a warning.
- **Fixed the ZED Capture node saving each image twice** when its camera renders slower than the app runs, for example at 30 fps in a 60 Hz scene.

### Performance
- **The ZED Capture node saves frames in the background**: several times more frames per second, without holding up the simulation. If the disk or CPU cannot keep up, the app slows down rather than dropping frames, and stopping the simulation waits for the last frames to be written. Custom `frame_writer`s still write on the calling thread.
- Depth EXRs (ZED Capture node and Isaac Lab helpers) are PIZ-compressed instead of ZIP: still lossless, about 15% smaller and a quarter faster to write.

### Changed
- **Removed the 5.2.0 ZED Sim2Real settings** (**Scene Lux**, the auto exposure target, **Exposure gain**, **Response**, **Vignette strength**, **Isolate tone and vignette**). Graphs from 5.2 drop them on load and get **Apply ZED Sim2Real** switched on, even where it was off.
- **Streamed and captured images are sRGB-encoded** like a real ZED X's, instead of the renderer's tone-mapped image: scenes tuned for the old look appear brighter in the mid-tones and darker in the shadows.
- **Isaac Lab: `ZedSim2Real` takes HDR images**: render `rgb_hdr`, call `prepare_cameras(stage, camera_prim_paths)` once before the sensors start, then `apply(hdr_left, hdr_right, dt)` returns the images instead of modifying 8-bit tensors in place. `--zed_sim2real_scene_lux` is removed.
- ZED Sim2Real needs the `sl_zed_sim2real` library 1.0.0. Without it, images are plain sRGB and a warning is logged once.
- The **ZED Depth** node is renamed **ZED Capture** in the UI, since it records images with or without depth. The node type is unchanged, so existing graphs load as before.
- Removed `make_stereo_camera_cfgs()` and the `spawn_pinhole`, `clipping_range` and `offset` arguments of `make_camera_cfg()`: their stand-in pinhole cameras cannot carry a ZED's fisheye lens. Mount the real ZED USD with `make_zed_usd_link_mount()` + `author_zed_link_joint()`, as the examples do.
- `ZEDDepthCamera` takes an optional `frame_writer` that decides where each captured frame goes, what it is called and whether it is written. The default writes the same numbered PNGs as before. See `sl.sensor.camera.frames.FrameWriter`.

### Compatibility
- Added support for Isaac Sim 6.1 (Kit 110.3.0). Isaac Sim 6.0 (Kit 110.1.2) stays supported with the same build.
- The Humanoid and Pick-Place demos now run on Isaac Sim 6.1, which removed the H1 locomotion policy and Franka pick-place classes they used. The 6.1 pick-place plans with cuMotion, so the arm moves differently and the two cubes alternate between their bench positions instead of random ones.

## [5.2.1]
### Fixes
- Fixed a crash a few seconds after a stereo stream started on Linux when the transport mode was `IPC` or `BOTH`. Isaac Sim exited silently, with no crash report.
- A camera that fails to start streaming is now recoverable: stop and play again. Previously every later attempt failed until Isaac Sim was restarted, whatever the port was set to. The failure is also reported once instead of every frame.
- Deleting one ZED camera no longer stops the other cameras streaming in the same scene.

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
