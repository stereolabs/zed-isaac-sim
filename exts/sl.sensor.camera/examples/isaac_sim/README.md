# SDK-free ZED depth capture in Isaac Sim

Capture **RGB + depth** from a simulated ZED inside Isaac Sim using the renderer - **no ZED SDK, no
streaming**. Both scripts are driven by `sl.sensor.camera.zed_depth.ZEDDepthCamera`, which pairs
Replicator's `rgb` and `distance_to_image_plane` annotators.

> The depth here is Isaac Sim's *renderer* depth (ground truth), **not** the ZED SDK's stereo-matched
> depth. For real ZED SDK depth, use the streaming path (see the
> [extension reference](../../docs/README.md)).

Both scripts locate the extension via the shared [`../_bootstrap.py`](../_bootstrap.py), so they run
from any location without installing the extension.

## Scripts

| Script | Runs in | How to launch |
|---|---|---|
| [`zed_depth_standalone.py`](zed_depth_standalone.py) | Headless / standalone (`SimulationApp`) | `python.bat` / `python.sh` with CLI args |
| [`zed_depth_example.py`](zed_depth_example.py) | Isaac Sim **GUI** Script Editor | paste, edit CONFIG, press **Play** |

### `zed_depth_standalone.py` - standalone / CLI

Captures left RGB + depth for N frames, prints per-frame stats, and optionally saves PNG/EXR. Runs
with **no arguments**: when no scene or camera is given, it builds a minimal ground + dome-light scene
and spawns a ZED camera at a small default pose, so it produces a usable depth capture out of the box.

```bash
# Zero-config: minimal scene + auto-spawned ZED_X
./python.sh exts/sl.sensor.camera/examples/isaac_sim/zed_depth_standalone.py

# Full control: load your own scene and/or use a camera already placed in it
./python.sh exts/sl.sensor.camera/examples/isaac_sim/zed_depth_standalone.py \
    --usd_path /path/to/scene.usd \
    --camera_prim /World/ZED_X \
    --camera_model ZED_X \
    --resolution HD1200 \
    --num_frames 10 \
    --output_dir /tmp/zed_depth
# Windows: use python.bat. Add --headless for no GUI.
```

| Argument | Default | Description |
|---|---|---|
| `--usd_path` | *(minimal scene)* | Environment USD to load. Omit to build a ground + dome-light scene. |
| `--camera_prim` | *(spawn ZED)* | Prim path of an existing ZED camera. Omit to spawn one at `/World/ZED_X`. |
| `--camera_model` | `ZED_X` | `ZED_X`, `ZED_XM`, `ZED_X_4MM`, `ZED_XM_4MM`. |
| `--resolution` | `HD1200` | `HD1200`, `HD1080`, `SVGA`. |
| `--num_frames` | `10` | Number of frames to capture. |
| `--output_dir` | `None` | If set, save RGB (`.png`) + depth (`.exr`) here. |
| `--headless` | off | Run without a GUI window. |

### `zed_depth_example.py` - GUI Script Editor

For interactive use inside the Isaac Sim GUI (extension enabled):

1. Open Isaac Sim and load a scene containing a ZED X / ZED X Mini camera.
2. Paste the script into the **Script Editor** and edit the CONFIG block:
   `CAMERA_PRIM_PATH`, `CAMERA_MODEL`, `RESOLUTION`, `CAPTURE_INTERVAL` (capture every N physics steps),
   and `SAVE_DIR` (leave empty to only print stats).
3. Execute the script, then press **Play** - RGB + depth are captured every `CAPTURE_INTERVAL` steps.
4. Press **Stop** to clean up.

## Output

- **Console** - per-capture shape and depth range stats.
- **Files** (when a save path is set) - `rgb_left_NNNNNN.png` (left RGB) and `depth_NNNNNN.exr` (float32
  depth in meters, `0` = invalid). For stereo models, `rgb_right_NNNNNN.png` (right RGB) is saved too;
  depth stays left-referenced.
