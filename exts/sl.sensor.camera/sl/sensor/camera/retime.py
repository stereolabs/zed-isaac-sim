"""The app timing that lets streamed ZED cameras send every frame.

Under Isaac Sim's multi-tick rendering a camera with ``omni:sensor:tickRate`` = fps is drawn in the first
app update whose physics reaches each tick k/fps, and the frame is stamped with its tick. A stream sends at
most one frame per app update (ZED_FrameImu), so it sends every frame only when no app update spans more
than 1/fps. An update is a whole number of physics steps: 60 Hz physics with 15 Hz updates puts 66.7 ms in
each, and a 30 fps stream then sends one frame in two.

:func:`retimed` is the rule and is Kit-free: a timing that fits is kept and any other gets the highest
multiple of the stream rates at or below the app's update rate, or with ``one_per_frame`` the app updates
once per frame.
:data:`TIMING_SETTING` picks ``fit``, ``frame`` or ``off`` (the app's timing is kept).
:func:`retime_on_play` applies it at each Play to the streams :func:`stream_rates` finds and puts back at
Stop what it changed (:func:`undo`); :func:`timing_problem` says why the running app cannot draw a camera
at its rate.
"""
from __future__ import annotations

import math
import sys
import traceback
from typing import Any, Callable, Iterable, List, NamedTuple, Optional, Tuple

try:
    import carb
    _log_error, _log_warn, _log_info = carb.log_error, carb.log_warn, carb.log_info
except ImportError:
    import logging
    _logger = logging.getLogger(__name__)
    _log_error, _log_warn, _log_info = _logger.error, _logger.warning, _logger.info

TIMING_SETTING = "/persistent/exts/sl.sensor.camera/streamTiming"
TIMING_FIT = "fit"
TIMING_FRAME = "frame"
TIMING_OFF = "off"
TIMINGS = (TIMING_FIT, TIMING_FRAME, TIMING_OFF)
_unknown_timing_warned = None
_retime_warned = False

# PhysX's step rate for a scene that does not author physxScene:timeStepsPerSecond
_PHYSX_DEFAULT_HZ = 60
# Where SimulationManager creates a physics scene at Play when the stage has none
_DEFAULT_SCENE_PATH = "/PhysicsScene"
# Relative: an update rate read back from a float step is a whole rate within this
_WHOLE_HZ_TOLERANCE = 1e-6
# PhysX simulates at most 1/minFrameRate s per app update and drops the rest
_MIN_FRAME_RATE = "/persistent/simulation/minFrameRate"
# On (Isaac Sim's GUI), the timeline advances 1/timeCodesPerSecond per update; off, the loop runner's step
_FIXED_TIME_STEPPING = "/app/player/useFixedTimeStepping"
_MULTI_TICK = "/rtx/hydra/supportMultiTickRate"
# Ahead of SimulationManager's warm start (order 0), which takes the run's first physics steps at Play
_PLAY_ORDER = -100
# After the Stop handlers at the default order 0, which still see the run's timing
_STOP_ORDER = 100
# Relative: a float read back from single-precision storage is the value written within this
_SAME_VALUE_TOLERANCE = 1e-6

_STREAM_NODE_TYPES = ("sl.sensor.camera.ZED_Camera", "sl.sensor.camera.ZED_Camera_One")


def whole_hz(rate) -> Optional[int]:
    """``rate`` (Hz) as an int when it is a whole rate, else None."""
    if not rate or rate <= 0:
        return None
    hz = round(rate)
    return hz if abs(rate - hz) <= _WHOLE_HZ_TOLERANCE * hz else None


def fits(physics_hz: int, update_hz, fps: int) -> bool:
    """Whether a stream at ``fps`` sends every frame: app updates at a whole rate, none spanning more than
    1/fps. An update is a whole number of physics steps, up to ceil(physics_hz / update) of them."""
    update = whole_hz(update_hz)
    return bool(update) and physics_hz > 0 and -(-physics_hz // update) * fps <= physics_hz


def retimed(physics_hz: int, update_hz, rates: Iterable[int], one_per_frame: bool = False) -> Tuple[int, int]:
    """The physics and app update rates (Hz) closest to these at which streams at each of ``rates`` (fps)
    send every frame (:func:`fits`).

    A timing that fits every rate is kept. Otherwise updates go to the highest multiple of every rate at or
    below ``update_hz`` (that multiple itself when ``update_hz`` is lower or None, updates following the
    wall clock), and physics to the next multiple of that, never slower than it was: 50 Hz physics with
    40 Hz updates becomes 60 Hz and 30 Hz for a 30 fps stream. ``one_per_frame`` sets updates to the
    lowest common multiple of the rates even when the timing fits: one update per frame for a single stream.
    """
    rates = list(rates)
    if physics_hz <= 0 or not rates or any(fps <= 0 for fps in rates):
        raise ValueError(f"needs a positive physics rate and frame rates, got {physics_hz} Hz and {rates}")
    step = math.lcm(*rates)
    if one_per_frame:
        update = step
    elif fits(physics_hz, update_hz, step):
        return physics_hz, whole_hz(update_hz)
    else:
        update = max(int(update_hz // step), 1) * step if update_hz else step
    return -(-physics_hz // update) * update, update


# ------------------------------------------------------------------ the running app (Kit)
def _physics_scenes(stage) -> list:
    from pxr import UsdPhysics

    return [prim for prim in stage.Traverse() if prim.IsA(UsdPhysics.Scene)]


def current_timing() -> Tuple[int, Optional[float]]:
    """The app's physics rate (Hz, its first physics scene's) and update rate (Hz, None when updates follow
    the wall clock)."""
    import carb.settings
    import omni.timeline
    import omni.usd

    stage = omni.usd.get_context().get_stage()
    scenes = _physics_scenes(stage) if stage else []
    attr = scenes[0].GetAttribute("physxScene:timeStepsPerSecond") if scenes else None
    value = attr.Get() if attr else None
    physics_hz = int(value) if value is not None else _PHYSX_DEFAULT_HZ

    if carb.settings.get_settings().get_as_bool(_FIXED_TIME_STEPPING):
        return physics_hz, omni.timeline.get_timeline_interface().get_time_codes_per_second()
    try:
        from omni.kit.loop import _loop

        loop = _loop.acquire_loop_interface()
        step_s = loop.get_manual_step_size() if loop.get_manual_mode() else 0.0
    except (ImportError, AttributeError):   # not Isaac Sim's loop runner
        step_s = 0.0
    return physics_hz, (1.0 / step_s if step_s > 0.0 else None)


def isaac_lab_drives_physics() -> bool:
    """Whether an Isaac Lab simulation steps the physics with its own step, whatever the app's timing says."""
    module = sys.modules.get("isaaclab.sim.simulation_context")
    context = getattr(module, "SimulationContext", None)
    return context is not None and context.instance() is not None


def stream_timing() -> str:
    """:data:`TIMING_SETTING`, one of :data:`TIMINGS`: fit when unset, and fit with a warning (once per value)
    when unknown."""
    import carb.settings

    global _unknown_timing_warned
    value = carb.settings.get_settings().get(TIMING_SETTING)
    timing = str(value).strip().lower() if value is not None else TIMING_FIT
    if timing in TIMINGS:
        return timing
    if value != _unknown_timing_warned:
        _unknown_timing_warned = value
        _log_warn(f"[ZED] {TIMING_SETTING} is '{value}', expected one of {', '.join(TIMINGS)}: using {TIMING_FIT}.")
    return TIMING_FIT


def set_stream_timing(timing: str) -> None:
    if timing not in TIMINGS:
        raise ValueError(f"Unknown ZED stream timing '{timing}', expected one of {TIMINGS}")
    import carb.settings

    carb.settings.get_settings().set(TIMING_SETTING, timing)


def _retime_app(rates: List[int], one_per_frame: bool = False) -> bool:
    """Retime the running app to :func:`retimed`'s rates for streams at ``rates`` (fps) and log what changed.

    Run it before the run's first physics step: the simulation clock reads the physics rate once a run, so
    a change after that makes simulation time jump. False when the app cannot be retimed."""
    global _retime_warned
    import carb.settings
    import omni.usd
    from pxr import PhysxSchema, UsdPhysics

    shown = "/".join(f"{fps:g}" for fps in sorted(set(rates)))
    physics_hz, update_hz = current_timing()
    try:
        physics, update = retimed(physics_hz, update_hz, rates, one_per_frame)
    except ValueError as e:
        _log_error(f"[ZED] Cannot retime the app for {shown} fps streams: {e}.")
        return False
    if update != whole_hz(update_hz):
        try:
            from isaacsim.core.rendering_manager import RenderingManager
        except ImportError:
            _log_error(f"[ZED] Cannot set the app update rate to {update} Hz for {shown} fps streams: "
                       f"isaacsim.core.rendering_manager is not available.")
            return False

    changes = []
    if physics != physics_hz:
        stage = omni.usd.get_context().get_stage()
        scenes = _physics_scenes(stage) or [UsdPhysics.Scene.Define(stage, _DEFAULT_SCENE_PATH).GetPrim()]
        for prim in scenes:
            # Not SimulationManager.set_physics_dt: it refuses while the timeline plays, which it does at PLAY.
            PhysxSchema.PhysxSceneAPI.Apply(prim).CreateTimeStepsPerSecondAttr().Set(physics)
        changes.append(f"physics {physics_hz} -> {physics} Hz")
    if update != whole_hz(update_hz):
        # Sets the loop runner's step and the timeline's (and stage's) time codes per second together.
        RenderingManager.set_dt(1.0 / update)
        changes.append(f"app updates {'wall clock' if update_hz is None else f'{update_hz:g} Hz'} -> {update} Hz")
    settings = carb.settings.get_settings()
    min_frame_rate = settings.get_as_int(_MIN_FRAME_RATE)
    if min_frame_rate > update:
        settings.set_int(_MIN_FRAME_RATE, update)
        changes.append(f"{_MIN_FRAME_RATE} {min_frame_rate} -> {update}")
    if changes:
        message = (f"[ZED] Retimed the app so the {shown} fps ZED streams send every frame: "
                   f"{', '.join(changes)}. Stop puts it back; set Stream timing in the ZED Cameras panel "
                   f"({TIMING_SETTING}) to {TIMING_OFF} to keep your timing.")
        # A new physics rate changes the simulation; frame timing is the user's choice, fit is the default
        if physics != physics_hz or not (one_per_frame or _retime_warned):
            _retime_warned = _retime_warned or not one_per_frame
            _log_warn(message)
        else:
            _log_info(message)
    return True


def timing_problem(fps: int, camera_path: str) -> Optional[str]:
    """Why the running app keeps a stream of the camera at ``camera_path`` from sending every frame, None when
    it does not."""
    import carb.settings
    import omni.usd

    physics_hz, update_hz = current_timing()
    if update_hz is None:
        return "app updates follow the wall clock, not a fixed step"
    update = whole_hz(update_hz)
    if not update:
        return f"app updates at {update_hz:g} Hz are not a whole rate"
    if not fits(physics_hz, update, fps):
        steps = -(-physics_hz // update)
        return (f"{physics_hz} Hz physics with {update} Hz app updates puts up to {steps} physics steps "
                f"({1000.0 * steps / physics_hz:.1f} ms) in an app update, more than a {1000.0 / fps:.1f} ms frame")
    settings = carb.settings.get_settings()
    prim = omni.usd.get_context().get_stage().GetPrimAtPath(camera_path)
    attr = prim.GetAttribute("omni:sensor:tickRate") if prim else None
    tick_rate = attr.Get() if attr and attr.HasAuthoredValue() and settings.get_as_bool(_MULTI_TICK) else None
    if whole_hz(tick_rate or update_hz) != fps:
        return f"the camera renders at {tick_rate or update_hz:g} fps"
    min_frame_rate = settings.get_as_int(_MIN_FRAME_RATE)
    if min_frame_rate > update_hz:
        return f"{_MIN_FRAME_RATE} is {min_frame_rate}, which drops physics steps from {update_hz:g} Hz app updates"
    return None


def physics_steps() -> Optional[int]:
    """Physics steps since Play, None outside Isaac Sim."""
    try:
        from isaacsim.core.simulation_manager import SimulationManager
    except ImportError:
        return None
    return SimulationManager.get_num_physics_steps()


def stream_rates() -> List[int]:
    """The frame rate of every enabled stream node in the stage's graphs."""
    import omni.graph.core as og

    from .utils import stream_frame_rate

    return [stream_frame_rate(og.Controller.get(node.get_attribute("inputs:fps")))
            for graph in og.get_all_graphs_and_subgraphs() for node in graph.get_nodes()
            if node.get_type_name() in _STREAM_NODE_TYPES and not node.is_disabled()]


# ------------------------------------------------------------------ putting the timing back (Kit-free)
# What a probe reads once its value is gone: the stage it belongs to was closed
GONE = object()


def _show(value) -> str:
    if value is None:
        return "unset"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


class Probe(NamedTuple):
    """One value a retime may change. ``read()`` returns it (None when unset, :data:`GONE` when gone) and
    ``write(value)`` sets it (None unsets it). ``before()``, when given, reads the value in effect before the
    retime where ``read()`` can lag behind it."""
    what: str
    read: Callable[[], Any]
    write: Callable[[Any], None]
    show: Callable[[Any], str] = _show
    before: Optional[Callable[[], Any]] = None


class Change(NamedTuple):
    probe: Probe
    old: Any
    new: Any


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return (isinstance(a, (int, float)) and isinstance(b, (int, float))
                and math.isclose(a, b, rel_tol=_SAME_VALUE_TOLERANCE))
    return a == b


def snapshot(probes: Iterable[Probe]) -> List[Tuple[Probe, Any]]:
    """Each probe with the value it has before a retime."""
    return [(probe, (probe.before or probe.read)()) for probe in probes]


def changes_since(before: Iterable[Tuple[Probe, Any]]) -> List[Change]:
    """The values that moved since ``before``, a :func:`snapshot`."""
    changes = []
    for probe, old in before:
        new = probe.read()
        if not _same(new, old):
            changes.append(Change(probe, old, new))
    return changes


def undo(changes: Iterable[Change]) -> Tuple[List[str], List[str]]:
    """Put back, latest first, each changed value that still holds what the change set. A value changed again
    since is kept, and one that is gone or already back is left alone. Returns what was put back and what was
    kept, for the log."""
    restored, kept = [], []
    for probe, old, new in reversed(list(changes)):
        try:
            now = probe.read()
            if now is GONE or _same(now, old):
                continue
            if not _same(now, new):
                kept.append(f"{probe.what} at {probe.show(now)}")
                continue
            probe.write(old)
            restored.append(f"{probe.what} {probe.show(new)} -> {probe.show(old)}")
        except Exception:
            _log_error(f"[ZED] Could not put {probe.what} back to {probe.show(old)}:\n{traceback.format_exc()}")
    return restored, kept


# ------------------------------------------------------------------ the values a retime changes (Kit)
_TIME_STEPS_PER_SECOND = "physxScene:timeStepsPerSecond"
# RenderingManager.set_dt writes these with the update rate
_RATE_LIMIT_FREQUENCY = "/app/runLoops/main/rateLimitFrequency"
_FABRIC_SIM_PERIOD = ("/app/settings/fabricDefaultSimPeriodNumerator",
                      "/app/settings/fabricDefaultSimPeriodDenominator")


def _hz(value) -> str:
    return _show(value) if value is None else f"{value:g} Hz"


def _setting_probe(path: str) -> Probe:
    import carb.settings

    settings = carb.settings.get_settings()

    def write(value):
        if value is None:
            settings.destroy_item(path)
        else:
            settings.set(path, value)

    return Probe(path, lambda: settings.get(path), write)


def _app_probes() -> List[Probe]:
    """The app's values that :func:`_retime_app` and ``RenderingManager.set_dt`` may change, apart from the
    timeline's (see :func:`_stage_probes` and :func:`retime_on_play`)."""
    probes = []
    try:
        from omni.kit.loop import _loop

        loop = _loop.acquire_loop_interface()
        probes += [Probe("app update step", loop.get_manual_step_size, loop.set_manual_step_size,
                         lambda step: _hz(1.0 / step) if step else _show(step)),
                   Probe("fixed app update step", loop.get_manual_mode, loop.set_manual_mode)]
    except (ImportError, AttributeError):   # not Isaac Sim's loop runner
        pass
    probes.append(_setting_probe(_RATE_LIMIT_FREQUENCY)._replace(show=_hz))
    return probes + [_setting_probe(path) for path in (*_FABRIC_SIM_PERIOD, _MIN_FRAME_RATE)]


def _stage_probes(stage) -> List[Probe]:
    """The stage's values that :func:`_retime_app` may change: the time codes per second, and the physics rate of
    each scene it would write, in the layer it would write it to (its edit target). They read :data:`GONE` once
    another stage is open.

    Kit keeps the timeline's time codes per second and the root layer's in step, each following the other at
    the next app update. The timeline's is the one in effect, but a value set on it reads back only after that
    update. The probe reads the root layer's and takes the timeline's as the value before the retime."""
    import omni.timeline
    import omni.usd
    from pxr import Sdf, Usd

    timeline = omni.timeline.get_timeline_interface()
    root_id = stage.GetRootLayer().identifier
    edit_id = stage.GetEditTarget().GetLayer().identifier

    def same_stage():
        now = omni.usd.get_context().get_stage()
        return now if now and now.GetRootLayer().identifier == root_id else None

    def read_tcps():
        now = same_stage()
        return GONE if now is None else now.GetRootLayer().timeCodesPerSecond

    def write_tcps(value):
        same_stage().GetRootLayer().timeCodesPerSecond = value
        timeline.set_time_codes_per_second(value)

    def physics(path: str) -> Probe:
        attr_path = Sdf.Path(path).AppendProperty(_TIME_STEPS_PER_SECOND)

        def read():
            layer = Sdf.Layer.Find(edit_id) if same_stage() else None
            if layer is None:
                return GONE
            spec = layer.GetAttributeAtPath(attr_path)
            return spec.default if spec and spec.HasDefaultValue() else None

        def write(value):
            now = same_stage()
            with Usd.EditContext(now, Sdf.Layer.Find(edit_id)):
                prim = now.GetPrimAtPath(path)
                if value is None:
                    prim.RemoveProperty(_TIME_STEPS_PER_SECOND)
                else:
                    prim.GetAttribute(_TIME_STEPS_PER_SECOND).Set(value)

        return Probe(f"physics {path}", read, write, _hz)

    paths = [str(prim.GetPath()) for prim in _physics_scenes(stage)] or [_DEFAULT_SCENE_PATH]
    tcps = Probe("time codes per second", read_tcps, write_tcps, before=timeline.get_time_codes_per_second)
    return [tcps] + [physics(path) for path in paths]


def retime_on_play(rates: Callable[[], Iterable[int]]):
    """Retime the app at every Play for the stream frame rates ``rates()`` returns, as :func:`stream_timing`
    says, unless Isaac Lab steps the physics, and put back at Stop each value the retime changed, unless it was
    changed again since. Returns the Play and Stop timeline subscriptions: drop them to stop."""
    import carb.settings
    import omni.timeline
    import omni.usd

    timeline = omni.timeline.get_timeline_interface()
    target_framerate = Probe("timeline target frame rate", timeline.get_target_framerate,
                             timeline.set_target_framerate, _hz)
    pending: List[Change] = []

    def on_play(_event):
        try:
            # A Play that resumes a pause finds physics already stepped: a new rate now would make
            # simulation time jump. None: not Isaac Sim, so no physics to retime.
            steps = physics_steps()
            if steps is None or steps:
                return
            wanted = list(rates())
            if not wanted:
                return
            timing = stream_timing()
            if timing == TIMING_OFF:
                return
            if isaac_lab_drives_physics():
                _log_warn("[ZED] Isaac Lab steps the physics, so the app is not retimed for the ZED streams: a "
                          "stream sends every frame only when no render spans more than 1/fps of physics steps.")
                return
            stage = omni.usd.get_context().get_stage()
            before = snapshot(_app_probes() + (_stage_probes(stage) if stage else []))
            target_before = timeline.get_target_framerate()
            try:
                _retime_app(wanted, one_per_frame=timing == TIMING_FRAME)
            finally:
                changes = changes_since(before)
                # set_dt sets the target frame rate to the rate limit it sets, and a timeline value set
                # reads back only after the next app update.
                rate_limit = next((c for c in changes if c.probe.what == _RATE_LIMIT_FREQUENCY), None)
                if rate_limit is not None and not _same(rate_limit.new, target_before):
                    changes.append(Change(target_framerate, target_before, rate_limit.new))
                # With fixed time stepping the timeline sets the rate limit at Play, before this handler,
                # and puts its own value back at Stop, before ours.
                if carb.settings.get_settings().get_as_bool(_FIXED_TIME_STEPPING):
                    changes = [c for c in changes if c.probe.what != _RATE_LIMIT_FREQUENCY]
                pending.extend(changes)
        except Exception:
            _log_error(f"[ZED] Retiming the app at Play failed:\n{traceback.format_exc()}")

    def on_stop(_event):
        try:
            restored, kept = undo(pending)
            if restored:
                _log_info(f"[ZED] Put the app's timing back at Stop: {', '.join(restored)}.")
            if kept:
                _log_warn(f"[ZED] Kept at Stop the timing changed during Play, not the one before Play: "
                          f"{', '.join(kept)}.")
        except Exception:
            _log_error(f"[ZED] Putting the app's timing back at Stop failed:\n{traceback.format_exc()}")
        finally:
            pending.clear()

    stream = timeline.get_timeline_event_stream()
    return (stream.create_subscription_to_pop_by_type(int(omni.timeline.TimelineEventType.PLAY), on_play,
                                                      order=_PLAY_ORDER, name="sl.sensor.camera retime"),
            stream.create_subscription_to_pop_by_type(int(omni.timeline.TimelineEventType.STOP), on_stop,
                                                      order=_STOP_ORDER, name="sl.sensor.camera restore"))
