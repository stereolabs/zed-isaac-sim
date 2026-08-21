-- Pure-Python extension: no C++/OGN. This file exists only to stage the source folders
-- into the build tree (_build/.../exts/<name>/) so the extension is discoverable by kit
-- and publishable alongside sl.sensor.camera.
local ext = get_current_extension_info()
project_ext(ext)

repo_build.prebuild_link {
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" },
    { "sl/sensor/camera/", ext.target_dir.."/sl/sensor/camera/" },
}
