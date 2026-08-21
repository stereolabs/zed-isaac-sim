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

Paths 2 and 3 both produce the **same SDK-free renderer depth** (`distance_to_image_plane`); they
differ only in framework and delivery - Isaac Lab GPU tensors vs. plain-Isaac-Sim numpy/disk - not in
the depth itself. Only path 1 uses the ZED SDK.

## Compatibility

Pick the extension version that matches your Isaac Sim version:

| Isaac Sim Version | Extension Version |
| :---------------- | :---------------- |
| 2023.X.X          | 1.X.X             |
| 4.0               | 2.X.X             |
| 4.5               | 3.X.X             |
| 5.0               | 4.X.X             |
| 6.0               | 5.X.X             |

This version targets **Isaac Sim 6.0 (Kit 110.1.2)**. Streaming requires **ZED SDK 5.4.1 or newer** on
the receiving side.

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
   lens are detected automatically from the asset (see below) - just pick a **Resolution**.
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
asset itself - its name gives the model and its **Lens** selection (Wide / Narrow / Fisheye,
set on the camera prim in the viewport) gives the lens - and the property panel shows them as a
read-only summary instead of dropdowns. Only the **Resolution** stays editable (filtered to the
values valid for the detected model). The editable Camera Model / Lens Type dropdowns reappear as
a fallback if no camera prim is connected. Two ZED X One mono cameras can be paired into a
"virtual stereo" ZED - see the **Virtual stereo cameras** section below.

### ZED Cameras panel

The **ZED Cameras** panel opens automatically at startup (docked next to the Content
browser) and lists every ZED camera placed in the stage - thumbnail, prim name and model -
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
| `applyZedSim2Real` | bool | `false` | **Apply** toggle for the calibrated [ZED Sim2Real camera model](#zed-sim2real-camera-model-experimental) (real-camera look). Editable live while playing. |
| `zedSim2RealSceneLux` | float | `0.0` | **Scene Lux** - assumed scene illuminance for low-light modeling. `<=0` = bright scene (no added darkening/noise); a positive value simulates a dimmer scene (lower = darker & noisier). Editable live. |

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
| `applyZedSim2Real` | bool | `false` | **Apply** toggle for the calibrated [ZED Sim2Real camera model](#zed-sim2real-camera-model-experimental). Editable live while playing. |
| `zedSim2RealSceneLux` | float | `0.0` | **Scene Lux** - assumed scene illuminance; `<=0` = bright scene, a positive value simulates a dimmer, noisier scene. Editable live. |

### ZED Depth - SDK-free RGB + depth capture

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

## Depth streaming

Enable **`streamDepth`** on the ZED Camera Helper (or ZED Camera One Helper) node to stream the **left
RGB image + a depth map** instead of the left + right stereo pair. The depth is Isaac Sim's
**ground-truth renderer depth** (`distance_to_image_plane`), delivered to the ZED SDK via its
`ingestCustomDepth` feature (introduced in **ZED SDK 5.4.0**). The streamed depth is fixed at **896x512**.
On the ZED Camera One Helper node, `streamDepth` requires a **virtual stereo pair** (both camera prims
set) - a single mono camera cannot produce depth on real hardware, so the option is ignored with a
warning.

This is simulated depth, not the SDK's stereo-matched depth. It is useful for feeding a known-good depth
map into a ZED SDK pipeline for testing.

## ZED Sim2Real camera model (experimental)

> **Experimental** - this feature is under active development; behavior and calibration may change.

An optional post-process that makes the simulated RGB look like a real ZED X camera — lens
blur (MTF), vignetting and corner color shading, temporal auto-exposure, white balance, color
correction, tone curve, sharpening and gain-coupled sensor noise. Useful for closing the
sim-to-real gap when validating against the ZED SDK or generating training data.

- **Streaming:** turn on **Apply** (in the node's **ZED Sim2Real** group) on the ZED Camera Helper node;
  the model runs on the GPU before the frame is encoded and sent. **Apply** and **Scene Lux** can be
  changed live while the timeline is playing, so you can tune the look without stopping.
- **Isaac Lab tensor path:** pass `--apply_zed_sim2real` to the examples, or call
  `sl.sensor.camera.zed_sim2real.ZedSim2Real` to degrade RGB tensors in place (one auto-exposure state
  per env; both eyes of a stereo pair share it).

The model ships as a standalone `sl_zed_sim2real` library used by both paths. If it is not present
the toggle is a safe no-op (frames pass through unmodified) and a warning is logged once.

## IPC (shared-memory) transport

IPC streams to the ZED SDK on the **same machine** using shared memory, which is faster than the network
path and ignores `bitrate` / `chunkSize`. Set `transportLayerMode` to `IPC` or `BOTH` (the default).
Supported on Linux and, since v5.2.0, on Windows. On the ZED SDK client, set the input IP to `127.0.0.1`
or `localhost`.

## Multiple cameras

Each streaming node must use a **unique, even `streamingPort`** (e.g. `30000`, `30002`, `30004`).
Port uniqueness is enforced globally within the process; reusing a port across two cameras is an error.

## Python API

The `sl.sensor.camera` package is importable **without a running Kit app** (a plain `sys.path` insert is
enough), so its helpers work in standalone Isaac Lab / Isaac Sim scripts. Key modules:

| Module | Purpose |
|---|---|
| `sl.sensor.camera.utils` | Camera-model spec tables. E.g. `get_supported_models()`, `get_resolution()`, `get_baseline()`, `get_focal_length()`, `get_camera_paths()`, `get_camera_usd_path()`, `get_pinhole_parameters()`. |
| `sl.sensor.camera.zed_depth.ZEDDepthCamera` | Capture RGB + renderer depth inside a Kit app; `get_rgba()`, `get_depth()`, `save_frame()`. See [Isaac Sim examples](../examples/isaac_sim/README.md). |
| `sl.sensor.camera.isaaclab_utils` | Isaac Lab helpers: `make_camera_cfg()`, `make_zed_usd_link_mount()`, `add_zed_cli_args()`, `wait_for_camera_data()`, `unwrap_output()`. See [Isaac Lab examples](../examples/isaaclab/README.md). |

## Connecting to the ZED SDK

Once the simulation is running, connect to the virtual camera with the
[ZED SDK Streaming API](https://www.stereolabs.com/docs/video/streaming): the SDK detects the stream on
the configured port (network) or via IPC on `127.0.0.1` (same machine).

## Troubleshooting

- **Stream not detected.** Confirm the simulation is playing, the `streamingPort` is **even** and unique,
  and (network mode) the port is open in your firewall. For IPC, the client IP must be `127.0.0.1` /
  `localhost`.
- **`ZED SDK version` error / no connection.** The receiving app needs **ZED SDK >= 5.4.1**. Depth
  streaming additionally relies on `ingestCustomDepth` (ZED SDK >= 5.4.0).
- **First frame is slow / appears to hang.** The first rendered frame compiles RTX shaders and can take
  minutes on a cold cache. It is compiling, not stuck.
- **`Streamer initialization failed` in the console.** Most often the port is already in use or is not
  even. Check the port reported in the message, then **Stop and Play again** - the camera does not retry
  on its own within a session.
- **Multiple cameras conflict.** Give each camera its own even port; port reuse is rejected. On IPC (or
  the `BOTH` transport mode), closing one camera's stream currently also interrupts IPC delivery for the
  other cameras in the scene; their network streams are unaffected.
- **Wrong intrinsics / baseline.** Use the shipped ZED USD models (with their authored
  `CameraLeft`/`CameraRight` prims), not ad-hoc pinhole cameras, so intrinsics and baseline match the
  real hardware.

## Virtual stereo cameras

Pair two ZED X One mono cameras into one stereo ZED. This needs a one-time calibration handled by the
**ZED Calibration Exporter** extension - see its
[guide](../../sl.sensor.camera.calibration_exporter/docs/README.md).
