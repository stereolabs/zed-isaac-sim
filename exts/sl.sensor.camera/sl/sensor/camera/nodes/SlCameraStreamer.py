"""
This is the implementation of the OGN node defined in SlCameraStreamer.ogn
"""
from ..ogn.SlCameraStreamerDatabase import SlCameraStreamerDatabase
from . import _streamer


class SlCameraStreamer:
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
        if len(db.inputs.cameraPrim) == 0:
            _streamer.report(db.per_instance_state, "[ZED] A camera prim must be specified.")
            return False
        return _streamer.setup(db, db.inputs.cameraPrim, stream_depth=db.inputs.streamDepth)

    @staticmethod
    def release_instance(node, graph_instance_id):
        try:
            state = SlCameraStreamerDatabase.per_instance_internal_state(node)
        except Exception:
            state = None

        if state is not None:
            _streamer.release(state)
