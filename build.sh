#!/bin/bash
set -e

SCRIPT_DIR=$(dirname "${BASH_SOURCE}")

mkdir -p exts/sl.sensor.camera/bin/
rm -f exts/sl.sensor.camera/bin/libsl.sensor.camera.plugin.so

# Each dependency is versioned independently under its own path segment
# (<CDN_BASE>/<lib>/<version>/<archive>), so bumping one lib's version never forces
# re-uploading another unchanged lib.
ZED_ISAAC_SIM_VERSION=5.1.1
SL_ZED_SIM2REAL_VERSION=0.1.0
echo "Downloading dependencies (sl_zed $ZED_ISAAC_SIM_VERSION, sl_zed_sim2real $SL_ZED_SIM2REAL_VERSION)..."

CDN_BASE="https://stereolabs.sfo2.cdn.digitaloceanspaces.com/utils/zed_isaac_sim"
SL_ZED_DOWNLOAD_URL="${CDN_BASE}/sl_zed/${ZED_ISAAC_SIM_VERSION}/libsl_zed_linux_x86_64_${ZED_ISAAC_SIM_VERSION}.tar.gz"

BUILD_PATH="_build/linux-x86_64/release/exts/sl.sensor.camera/bin/"

# sl_zed_sim2real (ZED Sim2Real model) is fetched from the CDN like sl_zed, in its own archive.
SL_ZED_SIM2REAL_ARCHIVE="sl_zed_sim2real_linux_x86_64_${SL_ZED_SIM2REAL_VERSION}.tar.gz"
SL_ZED_SIM2REAL_URL="${CDN_BASE}/sl_zed_sim2real/${SL_ZED_SIM2REAL_VERSION}/${SL_ZED_SIM2REAL_ARCHIVE}"

# Download the sl_zed library
if [ ! -f "exts/sl.sensor.camera/bin/libsl_zed.so" ]; then
    echo "Downloading sl_zed library..."
    wget -O "exts/sl.sensor.camera/bin/libsl_zed_linux_x86_64_${ZED_ISAAC_SIM_VERSION}.tar.gz" "$SL_ZED_DOWNLOAD_URL"
    if [ $? -ne 0 ]; then
        echo "Failed to download sl_zed library from $SL_ZED_DOWNLOAD_URL"
        exit 1
    fi

    # Extract the downloaded library and copy it to the correct location
    tar -xzf "exts/sl.sensor.camera/bin/libsl_zed_linux_x86_64_${ZED_ISAAC_SIM_VERSION}.tar.gz" -C "exts/sl.sensor.camera/bin/"
    rm -f "exts/sl.sensor.camera/bin/libsl_zed_linux_x86_64_${ZED_ISAAC_SIM_VERSION}.tar.gz"
else
    echo "sl_zed library already exists, skipping download."
fi

# Download the sl_zed_sim2real library. Optional: sim2real degrades gracefully if absent, so a
# missing archive is a warning, not a fatal error (the failing wget is in an `if` so `set -e`
# does not abort the build).
if [ ! -f "exts/sl.sensor.camera/bin/libsl_zed_sim2real.so" ]; then
    echo "Downloading sl_zed_sim2real library..."
    if wget -q -O "exts/sl.sensor.camera/bin/${SL_ZED_SIM2REAL_ARCHIVE}" "$SL_ZED_SIM2REAL_URL"; then
        tar -xzf "exts/sl.sensor.camera/bin/${SL_ZED_SIM2REAL_ARCHIVE}" -C "exts/sl.sensor.camera/bin/"
        rm -f "exts/sl.sensor.camera/bin/${SL_ZED_SIM2REAL_ARCHIVE}"
    else
        rm -f "exts/sl.sensor.camera/bin/${SL_ZED_SIM2REAL_ARCHIVE}"
        echo "WARN: could not download sl_zed_sim2real from $SL_ZED_SIM2REAL_URL -- ZED Sim2Real disabled at runtime."
    fi
else
    echo "sl_zed_sim2real library already exists, skipping download."
fi

$SCRIPT_DIR/repo.sh build "$@"

# Copy build artifacts into exts path for simplicity
cp -r $BUILD_PATH/* "exts/sl.sensor.camera/bin/"

cp "exts/sl.sensor.camera/bin/libsl_zed.so" "$BUILD_PATH/libsl_zed.so"

# Mirror the sim2real lib into the build tree too, so _build is runnable (parallels libsl_zed.so).
if [ -f "exts/sl.sensor.camera/bin/libsl_zed_sim2real.so" ]; then
    cp "exts/sl.sensor.camera/bin/libsl_zed_sim2real.so" "$BUILD_PATH/libsl_zed_sim2real.so"
fi

# Remove generated __ogn_files_prebuilt file
if [ -f "exts/sl.sensor.camera/sl/sensor/camera/ogn/__ogn_files_prebuilt" ]; then
    #echo "Removing __ogn_files_prebuilt file..."
    rm -f "exts/sl.sensor.camera/sl/sensor/camera/ogn/__ogn_files_prebuilt"
fi

#rm -rf _compiler _deps _repo
