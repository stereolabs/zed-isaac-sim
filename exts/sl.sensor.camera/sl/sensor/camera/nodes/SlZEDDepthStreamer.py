"""
This is the implementation of the OGN node defined in SlZEDDepthStreamer.ogn
"""
import carb
from dataclasses import dataclass
import traceback
import omni.timeline
import omni.usd

from ..zed_depth import ZEDDepthCamera
from ..ogn.SlZEDDepthStreamerDatabase import SlZEDDepthStreamerDatabase
from ..utils import compose_model, resolve_camera_model


class SlZEDDepthStreamer:
    """
    OGN node that captures RGB + simulated stereo depth from a ZED camera.

    Initialization is deferred: the render pipeline may not be ready on
    the first frame after Play. The node retries each compute() until
    the depth sensor is fully initialized.
    """

    @dataclass
    class State:
        initialized: bool = False
        zed_depth: ZEDDepthCamera = None
        timeline_stop_sub = None
        reported: str = None  # the last setup error logged
        failed_setup: tuple = None  # the inputs a setup failed with; not retried until they change

    @staticmethod
    def internal_state():
        return SlZEDDepthStreamer.State()

    @staticmethod
    def _report(state, message) -> None:
        """Log a setup error once: compute retries setup on every tick."""
        if state.reported != message:
            state.reported = message
            carb.log_error(message)

    @staticmethod
    def compute(db) -> bool:
        state = db.per_instance_state

        if state.initialized:
            return True

        try:
            if state.zed_depth is None:
                if len(db.inputs.cameraPrim) == 0:
                    SlZEDDepthStreamer._report(state, "[ZED][Depth] No camera prim specified.")
                    return False

                camera_prim_path = db.inputs.cameraPrim[0].pathString

                # Prefer the model + lens read from the placed asset (its 'lens'
                # variant / sl:cameraModel); fall back to the node's base-model +
                # lens-type dropdowns when the asset carries neither.
                effective_model = resolve_camera_model(
                    omni.usd.get_context().get_stage(), camera_prim_path,
                    compose_model(db.inputs.cameraModel, db.inputs.lensType))
                setup = (camera_prim_path, effective_model, db.inputs.resolution, db.inputs.enableSave,
                         db.inputs.outputDir, db.inputs.saveDepth)
                if setup == state.failed_setup:
                    return False

                # Stop releases the capture, and also clears a failed setup so Play retries it.
                if state.timeline_stop_sub is None:
                    def cleanup(event, _state=state):
                        SlZEDDepthStreamer.release(_state)

                    timeline_events = omni.timeline.get_timeline_interface().get_timeline_event_stream()
                    state.timeline_stop_sub = timeline_events.create_subscription_to_pop_by_type(
                        int(omni.timeline.TimelineEventType.STOP), cleanup)

                state.zed_depth = ZEDDepthCamera(
                    camera_prim_path=camera_prim_path,
                    camera_model=effective_model,
                    resolution=db.inputs.resolution,
                    enable_save=db.inputs.enableSave,
                    output_dir=db.inputs.outputDir,
                    save_depth=db.inputs.saveDepth,
                )

                if state.zed_depth._init_failed:
                    SlZEDDepthStreamer._report(
                        state,
                        f"[ZED][Depth] Setup failed for {camera_prim_path}. "
                        "Check that the prim path and camera model are correct."
                    )
                    state.failed_setup = setup
                    state.zed_depth = None
                    return False
                state.failed_setup = state.reported = None

            if state.zed_depth.try_initialize():
                state.initialized = True

        except Exception:
            SlZEDDepthStreamer._report(state, f"[ZED][Depth] Setup failed:\n{traceback.format_exc()}")

        return True

    @staticmethod
    def release_instance(node, graph_instance_id):
        try:
            state = SlZEDDepthStreamerDatabase.per_instance_internal_state(node)
        except Exception:
            state = None

        if state is not None:
            SlZEDDepthStreamer.release(state)

    @staticmethod
    def release(state):
        try:
            if not isinstance(state, SlZEDDepthStreamer.State):
                return

            if state.zed_depth is not None:
                try:
                    state.zed_depth.destroy()
                except Exception:
                    carb.log_error(f"[ZED][Depth] Teardown failed:\n{traceback.format_exc()}")
                state.zed_depth = None

            if state.timeline_stop_sub is not None:
                state.timeline_stop_sub.unsubscribe()

            state.initialized = False
            state.timeline_stop_sub = None
            state.failed_setup = state.reported = None

        except Exception:
            carb.log_error(f"[ZED][Depth] Release failed:\n{traceback.format_exc()}")
