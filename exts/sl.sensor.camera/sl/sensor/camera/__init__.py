import traceback

import carb
import omni.ext

from .nodes.SlCameraOneStreamer import SlCameraOneStreamer
from .nodes.SlCameraStreamer import SlCameraStreamer
from .ogn.SlCameraOneStreamerDatabase import SlCameraOneStreamerDatabase
from .ogn.SlCameraStreamerDatabase import SlCameraStreamerDatabase


class SlSensorCameraExtension(omni.ext.IExt):
	def on_startup(self, ext_id):
		carb.log_info(f"[sl.sensor.camera] Startup ({ext_id})")
		try:
			SlCameraStreamerDatabase.register(SlCameraStreamer)
			SlCameraOneStreamerDatabase.register(SlCameraOneStreamer)
			carb.log_info("[sl.sensor.camera] Registered Python OGN node types")
		except Exception:
			carb.log_error("[sl.sensor.camera] Failed to register Python OGN node types")
			carb.log_error(traceback.format_exc())

	def on_shutdown(self):
		carb.log_info("[sl.sensor.camera] Shutdown")
		try:
			SlCameraOneStreamerDatabase.deregister()
			SlCameraStreamerDatabase.deregister()
		except Exception:
			carb.log_warn("[sl.sensor.camera] Failed to deregister one or more Python OGN node types")
			carb.log_warn(traceback.format_exc())
