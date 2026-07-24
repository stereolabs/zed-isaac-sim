"""
This is the implementation of the OGN node defined in SlCameraStreamer.ogn
"""
import carb
from dataclasses import dataclass
import traceback
import omni.kit.commands
import omni.kit.app
import omni.graph.core as og
try:
    from isaacsim.core.utils.stage import get_current_stage
except ImportError:  
    get_current_stage = None

from ..annotators import ZEDAnnotator, used_ports as _used_ports
from ..ogn.SlCameraStreamerDatabase import SlCameraStreamerDatabase
from ..utils import compose_model, resolve_camera_model
from ._migration import migrate_camera_model_to_base_lens

class SlCameraStreamer:
    """
         Streams camera data to the ZED SDK
    """
    used_ports = _used_ports

    @dataclass
    class State:
        initialized: bool = False
        annotator: ZEDAnnotator = None
        port: int = None
        timeline_stop_sub = None
        sim2real_sub = None

    @staticmethod
    def internal_state() -> State:
        return SlCameraStreamer.State()

    @staticmethod
    def update_node_version(context, node, old_version, new_version):
        # v3 split the single composite "cameraModel" token (e.g. "ZED_X_4MM")
        # into base model + lens. Carry old values over so existing graphs keep
        # their camera configuration. The OG runtime attributes aren't valid yet
        # during an upgrade, so read/write the authored values on the USD prim.
        # Degrade gracefully: a migration hiccup must never abort node creation.
        if old_version < 3 <= new_version:
            try:
                migrate_camera_model_to_base_lens(node)
            except Exception:
                carb.log_warn(f"[ZED] cameraModel v{old_version}->v{new_version} migration failed:\n{traceback.format_exc()}")
        return True

    def compute(db) -> bool:
        state = db.per_instance_state
        if state.initialized is False:
            try:
                port = db.inputs.streamingPort

                # Check if the port is already used
                if port in SlCameraStreamer.used_ports:
                    carb.log_error(f"[ZED] Port {port} is already used by another instance.")
                    return False

                if len(db.inputs.cameraPrim) == 0:
                    carb.log_error("[ZED] A camera prim must be specified.")
                    return False

                # Prefer the model + lens read from the placed asset (its 'lens'
                # variant / sl:cameraModel); fall back to the node's base-model +
                # lens-type dropdowns when the asset carries neither.
                effective_model = resolve_camera_model(
                    get_current_stage(), db.inputs.cameraPrim[0].pathString,
                    compose_model(db.inputs.cameraModel, db.inputs.lensType))

                state.annotator = ZEDAnnotator(
                    db.inputs.cameraPrim,
                    effective_model,
                    port,
                    db.inputs.resolution,
                    db.inputs.fps,
                    db.inputs.bitrate,
                    db.inputs.chunkSize,
                    db.inputs.transportLayerMode,
                    stream_depth=db.inputs.streamDepth,
                    apply_zed_sim2real=db.inputs.applyZedSim2Real,
                    zed_sim2real_scene_lux=db.inputs.zedSim2RealSceneLux,
                    zed_sim2real_ae_target=db.inputs.zedSim2RealAeTarget)

                state.initialized = True
                state.port = port
                # Mark the port as used
                SlCameraStreamer.used_ports.add(port)

                def cleanup(event, _state=state):
                    SlCameraStreamer.release(_state)

                timeline = omni.timeline.get_timeline_interface()
                state.timeline_stop_sub = timeline.get_timeline_event_stream().create_subscription_to_pop_by_type(
                    int(omni.timeline.TimelineEventType.STOP), cleanup
                )

                # This node's execIn may fire only once (e.g. when driven by a
                # run-one-simulation-frame node), so sim2real enable/lux edits made while
                # playing would never reach the C++ node via a re-compute - and property-panel
                # edits during play go to fabric, not USD, so a USD change notice won't fire
                # either. Poll the two inputs on every app update instead and push any change
                # to the C++ node (set_sim2real is change-gated), so the toggle works live
                # regardless of how the graph ticks this node.
                node = db.node

                def push_sim2real(_e, _state=state, _node=node):
                    if _state.annotator is None:
                        return
                    _state.annotator.set_sim2real(
                        og.Controller.get(og.Controller.attribute("inputs:applyZedSim2Real", _node)),
                        og.Controller.get(og.Controller.attribute("inputs:zedSim2RealSceneLux", _node)),
                        og.Controller.get(og.Controller.attribute("inputs:zedSim2RealAeTarget", _node)),
                    )

                state.sim2real_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
                    push_sim2real, name=f"zed_sim2real_poll_{port}"
                )

            except Exception:
                carb.log_error(traceback.format_exc())
        elif state.annotator is not None:
            # Forward live edits of the sim2real config (the C++ node reads them per frame).
            state.annotator.set_sim2real(db.inputs.applyZedSim2Real, db.inputs.zedSim2RealSceneLux,
                                         db.inputs.zedSim2RealAeTarget)
        return True

    @staticmethod
    def release_instance(node, graph_instance_id):
        try:
            state = SlCameraStreamerDatabase.per_instance_internal_state(node)
        except Exception:
            state = None

        if state is not None:
            SlCameraStreamer.release(state)

    @staticmethod
    def release(state):
        """Release all resources for this node instance."""
        try:
            if not isinstance(state, SlCameraStreamer.State):
                return

            if not state.initialized:
                return

            carb.log_info(f"[ZED] Releasing resources for port {state.port}")

            # Destroy annotator if active
            if state.annotator is not None:
                try:
                    state.annotator.destroy()
                except Exception:
                    carb.log_error(traceback.format_exc())
                state.annotator = None

            # Free port reservation
            if state.port in SlCameraStreamer.used_ports:
                SlCameraStreamer.used_ports.remove(state.port)
                carb.log_info(f"[ZED] Freed port {state.port}")

            # Remove subscriptions
            if state.timeline_stop_sub is not None:
                state.timeline_stop_sub.unsubscribe()
            if state.sim2real_sub is not None:
                state.sim2real_sub.unsubscribe()

            # Reset state
            state.initialized = False
            state.port = None
            state.timeline_stop_sub = None
            state.sim2real_sub = None

        except Exception:
            carb.log_error(traceback.format_exc())