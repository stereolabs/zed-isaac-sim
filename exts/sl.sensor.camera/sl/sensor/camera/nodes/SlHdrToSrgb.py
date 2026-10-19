"""
This is the implementation of the OGN node defined in SlHdrToSrgb.ogn
"""
import carb
import omni.graph.core as og
import warp as wp

from ..stream_encoding import LIGHT_FLICKER_HZ_SETTING, LIGHT_FLICKER_SETTING, StreamEncoder, light_flicker_gain


def _light_gain() -> float:
    """This frame's light flicker, from the settings and the simulation time (the same for both eyes)."""
    settings = carb.settings.get_settings()
    std = settings.get(LIGHT_FLICKER_SETTING)
    if not std:
        return 1.0
    import omni.timeline

    t = omni.timeline.get_timeline_interface().get_current_time()
    return light_flicker_gain(t, float(std), float(settings.get(LIGHT_FLICKER_HZ_SETTING) or 0.0))


class SlHdrToSrgb:
    """Encodes the render product's linear HdrColor into the sRGB RGBA8 image the ZED node streams,
    as a real ZED X would output it (the ZED X camera model, see stream_encoding): its sharpness
    (inputs:cameraMtf), lens vignetting (inputs:vignetteInvFocal), motion blur over the exposure time
    (inputs:blurScale), white balance (inputs:whiteBalance) and sensor noise at its gain
    (inputs:noiseGain); plus the scene lights' flicker when the lightFlickerStd setting is set."""

    class State:
        def __init__(self):
            self.output = None  # persistent RGBA8 device buffer, reused every frame
            self.encoder = None  # the camera model's per-eye scratch
            self.warned = False
            self.frame = 0  # advances the noise every frame

    @staticmethod
    def internal_state():
        return SlHdrToSrgb.State()

    @staticmethod
    def compute(db) -> bool:
        state = db.per_instance_state
        ptr, size = db.inputs.dataPtr, db.inputs.bufferSize
        width, height, device_index = db.inputs.width, db.inputs.height, db.inputs.cudaDeviceIndex
        if not ptr or not width or not height:
            return False  # annotator not delivering yet
        if device_index < 0 or size != width * height * 8:
            if not state.warned:
                state.warned = True
                carb.log_error(f"[ZED] sRGB encode expects a float16 RGBA device buffer ({width}x{height}x8 bytes "
                               f"on CUDA), got {size} bytes on device {device_index}")
            return False
        device = f"cuda:{device_index}"
        pixel_stride, row_stride = db.inputs.strides
        src = wp.array(ptr=ptr, dtype=wp.float16, shape=(height, width, 4),
                       strides=(row_stride or width * 8, pixel_stride or 8, 2), device=device)
        if state.output is None or state.output.shape != (height, width, 4) or str(state.output.device) != device:
            state.output = wp.empty((height, width, 4), dtype=wp.uint8, device=device)
        if state.encoder is None:
            state.encoder = StreamEncoder()
        state.frame += 1
        motion, blur_scale = None, 0.0
        if db.inputs.blurScale > 0 and db.inputs.motionPtr and db.inputs.motionSize == width * height * 16:
            motion = wp.array(ptr=db.inputs.motionPtr, dtype=wp.float32, shape=(height, width, 4), device=device)
            blur_scale = db.inputs.blurScale
        wb = db.inputs.whiteBalance
        wb = tuple(float(v) for v in wb) if wb is not None and len(wb) == 3 else None
        if not state.encoder.encode(src, state.output, seed=state.frame * 7919 + db.inputs.noiseSeed * 104729,
                                    gain=db.inputs.noiseGain, motion=motion, blur_scale=blur_scale,
                                    vignette_inv_f=db.inputs.vignetteInvFocal, sharpness=db.inputs.cameraMtf,
                                    light_gain=_light_gain(), wb=wb, eye=db.inputs.eye):
            if not state.warned:
                state.warned = True
                carb.log_error("[ZED] sRGB encode failed on the GPU")
            return False
        # The ZED node copies this buffer on its own CUDA stream, which is not ordered after Warp's
        # stream (both are blocking streams), so finish the encode before handing the pointer on.
        wp.synchronize_stream(wp.get_stream(device))
        db.outputs.dataPtr = state.output.ptr
        db.outputs.bufferSize = width * height * 4
        db.outputs.width = width
        db.outputs.height = height
        db.outputs.cudaDeviceIndex = device_index
        db.outputs.exec = og.ExecutionAttributeState.ENABLED
        return True
