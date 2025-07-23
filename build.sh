#!/bin/bash
set -e

SCRIPT_DIR=$(dirname "${BASH_SOURCE}")

mkdir -p exts/sl.sensor.camera.bridge/bin/
rm -f exts/sl.sensor.camera.bridge/bin/libsl.sensor.camera.bridge.plugin.so

# linux by default, overwrite if we are on windows
BUILD_PATH="_build/linux-x86_64/release/exts/sl.sensor.camera.bridge"

$SCRIPT_DIR/repo.sh build "$@"

# Copy build artifacts into exts path for simplicity
cp -r $BUILD_PATH/bin/* "exts/sl.sensor.camera.bridge/bin/"

cp "exts/sl.sensor.camera.bridge/bin/libsl_zed.so" "$BUILD_PATH/bin/libsl_zed.so"

#rm -rf _compiler _deps _repo
