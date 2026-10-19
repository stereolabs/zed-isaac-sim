# Notices

The source in this repository is licensed under the MIT License (see [LICENSE](LICENSE)).

Part one lists third-party code included here under its own license. Part two lists
components that ship with, or are required by, this repository without being covered by
its MIT license.

## Third-party code in this repository

### NVIDIA Omniverse Kit C++ extension template

- Source: https://github.com/NVIDIA-Omniverse/kit-extension-template-cpp
- License: Apache License 2.0 (see [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt))
- Copyright (c) 2022 NVIDIA CORPORATION

The build scaffolding and the Kit plugin entry point are derived from this template:

| Path | Relationship |
|---|---|
| `repo.bat`, `repo.sh`, `tools/repoman/` | Unchanged |
| `premake5.lua`, `repo.toml`, `.gitignore`, `.gitattributes` | Modified for this repository |
| `exts/sl.sensor.camera/plugins/sl.sensor.camera/ZEDSimNodeExtension.cpp` | Renamed to the `sl.sensor.camera` plugin and namespace, otherwise unchanged. Stays under Apache 2.0. |
| `exts/sl.sensor.camera/plugins/nodes/OgnZEDSimCameraNode.cpp` | Node skeleton only (database include, static `compute`, `REGISTER_OGN_NODE`). The implementation is Stereolabs' and the file is MIT. |

### NVIDIA packman

- Source: bundled with the template above
- License: Apache License 2.0
- Copyright 2019-2024 NVIDIA CORPORATION

`tools/packman/` is unchanged. Each file carries its own Apache 2.0 header.

### NVIDIA Isaac Sim UI extension template

- Source: Isaac Sim, `isaacsim.examples.extension/template_source_files`
- License: Apache License 2.0
- Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES

`sl.sensor.camera.calibration_exporter` was scaffolded from this template. Files keep
their Apache 2.0 headers:

| Path | Relationship |
|---|---|
| `__init__.py`, `global_variables.py` | Template, with this extension's strings |
| `extension.py`, `ui_builder.py` | Template scaffolding with Stereolabs code added |
| `calibration.py` | Stereolabs, MIT |

## Not covered by the MIT license

### ZED SDK runtime (Stereolabs)

`sl_zed64.dll` / `libsl_zed.so` are not in this repository. `build.bat` / `build.sh`
download them, and release packages bundle them. They are proprietary Stereolabs
software, licensed separately under the ZED SDK license and not under this repository's
MIT license: https://www.stereolabs.com/developers/license

### Omniverse Kit and Isaac Sim

Not redistributed. The Kit SDK is fetched at build time, and the demo scenes reference
Isaac Sim assets from the asset root of the user's own installation. Both remain under
NVIDIA's terms: https://www.nvidia.com/en-us/agreements/enterprise-software/isaac-sim-additional-software-and-materials-license/
