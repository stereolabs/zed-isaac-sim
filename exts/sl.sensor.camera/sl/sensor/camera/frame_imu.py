"""The IMU of every physics step, for the ZED_FrameImu node to look up at each streamed frame's time.

A feeder (imu_stream) pushes each step's IMU to an ImuHistory registered under the path of the camera's
ZED_FrameImu node, which finds it with its own prim path.
"""
from __future__ import annotations

import bisect
import threading
from collections import deque

from pxr import Gf

# Seconds of physics steps kept: a frame is streamed a few render frames after the step it was rendered at.
HISTORY_S = 1.0

FOUND, NO_HISTORY, MISSED = 0, 1, 2

_histories: dict[str, ImuHistory] = {}


class ImuHistory:
    """Simulation time, sensor world orientation and sensor-frame specific force (m/s^2) of each physics step,
    in IsaacReadIMU's conventions."""

    def __init__(self):
        self._steps = deque()
        self._lock = threading.Lock()

    def push(self, t: float, orientation: Gf.Quatd, linear_acceleration: Gf.Vec3d) -> None:
        with self._lock:
            if self._steps and t <= self._steps[-1][0]:
                self._steps.clear()  # the simulation time went back: a new run
            self._steps.append((t, orientation, linear_acceleration))
            while self._steps[0][0] < t - HISTORY_S:
                self._steps.popleft()

    def at(self, t: float):
        """(FOUND, (orientation, linear acceleration)) at time t, interpolated between the steps around it;
        (NO_HISTORY, None) before the first step; (MISSED, None) when t is outside a history that should
        hold it."""
        with self._lock:
            steps = self._steps
            if not steps:
                return NO_HISTORY, None
            if t > steps[-1][0]:
                return MISSED, None
            if t < steps[0][0]:
                if steps[-1][0] - steps[0][0] >= 0.9 * HISTORY_S:
                    return MISSED, None
                t = steps[0][0]  # the first frames, rendered before the first step
            i = bisect.bisect_left(steps, t, key=lambda step: step[0])
            hi = steps[i]
            if hi[0] == t or i == 0:
                return FOUND, (hi[1], hi[2])
            lo = steps[i - 1]
            a = (t - lo[0]) / (hi[0] - lo[0])
            return FOUND, (Gf.Slerp(a, lo[1], hi[1]), lo[2] + a * (hi[2] - lo[2]))


def register(node_path: str, history: ImuHistory) -> None:
    _histories[node_path] = history


def unregister(node_path: str, history: ImuHistory) -> None:
    if _histories.get(node_path) is history:
        del _histories[node_path]


def lookup(node_path: str) -> ImuHistory | None:
    return _histories.get(node_path)
