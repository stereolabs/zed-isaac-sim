.. _sl_sensor_camera_ZED_Camera_3:

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
    "", "Metadata", "*allowedTokens* = ZED_X,ZED_XM,ZED_X_Nano,ZED_M", ""
    "ZED Camera Prim (*inputs:cameraPrim*)", "``target``", "ZED Camera prim used to stream data.", "None"
    "", "Metadata", "*literalOnly* = 1", ""
    "", "Metadata", "*allowMultiInputs* = 0", ""
    "Streaming Chunk Size (*inputs:chunkSize*)", "``uint``", "Chunk size in bytes. (Used only if IPC is disabled)", "4096"
    "ZED-twin camera model (*inputs:enableTwin*)", "``bool``", "Apply the Imatest-calibrated ZED-twin camera model (MTF, vignetting, AE, bloom, AWB, tone, sharpening, sensor noise) to the streamed frames", "False"
    "ExecIn (*inputs:execIn*)", "``execution``", "Triggers execution", "0"
    "FPS (*inputs:fps*)", "``uint``", "Camera stream frame rate.", "60"
    "Lens Type (*inputs:lensType*)", "``token``", "Lens fitted to the camera. Options shown depend on the selected camera model.", "Wide"
    "", "Metadata", "*allowedTokens* = Wide,Narrow", ""
    "Resolution (*inputs:resolution*)", "``token``", "Camera stream resolution.", "SVGA"
    "", "Metadata", "*allowedTokens* = HD2K,HD1200,HD1080,HD720,SVGA,VGA", ""
    "Streaming Port (*inputs:streamingPort*)", "``uint``", "Unique port per camera.", "30000"
    "Transport layer mode (*inputs:transportLayerMode*)", "``token``", "Communication protocol used to send data to the ZED SDK. IPC improves streaming performance when streaming to the same machine (Linux and Windows)", "BOTH"
    "", "Metadata", "*allowedTokens* = BOTH,NETWORK,IPC", ""
    "Twin scene lux (*inputs:twinSceneLux*)", "``float``", "Absolute scene illuminance (lux) for the twin's gain-ceiling AE and gain-coupled noise. 0 = bright scene", "0.0"


Metadata
--------
.. csv-table::
    :header: "Name", "Value"
    :widths: 30,70

    "Unique ID", "sl.sensor.camera.ZED_Camera"
    "Version", "3"
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

