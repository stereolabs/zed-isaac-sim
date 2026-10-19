@echo off
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0

REM An elevated build leaves packman cache folders only Administrators can access, which then
REM break every normal build. "net session" only succeeds with admin rights.
net session >nul 2>&1
if %errorlevel%==0 (
    echo [ERROR] Do not run build.bat as administrator: it leaves packman cache folders your
    echo         normal account cannot use. Run it from a normal shell.
    exit /b 1
)

REM Each dependency is versioned independently under its own path segment
REM (<CDN_BASE>/<lib>/<version>/<archive>), so bumping one lib's version never forces
REM re-uploading another unchanged lib.
set "SL_ZED_VERSION=5.2.0"
set "SL_ZED_SIM2REAL_VERSION=1.0.0"
set "BUILD_PATH=_build\windows-x86_64\release\exts\sl.sensor.camera\bin"
set "BIN_TARGET=exts\sl.sensor.camera\bin"
set "CDN_BASE=https://stereolabs.sfo2.cdn.digitaloceanspaces.com/utils/zed_isaac_sim"
set "SL_ZED_FILENAME=sl_zed64_windows_x86_64_!SL_ZED_VERSION!.tar.gz"
set "SL_ZED_DOWNLOAD_URL=!CDN_BASE!/sl_zed/!SL_ZED_VERSION!/!SL_ZED_FILENAME!"
REM sl_zed_sim2real (ZED Sim2Real model) is fetched from the CDN like sl_zed, in its own archive.
set "SL_ZED_SIM2REAL_FILENAME=sl_zed_sim2real_windows_x86_64_!SL_ZED_SIM2REAL_VERSION!.tar.gz"
set "SL_ZED_SIM2REAL_URL=!CDN_BASE!/sl_zed_sim2real/!SL_ZED_SIM2REAL_VERSION!/!SL_ZED_SIM2REAL_FILENAME!"
REM Windows' own tar: from Git Bash, a bare "tar" resolves to Git's GNU tar, which cannot open
REM the backslash -C path.
set "TAR=%SystemRoot%\System32\tar.exe"

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

REM 2. Download and Extract sl_zed library. bin\sl_zed.version holds the downloaded version, so
REM changing SL_ZED_VERSION downloads the library again.
set "SL_ZED_INSTALLED="
if exist "%BIN_TARGET%\sl_zed.version" set /p SL_ZED_INSTALLED=<"%BIN_TARGET%\sl_zed.version"
if not exist "%BIN_TARGET%\sl_zed64.dll" set "SL_ZED_INSTALLED="
if not "!SL_ZED_INSTALLED!"=="!SL_ZED_VERSION!" (
    echo [INFO] Downloading sl_zed !SL_ZED_VERSION!...

    powershell -Command "Invoke-WebRequest -Uri '!SL_ZED_DOWNLOAD_URL!' -OutFile '%BIN_TARGET%\!SL_ZED_FILENAME!'"
    if errorlevel 1 (
        echo [ERROR] Failed to download library from !SL_ZED_DOWNLOAD_URL!
        exit /b 1
    )

    echo [INFO] Extracting !SL_ZED_FILENAME!...
    "%TAR%" -xzvf "%BIN_TARGET%\!SL_ZED_FILENAME!" -C "%BIN_TARGET%"
    if errorlevel 1 (
        echo [ERROR] Failed to extract library.
        exit /b 1
    )

    REM --- NEW: Cleanup the archive after extraction ---
    echo [INFO] Cleaning up archive...
    del /f /q "%BIN_TARGET%\!SL_ZED_FILENAME!"
    (echo !SL_ZED_VERSION!)>"%BIN_TARGET%\sl_zed.version"
) else (
    echo [INFO] sl_zed !SL_ZED_VERSION! already downloaded, skipping.
)

REM 2b. Download and Extract the sl_zed_sim2real library (ZED Sim2Real model). Optional:
REM sim2real degrades gracefully if absent, so a missing archive is a warning, not an error.
REM bin\sl_zed_sim2real.version works like sl_zed.version.
set "SL_ZED_SIM2REAL_INSTALLED="
if exist "%BIN_TARGET%\sl_zed_sim2real.version" set /p SL_ZED_SIM2REAL_INSTALLED=<"%BIN_TARGET%\sl_zed_sim2real.version"
if not exist "%BIN_TARGET%\sl_zed_sim2real.dll" set "SL_ZED_SIM2REAL_INSTALLED="
if not "!SL_ZED_SIM2REAL_INSTALLED!"=="!SL_ZED_SIM2REAL_VERSION!" (
    echo [INFO] Downloading sl_zed_sim2real !SL_ZED_SIM2REAL_VERSION!...
    powershell -Command "try { Invoke-WebRequest -Uri '!SL_ZED_SIM2REAL_URL!' -OutFile '%BIN_TARGET%\!SL_ZED_SIM2REAL_FILENAME!' -ErrorAction Stop } catch { exit 1 }"
    if errorlevel 1 (
        echo [WARN] Could not download sl_zed_sim2real from !SL_ZED_SIM2REAL_URL!
        echo [WARN] ZED Sim2Real will be disabled at runtime.
    ) else (
        echo [INFO] Extracting !SL_ZED_SIM2REAL_FILENAME!...
        "%TAR%" -xzf "%BIN_TARGET%\!SL_ZED_SIM2REAL_FILENAME!" -C "%BIN_TARGET%"
        if errorlevel 1 (
            echo [WARN] Could not extract !SL_ZED_SIM2REAL_FILENAME!
        ) else (
            (echo !SL_ZED_SIM2REAL_VERSION!)>"%BIN_TARGET%\sl_zed_sim2real.version"
        )
        del /f /q "%BIN_TARGET%\!SL_ZED_SIM2REAL_FILENAME!"
    )
) else (
    echo [INFO] sl_zed_sim2real !SL_ZED_SIM2REAL_VERSION! already downloaded, skipping.
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

REM 5. Sync the downloaded DLLs into the build tree first, so _build is runnable and copying the
REM build artifacts back cannot replace them with an older copy left in _build.
copy /y "%BIN_TARGET%\sl_zed64.dll" "%BUILD_PATH%\sl_zed64.dll" >nul
if exist "%BIN_TARGET%\sl_zed_sim2real.dll" copy /y "%BIN_TARGET%\sl_zed_sim2real.dll" "%BUILD_PATH%\sl_zed_sim2real.dll" >nul
echo [INFO] Syncing build artifacts...
xcopy /e /i /y "%BUILD_PATH%\*" "%BIN_TARGET%"

REM 6. Remove generated __ogn_files_prebuilt file
if exist "exts\sl.sensor.camera\sl\sensor\camera\ogn\__ogn_files_prebuilt" (
    REM echo [INFO] Removing __ogn_files_prebuilt file...
    del /f /q "exts\sl.sensor.camera\sl\sensor\camera\ogn\__ogn_files_prebuilt"
)

REM 7. Stage license files so repo package includes them in the release archive.
REM _build\<platform>\<config>\PACKAGE-LICENSES links here, and the packager keeps it.
if not exist "_build\PACKAGE-LICENSES" mkdir "_build\PACKAGE-LICENSES"
copy /y "LICENSE" "_build\PACKAGE-LICENSES\LICENSE" >nul
copy /y "THIRD_PARTY_NOTICES.md" "_build\PACKAGE-LICENSES\THIRD_PARTY_NOTICES.md" >nul
copy /y "LICENSES\Apache-2.0.txt" "_build\PACKAGE-LICENSES\Apache-2.0.txt" >nul

echo [SUCCESS] Process complete.