"""Shared Property-panel layout for the ZED camera OmniGraph nodes.

Replaces the default ``Lens Type`` and ``Resolution`` combo boxes with ones whose
values are filtered to the combinations supported by the currently selected
``Camera Model`` (base model), and rebuilds them live whenever the model or lens
changes. All other inputs keep their default layout (order, grouping) untouched.
"""
import json

import carb
import omni.graph.core as og
import omni.ui as ui
from omni.graph.ui import OmniGraphPropertiesWidgetBuilder
from omni.kit.window.property.templates import HORIZONTAL_SPACING, LABEL_WIDTH
from pxr import Tf, Usd

from sl.sensor.camera.utils import (
    compose_model,
    get_allowed_lens_types,
    get_allowed_resolutions,
    get_base_models,
    get_camera_model,
    get_default_lens_type,
    get_default_resolution,
    get_lens_type,
    resolve_camera_model,
)
from sl.sensor.camera.templates._filtered_token_model import FilteredTokenModel

_CAMERA_MODEL_ATTR = "inputs:cameraModel"
_LENS_TYPE_ATTR = "inputs:lensType"
_RESOLUTION_ATTR = "inputs:resolution"
# Depth props that only make sense for a virtual stereo pair (two prims).
_DEPTH_ATTRS = {"inputs:streamDepth"}
# Target relationships the streamer nodes use to point at the placed ZED asset:
# stereo (ZED_Camera) uses cameraPrim, mono (ZED_Camera_One) uses leftCameraPrim
# (+ rightCameraPrim for virtual stereo).
_CAMERA_PRIM_RELS = ("inputs:cameraPrim", "inputs:leftCameraPrim", "inputs:rightCameraPrim")
# Second prim of a virtual stereo pair (ZED_Camera_One node only); gates the depth props.
_RIGHT_PRIM_ATTR = "inputs:rightCameraPrim"
_LABEL_STYLE = {"alignment": ui.Alignment.RIGHT_TOP}

# Order the category frames appear in the panel. Inputs whose uiGroup is not listed
# (or have none) fall through to the end.
_GROUP_ORDER = ("Camera Selection", "Configuration", "Streaming", "ZED Sim2Real")
# Base model names, used to recognise a placed ZED asset by its authored structure
# (<root>/base_link/<base_model>, see get_camera_subpaths) when filtering the
# camera-prim target picker.
_BASE_MODELS = set(get_base_models())


def _is_zed_camera_prim(prim) -> bool:
    """True only for a placed ZED asset root (the prim to target), not its
    ancestors or the inner camera prims. Used to filter the target picker."""
    if not prim or not prim.IsValid():
        return False
    base_link = prim.GetChild("base_link")
    if not base_link or not base_link.IsValid():
        return False
    return any(child.GetName() in _BASE_MODELS for child in base_link.GetChildren())


class CustomLayout:
    """Picked up by omni.graph.ui ComputeNodeWidget.load_template().

    A new instance is created on every panel rebuild; ``compute_node_widget.template``
    always points to the live one, which we use to retire stale change listeners.
    """

    def __init__(self, compute_node_widget):
        self.enable = True
        self.compute_node_widget = compute_node_widget
        self.node_prim_path = compute_node_widget._payload[-1]
        self.node = og.Controller().node(self.node_prim_path)
        self.lens_model = None
        self.resolution_model = None
        # Composite model detected from the connected asset (None = nothing
        # connected -> fall back to the editable Model/Lens dropdowns). Set in apply().
        self._detected = None
        # Path of the connected asset (for the live-refresh listener). Set alongside.
        self._asset_root = None
        self._camera_model_path = self.node_prim_path.AppendProperty(_CAMERA_MODEL_ATTR)
        self._lens_type_path = self.node_prim_path.AppendProperty(_LENS_TYPE_ATTR)
        # Connecting/clearing a camera prim must flip the panel between the editable
        # combos and the read-only detected line, so watch those relationships too.
        self._rel_paths = tuple(self.node_prim_path.AppendProperty(rel) for rel in _CAMERA_PRIM_RELS)

        # Live refresh: a camera-model / lens value change is a "changed info" edit
        # that does not re-run the layout on its own, so listen and trigger a rebuild.
        self._listener = Tf.Notice.Register(
            Usd.Notice.ObjectsChanged, self._on_objects_changed, compute_node_widget.stage
        )

    def _og_value(self, attr_name):
        """Read a token input's live (fabric) value.

        This reflects the node-type default even before the input is authored to
        USD. Reading the USD attribute instead (GetAttributeAtPath) returns None on
        a freshly created node, which makes the value look unsupported and triggers
        a needless snap in _ensure_valid_* - the source of the resolution defaulting
        to the first allowed token (HD1200) instead of the SVGA node default.
        """
        try:
            return og.Controller.get(og.Controller.attribute(attr_name, self.node))
        except Exception:
            return None

    def _current_camera_model(self) -> str:
        value = self._og_value(_CAMERA_MODEL_ATTR)
        return str(value) if value is not None else "ZED_X"

    def _current_lens_type(self):
        return self._og_value(_LENS_TYPE_ATTR)

    def _current_resolution(self):
        return self._og_value(_RESOLUTION_ATTR)

    def _connected_camera_model(self):
        """Composite model resolved from the connected ZED asset, or None.

        Reads the node's camera-prim target relationship and resolves the model +
        lens from the placed asset (its 'lens' variant / sl:cameraModel). Returns
        None when no prim is connected or the asset yields nothing, so the panel
        falls back to the editable Model/Lens dropdowns.
        """
        self._asset_root = None
        stage = self.compute_node_widget.stage
        node_prim = stage.GetPrimAtPath(self.node_prim_path)
        if not node_prim or not node_prim.IsValid():
            return None
        for rel_name in _CAMERA_PRIM_RELS:
            rel = node_prim.GetRelationship(rel_name)
            if not rel:
                continue
            targets = rel.GetTargets()
            if targets:
                self._asset_root = targets[0]
                return resolve_camera_model(stage, targets[0].pathString, None)
        return None

    def _second_prim_state(self):
        """Whether the (optional) second camera prim is populated.

        Returns ``None`` when the node has no ``rightCameraPrim`` input at all
        (i.e. the real-stereo ``ZED_Camera`` node, which shares this layout) so
        callers know not to gate the depth props there. ``True``/``False``
        otherwise, for the ``ZED_Camera_One`` node.
        """
        prim = self.compute_node_widget.stage.GetPrimAtPath(self.node_prim_path)
        rel = prim.GetRelationship(_RIGHT_PRIM_ATTR) if prim else None
        if not rel or not rel.IsValid():
            return None
        return bool(rel.GetTargets())

    def _current_composite(self) -> str:
        """The composite model driving the Resolution list: the detected one when
        an asset is connected, else recomposed from the editable dropdowns."""
        if self._detected is not None:
            return self._detected
        return compose_model(self._current_camera_model(), self._current_lens_type())

    # OmniGraph imprints the .ogn "default" under the metadata key "__default"
    # (omni.graph.tools.ogn.MetadataKeys.DEFAULT), not "default" - reading the
    # wrong key returns None and makes get_default_resolution fall back to the
    # first allowed token (HD1200) instead of the SVGA node default.
    _OGN_DEFAULT_KEY = "__default"

    def _ogn_default(self, attr_name):
        """Read a token attribute's OGN-authored default (e.g. "SVGA", "Wide")."""
        try:
            raw = og.Controller.attribute(attr_name, self.node).get_metadata(self._OGN_DEFAULT_KEY)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    def _ui_group(self, attr_name):
        """Read an input's authored ``uiGroup`` (stripped of any port prefix).

        ComputeNodeWidget.apply_default_layout collapses every input under a single
        "Inputs" frame and ignores the .ogn ``uiGroup`` metadata, so we re-apply it here
        to split the inputs into category frames."""
        try:
            return og.Controller.attribute(attr_name, self.node).get_metadata("uiGroup")
        except Exception:
            return None

    def _ogn_description(self, attr_name):
        """Read a token attribute's OGN-authored description, used as the tooltip
        (our custom combos replace the default widget, which would set it for us)."""
        try:
            return og.Controller.attribute(attr_name, self.node).get_metadata("__description") or ""
        except Exception:
            return ""

    def _ensure_valid_lens(self, camera_model, allowed):
        """Snap the stored lens to the model's default when the current value is
        not supported by the selected model (e.g. after a model switch)."""
        if self._current_lens_type() in allowed:
            return
        default = get_default_lens_type(camera_model, self._ogn_default(_LENS_TYPE_ATTR))
        try:
            og.Controller.set(og.Controller.attribute(_LENS_TYPE_ATTR, self.node), default)
        except Exception:
            carb.log_warn(f"[ZED] Could not set default lens '{default}' for '{camera_model}'.")

    def _ensure_valid_resolution(self, composite_model, allowed):
        """Snap the stored resolution to the model's default.
        """
        force = getattr(self.compute_node_widget, "_zed_force_resolution_default", False)
        if force:
            self.compute_node_widget._zed_force_resolution_default = False
        elif self._current_resolution() in allowed:
            return
        default = get_default_resolution(composite_model, self._ogn_default(_RESOLUTION_ATTR))
        if default is None:
            return
        try:
            og.Controller.set(og.Controller.attribute(_RESOLUTION_ATTR, self.node), default)
        except Exception:
            carb.log_warn(f"[ZED] Could not set default resolution '{default}' for '{composite_model}'.")

    def _build_token_combo(self, label, attr_name, allowed):
        attr_path = self.node_prim_path.AppendProperty(attr_name)
        tooltip = self._ogn_description(attr_name)
        with ui.HStack(spacing=HORIZONTAL_SPACING):
            ui.Label(label, name="label", style=_LABEL_STYLE, width=LABEL_WIDTH, tooltip=tooltip)
            ui.Spacer(width=HORIZONTAL_SPACING)
            with ui.ZStack():
                model = FilteredTokenModel(
                    self.compute_node_widget.stage, [attr_path], False, {}, allowed
                )
                ui.ComboBox(model, tooltip=tooltip)
        return model

    def _lens_build_fn(self, *args):
        camera_model = self._current_camera_model()
        allowed = get_allowed_lens_types(camera_model)
        self._ensure_valid_lens(camera_model, allowed)
        self.lens_model = self._build_token_combo("Lens Type", _LENS_TYPE_ATTR, allowed)
        return self.lens_model

    def _detected_build_fn(self, *args):
        """Read-only line shown in place of the Camera Model / Lens Type combos
        when the model is auto-detected from the connected ZED asset."""
        composite = self._detected
        base = get_camera_model(composite)
        lens = get_lens_type(composite).value
        tooltip = "Camera model and lens are read from the connected ZED USD asset."
        with ui.HStack(spacing=HORIZONTAL_SPACING):
            ui.Label("Camera", name="label", style=_LABEL_STYLE, width=LABEL_WIDTH, tooltip=tooltip)
            ui.Spacer(width=HORIZONTAL_SPACING)
            ui.Label(f"{base}  ·  {lens}", style={"font_size": 18}, tooltip=tooltip)

    def _hidden_build_fn(self, *args):
        # The Lens Type is folded into the detected line above; render nothing.
        pass

    def _camera_prim_build_fn(self, stage, attr_name, metadata, property_type, prim_paths,
                              additional_label_kwargs=None, additional_widget_kwargs=None):
        """Build the camera-prim target widget with its picker filtered to ZED
        assets only. Delegates to the stock OmniGraph builder so the target model,
        'Select Graph Target Prim' button and targets_limit are preserved."""
        kwargs = dict(additional_widget_kwargs or {})
        kwargs["target_picker_filter_lambda"] = _is_zed_camera_prim
        return OmniGraphPropertiesWidgetBuilder.build(
            stage, attr_name, metadata, property_type, prim_paths, additional_label_kwargs, kwargs)

    def _resolution_build_fn(self, *args):
        # Resolution options are keyed on the composite token; use the model
        # detected from the asset, else recompose from the base model + lens.
        composite = self._current_composite()
        allowed = get_allowed_resolutions(composite)
        self._ensure_valid_resolution(composite, allowed)
        self.resolution_model = self._build_token_combo("Resolution", _RESOLUTION_ATTR, allowed)
        return self.resolution_model

    def _is_current(self) -> bool:
        """True only while this instance is the live template for our node."""
        widget = self.compute_node_widget
        if getattr(widget, "template", None) is not self:
            return False
        payload = getattr(widget, "_payload", None)
        return bool(payload) and payload[-1] == self.node_prim_path

    def _on_objects_changed(self, notice, stage):
        # Retire this listener once a newer layout replaces it or the selection
        # moves to another prim, so listeners do not accumulate.
        if not self._is_current():
            self._listener.Revoke()
            return
        # Info-only edits: only the model/lens/camera-prim inputs matter here. Match
        # exactly (not by node prefix) so editing Resolution/Port/etc. doesn't steal
        # focus by rebuilding mid-edit.
        watched = (self._camera_model_path, self._lens_type_path) + self._rel_paths
        for path in notice.GetChangedInfoOnlyPaths():
            # A model switch must always re-default the resolution (not just when the
            # carried-over value is unsupported), else a value valid for both models
            # sticks across a round-trip. Flag it for the rebuild rather than authoring
            # it here: the previous model's resolution combo is still live and would
            # clamp an out-of-its-list value back (see _ensure_valid_resolution).
            if path == self._camera_model_path:
                self.compute_node_widget._zed_force_resolution_default = True
                self.compute_node_widget.rebuild_window()
                return
            if path in watched:
                self.compute_node_widget.rebuild_window()
                return
        # Resyncs are structural (not text edits): a camera-prim (dis)connect shows up
        # under the node prim; a live 'lens' variant switch shows up under the connected
        # asset. Either flips the panel between the editable combos and detected line.
        for path in notice.GetResyncedPaths():
            if path.HasPrefix(self.node_prim_path) or (
                self._asset_root is not None and path.HasPrefix(self._asset_root)
            ):
                self.compute_node_widget.rebuild_window()
                return

    def _order_lens_after_model(self, props):
        """Move the Lens Type property to sit directly below Camera Model.

        The default layout orders inputs alphabetically, which separates the two;
        keep them together since the lens choice is scoped to the model.
        """
        names = [p.prop_name for p in props]
        if _CAMERA_MODEL_ATTR in names and _LENS_TYPE_ATTR in names:
            lens_prop = props.pop(names.index(_LENS_TYPE_ATTR))
            model_idx = [p.prop_name for p in props].index(_CAMERA_MODEL_ATTR)
            props.insert(model_idx + 1, lens_prop)
        return props

    def apply(self, props):
        # Reuse OmniGraph's default layout so the node's bookkeeping attributes
        # (node:type, node:typeVersion, ui:nodegraph:node:*, ...) are filtered
        # out and inputs/outputs are grouped as usual, then swap in our
        # model-filtered Lens Type and Resolution combos and pin Lens Type under
        # Camera Model.
        props = self.compute_node_widget.apply_default_layout(props)
        # Stream Depth is a virtual-stereo-only feature on the ZED Camera One node:
        # hide the depth props while only one prim is selected. Leaves the real-stereo
        # ZED_Camera node (no rightCameraPrim input -> None) untouched.
        if self._second_prim_state() is False:
            props = [p for p in props if p.prop_name not in _DEPTH_ATTRS]
        # When a ZED asset is connected, the model + lens come from it: replace the
        # Camera Model combo with a read-only detected line and hide Lens Type.
        # Otherwise keep the editable, model-filtered combos as the fallback.
        self._detected = self._connected_camera_model()
        if self._detected is not None:
            build_fns = {
                _CAMERA_MODEL_ATTR: self._detected_build_fn,
                _LENS_TYPE_ATTR: self._hidden_build_fn,
                _RESOLUTION_ATTR: self._resolution_build_fn,
            }
        else:
            build_fns = {_LENS_TYPE_ATTR: self._lens_build_fn, _RESOLUTION_ATTR: self._resolution_build_fn}
        # Filter the camera-prim target picker(s) to ZED assets, in both branches.
        for rel in _CAMERA_PRIM_RELS:
            build_fns[rel] = self._camera_prim_build_fn
        for prop in props:
            build_fn = build_fns.get(prop.prop_name)
            if build_fn is not None:
                prop.build_fn = build_fn
            group = self._ui_group(prop.prop_name)
            if group:
                prop.override_display_group(group)
        props = self._order_lens_after_model(props)
        # Stable-sort so the category frames render in _GROUP_ORDER (sort preserves the
        # within-group order set by apply_default_layout / _order_lens_after_model).
        rank = {name: i for i, name in enumerate(_GROUP_ORDER)}
        props.sort(key=lambda p: rank.get(self._ui_group(p.prop_name), len(_GROUP_ORDER)))
        return props
