# SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import os
from typing import List

import omni.ui as ui
import omni.usd
from isaacsim.gui.components.element_wrappers import (
    Button,
    DropDown,
    CollapsableFrame,
    StringField
)
from isaacsim.gui.components.ui_utils import get_style

from .calibration import (
    write_stereo_calibration_file,
    generate_virtual_sn,
    get_base_models,
    get_allowed_lens_types,
    compose_model,
)

class UIBuilder:
    def __init__(self):
        # Frames are sub-windows that can contain multiple UI elements
        self.frames = []

        # UI elements created using a UIElementWrapper from isaacsim.gui.components.element_wrappers
        self.wrapped_ui_elements = []
        self.serial_number = -1
        self.base_model = "ZED_XONE_GS"
        self.lens_type = "Wide"
        self.camera_model = "ZED_XONE_GS"

    ###################################################################################
    #           The Functions Below Are Called Automatically By extension.py
    ###################################################################################

    def on_menu_callback(self):
        """Callback for when the UI is opened from the toolbar.
        This is called directly after build_ui().
        """
        pass

    def on_timeline_event(self, event):
        """Callback for Timeline events (Play, Pause, Stop)

        Args:
            event (omni.timeline.TimelineEventType): Event Type
        """
        pass

    def on_physics_step(self, step):
        """Callback for Physics Step.
        Physics steps only occur when the timeline is playing

        Args:
            step (float): Size of physics step
        """
        pass

    def on_stage_event(self, event):
        """Callback for Stage Events

        Args:
            event (omni.usd.StageEventType): Event Type
        """
        pass

    def cleanup(self):
        """
        Called when the stage is closed or the extension is hot reloaded.
        Perform any necessary cleanup such as removing active callback functions
        Buttons imported from isaacsim.gui.components.element_wrappers implement a cleanup function that should be called
        """
        # None of the UI elements in this template actually have any internal state that needs to be cleaned up.
        # But it is best practice to call cleanup() on all wrapped UI elements to simplify development.
        for ui_elem in self.wrapped_ui_elements:
            ui_elem.cleanup()

    def build_ui(self):
        """
        Build a custom UI tool to run your extension.
        This function will be called any time the UI window is closed and reopened.
        """
        self.serial_number = generate_virtual_sn()
        self._create_calibration_frame()

    def _create_calibration_frame(self):
        self._calibration_frame = CollapsableFrame("Virtual Stereo calibration", collapsed=False)
        with self._calibration_frame:
            with ui.VStack(style=get_style(), spacing=5, height=0):

                def pick_selected_prim(field: StringField):
                    selection = omni.usd.get_context().get_selection().get_selected_prim_paths()
                    if not selection:
                        print("No prim selected in the stage")
                        return
                    # Just take the first selected prim
                    selected_prim = selection[0]
                    field.set_value(selected_prim)

                with ui.HStack():
                    self.left_cam_field = StringField(
                        "Left Camera prim",
                        default_value="",
                        tooltip="Left camera of the virtual stereo camera",
                        read_only=False,
                        multiline_okay=False,
                        use_folder_picker=False
                    )
                    ui.Button("Select", clicked_fn=lambda: pick_selected_prim(self.left_cam_field))
                    self.wrapped_ui_elements.append(self.left_cam_field)


                with ui.HStack():
                    self.right_cam_field = StringField(
                        "Right Camera prim",
                        default_value="",
                        tooltip="Right camera of the virtual stereo camera",
                        read_only=False,
                        multiline_okay=False,
                        use_folder_picker=False
                    )
                    ui.Button("Select", clicked_fn=lambda: pick_selected_prim(self.right_cam_field))
                    self.wrapped_ui_elements.append(self.right_cam_field)

                with ui.VStack(style=get_style(), spacing=5, height=0):
                    # Camera model (base) + Lens type, split like the ZED camera
                    # helper nodes. The lens list is filtered to the selected base;
                    # both recompose into the composite token used for calibration.
                    model_dropdown = DropDown(
                        "Camera model",
                        tooltip="Camera model used to create a virtual stereo camera",
                        populate_fn=get_base_models,
                        on_selection_fn=self._on_model_selection,
                    )
                    self.wrapped_ui_elements.append(model_dropdown)

                    self.lens_dropdown = DropDown(
                        "Lens type",
                        tooltip="Lens fitted to the camera",
                        populate_fn=lambda: get_allowed_lens_types(self.base_model),
                        on_selection_fn=self._on_lens_selection,
                    )
                    self.wrapped_ui_elements.append(self.lens_dropdown)

                    # This does not happen automatically; repopulating the base
                    # cascades into the lens dropdown via _on_model_selection.
                    model_dropdown.repopulate()

                self.serial_number_field = StringField(
                    "Serial number",
                    default_value=str(self.serial_number),
                    tooltip="Serial number of the stereo camera",
                    read_only=False,
                    multiline_okay=False,
                    use_folder_picker=True
                )
                self.wrapped_ui_elements.append(self.serial_number_field)

                button = Button(
                    "Generate calibration",
                    "Generate",
                    tooltip="Click This Button to generate calibration and save it on disk",
                    on_click_fn=self._on_button_clicked_fn,
                )
                self.wrapped_ui_elements.append(button)

    ######################################################################################
    # Functions Below This Point Are Callback Functions Attached to UI Element Wrappers
    ######################################################################################


    def _on_button_clicked_fn(self):
        write_stereo_calibration_file(left_prim_path=self.left_cam_field.get_value(), right_prim_path=self.right_cam_field.get_value(),
            serial_number=self.serial_number_field.get_value(), camera_model=self.camera_model)

    def _on_model_selection(self, item: str):
        self.base_model = item
        # Re-filter the lens list for the new base; repopulate cascades into
        # _on_lens_selection, which recomposes the composite token.
        self.lens_dropdown.repopulate()

    def _on_lens_selection(self, item: str):
        self.lens_type = item
        self.camera_model = compose_model(self.base_model, self.lens_type)
