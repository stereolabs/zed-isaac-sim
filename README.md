# zed-isaac-sim

ISAAC Sim integration for ZED SDK.

![](./exts/sl.sensor.camera/data/preview.png)

The ZED camera extension streams your virtual ZED camera data to the ZED SDK.

## Getting Started

### Requirements

- Linux Ubuntu 22.04 or Windows 10/11
- [NVIDIA Isaac SIM Requirements](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html)
- [Isaac SIM >=5.0.0 (Workstation or Container)](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_workstation.html)

### Installation

1. Clone the repository
2. Run ./build.bat on Windows or ./build.sh on Linux to build the extension.

## Usage

1. Launch Isaac Sim
2. Open **Window -> Extensions** from the top menu
3. In the Extensions manager window (hamburger button near search field), open **Settings**.
4. Click the "+" button and add the path to your cloned repo + `/exts`

<img src="imgs/add_ext.png">
<br><br>

5. Enable the `ZED Camera` extension in the Third-Party tab.

<img src="imgs/zed_camera_ext_isaac.png">
<br><br>

Then, In your scene,

1. Add a ZED Camera (mono or stereo)

<img src="imgs/zed_x_usd.png">
<br><br>

2. Create a new Action Graph similar to this :

<img src="imgs/action_graph_zed.png">

<img src="imgs/zed_x_prim.png">
<br><br>

- To stream a monocular camera (ZED X One cameras), use the **ZED One Camera Helper** Node instead:
Note : the **serial number** input is only used for Virtual stereo cameras
<img src="imgs/zed_camera_one_helper.png">


### Using IPC

It is now possible to stream images to the ZED SDK using IPC instead of RTSP.
This feature is only available on Linux and only when streaming to the same machine.

To use IPC:

- In the action graph, enable the "IPC" option in the ZED Camera Helper node. It is enabled by default.


<img src="imgs/enable_ipc.png">

Once streaming has started, you should see the following message in the console window:

<img src="imgs/log_ipc_enable.png">
<br><br>

**Important**:

To receive a stream using IPC, the IP address must be set to `127.0.0.1` or `localhost`.

For example, in ZED Explorer:

- Set the IP to 127.0.0.1

<img src="imgs/ipc_stream_ip.png">
<br><br>

- On the top-left corner, the streaming mode will be displayed:

<img src="imgs/stream_ipc_zed_explorer.png">


## Create a Virtual stereo Camera

It is also possible to create what we call "Virtual stereo cameras" by pairing two ZED X One cameras together.
In order to do that, a calibration step is required.

- First, open the Extension windows and enable the `ZED Calibration Exporter` extension in the Third-Party tab.
- In the top Menu bar, Click `ZED` -> `ZED Calibration Exporter`. A new window will open.
- Set the left and right cameras by selecting each prim in the Stage and click `Select`.
- Select the Camera model.
- Change the Serial Number if necessary.
- Click on Generate. A calibration file (.conf) will be generated and saved on your machine.

<br><br>
<img src="imgs/zed_calibration_full.gif">
<br><br>


- Then, in your action graph, add a `ZED Camera One Helper` and set the left and right cameras.
- You also need to set the serial number chosen during the calibration process.

<img src="imgs/virtual_stereo_graph.gif">