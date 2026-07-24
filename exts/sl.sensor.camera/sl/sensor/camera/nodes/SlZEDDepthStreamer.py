"""
This is the implementation of the OGN node defined in SlZEDDepthStreamer.ogn
"""
import carb
from dataclasses import dataclass
import traceback
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

    @staticmethod
    def internal_state():
        return SlZEDDepthStreamer.State()

    @staticmethod
    def compute(db) -> bool:
        state = db.per_instance_state

        if state.initialized:
            return True

        try:
            if state.zed_depth is None:
                if len(db.inputs.cameraPrim) == 0:
                    carb.log_error("[ZED Depth] No camera prim specified.")
                    return False

                camera_prim_path = db.inputs.cameraPrim[0].pathString

                # Prefer the model + lens read from the placed asset (its 'lens'
                # variant / sl:cameraModel); fall back to the node's base-model +
                # lens-type dropdowns when the asset carries neither.
                effective_model = resolve_camera_model(
                    omni.usd.get_context().get_stage(), camera_prim_path,
                    compose_model(db.inputs.cameraModel, db.inputs.lensType))

                state.zed_depth = ZEDDepthCamera(
                    camera_prim_path=camera_prim_path,
                    camera_model=effective_model,
                    resolution=db.inputs.resolution,
                    enable_save=db.inputs.enableSave,
                    output_dir=db.inputs.outputDir,
                )

                if state.zed_depth._init_failed:
                    carb.log_error(
                        f"[ZED Depth] Setup failed for {camera_prim_path}. "
                        "Check that the prim path and camera model are correct."
                    )
                    state.zed_depth = None
                    return False

                def cleanup(event, _state=state):
                    SlZEDDepthStreamer.release(_state)

                import omni.timeline
                timeline = omni.timeline.get_timeline_interface()
                state.timeline_stop_sub = (
                    timeline.get_timeline_event_stream()
                    .create_subscription_to_pop_by_type(
                        int(omni.timeline.TimelineEventType.STOP), cleanup
                    )
                )

            if state.zed_depth.try_initialize():
                state.initialized = True

        except Exception:
            carb.log_error(traceback.format_exc())

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
                    carb.log_error(traceback.format_exc())
                state.zed_depth = None

            if state.timeline_stop_sub is not None:
                state.timeline_stop_sub.unsubscribe()

            state.initialized = False
            state.timeline_stop_sub = None

        except Exception:
            carb.log_error(traceback.format_exc())
