# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
