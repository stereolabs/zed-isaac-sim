# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""'ZED Cameras' panel: at-a-glance lens control for the ZED cameras in the stage.

A dockable window (Stereolabs menu) that lists every placed ZED camera - thumbnail,
prim name, model - with its lens shown as segmented buttons (Wide | Narrow |
Fisheye): the current lens is highlighted, only the lenses the model supports are
shown, and one click switches. It complements the per-prim variant dropdown in the
Property window; both edit the same 'lens' variant selection, which the streamer
picks up through utils.resolve_camera_model, so the visible lens and the streamed
camera model stay in sync.

Fixed-lens models (ZED M, ZED X Nano, ZED X One UHD) are listed with their single
lens as a static tag (e.g. "Wide lens") instead of buttons.
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

from ..utils import find_placed_zed_cameras, get_camera_thumbnail_path, get_lens_type

_TITLE = "ZED Cameras"
_MENU_GROUP = "Stereolabs"
_LENS_ORDER = ("Wide", "Narrow", "Fisheye")

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

    # ------------------------------------------------------------- lifecycle
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

    # ----------------------------------------------------------- refreshing
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

    # ------------------------------------------------------------- actions
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

    # -------------------------------------------------------------- building
    def _build(self):
        with self._window.frame:
            with ui.VStack(spacing=6, height=0):
                ui.Spacer(height=2)
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
