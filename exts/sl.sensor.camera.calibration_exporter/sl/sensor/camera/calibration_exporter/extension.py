# SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-FileCopyrightText: Copyright (c) 2023-2026 Stereolabs. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Modified from the Isaac Sim UI extension template
# (isaacsim.examples.extension/template_source_files). See THIRD_PARTY_NOTICES.md.

import asyncio
import gc

import carb
import omni
import omni.kit.commands
import omni.ui as ui
import omni.usd
from omni.kit.menu.utils import add_menu_items, remove_menu_items
from omni.usd import StageEventType

from .global_variables import EXTENSION_TITLE

# isaacsim.gui.components (and ui_builder, which needs it) are imported in on_startup: this
# module has to import in a plain Kit app, which the extension tests run in, and where Isaac Sim
# is absent. Nothing here is usable without it, so the extension just does not open there.


class Extension(omni.ext.IExt):
    def on_startup(self, ext_id: str):
        """Initialize extension and UI elements"""
        try:
            from isaacsim.gui.components.element_wrappers import ScrollingWindow
            from isaacsim.gui.components.menu import MenuItemDescription

            from .ui_builder import UIBuilder
        except ImportError as exc:
            self._window = None
            self._menu_items = []
            carb.log_info(f"[ZED][Calibration Exporter] Isaac Sim UI components unavailable "
                          f"({exc}); the exporter window is not registered.")
            return

        self.ext_id = ext_id
        self._usd_context = omni.usd.get_context()

        # Build Window
        self._window = ScrollingWindow(
            title=EXTENSION_TITLE, width=600, height=500, visible=False, dockPreference=ui.DockPreference.LEFT_BOTTOM
        )
        self._window.set_visibility_changed_fn(self._on_window)

        action_registry = omni.kit.actions.core.get_action_registry()
        action_registry.register_action(
            ext_id,
            f"CreateUIExtension:{EXTENSION_TITLE}",
            self._menu_callback,
            description=f"Add {EXTENSION_TITLE} Extension to UI toolbar",
        )
        self._menu_items = [
            MenuItemDescription(name=EXTENSION_TITLE, onclick_action=(ext_id, f"CreateUIExtension:{EXTENSION_TITLE}"))
        ]

        add_menu_items(self._menu_items, "Stereolabs")

        self.ui_builder = UIBuilder()
        self._stage_event_sub = None

    def on_shutdown(self):
        if not self._menu_items:
            return   # never started: Isaac Sim UI components were unavailable
        remove_menu_items(self._menu_items, "Stereolabs")

        action_registry = omni.kit.actions.core.get_action_registry()
        action_registry.deregister_action(self.ext_id, f"CreateUIExtension:{EXTENSION_TITLE}")

        if self._window:
            self._window = None
        self.ui_builder.cleanup()
        gc.collect()

    def _on_window(self, visible):
        if self._window.visible:
            self._usd_context = omni.usd.get_context()
            events = self._usd_context.get_stage_event_stream()
            self._stage_event_sub = events.create_subscription_to_pop(self._on_stage_event)

            self._build_ui()
        else:
            self._usd_context = None
            self._stage_event_sub = None
            self.ui_builder.cleanup()

    def _build_ui(self):
        with self._window.frame:
            with ui.VStack(spacing=5, height=0):
                self._build_extension_ui()

        async def dock_window():
            await omni.kit.app.get_app().next_update_async()

            def dock(space, name, location, pos=0.5):
                window = omni.ui.Workspace.get_window(name)
                if window and space:
                    window.dock_in(space, location, pos)
                return window

            tgt = ui.Workspace.get_window("Viewport")
            dock(tgt, EXTENSION_TITLE, omni.ui.DockPosition.LEFT, 0.33)
            await omni.kit.app.get_app().next_update_async()

        self._task = asyncio.ensure_future(dock_window())

    #################################################################
    # Functions below this point call user functions
    #################################################################

    def _menu_callback(self):
        self._window.visible = not self._window.visible

    def _on_stage_event(self, event):
        if event.type == int(StageEventType.OPENED) or event.type == int(StageEventType.CLOSED):
            self.ui_builder.cleanup()

    def _build_extension_ui(self):
        # Call user function for building UI
        self.ui_builder.build_ui()
