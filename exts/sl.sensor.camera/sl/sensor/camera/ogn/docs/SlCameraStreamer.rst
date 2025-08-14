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

    "Camera Model (*inputs:cameraModel*)", "``token``", "ZED Camera model. Can be either ZED_X, ZED_X_Mini", "ZED_X"
    "", "Metadata", "*allowedTokens* = ZED_X,ZED_X_Mini", ""
    "ZED Camera prim (*inputs:cameraPrim*)", "``target``", "ZED Camera prim used to stream data", "None"
    "ExecIn (*inputs:execIn*)", "``execution``", "Triggers execution", "0"
    "FPS (*inputs:fps*)", "``uint``", "Camera stream frame rate. Can be either 60, 30 or 15.", "30"
    "IPC (*inputs:ipc*)", "``bool``", "Stream data using IPC (Only available on Linux). This improve streaming performances when streaming to the same machine", "True"
    "Resolution (*inputs:resolution*)", "``token``", "Camera stream resolution. Can be either HD1200, HD1080 or SVGA", "HD1200"
    "", "Metadata", "*allowedTokens* = HD1200,HD1080,SVGA", ""
    "Streaming port (*inputs:streamingPort*)", "``uint``", "Streaming port - unique per camera", "30000"


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

