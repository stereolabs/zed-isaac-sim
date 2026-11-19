"""Author a ZED camera model's optics onto a USD camera prim.

Used by the streaming, SDK-free capture and Isaac Lab paths, so a given model and resolution
render the same field of view and lens whichever one drives the camera.

pxr and numpy only (no Kit), so it imports in standalone Isaac Sim / Isaac Lab scripts.
"""
import math

from pxr import Gf, Sdf, Usd, UsdGeom

from . import fisheye_lut, sdk_virtual_camera
from .utils import (
    get_camera_model,
    get_distortion_coefficients,
    get_lens_type,
    get_optical_center,
    get_pinhole_parameters,
    get_sdk_model_id,
    get_sim_lens_type_id,
)

try:
    import carb
    _log_warn = carb.log_warn
except ImportError:
    import logging
    _log_warn = logging.getLogger(__name__).warning

_FISHEYE_SCHEMA = "OmniLensDistortionLutAPI"
_PINHOLE_SCHEMA = "OmniLensDistortionOpenCvPinholeAPI"
# Legacy camera attribute RTX reads as the field of view of the opencvFisheye and lut models, in
# degrees; unauthored, they render nothing past 100 degrees off-axis
_MAX_FOV_ATTR = "fthetaMaxFov"

# Right-eye pose of a virtual camera, authored on the session layer only
_RIGHT_EYE_OP_SUFFIX = "zedCalibration"
_RIGHT_EYE_OP_ATTR = f"xformOp:transform:{_RIGHT_EYE_OP_SUFFIX}"


def apply_camera_optics(cam_prim, camera_model, resolution_token, *, fps=None) -> bool:
    """Author `camera_model`'s field of view and lens on `cam_prim`.

    Args:
        cam_prim: The camera prim to author on
        camera_model: The full camera model name (e.g. "ZED_XONE_S_FISHEYE")
        resolution_token: The resolution name (see :func:`utils.get_supported_resolutions`)
        fps: Cap the render rate at this many frames per second (Isaac Sim 6.0 multi-tick
            rendering). None leaves the tick rate alone.

    Returns:
        True if the optics were authored, False if the model + resolution is unknown (the prim
        is then left as authored)
    """
    params = get_pinhole_parameters(camera_model, resolution_token)
    if params is None:
        _log_warn(f"[ZED] No optics for '{camera_model}' at resolution '{resolution_token}'; "
                  f"leaving {cam_prim.GetPath()} as authored.")
        return False

    cam_prim.GetAttribute("focalLength").Set(params["focal_length_mm"])
    cam_prim.GetAttribute("horizontalAperture").Set(params["horizontal_aperture_mm"])
    cam_prim.GetAttribute("verticalAperture").Set(params["vertical_aperture_mm"])
    cam_prim.GetAttribute("fStop").Set(0)   # no depth of field
    _set_tick_rate(cam_prim, fps)

    _apply_lens_distortion(cam_prim, camera_model, [params["width"], params["height"]],
                           params["focal_length_px"])
    # a camera previously run in virtual mode gets its asset pose back
    _clear_right_eye_pose(cam_prim)
    return True


def _set_tick_rate(cam_prim, fps) -> None:
    if fps is not None:
        cam_prim.ApplyAPI("OmniSensorAPI")
        cam_prim.GetAttribute("omni:sensor:tickRate").Set(float(fps))


def _clear_lens_distortion(cam_prim) -> None:
    """Remove the lens from the edit target and from the session layer, where the fisheye one lives."""
    stage = cam_prim.GetStage()
    for layer in (stage.GetEditTarget().GetLayer(), stage.GetSessionLayer()):
        spec = layer.GetPrimAtPath(cam_prim.GetPath())
        if spec is not None:
            _remove_lens_specs(spec)
    spec = stage.GetSessionLayer().GetPrimAtPath(cam_prim.GetPath())
    if spec is not None and "clippingRange" in spec.properties:
        spec.RemoveProperty(spec.properties["clippingRange"])


def _remove_lens_specs(spec) -> None:
    if spec.HasInfo("apiSchemas"):
        schemas = spec.GetInfo("apiSchemas")
        fields = ["explicitItems"] if schemas.isExplicit else ["prependedItems", "appendedItems", "deletedItems"]
        for field in fields:
            setattr(schemas, field, [s for s in getattr(schemas, field) if not s.startswith("OmniLensDistortion")])
        if schemas.isExplicit or any(getattr(schemas, field) for field in fields):
            spec.SetInfo("apiSchemas", schemas)
        else:
            spec.ClearInfo("apiSchemas")
    for name in [n for n in spec.properties.keys() if n.startswith("omni:lensdistortion:") or n == _MAX_FOV_ATTR]:
        spec.RemoveProperty(spec.properties[name])


def _corner_cosine(size, fx, fy, cx, cy, is_fisheye) -> float:
    """Cosine of the angle between the optical axis and the ray of the farthest image corner."""
    cosines = []
    for x in (0.0, size[0]):
        for y in (0.0, size[1]):
            r = math.hypot((x - cx) / fx, (y - cy) / fy)
            # a fisheye is taken as equidistant (angle = r), ignoring its k terms
            cosines.append(math.cos(r) if is_fisheye else 1.0 / math.sqrt(1.0 + r * r))
    return min(cosines)


def _apply_lens_schema(cam_prim, schema, corner_cosine) -> None:
    """Apply a lens schema and adapt the near clip to it, on the session layer (the scene keeps the asset's).

    With a lens schema RTX clips at the near distance along each ray instead of along the optical
    axis. The asset's near plane keeps the camera's own lens window out of the image; the near
    distance divided by the corner cosine keeps that plane out up to the image corners. A larger
    fixed value would also cut away the surface a camera rests on, its lens being only ~13-16 mm
    above it. Past 90 degrees (fisheye) no near distance keeps a plane out, so the asset's value stays.
    """
    cam_prim.ApplyAPI(schema)
    if corner_cosine <= 0.0:
        return
    stage = cam_prim.GetStage()
    attr = UsdGeom.Camera(cam_prim).GetClippingRangeAttr()
    near, far = attr.Get()
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        attr.Set(Gf.Vec2f(near / corner_cosine, far))


def _apply_lens_distortion(cam_prim, camera_model, resolution, focal_px) -> None:
    """Apply the model's lens distortion, or clear it for a pinhole model.

    The RTX renderer bends the image only while a lens schema is on the prim, and a placed asset
    switching its lens variant re-uses the same prim, hence the clearing half.
    """
    distortion = get_distortion_coefficients(camera_model)
    _clear_lens_distortion(cam_prim)
    if distortion is not None:
        cx, cy = get_optical_center(camera_model, resolution)
        _author_fisheye(cam_prim, resolution, focal_px, focal_px, cx, cy, distortion)


def _author_fisheye(cam_prim, size, fx, fy, cx, cy, k) -> None:
    """Render an OpenCV fisheye calibration (cx, cy from the center of the first pixel) through lookup textures.

    In the image corners, past about 100 degrees off-axis, the calibration is an extrapolation: its
    polynomial is fitted on targets nearer the axis and turns over around 120 degrees, so the
    corners follow the model rather than a measurement. Pixels past that angle stay black, or show the
    dome light as seen straight behind the camera.

    Session layer only: the textures are files of this machine's temp folder, so a saved scene
    keeps none of the lens and each run authors it again.
    """
    width, height = int(size[0]), int(size[1])
    unproject, project = fisheye_lut.textures(width, height, fx, fy, cx, cy, k)
    stage = cam_prim.GetStage()
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        _apply_lens_schema(cam_prim, _FISHEYE_SCHEMA, _corner_cosine(size, fx, fy, cx, cy, is_fisheye=True))
        prefix = "omni:lensdistortion:lut:"
        cam_prim.GetAttribute("omni:lensdistortion:model").Set("lut")
        cam_prim.GetAttribute(prefix + "nominalWidth").Set(float(width))
        cam_prim.GetAttribute(prefix + "nominalHeight").Set(float(height))
        # the textures carry the optical center; the schema's one stays at the image center
        cam_prim.GetAttribute(prefix + "opticalCenter").Set(Gf.Vec2f(width / 2.0, height / 2.0))
        cam_prim.GetAttribute(prefix + "rayEnterDirectionTexture").Set(Sdf.AssetPath(unproject))
        cam_prim.GetAttribute(prefix + "rayExitPositionTexture").Set(Sdf.AssetPath(project))
        # twice the lens's largest angle: the textures point the pixels past it straight back, which
        # a wider field of view would render
        cam_prim.CreateAttribute(_MAX_FOV_ATTR, Sdf.ValueTypeNames.Float, custom=True).Set(
            2.0 * math.degrees(fisheye_lut.theta_max(k)))


def setup_virtual_camera(left_prim, right_prim, camera_model, resolution_token, camera_index=None,
                         *, fps=None) -> "sdk_virtual_camera.VirtualCamera":
    """Get a simulated camera from the ZED SDK and render its prims with its calibration.

    Args:
        left_prim: The left camera prim (the only camera of a mono model)
        right_prim: The right camera prim, or None (mono model, or right eye not rendered)
        camera_model: The full camera model name (e.g. "ZED_X_4MM")
        resolution_token: The resolution name
        camera_index: See :func:`sdk_virtual_camera.acquire`
        fps: See :func:`apply_camera_optics`

    Returns:
        The camera; hand it back to :func:`sdk_virtual_camera.release` when done

    Raises:
        sdk_virtual_camera.VirtualCameraError: the SDK could not provide the camera
    """
    params = get_pinhole_parameters(camera_model, resolution_token)
    if params is None:
        raise sdk_virtual_camera.VirtualCameraError(
            f"Unknown resolution '{resolution_token}' for camera model '{camera_model}'.")

    camera = sdk_virtual_camera.acquire(
        get_sdk_model_id(get_camera_model(camera_model)), get_sim_lens_type_id(get_lens_type(camera_model)),
        int(params["width"]), int(params["height"]), camera_index)
    try:
        apply_virtual_camera_optics(left_prim, right_prim, camera.calibration, params["pixel_size_mm"], fps=fps)
    except Exception:
        sdk_virtual_camera.release(camera)
        raise
    prefix = f"[ZED] {left_prim.GetParent().GetPath()} "
    print(f"{prefix}virtual camera SN {camera.serial_number} (index {camera.index})\n"
          f"{camera.calibration.describe(prefix)}")
    return camera


def apply_virtual_camera_optics(left_prim, right_prim, calibration, pixel_size_mm, *, fps=None) -> None:
    """Author an SDK-generated calibration: per-eye intrinsics and distortion, right-eye pose.

    RTX ignores the aperture offsets and the vertical aperture, so fy, cx and cy only reach the
    image through the lens schemas; the pinhole one is applied even with zero distortion.
    """
    eyes = [(left_prim, calibration.left)]
    if right_prim is not None:
        eyes.append((right_prim, calibration.right))
    size = Gf.Vec2i(calibration.width, calibration.height)
    for prim, eye in eyes:
        _author_intrinsics(prim, eye, size, pixel_size_mm, calibration.is_fisheye)
        _set_tick_rate(prim, fps)
    if right_prim is not None:
        author_right_eye_pose(left_prim, right_prim, calibration)


def _author_intrinsics(cam_prim, eye, size, pixel_size_mm, is_fisheye) -> None:
    # focal length and apertures keep fx = focal * width / horizontalAperture (and the same for
    # fy), which is what Isaac Lab and the CameraParams annotator report
    cam_prim.GetAttribute("focalLength").Set(eye.fx * pixel_size_mm)
    cam_prim.GetAttribute("horizontalAperture").Set(size[0] * pixel_size_mm)
    cam_prim.GetAttribute("verticalAperture").Set(size[1] * pixel_size_mm * eye.fx / eye.fy)
    cam_prim.GetAttribute("fStop").Set(0)   # no depth of field

    _clear_lens_distortion(cam_prim)
    if is_fisheye:
        _author_fisheye(cam_prim, size, eye.fx, eye.fy, eye.cx, eye.cy,
                        [float(v) for v in sdk_virtual_camera.fisheye_coefficients(eye)])
        return
    _apply_lens_schema(cam_prim, _PINHOLE_SCHEMA,
                       _corner_cosine(size, eye.fx, eye.fy, eye.cx, eye.cy, is_fisheye=False))
    cam_prim.GetAttribute("omni:lensdistortion:model").Set("opencvPinhole")
    prefix = "omni:lensdistortion:opencvPinhole:"
    for name, value in zip(sdk_virtual_camera.DISTO_NAMES, eye.disto):
        cam_prim.GetAttribute(prefix + name).Set(float(value))
    cam_prim.GetAttribute(prefix + "fx").Set(float(eye.fx))
    cam_prim.GetAttribute(prefix + "fy").Set(float(eye.fy))
    # the SDK calibration puts pixel (0, 0) at the center of the first pixel (OpenCV), the lens
    # schema at its top-left corner
    cam_prim.GetAttribute(prefix + "cx").Set(float(eye.cx) + 0.5)
    cam_prim.GetAttribute(prefix + "cy").Set(float(eye.cy) + 0.5)
    cam_prim.GetAttribute(prefix + "imageSize").Set(size)


def right_eye_relative_matrix(calibration, meters_per_unit: float) -> Gf.Matrix4d:
    """Pose of the right eye in the left eye's USD camera frame, in stage units.

    The SDK's rectification hands the calibration to OpenCV's stereoRectify as R = (rx, ry, rz)
    and T = (-baseline, ty, tz), which map a point from the left eye frame into the right one, in
    the IMAGE frame (x right, y down, z forward, millimeters). The right eye's pose is the inverse
    of that map. A USD camera looks down -z with y up: a 180 degree turn about x.
    """
    rotation_vector = Gf.Vec3d(calibration.rx, calibration.ry, calibration.rz)
    angle = rotation_vector.GetLength()
    left_to_right = (Gf.Rotation(rotation_vector / angle, math.degrees(angle)) if angle > 0.0
                     else Gf.Rotation().SetIdentity())
    orientation = left_to_right.GetInverse()
    position = -orientation.TransformDir(Gf.Vec3d(-calibration.baseline_mm, calibration.ty_mm, calibration.tz_mm))

    # IMAGE -> USD camera frame; a rotation turned by 180 degrees about x keeps its angle and
    # turns its axis
    axis = orientation.GetAxis()
    orientation = Gf.Rotation(Gf.Vec3d(axis[0], -axis[1], -axis[2]), orientation.GetAngle())
    position = Gf.Vec3d(position[0], -position[1], -position[2]) * (1e-3 / meters_per_unit)
    return Gf.Matrix4d().SetTransform(orientation, position)


def author_right_eye_pose(left_prim, right_prim, calibration) -> None:
    """Place the right eye where the calibration says, relative to the left one.

    Session layer only: the pose belongs to this run's camera, not to the user's scene.
    """
    stage = right_prim.GetStage()
    xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    left_world = xform_cache.GetLocalToWorldTransform(left_prim)
    parent_world = xform_cache.GetParentToWorldTransform(right_prim)

    # the relative translation is in stage units, so apply it without the asset's scale
    left_scale = Gf.Matrix4d().SetScale(Gf.Transform(left_world).GetScale())
    left_rigid = Gf.Matrix4d(left_world).RemoveScaleShear()
    relative = right_eye_relative_matrix(calibration, UsdGeom.GetStageMetersPerUnit(stage))
    right_local = left_scale * relative * left_rigid * parent_world.GetInverse()

    with Usd.EditContext(stage, stage.GetSessionLayer()):
        xformable = UsdGeom.Xformable(right_prim)
        if right_prim.HasAttribute(_RIGHT_EYE_OP_ATTR):
            op = UsdGeom.XformOp(right_prim.GetAttribute(_RIGHT_EYE_OP_ATTR))
        else:
            op = xformable.AddTransformOp(opSuffix=_RIGHT_EYE_OP_SUFFIX)
        op.Set(right_local)
        xformable.SetXformOpOrder([op])


def _clear_right_eye_pose(cam_prim) -> None:
    spec = cam_prim.GetStage().GetSessionLayer().GetPrimAtPath(cam_prim.GetPath())
    if spec is None or _RIGHT_EYE_OP_ATTR not in spec.properties:
        return
    for name in (_RIGHT_EYE_OP_ATTR, "xformOpOrder"):
        if name in spec.properties:
            spec.RemoveProperty(spec.properties[name])
