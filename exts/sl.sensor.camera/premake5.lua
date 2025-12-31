-- Setup the basic extension information.
local ext = get_current_extension_info()
project_ext(ext)


-- --------------------------------------------------------------------------------------------------------------
-- Helper variable containing standard configuration information for projects containing OGN files.
local ogn = get_ogn_project_information(ext, "sl/sensor/camera/")


-- --------------------------------------------------------------------------------------------------------------
-- Link folders that should be packaged with the extension.
repo_build.prebuild_link {
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" }
}

-- --------------------------------------------------------------------------------------------------------------
repo_build.prebuild_link {
    { "sl/sensor/camera/", ext.target_dir.."/sl/sensor/camera/" },
}
-- --------------------------------------------------------------------------------------------------------------
-- --------------------------------------------------------------------------------------------------------------
-- Breaking this out as a separate project ensures the .ogn files are processed before their results are needed.
project_ext_ogn( ext, ogn )


local abs_target_deps = path.getabsolute(target_deps)

-- --------------------------------------------------------------------------------------------------------------
-- Build the C++ plugin that will be loaded by the extension.
project_ext_plugin(ext, ogn.plugin_project)
    -- It is important that you add all subdirectories containing C++ code to this project
    add_files("source", "plugins/"..ogn.module)
    add_files("nodes", "plugins/nodes")

    includedirs { "include/"}

    filter "system:linux"
        includedirs { "%{target_deps}/cuda/include" }
        libdirs     { "%{target_deps}/cuda/lib64" }
        -- Even if nvcc does this by default, being explicit prevents
        -- errors if you change compiler settings later.
        links       { "cudart_static", "pthread", "dl", "rt"}

    filter "system:windows"
        includedirs { "%{target_deps}/cuda/include" }
        libdirs     { "%{target_deps}/cuda/lib/x64" }
        links       { "cudart_static" }
    filter {}

    -- Add the standard dependencies all OGN projects have; includes, libraries to link, and required compiler flags
    add_ogn_dependencies(ogn)

    cppdialect "C++17"
