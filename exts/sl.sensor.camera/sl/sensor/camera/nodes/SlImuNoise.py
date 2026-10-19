"""
This is the implementation of the OGN node defined in SlImuNoise.ogn
"""
import math

import numpy as np
import omni.graph.core as og


class SlImuNoise:
    """Adds a real ZED X IMU's noise to the reading the ZED node streams (see the .ogn description)."""

    class State:
        def __init__(self):
            self.rng = None
            self.bias = None

    @staticmethod
    def internal_state():
        return SlImuNoise.State()

    @staticmethod
    def compute(db) -> bool:
        q = np.asarray(db.inputs.orientation, dtype=np.float64)  # (i, j, k, r)
        acc = np.asarray(db.inputs.linAcc, dtype=np.float64)
        if db.inputs.enabled:
            state = db.per_instance_state
            if state.rng is None:
                state.rng = np.random.default_rng(int(db.inputs.seed) or None)
                state.bias = state.rng.normal(0.0, max(db.inputs.accBias, 0.0), 3)
            acc = acc + state.bias + state.rng.normal(0.0, max(db.inputs.accNoise, 0.0), 3)
            sigma = math.radians(max(db.inputs.orientationNoise, 0.0))
            if sigma > 0 and np.dot(q, q) > 0:
                # small random rotation (axis-angle, per axis sigma) applied on the right
                rv = state.rng.normal(0.0, sigma, 3)
                angle = float(np.linalg.norm(rv))
                if angle > 0:
                    axis = rv / angle
                    dq = np.r_[axis * math.sin(angle / 2), math.cos(angle / 2)]
                    x1, y1, z1, w1 = q
                    x2, y2, z2, w2 = dq
                    q = np.array([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                                  w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                                  w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
                                  w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2])
        db.outputs.orientation = q
        db.outputs.linAcc = acc
        db.outputs.execOut = og.ExecutionAttributeState.ENABLED
        return True
