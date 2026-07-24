# Stereolabs ZED Warehouse Demos

Turnkey demo scenes for the ZED Isaac Sim integration. Enabling this extension adds three entries to
the Isaac **Examples** browser under the **Stereolabs** category, each building a complete warehouse
scene with a robot-mounted ZED X streaming to the ZED SDK.

## Prerequisites

- A full **Isaac Sim** install (the scenes reference the Isaac asset library).
- The core **`sl.sensor.camera`** extension enabled (the demos enable it automatically if needed).
- To view the streams: a ZED SDK app - **ZED Explorer**, **ZED Studio**, or the **ZED Depth Viewer** -
  set to receive on `127.0.0.1`.

## Running a demo

Open **Window -> Examples -> Robotics Examples** (or the Examples browser), find the **Stereolabs**
category, pick a demo, and click **Load & Run**. This builds the scene and starts the simulation and
the ZED stream. Then open a ZED SDK app on `127.0.0.1` at the demo's port to view the stereo (or depth)
stream.

| Demo | Robot & scene | ZED mount | Stream |
|---|---|---|---|
| **ZED Pick-Place Integration** | Franka arm on a workbench in the Simple Warehouse; continuously picks a random cube and drops it in a KLT bin. | Wrist-mounted ZED X. | `127.0.0.1:30000` |
| **ZED Humanoid Integration** | Unitree H1 humanoid in the warehouse. | Front and rear ZED X. | `127.0.0.1:30000` |
| **ZED AMR Integration** | Idealworks iw.hub AMR patrolling a warehouse aisle. | Front and rear ZED X, selectable stream. | Front `127.0.0.1:30000`, rear `127.0.0.1:30002` (Both mode) |

For the AMR, pick **Front**, **Rear**, or **Both** in the demo panel before **Load & Run** - Both runs
two streams (front on `30000`, rear on `30002`).

## Troubleshooting

- **No stream in the ZED app.** Confirm the simulation is playing and the app's input IP is `127.0.0.1`
  at the port above. See the [extension troubleshooting](../../sl.sensor.camera/docs/README.md#troubleshooting).
- **First run is slow.** The first rendered frame compiles RTX shaders (can take minutes on a cold
  cache); it is compiling, not stuck.

Assets: the environment and robots are referenced from the Isaac asset library; the ZED X model is
bundled with the `sl.sensor.camera` extension.
