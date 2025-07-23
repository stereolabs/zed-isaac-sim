// Copyright (c) 2022, NVIDIA CORPORATION. All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//

#define CARB_EXPORTS

#include <carb/PluginUtils.h>

#include <omni/ext/IExt.h>
#include <omni/graph/core/IGraphRegistry.h>
#include <omni/graph/core/ogn/Database.h>
#include <omni/graph/core/ogn/Registration.h>

// Standard plugin definitions required by Carbonite.
const struct carb::PluginImplDesc pluginImplDesc = { "sl.sensor.camera.bridge.plugin",
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
namespace bridge
{

class ZEDSimNodeExtension : public omni::ext::IExt
{
public:
    void onStartup(const char* extId) override
    {
        printf("ZEDSimNodeExtension starting up (ext_id: %s).\n", extId);
        // This macro walks the list of pending node type definitions and registers them with OmniGraph

        INITIALIZE_OGN_NODES()
    }

    void onShutdown() override
    {
        printf("ZEDSimNodeExtension shutting down.\n");
        // This macro walks the list of registered node type definitions and deregisters all of them. This is required
        // for hot reload to work.
        RELEASE_OGN_NODES()
    }

private:
};

}
}
}
}

CARB_PLUGIN_IMPL(pluginImplDesc, sl::sensor::camera::bridge::ZEDSimNodeExtension)

void fillInterface(sl::sensor::camera::bridge::ZEDSimNodeExtension& iface)
{
}
