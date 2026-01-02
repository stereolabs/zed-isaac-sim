.. _sl_sensor_camera_ZED_Camera_2:

.. _sl_sensor_camera_ZED_Camera:

.. ================================================================================
.. THIS PAGE IS AUTO-GENERATED. DO NOT MANUALLY EDIT.
.. ================================================================================

:orphan:

.. meta::
    :title: ZED Camera Helper
    :keywords: lang-en omnigraph node Stereolabs camera z-e-d_-camera


ZED Camera Helper
=================

.. <description>

Streams ZED camera data to the ZED SDK

.. </description>


Installation
------------

To use this node enable :ref:`sl.sensor.camera<ext_sl_sensor_camera>` in the Extension Manager.


Inputs
------
.. csv-table::
    :header: "Name", "Type", "Descripton", "Default"
    :widths: 20, 20, 50, 10

    "Streaming Bitrate (*inputs:bitrate*)", "``uint``", "Bitrate in Kbps. (Used only if IPC is disabled)", "8000"
    "Camera Model (*inputs:cameraModel*)", "``token``", "ZED Camera model.", "ZED_X"
    "", "Metadata", "*allowedTokens* = ZED_X,ZED_XM,ZED_X_4MM,ZED_XM_4MM", ""
    "ZED Camera Prim (*inputs:cameraPrim*)", "``target``", "ZED Camera prim used to stream data.", "None"
    "", "Metadata", "*literalOnly* = 1", ""
    "", "Metadata", "*allowMultiInputs* = 0", ""
    "Streaming Chunk Size (*inputs:chunkSize*)", "``uint``", "Chunk size in bytes. (Used only if IPC is disabled)", "4096"
    "ExecIn (*inputs:execIn*)", "``execution``", "Triggers execution", "0"
    "FPS (*inputs:fps*)", "``uint``", "Camera stream frame rate.", "30"
    "Resolution (*inputs:resolution*)", "``token``", "Camera stream resolution.", "HD1200"
    "", "Metadata", "*allowedTokens* = HD1200,HD1080,SVGA", ""
    "Streaming Port (*inputs:streamingPort*)", "``uint``", "Unique port per camera.", "30000"
    "Transport layer mode (*inputs:transportLayerMode*)", "``token``", "Communication protocol used to send data to the ZED SDK. IPC (Only available on Linux)improves streaming performances when streaming to the same machine", "BOTH"
    "", "Metadata", "*allowedTokens* = BOTH,NETWORK,IPC", ""


Metadata
--------
.. csv-table::
    :header: "Name", "Value"
    :widths: 30,70

    "Unique ID", "sl.sensor.camera.ZED_Camera"
    "Version", "2"
    "Extension", "sl.sensor.camera"
    "Has State?", "False"
    "Implementation Language", "Python"
    "Default Memory Type", "cpu"
    "Generated Code Exclusions", "None"
    "uiName", "ZED Camera Helper"
    "Categories", "Stereolabs"
    "__categoryDescriptions", "Stereolabs,Nodes used with the Stereolabs ZED SDK"
    "Generated Class Name", "SlCameraStreamerDatabase"
    "Python Module", "sl.sensor.camera"

