"""Author a ZED camera model's optics onto a USD camera prim.

Used by the streaming, SDK-free capture and Isaac Lab paths, so a given model and resolution
render the same field of view and lens whichever one drives the camera.

pxr only (no Kit), so it imports in standalone Isaac Sim / Isaac Lab scripts.
"""
import math

from pxr import Gf, Usd, UsdGeom

from .utils import get_distortion_coefficients, get_optical_center, get_pinhole_parameters

try:
    import carb
    _log_warn = carb.log_warn
except ImportError:
    import logging
    _log_warn = logging.getLogger(__name__).warning

_FISHEYE_SCHEMA = "OmniLensDistortionOpenCvFisheyeAPI"


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
    return True


def _set_tick_rate(cam_prim, fps) -> None:
    if fps is not None:
        cam_prim.ApplyAPI("OmniSensorAPI")
        cam_prim.GetAttribute("omni:sensor:tickRate").Set(float(fps))


def _clear_lens_distortion(cam_prim) -> None:
    for schema in cam_prim.GetAppliedSchemas():
        if schema.startswith("OmniLensDistortion"):
            cam_prim.RemoveAppliedSchema(schema)
    if cam_prim.HasAttribute("omni:lensdistortion:model"):
        cam_prim.RemoveProperty("omni:lensdistortion:model")
    spec = cam_prim.GetStage().GetSessionLayer().GetPrimAtPath(cam_prim.GetPath())
    if spec is not None and "clippingRange" in spec.properties:
        spec.RemoveProperty(spec.properties["clippingRange"])


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

    The RTX renderer bends the image only while the OpenCV fisheye schema is on the prim, and a
    placed asset switching its lens variant re-uses the same prim - hence the clearing half.
    """
    distortion = get_distortion_coefficients(camera_model)
    if distortion is None:
        _clear_lens_distortion(cam_prim)
        return

    cx, cy = get_optical_center(camera_model, resolution)
    _clear_lens_distortion(cam_prim)
    _apply_lens_schema(cam_prim, _FISHEYE_SCHEMA,
                       _corner_cosine(resolution, focal_px, focal_px, cx, cy, is_fisheye=True))
    cam_prim.GetAttribute("omni:lensdistortion:model").Set("opencvFisheye")
    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:k1").Set(distortion[0])
    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:k2").Set(distortion[1])
    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:k3").Set(distortion[2])
    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:k4").Set(distortion[3])
    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:cx").Set(cx)
    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:cy").Set(cy)
    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:fx").Set(focal_px)
    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:fy").Set(focal_px)
    cam_prim.GetAttribute("omni:lensdistortion:opencvFisheye:imageSize").Set(
        Gf.Vec2i(resolution[0], resolution[1]))
