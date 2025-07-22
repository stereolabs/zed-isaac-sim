.. _sl_sensor_camera_bridge_OgnZEDSimCameraNode_1:

.. _sl_sensor_camera_bridge_OgnZEDSimCameraNode:

.. ================================================================================
.. THIS PAGE IS AUTO-GENERATED. DO NOT MANUALLY EDIT.
.. ================================================================================

:orphan:

.. meta::
    :title: ZED Stream
    :keywords: lang-en omnigraph node function bridge ogn-z-e-d-sim-camera-node


ZED Stream
==========

.. <description>



.. </description>


Installation
------------

To use this node enable :ref:`sl.sensor.camera.bridge<ext_sl_sensor_camera_bridge>` in the Extension Manager.


Inputs
------
.. csv-table::
    :header: "Name", "Type", "Descripton", "Default"
    :widths: 20, 20, 50, 10

    "Buffer Size Left (*inputs:bufferSizeLeft*)", "``uint64``", "Size (in bytes) of the buffer (0 if the input is a texture)", "0"
    "Buffer Size Right (*inputs:bufferSizeRight*)", "``uint64``", "Size (in bytes) of the buffer (0 if the input is a texture)", "0"
    "Camera Model (*inputs:cameraModel*)", "``string``", "ZED Camera model. Can be either ZED_X, ZED_X_Mini", "ZED_X"
    "Data Ptr Left (*inputs:dataPtrLeft*)", "``uint64``", "Pointer to the raw data (cuda device pointer or host pointer)", "0"
    "Data Ptr Right (*inputs:dataPtrRight*)", "``uint64``", "Pointer to the raw data (cuda device pointer or host pointer)", "0"
    "ExecIn (*inputs:execIn*)", "``execution``", "Triggers execution", "0"
    "Fps (*inputs:fps*)", "``uint``", "frame rate", "30"
    "Height (*inputs:height*)", "``uint``", "Camera stream resolution. Can be either HD1200, HD1080 or SVGA", "1200"
    "Ipc (*inputs:ipc*)", "``bool``", "sream data using IPC (only available on Linux)", "False"
    "Linear Acceleration (*inputs:linearAcceleration*)", "``vectord[3]``", "imu acceleration", "[0.0, 0.0, 0.0]"
    "Orientation (*inputs:orientation*)", "``quatd[4]``", "imu orientation", "[0.0, 0.0, 0.0, 1.0]"
    "Port (*inputs:port*)", "``uint``", "server port", "5561"
    "Simulation Time (*inputs:simulationTime*)", "``double``", "simulation time", "0.0"
    "Stream (*inputs:stream*)", "``bool``", "stream", "False"
    "System Time (*inputs:systemTime*)", "``double``", "system time", "0.0"
    "Width (*inputs:width*)", "``uint``", "Camera stream resolution. Can be either HD1200, HD1080 or SVGA", "1920"


Metadata
--------
.. csv-table::
    :header: "Name", "Value"
    :widths: 30,70

    "Unique ID", "sl.sensor.camera.bridge.OgnZEDSimCameraNode"
    "Version", "1"
    "Extension", "sl.sensor.camera.bridge"
    "Has State?", "False"
    "Implementation Language", "C++"
    "Default Memory Type", "cpu"
    "Generated Code Exclusions", "None"
    "uiName", "ZED Stream"
    "Categories", "function"
    "Generated Class Name", "OgnZEDSimCameraNodeDatabase"
    "Python Module", "sl.sensor.camera.bridge"

