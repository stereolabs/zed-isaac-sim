// Copyright (c) 2022, NVIDIA CORPORATION. All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//

#include <chrono>
#include <algorithm>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <memory>

#include <OgnZEDSimCameraNodeDatabase.h>
#include <cuda/include/cuda_runtime_api.h>
#include "zed_interface_loader.hpp"
#include "types_c.h"

// Helpers to explicit shorten names you know you will use
using omni::graph::core::Type;
using omni::graph::core::BaseDataType;

#define CUDA_CHECK(call)                                                   \
do {                                                                       \
    cudaError_t err = call;                                                \
    if (err != cudaSuccess) {                                              \
        fprintf(stderr, "CUDA error at %s %d: %s\n", __FILE__, __LINE__,   \
                cudaGetErrorString(err));                                  \
        /* Instead of exiting, log the error and continue */               \
        return true;                                                       \
    }                                                                      \
} while (0)

namespace sl {
    namespace sensor{
        namespace camera {
            namespace bridge{
                static int streamer_id = -1;

                static std::map<std::string, std::vector<int>> available_zed_cameras = {
                    {"ZED_X",   { 40976320, 41116066, 49123828, 45626933 }},
                    {"ZED_X_Mini",   { 57890353,55263213,57800035,57706147 }}
                };

                static std::map<std::string, std::vector<int>> remaining_serial_numbers = {};

                static int addStreamer(std::string camera_model)
                {       
                    if (remaining_serial_numbers[camera_model].size() > 0)
                    {
                        streamer_id += 1;
                        int serial_number = remaining_serial_numbers[camera_model][remaining_serial_numbers[camera_model].size() - 1];
                        remaining_serial_numbers[camera_model].pop_back();
                        return serial_number;
                    }

                    CARB_LOG_FATAL("[ZED] Maximum number of camera reached! %d", streamer_id);
                    return -1;
                }

                struct FrameData {
                    void* raw_ptr_left;
                    void* raw_ptr_right;
                    size_t data_size_left;
                    size_t data_size_right;
                    float4 quaternion;
                    float3 linear_acceleration;
                    double timestamp;
                    bool valid = false;
                };

                class OgnZEDSimCameraNode
                {
                    bool m_zed_sdk_compatible{ false };
                    sl::StreamingParameters m_zedStreamerParams;
                    sl::ZedStreamer m_zedStreamer;
                    cudaStream_t m_cudaStream;
                    bool m_cudaStreamNotCreated{ true };
                    bool m_zedStreamerInitStatus{ false };

                    // Threading members
                    std::thread m_streamingThread;
                    std::atomic<bool> m_shouldStop{ false };
                    std::mutex m_frameMutex;
                    std::condition_variable m_frameCondition;
                    FrameData m_currentFrame;
                    FrameData m_pendingFrame;
                    bool m_newFrameAvailable = false;
                    int m_streamer_id = 0;

                    static void streamingThreadFunc(OgnZEDSimCameraNode& state) {
                        //CARB_LOG_WARN("Starting streaming thread - will stream on new data arrival");

                        while (!state.m_shouldStop.load()) {
                            // Wait for new frame data
                            std::unique_lock<std::mutex> lock(state.m_frameMutex);
                            state.m_frameCondition.wait(lock, [&state] { return state.m_newFrameAvailable || state.m_shouldStop.load(); });

                            if (state.m_shouldStop.load()) break;

                            if (state.m_newFrameAvailable && state.m_pendingFrame.valid) {
                                // Swap current and pending frames
                                std::swap(state.m_currentFrame, state.m_pendingFrame);
                                state.m_newFrameAvailable = false;
                                state.m_pendingFrame.valid = false;
                                lock.unlock(); // Unlock early to minimize lock time

                                // Process and stream the frame immediately
                                auto data_ptr_left = std::make_unique<unsigned char[]>(state.m_currentFrame.data_size_left);
                                auto data_ptr_right = std::make_unique<unsigned char[]>(state.m_currentFrame.data_size_right);

                                // Copy data from GPU to CPU
                                cudaError_t err_left = cudaMemcpyAsync(data_ptr_left.get(),
                                    state.m_currentFrame.raw_ptr_left,
                                    state.m_currentFrame.data_size_left, cudaMemcpyDeviceToHost, state.m_cudaStream);

                                cudaError_t err_right = cudaMemcpyAsync(data_ptr_right.get(),
                                    state.m_currentFrame.raw_ptr_right,
                                    state.m_currentFrame.data_size_right, cudaMemcpyDeviceToHost, state.m_cudaStream);

                                if (err_left != cudaSuccess || err_right != cudaSuccess) {
                                    //CARB_LOG_ERROR("CUDA memcpy error in streaming thread: %s",
                                    //    cudaGetErrorString(err_left != cudaSuccess ? err_left : err_right));
                                    continue;
                                }

                                // Wait for GPU operations to complete
                                cudaError_t sync_err = cudaStreamSynchronize(state.m_cudaStream);
                                if (sync_err != cudaSuccess) {
                                    CARB_LOG_ERROR("[ZED] CUDA stream synchronization error: %s", cudaGetErrorString(sync_err));
                                    continue;
                                }

                                // Stream the data immediately
                                auto ts_ns = static_cast<long long>(state.m_currentFrame.timestamp * 1000000000);


                                int stream_err = state.m_zedStreamer.stream(state.m_zedStreamerParams.input_format, state.m_streamer_id,
                                    data_ptr_left.get(),
                                    data_ptr_right.get(),
                                    ts_ns,
                                    state.m_currentFrame.quaternion.x,
                                    state.m_currentFrame.quaternion.y,
                                    state.m_currentFrame.quaternion.z,
                                    state.m_currentFrame.quaternion.w,
                                    state.m_currentFrame.linear_acceleration.x,
                                    state.m_currentFrame.linear_acceleration.y,
                                    state.m_currentFrame.linear_acceleration.z);

                                //if (stream_err != 0) {
                                //    CARB_LOG_WARN("Stream error: %d", stream_err);
                                //}
                            }
                        }

                        CARB_LOG_INFO("[ZED] Streaming thread stopped");
                    }

                public:

                    OgnZEDSimCameraNode()
                    {
                        //CARB_LOG_WARN("Create node");
                        m_zedStreamerInitStatus = false;
                        m_newFrameAvailable = false;
                        m_cudaStreamNotCreated = true;
                        m_shouldStop = false;

                        remaining_serial_numbers = available_zed_cameras;

                        // Load zed streamer lib and init the streamer
                        std::string prefix = "";
                        std::string suffix = "";
#ifndef _WIN32
                        prefix = "lib";
                        suffix = ".so";
#else
                        suffix = "64.dll";
#endif
                        std::string lib_name = prefix + "sl_zed" + suffix;

                        if (m_zedStreamer.load_lib(lib_name) && m_zedStreamer.isZEDSDKCompatible())
                        {
                            m_zed_sdk_compatible = true;
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
                        remaining_serial_numbers = available_zed_cameras;
                        streamer_id -= 1;
                        // Stop the streaming thread
                        m_shouldStop.store(true);
                        m_frameCondition.notify_all();

                        if (m_streamingThread.joinable()) {
                            m_streamingThread.join();
                        }

                        // Clean up ZED streamer
                        if (m_zedStreamerInitStatus) {
                            m_zedStreamer.closeStreamer(0);
                            m_zedStreamer.destroyInstance();

                            m_zedStreamerInitStatus = false;
                        }

                        // Clean up CUDA stream if it was created
                        if (!m_cudaStreamNotCreated) {
                            cudaError_t err = cudaStreamDestroy(m_cudaStream);
                            if (err != cudaSuccess) {
                                CARB_LOG_ERROR("[ZED] Error destroying CUDA stream in destructor: %s", cudaGetErrorString(err));
                            }
                        }
                        m_zedStreamer.unload();
                        m_zed_sdk_compatible = false;
                    }

                    // called every time a new frame is rendered
                    static bool compute(OgnZEDSimCameraNodeDatabase& db)
                    {
                        auto& state = db.perInstanceState<OgnZEDSimCameraNode>();

                        if (!db.inputs.stream() || !state.m_zed_sdk_compatible) return true;

                        if (!state.m_zedStreamerInitStatus)
                        {
                            float warmup = 1.0f;
                            if (db.inputs.simulationTime() < warmup) return true;

                            unsigned short port = db.inputs.port();
                            int serial_number = addStreamer(db.inputs.cameraModel());

                            if (serial_number <= 0)
                            {
                                CARB_LOG_FATAL("[ZED] Invalid streamer configuration !");
                            }

                            CARB_LOG_INFO("[ZED] Opening camera %d : %d", serial_number, port);

                            bool use_ipc = db.inputs.ipc();

#ifdef _WIN32
                            use_ipc = false;

                            CARB_LOG_WARN("[ZED] IPC mode is not available on Windows. Switching back to RTSP...");
#endif

                            state.m_zedStreamer.load_api();
                            state.m_zedStreamerParams.alpha_channel_included = true;
                            state.m_zedStreamerParams.codec_type = 1;
                            state.m_zedStreamerParams.fps = db.inputs.fps();
                            state.m_zedStreamerParams.image_height = db.inputs.height();
                            state.m_zedStreamerParams.image_width = db.inputs.width();
                            state.m_zedStreamerParams.mode = 1;
                            state.m_zedStreamerParams.transport_layer_mode = use_ipc;
                            state.m_zedStreamerParams.input_format = use_ipc == 1 ? sl::INPUT_FORMAT::YUV : sl::INPUT_FORMAT::BGR;
                            state.m_zedStreamerParams.serial_number = serial_number;
                            state.m_zedStreamerParams.port = port;
                            state.m_zedStreamerParams.verbose = 0;

                            state.m_streamer_id = streamer_id;
                            state.m_zedStreamerInitStatus = state.m_zedStreamer.initStreamer(state.m_streamer_id, &state.m_zedStreamerParams);

                            if (state.m_zedStreamerInitStatus)
                            {
                                CARB_LOG_INFO("[ZED] Start Streaming at port %d", state.m_zedStreamerParams.port);

                                // Create CUDA stream
                                CUDA_CHECK(cudaStreamCreate(&state.m_cudaStream));
                                state.m_cudaStreamNotCreated = false;

                                // Start streaming thread
                                state.m_streamingThread = std::thread(&OgnZEDSimCameraNode::streamingThreadFunc, std::ref(state));
                            }
                            else {
                                CARB_LOG_ERROR("Error during zed streamer initialization %d", state.m_zedStreamerInitStatus);
                            }
                        }
                        else
                        {
                            // Get frame data pointers and sizes
                            size_t data_size_left = db.inputs.bufferSizeLeft();
                            void* raw_ptr_left = reinterpret_cast<void*>(db.inputs.dataPtrLeft());

                            size_t data_size_right = db.inputs.bufferSizeRight();
                            void* raw_ptr_right = reinterpret_cast<void*>(db.inputs.dataPtrRight());

                            if (!raw_ptr_left || !raw_ptr_right)
                            {
                                //CARB_LOG_ERROR("Left and Right images are not valid");
                                return false;
                            }

                            if (data_size_left != data_size_right || data_size_left == 0)
                            {
                                CARB_LOG_ERROR("[ZED] Left and Right images have different sizes");
                                return false;
                            }

                            // Prepare new frame data (just pointers and metadata)
                            FrameData new_frame;
                            new_frame.raw_ptr_left = raw_ptr_left;
                            new_frame.raw_ptr_right = raw_ptr_right;
                            new_frame.data_size_left = data_size_left;
                            new_frame.data_size_right = data_size_right;
                            new_frame.timestamp = db.inputs.simulationTime();
                            new_frame.valid = true;
                            auto quat = db.inputs.orientation();
                            auto lin_acc = db.inputs.linearAcceleration();

                            new_frame.quaternion.x = quat[0];
                            new_frame.quaternion.y = -quat[1];
                            new_frame.quaternion.z = -quat[3];
                            new_frame.quaternion.w = -quat[2];

                            new_frame.linear_acceleration.x = lin_acc[0];
                            new_frame.linear_acceleration.y = lin_acc[1];
                            new_frame.linear_acceleration.z = lin_acc[2];

                            // Pass frame info to streaming thread
                            {
                                std::lock_guard<std::mutex> lock(state.m_frameMutex);
                                state.m_pendingFrame = std::move(new_frame);
                                state.m_newFrameAvailable = true;
                            }
                            state.m_frameCondition.notify_one();
                        }
                        return true;
                    }
                };

                // This macro provides the information necessary to OmniGraph that lets it automatically register and deregister
                // your node type definition.
                REGISTER_OGN_NODE()

            } // bridge
        } // camera
    } // sensor
} // sl