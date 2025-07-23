@echo off
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0


set "BUILD_PATH=_build/windows-x86_64/release/exts/sl.sensor.camera.bridge"

REM Remove old build binaries
del /q exts\sl.sensor.camera.bridge\bin\sl.sensor.camera.bridge.plugin*

REM Call repo.bat (must exist as a .bat or .cmd)
call "%SCRIPT_DIR%repo.bat" build %*
if errorlevel 1 exit /b %ERRORLEVEL%

REM Copy build artifacts
xcopy /e /i /y "%BUILD_PATH%\bin\*" "exts\sl.sensor.camera.bridge\bin"
xcopy /e /i /y "%BUILD_PATH%\ogn" "exts\sl.sensor.camera.bridge\ogn"
