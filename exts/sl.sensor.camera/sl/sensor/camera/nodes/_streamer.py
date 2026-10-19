"""Setup, live switches and teardown shared by the ZED Camera Helper and ZED Camera One Helper nodes."""
import traceback
from dataclasses import dataclass

import carb
import omni.graph.core as og
import omni.kit.app
import omni.timeline
import omni.usd

from ..annotators import ZEDAnnotator, used_ports
from ..utils import compose_model, resolve_camera_model
from ._migration import migrate_camera_model_to_base_lens, migrate_sim2real_to_master_switch

# The camera model's live switches: node input -> ZEDAnnotator setter.
_SIM2REAL_SWITCHES = (
    ("inputs:applyZedSim2Real", "set_apply_zed_sim2real"),
    ("inputs:autoExposure", "set_auto_exposure"),
    ("inputs:sensorNoise", "set_sensor_noise"),
    ("inputs:motionBlur", "set_motion_blur"),
    ("inputs:vignetting", "set_vignetting"),
    ("inputs:cameraSharpness", "set_camera_sharpness"),
    ("inputs:autoWhiteBalance", "set_auto_white_balance"),
)


@dataclass
class State:
    initialized: bool = False
    annotator: ZEDAnnotator = None
    port: int = None
    timeline_stop_sub = None
    sim2real_sub = None
    reported: str = None  # the last setup error logged


def report(state, message) -> None:
    """Log a setup error once: setup is retried on every tick until it succeeds."""
    if state.reported != message:
        state.reported = message
        carb.log_error(message)


def update_node_version(node, old_version, new_version) -> bool:
    # v3 split the single composite "cameraModel" token (e.g. "ZED_X_4MM") into base model + lens.
    # The OG runtime attributes aren't valid yet during an upgrade, so the migrations read and
    # write the authored values on the USD prim. A migration hiccup must never abort node creation.
    if old_version < 3 <= new_version:
        try:
            migrate_camera_model_to_base_lens(node)
        except Exception:
            carb.log_warn(f"[ZED] cameraModel v{old_version}->v{new_version} migration failed:\n{traceback.format_exc()}")
    # v5: applyZedSim2Real became the camera model's master switch (see _migration).
    if old_version < 5 <= new_version:
        try:
            migrate_sim2real_to_master_switch(node)
        except Exception:
            carb.log_warn(f"[ZED] ZED Sim2Real v{old_version}->v{new_version} migration failed:\n{traceback.format_exc()}")
    return True


def setup(db, camera_prims, serial_number=None, stream_depth=False) -> bool:
    """Start streaming `camera_prims` (one prim, or the two of a virtual stereo pair) on the node's port."""
    state = db.per_instance_state
    try:
        port = db.inputs.streamingPort
        if port in used_ports:
            report(state, f"[ZED] Port {port} is already used by another instance.")
            return False

        # Prefer the model + lens read from the placed asset (its 'lens' variant / sl:cameraModel);
        # fall back to the node's base-model + lens-type dropdowns when the asset carries neither.
        effective_model = resolve_camera_model(
            omni.usd.get_context().get_stage(), camera_prims[0].pathString,
            compose_model(db.inputs.cameraModel, db.inputs.lensType))

        state.annotator = ZEDAnnotator(
            camera_prims,
            effective_model,
            port,
            db.inputs.resolution,
            db.inputs.fps,
            db.inputs.bitrate,
            db.inputs.chunkSize,
            db.inputs.transportLayerMode,
            serial_number,
            stream_depth=stream_depth,
            apply_zed_sim2real=db.inputs.applyZedSim2Real,
            auto_exposure=db.inputs.autoExposure,
            sensor_noise=db.inputs.sensorNoise,
            motion_blur=db.inputs.motionBlur,
            vignetting=db.inputs.vignetting,
            camera_sharpness=db.inputs.cameraSharpness,
            auto_white_balance=db.inputs.autoWhiteBalance)

        state.initialized = True
        state.reported = None
        state.port = port
        used_ports.add(port)

        timeline_events = omni.timeline.get_timeline_interface().get_timeline_event_stream()
        state.timeline_stop_sub = timeline_events.create_subscription_to_pop_by_type(
            int(omni.timeline.TimelineEventType.STOP), lambda _e, _state=state: release(_state))

        # The switches are polled on every app update rather than read in compute: execIn may fire
        # only once (e.g. from a run-one-simulation-frame node), and property-panel edits during play
        # go to fabric, which emits no USD change notice. The annotator's setters are change-gated.
        # The same poll warns once if the IMU never lets the stream start.
        node = db.node

        def push_sim2real(_e, _state=state, _node=node):
            if _state.annotator is None:
                return
            _state.annotator.warn_if_imu_blocks_stream()
            for attr, setter in _SIM2REAL_SWITCHES:
                getattr(_state.annotator, setter)(og.Controller.get(og.Controller.attribute(attr, _node)))

        state.sim2real_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            push_sim2real, name=f"zed_sim2real_poll_{port}"
        )

    except Exception:
        report(state, f"[ZED] Streamer setup failed:\n{traceback.format_exc()}")
    return True


def release(state):
    """Release all resources for this node instance."""
    try:
        if not isinstance(state, State) or not state.initialized:
            return

        carb.log_info(f"[ZED] Releasing resources for port {state.port}")

        if state.annotator is not None:
            try:
                state.annotator.destroy()
            except Exception:
                carb.log_error(f"[ZED] Annotator teardown failed:\n{traceback.format_exc()}")
            state.annotator = None

        if state.port in used_ports:
            used_ports.remove(state.port)
            carb.log_info(f"[ZED] Freed port {state.port}")

        if state.timeline_stop_sub is not None:
            state.timeline_stop_sub.unsubscribe()
        if state.sim2real_sub is not None:
            state.sim2real_sub.unsubscribe()

        state.initialized = False
        state.port = None
        state.timeline_stop_sub = None
        state.sim2real_sub = None

    except Exception:
        carb.log_error(f"[ZED] Streamer release failed:\n{traceback.format_exc()}")
