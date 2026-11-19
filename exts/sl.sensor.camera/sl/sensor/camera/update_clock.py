"""The app update a rendered frame's tick fell in, for a stream to send at most one frame per app update, evenly
spaced, and declare the rate it sends at.

Under multi-tick rendering (rtx.hydra.supportMultiTickRate in Isaac Sim's apps, a camera's omni:sensor:tickRate)
a camera faster than the app updates renders several ticks in one update, each showing the physics state at its
tick k / fps (IsaacReadSimulationTime's time, the frame's stamp). The clock kept here records the physics time at
the end of each app update: a tick belongs to the first update whose end is at or after it.
"""
from __future__ import annotations

import bisect
import math
import statistics
import threading
from collections import deque

import carb

# Seconds of update ends kept: a frame is read back a few updates after the one it was rendered at.
HISTORY_S = 2.0
# Float slack between a tick and the update end it equals, seconds.
_MATCH_S = 1e-6
# Update ends the update period is the median over.
_PERIOD_ENDS = 9
_STEP_ORDER = 10


def first_end_at_or_after(t: float, update_ends) -> float | None:
    """The first of ``update_ends`` (ascending) at or after ``t``, None when none is."""
    i = bisect.bisect_left(update_ends, t - _MATCH_S)
    return update_ends[i] if i < len(update_ends) else None


def frame_stride(fps: int, update_period: float | None) -> int:
    """How many ticks apart the frames are that a stream ticking at ``fps`` sends, with app updates of
    ``update_period`` seconds of simulation time: 1 when no update spans more than a tick or the period is
    unknown (None), else the fewest that keep each sent frame in an app update of its own. Every stride-th tick
    keeps the frames evenly spaced: the ZED SDK's sender drops a frame closer than 0.8 of the declared period to
    the last one, so the first tick of each update, 33 then 67 ms apart at 30 fps over 20 Hz updates, would
    reach the receiver at 10 fps."""
    if not update_period or update_period <= 0.0 or fps * update_period <= 1.0 + _MATCH_S:
        return 1
    return math.ceil(fps * update_period - _MATCH_S)


def stream_rate(fps: int, update_period: float | None) -> int:
    """The rate a stream ticking at ``fps`` sends frames at (:func:`frame_stride`), rounded down to a whole
    rate, as the receiver is given it."""
    return max(1, fps // frame_stride(fps, update_period))


class UpdateClock:
    """The physics time at the end of each app update, from each physics step and the update it ran in."""

    def __init__(self):
        self._ends = deque()
        self._update = None
        self._last = None  # the latest step's time: the running update's end so far
        self._lock = threading.Lock()

    def step(self, update: int, t: float) -> None:
        with self._lock:
            if self._last is not None and t < self._last:  # the simulation time went back: a new run
                self._ends.clear()
                self._update = self._last = None
            if update != self._update and self._last is not None:
                self._ends.append(self._last)
            self._update, self._last = update, t
            while self._ends and self._ends[0] < t - HISTORY_S:
                self._ends.popleft()

    def update_end(self, t: float) -> float | None:
        with self._lock:
            ends = list(self._ends) + ([self._last] if self._last is not None else [])
        return first_end_at_or_after(t, ends)

    def update_period(self) -> float | None:
        """The simulation time an app update covers, seconds: the median over the latest finished updates. None
        before two of them."""
        with self._lock:
            ends = list(self._ends)[-_PERIOD_ENDS:]
        if len(ends) < 2:
            return None
        return statistics.median(b - a for a, b in zip(ends, ends[1:]))

    def clear(self) -> None:
        with self._lock:
            self._ends.clear()
            self._update = self._last = None


_clock = UpdateClock()
_users = 0
_sub = None


def acquire() -> None:
    """Record the update ends while a stream asks update_end(); pair with release()."""
    global _users, _sub
    _users += 1
    if _sub is not None:
        return
    try:
        import omni.kit.app
        import omni.physics.core
        from isaacsim.core.simulation_manager import SimulationManager
    except ImportError as exc:
        carb.log_info(f"[ZED] Streams send every rendered frame ({exc}).")
        return
    app = omni.kit.app.get_app()

    def on_step(_dt, _context):
        _clock.step(app.get_update_number(), SimulationManager.get_simulation_time())

    _sub = omni.physics.core.get_physics_simulation_interface().subscribe_physics_on_step_events(
        pre_step=False, order=_STEP_ORDER, on_update=on_step)


def release() -> None:
    global _users, _sub
    _users = max(0, _users - 1)
    if _users == 0:
        _sub = None
        _clock.clear()


def update_end(t: float) -> float | None:
    """The physics time at the end of the app update a frame stamped ``t`` (IsaacReadSimulationTime) was
    rendered in, seconds; None when no update end at or after it was recorded (no physics steps, or acquire()
    not called)."""
    return _clock.update_end(t)


def update_period() -> float | None:
    """The simulation time an app update covers, seconds; None before two updates were recorded."""
    return _clock.update_period()


def recording() -> bool:
    """Whether update ends are being recorded: acquire() found the physics step events."""
    return _sub is not None
