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

                static int streamer_id = 0;

                // Data struct shared to the streaming thread
                struct FrameData {
                    const void* raw_ptr_left{ nullptr };
                    const void* raw_ptr_right{ nullptr };
                    const size_t data_size_left{ 0 };
                    const size_t data_size_right{ 0 };
                    GfQuatd quaternion;
                    GfVec3d linear_acceleration;
                    double timestamp;
                    bool valid = false;

					FrameData() = default;

                    FrameData(const void* left_ptr, size_t left_size,
                        const void* right_ptr = nullptr, size_t right_size = 0)
                        : raw_ptr_left(left_ptr)
                        , raw_ptr_right(right_ptr)
                        , data_size_left(left_size)
                        , data_size_right(right_size)
                    {
                    }
                };

                // List of available SN per camera model
                static std::map<std::string, std::vector<int>> available_zed_cameras = {
                    {"ZED_X",   { 40976320, 41116066, 49123828, 45626933 }},
                    {"ZED_X_4MM", { 47890353,45263213,47800035,47706147 }},
                    {"ZED_XM",   { 57890353,55263213,57800035,57706147 }},                  
                    {"ZED_XM_4MM",   { 50179396,52835616,59695059,55043860 }},
                    {"ZED_XONE_UHD",   { 305221009, 305952675, 307526942, 307184845 }},
                    {"ZED_XONE_GS",   { 313021359, 318822533, 319625509, 318353328 }},
                    {"ZED_XONE_GS_4MM",   {300605725, 302696256, 302485375, 307845777 }}
                };

                // List of currently opened cameras
                static std::map<std::string, std::vector<int>> remaining_serial_numbers = {};

                // Try to open a new streamer given a camera model. Check if a serial number is still available among the list.
                static int addStreamer(std::string camera_model)
                {
                    if (remaining_serial_numbers[camera_model].size() > 0)
                    {
                        int serial_number = remaining_serial_numbers[camera_model][remaining_serial_numbers[camera_model].size() - 1];
                        remaining_serial_numbers[camera_model].pop_back();
                        return serial_number;
                    }

                    CARB_LOG_FATAL("[ZED] Maximum number of %s camera reached!", camera_model.c_str());
                    return -1;
                }

                class OgnZEDSimCameraNode
                {
                    sl::StreamingParameters m_zedStreamerParams;
                    sl::ZedStreamer m_zedStreamer;
                    cudaStream_t m_cudaStream;
                    bool m_cudaStreamNotCreated{ true };
                    int m_zedStreamerInitStatus{ -1 };
					bool m_stereo_camera{ true };
                    bool m_valid{ false };
                    // Threading members
                    std::thread m_streamingThread;
                    std::atomic<bool> m_shouldStop{ false };
                    sl::DoubleBuffer<FrameData> m_frameBuffer;
					unsigned int m_streamer_id{ 0 };

                    static const pxr::GfMatrix4d rotation_matrix;

                    static const pxr::GfMatrix4d inv_rotation_matrix;

                    static void streamingThreadFunc(OgnZEDSimCameraNode& state) {
                        //CARB_LOG_WARN("Starting streaming thread - will stream on new data arrival");

                        std::unique_ptr<unsigned char[]> data_ptr_left;
                        std::unique_ptr<unsigned char[]> data_ptr_right;
                        size_t allocated_size_left = 0;
                        size_t allocated_size_right = 0;

                        FrameData current_frame;

                        int frame_index = -1;

                        while (!state.m_shouldStop.load())
                        {
                            auto current_frame = state.m_frameBuffer.wait_and_read(state.m_shouldStop, frame_index);
                            if (!current_frame || !current_frame->valid)
                            {
                                continue;
                            }

                            const size_t data_size_left{ current_frame->data_size_left };
                            const void* raw_ptr_left{ current_frame->raw_ptr_left };
                            const void* raw_ptr_right{ current_frame->raw_ptr_right };
                            const size_t data_size_right{ current_frame->data_size_right };

                            const double timestamp = current_frame->timestamp;
                            const auto quaternion = current_frame->quaternion;
                            const auto linear_acceleration = current_frame->linear_acceleration;
                            const auto cudaStream = state.m_cudaStream;

                            GfQuatd quat = quaternion.GetNormalized();

                            pxr::GfMatrix4d orientation_mat;
                            orientation_mat.SetRotate(quat);

                            pxr::GfMatrix4d lin_acc_mat;
                            lin_acc_mat.SetTranslate(linear_acceleration);

                            GfQuatd converted_orientation = (rotation_matrix * orientation_mat * inv_rotation_matrix).GetOrthonormalized().ExtractRotationQuat();

                            GfVec3d converted_lin_acc = (rotation_matrix * lin_acc_mat * inv_rotation_matrix).GetOrthonormalized().ExtractTranslation();

                            //CARB_LOG_INFO("%f %f %f %f",
                            //    converted_quat.GetImaginary()[0],
                            //    converted_quat.GetImaginary()[1],
                            //    converted_quat.GetImaginary()[2],
                            //    converted_quat.GetReal());

                            // Resize buffers only if needed
                            if (allocated_size_left < data_size_left) {
                                data_ptr_left = std::make_unique<unsigned char[]>(data_size_left);
                                allocated_size_left = data_size_left;
                            }
                            if (state.m_stereo_camera && allocated_size_right < data_size_right) {
                                data_ptr_right = std::make_unique<unsigned char[]>(data_size_right);
                                allocated_size_right = data_size_right;
                            }

                            // Copy data from GPU to CPU
                            cudaError_t err_left = cudaMemcpyAsync(data_ptr_left.get(),
                                raw_ptr_left,
                                data_size_left, cudaMemcpyDeviceToHost, cudaStream);

                            cudaError_t err_right = cudaSuccess;

                            if (state.m_stereo_camera)
                            {
                                err_right = cudaMemcpyAsync(data_ptr_right.get(),
                                    raw_ptr_right,
                                    data_size_right, cudaMemcpyDeviceToHost, cudaStream);
                            }

                            if (err_left != cudaSuccess || err_right != cudaSuccess) {
                                //CARB_LOG_ERROR("CUDA memcpy error in streaming thread: %s",
                                //    cudaGetErrorString(err_left != cudaSuccess ? err_left : err_right));
                                continue;
                            }

                            // Wait for GPU operations to complete
                            cudaError_t sync_err = cudaStreamSynchronize(cudaStream);
                            if (sync_err != cudaSuccess) {
                                CARB_LOG_ERROR("[ZED] CUDA stream synchronization error: %s", cudaGetErrorString(sync_err));
                                continue;
                            }

                            // Stream the data immediately
                            auto ts_ns = static_cast<long long>(timestamp * 1000000000);

                            int stream_status = state.m_zedStreamer.stream(state.m_zedStreamerParams.input_format, state.m_streamer_id,
                                data_ptr_left.get(),
                                data_ptr_right.get(),
                                ts_ns,
                                static_cast<float>(converted_orientation.GetReal()),
                                static_cast<float>(converted_orientation.GetImaginary()[0]),
                                static_cast<float>(converted_orientation.GetImaginary()[1]),
                                static_cast<float>(converted_orientation.GetImaginary()[2]),
                                static_cast<float>(converted_lin_acc[0]),
                                static_cast<float>(converted_lin_acc[1]),
                                static_cast<float>(converted_lin_acc[2]));

							//CARB_LOG_WARN(" [ZED] Streamed frame at time %f (status %d)", timestamp, stream_status);

                        }

                        CARB_LOG_INFO("[ZED] Streaming thread stopped");
                    }

public:

                    OgnZEDSimCameraNode()
                    {
                        //CARB_LOG_WARN("Create node");
                        m_zedStreamerInitStatus = false;
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
                            m_valid = true;
                            CARB_LOG_INFO("[ZED] Successfully found and loaded ZED SDK");
                        }
                        else
                        {
                            CARB_LOG_ERROR("[ZED] Error while loading ZED SDK. Make sure a compatible version is installed");
                        }

						m_streamer_id = streamer_id;
                    }

                    ~OgnZEDSimCameraNode()
                    {
                        stop();
                    }

                    void stop()
                    {
                        remaining_serial_numbers = available_zed_cameras;

                        // Stop the streaming thread
                        m_shouldStop.store(true, std::memory_order_release);

                        if (m_streamingThread.joinable()) {
                            m_streamingThread.join();
                        }

                        // Clean up ZED streamer
                        if (m_zedStreamerInitStatus == 1) {
                            m_zedStreamer.closeStreamer(m_streamer_id);
                            m_zedStreamer.destroyInstance();

                            m_zedStreamerInitStatus = 0;
                        }

                        // Clean up CUDA stream if it was created
                        if (!m_cudaStreamNotCreated) {
                            cudaError_t err = cudaStreamDestroy(m_cudaStream);
                            if (err != cudaSuccess) {
                                CARB_LOG_ERROR("[ZED] Error destroying CUDA stream in destructor: %s", cudaGetErrorString(err));
                            }
                        }

                        CARB_LOG_INFO("[ZED] Stop streamer %d", m_streamer_id);
                        m_zedStreamer.unload();
                        m_valid = false;
                        streamer_id -= 1;
                    }


                    // called every time a new frame is rendered
                    static bool compute(OgnZEDSimCameraNodeDatabase& db)
                    {
                        auto& state = db.perInstanceState<OgnZEDSimCameraNode>();
                        if (!state.m_valid || !db.inputs.stream()) return false;

                        // Done once, init the streamer and start a stream
                        if (state.m_zedStreamerInitStatus != 1)
                        {
                            float warmup = 1.0f;
                            if (db.inputs.simulationTime() < warmup) return true;

                            state.m_stereo_camera = db.inputs.bufferSizeRight() > 0 && reinterpret_cast<void*>(db.inputs.dataPtrRight()) != nullptr;

							std::string camera_model = db.inputs.cameraModel();
                            if (!state.m_stereo_camera)
                            {
                                CARB_LOG_INFO("[ZED] Opening mono camera %s", camera_model.c_str());
                            }

                            unsigned short port = db.inputs.port();

                            int serial_number = -1;
                            if (camera_model == "VIRTUAL_ZED_X")
                            {
                                serial_number = std::stoi(db.inputs.serialNumber());
                            }
                            else
                            {
                                serial_number = addStreamer(camera_model);
                            }

                            if (serial_number <= 0)
                            {
                                CARB_LOG_FATAL("[ZED] Invalid streamer configuration!");
                                state.m_valid = false;
                                return false;
                            }

                            CARB_LOG_INFO("[ZED] Opening camera %d : %d", serial_number, port);

                            bool use_ipc = db.inputs.ipc();

#ifdef _WIN32
                            use_ipc = false;

                            CARB_LOG_WARN("[ZED] IPC mode is not available on Windows. Switching back to network streaming...");
#endif
							// Use YUV format for IPC or mono cameras
                            bool use_yuv = use_ipc || !state.m_stereo_camera;
                            state.m_zedStreamer.load_api();
                            state.m_zedStreamerParams.alpha_channel_included = true;
                            state.m_zedStreamerParams.codec_type = 1;
                            state.m_zedStreamerParams.fps = db.inputs.fps();
                            state.m_zedStreamerParams.image_height = db.inputs.height();
                            state.m_zedStreamerParams.image_width = db.inputs.width();
                            state.m_zedStreamerParams.mode = 1;
                            state.m_zedStreamerParams.transport_layer_mode = use_ipc;
                            state.m_zedStreamerParams.input_format = use_yuv ? sl::INPUT_FORMAT::YUV : sl::INPUT_FORMAT::BGR;
                            state.m_zedStreamerParams.serial_number = serial_number;
                            state.m_zedStreamerParams.port = port;
                            state.m_zedStreamerParams.verbose = 0;

                            state.m_zedStreamerInitStatus = state.m_zedStreamer.initStreamer(state.m_streamer_id, &state.m_zedStreamerParams);

                            if (state.m_zedStreamerInitStatus)
                            {
                                streamer_id++;
                                CARB_LOG_INFO("[ZED] Start Streaming at port %d", state.m_zedStreamerParams.port);

                                // Create CUDA stream
                                CUDA_CHECK(cudaStreamCreate(&state.m_cudaStream));
                                state.m_cudaStreamNotCreated = false;

                                // Start streaming thread
                                state.m_streamingThread = std::thread(&OgnZEDSimCameraNode::streamingThreadFunc, std::ref(state));
                            }
                            else {
                                CARB_LOG_ERROR("Error during zed streamer initialization %d", state.m_zedStreamerInitStatus);
                                return false;
                            }
                        }
                        else
                        {
                            // Get frame data pointers and sizes
                            const size_t data_size_left{ db.inputs.bufferSizeLeft() };
                            const void* raw_ptr_left{ reinterpret_cast<void*>(db.inputs.dataPtrLeft()) };
                            const size_t data_size_right{ db.inputs.bufferSizeRight() };
                            const void* raw_ptr_right{ reinterpret_cast<void*>(db.inputs.dataPtrRight()) };

                            if (!raw_ptr_left)
                            {
                                CARB_LOG_ERROR("[ZED] Left image is not valid");
                                return false;
                            }

                            if (state.m_stereo_camera && data_size_left != data_size_right)
                            {
                                CARB_LOG_ERROR("[ZED] Left and Right images have different sizes");
                                return false;
                            }

                            // Prepare new frame data (just pointers and metadata)
                            auto new_frame = std::make_shared<FrameData>(
                                raw_ptr_left, data_size_left,
                                state.m_stereo_camera ? raw_ptr_right : nullptr,
                                state.m_stereo_camera ? data_size_right : 0
                            );

                            new_frame->timestamp = db.inputs.simulationTime();
                            new_frame->valid = true;
                            new_frame->quaternion = db.inputs.orientation();
                            new_frame->linear_acceleration = db.inputs.linearAcceleration();

                            // Write frame to the double buffer
                            state.m_frameBuffer.write(std::move(new_frame));
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

            } // bridge
        } // camera
    } // sensor
} // sl