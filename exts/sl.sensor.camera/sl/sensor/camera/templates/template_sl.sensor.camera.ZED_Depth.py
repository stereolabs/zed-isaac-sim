"""Property-panel template for the "ZED Capture" node (sl.sensor.camera.ZED_Depth).

The node type id still says ZED_Depth: it is what every saved user graph references, and
the display name is the only part that changed.

ComputeNodeWidget.load_template() imports this file and instantiates CustomLayout.
"""
from sl.sensor.camera.templates._camera_layout import CustomLayout  # noqa: F401
