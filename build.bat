@echo off
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0

REM Each dependency is versioned independently under its own path segment
REM (<CDN_BASE>/<lib>/<version>/<archive>), so bumping one lib's version never forces
REM re-uploading another unchanged lib.
set "SL_ZED_VERSION=5.1.0"
set "SL_ZED_SIM2REAL_VERSION=0.1.0"
set "BUILD_PATH=_build\windows-x86_64\release\exts\sl.sensor.camera\bin"
set "BIN_TARGET=exts\sl.sensor.camera\bin"
set "CDN_BASE=https://stereolabs.sfo2.cdn.digitaloceanspaces.com/utils/zed_isaac_sim"
set "SL_ZED_FILENAME=sl_zed64_windows_x86_64_!SL_ZED_VERSION!.tar.gz"
set "SL_ZED_DOWNLOAD_URL=!CDN_BASE!/sl_zed/!SL_ZED_VERSION!/!SL_ZED_FILENAME!"
REM sl_zed_sim2real (ZED Sim2Real model) is fetched from the CDN like sl_zed, in its own archive.
set "SL_ZED_SIM2REAL_FILENAME=sl_zed_sim2real_windows_x86_64_!SL_ZED_SIM2REAL_VERSION!.tar.gz"
set "SL_ZED_SIM2REAL_URL=!CDN_BASE!/sl_zed_sim2real/!SL_ZED_SIM2REAL_VERSION!/!SL_ZED_SIM2REAL_FILENAME!"

echo ====================================================
echo Initializing Dependencies (Version: !SL_ZED_VERSION!)
echo ====================================================

REM 1. Create directories if they don't exist
if not exist "%BIN_TARGET%" (
    echo [INFO] Creating target directory: %BIN_TARGET%
    mkdir "%BIN_TARGET%"
)
if not exist "%BUILD_PATH%" (
    echo [INFO] Creating build path: %BUILD_PATH%
    mkdir "%BUILD_PATH%"
)

REM 2. Download and Extract sl_zed library
if not exist "%BIN_TARGET%\sl_zed64.dll" (
    echo [INFO] sl_zed64.dll not found. Starting download...

    powershell -Command "Invoke-WebRequest -Uri '!SL_ZED_DOWNLOAD_URL!' -OutFile '%BIN_TARGET%\!SL_ZED_FILENAME!'"
    if errorlevel 1 (
        echo [ERROR] Failed to download library from !SL_ZED_DOWNLOAD_URL!
        exit /b 1
    )

    echo [INFO] Extracting !SL_ZED_FILENAME!...
    powershell -Command "tar -xzvf '%BIN_TARGET%\!SL_ZED_FILENAME!' -C '%BIN_TARGET%'"
    if errorlevel 1 (
        echo [ERROR] Failed to extract library.
        exit /b 1
    )

    REM --- NEW: Cleanup the archive after extraction ---
    echo [INFO] Cleaning up archive...
    del /f /q "%BIN_TARGET%\!SL_ZED_FILENAME!"
) else (
    echo [INFO] sl_zed library already exists, skipping download.
)

REM 2b. Download and Extract the sl_zed_sim2real library (ZED Sim2Real model). Optional:
REM sim2real degrades gracefully if absent, so a missing archive is a warning, not an error.
if not exist "%BIN_TARGET%\sl_zed_sim2real.dll" (
    echo [INFO] sl_zed_sim2real.dll not found. Starting download...
    powershell -Command "try { Invoke-WebRequest -Uri '!SL_ZED_SIM2REAL_URL!' -OutFile '%BIN_TARGET%\!SL_ZED_SIM2REAL_FILENAME!' -ErrorAction Stop } catch { exit 1 }"
    if errorlevel 1 (
        echo [WARN] Could not download sl_zed_sim2real from !SL_ZED_SIM2REAL_URL!
        echo [WARN] ZED Sim2Real will be disabled at runtime.
    ) else (
        echo [INFO] Extracting !SL_ZED_SIM2REAL_FILENAME!...
        powershell -Command "tar -xzf '%BIN_TARGET%\!SL_ZED_SIM2REAL_FILENAME!' -C '%BIN_TARGET%'"
        del /f /q "%BIN_TARGET%\!SL_ZED_SIM2REAL_FILENAME!"
    )
) else (
    echo [INFO] sl_zed_sim2real library already exists, skipping download.
)

REM 3. Remove old build binaries safely
if exist "%BIN_TARGET%\sl.sensor.camera.plugin*" (
    echo [INFO] Removing old plugin binaries...
    del /q "%BIN_TARGET%\sl.sensor.camera.plugin*"
)

REM 4. Execute Build
echo [INFO] Calling repo.bat build...
call "%SCRIPT_DIR%repo.bat" build %*
if errorlevel 1 (
    echo [ERROR] Build failed with exit code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

REM 5. Copy build artifacts and sync DLL
echo [INFO] Syncing build artifacts...
xcopy /e /i /y "%BUILD_PATH%\*" "%BIN_TARGET%"
copy /y "%BIN_TARGET%\sl_zed64.dll" "%BUILD_PATH%\sl_zed64.dll" >nul
REM Mirror the sim2real DLL into the build tree too, so _build is runnable (parallels sl_zed64).
if exist "%BIN_TARGET%\sl_zed_sim2real.dll" copy /y "%BIN_TARGET%\sl_zed_sim2real.dll" "%BUILD_PATH%\sl_zed_sim2real.dll" >nul

REM 6. Remove generated __ogn_files_prebuilt file
if exist "exts\sl.sensor.camera\sl\sensor\camera\ogn\__ogn_files_prebuilt" (
    REM echo [INFO] Removing __ogn_files_prebuilt file...
    del /f /q "exts\sl.sensor.camera\sl\sensor\camera\ogn\__ogn_files_prebuilt"
)

echo [SUCCESS] Process complete.