"""Fix a ZED rigid body to a moving robot link.

A camera nested under a robot link does not follow it once Fabric is on - the nested USD
transform is never re-read. A light rigid body held to the link by a ``UsdPhysics.FixedJoint``,
excluded from the articulation so the solver does not fight the robot's controller, does.

Used by both the Isaac Sim demos and the Isaac Lab helpers.

pxr only (no Kit), so it imports in standalone Isaac Sim / Isaac Lab scripts.
"""
from pxr import Gf, Sdf, UsdPhysics


def author_fixed_joint(stage, link_prim_path: str, body_prim_path: str, local_pos, local_rot,
                       joint_name: str = "FixedJointToLink") -> bool:
    """Author a fixed joint holding `body_prim_path` at a pose in `link_prim_path`'s frame.

    Idempotent: an existing joint of that name is left alone, so calling it on every prestartup
    event is safe.

    Args:
        stage: The USD stage
        link_prim_path: The robot link the body is fixed to (joint body0)
        body_prim_path: The rigid body being held (joint body1); also where the joint is authored
        local_pos: (x, y, z) position of the body in the link frame
        local_rot: (w, x, y, z) rotation of the body in the link frame
        joint_name: Name of the joint prim, as a child of the body

    Returns:
        True if the joint is in place, False if the body prim does not exist
    """
    if not stage.GetPrimAtPath(body_prim_path).IsValid():
        return False
    joint_path = Sdf.Path(f"{body_prim_path}/{joint_name}")
    if stage.GetPrimAtPath(joint_path).IsValid():
        return True

    joint = UsdPhysics.FixedJoint.Define(stage, joint_path)
    joint.CreateBody0Rel().SetTargets([link_prim_path])
    joint.CreateBody1Rel().SetTargets([body_prim_path])
    joint.CreateLocalPos0Attr().Set(Gf.Vec3f(*[float(v) for v in local_pos]))
    joint.CreateLocalRot0Attr().Set(Gf.Quatf(*[float(v) for v in local_rot]))
    joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
    joint.CreateLocalRot1Attr().Set(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
    # Not part of the robot's articulation, or the solver treats it as an extra link.
    joint.CreateExcludeFromArticulationAttr(True)
    return True
