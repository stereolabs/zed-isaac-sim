"""
This is the implementation of the OGN node defined in SlVirtualCameraStreamer.ogn
"""
import carb
from dataclasses import dataclass
import traceback
import omni.kit.commands
from carb.events import IEvent
from isaacsim.core.utils.stage import get_current_stage
from pxr import Sdf

from ..annotators import ZEDAnnotator

class SlCameraOneStreamer:
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
        return SlCameraOneStreamer.State()

    def compute(db) -> bool:
        state = db.per_instance_state
        if state.initialized is False:
            try:
                port = db.inputs.streamingPort

                # Check if the port is already used
                if port in SlCameraOneStreamer.used_ports:
                    carb.log_error(f"[ZED] Port {port} is already used by another instance.")
                    return False

                cameraPrims = []
                if (len(db.inputs.leftCameraPrim) > 0):
                    cameraPrims.append(db.inputs.leftCameraPrim[0])

                if (len(db.inputs.rightCameraPrim) > 0):
                    cameraPrims.append(db.inputs.rightCameraPrim[0])

                if len(cameraPrims) == 0:
                    carb.log_error("[ZED] At least one camera prim must be specified.")
                    return False

                state.port = port
                state.annotator = ZEDAnnotator(
                    cameraPrims,
                    db.inputs.cameraModel,
                    state.port,
                    db.inputs.resolution,
                    db.inputs.fps,
                    db.inputs.ipc,
                    db.inputs.serialNumber)
         
                state.initialized = True
                # Mark the port as used
                SlCameraOneStreamer.used_ports.add(port)

                def cleanup(event, _state=state):
                    SlCameraOneStreamer.release(_state)

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
            state = SlCameraOneStreamer.per_instance_internal_state(node)
            if state.port in SlCameraOneStreamer.used_ports:
                SlCameraOneStreamer.used_ports.remove(state.port)

        except Exception:
            state = None
            pass

        if state is not None:
            state.reset()

    @staticmethod
    def release(state):
        """Release all resources for this node instance."""
        try:
            if not isinstance(state, SlCameraOneStreamer.State):
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
            if state.port in SlCameraOneStreamer.used_ports:
                SlCameraOneStreamer.used_ports.remove(state.port)
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
