#!/bin/bash
set -e

SCRIPT_DIR=$(dirname "${BASH_SOURCE}")

mkdir -p exts/sl.sensor.camera/bin/
rm -f exts/sl.sensor.camera/bin/libsl.sensor.camera.plugin.so

ZED_ISAAC_SIM_VERSION=4.1.0
echo "Downloading dependencies version $ZED_ISAAC_SIM_VERSION..."

SL_ZED_DOWNLOAD_URL="https://stereolabs.sfo2.cdn.digitaloceanspaces.com/utils/zed_isaac_sim/${ZED_ISAAC_SIM_VERSION}/libsl_zed_linux_x86_64_${ZED_ISAAC_SIM_VERSION}.tar.gz"

BUILD_PATH="_build/linux-x86_64/release/exts/sl.sensor.camera/bin/"

# Download the sl_zed library
if [ ! -f "$BUILD_PATH/libsl_zed.so" ]; then
    echo "Downloading sl_zed library..."
    wget -O "exts/sl.sensor.camera/bin/libsl_zed_linux_x86_64_${ZED_ISAAC_SIM_VERSION}.tar.gz" "$SL_ZED_DOWNLOAD_URL"
    if [ $? -ne 0 ]; then
        echo "Failed to download sl_zed library from $SL_ZED_DOWNLOAD_URL"
        exit 1
    fi

    # Extract the downloaded library and copy it to the correct location
    tar -xzf "exts/sl.sensor.camera/bin/libsl_zed_linux_x86_64_${ZED_ISAAC_SIM_VERSION}.tar.gz" -C "exts/sl.sensor.camera/bin/"
else
    echo "sl_zed library already exists, skipping download."
fi

$SCRIPT_DIR/repo.sh build "$@"

# Copy build artifacts into exts path for simplicity
cp -r $BUILD_PATH/* "exts/sl.sensor.camera/bin/"

cp "exts/sl.sensor.camera/bin/libsl_zed.so" "$BUILD_PATH/libsl_zed.so"

#rm -rf _compiler _deps _repo
