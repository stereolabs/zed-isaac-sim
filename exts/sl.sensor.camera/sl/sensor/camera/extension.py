# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT

import traceback

import carb
import omni.ext


# Python OGN nodes are registered automatically by OmniGraph from the committed
# manifest (ogn/nodes.json) - same path the C++ node uses. Do not register them
# manually here too, or OmniGraph aborts with "registered twice".
class SlSensorCameraExtension(omni.ext.IExt):
	def on_startup(self, ext_id):
		carb.log_info(f"[sl.sensor.camera] Startup ({ext_id})")
		self._lens_panel = None

		# Register the Property-panel templates that filter the Resolution
		# dropdown by the selected Camera Model (see templates/ folder).
		try:
			import omni.graph.ui
			widget = omni.graph.ui.ComputeNodeWidget.get_instance()
			if widget is not None:
				widget.add_template_path(__file__)
				carb.log_info("[sl.sensor.camera] Registered node property templates")
			else:
				carb.log_warn("[sl.sensor.camera] ComputeNodeWidget unavailable; node property templates not registered")
		except Exception:
			carb.log_warn("[sl.sensor.camera] Failed to register node property templates")
			carb.log_warn(traceback.format_exc())

		# Register the "ZED Cameras" lens panel (Stereolabs menu). GUI-only:
		# skip quietly in headless sessions where the UI stack is unavailable.
		try:
			from .ui import ZedLensPanel
			self._lens_panel = ZedLensPanel(ext_id)
			carb.log_info("[sl.sensor.camera] Registered the ZED Cameras lens panel")
		except ImportError:
			carb.log_info("[sl.sensor.camera] UI stack unavailable; ZED Cameras lens panel not registered")
		except Exception:
			carb.log_warn("[sl.sensor.camera] Failed to register the ZED Cameras lens panel")
			carb.log_warn(traceback.format_exc())

	def on_shutdown(self):
		if getattr(self, "_lens_panel", None) is not None:
			try:
				self._lens_panel.destroy()
			except Exception:
				carb.log_warn(traceback.format_exc())
			self._lens_panel = None
		carb.log_info("[sl.sensor.camera] Shutdown")
