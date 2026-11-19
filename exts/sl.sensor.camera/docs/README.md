# Stereolabs ZED Camera Extension

Simulate Stereolabs ZED cameras inside NVIDIA Isaac Sim and deliver their data to the ZED SDK, to
Isaac Lab, or to disk. The extension provides OmniGraph nodes for streaming and depth capture, USD
models for every ZED camera, and a Python API usable from standalone Isaac Lab / Isaac Sim scripts.

There are three ways to consume the data (this doc covers the streaming and SDK-free paths; the Isaac
Lab path is documented under [`examples/isaaclab/`](../examples/isaaclab/README.md)):

1. **Stream to the ZED SDK**: stereo RGB (+ optional depth) and IMU streamed over RTP or IPC. This is
   the only path that involves the ZED SDK.
2. **Isaac Lab (in-process tensors)**: `isaaclab.sensors.Camera` delivers stereo RGB + depth as
   batched torch tensors on the GPU, for RL / imitation learning. Needs Isaac Lab.
3. **SDK-free capture (to disk)**: `zed_depth.py` reads the same renderer depth via Replicator
   annotators and saves PNG/EXR. Plain Isaac Sim, no Isaac Lab.

## Compatibility

Pick the extension version that matches your Isaac Sim version:

| Isaac Sim Version | Extension Version |
| :---------------- | :---------------- |
| 2023.X.X          | 1.X.X             |
| 4.0               | 2.X.X             |
| 4.5               | 3.X.X             |
| 5.0               | 4.X.X             |
| 6.0, 6.1, 6.2     | 5.X.X             |

This version is built against **Isaac Sim 6.1 (Kit 110.3.0)** and also runs on **Isaac Sim 6.0 (Kit
110.1.2)** and **Isaac Sim 6.2 (Kit 110.4.0)**. Streaming requires **ZED SDK 5.6.0 or newer** on the
receiving side (5.5.0 in [legacy camera mode](#simulated-camera-serial-numbers-and-calibration)).

## Getting Started

For a guided walkthrough, follow the
[Getting started with Isaac Sim](https://www.stereolabs.com/docs/isaac-sim/isaac_sim) guide. The short
version:

1. **Add a camera model.** ZED USD models live in the extension's `data/usd` folder in the Content
   Browser. Drag one into your stage.
2. **Add a streaming node.** Open the **Action Graph** (`Window` -> `Graph Editors` -> `Action Graph`),
   add a **ZED Camera Helper** node (or **ZED Camera One Helper** for mono / virtual stereo), and
   connect an **On Playback Tick** node to its `execIn`.
3. **Point it at your camera.** Set the node's **ZED Camera Prim**. The camera model and
   lens are detected automatically from the asset (see below); pick a **Resolution**.
4. **Press Play**, then open the stream from any ZED SDK app (see the
   [ZED SDK Streaming API](https://www.stereolabs.com/docs/video/streaming)): the SDK detects it on the
   camera's port (network) or via IPC on `127.0.0.1` (same machine).

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
set in the [ZED Cameras panel](#zed-cameras-panel)) gives the lens. The property panel shows them as a
read-only summary instead of dropdowns. Only the **Resolution** stays editable (filtered to the
values valid for the detected model). The editable Camera Model / Lens Type dropdowns reappear as
a fallback if no camera prim is connected. Two ZED X One mono cameras can be paired into a
"virtual stereo" ZED: see [Virtual stereo cameras](#virtual-stereo-cameras).

### ZED Cameras panel

The **ZED Cameras** panel opens automatically at startup (docked next to the Content
Browser) and lists every ZED camera placed in the stage (thumbnail, prim name and model),
with its lens shown as buttons (**Wide | Narrow | Fisheye**): the current lens is
highlighted, only the lenses that the model supports are shown, and one click switches. It
edits the same **Lens** selection as the camera prim's variant dropdown, so the visible
lens, the property panel and the streamed calibration all stay in sync. Fixed-lens models
show their single lens as a plain tag. Click anywhere on a camera's row to select it in the
stage. If you close the panel, reopen it anytime from **Stereolabs -> ZED Cameras**.

Its **Settings** tab holds two settings shared by every camera: **Camera mode** (see
[Simulated camera serial numbers and calibration](#simulated-camera-serial-numbers-and-calibration)) and
**Stream timing** (see [Stream frame rate and app timing](#stream-frame-rate-and-app-timing)).

## OmniGraph nodes

The node library shows three nodes, all under the **Stereolabs** category. Connect **On Playback Tick**
-> node `execIn` and configure the inputs in the Property panel. None of the nodes have output ports;
data is delivered to the ZED SDK (or disk) as a side effect.

### ZED Camera Helper: stereo streaming

Streams a stereo ZED (or its left + depth) to the ZED SDK.

| Input | Type | Default | Description |
|---|---|---|---|
| `cameraPrim` | target | - | The ZED camera prim (e.g. `/World/ZED_X`). |
| `cameraModel` | token | `ZED_X` | Auto-detected from the connected asset's name; used only as a fallback when no `cameraPrim` is set. Base model: `ZED_X`, `ZED_XM`, `ZED_X_Nano`, `ZED_M`, `ZED_2i`. |
| `lensType` | token | `Wide` | Auto-detected from the asset's **Lens** selection; fallback only. `Wide`, `Narrow` (filtered per model). |
| `resolution` | token | `SVGA` | `HD2K`, `HD1200`, `HD1080`, `HD720`, `SVGA`, `VGA` (filtered per model). |
| `fps` | uint | `30` | Stream frame rate: `15`, `30`, `60` or `120`. Play changes the app's timing when it cannot send exactly this rate; see [Stream frame rate and app timing](#stream-frame-rate-and-app-timing). |
| `cameraIndex` | int | `-1` | SDK virtual camera mode only. Which simulated camera this is, among the cameras of the same model and lens. The ZED SDK derives the serial number and calibration from it. `-1` takes the first free index at Play. See [Simulated camera serial numbers](#simulated-camera-serial-numbers-and-calibration). |
| `transportLayerMode` | token | `BOTH` | `NETWORK`, `IPC`, or `BOTH`. See [IPC](#ipc-shared-memory-transport). |
| `streamingPort` | uint | `30000` | Streaming port, even. If another camera already uses it, it changes to the next free even port at Play. See [Multiple cameras](#multiple-cameras). |
| `bitrate` | uint | `8000` | Streaming bitrate in Kbps (network only). |
| `chunkSize` | uint | `4096` | Network chunk size in bytes (network only). |
| `streamDepth` | bool | `false` | Stream **Left + Depth** instead of **Left + Right**. See [Depth streaming](#depth-streaming). |
| `applyZedSim2Real` | bool | `true` | **Apply ZED Sim2Real**: master switch of the [ZED X camera model](#zed-sim2real-camera-model). Off streams the render as it is. Editable live. |
| `autoExposure`, `autoWhiteBalance`, `sensorNoise`, `motionBlur`, `vignetting`, `cameraSharpness` | bool | `true` | The camera model's effects, each on its own switch (needs **Apply ZED Sim2Real**). Editable live. |
| `focusBlur` | bool | `false` | **Focus blur**: the lens's fixed-focus blur, from each eye's depth (needs **Apply ZED Sim2Real**; ZED X, X Mini and X One GS / S lenses). Renders a depth image per eye while on. Editable live. See [Focus blur](#focus-blur). |

### ZED Camera One Helper: mono & virtual stereo streaming

Streams a single ZED X One (mono), or pairs two of them into a virtual stereo ZED.

| Input | Type | Default | Description |
|---|---|---|---|
| `leftCameraPrim` | target | - | The (main) mono camera prim. |
| `rightCameraPrim` | target | *(optional)* | Set to pair two ZED X One cameras into a virtual stereo camera. |
| `cameraModel` | token | `ZED_XONE_GS` | Auto-detected from the connected asset's name; used only as a fallback when no camera prim is set. Base model: `ZED_XONE_UHD`, `ZED_XONE_GS`, `ZED_XONE_S`. |
| `lensType` | token | `Wide` | Auto-detected from the asset's **Lens** selection; fallback only. `Wide`, `Narrow`, `Fisheye` (filtered per model). |
| `resolution` | token | `SVGA` | `HD4K`, `QHDPLUS`, `HD1200`, `HD1080`, `SVGA` (filtered per model). |
| `fps` | uint | `30` | Stream frame rate: `15`, `30`, `60` or `120`. Play changes the app's timing when it cannot send exactly this rate; see [Stream frame rate and app timing](#stream-frame-rate-and-app-timing). |
| `cameraIndex` | int | `-1` | SDK virtual camera mode only. Which simulated camera this is, among the cameras of the same model and lens. The ZED SDK derives the serial number and calibration from it. Not used for virtual stereo. `-1` takes the first free index at Play. See [Simulated camera serial numbers](#simulated-camera-serial-numbers-and-calibration). |
| `serialNumber` | string | `119999999` | Serial for the virtual stereo camera. **Only used when a right camera is set**; must match the serial from the Calibration Exporter. |
| `transportLayerMode` | token | `BOTH` | `NETWORK`, `IPC`, or `BOTH`. |
| `streamingPort` | uint | `30000` | Streaming port, even. If another camera already uses it, it changes to the next free even port at Play. See [Multiple cameras](#multiple-cameras). |
| `bitrate` | uint | `8000` | Streaming bitrate in Kbps (network only). |
| `chunkSize` | uint | `4096` | Network chunk size in bytes (network only). |
| `streamDepth` | bool | `false` | Stream Left + Depth instead of Left + Right. **Virtual stereo only** (both camera prims set); ignored for a single mono camera. |
| `applyZedSim2Real` | bool | `true` | **Apply ZED Sim2Real**: master switch of the [ZED X camera model](#zed-sim2real-camera-model). Off streams the render as it is. Editable live. |
| `autoExposure`, `autoWhiteBalance`, `sensorNoise`, `motionBlur`, `vignetting`, `cameraSharpness` | bool | `true` | The camera model's effects, each on its own switch (needs **Apply ZED Sim2Real**). Editable live. |
| `focusBlur` | bool | `false` | **Focus blur**: the lens's fixed-focus blur, from each eye's depth (needs **Apply ZED Sim2Real**; ZED X, X Mini and X One GS / S lenses). Renders a depth image per eye while on. Editable live. See [Focus blur](#focus-blur). |

### ZED Capture: SDK-free RGB + depth capture

Captures RGB and depth from a ZED using Isaac Sim's renderer. Nothing is streamed and **no ZED SDK is
required**; frames are optionally written to disk.

| Input | Type | Default | Description |
|---|---|---|---|
| `cameraPrim` | target | - | The ZED camera prim. |
| `cameraModel` | token | `ZED_X` | `ZED_X`, `ZED_XM`, `ZED_X_Nano`, `ZED_M`, `ZED_2i`. Auto-detected from the connected ZED USD asset when it carries the info. |
| `lensType` | token | `Wide` | `Wide`, `Narrow` (filtered per model). Auto-detected like `cameraModel`. |
| `resolution` | token | `SVGA` | `HD2K`, `HD1200`, `HD1080`, `HD720`, `SVGA`, `VGA` (filtered per model). |
| `enableSave` | bool | `false` | Save RGB (PNG) + depth (EXR) of every frame the camera renders. |
| `outputDir` | string | `""` | Output directory. Required when `enableSave` is on. |
| `saveDepth` | bool | `true` | Write the depth map (EXR). Turn off to record images only. Stereo models only. |
| `cameraIndex` | int | `-1` | SDK virtual camera mode only. Which simulated camera this is, among the cameras of the same model and lens. The images are rendered with the calibration the ZED SDK generates for it. `-1` takes the first free index at Play. See [Simulated camera serial numbers](#simulated-camera-serial-numbers-and-calibration). |
| `fps` | double | `0.0` | The rate the camera renders at, capped to this value as on a streamed camera. The auto exposure and the motion blur need it. `0` takes the camera's `omni:sensor:tickRate`, and without one the app's update rate. See [ZED Sim2Real](#zed-sim2real-camera-model). |
| `applyZedSim2Real` | bool | `true` | **Apply ZED Sim2Real**: master switch of the [ZED X camera model](#zed-sim2real-camera-model). Off captures the render as it is. Read when the capture starts. |
| `autoExposure`, `autoWhiteBalance`, `sensorNoise`, `motionBlur`, `vignetting`, `cameraSharpness` | bool | `true` | The camera model's effects, each on its own switch (needs **Apply ZED Sim2Real**). The auto exposure takes a moment to settle on a new scene, so the first frames saved can be over- or under-exposed. |
| `focusBlur` | bool | `false` | **Focus blur**, as on the streaming nodes (needs **Apply ZED Sim2Real**). See [Focus blur](#focus-blur). |

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
- **auto white balance** from the gray surfaces in view, with the real camera's limits;
- **sensor noise** at the camera's gain, stronger along edges as in the real image processing;
- **motion blur** over each frame's exposure time;
- **lens vignetting** and the camera's **sharpness**;
- **focus blur** (off by default): the lens's fixed focus, close surfaces blurred by their distance.

**Apply ZED Sim2Real**, on by default, is the master switch; each effect also has its own switch under
it, in the node's **ZED Sim2Real** group. On the streaming nodes all of them can be changed live while
the timeline is playing. Off, the render goes out as it is: the scene's own camera exposure and plain
sRGB.

**SDK-free captures get the same camera model.** The ZED Capture node and `ZEDDepthCamera` carry every
effect above, under the same switches (`apply_zed_sim2real=`, `auto_exposure=`, `motion_blur=`,
`focus_blur=`, ...), with the same defaults as on the streams; they are read once, when the capture
starts, instead of live. The auto exposure and the motion blur need the rate the camera renders at.
Set **FPS** on the node, or `fps=` (e.g. `1 / rendering_dt`), to choose it: it also caps the render
rate, as on a streamed camera. Without it the camera's own `omni:sensor:tickRate` is used, and without
that the app's update rate, since the camera then renders once per update. An app that updates on the
wall clock has no update rate: those two effects then stay off, with a warning. When recording:

- With the auto exposure, the exposure settles on a new scene in about half a second, as the real
  camera's does, so start saving on `exposure_state.converged` to keep over- and under-exposed frames
  out of the recording. The node and `enable_save=True` save from the first frame.
- Without it, the blur follows whatever `exposure:time` the camera carries, which is the render
  product's 0.02 s unless the scene authors one: most of a frame at 30 fps.

**Isaac Lab.** `zed_single.py` and `zed_multi_env.py` apply the model by default
(`--no-apply_zed_sim2real` turns it off). A script of your own uses
`sl.sensor.camera.zed_sim2real.ZedSim2Real` on the cameras' `rgb_hdr` output:
`prepare_cameras(stage, camera_prim_paths)` once before the sensors start, then
`apply(hdr_left, hdr_right, dt)` returns the camera's images, with one auto exposure and white balance
per env (both eyes share them). It has no motion blur or focus blur.

The model ships as the `sl_zed_sim2real` library (1.0.1). Without it, images are streamed and captured
as plain sRGB and a warning is logged once.

**Light flicker** (streams and SDK-free captures; off by default): mains-powered lamps make a real
camera's frames flicker, a 10 Hz beat at 30 fps under 50 Hz mains, weaker with longer exposures. Set
`/exts/sl.sensor.camera/lightFlickerStd` to `office_led` (LED panels), `lamps` (halogen, fluorescent or
LED lamps) or a fraction (e.g. `0.01`), and `/exts/sl.sensor.camera/lightFlickerMainsHz` to `60` where
the mains is 60 Hz (no beat at 30 fps).

### Focus blur

The ZED X lenses have a fixed focus: the 2.2 mm lens is focused at 1.15 m (f/2.2), the 4 mm lens at 2 m (f/2.0).
A real camera blurs what is away from that distance, close surfaces most: with the 2.2 mm lens a surface at
0.2 m is blurred over ~3 px and one at 0.1 m over ~7 px (HD1200); the 4 mm lens blurs ~9 px at 0.25 m and
~4 px at 0.5 m. **Focus blur** in the ZED Sim2Real group adds it, from each eye's depth: a blurred foreground
spreads over what is behind it, a sharp foreground stays sharp in front of a blurred background. It matches
the thin-lens blur Isaac Sim renders in path tracing (within 0.1 px). Isaac's own real-time depth of field is
not used: it drops every blur under ~3.5 px.

It is off by default: while on, each eye also renders a depth image. Measured at HD1200 stereo on an
RTX 5090: about +0.4 ms per frame for the depth images and up to +1.3 ms more for the blur in a scene with
much of the image close up (+5% in total); nothing when off, the depth images are detached. The settings
`/exts/sl.sensor.camera/focusBlurFNumber` and `/exts/sl.sensor.camera/focusBlurDistance` (meters) override the
lenses' figures for every camera, e.g. for a unit focused nearer. The blur applies to streams and SDK-free
captures (**Focus Blur** on the ZED Capture node, `focus_blur=True` on `ZEDDepthCamera`); Isaac Lab images
are not blurred.

## IPC (shared-memory) transport

IPC streams to the ZED SDK on the **same machine** using shared memory, which is faster than the network
path and ignores `bitrate` / `chunkSize`. Set `transportLayerMode` to `IPC` or `BOTH` (the default).
Supported on Linux and, since v5.2.0, on Windows. On the ZED SDK client, set the input IP to `127.0.0.1`
or `localhost`.

## Multiple cameras

Each camera streams on its own even port (e.g. `30000`, `30002`, `30004`). When a camera's `streamingPort` is
already used by another camera in the scene, Play sets it to the next free even port; a console warning names
the camera and its new port. The node keeps that port for the next Play, and in the scene file once saved.
Which camera keeps the shared port depends on the order the graphs run in. A port held by another application
is not skipped: that camera fails with `PORT_UNAVAILABLE`.

## Stream frame rate and app timing

Each streamed frame is stamped with the simulation time of the image it carries, its tick k/fps. A stream sends
at most one frame per app update, so it sends every frame only when no app update spans more than 1/fps of
simulation time. An update is a whole number of physics steps: 60 Hz physics with 15 Hz updates puts 66.7 ms
in each, and a 30 fps stream then sends 15 frames a second. Isaac Sim's default timing, 60 Hz updates and
physics, fits 15, 30 and 60 fps streams.

At Play, before the first physics step, the extension can change the app's timing so that every stream on
the stage fits, and says so in the console. **Stream timing** in the **Settings** tab of the ZED Cameras
panel (Stereolabs menu) picks how, for every camera. Scripts set `/persistent/exts/sl.sensor.camera/streamTiming`
instead, for example `--/persistent/exts/sl.sensor.camera/streamTiming=frame` on the command line. It
applies from the next Play. Isaac Sim's GUI keeps the choice for its next sessions; a standalone script's
lasts for that run.

| Stream timing | Setting | App update rate at Play, for a 30 fps stream |
|---|---|---|
| Fit the stream fps (default) | `fit` | A timing that fits is kept: with 60 Hz physics, 60 Hz and 50 Hz updates both stay. Otherwise the highest multiple of the stream fps at or below the app's update rate. |
| One update per frame | `frame` | The stream fps: 60 Hz and 50 Hz both become 30 Hz. |
| Keep the app's timing | `off` | Unchanged. |

In both `fit` and `frame`:

- An app that updates slower than the stream goes up to its fps. With streams at several rates, the update
  rate is a multiple of all of them (30 Hz for a 15 and a 30 fps stream).
- When the update rate changes, the physics rate goes up to the next multiple of it, never down: 200 Hz
  becomes 210 Hz with 30 Hz updates.
- `/persistent/simulation/minFrameRate` comes down to the update rate when it is above it, so that no
  physics step is dropped.
- At Stop each value goes back to what it was, unless it was changed during Play.
- The console warns at each new physics rate and the first time `fit` changes the app's timing; any other
  change is logged at info level.
- An SDK-free capture that saves on its own (ZED Capture node, `ZEDDepthCamera` with `enable_save`) keeps
  every frame at one update per frame. A script that calls `save_frame()` itself at a capture fps equal to
  the new update rate can miss frames: 10 to 14% of them on an empty stage. With `frame` that is any such
  capture at the stream fps.

Use `frame` when the machine cannot keep up with the app's update rate in real time: with 60 Hz updates, a
machine that manages 40 updates a second sends a 30 fps stream at 20 frames a second (each still stamped
1/30 s apart), and with `frame` it updates at 30 Hz. During Play the viewport then refreshes at the stream
fps too.

A new physics rate changes anything tuned to it, such as a robot's control policy. A new update rate also
sets the timeline's time codes per second, which Isaac Sim keeps equal to the update rate, so USD
time-sampled animation plays at another speed: animation authored at 60 time codes per second plays at half
speed with 30 Hz updates.

With `off` and a timing that does not fit, a stream sends fewer frames than its fps: every second frame, or
every third and so on, the fewest skipped that keep each frame in an app update of its own, so the frames stay
evenly spaced. The stream declares that rate to the receiver: a 30 fps stream over 15 or 20 Hz app updates
sends 15 frames a second. The console warns once per camera whose timing does not fit.

The app is not retimed for a camera added during Play, nor on a Play that resumes a pause: Stop, then
Play. Isaac Lab steps the physics itself and is not retimed either; there, keep each render to at most 1/fps of
physics steps.

## Simulated camera serial numbers and calibration

By default the ZED SDK generates each simulated camera: the extension asks it for a camera of a given
model, lens and index, and gets back a serial number and a calibration (per-eye focal lengths and
optical centers, pose of the right eye). The images are rendered with that calibration. The receiver
regenerates it from the serial number and uses it as the camera's factory calibration, so the ZED SDK
rectifies the images as it does a real camera's. There is no limit on the number of cameras,
nothing to download, and it works offline.

- **Each camera is its own unit.** Calibrations differ slightly from one camera to the next, like real
  units do, and a given camera keeps the same serial number and calibration from one run to the next.
  The right eye is moved to its calibrated pose while the simulation runs; the scene file keeps the
  asset's pose.
- **Picking a camera.** Set the node's **Camera Index** (`cameraIndex`) to choose a specific camera:
  the same model, lens and index always give the same serial number and calibration. The default, `-1`,
  takes the first free index of its model and lens when Play is pressed, so set it explicitly if a
  camera must keep its serial number when cameras are added or removed. The serial number is printed
  when streaming starts.
- **Receiver.** Needs ZED SDK 5.6.0 or newer. Disabling self-calibration on the receiver
  (`InitParameters.camera_disable_self_calib = True`) is recommended in simulation: the streamed
  calibration is exact, and self-calibration would only move it away.
- **Isaac Lab.** `apply_zed_optics()` returns the generated camera. Isaac Lab's
  `Camera.data.intrinsic_matrices` assumes square pixels and a centered optical center, so read the true
  intrinsics from the returned camera's `calibration`.

**Legacy mode.** Switch the **Camera mode** in the **Settings** tab of the **ZED Cameras** panel to
**Legacy serial number** (or set `/persistent/exts/sl.sensor.camera/simCameraMode` to `"legacy"`) to
stream under serial numbers from the ZED SDK's short reserved list, with a calibration file the
receiver downloads the first time (it must be online once). Use it with a receiver older than ZED SDK
5.6.0: it works from 5.5.0, but limits each model and lens to a few cameras, all with the same ideal
calibration. The cameras also fall back to it, with a warning, when the ZED SDK library bundled with
the extension cannot generate simulated cameras. A stream gets the same serial number on every run as
long as its port does not change, so a ZED Fusion configuration written for the cameras keeps
matching them. The mode applies to every camera, from the next Play. Virtual stereo cameras
(two ZED X One) always use the serial number and calibration file from the
[Calibration Exporter](#virtual-stereo-cameras), in both modes.

## Virtual stereo cameras

Pair two ZED X One mono cameras into one stereo ZED. This needs a one-time calibration handled by the
**ZED Calibration Exporter** extension. See its
[guide](../../sl.sensor.camera.calibration_exporter/docs/README.md).

## Python API

The `sl.sensor.camera` package is importable **without a running Kit app** (a plain `sys.path` insert is
enough), so its helpers work in standalone Isaac Lab / Isaac Sim scripts. Key modules:

| Module | Purpose |
|---|---|
| `sl.sensor.camera.utils` | Camera-model spec tables. E.g. `get_supported_models()`, `get_resolution()`, `get_baseline()`, `get_focal_length()`, `get_camera_paths()`, `get_camera_usd_path()`, `get_pinhole_parameters()`. |
| `sl.sensor.camera.zed_depth.ZEDDepthCamera` | SDK-free capture inside a Kit app; `get_rgba()`, `get_depth()`, `save_frame()`. `save_depth=False` records images only (depth is stereo-only and off for mono either way). The ZED Sim2Real effects are on by default under `apply_zed_sim2real=`, the ZED X auto exposure and the motion blur included (`auto_exposure_limits=` narrows the exposure's ranges, `exposure_state` reads it back); they take the camera's render rate from `fps=`, else its `omni:sensor:tickRate`, else the app's update rate. `focus_blur=True` adds the lens's focus blur. Pass a `frames.FrameWriter` to send the frames somewhere other than numbered PNGs. `enable_save=True` saves every frame the camera renders; a script that calls `save_frame()` itself saves the latest frame at each call, so it misses one when an app update finishes two. See [Isaac Sim examples](../examples/isaac_sim/README.md). |
| `sl.sensor.camera.isaaclab_utils` | Isaac Lab helpers: `make_camera_cfg()`, `make_zed_usd_link_mount()`, `apply_zed_optics()`, `add_zed_cli_args()`, `wait_for_camera_data()`, `unwrap_output()`. See [Isaac Lab examples](../examples/isaaclab/README.md). |
| `sl.sensor.camera.sdk_virtual_camera` | Simulated cameras generated by the ZED SDK: `get_mode()` (the mode the cameras use), `get_mode_setting()` / `set_mode()`, `acquire()` / `release()`, the `SimCalibration` structure. |

## Troubleshooting

- **Stream not detected.** Confirm the simulation is playing, the `streamingPort` is **even** and is the
  port the receiver opens (Play changes a port another camera already uses), and (network mode) the port is
  open in your firewall. For IPC, the client IP must be `127.0.0.1` /
  `localhost`.
- **`ZED SDK version` error / no connection.** The receiving app needs **ZED SDK >= 5.6.0** (5.5.0 in
  legacy camera mode).
- **`Maximum number of ... camera reached` in the console.** In legacy camera mode, the reserved serial
  numbers of that model and lens are all in use. Switch the camera mode back to SDK virtual camera for
  more cameras (receiver on ZED SDK 5.6.0 or newer).
- **The receiver fails with `CALIBRATION_FILE_NOT_AVAILABLE` for a serial number like `42997950`.**
  Its ZED SDK is older than 5.6.0, so it cannot regenerate the calibration of a simulated camera.
  Update the receiver, or switch the camera mode to Legacy serial number.
- **`cannot generate simulated cameras` in the console.** The ZED SDK library bundled with the
  extension is older than 5.6.0, so the cameras use the legacy camera mode. Rebuild the extension to
  update it. `create_virtual_camera failed` means the SDK does not simulate that model,
  lens and resolution; `Camera index ... is already used` means two nodes ask for the same camera.
- **First frame is slow / appears to hang.** The first rendered frame compiles RTX shaders and can take
  minutes on a cold cache. It is compiling, not stuck.
- **`Streamer initialization failed` in the console.** The message names the cause and what to do about
  it: `PORT_UNAVAILABLE` (port already in use: stop the other stream or pick another port),
  `INVALID_PORT` (the port must be even), `ENCODER_LOAD_FAILED` / `ENCODER_CREATION_FAILED` (hardware
  video encoder unavailable or the configuration was rejected: check the GPU driver, resolution and FPS),
  `INVALID_SERIAL_NUMBER` (not a valid virtual camera), `INVALID_INPUT` (among others, a resolution
  the model does not support). After fixing the cause, **Stop and Play again**: the camera does not
  retry on its own within a session.
- **Multiple cameras conflict.** Cameras set to the same port get different ports at Play (see
  [Multiple cameras](#multiple-cameras)).
- **Wrong intrinsics / baseline.** Use the shipped ZED USD models (with their authored
  `CameraLeft`/`CameraRight` prims), not ad-hoc pinhole cameras, so intrinsics and baseline match the
  real hardware. In SDK virtual camera mode, keep self-calibration disabled on the receiver.
