.. _sl_sensor_camera_ZED_Camera_1:

.. _sl_sensor_camera_ZED_Camera:

.. ================================================================================
.. THIS PAGE IS AUTO-GENERATED. DO NOT MANUALLY EDIT.
.. ================================================================================

:orphan:

.. meta::
    :title: ZED camera streamer
    :keywords: lang-en omnigraph node Stereolabs camera z-e-d_-camera


ZED camera streamer
===================

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

    "ZED Camera prim (*inputs:camera_prim*)", "``target``", "ZED Camera prim used to stream data", "None"
    "ExecIn (*inputs:exec_in*)", "``execution``", "Triggers execution", "0"
    "FPS (*inputs:fps*)", "``uint``", "Camera stream frame rate. Can be either 60, 30 or 15.", "30"
    "Resolution (*inputs:resolution*)", "``token``", "Camera stream resolution. Can be either HD1200, HD1080 or SVGA", "HD1200"
    "", "Metadata", "*allowedTokens* = HD1200,HD1080,SVGA", ""
    "Serial number (*inputs:serial_number*)", "``uint``", "Serial number (identification) of the camera to stream, can be left to default. It must be of one of the compatible values: 40976320, 41116066, 49123828, 45626933, 47890353, 45263213, 47800035, 47706147", "40976320"
    "Streaming port (*inputs:streaming_port*)", "``uint``", "Streaming port - unique per camera", "30000"
    "Use system time (*inputs:use_system_time*)", "``bool``", "Override simulation time with system time for image timestamps", "False"


Metadata
--------
.. csv-table::
    :header: "Name", "Value"
    :widths: 30,70

    "Unique ID", "sl.sensor.camera.ZED_Camera"
    "Version", "1"
    "Extension", "sl.sensor.camera"
    "Has State?", "False"
    "Implementation Language", "Python"
    "Default Memory Type", "cpu"
    "Generated Code Exclusions", "None"
    "uiName", "ZED camera streamer"
    "Categories", "Stereolabs"
    "__categoryDescriptions", "Stereolabs,Nodes used with the Stereolabs ZED SDK"
    "Generated Class Name", "SlCameraStreamerDatabase"
    "Python Module", "sl.sensor.camera"

