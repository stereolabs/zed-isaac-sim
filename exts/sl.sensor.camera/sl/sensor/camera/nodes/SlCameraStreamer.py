"""
This is the implementation of the OGN node defined in SlCameraStreamer.ogn
"""
import carb
from dataclasses import dataclass
import traceback
import omni.kit.commands

from ..annotators import ZEDAnnotator

class SlCameraStreamer:
    """
         Streams camera data to the ZED SDK
    """
    used_ports = set()

    @dataclass
    class State:
        initialized: bool = False
        annotator: ZEDAnnotator = None
        port: int = None
        timeline_stop_sub = None

    @staticmethod
    def internal_state() -> State:
        return SlCameraStreamer.State()

    def compute(db) -> bool:
        state = db.per_instance_state
        if state.initialized is False:
            try:
                port = db.inputs.streamingPort

                # Check if the port is already used
                if port in SlCameraStreamer.used_ports:
                    carb.log_error(f"[ZED] Port {port} is already used by another instance.")
                    return False

                state.initialized = True

                # Mark the port as used
                SlCameraStreamer.used_ports.add(port)
                state.port = port

                state.annotator = ZEDAnnotator(
                    db.inputs.cameraPrim,
                    db.inputs.cameraModel,
                    state.port,
                    db.inputs.resolution,
                    db.inputs.fps,
                    db.inputs.bitrate,
                    db.inputs.chunkSize,
                    db.inputs.transportLayerMode)

                def cleanup(event, _state=state):
                    SlCameraStreamer.release(_state)

                timeline = omni.timeline.get_timeline_interface()
                state.timeline_stop_sub = timeline.get_timeline_event_stream().create_subscription_to_pop_by_type(
                    int(omni.timeline.TimelineEventType.STOP), cleanup
                )

            except Exception as e:
                print(traceback.format_exc())
                pass
        return True

    @staticmethod
    def release_instance(node, graph_instance_id):
        try:
            state = SlCameraStreamer.per_instance_internal_state(node)
            if state.port in SlCameraStreamer.used_ports:
                SlCameraStreamer.used_ports.remove(state.port)

        except Exception:
            state = None
            pass

        if state is not None:
            state.reset()

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

            # Reset state
            state.initialized = False
            state.port = None
            state.timeline_stop_sub = None

        except Exception:
            carb.log_error(traceback.format_exc())
