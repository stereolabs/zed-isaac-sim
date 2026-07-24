# ******************************************************************************
# File Name          : zed_quadruped.py
# Description        : Isaac Lab flagship demo port. A walking ANYmal-C quadruped on
#                      generated rough terrain, driven by the pretrained ANYmal-C
#                      "HeightScan" locomotion policy and steered live from the keyboard.
#                      A real ZED_X USD model rides the base link (rigid body + fixed joint)
#                      and its authored CameraLeft/CameraRight deliver batched stereo RGB +
#                      render-based depth as (N, H, W, C) tensors across N envs. No ZED SDK.
#
# Combines two Isaac Lab patterns (BSD-3-Clause, The Isaac Lab Project Developers): the scene +
# JIT locomotion policy from scripts/tutorials/03_envs/create_quadruped_base_env.py, and the
# keyboard command injection from scripts/demos/h1_locomotion.py. The ZED delta: the single
# pinhole is replaced by the real ZED_X model mounted on the base link, whose authored stereo
# cameras are read directly - no pinhole.
#
# The walking policy is downloaded from the Isaac Lab Nucleus server on first run
# (Policies/ANYmal-C/HeightScan/policy.pt) - needs network access.
#
# Keyboard controls (Isaac Lab Se2Keyboard; need a focused Kit viewport - click it first):
#   UP / DOWN   walk forward / back        LEFT / RIGHT  strafe left / right
#   Z / X       turn left / right          L             reset command to zero
# For a headless / non-interactive walk, pass --command VX VY WZ instead of using the keyboard.
#
# Usage (rendering must be enabled; one robot by default, --num_envs to spawn more):
#   # GUI, keyboard-steered, streaming per-env depth stats:
#   F:\IsaacLab\isaaclab.bat -p exts\sl.sensor.camera\examples\isaaclab\zed_quadruped.py --verbose
#   # capture frames to disk while walking:
#   F:\IsaacLab\isaaclab.bat -p exts\sl.sensor.camera\examples\isaaclab\zed_quadruped.py --save_dir F:\zed_quad_out --num_frames 5 --save_every 10
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

parser = argparse.ArgumentParser(description="Walking ANYmal-C with a ZED stereo pair on the base link, keyboard-steered.")
add_zed_cli_args(parser)
parser.add_argument("--num_envs", type=int, default=1, help="Number of environments (robots) to spawn.")
parser.add_argument("--disable_fabric", action="store_true", help="Disable Fabric API and use USD instead.")
parser.add_argument("--save_every", type=int, default=10, help="Save one batch every N steps when --save_dir is set.")
parser.add_argument("--reset_every", type=int, default=0,
                    help="Reset the scene every N steps (0 = never; use to recover fallen robots).")
parser.add_argument("--command", type=float, nargs=3, default=None, metavar=("VX", "VY", "WZ"),
                    help="Constant velocity command (m/s, m/s, rad/s); overrides the keyboard and "
                         "lets the robot walk headlessly (e.g. --command 1 0 0).")
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
# Keyboard teleop needs a focused GUI window, so open the Kit visualizer - unless running
# headless (cameras still render via --enable_cameras, but keyboard input is unavailable)
# or the user explicitly selected another visualizer.
if getattr(args, "headless", False):
    if args.command is None:
        print("[ZED] WARNING: --headless -> no Kit window; keyboard steering unavailable. Pass "
              "--command VX VY WZ to make the robot walk (otherwise it stands still).")
elif not getattr(args, "visualizer", None):
    args.visualizer = ["kit"]

app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

# ---- Everything below runs after the Kit app exists ----
import functools
import math

# Flush prints immediately so progress is visible during the (slow) first render.
print = functools.partial(print, flush=True)

import numpy as np
import torch

import isaaclab.envs.mdp as mdp
import isaaclab.sim as sim_utils
from isaaclab.assets import ArticulationCfg, AssetBaseCfg
from isaaclab.devices import Se2Keyboard, Se2KeyboardCfg
from isaaclab.envs import ManagerBasedEnv, ManagerBasedEnvCfg
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.sensors import RayCasterCfg, patterns
from isaaclab.terrains import TerrainImporterCfg
from isaaclab.utils.assets import ISAACLAB_NUCLEUS_DIR, check_file_path, read_file
from isaaclab.utils.configclass import configclass
from isaaclab.utils.noise import UniformNoiseCfg as Unoise

from isaaclab.terrains.config.rough import ROUGH_TERRAINS_CFG  # isort:skip
from isaaclab_assets.robots.anymal import ANYMAL_C_CFG  # isort:skip

from sl.sensor.camera.isaaclab_utils import (  # noqa: E402
    author_zed_link_joint, depth_to_2d, make_zed_usd_link_mount, save_batch_frames, unwrap_output,
)
from sl.sensor.camera.utils import get_baseline  # noqa: E402

_W, _H = get_resolution(args.camera_model, args.resolution)

# ZED mounted on the ANYmal base link, looking forward (+X of the base). Placement is a local
# translate + RotateXYZ(deg) in the base frame - the SL-demo convention. Tune in-engine.
_ZED_BASE_LOCALPOS0 = (0.38, 0.0, 0.16)         # on the front of the body, just high enough to clear it
_ZED_BASE_ROT_EULER_DEG = (180.0, 0.0, 0.0)     # authored ZED camera looks +X (base forward)

# Robot spawn yaw about Z (degrees) - orients its forward/walking direction. NOTE: the onboard ZED
# view rolls with the spawn yaw (an Isaac Lab joint-mounted-camera quirk: roll ~ yaw mod 180 deg), so
# only EVEN multiples of 180 (0, 180) keep the horizon level. 90/270 roll the image 90 deg.
_ROBOT_SPAWN_YAW_DEG = 180.0
_h = math.radians(_ROBOT_SPAWN_YAW_DEG) / 2.0
_ROBOT_SPAWN_QUAT = (math.cos(_h), 0.0, 0.0, math.sin(_h))  # (w, x, y, z)

# GUI follow-cam distances (meters): how far BEHIND the robot the viewport sits, how high, and how
# far AHEAD of it to aim. Applied each step by _update_follow_cam so the camera tracks the base
# position AND yaw (a true chase cam that swings around on turns). Tune to taste.
_CAM_BEHIND_M, _CAM_UP_M, _CAM_AHEAD_M = 3.5, 1.4, 2.0


# Steering: a shared command holder read by the velocity_command obs term. It is refreshed each
# step from the Se2Keyboard device (interactive) or the constant --command (headless / CI).
_CMD = {"vx": 0.0, "vy": 0.0, "wz": 0.0}  # ANYmal-C policy command: base lin vel x/y + ang vel z


def velocity_command(env: ManagerBasedEnv) -> torch.Tensor:
    """Observation term: the current keyboard-driven velocity command, broadcast to all envs."""
    return torch.tensor([[_CMD["vx"], _CMD["vy"], _CMD["wz"]]], device=env.device).repeat(env.num_envs, 1)


def _author_zed_base_joint(env, env_ids=None, **kwargs):
    """prestartup event: rigidly fix each env's ZED rigid body to its ANYmal base link.

    Runs after the scene is built but before physics initializes, so PhysX parses the joint
    (ManagerBasedEnv applies prestartup events before sim.reset()).
    """
    for i in range(env.scene.num_envs):
        author_zed_link_joint(env.sim.stage, f"/World/envs/env_{i}/Robot/base",
                              f"/World/envs/env_{i}/zed", _ZED_BASE_LOCALPOS0, _ZED_BASE_ROT_EULER_DEG)


# ==============================================================================
# Scene + MDP config (copy-adapted from Isaac Lab's create_quadruped_base_env.py,
# BSD-3-Clause). The ZED stereo pair is assigned onto the scene instance in main().
# ==============================================================================


@configclass
class ZedQuadrupedSceneCfg(InteractiveSceneCfg):
    """Rough-terrain scene with an ANYmal-C robot and a height scanner for the walking policy."""

    terrain = TerrainImporterCfg(
        prim_path="/World/ground",
        terrain_type="generator",
        terrain_generator=ROUGH_TERRAINS_CFG,
        max_init_terrain_level=5,
        collision_group=-1,
        physics_material=sim_utils.RigidBodyMaterialCfg(
            friction_combine_mode="multiply",
            restitution_combine_mode="multiply",
            static_friction=1.0,
            dynamic_friction=1.0,
        ),
        debug_vis=False,
    )

    # Spawn yaw about Z so the robot faces - and walks toward - the terrain interior instead of the
    # near edge. Single knob in degrees; tune it live if the heading is off. The policy is
    # body-frame, so walking is unaffected by the spawn yaw.
    robot: ArticulationCfg = ANYMAL_C_CFG.replace(
        prim_path="{ENV_REGEX_NS}/Robot",
        init_state=ANYMAL_C_CFG.init_state.replace(rot=_ROBOT_SPAWN_QUAT),
    )

    # The ANYmal-C HeightScan policy consumes a 1.6 x 1.0 m grid height scan under the base.
    height_scanner = RayCasterCfg(
        prim_path="{ENV_REGEX_NS}/Robot/base",
        offset=RayCasterCfg.OffsetCfg(pos=(0.0, 0.0, 20.0)),
        ray_alignment="yaw",
        pattern_cfg=patterns.GridPatternCfg(resolution=0.1, size=[1.6, 1.0]),
        debug_vis=False,
        mesh_prim_paths=["/World/ground"],
    )

    # Sun + sky fill so the terrain reads well from the robot's low, forward-looking view.
    light = AssetBaseCfg(
        prim_path="/World/light",
        spawn=sim_utils.DistantLightCfg(color=(1.0, 0.98, 0.95), intensity=3500.0, angle=5.0),
    )
    sky_light = AssetBaseCfg(
        prim_path="/World/skyLight",
        spawn=sim_utils.DomeLightCfg(color=(0.8, 0.85, 1.0), intensity=1500.0),
    )


@configclass
class ActionsCfg:
    """Action specifications for the MDP."""

    joint_pos = mdp.JointPositionActionCfg(asset_name="robot", joint_names=[".*"], scale=0.5, use_default_offset=True)


@configclass
class ObservationsCfg:
    """Observation specifications - term order must match the ANYmal-C HeightScan policy."""

    @configclass
    class PolicyCfg(ObsGroup):
        """Observations for the policy group."""

        base_lin_vel = ObsTerm(func=mdp.base_lin_vel, noise=Unoise(n_min=-0.1, n_max=0.1))
        base_ang_vel = ObsTerm(func=mdp.base_ang_vel, noise=Unoise(n_min=-0.2, n_max=0.2))
        projected_gravity = ObsTerm(func=mdp.projected_gravity, noise=Unoise(n_min=-0.05, n_max=0.05))
        velocity_commands = ObsTerm(func=velocity_command)  # keyboard-driven (replaces the tutorial's constant)
        joint_pos = ObsTerm(func=mdp.joint_pos_rel, noise=Unoise(n_min=-0.01, n_max=0.01))
        joint_vel = ObsTerm(func=mdp.joint_vel_rel, noise=Unoise(n_min=-1.5, n_max=1.5))
        actions = ObsTerm(func=mdp.last_action)
        height_scan = ObsTerm(
            func=mdp.height_scan,
            params={"sensor_cfg": SceneEntityCfg("height_scanner")},
            noise=Unoise(n_min=-0.1, n_max=0.1),
            clip=(-1.0, 1.0),
        )

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    policy: PolicyCfg = PolicyCfg()


@configclass
class EventCfg:
    """Configuration for events."""

    reset_scene = EventTerm(func=mdp.reset_scene_to_default, mode="reset")
    # USD-level fixed joint fixing the ZED to the base link; must run before physics starts.
    zed_base_joint = EventTerm(func=_author_zed_base_joint, mode="prestartup")


@configclass
class QuadrupedEnvCfg(ManagerBasedEnvCfg):
    """Locomotion environment for a keyboard-steered walking ANYmal-C."""

    scene: ZedQuadrupedSceneCfg = ZedQuadrupedSceneCfg(num_envs=args.num_envs, env_spacing=2.5)
    observations: ObservationsCfg = ObservationsCfg()
    actions: ActionsCfg = ActionsCfg()
    events: EventCfg = EventCfg()

    def __post_init__(self):
        self.decimation = 4               # env decimation -> 50 Hz control
        self.sim.dt = 0.005               # 200 Hz physics
        self.sim.render_interval = self.decimation
        self.sim.physics_material = self.scene.terrain.physics_material
        self.sim.device = args.device
        self.sim.use_fabric = not args.disable_fabric
        if self.scene.height_scanner is not None:
            self.scene.height_scanner.update_period = self.decimation * self.sim.dt  # 50 Hz


def _update_follow_cam(env, robot):
    """Per-step chase cam: keep the GUI viewport behind the robot's base, looking forward,
    rotating with the base yaw so it follows turns. We override the viewport camera each step.
    First env only; caller skips it when headless."""
    rp = robot.data.root_pos_w
    hw = robot.data.heading_w  # canonical base yaw (world), same field the MDP uses
    pos = (rp.torch if hasattr(rp, "torch") else rp)[0].tolist()
    heading = float((hw.torch if hasattr(hw, "torch") else hw)[0])
    # heading_w points along the robot's forward (base +X). Camera sits behind it and aims ahead.
    fx, fy = math.cos(heading), math.sin(heading)
    env.sim.set_camera_view(
        eye=(pos[0] - fx * _CAM_BEHIND_M, pos[1] - fy * _CAM_BEHIND_M, pos[2] + _CAM_UP_M),
        target=(pos[0] + fx * _CAM_AHEAD_M, pos[1] + fy * _CAM_AHEAD_M, pos[2] + 0.3),
    )


def main():
    env_cfg = QuadrupedEnvCfg()
    # The real ZED_X model rides the base link (spawned as a rigid body, fixed to the link by the
    # prestartup joint above) and its authored CameraLeft/CameraRight are the stereo sensors (no
    # pinhole). USD-level fixed-joint authoring requires scene replication off.
    env_cfg.scene.replicate_physics = False
    env_cfg.scene.zed_model, env_cfg.scene.zed_left, env_cfg.scene.zed_right = make_zed_usd_link_mount(
        "{ENV_REGEX_NS}/zed", args.camera_model, args.resolution, spawn_init_pos=(0.4, 0.0, 0.6))

    env = ManagerBasedEnv(cfg=env_cfg)

    # Load the pretrained walking policy (downloaded from Nucleus on first run).
    policy_path = ISAACLAB_NUCLEUS_DIR + "/Policies/ANYmal-C/HeightScan/policy.pt"
    if not check_file_path(policy_path):
        raise FileNotFoundError(f"Policy file '{policy_path}' does not exist.")
    policy = torch.jit.load(read_file(policy_path)).to(env.device).eval()

    # Steering: constant --command (headless / CI) or the interactive Se2Keyboard device.
    keyboard = None
    if args.command is not None:
        _CMD["vx"], _CMD["vy"], _CMD["wz"] = args.command
        print(f"[ZED] Constant command vx={args.command[0]} vy={args.command[1]} wz={args.command[2]} (keyboard disabled).")
    elif getattr(args, "headless", False):
        print("[ZED] Headless with no --command: robot will stand still.")
    else:
        keyboard = Se2Keyboard(Se2KeyboardCfg(
            v_x_sensitivity=1.0, v_y_sensitivity=0.6, omega_z_sensitivity=1.0, sim_device=env.device))
        keyboard.reset()
        print("[ZED] Keyboard steering ready - click the 3D viewport to focus it, then:")
        print(str(keyboard))

    print(f"[ZED] {args.num_envs} env(s), walking ANYmal-C, "
          f"baseline = {get_baseline(args.camera_model) * 1e-3:.3f} m, {_W}x{_H}.")
    print("[ZED] Submitting first render - on a cold RTX shader cache this can take several "
          "minutes (compiling, not hung). Subsequent runs are fast.")

    if args.save_dir:
        os.makedirs(args.save_dir, exist_ok=True)
    # Without --save_dir this is a console-only run: stream until the app/window closes,
    # ignoring --num_frames. With --save_dir, capture exactly --num_frames step batches.
    run_forever = args.save_dir is None
    if run_forever:
        print("[ZED] No --save_dir -> streaming indefinitely (ignoring --num_frames); stop with Ctrl-C / close the window.")

    robot = env.scene["robot"]
    zed_left, zed_right = env.scene["zed_left"], env.scene["zed_right"]
    follow_cam = not getattr(args, "headless", False)  # no viewport to steer when headless
    obs, _ = env.reset()
    step = 0
    saved = 0
    warmed = False
    fall_cooldown = 30   # grace to let the robot settle after start/reset before fall-checking
    fallen_streak = 0    # consecutive tilted frames (a transient spike must not trigger a reset)
    while simulation_app.is_running() and (run_forever or saved < args.num_frames):
        # Stop before touching physics if Kit is tearing down (avoids a released-view ReferenceError).
        if env.sim.is_stopped():
            break
        # Refresh the shared command from the keyboard (the obs term reads it inside env.step).
        if keyboard is not None:
            _CMD["vx"], _CMD["vy"], _CMD["wz"] = keyboard.advance().tolist()
        with torch.inference_mode():
            if args.reset_every and step > 0 and step % args.reset_every == 0:
                obs, _ = env.reset()
                print("[INFO]: Resetting environment...")
            action = policy(obs["policy"])
            try:
                obs, _ = env.step(action)
            except Exception as exc:  # noqa: BLE001 - benign if Kit is tearing down mid-step
                if simulation_app.is_running():
                    raise
                print(f"[ZED] Kit shut down mid-step ({type(exc).__name__}) - exiting.")
                break
        step += 1

        if follow_cam:
            _update_follow_cam(env, robot)

        # Auto-recover: if the base stays tipped over, reset. projected_gravity_b z is ~-1 upright
        # and rises toward 0 as the base tilts (> -0.3 ~ tilted past ~70 deg). Require a sustained
        # tilt so normal balancing on rough terrain does not trigger it. (Resets all envs - fine
        # for the single-robot default.)
        if fall_cooldown > 0:
            fall_cooldown -= 1
        else:
            pg = robot.data.projected_gravity_b
            pg = pg.torch if hasattr(pg, "torch") else pg
            fallen_streak = fallen_streak + 1 if bool((pg[:, 2] > -0.3).any()) else 0
            if fallen_streak >= 8:  # ~0.16 s tilted => really down, not mid-stride
                print("[ZED] Robot tipped over - resetting to recover.")
                obs, _ = env.reset()
                fall_cooldown = 30
                fallen_streak = 0

        rgb_l = unwrap_output(zed_left.data.output, "rgb")                      # (N, H, W, 3)
        rgb_r = unwrap_output(zed_right.data.output, "rgb")                     # (N, H, W, 3)
        depth = unwrap_output(zed_left.data.output, "distance_to_image_plane")  # (N, H, W, 1)
        if rgb_l is None or depth is None:
            continue  # annotator buffers still filling (warmup)
        if not warmed:
            print(f"[ZED] Streaming data after {step} frames.")
            warmed = True

        # Only pull depth to host when we actually need it (on a save step, or verbose).
        want_save = args.save_dir and (step % args.save_every == 0)
        d = depth_to_2d(depth).detach().cpu().numpy() if (args.verbose or want_save) else None  # (N, H, W)

        if args.verbose and d is not None:
            valid = np.isfinite(d) & (d > 0)
            per_env = " ".join(f"env{e}:{100.0 * valid[e].mean():.0f}%" for e in range(d.shape[0]))
            print(f"  step {step}: cmd(vx={_CMD['vx']:.1f} vy={_CMD['vy']:.1f} wz={_CMD['wz']:.1f}) | "
                  f"rgb_l {tuple(rgb_l.shape)} | depth {tuple(depth.shape)} | valid[{per_env}]")

        if want_save:
            save_batch_frames(os.path.join(args.save_dir, f"step_{step:05d}"), rgb_l, rgb_r, d)
            saved += 1
            print(f"[ZED] Saved batch {saved}/{args.num_frames} to step_{step:05d}/")

    if args.save_dir:
        print(f"[ZED] Saved {saved} step batch(es) under {args.save_dir}")
    try:
        env.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[ZED] (env.close raised during shutdown: {exc})")


if __name__ == "__main__":
    main()
    simulation_app.close()
    print("[ZED] Done.")
