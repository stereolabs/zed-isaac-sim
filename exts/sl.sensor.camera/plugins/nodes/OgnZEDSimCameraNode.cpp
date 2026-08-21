
// Copyright (c) 2022, NVIDIA CORPORATION. All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdlib>
#include <condition_variable>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>

#include <OgnZEDSimCameraNodeDatabase.h>
#include <cuda/include/cuda_runtime_api.h>
#include "zed_interface_loader.hpp"
#include "types_c.h"
#include "sl_zed_sim2real_loader.hpp"

// Helpers to explicit shorten names you know you will use
using omni::graph::core::Type;
using omni::graph::core::BaseDataType;

namespace sl {
    namespace sensor{
        namespace camera {

            // ---------------------------------------------------------------
            // Shared state across all camera node instances.
            // OmniGraph evaluates nodes from a thread pool and a scene usually
            // contains several camera nodes, so every access below is guarded
            // by g_state_mutex.
            // ---------------------------------------------------------------
            static std::mutex g_state_mutex;

            // Depth streamed to the ZED SDK (ingestCustomDepth) is fixed at this
            // resolution; it must match the depth render product sized in annotators.py.
            static constexpr int kStreamDepthWidth = 896;
            static constexpr int kStreamDepthHeight = 512;

            // Monotonic id allocator with a free-list, so ids are unique while a
            // streamer is alive and get recycled on teardown (no collisions on
            // stop/restart, unlike a bare counter that was both ++'d and --'d).
            static int g_next_streamer_id = 0;
            static std::vector<int> g_free_streamer_ids = {};

            // List of available SN per camera model (populated from SDK at runtime)
            static std::map<std::string, std::vector<int>> available_zed_cameras = {};

            // List of currently available (not yet opened) serial numbers per model
            static std::map<std::string, std::vector<int>> remaining_serial_numbers = {};

            static int allocStreamerId()
            {
                std::lock_guard<std::mutex> lk(g_state_mutex);
                if (!g_free_streamer_ids.empty()) {
                    int id = g_free_streamer_ids.back();
                    g_free_streamer_ids.pop_back();
                    return id;
                }
                return g_next_streamer_id++;
            }

            static void freeStreamerId(int id)
            {
                std::lock_guard<std::mutex> lk(g_state_mutex);
                g_free_streamer_ids.push_back(id);
            }

            // One frame's image buffers + metadata, recycled by FramePipeline. Buffers are
            // pinned host memory (cudaMallocHost) by default, or CUDA device memory
            // (cudaMalloc) when the zero-copy GPU path is active (see on_device).
            struct FrameSlot {
                unsigned char* buf_left{ nullptr };
                unsigned char* buf_right{ nullptr };
                unsigned char* buf_depth{ nullptr };  // raw float depth bytes (Left+Depth mode)
                size_t cap_left{ 0 };                 // allocated capacity
                size_t cap_right{ 0 };
                size_t cap_depth{ 0 };
                size_t size_left{ 0 };                // valid bytes for this frame
                size_t size_right{ 0 };
                size_t size_depth{ 0 };
                bool has_right{ false };
                bool has_depth{ false };              // depth buffer valid (Left+Depth mode)
                bool on_device{ false }; // buffers are CUDA device memory (zero-copy path)
                unsigned long long ts_ns{ 0 }; // streamed timestamp (wall-clock anchored), in ns
                // IMU values already converted to the streamer convention.
                float qw{ 1.f }, qx{ 0.f }, qy{ 0.f }, qz{ 0.f };
                float ax{ 0.f }, ay{ 0.f }, az{ 0.f };
            };

            // Lock-step producer/consumer hand-off over a small pool of pinned
            // buffers. The producer (compute thread) copies pixels D2H into a
            // free slot and publishes it; the consumer (streaming thread) encodes
            // and sends it. With 3 slots and a serialized producer there is always
            // a free slot to fill (consumer holds <=1, ready holds <=1), so the
            // producer never blocks and never races. Under backpressure the newest
            // frame wins and the previously pending one is dropped.
            class FramePipeline {
            public:
                static constexpr int NUM_SLOTS = 3;

                FramePipeline() {
                    for (int i = 0; i < NUM_SLOTS; ++i) m_free.push_back(i);
                }
                ~FramePipeline() { release(); }

                FrameSlot* slots() { return m_slots; }

                // Producer: take an exclusive free slot to fill. Returns nullptr
                // when stopping or (defensively) if no slot is free.
                FrameSlot* acquire() {
                    std::lock_guard<std::mutex> lk(m_mutex);
                    if (m_stop || m_free.empty()) return nullptr;
                    int idx = m_free.back();
                    m_free.pop_back();
                    return &m_slots[idx];
                }

                // Producer: hand a filled slot to the consumer, dropping any
                // still-pending frame (newest wins).
                void publish(FrameSlot* slot) {
                    std::lock_guard<std::mutex> lk(m_mutex);
                    if (m_ready >= 0) m_free.push_back(m_ready);
                    m_ready = index(slot);
                    m_cv.notify_one();
                }

                // Producer: return an acquired-but-not-published slot (copy failed).
                void cancel(FrameSlot* slot) {
                    std::lock_guard<std::mutex> lk(m_mutex);
                    m_free.push_back(index(slot));
                }

                // Consumer: block until a frame is published. Returns nullptr when
                // stopping.
                FrameSlot* waitReady() {
                    std::unique_lock<std::mutex> lk(m_mutex);
                    m_cv.wait(lk, [this] { return m_ready >= 0 || m_stop; });
                    if (m_ready < 0) return nullptr;
                    m_consuming = m_ready;
                    m_ready = -1;
                    return &m_slots[m_consuming];
                }

                // Consumer: release the slot after streaming.
                void releaseConsumed() {
                    std::lock_guard<std::mutex> lk(m_mutex);
                    if (m_consuming >= 0) {
                        m_free.push_back(m_consuming);
                        m_consuming = -1;
                    }
                }

                void stop() {
                    std::lock_guard<std::mutex> lk(m_mutex);
                    m_stop = true;
                    m_cv.notify_all();
                }

                // Free slot memory. Only call after the consumer thread joined.
                void release() {
                    for (auto& s : m_slots) {
                        if (s.buf_left)  { if (s.on_device) cudaFree(s.buf_left);  else cudaFreeHost(s.buf_left); }
                        if (s.buf_right) { if (s.on_device) cudaFree(s.buf_right); else cudaFreeHost(s.buf_right); }
                        if (s.buf_depth) { if (s.on_device) cudaFree(s.buf_depth); else cudaFreeHost(s.buf_depth); }
                        s = FrameSlot{};
                    }
                }

            private:
                int index(FrameSlot* slot) const {
                    return static_cast<int>(slot - m_slots);
                }

                FrameSlot m_slots[NUM_SLOTS];
                std::vector<int> m_free;
                int m_ready{ -1 };
                int m_consuming{ -1 };
                bool m_stop{ false };
                std::mutex m_mutex;
                std::condition_variable m_cv;
            };

            // Grow a slot's buffers if the incoming frame is larger. device=true allocates CUDA
            // device memory (zero-copy GPU path); otherwise pinned host memory.
            static bool ensureSlotCapacity(FrameSlot& s, size_t need_left, size_t need_right, size_t need_depth,
                                           bool has_right, bool has_depth, bool device)
            {
                auto freeBuf = [](unsigned char* p, bool dev) { if (p) { if (dev) cudaFree(p); else cudaFreeHost(p); } };
                auto allocBuf = [](unsigned char** p, size_t n, bool dev) {
                    return dev ? cudaMalloc(reinterpret_cast<void**>(p), n)
                               : cudaMallocHost(reinterpret_cast<void**>(p), n);
                };
                if (need_left > s.cap_left) {
                    freeBuf(s.buf_left, s.on_device);
                    s.buf_left = nullptr;
                    s.cap_left = 0;
                    if (allocBuf(&s.buf_left, need_left, device) != cudaSuccess) { s.buf_left = nullptr; return false; }
                    s.cap_left = need_left;
                    s.on_device = device;
                }
                if (has_right && need_right > s.cap_right) {
                    freeBuf(s.buf_right, s.on_device);
                    s.buf_right = nullptr;
                    s.cap_right = 0;
                    if (allocBuf(&s.buf_right, need_right, device) != cudaSuccess) { s.buf_right = nullptr; return false; }
                    s.cap_right = need_right;
                    s.on_device = device;
                }
                // Depth follows the same device/host choice as the images (GPU path keeps it on device).
                if (has_depth && need_depth > s.cap_depth) {
                    freeBuf(s.buf_depth, s.on_device);
                    s.buf_depth = nullptr;
                    s.cap_depth = 0;
                    if (allocBuf(&s.buf_depth, need_depth, device) != cudaSuccess) { s.buf_depth = nullptr; return false; }
                    s.cap_depth = need_depth;
                    s.on_device = device;
                }
                return true;
            }


            // SDK MODEL codes. The real values come from the ZED SDK sl::MODEL enum;
            // the ones below mirror what the SDK reports in SimCameraInfo::model and
            // MUST stay in lock-step with utils._SDK_MODEL_ID on the Python side.
            static constexpr int MODEL_ID_VIRTUAL_ZED_X = -1;   // custom two-mono virtual stereo (not a real SDK model)

            // Composite serial-pool key for a camera, from its SDK MODEL code and lens.
            // Single source of truth for the key namespace: used both to build the pools
            // from SimCameraInfo (populateAvailableCameras) and to look one up from the
            // primitives the annotator sends (compute).
            static std::string simCameraModelKey(int model, int lens_type) {
                const bool narrow  = (lens_type == static_cast<int>(SIM_LENS_TYPE::NARROW));
                const bool fisheye = (lens_type == static_cast<int>(SIM_LENS_TYPE::FISHEYE));
                switch (model) {
                    case 1:  return "ZED_M";
                    case 4:  return narrow ? "ZED_X_4MM" : "ZED_X";
                    case 5:  return narrow ? "ZED_XM_4MM" : "ZED_XM";
                    case 9:  return "ZED_X_Nano";
                    // ZED X One S/GS/fisheye all share SDK model 30; the lens splits them.
                    // The fisheye key matches the serial-set key in populateAvailableCameras
                    // (fisheye is still identified by serial number, see below).
                    case 30: return fisheye ? "ZED_XONE_S_FISHEYE" : (narrow ? "ZED_XONE_GS_4MM" : "ZED_XONE_GS");
                    case 31: return "ZED_XONE_UHD";
                    case 3:        return narrow ? "ZED_2i_4MM" : "ZED_2i";
                    default: return "";
                }
            }

            // SNs reported as ZED_XONE_GS by the SDK but fitted with a fisheye lens
            static const std::set<int> fisheye_serial_numbers = { 303412363, 303835666, 306847047, 303198502 };

            // Caller must hold g_state_mutex.
            static void populateAvailableCameras(sl::ZedStreamer& streamer) {
                available_zed_cameras.clear();
                int count = 0;
                sl::SimCameraInfo* info = streamer.getVirtualCameraInfo(&count);
                if (!info || count == 0) return;
                for (int i = 0; i < count; i++) {
                    std::string key;
                    // Fisheye units are still identified by serial number: the SDK
                    // reports them as ZED_XONE_GS (model 30). Once the SDK reports
                    // LENS_FISHEYE via lens_type, this hard-coded set can be retired
                    // in favor of `info[i].lens_type == LENS_FISHEYE`.
                    if (fisheye_serial_numbers.count(info[i].serial_number))
                        key = "ZED_XONE_S_FISHEYE";
                    else
                        key = simCameraModelKey(info[i].model, static_cast<int>(info[i].lens_type));
                    if (!key.empty())
                        available_zed_cameras[key].push_back(info[i].serial_number);
                }
            }

            // Try to open a new streamer given a camera model. Check if a serial number is still available among the list.
            static int addStreamer(const std::string& camera_model)
            {
                std::lock_guard<std::mutex> lk(g_state_mutex);
                auto& pool = remaining_serial_numbers[camera_model];
                if (!pool.empty())
                {
                    int serial_number = pool.back();
                    pool.pop_back();
                    return serial_number;
                }

                CARB_LOG_FATAL("[ZED] Maximum number of %s camera reached!", camera_model.c_str());
                return -1;
            }

            static int removeStreamer(const std::string& camera_model, int serial_number)
            {
                std::lock_guard<std::mutex> lk(g_state_mutex);
                auto& pool = remaining_serial_numbers[camera_model];
                // If the serial number is already in the list, do not add it again
                if (std::find(pool.begin(), pool.end(), serial_number) != pool.end())
                {
                    CARB_LOG_ERROR("[ZED] Trying to remove invalid serial number %d for camera model %s",
                        serial_number, camera_model.c_str());
                    return -1;
                }
                pool.push_back(serial_number);
                return 0;
            }

            static int transportLayerModeToInt(const std::string& mode_str)
            {
                if (mode_str == "NETWORK")
                    return 0;
                else if (mode_str == "IPC")
                    return 1;
                else if (mode_str == "BOTH")
                    return 2;
                else
                {
                    CARB_LOG_WARN("[ZED] Invalid transport layer mode string %s, defaulting to NETWORK", mode_str.c_str());
                    return 0;
                }
            }

            class OgnZEDSimCameraNode
            {
                sl::StreamingParameters m_zedStreamerParams;
                sl::ZedStreamer m_zedStreamer;
                cudaStream_t m_cudaStream;
                bool m_cudaStreamNotCreated{ true };
                int m_zedStreamerInitStatus{ -1 };
                bool m_stereo_camera{ true };
                bool m_stream_depth{ false };
                bool m_valid{ false };
                bool m_loggedInvalid{ false };
                bool m_gpu_input{ false }; // zero-copy GPU input active (device pointers to encoder)
                double previous_timestamp{ 0.0 };

                // Streamed timestamps are anchored to real wall-clock time captured on the
                // first frame, then advanced by simulation time. This keeps the simulated
                // frame cadence while making the absolute timestamp the actual current time
                // (a real camera stamps frames with Unix time, not from 0).
                bool m_timestamp_base_set{ false };
                double m_sim_time_base{ 0.0 };
                unsigned long long m_epoch_base_ns{ 0 };

                // Streamer identity owned by this instance (for clean teardown)
                std::string m_camera_model;
                int m_serial_number{ -1 };
                bool m_owns_pool_serial{ false };

                // Threading members
                std::thread m_streamingThread;
                FramePipeline m_pipeline;
                int m_streamer_id{ 0 };

                // ZED Sim2Real camera model (Imatest-calibrated post, from the sl_zed_sim2real lib,
                // loaded at runtime). Runs on the compute (producer) thread. The engine owns the
                // GPU scratch; the state owns per-stream auto-exposure (both eyes share one state).
                sl::ZedSim2Real      m_sim2real;
                sl_zed_sim2real_engine* m_sim2realEngine{ nullptr };
                sl_zed_sim2real_state*  m_sim2realState{ nullptr };
                // Last AE-target pushed to the state (sentinel -2 = never pushed); the input is
                // forwarded only on change so the per-frame cost is one float compare.
                float m_sim2realAeTargetApplied{ -2.0f };
                // One-shot diagnostics for the sim2real path: log the effective config and any
                // silent no-op branch exactly once per stream, so a "sim2real does nothing"
                // report can be pinpointed from the Kit log without spamming per frame.
                // One-shot guards so the silent-failure warnings below never spam per frame.
                bool m_sim2real_guard_warned{ false };
                bool m_sim2real_gpu_null_warned{ false };

                // One-shot guard for the input-buffer-size mismatch below.
                bool m_size_warned{ false };

                // Set when streamer init fails, so the failure is reported once instead of every frame.
                bool m_streamerInitFailed{ false };

                // Fallback clock: some Isaac builds deliver simulationTime == 0 from the
                // SDG time nodes; without a monotonic time the warmup gate and the
                // frame-dedup logic would stall the streamer.
                std::chrono::steady_clock::time_point m_clock0;
                bool m_clock0_set{ false };

                static const pxr::GfMatrix4d rotation_matrix;
                static const pxr::GfMatrix4d inv_rotation_matrix;

                // Consumer thread: encode + send already-copied frames. This is the
                // expensive work (NVENC encode + network/IPC send) kept off the
                // OmniGraph compute (render) thread.
                static void streamingThreadFunc(OgnZEDSimCameraNode& state) {
                    while (true)
                    {
                        FrameSlot* slot = state.m_pipeline.waitReady();
                        if (!slot) break; // stopping

                        if (slot->has_depth)
                        {
                            state.m_zedStreamer.streamLeftAndDepth(state.m_streamer_id,
                                slot->buf_left,
                                reinterpret_cast<float*>(slot->buf_depth),
                                slot->ts_ns,
                                slot->qw, slot->qx, slot->qy, slot->qz,
                                slot->ax, slot->ay, slot->az);
                        }
                        else
                        {
                            state.m_zedStreamer.stream(state.m_zedStreamerParams.input_format, state.m_streamer_id,
                                slot->buf_left,
                                slot->has_right ? slot->buf_right : nullptr,
                                slot->ts_ns,
                                slot->qw, slot->qx, slot->qy, slot->qz,
                                slot->ax, slot->ay, slot->az);
                        }

                        state.m_pipeline.releaseConsumed();
                    }
                }

public:

                OgnZEDSimCameraNode()
                {
                    m_zedStreamerInitStatus = 0;
                    m_cudaStreamNotCreated = true;

                    // Load zed streamer lib and init the streamer
                    std::string prefix = "";
                    std::string suffix = "";
                    std::string sep = "/";
#ifndef _WIN32
                    prefix = "lib";
                    suffix = ".so";
#else
                    suffix = "64.dll";
                    sep = "\\";
#endif
                    std::string lib_name = prefix + "sl_zed" + suffix;

                    // Load by absolute path from this plugin's own directory (the extension's
                    // bin/ folder) so the bundled lib is used, never a ZED SDK system install.
                    std::string module_dir = sl::get_current_module_dir();
                    std::string lib_path = module_dir.empty() ? lib_name : module_dir + sep + lib_name;

                    if (m_zedStreamer.load_lib(lib_path) && m_zedStreamer.isZEDSDKCompatible())
                    {
                        m_valid = true;
                        CARB_LOG_INFO("[ZED] Successfully found and loaded ZED SDK");
                    }
                    else
                    {
                        CARB_LOG_ERROR("[ZED] Error while loading ZED SDK. Make sure a compatible version is installed");
                    }
                }

                ~OgnZEDSimCameraNode()
                {
                    stop();
                }

                void stop()
                {
                    // Stop and join the consumer thread before touching anything it
                    // uses (pinned buffers, streamer, cuda stream).
                    m_pipeline.stop();
                    if (m_streamingThread.joinable()) {
                        m_streamingThread.join();
                    }

                    // Free this instance's pinned buffers now the consumer is done.
                    m_pipeline.release();

                    // Free the sim2real engine/state. Only the compute (producer) thread touches
                    // them, and no more frames are computed once teardown begins. Non-null implies
                    // the library loaded, so the function pointers are valid.
                    if (m_sim2realState)  { m_sim2real.state_destroy(m_sim2realState);   m_sim2realState  = nullptr; }
                    if (m_sim2realEngine) { m_sim2real.engine_destroy(m_sim2realEngine); m_sim2realEngine = nullptr; }

                    // Return only our own serial / id to the shared pools.
                    if (m_owns_pool_serial && m_serial_number > 0) {
                        removeStreamer(m_camera_model, m_serial_number);
                        m_owns_pool_serial = false;
                    }

                    // Clean up ZED streamer.
                    if (m_zedStreamerInitStatus == 1) {
                        m_zedStreamer.closeStreamer(m_streamer_id);
                        freeStreamerId(m_streamer_id);
                        m_zedStreamerInitStatus = 0;
                    }

                    // Clean up CUDA stream if it was created
                    if (!m_cudaStreamNotCreated) {
                        cudaError_t err = cudaStreamDestroy(m_cudaStream);
                        if (err != cudaSuccess) {
                            CARB_LOG_ERROR("[ZED] Error destroying CUDA stream in destructor: %s", cudaGetErrorString(err));
                        }
                        m_cudaStreamNotCreated = true;
                    }

                    m_zedStreamer.unload();
                    m_valid = false;
                }


                // called every time a new frame is rendered
                static bool compute(OgnZEDSimCameraNodeDatabase& db)
                {
                    auto& state = db.perInstanceState<OgnZEDSimCameraNode>();
                    if (!state.m_valid) {
                        if (!state.m_loggedInvalid) {
                            CARB_LOG_WARN("[ZED] Node is in an invalid state, streaming is disabled");
                            state.m_loggedInvalid = true;
                        }
                        return false;
                    }
                    if (!db.inputs.stream()) {
                        // Streaming simply turned off - nothing to do this frame.
                        state.m_streamerInitFailed = false;
                        return false;
                    }
                    if (state.m_streamerInitFailed) return false;

                    // Robust frame time: prefer simulationTime, fall back to an internal
                    // steady clock when the upstream time nodes deliver 0 (Isaac build
                    // regression observed with Kit 110.1).
                    double frame_time = db.inputs.simulationTime();
                    if (frame_time <= 0.0) {
                        if (!state.m_clock0_set) {
                            state.m_clock0 = std::chrono::steady_clock::now();
                            state.m_clock0_set = true;
                        }
                        frame_time = std::chrono::duration<double>(
                            std::chrono::steady_clock::now() - state.m_clock0).count();
                    }

                    // Done once, init the streamer and start a stream
                    if (state.m_zedStreamerInitStatus != 1)
                    {
                        float warmup = 1.0f;
                        if (frame_time < warmup) return true;

                        state.m_zedStreamer.load_api();

                        {
                            std::lock_guard<std::mutex> lk(g_state_mutex);
                            if (available_zed_cameras.empty())
                            {
                                populateAvailableCameras(state.m_zedStreamer);
                                remaining_serial_numbers = available_zed_cameras;
                            }
                        }

                        state.m_stream_depth = db.inputs.streamDepth();

                        if (state.m_stream_depth)
                        {
                            state.m_stereo_camera = false;
                        }
                        else
                        {
                            state.m_stereo_camera = db.inputs.bufferSizeRight() > 0 && reinterpret_cast<void*>(db.inputs.dataPtrRight()) != nullptr;
                        }

                        // Derive the serial-pool key from the SDK MODEL code + lens the
                        // annotator sends. simCameraModelKey() owns the key namespace, so
                        // model 30 already collapses ZED X One S into the shared GS pool -
                        // no per-model remap needed here.
                        const int model_id = db.inputs.simCameraModel();
                        std::string camera_model = (model_id == MODEL_ID_VIRTUAL_ZED_X)
                            ? std::string("VIRTUAL_ZED_X")
                            : simCameraModelKey(model_id, db.inputs.simLensType());

                        unsigned short port = db.inputs.port();

                        int serial_number = -1;
                        bool owns_pool_serial = false;
                        if (camera_model == "VIRTUAL_ZED_X")
                        {
                            serial_number = std::stoi(db.inputs.serialNumber());
                        }
                        else
                        {
                            serial_number = addStreamer(camera_model);
                            owns_pool_serial = serial_number > 0;
                        }

                        if (serial_number <= 0) {
                            state.m_valid = false;
                            return false;
                        } else if (!state.m_zedStreamer.isSNValid(serial_number)) {
                            state.m_valid = false;

                            if (camera_model == "VIRTUAL_ZED_X")
                            {
                                CARB_LOG_FATAL("[ZED] Invalid streamer configuration %d ! Make sure the SN starts with 11XXXXXXX",
                                    serial_number);
                            }
                            else
                            {
                                CARB_LOG_FATAL("[ZED] Invalid streamer configuration %d !",
                                    serial_number);
                            }

                            if (owns_pool_serial)
                                removeStreamer(camera_model, serial_number);
                            return false;
                        }

                        if (state.m_stream_depth)
                        {
                            CARB_LOG_INFO("[ZED] Opening camera %s in Left+Depth mode", camera_model.c_str());
                        }
                        else if (!state.m_stereo_camera)
                        {
                            CARB_LOG_INFO("[ZED] Opening mono camera %s %d", camera_model.c_str(), serial_number);
                        }
                        else {
                            CARB_LOG_INFO("[ZED] Opening stereo camera %s %d", camera_model.c_str(), serial_number);
                        }

                        int transport_layer_mode = transportLayerModeToInt(db.tokenToString(db.inputs.transportLayerMode()));

                        // Use YUV format for IPC or mono cameras
                        bool use_yuv = transport_layer_mode > 0 || !state.m_stereo_camera;
                        state.m_zedStreamerParams.alpha_channel_included = true;
                        state.m_zedStreamerParams.codec_type = 1;
                        state.m_zedStreamerParams.fps = db.inputs.fps();
                        state.m_zedStreamerParams.image_height = db.inputs.height();
                        state.m_zedStreamerParams.image_width = db.inputs.width();
                        state.m_zedStreamerParams.bitrate = db.inputs.bitrate();
                        state.m_zedStreamerParams.chunk_size = db.inputs.chunkSize();
                        state.m_zedStreamerParams.mode = 1;
                        state.m_zedStreamerParams.transport_layer_mode = transport_layer_mode;
                        state.m_zedStreamerParams.input_format = use_yuv ? sl::INPUT_FORMAT::YUV : sl::INPUT_FORMAT::BGR;

                        // Zero-copy GPU input: hand the annotator's CUDA device pointers straight to
                        // the encoder (NVENC converts on-GPU), eliminating the GPU->CPU->GPU round
                        // trip. Valid only on the BGR network stereo path; mono/YUV/IPC keep the host
                        // path.
                        state.m_gpu_input = state.m_stereo_camera && !use_yuv;
                        state.m_zedStreamerParams.gpu_input = state.m_gpu_input;
                        state.m_zedStreamerParams.serial_number = serial_number;
                        state.m_zedStreamerParams.port = port;
                        state.m_zedStreamerParams.verbose = 0;
                        state.m_zedStreamerParams.stream_depth = state.m_stream_depth;
                        state.m_zedStreamerParams.depth_width = kStreamDepthWidth;
                        state.m_zedStreamerParams.depth_height = kStreamDepthHeight;
                        state.m_streamer_id = allocStreamerId();
                        state.m_zedStreamerInitStatus = state.m_zedStreamer.initStreamer(state.m_streamer_id, &state.m_zedStreamerParams);

                        if (state.m_zedStreamerInitStatus > 0)
                        {
                            CARB_LOG_INFO("[ZED] ZED Streamer initialized successfully with ID %d", state.m_streamer_id);

                            // Remember our identity so stop() returns only our own resources.
                            state.m_camera_model = camera_model;
                            state.m_serial_number = serial_number;
                            state.m_owns_pool_serial = owns_pool_serial;

                            // Create CUDA stream
                            cudaError_t cuerr = cudaStreamCreate(&state.m_cudaStream);
                            if (cuerr != cudaSuccess) {
                                CARB_LOG_ERROR("[ZED] Failed to create CUDA stream: %s", cudaGetErrorString(cuerr));
                                state.m_valid = false;
                                return false;
                            }
                            state.m_cudaStreamNotCreated = false;

                            // Start streaming (consumer) thread
                            state.m_streamingThread = std::thread(&OgnZEDSimCameraNode::streamingThreadFunc, std::ref(state));
                        }
                        else {
                            state.m_streamerInitFailed = true;
                            CARB_LOG_ERROR("[ZED] Streamer initialization failed. "
                                "Camera %s SN %d, port %d, %dx%d @ %d FPS.",
                                camera_model.c_str(), serial_number, static_cast<int>(port),
                                state.m_zedStreamerParams.image_width, state.m_zedStreamerParams.image_height,
                                state.m_zedStreamerParams.fps);
                            state.m_zedStreamer.closeStreamer(state.m_streamer_id);
                            freeStreamerId(state.m_streamer_id);
                            if (owns_pool_serial)
                                removeStreamer(camera_model, serial_number);
                            return false;
                        }
                    }
                    else
                    {
                        // Read the sim2real config from the graph inputs each frame.
                        const bool  sim2real_enable    = db.inputs.applyZedSim2Real();
                        const float zed_sim2real_scene_lux = db.inputs.zedSim2RealSceneLux();
                        const float zed_sim2real_ae_target = db.inputs.zedSim2RealAeTarget();
                        // Get frame data pointers and sizes
                        const size_t data_size_left{ db.inputs.bufferSizeLeft() };
                        const void* raw_ptr_left{ reinterpret_cast<void*>(db.inputs.dataPtrLeft()) };
                        const size_t data_size_right{ db.inputs.bufferSizeRight() };
                        const void* raw_ptr_right{ reinterpret_cast<void*>(db.inputs.dataPtrRight()) };
                        const size_t data_size_depth{ db.inputs.bufferSizeDepth() };
                        const void* raw_ptr_depth{ reinterpret_cast<void*>(db.inputs.dataPtrDepth()) };

                        if (!raw_ptr_left)
                        {
                            CARB_LOG_ERROR("[ZED] Left image is not valid");
                            return false;
                        }

                        if (state.m_stream_depth && !raw_ptr_depth)
                        {
                            CARB_LOG_ERROR("[ZED] Depth buffer is not valid");
                            return false;
                        }

                        if (!state.m_stream_depth && state.m_stereo_camera && data_size_left != data_size_right)
                        {
                            CARB_LOG_ERROR("[ZED] Left and Right images have different sizes");
                            return false;
                        }

                        const size_t expected_image_bytes =
                            static_cast<size_t>(state.m_zedStreamerParams.image_width) *
                            state.m_zedStreamerParams.image_height * 4;
                        if (data_size_left != expected_image_bytes ||
                            (state.m_stereo_camera && data_size_right != expected_image_bytes))
                        {
                            if (!state.m_size_warned) {
                                state.m_size_warned = true;
                                CARB_LOG_ERROR("[ZED] Image buffer size mismatch: left=%zu right=%zu "
                                               "expected=%zu (%dx%d RGBA8). Skipping frames until it "
                                               "matches - the render product resolution differs from "
                                               "the stream width/height.",
                                               data_size_left, data_size_right, expected_image_bytes,
                                               state.m_zedStreamerParams.image_width,
                                               state.m_zedStreamerParams.image_height);
                            }
                            return false;
                        }

                        if (state.m_stream_depth)
                        {
                            const size_t expected_depth_bytes =
                                static_cast<size_t>(kStreamDepthWidth) * kStreamDepthHeight * sizeof(float);
                            if (data_size_depth != expected_depth_bytes)
                            {
                                if (!state.m_size_warned) {
                                    state.m_size_warned = true;
                                    CARB_LOG_ERROR("[ZED] Depth buffer size mismatch: depth=%zu expected=%zu "
                                                   "(%dx%d float32). Skipping frames until it matches.",
                                                   data_size_depth, expected_depth_bytes,
                                                   kStreamDepthWidth, kStreamDepthHeight);
                                }
                                return false;
                            }
                        }

                        const double timestamp = frame_time;

                        // Avoid streaming the same frame twice (dedup on the producer side).
                        if (timestamp <= state.previous_timestamp)
                            return true;
                        state.previous_timestamp = timestamp;

                        // Grab a free slot to copy into (pinned host, or CUDA device on the
                        // zero-copy path).
                        FrameSlot* slot = state.m_pipeline.acquire();
                        if (!slot)
                            return true; // stopping, or transiently no free slot

                        if (!ensureSlotCapacity(*slot, data_size_left, data_size_right, data_size_depth,
                                                state.m_stereo_camera, state.m_stream_depth, state.m_gpu_input)) {
                            CARB_LOG_ERROR("[ZED] Failed to allocate frame buffer");
                            state.m_pipeline.cancel(slot);
                            return false;
                        }

                        // Capture the frame off the annotator's GPU buffer while it is still valid.
                        // GPU path: device-to-device into a CUDA slot (no PCIe transfer). Host path:
                        // device-to-host into a pinned slot. Either way only the copy runs on the
                        // compute thread; the encode/send is offloaded to the consumer.
                        cudaMemcpyKind copy_kind = state.m_gpu_input ? cudaMemcpyDeviceToDevice
                                                                     : cudaMemcpyDeviceToHost;

                        // ZED Sim2Real stage-2: process the annotator's DEVICE buffers with the CUDA
                        // sim2real, then copy the processed (device) output into the slot with copy_kind
                        // - device-to-device on the zero-copy path (frame never leaves the GPU),
                        // device-to-host otherwise. Falls back to a raw copy below on failure, and to
                        // the CPU sim2real only when the slot is host memory.
                        const int tw = static_cast<int>(state.m_zedStreamerParams.image_width);
                        const int th = static_cast<int>(state.m_zedStreamerParams.image_height);
                        const bool sim2real_enabled = sim2real_enable &&
                            static_cast<size_t>(tw) * th * 4 == data_size_left;

                        // Sim2Real requested but the buffer isn't the expected RGBA8 tw*th frame:
                        // the ISP is silently skipped. Warn once with the mismatch so it's visible.
                        if (sim2real_enable && !sim2real_enabled && !state.m_sim2real_guard_warned) {
                            state.m_sim2real_guard_warned = true;
                            CARB_LOG_WARN("[ZED] Sim2Real skipped: buffer size %zu != expected %zu (tw=%d th=%d, RGBA8); "
                                          "check the stream resolution vs the render product",
                                          data_size_left, static_cast<size_t>(tw) * th * 4, tw, th);
                        }

                        bool sim2real_gpu_done = false;
                        if (sim2real_enabled && state.m_sim2real.load()) {
                            if (!state.m_sim2realEngine) {
                                state.m_sim2realEngine = state.m_sim2real.engine_create();
                                state.m_sim2realState  = state.m_sim2real.state_create(/*seed=*/0);
                            }
                            // Forward the AE set-point override on change (covers the CPU
                            // fallback too - both paths share this state). Null on pre-v0.2.0
                            // libraries, where the input is silently ignored.
                            if (state.m_sim2real.state_set_ae_target && state.m_sim2realState &&
                                zed_sim2real_ae_target != state.m_sim2realAeTargetApplied) {
                                state.m_sim2real.state_set_ae_target(state.m_sim2realState,
                                                                     zed_sim2real_ae_target);
                                state.m_sim2realAeTargetApplied = zed_sim2real_ae_target;
                            }
                            // Left eye advances auto-exposure; the right eye reuses it.
                            const void* out_left = state.m_sim2real.process_device_out(
                                state.m_sim2realEngine, state.m_sim2realState, raw_ptr_left, tw, th,
                                state.m_cudaStream, /*enable=*/1, zed_sim2real_scene_lux, /*advance=*/1);
                            sim2real_gpu_done = (out_left != nullptr);
                            if (sim2real_gpu_done) {
                                cudaMemcpyAsync(slot->buf_left, out_left,
                                    data_size_left, copy_kind, state.m_cudaStream);
                                if (state.m_stereo_camera) {
                                    const void* out_right = state.m_sim2real.process_device_out(
                                        state.m_sim2realEngine, state.m_sim2realState, raw_ptr_right, tw, th,
                                        state.m_cudaStream, /*enable=*/1, zed_sim2real_scene_lux, /*advance=*/0);
                                    sim2real_gpu_done = (out_right != nullptr);
                                    if (sim2real_gpu_done)
                                        cudaMemcpyAsync(slot->buf_right, out_right,
                                            data_size_right, copy_kind, state.m_cudaStream);
                                }
                            }
                            // GPU sim2real returned null: the raw (un-degraded) frame is streamed
                            // instead, and on the zero-copy path the CPU fallback below is skipped.
                            // Warn once so this doesn't look like "sim2real does nothing".
                            if (!sim2real_gpu_done && !state.m_sim2real_gpu_null_warned) {
                                state.m_sim2real_gpu_null_warned = true;
                                CARB_LOG_WARN("[ZED] Sim2Real GPU path returned null; streaming raw frame"
                                              "%s", state.m_gpu_input ? " (CPU fallback unavailable on zero-copy path)" : "");
                            }
                        }

                        cudaError_t err_left = cudaSuccess;
                        cudaError_t err_right = cudaSuccess;
                        if (!sim2real_gpu_done) {
                            err_left = cudaMemcpyAsync(slot->buf_left, raw_ptr_left,
                                data_size_left, copy_kind, state.m_cudaStream);
                            if (state.m_stereo_camera)
                            {
                                err_right = cudaMemcpyAsync(slot->buf_right, raw_ptr_right,
                                    data_size_right, copy_kind, state.m_cudaStream);
                            }
                        }
                        cudaError_t err_depth = cudaSuccess;
                        if (state.m_stream_depth)
                        {
                            err_depth = cudaMemcpyAsync(slot->buf_depth, raw_ptr_depth,
                                data_size_depth, copy_kind, state.m_cudaStream);
                        }

                        if (err_left != cudaSuccess || err_right != cudaSuccess || err_depth != cudaSuccess) {
                            cudaError_t first_err = err_left != cudaSuccess ? err_left
                                                  : (err_right != cudaSuccess ? err_right : err_depth);
                            CARB_LOG_ERROR("[ZED] CUDA memcpy error: %s", cudaGetErrorString(first_err));
                            state.m_pipeline.cancel(slot);
                            return false;
                        }

                        cudaError_t sync_err = cudaStreamSynchronize(state.m_cudaStream);
                        if (sync_err != cudaSuccess) {
                            CARB_LOG_ERROR("[ZED] CUDA stream synchronization error: %s", cudaGetErrorString(sync_err));
                            state.m_pipeline.cancel(slot);
                            return false;
                        }

                        // ZED Sim2Real CPU fallback: only when the GPU path was unavailable, the library
                        // and per-stream state exist, AND the slot is host memory. On the zero-copy
                        // (gpu_input) path the slot is device memory, so process_host cannot touch it -
                        // a GPU failure there just streams the raw frame copied above.
                        if (sim2real_enabled && !sim2real_gpu_done && state.m_sim2realState && !state.m_gpu_input) {
                            state.m_sim2real.process_host(state.m_sim2realState, slot->buf_left, tw, th,
                                                         /*enable=*/1, zed_sim2real_scene_lux, /*advance=*/1);
                            if (state.m_stereo_camera)
                                state.m_sim2real.process_host(state.m_sim2realState, slot->buf_right, tw, th,
                                                             /*enable=*/1, zed_sim2real_scene_lux, /*advance=*/0);
                        }

                        // Convert IMU orientation / linear acceleration into the
                        // streamer's coordinate convention.
                        GfQuatd quat = db.inputs.orientation().GetNormalized();
                        pxr::GfMatrix4d orientation_mat;
                        orientation_mat.SetRotate(quat);
                        pxr::GfMatrix4d lin_acc_mat;
                        lin_acc_mat.SetTranslate(db.inputs.linearAcceleration());

                        GfQuatd converted_orientation = (rotation_matrix * orientation_mat * inv_rotation_matrix).GetOrthonormalized().ExtractRotationQuat();
                        GfVec3d converted_lin_acc = (rotation_matrix * lin_acc_mat * inv_rotation_matrix).GetOrthonormalized().ExtractTranslation();

                        // Anchor the stream to real wall-clock time on the first frame, then
                        // advance by simulation time so frame cadence is preserved while the
                        // absolute timestamp reflects the actual current time.
                        if (!state.m_timestamp_base_set) {
                            state.m_epoch_base_ns = static_cast<unsigned long long>(
                                std::chrono::duration_cast<std::chrono::nanoseconds>(
                                    std::chrono::system_clock::now().time_since_epoch()).count());
                            state.m_sim_time_base = timestamp;
                            state.m_timestamp_base_set = true;
                        }

                        slot->size_left = data_size_left;
                        slot->size_right = state.m_stereo_camera ? data_size_right : 0;
                        slot->has_right = state.m_stereo_camera;
                        slot->size_depth = state.m_stream_depth ? data_size_depth : 0;
                        slot->has_depth = state.m_stream_depth;
                        slot->ts_ns = state.m_epoch_base_ns +
                            static_cast<unsigned long long>((timestamp - state.m_sim_time_base) * 1e9);
                        slot->qw = static_cast<float>(converted_orientation.GetReal());
                        slot->qx = -static_cast<float>(converted_orientation.GetImaginary()[0]);
                        slot->qy = -static_cast<float>(converted_orientation.GetImaginary()[1]);
                        slot->qz = static_cast<float>(converted_orientation.GetImaginary()[2]);
                        slot->ax = static_cast<float>(converted_lin_acc[0]);
                        slot->ay = static_cast<float>(converted_lin_acc[1]);
                        slot->az = static_cast<float>(converted_lin_acc[2]);

                        // Hand off to the consumer thread for encode + send.
                        state.m_pipeline.publish(slot);
                    }
                    return true;
                }
            };

            const pxr::GfMatrix4d OgnZEDSimCameraNode::rotation_matrix{
                0, -1, 0, 0,
                0, 0, -1, 0,
                1, 0, 0, 0,
                0, 0, 0, 1
                        };

            const pxr::GfMatrix4d OgnZEDSimCameraNode::inv_rotation_matrix = rotation_matrix.GetInverse();

            // This macro provides the information necessary to OmniGraph that lets it automatically register and deregister
            // your node type definition.
            REGISTER_OGN_NODE()

        } // camera
    } // sensor
} // sl
