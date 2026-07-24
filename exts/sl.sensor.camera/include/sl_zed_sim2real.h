// sl_zed_sim2real — public C ABI for the ZED Sim2Real camera model.
//
// The calibrated "ZED X look" ISP (sRGB decode -> MTF blur -> vignette/shading ->
// temporal AE -> bloom -> AWB -> CCM -> tone LUT -> sensor noise -> edge-preserving NR -> residue speckle -> asymmetric USM) applied to
// RGBA8 frames. This C ABI is the stable, ctypes-friendly surface used by the Python
// binding (Isaac Lab tensors, dataset capture). The C++ streaming plugin uses the
// richer C++ API in zed_sim2real_gpu.h / zed_sim2real.h directly.
//
// Threading / state model:
//   * An "engine" owns the GPU scratch buffers and is sized to one frame; share ONE
//     engine across many streams/envs (the scratch is reused, not duplicated).
//   * A "state" holds per-stream temporal tracking (auto-exposure). Use one state per
//     independent camera / RL env so their exposures evolve independently.
#pragma once
#include "sl_zed_sim2real_export.h"

// Bump on any breaking change to this C ABI. Consumers can compare this compile-time value
// against the runtime sl_zed_sim2real_abi_version() to detect a stale/ mismatched library.
#define SL_ZED_SIM2REAL_ABI_VERSION 1

#ifdef __cplusplus
extern "C" {
#endif

typedef struct sl_zed_sim2real_engine sl_zed_sim2real_engine;
typedef struct sl_zed_sim2real_state  sl_zed_sim2real_state;

// Returns the ABI version the loaded library was built with (SL_ZED_SIM2REAL_ABI_VERSION).
SL_ZED_SIM2REAL_API int sl_zed_sim2real_abi_version(void);

// GPU scratch owner (one frame's worth of buffers), sized to one resolution. Share across
// streams/envs, but use one engine per producer thread (not internally synchronized).
SL_ZED_SIM2REAL_API sl_zed_sim2real_engine* sl_zed_sim2real_engine_create(void);
SL_ZED_SIM2REAL_API void                sl_zed_sim2real_engine_destroy(sl_zed_sim2real_engine*);

// Per-stream state: auto-exposure + white-balance tracking, and a noise seed. Create one per
// independent camera / env. `seed` decorrelates this stream's sensor noise from others (e.g.
// pass the env index); pass 0 if you don't care.
SL_ZED_SIM2REAL_API sl_zed_sim2real_state*  sl_zed_sim2real_state_create(unsigned int seed);
SL_ZED_SIM2REAL_API void                sl_zed_sim2real_state_destroy(sl_zed_sim2real_state*);

// Override the AE set-point (median display luma, 0..1) for this stream — e.g. to match
// a real capture whose metering differs from the calibrated default. <=0 restores the default.
SL_ZED_SIM2REAL_API void sl_zed_sim2real_state_set_ae_target(sl_zed_sim2real_state*, float target01);

// Override the noise block for this stream: base multiplier on the sensor-noise tables,
// NR-residue speckle probability and amplitude (counts). <=0 on any value restores its
// calibrated default.
SL_ZED_SIM2REAL_API void sl_zed_sim2real_state_set_noise(sl_zed_sim2real_state*,
    float noise_gain, float salt_p, float salt_amp);

// Process one RGBA8 GPU frame; the result stays in an internal engine buffer and is
// NOT copied back. Use this when the caller copies the result elsewhere itself (e.g.
// the streaming plugin copying into its own frame slot).
//   rgba_dev : CUDA device pointer to the w*h*4 input (read, not written).
//   stream   : CUDA stream (cudaStream_t as void*); NULL = default stream.
//   advance_temporal: 1 updates auto-exposure from this frame; 0 reuses the last gain
//              (e.g. the right eye of a stereo pair reusing the left eye's AE).
// Returns a device pointer to the processed w*h*4 RGBA8 (valid until the next call on
// this engine), or NULL on no-op (enable==0) / GPU failure.
SL_ZED_SIM2REAL_API const void* sl_zed_sim2real_process_device_out(
    sl_zed_sim2real_engine* engine, sl_zed_sim2real_state* state,
    const void* rgba_dev, int w, int h, void* stream,
    int enable, float scene_lux, int advance_temporal);

// Process one RGBA8 GPU frame IN PLACE (rgba_dev overwritten with the result). Thin
// wrapper over sl_zed_sim2real_process_device_out + a device-to-device copy back. Intended
// for the tensor path (e.g. a torch tensor's data_ptr()).
// Returns 1 on success, 0 on GPU failure (frame left unchanged; caller may log once).
SL_ZED_SIM2REAL_API int sl_zed_sim2real_process_device(
    sl_zed_sim2real_engine* engine, sl_zed_sim2real_state* state,
    void* rgba_dev, int w, int h, void* stream,
    int enable, float scene_lux, int advance_temporal);

// Same as sl_zed_sim2real_process_device_out, plus an optional depth map (float meters,
// w*h, device pointer) enabling the near-field defocus stage (thin-lens CoC, fixed-focus
// optics). depth_dev == NULL behaves exactly like the depth-less variant.
SL_ZED_SIM2REAL_API const void* sl_zed_sim2real_process_device_depth_out(
    sl_zed_sim2real_engine* engine, sl_zed_sim2real_state* state,
    const void* rgba_dev, const void* depth_dev, int w, int h, void* stream,
    int enable, float scene_lux, int advance_temporal);

// In-place variant of sl_zed_sim2real_process_device_depth_out.
SL_ZED_SIM2REAL_API int sl_zed_sim2real_process_device_depth(
    sl_zed_sim2real_engine* engine, sl_zed_sim2real_state* state,
    void* rgba_dev, const void* depth_dev, int w, int h, void* stream,
    int enable, float scene_lux, int advance_temporal);

// Process N contiguous RGBA8 GPU frames (e.g. a batched (N,H,W,4) torch tensor), each
// with its own state, IN PLACE. states[i] must be non-NULL for i in [0,count).
//   base_dev    : device pointer to frame 0.
//   frame_stride: byte stride between consecutive frames (0 => w*h*4, i.e. tightly
//                 packed). Loops sl_zed_sim2real_process_device internally; the engine's
//                 scratch is reused so GPU memory stays at one frame regardless of N.
// Returns the number of frames processed successfully.
SL_ZED_SIM2REAL_API int sl_zed_sim2real_process_device_batch(
    sl_zed_sim2real_engine* engine, sl_zed_sim2real_state** states, int count,
    void* base_dev, int w, int h, long long frame_stride, void* stream,
    int enable, float scene_lux, int advance_temporal);

// Process one RGBA8 frame that lives on the HOST (numpy), IN PLACE. CPU path; no GPU
// required (engine not needed). Returns 1 (no-op when enable==0). scene_lux/advance as
// above.
SL_ZED_SIM2REAL_API int sl_zed_sim2real_process_host(
    sl_zed_sim2real_state* state, unsigned char* rgba, int w, int h,
    int enable, float scene_lux, int advance_temporal);

#ifdef __cplusplus
} // extern "C"
#endif
