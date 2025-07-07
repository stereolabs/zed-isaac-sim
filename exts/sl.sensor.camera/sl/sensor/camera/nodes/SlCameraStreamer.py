"""
This is the implementation of the OGN node defined in SlCameraStreamer.ogn
"""
import carb
from dataclasses import dataclass
import traceback
import omni.kit.commands
from carb.events import IEvent
from isaacsim.core.utils.stage import get_current_stage
from pxr import Sdf

from ..annotators import ZEDAnnotator

class SlCameraStreamer:
    """
         Streams camera data to the ZED SDK
    """
    used_ports = set()

    @dataclass
    class State:
        initialized: bool = False
        annotator = None
        port: int = None
        pass

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
                    carb.log_error(f"Port {port} is already used by another instance.")
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
                    db.inputs.ipc)

                def on_closed_event(event: carb.events.IEvent):
                    SlCameraStreamer.release(db)

                timeline = omni.timeline.get_timeline_interface()
                db.per_instance_state.timeline_stop_sub = timeline.get_timeline_event_stream().create_subscription_to_pop_by_type(
                    int(omni.timeline.TimelineEventType.STOP),
                    on_closed_event
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
    def release(db):
        try:
            state = db.per_instance_state
            if state.annotator is not None:
                state.annotator.destroy()

            SlCameraStreamer.used_ports = set()
            state.initialized = False

            stage = get_current_stage()
            path = "/Render"
            # delete any deltas on the root layer
            from omni.kit.usd.layers import RemovePrimSpecCommand
            RemovePrimSpecCommand(layer_identifier=stage.GetRootLayer().realPath, prim_spec_path=[Sdf.Path(path)]).do()

        except Exception:
            state = None
            pass
