# ZED Camera Extension

The ZED camera extension streams virtual ZED camera data from NVIDIA Isaac Sim to the ZED SDK. This allows you to test and develop applications using the ZED SDK in a simulated environment.

## Compatibility

Refer to the following table for the extension version compatible with your Isaac Sim version:

| Isaac Sim Version | Extension Version |
| :---------------- | :---------------- |
| 2023.X.X          | 1.X.X             |
| 4.0               | 2.X.X             |
| 4.5               | 3.X.X             |
| 5.0               | 4.X.X             |

## Getting Started

To start using the ZED Camera extension in Isaac Sim, we recommend following our [Getting started with Isaac Sim](https://www.stereolabs.com/docs/isaac-sim/isaac_sim) guide.

### Adding ZED Camera Models

You can find USD models for various ZED cameras in the extension's `data` folder within the Content Browser. Supported models include:
- **ZED X** and **ZED X Mini**
- **ZED X One GS** and **ZED X One UHD**
- **Virtual ZED X**

Drag and drop the desired `.usd` file into your stage to begin.

### Starting the Data Stream

To enable streaming:
1. Open the **Action Graph** (`Window` > `Visual Scripting` > `Action Graph`).
2. Add the **ZED Camera** node to the graph.
3. Connect an **On Playback Tick** node to the `Exec In` of the ZED Camera node.
4. Select the ZED Camera node and configure its properties in the **Property** panel.
5. Press **Play**.

### Node Parameters

| Parameter | Description |
| :--- | :--- |
| **Stream** | Enables or disables the data stream. |
| **Camera Prim** | The path to the ZED camera prim in the stage (e.g., `/World/ZED_X`). |
| **Camera Model** | Select the camera model (ZED X, ZED X Mini, ZED X One GS, etc.). |
| **Transport Layer Mode** | Choose between `NETWORK` (streaming over port), `IPC` (shared memory for local streaming), or `BOTH`. |
| **Port** | Defines the network streaming port (must be an even number). |
| **Serial Number** | For `VIRTUAL_ZED_X`, sets a custom serial number (must start with 11). For other models, it is automatically assigned. |
| **Bitrate** | Configures the streaming bitrate (in kbps). |
| **Chunk Size** | Configures the network chunk size for streaming. |
| **FPS** | Target frame rate for the stream. |
| **Resolution** | Defines the width and height of the streamed images. |

> [!NOTE]
> **IPC Mode** provides the best performance for local streaming but is currently only available on **Linux**. On Windows, the extension will automatically fallback to Network streaming.

### Connecting to the ZED SDK

Once the simulation is running and the node is active, you can connect to the virtual camera using the [ZED SDK Streaming API](https://www.stereolabs.com/docs/video/streaming). The SDK will detect the stream on the specified port or via IPC on Linux.