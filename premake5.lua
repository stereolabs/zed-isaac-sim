-- Shared build scripts from repo_build package.
repo_build = require("omni/repo/build")

-- Repo root
root = repo_build.get_abs_path(".")

-- Set the desired MSVC, WINSDK, and MSBUILD versions before executing the kit template premake configuration.
MSVC_VERSION = "14.27.29110"
WINSDK_VERSION = "10.0.18362.0"
MSBUILD_VERSION = "Current"

-- Workaround: Define premake.warning function if it doesn't exist (for compatibility with ogn_helpers.lua)
if not premake.warning then
    premake.warning = function(msg)
        print("WARNING: " .. msg)
    end
end

-- Execute the kit template premake configuration, which creates the solution, finds extensions, etc.
dofile("_repo/deps/repo_kit_tools/kit-template/premake5.lua")

include("exts/sl.sensor.camera/premake5.lua")