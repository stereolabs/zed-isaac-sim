# ZED in Isaac Lab - stereo RGB + depth as tensors

Use a simulated ZED stereo camera inside [Isaac Lab](https://isaac-sim.github.io/IsaacLab/) and read
its stereo RGB pair and depth map as in-process tensors - no ZED SDK, no network streaming. This is
the path for reinforcement-learning and imitation-learning workflows. It complements the streaming
path (the ZED Camera Helper OmniGraph nodes), which remains the right choice for sim-to-real
validation of the full ZED SDK pipeline - see the [repository overview](../../../../README.md) for
all three data paths.

> **Note:** the depth captured here is Isaac Sim's simulated renderer depth
> (`distance_to_image_plane`) - clean, dense ground truth, ideal as an RL observation or supervision
> signal. It is **not** the ZED SDK's stereo-matched depth and does not reproduce real ZED depth
> noise or holes. For genuine ZED SDK depth, use the streaming path (see the
> [extension reference](../../docs/README.md)).

## How it works

The ZED USD models (e.g. [`ZED_X.usdc`](../../data/usd/)) ship with authored `CameraLeft` /
`CameraRight` prims carrying the real camera intrinsics and stereo baseline, looking down +X with
+Z up. The scripts reference
that USD, attach an Isaac Lab `Camera` sensor to each authored prim, and read `rgb` and
`distance_to_image_plane` every simulation step. To place or mount the camera, always transform the
**whole USD root** - the stereo rig moves rigidly with it. Never move the `CameraLeft` /
`CameraRight` prims individually: that breaks the stereo baseline and can put the camera housing in
frame.

## Requirements

- An [Isaac Lab](https://isaac-sim.github.io/IsaacLab/) installation (verified on Isaac Lab 3.0 /
  Kit 110.1.2), with the `sl.sensor.camera` extension from this repository (v5.2.0 or newer)
  available on `sys.path`.
  Each example imports the shared [`_bootstrap.py`](../_bootstrap.py), which handles this
  automatically - no install step is needed.
- Launch the scripts through the Isaac Lab launcher: `isaaclab.bat` (Windows) or `./isaaclab.sh`
  (Linux).
- Cameras are enabled automatically: RGB and depth are render-based, so every example script
  forces the launcher's `--enable_cameras` flag on, printing a `[ZED] Enabling cameras ...` notice
  when it was omitted. You only need to pass the flag when launching your own scripts.

> **First run is slow.** The first rendered frame compiles RTX shaders and can take several minutes
> on a cold cache (the console prints `[ZED] warmup frame N ...` while this happens). It is
> compiling, not hung; subsequent runs are fast.

## Quick start

[`zed_single.py`](zed_single.py) adds a single ZED X to a small demo scene and reads its stereo
RGB + depth tensors:

```bash
# Windows - headless, save 10 frames
isaaclab.bat -p exts\sl.sensor.camera\examples\isaaclab\zed_single.py --resolution SVGA --num_frames 10 --save_dir C:\zed_lab_out

# Linux
./isaaclab.sh -p exts/sl.sensor.camera/examples/isaaclab/zed_single.py --resolution SVGA --num_frames 10 --save_dir /tmp/zed_lab_out
```

To watch live in a GUI window instead of saving files, request a viewer:

```bash
./isaaclab.sh -p exts/sl.sensor.camera/examples/isaaclab/zed_single.py --resolution SVGA --viz kit
```

To mount the ZED on a robot, load the robot USD and point `--camera_prim` at a path under it:

```bash
./isaaclab.sh -p exts/sl.sensor.camera/examples/isaaclab/zed_single.py --robot_usd /path/to/robot.usd --camera_prim /World/Robot/wrist/ZED_X
```

The remaining commands in this document use the Linux form; on Windows, replace `./isaaclab.sh`
with `isaaclab.bat` and use back-slash paths.

## Command-line arguments

### Script arguments

Shared by all examples in this folder (via `add_zed_cli_args`):

| Argument | Default | Description |
| --- | --- | --- |
| `--camera_model` | `ZED_X` | Stereo ZED model: `ZED_X`, `ZED_XM`, `ZED_X_4MM`, `ZED_XM_4MM`, `ZED_X_Nano`. Sets the baseline and camera prim paths. |
| `--resolution` | `SVGA` | Capture resolution. ZED X family: `HD1200` (1920x1200), `HD1080` (1920x1080), `SVGA` (960x600). Validated against the selected model. |
| `--camera_prim` | `/World/ZED_X` | Stage path where the ZED USD is referenced. Must be the model root (its children are `base_link/<model>/CameraLeft\|CameraRight`). Put it under a robot link to mount it. |
| `--robot_usd` | `None` | Optional robot USD referenced at `/World/Robot`. When set, also pass `--camera_prim` pointing under the robot. (`zed_single.py`) |
| `--num_frames` | `10` | Frames to capture when `--save_dir` is set; ignored otherwise. |
| `--save_dir` | `None` | If set, save each frame to disk (see [Output](#output)) and stop after `--num_frames`. If omitted, the script runs until stopped (Ctrl-C / close) and only prints stats. |

### Isaac Lab launcher arguments

The most relevant of the standard `AppLauncher` arguments (run with `-h` for the full set):

| Argument | Description |
| --- | --- |
| `--enable_cameras` | Turns on the renderer so the camera sensors produce data. Enabled automatically by all example scripts; required when launching your own script. |
| `--headless` / `--viz` | Run without a GUI / select a viewer (`--viz kit` opens a window). Newer Isaac Lab versions deprecate `--headless` in favor of `--viz none`. |
| `--device` | Compute device for the tensors, e.g. `cuda:0` (default) or `cpu`. |
| `--verbose` | Also enables this script's per-frame log line and warmup heartbeat; off by default (only milestones and errors print). Note that it raises Kit logging to DEBUG as well. |

## Output

**Console** - milestones always print; the one-line-per-frame log requires `--verbose`:

```
[ZED] baseline = 0.120 m, stereo = True, 960x600.
[ZED] Streaming data after 1 frames.
  frame 0: rgb_l (600, 960, 3) | rgb_r (600, 960, 3) | depth (600, 960) [1.05, 4.89] m (94.6% valid)
```

**Saved files** (when `--save_dir` is set), one set per frame:

- `left_NNNNNN.png`, `right_NNNNNN.png` - 8-bit RGB.
- `depth_NNNNNN.exr` - float32 depth in **meters** (`0` = invalid / no return). Falls back to `.npy`
  if OpenCV is not available.

**In code**, per camera sensor:

- `cam.data.output["rgb"]` -> tensor `(num_cameras, H, W, 3)`, uint8, on `--device`.
- `cam.data.output["distance_to_image_plane"]` -> `(num_cameras, H, W, 1)`, float32 meters.
- Values are `ProxyArray`; use the `.torch` property to get a real tensor.

## Example scripts

Beyond `zed_single.py` (covered above), the folder contains a vectorized example, a keyboard-teleop
demo, and three ports of flagship Isaac Lab demos.

### `zed_multi_env.py` - vectorized capture (many environments)

Batched capture across N environments: the ZED USD is referenced once per environment (a centered
grid, 5 m pitch, each camera looking straight down at its own objects so envs stay out of each
other's view) and one `Camera` sensor per eye matches all of them by regex, so outputs come back
batched as `(num_envs, H, W, C)` tensors.

```bash
./isaaclab.sh -p exts/sl.sensor.camera/examples/isaaclab/zed_multi_env.py --num_envs 4 --resolution SVGA --save_dir /tmp/zed_lab_multi
```

Extra arguments: `--num_envs` (default `4`). With `--save_dir`, one frame set is saved per
environment (`left_env00.png`, ...).

> This referencing pattern - rather than `InteractiveScene`'s cloner - is deliberate: the cloner
> makes the embedded camera prims non-enumerable.

### Flagship demo ports

Three ports of flagship Isaac Lab demos. Each mounts the real
`ZED_X.usdc` model rigidly to a robot link and reads its authored `CameraLeft` / `CameraRight` - no
ad-hoc pinhole cameras, so intrinsics and baseline match real hardware. The mount pose (a translate
plus `RotateXYZ` in the link frame) is exposed as per-demo constants near the top of each script -
tune them in the viewport. All three accept the shared script arguments.

#### [`zed_quadruped.py`](zed_quadruped.py) - walking ANYmal-C on rough terrain

A single ANYmal-C **walking** on generated rough terrain, driven by the pretrained ANYmal-C
HeightScan locomotion policy and steered live from the keyboard, with the ZED X on the **base
link** looking forward; stereo RGB + depth as `(N, H, W, C)` tensors (`--num_envs` to spawn more
robots).

```bash
./isaaclab.sh -p exts/sl.sensor.camera/examples/isaaclab/zed_quadruped.py --verbose            # GUI, keyboard-steered
./isaaclab.sh -p exts/sl.sensor.camera/examples/isaaclab/zed_quadruped.py --command 1 0 0 --save_dir /tmp/zed_quad --num_frames 5 --save_every 10   # headless walk
```

Keyboard ([Isaac Lab `Se2Keyboard`](https://isaac-sim.github.io/IsaacLab/)) - **click the 3D
viewport to focus it first**: `↑`/`↓` walk forward/back, `←`/`→` strafe, `Z`/`X` turn, `L` reset.
For a non-interactive / headless walk, pass `--command VX VY WZ` (m/s, m/s, rad/s) instead of using
the keyboard.

With `--save_dir`, writes `step_NNNNN/{left,right}_envNN.png` + `depth_envNN.exr` per environment
every `--save_every` steps, stopping after `--num_frames` batches; without it, streams per-environment
depth statistics and the live command (with `--verbose`). If the robot tips over it auto-resets to
recover.

> The walking policy is downloaded from the Isaac Lab Nucleus server on first run
> (`Policies/ANYmal-C/HeightScan/policy.pt`) - needs network access.

#### [`zed_franka_manipulation.py`](zed_franka_manipulation.py) - autonomous Franka pick-and-lift

An autonomous state machine (no human, no policy) picks and lifts a cube while the ZED X rides the
Franka **wrist** (`panda_hand`). Fully headless-able, so it doubles as a CI check.

```bash
./isaaclab.sh -p exts/sl.sensor.camera/examples/isaaclab/zed_franka_manipulation.py --headless --num_envs 4 --num_frames 5 --save_dir /tmp/zed_franka
./isaaclab.sh -p exts/sl.sensor.camera/examples/isaaclab/zed_franka_manipulation.py --num_envs 1    # GUI
```

Saves a `zed_NNNNN/` batch (`{left,right}_envNN.png` + `depth_envNN.exr`) every `--save_every`
steps; the sequence shows the approach -> grasp -> lift.

#### [`zed_record_demos.py`](zed_record_demos.py) - imitation-learning HDF5 recording

Keyboard-teleop demo recording on the Franka cube-stacking task: a human stacks the cubes while the
recorder exports **successful demonstrations to HDF5**, with observations coming from the
wrist-mounted ZED X. A right-eye RGB (`wrist_cam_right`) and a `wrist_cam_depth` observation are
added to the task's default `wrist_cam`; the static `table_cam` is dropped (the robot-mounted view
is the relevant one). A GUI window is required for keyboard input.

```bash
./isaaclab.sh -p exts/sl.sensor.camera/examples/isaaclab/zed_record_demos.py --num_demos 1 --dataset_file /tmp/demos/zed_stack.hdf5
```

`--num_demos N` stops the session automatically once N successful stacks have been exported; `0`
(the default) records indefinitely until you close the window.

Keyboard controls: arrow keys and `WASDQE` move the end-effector, `K` / `L` toggle the gripper, and
`R` discards the current attempt and resets. See Isaac Lab's
[Teleoperation and Imitation Learning tutorial](https://isaac-sim.github.io/IsaacLab/main/source/overview/imitation-learning/teleop_imitation.html)
for the fuller walkthrough this script's keyboard path mirrors.

**What counts as a successful demo.** A demonstration is exported only when the task's success
condition (`cubes_stacked`) holds - which is stricter than the cubes merely touching. All of the
following must be true at the same time:

1. **All three cubes stacked in the required order** - blue (bottom), red (middle), green (top).
   The cubes have fixed identities; any other order does not count.
2. **Each pair aligned and one cube-height apart** - horizontal offset below ~4 cm, vertical gap
   ~4.7 cm, with the upper cube genuinely above the lower.
3. **Gripper released** - the jaws must return to fully open; success does not register while you
   are still holding the top cube.
4. **Held for `--num_success_steps` consecutive steps** (default `10`) - the tower must stay
   stable; a momentary touch does not count.

When all four hold, the console prints `[ZED] Recorded N successful demonstrations.` and the demo
is flushed to disk immediately. If you never see that line, nothing was recorded - closing the
window then removes the empty file. The `grasp_1` / `stack_1` / `grasp_2` subtask terms in the
console show how far an attempt got.

The light/texture randomization events are disabled by default (they trigger ~24 large HDR/texture
downloads from Nucleus); pass `--domain_rand` to re-enable them. To inspect the resulting file
(with any Python that has `h5py`, e.g. Isaac Lab's):

```bash
python -c "import h5py; f = h5py.File('/tmp/demos/zed_stack.hdf5'); f.visit(print)"
# -> data/demo_0/obs/{wrist_cam, wrist_cam_right, wrist_cam_depth, ...} at ZED HxW
```

## Using the sensor in your own script

The `sl.sensor.camera` package is importable without enabling the Kit extension - a plain
`sys.path` insert is enough (the shipped examples use [`../_bootstrap.py`](../_bootstrap.py) for
this) - and its helpers (`utils`, `isaaclab_utils`) do the ZED-specific lifting:

```python
import sys
sys.path.insert(0, r"/path/to/zed-isaac-sim/exts/sl.sensor.camera")  # this repo's core extension root

from isaaclab.app import AppLauncher
from sl.sensor.camera.isaaclab_utils import add_zed_cli_args  # shared --camera_model/--resolution/... args
# ... parse args, then force cameras on (RGB/depth are render-based) like the examples do:
args.enable_cameras = True
app = AppLauncher(args).app

import isaaclab.sim as sim_utils
from isaaclab.sim import SimulationContext
from isaaclab.sensors import Camera

from sl.sensor.camera.isaaclab_utils import make_camera_cfg, unwrap_output, wait_for_camera_data
from sl.sensor.camera.utils import get_camera_paths, get_camera_usd_path

sim = SimulationContext(sim_utils.SimulationCfg(device=args.device))

# 1) Reference the ZED USD and place the WHOLE root (the cameras inherit the pose + baseline).
root = "/World/Robot/wrist/ZED_X"
zed = sim_utils.UsdFileCfg(usd_path=get_camera_usd_path(args.camera_model))
zed.func(root, zed)

# 2) Attach Camera sensors to the authored stereo prims (spawn=None => use the existing prims).
paths = get_camera_paths(root, args.camera_model)   # {"left": .../CameraLeft, "right": ..., "imu": ...}
left  = Camera(make_camera_cfg(paths["left"],  args.camera_model, args.resolution,
                               data_types=["rgb", "distance_to_image_plane"]))
right = Camera(make_camera_cfg(paths["right"], args.camera_model, args.resolution,
                               data_types=["rgb"]))

sim.reset()
dt = sim.get_physics_dt()
wait_for_camera_data(sim, [left, right])            # step until the annotators deliver data
while app.is_running():
    sim.step()
    left.update(dt); right.update(dt)
    rgb_l = unwrap_output(left.data.output, "rgb")                        # (1, H, W, 3)
    depth = unwrap_output(left.data.output, "distance_to_image_plane")    # (1, H, W, 1) meters
    rgb_r = unwrap_output(right.data.output, "rgb")
    # ... use the tensors ...
```

To mount the ZED on a robot, spawn the model as a rigid body and fix it to the robot link with a
`FixedJoint` - the `make_zed_usd_link_mount` and `author_zed_link_joint` helpers in
`isaaclab_utils` implement this pattern, which is what all the robot-mounted examples use (a plain
nested reference does not track a moving link when Fabric is enabled).

## Known limitations

- **Renderer depth.** The depth is the renderer's ground truth, without real ZED depth noise or
  holes. For genuine ZED SDK depth and tracking, use the streaming path.
- **Frozen reported pose on robot mounts.** For a ZED mounted on a joint-driven link (all the robot
  demos), the images and depth track the link correctly, but the sensor's reported `data.pos_w` /
  `quat_w_world` stay frozen at the spawn pose - a known Isaac Lab quirk. Consume the pixels and
  depth; if you need the live camera pose (e.g. for depth-to-world reprojection), derive it from
  the link body pose (`data.body_pose_w`) composed with the mount offset.
- **Keyboard teleop needs a focused GUI window.** `zed_quadruped.py` and `zed_record_demos.py`
  read the keyboard through `carb.input`, which is unavailable headless; the Kit window must have
  focus for keys to register.
- **Demo scenes are illustrative.** Scene, lighting, and camera placement in the examples are
  starting points; on a real robot the framing comes from the physical mount.

## Troubleshooting

- **Empty / all-zero frames** (own scripts). `--enable_cameras` is missing - RGB and depth are
  render-based. The shipped examples force the flag on automatically.
- **First run seems to hang for minutes.** The first rendered frame compiles RTX shaders on a cold
  cache; it is compiling, not stuck. Later runs are fast.
- **`Number of camera prims in the view (1) does not match the number of environments`.** Attach
  the cameras with the regex pattern from
  [`zed_multi_env.py`](#zed_multi_envpy---vectorized-capture-many-environments) instead of cloning
  the ZED USD with `InteractiveScene`.
- **Out of memory with many environments.** Lower `--num_envs` or `--resolution` (`SVGA` is the
  lightest), or run headless.
- **Keyboard controls do nothing.** The Kit window must be focused, and a GUI is required - see
  [Known limitations](#known-limitations).
- **`data.pos_w` is frozen** on a robot-mounted ZED - expected; see
  [Known limitations](#known-limitations).
