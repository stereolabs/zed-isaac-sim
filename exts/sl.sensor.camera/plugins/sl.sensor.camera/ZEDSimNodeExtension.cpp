// SPDX-FileCopyrightText: Copyright (c) 2023-2026 Stereolabs. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
//
// Copyright (c) 2022, NVIDIA CORPORATION. All rights reserved.
//
// Modified from NVIDIA-Omniverse/kit-extension-template-cpp
// (omni.example.cpp.omnigraph_node): renamed to the sl.sensor.camera plugin and
// namespace. See THIRD_PARTY_NOTICES.md.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#define CARB_EXPORTS

#include <carb/PluginUtils.h>

#include <omni/ext/IExt.h>
#include <omni/graph/core/IGraphRegistry.h>
#include <omni/graph/core/ogn/Database.h>
#include <omni/graph/core/ogn/Registration.h>

// Standard plugin definitions required by Carbonite.
const struct carb::PluginImplDesc pluginImplDesc = { "sl.sensor.camera.plugin",
                                                     "", "Stereolabs",
                                                     carb::PluginHotReload::eEnabled, "dev" };

// These interface dependencies are required by all OmniGraph node types
CARB_PLUGIN_IMPL_DEPS(omni::graph::core::IGraphRegistry,
                      omni::fabric::IPath,
                      omni::fabric::IToken)

// This macro sets up the information required to register your node type definitions with OmniGraph
DECLARE_OGN_NODES()

namespace sl
{
namespace sensor
{
namespace camera
{

class ZEDSimNodeExtension : public omni::ext::IExt
{
public:
    void onStartup(const char* extId) override
    {
        //printf("ZEDSimNodeExtension starting up (ext_id: %s).\n", extId);
        // This macro walks the list of pending node type definitions and registers them with OmniGraph

        INITIALIZE_OGN_NODES()
    }

    void onShutdown() override
    {
        //printf("ZEDSimNodeExtension shutting down.\n");
        // This macro walks the list of registered node type definitions and deregisters all of them. This is required
        // for hot reload to work.
        RELEASE_OGN_NODES()
    }

private:
};

}
}
}

CARB_PLUGIN_IMPL(pluginImplDesc, sl::sensor::camera::ZEDSimNodeExtension)

void fillInterface(sl::sensor::camera::ZEDSimNodeExtension& iface)
{
}
