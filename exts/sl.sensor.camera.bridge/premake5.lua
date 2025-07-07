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


-- --------------------------------------------------------------------------------------------------------------
-- Build the C++ plugin that will be loaded by the extension.
project_ext_plugin(ext, ogn.plugin_project)
    -- It is important that you add all subdirectories containing C++ code to this project
    add_files("source", "plugins/"..ogn.module)
    add_files("nodes", "plugins/nodes")

    includedirs { "include/",
                  "%{target_deps}/cuda/include/"}

	filter "system:windows"
		libdirs{"%{target_deps}/cuda/lib/x64/"}

	filter "system:linux"
        libdirs{"%{target_deps}/cuda/lib64/"}

	filter {}

    links{"cudart"} --, "cuda"}


    -- Add the standard dependencies all OGN projects have; includes, libraries to link, and required compiler flags
    add_ogn_dependencies(ogn)

    cppdialect "C++17"
