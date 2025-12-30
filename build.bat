@echo off
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0

set "SL_ZED_VERSION=4.1.0"
echo Downloading dependencies version !SL_ZED_VERSION!...

set "BUILD_PATH=_build/windows-x86_64/release/exts/sl.sensor.camera/bin"
set "SL_ZED_DOWNLOAD_URL=https://stereolabs.sfo2.cdn.digitaloceanspaces.com/utils/zed_isaac_sim/!SL_ZED_VERSION!/sl_zed64_windows_x86_64_!SL_ZED_VERSION!.tar.gz"

REM Download the sl_zed library if it doesn't exist
if not exist "%BUILD_PATH%\sl_zed64.dll" (
    echo Downloading sl_zed library...
    powershell -Command "Invoke-WebRequest -Uri '!SL_ZED_DOWNLOAD_URL!' -OutFile 'exts\sl.sensor.camera\bin\sl_zed64_windows_x86_64_!SL_ZED_VERSION!.tar.gz'"
    if errorlevel 1 (
        echo Failed to download sl_zed library from !SL_ZED_DOWNLOAD_URL!
        exit /b 1
    )
    
    REM Extract the downloaded library
    powershell -Command "tar -xzvf 'exts\sl.sensor.camera\bin\sl_zed64_windows_x86_64_!SL_ZED_VERSION!.tar.gz' -C 'exts\sl.sensor.camera\bin\'"
    if errorlevel 1 (
        echo Failed to extract sl_zed library
        exit /b 1
    )
) else (
    echo sl_zed library already exists, skipping download.
)

REM Remove old build binaries
del /q exts\sl.sensor.camera\bin\sl.sensor.camera.plugin*

REM Call repo.bat (must exist as a .bat or .cmd)
call "%SCRIPT_DIR%repo.bat" build %*
if errorlevel 1 exit /b %ERRORLEVEL%

REM Copy build artifacts
xcopy /e /i /y "%BUILD_PATH%\*" "exts\sl.sensor.camera\bin"

copy /y "exts\sl.sensor.camera\bin\sl_zed64.dll" "%BUILD_PATH%\sl_zed64.dll" 