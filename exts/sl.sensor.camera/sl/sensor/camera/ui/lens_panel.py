# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""'ZED Cameras' panel: at-a-glance lens control for the ZED cameras in the stage.

A dockable window (Stereolabs menu) that lists every placed ZED camera (thumbnail,
prim name, model) with its lens shown as segmented buttons (Wide | Narrow |
Fisheye): the current lens is highlighted, only the lenses the model supports are
shown, and one click switches. It complements the per-prim variant dropdown in the
Property window; both edit the same 'lens' variant selection, which the streamer
picks up through utils.resolve_camera_model, so the visible lens and the streamed
camera model stay in sync.

Fixed-lens models (ZED M, ZED X Nano, ZED X One UHD) are listed with their single
lens as a static tag (e.g. "Wide lens") instead of buttons.

A Settings tab holds the camera mode (the simCameraMode setting) and the stream timing (the
streamTiming setting), shared by every camera.
"""
import asyncio
import functools

import carb
import omni.kit.app
import omni.ui as ui
import omni.usd
from isaacsim.gui.components.element_wrappers import ScrollingWindow
from isaacsim.gui.components.menu import MenuItemDescription
from omni.kit.menu.utils import add_menu_items, remove_menu_items
from omni.usd import StageEventType
from pxr import Tf, Usd

from .. import retime, sdk_virtual_camera
from ..utils import find_placed_zed_cameras, get_camera_thumbnail_path, get_lens_type

_TITLE = "ZED Cameras"
_MENU_GROUP = "Stereolabs"
_LENS_ORDER = ("Wide", "Narrow", "Fisheye")
_TABS = ("Cameras", "Settings")
_CAMERAS_TAB, _SETTINGS_TAB = range(len(_TABS))
# (setting value, combo label, tooltip), in combo order. The setting's own tooltip
# is on its name, the selected option's on the combo.
_MODES = (
    (sdk_virtual_camera.MODE_VIRTUAL, "SDK virtual camera",
     "The ZED SDK generates each camera's serial number and calibration, which the receiver\n"
     "regenerates from the serial number. Any number of cameras.\n"
     "The receiver needs ZED SDK 5.6.0 or newer."),
    (sdk_virtual_camera.MODE_LEGACY, "Legacy serial number",
     "Serial numbers from the SDK whitelist, calibration from their reserved file.\n"
     "A few cameras per model and lens. For receivers older than 5.6.0."),
)
_MODE_TOOLTIP = (
    "Which serial numbers and calibration the streamed cameras use.\n"
    "Applies from the next Play."
)
_TIMINGS = (
    (retime.TIMING_FIT, "Fit the stream fps",
     "A timing where no app update spans more than one frame is kept (60 Hz with a 15, 30 or\n"
     "60 fps stream), otherwise the update rate goes to the highest multiple of the stream fps\n"
     "at or below it."),
    (retime.TIMING_FRAME, "One update per frame",
     "The app updates at the stream fps instead of a multiple of it, for machines that cannot\n"
     "keep up with 60 Hz updates. During Play the viewport refreshes at the stream fps, USD\n"
     "time-sampled animation plays slower, and a script that calls save_frame() itself at the\n"
     "stream fps can miss frames."),
    (retime.TIMING_OFF, "Keep the app's timing",
     "Play leaves the app's timing as it is. When an app update spans more than one frame,\n"
     "a stream can send fewer frames than its fps, at most one per app update."),
)
_TIMING_TOOLTIP = (
    "How Play sets the app's timing so each stream sends every frame. Stop puts it back.\n"
    "Applies from the next Play."
)

# omni.ui colors are 0xAABBGGRR. Accent = Stereolabs lime, RGB (187, 255, 36).
_ACCENT = 0xFF24FFBB
_BTN_OFF_BG = 0xFF3A3A3A
_BTN_OFF_HOVER = 0xFF4A4A4A
_TEXT_DIM = 0xFF9E9E9E
_TEXT_ON_ACCENT = 0xFF1E1E1E

# Bright, border-less tooltips (widget styles leak into their tooltip popup, so
# every styled widget with a tooltip carries this override).
_TOOLTIP_STYLE = {"color": 0xFFEEEEEE, "background_color": 0xFF1F1F1F, "border_width": 0}

_BTN_ON_STYLE = {
    "Button": {"background_color": _ACCENT, "border_radius": 3.0},
    "Button:hovered": {"background_color": _ACCENT},
    "Button.Label": {"color": _TEXT_ON_ACCENT},
    "Tooltip": _TOOLTIP_STYLE,
}
_BTN_OFF_STYLE = {
    "Button": {"background_color": _BTN_OFF_BG, "border_radius": 3.0},
    "Button:hovered": {"background_color": _BTN_OFF_HOVER},
    "Button.Label": {"color": 0xFFCCCCCC},
    "Tooltip": _TOOLTIP_STYLE,
}
_TAB_STYLE = {
    "Button": {"background_color": 0x0, "border_radius": 0.0},
    "Button:hovered": {"background_color": _BTN_OFF_BG},
    "Button.Label": {"color": _TEXT_DIM},
}
_TAB_ON_STYLE = {**_TAB_STYLE, "Button.Label": {"color": 0xFFEEEEEE}}


def _lens_sort_key(name: str):
    return _LENS_ORDER.index(name) if name in _LENS_ORDER else len(_LENS_ORDER)


class ZedLensPanel:
    """Owns the window, its Stereolabs menu entry and the stage/USD listeners."""

    def __init__(self, ext_id: str):
        self._ext_id = ext_id
        self._action_name = f"CreateUIExtension:{_TITLE}"
        self._usd_context = omni.usd.get_context()
        self._stage_event_sub = None
        self._usd_listener = None
        self._rebuild_pending = False
        # Kept on self: every stage selection change rebuilds the window.
        self._tab = _CAMERAS_TAB

        self._window = ScrollingWindow(
            title=_TITLE, width=460, height=380, visible=False,
            dockPreference=ui.DockPreference.LEFT_BOTTOM,
        )
        self._window.set_visibility_changed_fn(self._on_visibility_changed)

        action_registry = omni.kit.actions.core.get_action_registry()
        action_registry.register_action(
            ext_id, self._action_name, self._on_menu_click,
            description=f"Toggle the {_TITLE} lens panel",
        )
        self._menu_items = [
            MenuItemDescription(name=_TITLE, onclick_action=(ext_id, self._action_name))
        ]
        add_menu_items(self._menu_items, _MENU_GROUP)

        # Auto-open at startup: whoever loads the ZED extension is doing camera
        # work, so show the fleet at once (the menu entry toggles it off/on).
        # Deferred a frame so the workspace exists, then docked next to Content.
        self._window.visible = True
        asyncio.ensure_future(self._dock_deferred())

    async def _dock_deferred(self):
        await omni.kit.app.get_app().next_update_async()
        win = ui.Workspace.get_window(_TITLE)
        target = ui.Workspace.get_window("Content")
        if win and target:
            win.dock_in(target, ui.DockPosition.RIGHT, 0.35)

    # Lifecycle
    def destroy(self):
        self._unsubscribe()
        remove_menu_items(self._menu_items, _MENU_GROUP)
        omni.kit.actions.core.get_action_registry().deregister_action(self._ext_id, self._action_name)
        if self._window is not None:
            self._window.visible = False
            try:
                self._window.destroy()
            except AttributeError:
                pass  # wrapper without destroy(); the gc.collect below reaps it
            self._window = None
        import gc
        gc.collect()

    def _on_menu_click(self):
        self._window.visible = not self._window.visible

    def _on_visibility_changed(self, visible: bool):
        if visible:
            self._subscribe()
            self._build()
        else:
            self._unsubscribe()

    # Refreshing
    def _subscribe(self):
        events = self._usd_context.get_stage_event_stream()
        self._stage_event_sub = events.create_subscription_to_pop(self._on_stage_event)
        self._register_usd_listener()

    def _unsubscribe(self):
        self._stage_event_sub = None
        self._revoke_usd_listener()

    def _register_usd_listener(self):
        self._revoke_usd_listener()
        stage = self._usd_context.get_stage()
        if stage is not None:
            self._usd_listener = Tf.Notice.Register(
                Usd.Notice.ObjectsChanged, self._on_objects_changed, stage
            )

    def _revoke_usd_listener(self):
        if self._usd_listener is not None:
            self._usd_listener.Revoke()
            self._usd_listener = None

    def _on_stage_event(self, event):
        if event.type in (int(StageEventType.OPENED), int(StageEventType.CLOSED)):
            # New (or no) stage: rebind the USD listener and redo the list.
            self._register_usd_listener()
            self._schedule_rebuild()
        elif event.type == int(StageEventType.SELECTION_CHANGED):
            # Track stage selection so the selected camera's row outline follows.
            self._schedule_rebuild()

    def _on_objects_changed(self, notice, stage):
        # Structure changes (prim added/removed, variant selection switched) come
        # through as resyncs; per-frame attribute writes are info-only and are
        # ignored so a running sim does not spam rebuilds.
        if notice.GetResyncedPaths():
            self._schedule_rebuild()

    def _schedule_rebuild(self):
        """Coalesce rebuild requests into one rebuild on the next app update."""
        if self._rebuild_pending or self._window is None or not self._window.visible:
            return
        self._rebuild_pending = True

        async def _rebuild():
            await omni.kit.app.get_app().next_update_async()
            self._rebuild_pending = False
            if self._window is not None and self._window.visible:
                self._build()

        asyncio.ensure_future(_rebuild())

    # Actions
    def _set_lens(self, model_prim_path: str, lens: str):
        stage = self._usd_context.get_stage()
        prim = stage.GetPrimAtPath(model_prim_path) if stage else None
        if not prim or not prim.IsValid():
            carb.log_warn(f"[ZED] {model_prim_path} no longer exists; refreshing the lens panel.")
            self._schedule_rebuild()
            return
        prim.GetVariantSets().GetVariantSet("lens").SetVariantSelection(lens)
        # The variant switch resyncs the prim, which triggers the rebuild.

    def _select_in_stage(self, root_path: str, x, y, button, modifier):
        if button == 0:  # left click
            self._usd_context.get_selection().set_selected_prim_paths([root_path], True)

    # Building
    def _build(self):
        with self._window.frame:
            with ui.VStack(spacing=6, height=0):
                self._build_tab_bar()
                if self._tab == _SETTINGS_TAB:
                    self._build_settings()
                else:
                    self._build_cameras()

    def _show_tab(self, tab: int):
        self._tab = tab
        self._build()

    def _build_tab_bar(self):
        with ui.VStack(height=0, spacing=0):
            with ui.HStack(height=26):
                for tab, name in enumerate(_TABS):
                    selected = tab == self._tab
                    with ui.VStack(width=90, spacing=0):
                        ui.Button(name, style=_TAB_ON_STYLE if selected else _TAB_STYLE,
                                  clicked_fn=functools.partial(self._show_tab, tab))
                        ui.Rectangle(height=2, style={"background_color": _ACCENT if selected else 0x0})
                ui.Spacer()
            ui.Rectangle(height=1, style={"background_color": _BTN_OFF_BG})

    def _build_cameras(self):
        cameras = find_placed_zed_cameras(self._usd_context.get_stage())
        self._build_header(len(cameras))
        if not cameras:
            with ui.HStack(height=40):
                ui.Spacer(width=10)
                ui.Label(
                    "No ZED camera in the stage.\n"
                    "Reference a ZED asset (data/usd) to see it here.",
                    style={"color": _TEXT_DIM},
                )
            return
        for cam in cameras:
            self._build_row(cam)

    def _build_settings(self):
        with ui.HStack(height=22):
            ui.Spacer(width=10)
            ui.Label("Shared by every ZED camera. Changes apply from the next Play.", style={"color": _TEXT_DIM})
        self._build_setting_selector("Camera mode", _MODES, sdk_virtual_camera.get_mode_setting(),
                                     sdk_virtual_camera.set_mode, _MODE_TOOLTIP)
        self._build_setting_selector("Stream timing", _TIMINGS, retime.stream_timing(),
                                     retime.set_stream_timing, _TIMING_TOOLTIP)

    def _build_setting_selector(self, name: str, options, current: str, set_value, tooltip: str):
        """A combo over ``options``, (setting value, label, tooltip) triples, that calls ``set_value`` with the pick."""
        values = [value for value, _, _ in options]
        index = values.index(current)

        def on_pick(model):
            set_value(values[model.as_int])
            self._schedule_rebuild()  # so the combo's tooltip describes the new pick

        with ui.HStack(height=22):
            ui.Spacer(width=10)
            ui.Label(name, width=100, style={"Label": {"color": _TEXT_DIM}, "Tooltip": _TOOLTIP_STYLE},
                     tooltip=tooltip)
            combo = ui.ComboBox(index, *[label for _, label, _ in options],
                                style={"Tooltip": _TOOLTIP_STYLE}, tooltip=options[index][2])
            combo.model.get_item_value_model().add_value_changed_fn(on_pick)
            ui.Spacer(width=6)

    def _build_header(self, count: int):
        with ui.HStack(height=22):
            ui.Spacer(width=10)
            label = f"{count} camera{'s' if count != 1 else ''} in the stage" if count else ""
            ui.Label(label, style={"color": _TEXT_DIM})
            ui.Spacer()
            ui.Button("Refresh", width=70, clicked_fn=self._build, tooltip="Rescan the stage")
            ui.Spacer(width=6)

    def _is_row_selected(self, root_path: str) -> bool:
        """True when the camera root (or anything inside it) is selected in the stage."""
        for path in self._usd_context.get_selection().get_selected_prim_paths():
            if path == root_path or path.startswith(root_path + "/"):
                return True
        return False

    def _build_row(self, cam: dict):
        thumb = get_camera_thumbnail_path(cam["base_model"])
        root_name = cam["root_path"].rsplit("/", 1)[-1] or cam["root_path"]
        select_fn = functools.partial(self._select_in_stage, cam["root_path"])
        # Type-scoped so the row look (esp. the selection outline) does not leak
        # into the hover tooltip, which gets its own bright style.
        row_style = {
            "Rectangle": {"background_color": 0xFF2C2C2C, "border_radius": 4.0},
            "Tooltip": _TOOLTIP_STYLE,
        }
        if self._is_row_selected(cam["root_path"]):
            # Outline the row of the camera selected in the stage, in the same
            # accent as the selected lens button.
            row_style["Rectangle"].update({"border_color": _ACCENT, "border_width": 2.0})
        with ui.ZStack(height=58):
            # The background carries the click: labels/images without handlers are
            # mouse-transparent, so anywhere on the row selects the camera (the
            # lens buttons on top still consume their own clicks).
            ui.Rectangle(
                style=row_style,
                mouse_pressed_fn=select_fn,
                tooltip=f"{cam['root_path']}\n(click to select in the stage)",
            )
            with ui.HStack(spacing=8):
                ui.Spacer(width=2)
                if thumb:
                    # No fixed height: the widget spans the row and the texture is
                    # fit + centered, so the margins above/below are equal.
                    ui.Image(
                        thumb.replace("\\", "/"), width=52,
                        fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                        alignment=ui.Alignment.CENTER,
                    )
                else:
                    ui.Spacer(width=52)
                with ui.VStack(spacing=2, width=ui.Fraction(1)):
                    ui.Spacer()
                    ui.Label(root_name, height=18, style={"font_size": 15.0})
                    ui.Label(
                        cam["base_model"] + ("  ·  stereo" if cam["is_stereo"] else "  ·  mono"),
                        height=14, style={"color": _TEXT_DIM, "font_size": 12.0},
                    )
                    ui.Spacer()
                self._build_lens_control(cam)
                ui.Spacer(width=6)

    def _build_lens_control(self, cam: dict):
        variants = sorted(cam["lens_variants"], key=_lens_sort_key)
        if not variants:
            # Fixed-lens model: show its (only) lens as a plain tag.
            lens = get_lens_type(cam["base_model"]).value + " lens"
            with ui.VStack(width=0):
                ui.Spacer()
                ui.Label(
                    lens, width=70,
                    style={"Label": {"color": _TEXT_DIM}, "Tooltip": _TOOLTIP_STYLE},
                    tooltip="This model has a single, non-interchangeable lens",
                )
                ui.Spacer()
            return
        with ui.VStack(width=0):
            ui.Spacer()
            with ui.HStack(height=26, spacing=3):
                for lens in variants:
                    selected = lens == cam["current_lens"]
                    ui.Button(
                        lens, width=62,
                        style=_BTN_ON_STYLE if selected else _BTN_OFF_STYLE,
                        clicked_fn=functools.partial(self._set_lens, cam["model_prim_path"], lens),
                        tooltip=f"Switch the {cam['base_model']} to the {lens} lens",
                    )
            ui.Spacer()
