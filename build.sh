#!/bin/bash
set -e

SCRIPT_DIR=$(dirname "${BASH_SOURCE}")

mkdir -p exts/sl.sensor.camera.bridge/bin/
rm -f exts/sl.sensor.camera.bridge/bin/libsl.sensor.camera.bridge.plugin.so

SL_ZED_VERSION=1.0.0
echo "Downloading dependencies version $SL_ZED_VERSION..."

SL_ZED_DOWNLOAD_URL="https://stereolabs.sfo2.cdn.digitaloceanspaces.com/utils/zed_isaac_sim/${SL_ZED_VERSION}/libsl_zed_linux_x86_64_${SL_ZED_VERSION}.tar.gz"

# Download the sl_zed library
if [ ! -f "exts/sl.sensor.camera.bridge/bin/libsl_zed.so" ]; then
    echo "Downloading sl_zed library..."
    wget -O "exts/sl.sensor.camera.bridge/bin/libsl_zed_linux_x86_64_${SL_ZED_VERSION}.tar.gz" "$SL_ZED_DOWNLOAD_URL"
    if [ $? -ne 0 ]; then
        echo "Failed to download sl_zed library from $SL_ZED_DOWNLOAD_URL"
        exit 1
    fi

    # Extract the downloaded library and copy it to the correct location
    tar -xzf "exts/sl.sensor.camera.bridge/bin/libsl_zed_linux_x86_64_${SL_ZED_VERSION}.tar.gz" -C "exts/sl.sensor.camera.bridge/bin/"
else
    echo "sl_zed library already exists, skipping download."
fi

# linux by default, overwrite if we are on windows
BUILD_PATH="_build/linux-x86_64/release/exts/sl.sensor.camera.bridge"

$SCRIPT_DIR/repo.sh build "$@"

# Copy build artifacts into exts path for simplicity
cp -r $BUILD_PATH/bin/* "exts/sl.sensor.camera.bridge/bin/"

cp "exts/sl.sensor.camera.bridge/bin/libsl_zed.so" "$BUILD_PATH/bin/libsl_zed.so"

#rm -rf _compiler _deps _repo
