# ******************************************************************************
# File Name          : zed_record_demos.py
# Description        : Isaac Lab flagship demo port. Keyboard-teleop imitation-learning
#                      recording: a human drives the Franka to stack cubes while the sim
#                      records HDF5 demonstrations whose camera observations come from a real
#                      wrist-mounted ZED_X (left + right RGB + optional ZED depth). No ZED SDK.
#
# Mirrors the keyboard path of Isaac Lab's scripts/tools/record_demos.py on task
# IsaacContrib-Stack-Cube-Franka-IK-Rel-Visuomotor.
# The ZED delta: the real ZED_X USD model is mounted on the panda_hand wrist (rigid body
# + fixed joint) and its authored CameraLeft/CameraRight are recorded (no pinhole);
# a right-eye RGB and a ZED depth observation (optionally degraded) are added. The
# task's static table camera is dropped, the robot-mounted view is the relevant one here.
#
# Keyboard teleop:
#   arrow / WASDQE etc. move the end-effector, K/L toggle the gripper, R resets the demo.
#
# Usage:
#   F:\IsaacLab\isaaclab.bat -p exts\sl.sensor.camera\examples\isaaclab\zed_record_demos.py --num_demos 1 --dataset_file F:\demos\zed_stack.hdf5
#   ... --domain_rand             # re-enable the (Nucleus-heavy) light/texture randomization
#
# NOTE: the very first rendered frame compiles RTX shaders and can take minutes on a cold
# cache; subsequent runs are fast.
# ******************************************************************************

import argparse
import os
import sys

# The ZED package (sl.sensor.camera) is importable without enabling the Kit extension;
# _bootstrap walks up to the extension root and puts it on sys.path (depth-independent).
_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.isfile(os.path.join(_d, "_bootstrap.py")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
import _bootstrap  # noqa: E402,F401  (adds the sl.sensor.camera extension root to sys.path)

from isaaclab.app import AppLauncher

from sl.sensor.camera.isaaclab_utils import add_zed_cli_args
from sl.sensor.camera.utils import get_resolution

parser = argparse.ArgumentParser(description="Record ZED-observation HDF5 demos by keyboard teleop (cube stacking).")
add_zed_cli_args(parser)
parser.add_argument("--dataset_file", type=str, default="./datasets/zed_stack_demos.hdf5",
                    help="File path to export recorded demos.")
parser.add_argument("--step_hz", type=int, default=30, help="Environment stepping rate in Hz.")
parser.add_argument("--num_demos", type=int, default=0, help="Number of demonstrations to record (0 = infinite).")
parser.add_argument("--num_success_steps", type=int, default=10,
                    help="Consecutive success steps required to conclude a demo as successful.")
parser.add_argument("--domain_rand", action="store_true",
                    help="Re-enable the Nucleus-heavy light/texture randomization events (off by default).")
# Adds --headless, --enable_cameras, --device, and --verbose.
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()

# --resolution choices are the union over all models; validate the pair.
if get_resolution(args.camera_model, args.resolution) is None:
    parser.error(f"--resolution {args.resolution} is not supported by {args.camera_model}")

# RGB/depth are render-based and this Isaac Lab build is headless-by-default with cameras
# OFF; force rendering on so the script works with or without --enable_cameras.
if not args.enable_cameras:
    print("[ZED] Enabling cameras (--enable_cameras) - required for RGB/depth rendering.")
args.enable_cameras = True
# Keyboard teleop needs a focused GUI window.
if getattr(args, "headless", False):
    print("[ZED] WARNING: --headless -> no Kit window; keyboard teleop is UNAVAILABLE. "
          "Use this only for a boot/obs-spec smoke test, not for actually recording demos.")

app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

# ---- Everything below runs after the Kit app exists ----
import functools
import time

# Flush prints immediately so progress is visible during the (slow) first render.
print = functools.partial(print, flush=True)

import gymnasium as gym
import torch

from isaaclab.devices import Se3Keyboard, Se3KeyboardCfg
from isaaclab.envs.mdp import image as mdp_image
from isaaclab.envs.mdp.recorders.recorders_cfg import ActionStateRecorderManagerCfg
from isaaclab.managers import DatasetExportMode, EventTermCfg, ObservationTermCfg as ObsTerm, SceneEntityCfg

import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils.parse_cfg import parse_env_cfg

from sl.sensor.camera.isaaclab_utils import author_zed_link_joint, make_zed_usd_link_mount  # noqa: E402
from sl.sensor.camera.utils import get_baseline, get_pinhole_parameters  # noqa: E402

_TASK = "IsaacContrib-Stack-Cube-Franka-IK-Rel-Visuomotor"
_P = get_pinhole_parameters(args.camera_model, args.resolution)
_W, _H = _P["width"], _P["height"]

# Wrist ZED placement in the panda_hand frame (SL-demo convention: translate + RotateXYZ deg).
_WRIST_LOCALPOS0 = (0.018, 0.0, 0.034)
_WRIST_ROT_EULER_DEG = (0.0, 90.0, 0.0)


class RateLimiter:
    """Convenience class for enforcing rates in loops (copied from record_demos.py)."""

    def __init__(self, hz):
        self.hz = hz
        self.last_time = time.time()
        self.sleep_duration = 1.0 / hz
        self.render_period = min(0.033, self.sleep_duration)

    def sleep(self, env):
        next_wakeup_time = self.last_time + self.sleep_duration
        while time.time() < next_wakeup_time:
            time.sleep(self.render_period)
            env.sim.render()
        self.last_time = self.last_time + self.sleep_duration
        if self.last_time < time.time():
            while self.last_time < time.time():
                self.last_time += self.sleep_duration


def _rgb_term(entity):
    return ObsTerm(func=mdp_image,
                   params={"sensor_cfg": SceneEntityCfg(entity), "data_type": "rgb", "normalize": False})


def _author_wrist_zed_joint(env, env_ids=None, **kwargs):
    """prestartup event: fix each env's wrist ZED rigid body to its panda_hand."""
    for i in range(env.scene.num_envs):
        author_zed_link_joint(env.sim.stage, f"/World/envs/env_{i}/Robot/panda_hand",
                              f"/World/envs/env_{i}/wrist_zed", _WRIST_LOCALPOS0, _WRIST_ROT_EULER_DEG)


def configure_cameras(env_cfg):
    """Mount the real ZED_X on the panda_hand wrist (rigid body + fixed joint) and record its
    authored CameraLeft/CameraRight, no pinhole. The task's static table camera is dropped
    (robot-mounted view is the relevant one for this wrist-teleop recording)."""
    # Drop the task's mono table camera and its policy observation term.
    env_cfg.scene.table_cam = None
    env_cfg.observations.policy.table_cam = None

    # Real ZED on the wrist; its authored cameras take over the task's wrist_cam entity names,
    # so the task's existing `wrist_cam` ObsTerm keeps working. The fixed joint is authored by
    # the prestartup event (registered in main()).
    model, left, right = make_zed_usd_link_mount(
        "{ENV_REGEX_NS}/wrist_zed", args.camera_model, args.resolution, spawn_init_pos=(0.4, 0.0, 0.55))
    env_cfg.scene.wrist_zed_model = model
    env_cfg.scene.wrist_cam = left
    env_cfg.scene.wrist_cam_right = right

    # Add the right-eye RGB and a ZED depth policy observation term.
    policy = env_cfg.observations.policy
    policy.wrist_cam_right = _rgb_term("wrist_cam_right")
    depth_params = {"sensor_cfg": SceneEntityCfg("wrist_cam"),
                    "data_type": "distance_to_image_plane", "normalize": False}
    policy.wrist_cam_depth = ObsTerm(func=mdp_image, params=depth_params)

    # Keep the visuomotor cfg's image list in sync with the new (wrist-only) terms.
    env_cfg.image_obs_list = ["wrist_cam", "wrist_cam_right", "wrist_cam_depth"]


def main():
    output_dir = os.path.dirname(os.path.abspath(args.dataset_file))
    output_file_name = os.path.splitext(os.path.basename(args.dataset_file))[0]
    os.makedirs(output_dir, exist_ok=True)
    # Actual file the recorder writes (it appends .hdf5 to dataset_filename); used below to
    # report the result and to remove an empty stub after a no-success run.
    dataset_path = os.path.join(output_dir, output_file_name + ".hdf5")

    env_cfg = parse_env_cfg(_TASK, device=args.device, num_envs=1)
    env_cfg.env_name = _TASK

    configure_cameras(env_cfg)
    # prestartup (USD-level) joint authoring for the wrist ZED requires scene replication off.
    env_cfg.scene.replicate_physics = False
    env_cfg.events.zed_wrist_joint = EventTermCfg(func=_author_wrist_zed_joint, mode="prestartup")

    # Unless --domain_rand, null the Nucleus-heavy randomization events (~24 4k HDR/texture
    # downloads) so recording works offline and stays visually stable across resets.
    if not args.domain_rand:
        for name in ("randomize_light", "randomize_table_visual_material", "randomize_robot_arm_visual_texture"):
            if hasattr(env_cfg.events, name):
                setattr(env_cfg.events, name, None)

    # Recorder wiring (mirrors record_demos.py): run until success/reset, export successes only.
    success_term = env_cfg.terminations.success
    env_cfg.terminations.success = None
    env_cfg.terminations.time_out = None
    env_cfg.observations.policy.concatenate_terms = False
    env_cfg.recorders = ActionStateRecorderManagerCfg()
    env_cfg.recorders.dataset_export_dir_path = output_dir
    env_cfg.recorders.dataset_filename = output_file_name
    env_cfg.recorders.dataset_export_mode = DatasetExportMode.EXPORT_SUCCEEDED_ONLY

    env = gym.make(_TASK, cfg=env_cfg).unwrapped

    print(f"[ZED] {args.camera_model} wrist-mounted authored cameras, {_W}x{_H}, "
          f"baseline {get_baseline(args.camera_model) * 1e-3:.3f} m. Depth (ground truth) recorded.")
    try:
        print("[ZED] Policy observation terms:", list(env.observation_manager.active_terms.get("policy", [])))
    except Exception as exc:  # noqa: BLE001 - purely informational
        print(f"[ZED] (could not list observation terms: {exc})")
    print("[ZED] Submitting first render - on a cold RTX shader cache this can take several "
          "minutes (compiling, not hung). Subsequent runs are fast.")

    # Keyboard teleop. advance() returns a 7-dim tensor [dx,dy,dz,rx,ry,rz,gripper+/-1],
    # which matches the IK-Rel + binary-gripper action space directly.
    teleop = Se3Keyboard(Se3KeyboardCfg(pos_sensitivity=0.2, rot_sensitivity=0.5))

    should_reset = False

    def reset_recording_instance():
        nonlocal should_reset
        should_reset = True
        print("[ZED] Reset requested.")

    teleop.add_callback("R", reset_recording_instance)

    rate_limiter = RateLimiter(args.step_hz)
    recorded = 0
    success_step_count = 0

    env.sim.reset()
    env.reset()
    teleop.reset()
    print("[ZED] Recording started. Stack the cubes; a successful stack is auto-saved. Press R to discard/reset.")

    with torch.inference_mode():
        try:
            while simulation_app.is_running():
                # Break before touching physics if the sim/app is shutting down, so we don't
                # call env.step() against a physics view Kit has already released on teardown.
                if env.sim.is_stopped():
                    break

                action = teleop.advance()
                if action is None:
                    env.sim.render()
                    continue
                actions = action.repeat(env.num_envs, 1)
                env.step(actions)

                # Success check: N consecutive success steps -> export the episode.
                if success_term is not None and bool(success_term.func(env, **success_term.params)[0]):
                    success_step_count += 1
                    if success_step_count >= args.num_success_steps:
                        env.recorder_manager.record_pre_reset([0], force_export_or_skip=False)
                        env.recorder_manager.set_success_to_episodes(
                            [0], torch.tensor([[True]], dtype=torch.bool, device=env.device))
                        env.recorder_manager.export_episodes([0])
                        should_reset = True
                else:
                    success_step_count = 0

                if env.recorder_manager.exported_successful_episode_count > recorded:
                    recorded = env.recorder_manager.exported_successful_episode_count
                    print(f"[ZED] Recorded {recorded} successful demonstrations.")

                if args.num_demos > 0 and recorded >= args.num_demos:
                    print(f"[ZED] All {recorded} demonstrations recorded. Exiting.")
                    break

                if should_reset:
                    env.sim.reset()
                    env.recorder_manager.reset()
                    env.reset()
                    teleop.reset()
                    success_step_count = 0
                    should_reset = False

                rate_limiter.sleep(env)
        except KeyboardInterrupt:
            print("[ZED] Interrupted - finalizing dataset.")
        except Exception as exc:  # noqa: BLE001
            # A released physics-view weakref (ReferenceError) or similar raised while Kit is
            # tearing down is a benign shutdown race. Re-raise anything that happens while the
            # app is still alive - that is a real error, not a teardown artifact.
            if simulation_app.is_running():
                raise
            print(f"[ZED] Kit shut down mid-step ({type(exc).__name__}) - finalizing dataset.")

    # Always finalize the dataset, even if the loop died in the teardown race above.
    # recorder_manager.close() flushes + closes the HDF5 and touches no physics, so it is safe
    # here; call it before env.close(), which stops physics and dels managers in an order that
    # can abort before reaching the recorder. Both closes are idempotent.
    try:
        recorded = env.recorder_manager.exported_successful_episode_count
    except Exception:  # noqa: BLE001 - purely to refresh the count for the message below
        pass
    try:
        env.recorder_manager.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[ZED] (recorder close raised during shutdown: {exc})")
    try:
        env.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[ZED] (env.close raised during shutdown: {exc})")

    # A zero-demo run leaves an unusable HDF5 stub (opened but never populated); remove it so a
    # no-success session doesn't masquerade as a real dataset.
    if recorded == 0 and os.path.isfile(dataset_path):
        try:
            os.remove(dataset_path)
            print(f"[ZED] No successful demos recorded - removed empty dataset {dataset_path}.")
        except OSError as exc:
            print(f"[ZED] (could not remove empty dataset {dataset_path}: {exc})")
    else:
        print(f"[ZED] Session complete: {recorded} demo(s) saved to {dataset_path}.")


if __name__ == "__main__":
    main()
    simulation_app.update()
    simulation_app.close()
