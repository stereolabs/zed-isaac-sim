import carb
import omni.graph.core as og

from .. import frame_imu, update_clock


class SlFrameImu:
    """Gives the ZED node its frame's time and the IMU at that time (see the .ogn description)."""

    class State:
        def __init__(self):
            self.warned = False
            self.last_update_end = None
            self.repeat_warned = False

    @staticmethod
    def internal_state():
        return SlFrameImu.State()

    @staticmethod
    def compute(db) -> bool:
        orientation = db.inputs.orientation
        lin_acc = db.inputs.linAcc * db.inputs.metersPerUnit
        state = db.per_instance_state
        t = db.inputs.simulationTime
        if t > 0.0:
            period = update_clock.update_period()
            if period is None and update_clock.recording():
                # The ZED node declares the rate given with the frame that opens the stream: wait for the
                # update rate, two app updates after the stream starts.
                return True
            # The stream ticks faster than the app updates: it sends every stride-th tick, evenly spaced, and
            # never two frames of one update (an update longer than the others).
            stride = update_clock.frame_stride(db.inputs.fps, period)
            end = update_clock.update_end(t)
            if round(t * db.inputs.fps) % stride or (end is not None and end == state.last_update_end):
                if not state.repeat_warned:
                    state.repeat_warned = True
                    rate = update_clock.stream_rate(db.inputs.fps, period)
                    carb.log_warn(f"[ZED] {db.node.get_prim_path()}: the stream's fps is above the rate the app "
                                  f"updates at, so it streams one frame in {stride}, {rate} a second.")
                return True
            state.last_update_end = end
            db.outputs.fps = update_clock.stream_rate(db.inputs.fps, period)
        else:
            db.outputs.fps = db.inputs.fps
        try:
            history = frame_imu.lookup(db.node.get_prim_path())
            if history is not None and t > 0.0:
                found, imu = history.at(t)
                if found == frame_imu.FOUND:
                    q, acc = imu
                    orientation, lin_acc = [*q.GetImaginary(), q.GetReal()], list(acc)
                elif found == frame_imu.MISSED and not state.warned:
                    state.warned = True
                    carb.log_warn(f"[ZED] {db.node.get_prim_path()}: no IMU sample at the time of a frame. Its "
                                  "frames carry IsaacReadIMU's latest reading instead.")
        except Exception as exc:  # this node triggers the stream: never stop it
            if not state.warned:
                state.warned = True
                carb.log_warn(f"[ZED] {db.node.get_prim_path()}: the IMU at the frame's time failed ({exc}). Its "
                              "frames carry IsaacReadIMU's latest reading instead.")
        db.outputs.frameTime = t
        db.outputs.orientation = orientation
        db.outputs.linAcc = lin_acc
        db.outputs.execOut = og.ExecutionAttributeState.ENABLED
        return True
