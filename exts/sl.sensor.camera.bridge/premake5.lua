-- Setup the basic extension information.
local ext = get_current_extension_info()
project_ext(ext)


-- --------------------------------------------------------------------------------------------------------------
-- Helper variable containing standard configuration information for projects containing OGN files.
local ogn = get_ogn_project_information(ext, "sl/sensor/camera/bridge")


-- --------------------------------------------------------------------------------------------------------------
-- Link folders that should be packaged with the extension.
repo_build.prebuild_link {
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" },
}


-- --------------------------------------------------------------------------------------------------------------
repo_build.prebuild_copy {
    { "sl/sensor/camera/bridge/__init__.py", ogn.python_target_path }
}
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

	filter "system:windows"
        includedirs"%{target_deps}/cuda"
	    libdirs{"%{target_deps}/cuda/lib/x64/"}
        links{"cudart"} --, "cuda"}

    filter {}

    -- Add the standard dependencies all OGN projects have; includes, libraries to link, and required compiler flags
    add_ogn_dependencies(ogn)

    cppdialect "C++17"
