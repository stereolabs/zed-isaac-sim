# Stereolabs ZED Camera Extension

Simulate Stereolabs ZED cameras inside NVIDIA Isaac Sim and deliver their data to the ZED SDK, to
Isaac Lab, or to disk. The extension provides OmniGraph nodes for streaming and depth capture, USD
models for every ZED camera, and a Python API usable from standalone Isaac Lab / Isaac Sim scripts.

There are three ways to consume the data (this doc covers the streaming and SDK-free paths; the Isaac
Lab path is documented under [`examples/isaaclab/`](../examples/isaaclab/README.md)):

1. **Stream to the ZED SDK** - stereo RGB (+ optional depth) and IMU streamed over RTP or IPC. This is
   the only path that involves the ZED SDK.
2. **Isaac Lab (in-process tensors)** - `isaaclab.sensors.Camera` delivers stereo RGB + depth as
   batched torch tensors on the GPU, for RL / imitation learning. Needs Isaac Lab.
3. **SDK-free capture (to disk)** - `zed_depth.py` reads the same renderer depth via Replicator
   annotators and saves PNG/EXR. Plain Isaac Sim, no Isaac Lab.

## Compatibility

Pick the extension version that matches your Isaac Sim version:

| Isaac Sim Version | Extension Version |
| :---------------- | :---------------- |
| 2023.X.X          | 1.X.X             |
| 4.0               | 2.X.X             |
| 4.5               | 3.X.X             |
| 5.0               | 4.X.X             |
| 6.0, 6.1          | 5.X.X             |

This version is built against **Isaac Sim 6.1 (Kit 110.3.0)** and also runs on **Isaac Sim 6.0 (Kit
110.1.2)**. Streaming requires **ZED SDK 5.5.0 or newer** on the receiving side.

## Getting Started

For a guided walkthrough, follow the
[Getting started with Isaac Sim](https://www.stereolabs.com/docs/isaac-sim/isaac_sim) guide. The short
version:

1. **Add a camera model.** ZED USD models live in the extension's `data` folder in the Content Browser.
   Drag one into your stage.
2. **Add a streaming node.** Open the **Action Graph** (`Window` -> `Graph Editors` -> `Action Graph`),
   add a **ZED Camera Helper** node (or **ZED Camera One Helper** for mono / virtual stereo), and
   connect an **On Playback Tick** node to its `execIn`.
3. **Point it at your camera.** Set the node's **ZED Camera Prim**. The camera model and
   lens are detected automatically from the asset (see below); pick a **Resolution**.
4. **Press Play**, then open the stream from any ZED SDK app.

### Supported camera models

| Camera Model | Type | Lens Type options | Baseline | Resolutions |
|---|---|---|---|---|
| `ZED_X` | Stereo | Wide, Narrow | 120 mm | HD1200, HD1080, SVGA |
| `ZED_XM` | Stereo | Wide, Narrow | 50 mm | HD1200, HD1080, SVGA |
| `ZED_X_Nano` | Stereo | Wide | 18 mm | HD1200, HD1080, SVGA |
| `ZED_2i` | Stereo | Wide, Narrow | 120 mm | HD2K, HD1080, HD720, VGA |
| `ZED_M` (ZED Mini) | Stereo | Wide | 63 mm | HD2K, HD1080, HD720, VGA |
| `ZED_XONE_UHD` | Mono | Wide | - | HD4K, QHDPLUS, HD1200, HD1080 |
| `ZED_XONE_GS` | Mono | Wide, Narrow | - | HD1200, HD1080, SVGA |
| `ZED_XONE_S` | Mono | Wide, Narrow, Fisheye | - | HD1200, HD1080, SVGA |

Once a camera prim is connected, the **Camera Model** and **Lens Type** are read from the
asset itself: its name gives the model, and its **Lens** selection (Wide / Narrow / Fisheye,
set on the camera prim in the viewport) gives the lens. The property panel shows them as a
read-only summary instead of dropdowns. Only the **Resolution** stays editable (filtered to the
values valid for the detected model). The editable Camera Model / Lens Type dropdowns reappear as
a fallback if no camera prim is connected. Two ZED X One mono cameras can be paired into a
"virtual stereo" ZED. See the **Virtual stereo cameras** section below.

### ZED Cameras panel

The **ZED Cameras** panel opens automatically at startup (docked next to the Content
browser) and lists every ZED camera placed in the stage (thumbnail, prim name and model),
with its lens shown as buttons (**Wide | Narrow | Fisheye**): the current lens is
highlighted, only the lenses that the model supports are shown, and one click switches. It
edits the same **Lens** selection as the camera prim's variant dropdown, so the visible
lens, the property panel and the streamed calibration all stay in sync. Fixed-lens models
show their single lens as a plain tag. Click anywhere on a camera's row to select it in the
stage. If you close the panel, reopen it anytime from **Stereolabs -> ZED Cameras**.

## OmniGraph nodes

The extension registers three nodes, all under the **Stereolabs** category. Connect **On Playback Tick**
-> node `execIn` and configure the inputs in the Property panel. None of the nodes have output ports;
data is delivered to the ZED SDK (or disk) as a side effect.

### ZED Camera Helper - stereo streaming

Streams a stereo ZED (or its left + depth) to the ZED SDK.

| Input | Type | Default | Description |
|---|---|---|---|
| `cameraPrim` | target | - | The ZED camera prim (e.g. `/World/ZED_X`). |
| `cameraModel` | token | `ZED_X` | Auto-detected from the connected asset's name; used only as a fallback when no `cameraPrim` is set. Base model: `ZED_X`, `ZED_XM`, `ZED_X_Nano`, `ZED_M`. |
| `lensType` | token | `Wide` | Auto-detected from the asset's **Lens** selection; fallback only. `Wide`, `Narrow` (filtered per model). |
| `resolution` | token | `SVGA` | `HD2K`, `HD1200`, `HD1080`, `HD720`, `SVGA`, `VGA` (filtered per model). |
| `fps` | uint | `30` | Target stream frame rate. |
| `transportLayerMode` | token | `BOTH` | `NETWORK`, `IPC`, or `BOTH`. See [IPC](#ipc-shared-memory-transport). |
| `streamingPort` | uint | `30000` | Streaming port. **Must be unique per camera** and even. |
| `bitrate` | uint | `8000` | Streaming bitrate in Kbps (network only). |
| `chunkSize` | uint | `4096` | Network chunk size in bytes (network only). |
| `streamDepth` | bool | `false` | Stream **Left + Depth** instead of **Left + Right**. See [Depth streaming](#depth-streaming). |
| `applyZedSim2Real` | bool | `true` | **Apply ZED Sim2Real**: master switch of the [ZED X camera model](#zed-sim2real-camera-model). Off streams the render as it is. Editable live. |
| `autoExposure`, `autoWhiteBalance`, `sensorNoise`, `motionBlur`, `vignetting`, `cameraSharpness` | bool | `true` | The camera model's effects, each on its own switch (needs **Apply ZED Sim2Real**). Editable live. |

### ZED Camera One Helper - mono & virtual stereo streaming

Streams a single ZED X One (mono), or pairs two of them into a virtual stereo ZED.

| Input | Type | Default | Description |
|---|---|---|---|
| `leftCameraPrim` | target | - | The (main) mono camera prim. |
| `rightCameraPrim` | target | *(optional)* | Set to pair two ZED X One cameras into a virtual stereo camera. |
| `cameraModel` | token | `ZED_XONE_GS` | Auto-detected from the connected asset's name; used only as a fallback when no camera prim is set. Base model: `ZED_XONE_UHD`, `ZED_XONE_GS`, `ZED_XONE_S`. |
| `lensType` | token | `Wide` | Auto-detected from the asset's **Lens** selection; fallback only. `Wide`, `Narrow`, `Fisheye` (filtered per model). |
| `resolution` | token | `SVGA` | `HD4K`, `QHDPLUS`, `HD1200`, `HD1080`, `SVGA` (filtered per model). |
| `fps` | uint | `30` | Target stream frame rate. |
| `serialNumber` | string | `119999999` | Serial for the virtual stereo camera. **Only used when a right camera is set**; must match the serial from the Calibration Exporter. |
| `transportLayerMode` | token | `BOTH` | `NETWORK`, `IPC`, or `BOTH`. |
| `streamingPort` | uint | `30000` | Streaming port. Must be unique per camera and even. |
| `bitrate` | uint | `8000` | Streaming bitrate in Kbps (network only). |
| `chunkSize` | uint | `4096` | Network chunk size in bytes (network only). |
| `streamDepth` | bool | `false` | Stream Left + Depth instead of Left + Right. **Virtual stereo only** (both camera prims set); ignored for a single mono camera. |
| `applyZedSim2Real` | bool | `true` | **Apply ZED Sim2Real**: master switch of the [ZED X camera model](#zed-sim2real-camera-model). Off streams the render as it is. Editable live. |
| `autoExposure`, `autoWhiteBalance`, `sensorNoise`, `motionBlur`, `vignetting`, `cameraSharpness` | bool | `true` | The camera model's effects, each on its own switch (needs **Apply ZED Sim2Real**). Editable live. |

### ZED Capture - SDK-free RGB + depth capture

Captures RGB and simulated stereo depth from a ZED using Isaac Sim's renderer. **No ZED SDK required** -
this does not stream; it optionally writes frames to disk.

| Input | Type | Default | Description |
|---|---|---|---|
| `cameraPrim` | target | - | The ZED camera prim. |
| `cameraModel` | token | `ZED_X` | `ZED_X`, `ZED_XM`, `ZED_X_Nano`, `ZED_M`, `ZED_2i`. Auto-detected from the connected ZED USD asset when it carries the info. |
| `lensType` | token | `Wide` | `Wide`, `Narrow` (filtered per model). Auto-detected like `cameraModel`. |
| `resolution` | token | `SVGA` | `HD2K`, `HD1200`, `HD1080`, `HD720`, `SVGA`, `VGA` (filtered per model). |
| `enableSave` | bool | `false` | Save RGB (PNG) + depth (EXR) each frame. |
| `outputDir` | string | `""` | Output directory. Required when `enableSave` is on. |
| `saveDepth` | bool | `true` | Write the depth map (EXR). Turn off to record images only. Stereo models only. |

## Depth streaming

Enable **`streamDepth`** on the ZED Camera Helper (or ZED Camera One Helper) node to stream the **left
RGB image + a depth map** instead of the left + right stereo pair. The depth is Isaac Sim's
**ground-truth renderer depth** (`distance_to_image_plane`), delivered to the ZED SDK via its
`ingestCustomDepth` feature (introduced in **ZED SDK 5.4.0**). The streamed depth is 896 pixels wide, with
the image's aspect ratio: **896x560** at HD1200 and SVGA, **896x504** at the 16:9 resolutions.
On the ZED Camera One Helper node, `streamDepth` requires a **virtual stereo pair** (both camera prims
set): a single mono camera cannot produce depth on real hardware, so the option is ignored with a
warning.

This is simulated depth, not the SDK's stereo-matched depth. It is useful for feeding a known-good depth
map into a ZED SDK pipeline for testing.

## ZED Sim2Real camera model

Simulated images are too clean. **ZED Sim2Real** is a model of the ZED X camera, fitted on real ZED X
recordings, that turns the renderer's HDR image into the image the camera would output:

- **auto exposure**: the camera meters its own image and sets its exposure time and gain like a real ZED
  X, so the image keeps a realistic brightness from direct sun to dim rooms, and the exposure time and
  gain it picks drive the motion blur and noise;
- **auto white balance** from the grey surfaces in view, with the real camera's limits;
- **sensor noise** at the camera's gain, stronger along edges as in the real image processing;
- **motion blur** over each frame's exposure time;
- **lens vignetting** and the camera's **sharpness**.

**Apply ZED Sim2Real**, on by default, is the master switch; each effect also has its own switch under it,
in the node's **ZED Sim2Real** group. All can be changed live while the timeline is playing. Off, the
render streams as it is: the scene's own camera exposure and plain sRGB. SDK-free captures
(ZED Capture node) get the same image without auto exposure and motion blur.

- **Isaac Lab:** pass `--apply_zed_sim2real` to `zed_single.py` or `zed_multi_env.py`, or use
  `sl.sensor.camera.zed_sim2real.ZedSim2Real` on the cameras' `rgb_hdr` output:
  `prepare_cameras(stage, camera_prim_paths)` once before the sensors start, then
  `apply(hdr_left, hdr_right, dt)` returns the camera's images, with one auto exposure and white
  balance per env (both eyes share them).

The model ships as the `sl_zed_sim2real` library (1.0.0). Without it, images are streamed and captured
as plain sRGB and a warning is logged once.

## IPC (shared-memory) transport

IPC streams to the ZED SDK on the **same machine** using shared memory, which is faster than the network
path and ignores `bitrate` / `chunkSize`. Set `transportLayerMode` to `IPC` or `BOTH` (the default).
Supported on Linux and, since v5.2.0, on Windows. On the ZED SDK client, set the input IP to `127.0.0.1`
or `localhost`.

## Multiple cameras

Each streaming node must use a **unique, even `streamingPort`** (e.g. `30000`, `30002`, `30004`).
Port uniqueness is enforced globally within the process; reusing a port across two cameras is an error.

## Simulated camera serial numbers

Each simulated camera streams under a serial number from the ZED SDK's short reserved list, with a
calibration file the receiver downloads the first time it opens the camera (it must be online once).
There are only a few of these serial numbers per model and lens, so only a few cameras of the same
model and lens stream at once. Virtual stereo cameras (two ZED X One) use the serial number and
calibration file from the [Calibration Exporter](#virtual-stereo-cameras) instead.

## Python API

The `sl.sensor.camera` package is importable **without a running Kit app** (a plain `sys.path` insert is
enough), so its helpers work in standalone Isaac Lab / Isaac Sim scripts. Key modules:

| Module | Purpose |
|---|---|
| `sl.sensor.camera.utils` | Camera-model spec tables. E.g. `get_supported_models()`, `get_resolution()`, `get_baseline()`, `get_focal_length()`, `get_camera_paths()`, `get_camera_usd_path()`, `get_pinhole_parameters()`. |
| `sl.sensor.camera.zed_depth.ZEDDepthCamera` | SDK-free capture inside a Kit app; `get_rgba()`, `get_depth()`, `save_frame()`. `save_depth=False` records images only (depth is stereo-only and off for mono either way). Pass a `frames.FrameWriter` to send the frames somewhere other than numbered PNGs. See [Isaac Sim examples](../examples/isaac_sim/README.md). |
| `sl.sensor.camera.isaaclab_utils` | Isaac Lab helpers: `make_camera_cfg()`, `make_zed_usd_link_mount()`, `apply_zed_optics()`, `add_zed_cli_args()`, `wait_for_camera_data()`, `unwrap_output()`. See [Isaac Lab examples](../examples/isaaclab/README.md). |

## Connecting to the ZED SDK

Once the simulation is running, connect to the virtual camera with the
[ZED SDK Streaming API](https://www.stereolabs.com/docs/video/streaming): the SDK detects the stream on
the configured port (network) or via IPC on `127.0.0.1` (same machine).

## Troubleshooting

- **Stream not detected.** Confirm the simulation is playing, the `streamingPort` is **even** and unique,
  and (network mode) the port is open in your firewall. For IPC, the client IP must be `127.0.0.1` /
  `localhost`.
- **`ZED SDK version` error / no connection.** The receiving app needs **ZED SDK >= 5.5.0**.
- **`Maximum number of ... camera reached` in the console.** The
  [reserved serial numbers](#simulated-camera-serial-numbers) of that model and lens are all in use:
  stream fewer cameras of that model and lens at once.
- **First frame is slow / appears to hang.** The first rendered frame compiles RTX shaders and can take
  minutes on a cold cache. It is compiling, not stuck.
- **`Streamer initialization failed` in the console.** The message names the cause and what to do about
  it: `PORT_UNAVAILABLE` (port already in use: stop the other stream or pick another port),
  `INVALID_PORT` (the port must be even), `ENCODER_LOAD_FAILED` / `ENCODER_CREATION_FAILED` (hardware
  video encoder unavailable or the configuration was rejected: check the GPU driver, resolution and FPS),
  `INVALID_SERIAL_NUMBER` (not a valid virtual camera), `INVALID_INPUT` (among others, a resolution
  the model does not support). After fixing the cause, **Stop and Play again** -
  the camera does not retry on its own within a session.
- **Multiple cameras conflict.** Give each camera its own even port; port reuse is rejected. On IPC (or
  the `BOTH` transport mode), closing one camera's stream currently also interrupts IPC delivery for the
  other cameras in the scene; their network streams are unaffected.
- **Wrong intrinsics / baseline.** Use the shipped ZED USD models (with their authored
  `CameraLeft`/`CameraRight` prims), not ad-hoc pinhole cameras, so intrinsics and baseline match the
  real hardware.

## Virtual stereo cameras

Pair two ZED X One mono cameras into one stereo ZED. This needs a one-time calibration handled by the
**ZED Calibration Exporter** extension. See its
[guide](../../sl.sensor.camera.calibration_exporter/docs/README.md).
