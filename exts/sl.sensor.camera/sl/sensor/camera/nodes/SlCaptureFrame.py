import traceback

import carb

from .. import zed_depth


class SlCaptureFrame:
    """Saves the frame the post-render graph just produced (see the .ogn description)."""

    class State:
        def __init__(self):
            self.warned = False

    @staticmethod
    def internal_state():
        return SlCaptureFrame.State()

    @staticmethod
    def compute(db) -> bool:
        try:
            zed_depth.save_rendered_frame(db.node.get_prim_path(),
                                          (db.inputs.rationalTimeNumerator, db.inputs.rationalTimeDenominator))
        except Exception:  # runs for every rendered frame: never take the post-render graph down
            state = db.per_instance_state
            if not state.warned:
                state.warned = True
                carb.log_error(f"[ZED][Depth] {db.node.get_prim_path()}: saving a frame failed:\n"
                               f"{traceback.format_exc()}")
        return True
