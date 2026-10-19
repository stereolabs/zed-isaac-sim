"""
This is the implementation of the OGN node defined in SlCameraOneStreamer.ogn
"""
import carb

from ..ogn.SlCameraOneStreamerDatabase import SlCameraOneStreamerDatabase
from . import _streamer


class SlCameraOneStreamer:
    """
         Streams camera data to the ZED SDK
    """

    @staticmethod
    def internal_state() -> _streamer.State:
        return _streamer.State()

    @staticmethod
    def update_node_version(context, node, old_version, new_version):
        return _streamer.update_node_version(node, old_version, new_version)

    @staticmethod
    def compute(db) -> bool:
        if db.per_instance_state.initialized:
            return True

        camera_prims = []
        if len(db.inputs.leftCameraPrim) > 0:
            camera_prims.append(db.inputs.leftCameraPrim[0])
        if len(db.inputs.rightCameraPrim) > 0:
            camera_prims.append(db.inputs.rightCameraPrim[0])
        if len(camera_prims) == 0:
            _streamer.report(db.per_instance_state, "[ZED] At least one camera prim must be specified.")
            return False

        # Stream Depth is a virtual-stereo-only feature (two ZED X One prims).
        # A single mono cam cannot produce depth on real hardware, so ignore it here.
        stream_depth = db.inputs.streamDepth
        if stream_depth and len(camera_prims) < 2:
            carb.log_warn(
                "[ZED] 'Stream Depth' requires a virtual stereo pair (two camera prims). "
                "Ignoring Stream Depth for a single mono camera."
            )
            stream_depth = False

        return _streamer.setup(db, camera_prims, db.inputs.serialNumber, stream_depth)

    @staticmethod
    def release_instance(node, graph_instance_id):
        try:
            state = SlCameraOneStreamerDatabase.per_instance_internal_state(node)
        except Exception:
            state = None

        if state is not None:
            _streamer.release(state)
