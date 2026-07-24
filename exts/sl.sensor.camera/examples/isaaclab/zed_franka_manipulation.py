# ******************************************************************************
# File Name          : zed_franka_manipulation.py
# Description        : Isaac Lab flagship demo port. Autonomous Franka pick-and-lift
#                      driven by a Warp state machine (no human, no policy). A real ZED_X
#                      USD model rides the gripper and its authored stereo cameras deliver
#                      stereo RGB + render-based depth as (N, H, W, C) tensors. No ZED SDK.
#
# Mirrors Isaac Lab's scripts/environments/state_machine/lift_cube_sm.py on task
# IsaacContrib-Lift-Cube-Franka-IK-Abs. The PickAndLiftSm class and the infer_state_machine
# Warp kernel are copied verbatim from that script (BSD-3-Clause, The Isaac Lab Project
# Developers). The ZED delta: the ZED_X.usdc model is spawned as a rigid body rigidly fixed
# to panda_hand (fixed joint authored by a prestartup event) so it tracks the gripper, and
# its authored CameraLeft/CameraRight are read directly (no pinhole).
#
# Usage (rendering must be enabled; runs headless):
#   F:\IsaacLab\isaaclab.bat -p exts\sl.sensor.camera\examples\isaaclab\zed_franka_manipulation.py --headless --num_envs 4 --num_frames 5 --save_dir F:\zed_franka_out
#   F:\IsaacLab\isaaclab.bat -p exts\sl.sensor.camera\examples\isaaclab\zed_franka_manipulation.py --num_envs 1
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

parser = argparse.ArgumentParser(description="Autonomous Franka pick-and-lift state machine with a ZED table-view pair.")
add_zed_cli_args(parser, default_model="ZED_X_Nano")
parser.add_argument("--num_envs", type=int, default=4, help="Number of environments to simulate.")
parser.add_argument("--disable_fabric", action="store_true", help="Disable fabric and use USD I/O operations.")
parser.add_argument("--save_every", type=int, default=10, help="Save one batch every N steps when --save_dir is set.")
# Adds --headless, --enable_cameras, --device, and --verbose (gates the per-frame log below).
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

app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

# ---- Everything below runs after the Kit app exists ----
import functools

# Flush prints immediately so progress is visible during the (slow) first render.
print = functools.partial(print, flush=True)

from collections.abc import Sequence

import gymnasium as gym
import numpy as np
import torch
import warp as wp

from isaaclab.assets.rigid_object.rigid_object_data import RigidObjectData
from isaaclab.managers import EventTermCfg

import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.core.lift.lift_env_cfg import LiftEnvCfg
from isaaclab_tasks.utils.parse_cfg import parse_env_cfg

from sl.sensor.camera.isaaclab_utils import (  # noqa: E402
    author_zed_link_joint, depth_to_2d, make_zed_usd_link_mount, save_batch_frames, unwrap_output,
)
from sl.sensor.camera.utils import get_baseline  # noqa: E402

# initialize warp
wp.init()

_W, _H = get_resolution(args.camera_model, args.resolution)


# ==============================================================================
# The following PickAndLiftSm class + infer_state_machine kernel are copied
# verbatim from Isaac Lab's scripts/environments/state_machine/lift_cube_sm.py
# (BSD-3-Clause, The Isaac Lab Project Developers). Only the ZED cameras, per-step
# tensor read/save and headless CI mode below are additions.
# ==============================================================================


class GripperState:
    """States for the gripper."""

    OPEN = wp.constant(1.0)
    CLOSE = wp.constant(-1.0)


class PickSmState:
    """States for the pick state machine."""

    REST = wp.constant(0)
    APPROACH_ABOVE_OBJECT = wp.constant(1)
    APPROACH_OBJECT = wp.constant(2)
    GRASP_OBJECT = wp.constant(3)
    LIFT_OBJECT = wp.constant(4)


class PickSmWaitTime:
    """Additional wait times (in s) for states for before switching."""

    REST = wp.constant(0.2)
    APPROACH_ABOVE_OBJECT = wp.constant(0.5)
    APPROACH_OBJECT = wp.constant(0.6)
    GRASP_OBJECT = wp.constant(0.3)
    LIFT_OBJECT = wp.constant(1.0)


@wp.func
def distance_below_threshold(current_pos: wp.vec3, desired_pos: wp.vec3, threshold: float) -> bool:
    return wp.length(current_pos - desired_pos) < threshold


@wp.kernel
def infer_state_machine(
    dt: wp.array(dtype=float),
    sm_state: wp.array(dtype=int),
    sm_wait_time: wp.array(dtype=float),
    ee_pose: wp.array(dtype=wp.transform),
    object_pose: wp.array(dtype=wp.transform),
    des_object_pose: wp.array(dtype=wp.transform),
    des_ee_pose: wp.array(dtype=wp.transform),
    gripper_state: wp.array(dtype=float),
    offset: wp.array(dtype=wp.transform),
    position_threshold: float,
):
    # retrieve thread id
    tid = wp.tid()
    # retrieve state machine state
    state = sm_state[tid]
    # decide next state
    if state == PickSmState.REST:
        des_ee_pose[tid] = ee_pose[tid]
        gripper_state[tid] = GripperState.OPEN
        # wait for a while
        if sm_wait_time[tid] >= PickSmWaitTime.REST:
            # move to next state and reset wait time
            sm_state[tid] = PickSmState.APPROACH_ABOVE_OBJECT
            sm_wait_time[tid] = 0.0
    elif state == PickSmState.APPROACH_ABOVE_OBJECT:
        des_ee_pose[tid] = wp.transform_multiply(offset[tid], object_pose[tid])
        gripper_state[tid] = GripperState.OPEN
        if distance_below_threshold(
            wp.transform_get_translation(ee_pose[tid]),
            wp.transform_get_translation(des_ee_pose[tid]),
            position_threshold,
        ):
            # wait for a while
            if sm_wait_time[tid] >= PickSmWaitTime.APPROACH_OBJECT:
                # move to next state and reset wait time
                sm_state[tid] = PickSmState.APPROACH_OBJECT
                sm_wait_time[tid] = 0.0
    elif state == PickSmState.APPROACH_OBJECT:
        des_ee_pose[tid] = object_pose[tid]
        gripper_state[tid] = GripperState.OPEN
        if distance_below_threshold(
            wp.transform_get_translation(ee_pose[tid]),
            wp.transform_get_translation(des_ee_pose[tid]),
            position_threshold,
        ):
            if sm_wait_time[tid] >= PickSmWaitTime.APPROACH_OBJECT:
                # move to next state and reset wait time
                sm_state[tid] = PickSmState.GRASP_OBJECT
                sm_wait_time[tid] = 0.0
    elif state == PickSmState.GRASP_OBJECT:
        des_ee_pose[tid] = object_pose[tid]
        gripper_state[tid] = GripperState.CLOSE
        # wait for a while
        if sm_wait_time[tid] >= PickSmWaitTime.GRASP_OBJECT:
            # move to next state and reset wait time
            sm_state[tid] = PickSmState.LIFT_OBJECT
            sm_wait_time[tid] = 0.0
    elif state == PickSmState.LIFT_OBJECT:
        des_ee_pose[tid] = des_object_pose[tid]
        gripper_state[tid] = GripperState.CLOSE
        if distance_below_threshold(
            wp.transform_get_translation(ee_pose[tid]),
            wp.transform_get_translation(des_ee_pose[tid]),
            position_threshold,
        ):
            # wait for a while
            if sm_wait_time[tid] >= PickSmWaitTime.LIFT_OBJECT:
                # move to next state and reset wait time
                sm_state[tid] = PickSmState.LIFT_OBJECT
                sm_wait_time[tid] = 0.0
    # increment wait time
    sm_wait_time[tid] = sm_wait_time[tid] + dt[tid]


class PickAndLiftSm:
    """A simple state machine in a robot's task space to pick and lift an object.

    The state machine is implemented as a warp kernel. It takes in the current state of
    the robot's end-effector and the object, and outputs the desired state of the robot's
    end-effector and the gripper. The state machine is implemented as a finite state
    machine with the following states:

    1. REST: The robot is at rest.
    2. APPROACH_ABOVE_OBJECT: The robot moves above the object.
    3. APPROACH_OBJECT: The robot moves to the object.
    4. GRASP_OBJECT: The robot grasps the object.
    5. LIFT_OBJECT: The robot lifts the object to the desired pose. This is the final state.
    """

    def __init__(self, dt: float, num_envs: int, device: torch.device | str = "cpu", position_threshold=0.01):
        """Initialize the state machine.

        Args:
            dt: The environment time step.
            num_envs: The number of environments to simulate.
            device: The device to run the state machine on.
        """
        # save parameters
        self.dt = float(dt)
        self.num_envs = num_envs
        self.device = device
        self.position_threshold = position_threshold
        # initialize state machine
        self.sm_dt = torch.full((self.num_envs,), self.dt, device=self.device)
        self.sm_state = torch.full((self.num_envs,), 0, dtype=torch.int32, device=self.device)
        self.sm_wait_time = torch.zeros((self.num_envs,), device=self.device)

        # desired state
        self.des_ee_pose = torch.zeros((self.num_envs, 7), device=self.device)
        self.des_gripper_state = torch.full((self.num_envs,), 0.0, device=self.device)

        # approach above object offset
        self.offset = torch.zeros((self.num_envs, 7), device=self.device)
        self.offset[:, 2] = 0.1
        self.offset[:, -1] = 1.0  # warp expects quaternion as (x, y, z, w)

        # convert to warp
        self.sm_dt_wp = wp.from_torch(self.sm_dt, wp.float32)
        self.sm_state_wp = wp.from_torch(self.sm_state, wp.int32)
        self.sm_wait_time_wp = wp.from_torch(self.sm_wait_time, wp.float32)
        self.des_ee_pose_wp = wp.from_torch(self.des_ee_pose, wp.transform)
        self.des_gripper_state_wp = wp.from_torch(self.des_gripper_state, wp.float32)
        self.offset_wp = wp.from_torch(self.offset, wp.transform)

    def reset_idx(self, env_ids: Sequence[int] = None):
        """Reset the state machine."""
        if env_ids is None:
            env_ids = slice(None)
        self.sm_state[env_ids] = 0
        self.sm_wait_time[env_ids] = 0.0

    def compute(self, ee_pose: torch.Tensor, object_pose: torch.Tensor, des_object_pose: torch.Tensor) -> torch.Tensor:
        """Compute the desired state of the robot's end-effector and the gripper."""

        # convert to warp
        ee_pose_wp = wp.from_torch(ee_pose.contiguous(), wp.transform)
        object_pose_wp = wp.from_torch(object_pose.contiguous(), wp.transform)
        des_object_pose_wp = wp.from_torch(des_object_pose.contiguous(), wp.transform)

        # run state machine
        wp.launch(
            kernel=infer_state_machine,
            dim=self.num_envs,
            inputs=[
                self.sm_dt_wp,
                self.sm_state_wp,
                self.sm_wait_time_wp,
                ee_pose_wp,
                object_pose_wp,
                des_object_pose_wp,
                self.des_ee_pose_wp,
                self.des_gripper_state_wp,
                self.offset_wp,
                self.position_threshold,
            ],
            device=self.device,
        )

        # convert to torch
        return torch.cat([self.des_ee_pose, self.des_gripper_state.unsqueeze(-1)], dim=-1)


# ==============================================================================
# End of copied Isaac Lab code.
# ==============================================================================


# Arm-mounted ZED placed like the Stereolabs SL Isaac-Sim demo (extension.py): parented in
# the panda_hand frame with a local translate + RotateXYZ(deg). Tune in-engine if needed.
_ZED_ARM_LOCALPOS0 = (0.018, 0.0, 0.034)
_ZED_ARM_ROT_EULER_DEG = (0.0, 90.0, 0.0)       # RotateXYZ degrees (SL demo placement, faces forward)


def _author_zed_arm_joints(env, env_ids=None, **kwargs):
    """prestartup event: rigidly fix each env's ZED rigid body to its panda_hand.

    Runs after the scene is built but before physics initializes, so PhysX parses the
    joint (see ManagerBasedEnv: prestartup events are applied before sim.reset()).
    """
    for i in range(env.scene.num_envs):
        author_zed_link_joint(env.sim.stage, f"/World/envs/env_{i}/Robot/panda_hand",
                              f"/World/envs/env_{i}/zed", _ZED_ARM_LOCALPOS0, _ZED_ARM_ROT_EULER_DEG)


def _read_and_save(env, save_dir, saved):
    """Read the arm ZED's authored stereo cameras and save one batch. Returns saved+1."""
    scene = env.unwrapped.scene
    rgb_l = unwrap_output(scene["zed_left"].data.output, "rgb")
    rgb_r = unwrap_output(scene["zed_right"].data.output, "rgb")
    depth = unwrap_output(scene["zed_left"].data.output, "distance_to_image_plane")
    if rgb_l is None or depth is None:
        return saved
    d = depth_to_2d(depth).detach().cpu().numpy()
    save_batch_frames(os.path.join(save_dir, f"zed_{saved:05d}"), rgb_l, rgb_r, d)
    if args.verbose:
        valid = np.isfinite(d) & (d > 0)
        per_env = " ".join(f"env{e}:{100.0 * valid[e].mean():.0f}%" for e in range(d.shape[0]))
        print(f"[ZED] batch {saved}: rgb {tuple(rgb_l.shape)} | depth {tuple(depth.shape)} | valid[{per_env}]")
    return saved + 1


def main():
    # parse configuration
    env_cfg: LiftEnvCfg = parse_env_cfg(
        "IsaacContrib-Lift-Cube-Franka-IK-Abs",
        device=args.device,
        num_envs=args.num_envs,
        use_fabric=not args.disable_fabric,
    )
    # Arm-mounted ZED: the real ZED_X model rides the gripper (spawned as a rigid body, rigidly
    # fixed to panda_hand via the prestartup-event joint below) and its authored CameraLeft/
    # CameraRight are the stereo sensors (no pinhole). prestartup (USD-level) joint authoring
    # requires scene replication off.
    env_cfg.scene.replicate_physics = False
    env_cfg.scene.zed_model, env_cfg.scene.zed_left, env_cfg.scene.zed_right = make_zed_usd_link_mount(
        "{ENV_REGEX_NS}/zed", args.camera_model, args.resolution, spawn_init_pos=(0.4, 0.0, 0.55))
    env_cfg.events.zed_arm_joint = EventTermCfg(func=_author_zed_arm_joints, mode="prestartup")
    # Hide the goal-pose debug frame markers (RGB axis gizmos) - they are real prims in the
    # scene, so the ZED render product would otherwise capture them in the RGB/depth output.
    env_cfg.commands.object_pose.debug_vis = False

    # create environment
    env = gym.make("IsaacContrib-Lift-Cube-Franka-IK-Abs", cfg=env_cfg)
    # reset environment at start
    env.reset()

    print(f"[ZED] {args.num_envs} envs, arm-mounted ZED (authored cameras), "
          f"baseline = {get_baseline(args.camera_model) * 1e-3:.3f} m, {_W}x{_H}.")
    print("[ZED] Submitting first render - on a cold RTX shader cache this can take several "
          "minutes (compiling, not hung). Subsequent runs are fast.")

    if args.save_dir:
        os.makedirs(args.save_dir, exist_ok=True)
    # Without --save_dir this is a console-only run: run until the app closes, ignoring
    # --num_frames. With --save_dir, capture --num_frames batches then exit (CI mode).
    run_forever = args.save_dir is None
    if run_forever:
        print("[ZED] No --save_dir -> running indefinitely (ignoring --num_frames); stop with Ctrl-C / close the window.")

    # create action buffers (position + quaternion)
    actions = torch.zeros(env.unwrapped.action_space.shape, device=env.unwrapped.device)
    actions[:, 3] = 1.0
    # desired object orientation (we only do position control of object)
    desired_orientation = torch.zeros((env.unwrapped.num_envs, 4), device=env.unwrapped.device)
    desired_orientation[:, 1] = 1.0
    # create state machine
    pick_sm = PickAndLiftSm(
        env_cfg.sim.dt * env_cfg.decimation, env.unwrapped.num_envs, env.unwrapped.device, position_threshold=0.01
    )

    step = 0
    saved = 0
    while simulation_app.is_running() and (run_forever or saved < args.num_frames):
        if env.unwrapped.sim.is_stopped():  # Kit tearing down: stop before touching a released view
            break
        # run everything in inference mode
        with torch.inference_mode():
            # step environment
            try:
                dones = env.step(actions)[-2]
            except Exception as exc:  # noqa: BLE001 - benign if Kit is tearing down mid-step
                if simulation_app.is_running():
                    raise
                print(f"[ZED] Kit shut down mid-step ({type(exc).__name__}) - exiting.")
                break

            # observations
            # -- end-effector frame
            ee_frame_sensor = env.unwrapped.scene["ee_frame"]
            tcp_rest_position = (
                ee_frame_sensor.data.target_pos_w.torch[..., 0, :].clone() - env.unwrapped.scene.env_origins
            )
            tcp_rest_orientation = ee_frame_sensor.data.target_quat_w.torch[..., 0, :].clone()
            # -- object frame
            object_data: RigidObjectData = env.unwrapped.scene["object"].data
            object_position = object_data.root_pos_w.torch - env.unwrapped.scene.env_origins
            # -- target object frame
            desired_position = env.unwrapped.command_manager.get_command("object_pose")[..., :3]

            # advance state machine
            actions = pick_sm.compute(
                torch.cat([tcp_rest_position, tcp_rest_orientation], dim=-1),
                torch.cat([object_position, desired_orientation], dim=-1),
                torch.cat([desired_position, desired_orientation], dim=-1),
            )

            # reset state machine
            if dones.any():
                pick_sm.reset_idx(dones.nonzero(as_tuple=False).squeeze(-1))

        # ZED read/save (outside inference_mode is fine - read-only tensor ops).
        if args.save_dir and step % args.save_every == 0:
            saved = _read_and_save(env, args.save_dir, saved)
        step += 1

    if args.save_dir:
        print(f"[ZED] Saved {saved} batch(es) under {args.save_dir}")
    try:
        env.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[ZED] (env.close raised during shutdown: {exc})")


if __name__ == "__main__":
    main()
    simulation_app.close()
