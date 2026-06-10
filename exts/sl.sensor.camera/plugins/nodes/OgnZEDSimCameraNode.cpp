
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

            static std::string simCameraModelKey(int model, bool is_4mm) {
                switch (model) {
                    case 4:  return is_4mm ? "ZED_X_4MM" : "ZED_X";
                    case 5:  return is_4mm ? "ZED_XM_4MM" : "ZED_XM";
                    case 9:  return "ZED_X_Nano";
                    case 30: return is_4mm ? "ZED_XONE_GS_4MM" : "ZED_XONE_GS";
                    case 31: return "ZED_XONE_UHD";
                    case 32: return "ZED_X_ONE_S_FISHEYE";
                    default: return "";
                }
            }

            // List of available SN per camera model (populated from SDK at runtime)
            static std::map<std::string, std::vector<int>> available_zed_cameras = {};

            // List of currently opened cameras
            static std::map<std::string, std::vector<int>> remaining_serial_numbers = {};

            static void populateAvailableCameras(sl::ZedStreamer& streamer) {
                available_zed_cameras.clear();
                int count = 0;
                sl::SimCameraInfo* info = streamer.getVirtualCameraInfo(&count);
                if (!info || count == 0) return;
                for (int i = 0; i < count; i++) {
                    std::string key = simCameraModelKey(info[i].model, info[i].is_4mm != 0);
                    if (!key.empty())
                        available_zed_cameras[key].push_back(info[i].serial_number);
                }
            }

            // Try to open a new streamer given a camera model. Check if a serial number is still available among the list.
            static int addStreamer(const std::string& camera_model)
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

            static int removeStreamer(const std::string& camera_model, int serial_number)
            {
                // If the serial number is already in the list, do not add it again
                if (std::find(remaining_serial_numbers[camera_model].begin(),
                    remaining_serial_numbers[camera_model].end(),
                    serial_number) != remaining_serial_numbers[camera_model].end())
                {
                    CARB_LOG_ERROR("[ZED] Trying to remove invalid serial number %d for camera model %s",
                        serial_number, camera_model.c_str());
                    return -1;
                }
                remaining_serial_numbers[camera_model].push_back(serial_number);
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
                    CARB_LOG_WARN("[ZED] Invalid transport layer mode string %s, defaulting to RTP_ONLY", mode_str.c_str());
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
                bool m_valid{ false };
                double previous_timestamp{ 0.0f };

                // Threading members
                std::thread m_streamingThread;
                std::atomic<bool> m_shouldStop{ false };
                sl::DoubleBuffer<FrameData> m_frameBuffer;
                unsigned int m_streamer_id{ 0 };

                size_t allocated_size_left{0};
                size_t allocated_size_right{0};
                std::unique_ptr<unsigned char[]> data_ptr_left{nullptr};
                std::unique_ptr<unsigned char[]> data_ptr_right{nullptr};

                static const pxr::GfMatrix4d rotation_matrix;
                static const pxr::GfMatrix4d inv_rotation_matrix;

                static void streamFrame(OgnZEDSimCameraNode& state, const std::shared_ptr<FrameData>& current_frame)
                {
                    if (!current_frame || !current_frame->valid)
                        return;

                    // Avoid streaming the same frame multiple times
                    if (current_frame->timestamp <= state.previous_timestamp)
                        return;

                    state.previous_timestamp = current_frame->timestamp;

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

                    // Resize buffers only if needed
                    if (state.data_ptr_left == nullptr || state.allocated_size_left < data_size_left) {
                        state.data_ptr_left = std::make_unique<unsigned char[]>(data_size_left);
                        state.allocated_size_left = data_size_left;
                    }
                    if (state.m_stereo_camera && (state.data_ptr_right == nullptr || state.allocated_size_right < data_size_right)) {
                        state.data_ptr_right = std::make_unique<unsigned char[]>(data_size_right);
                        state.allocated_size_right = data_size_right;
                    }

                    // Copy data from GPU to CPU
                    cudaError_t err_left = cudaMemcpyAsync(state.data_ptr_left.get(),
                        raw_ptr_left,
                        data_size_left, cudaMemcpyDeviceToHost, cudaStream);

                    cudaError_t err_right = cudaSuccess;

                    if (state.m_stereo_camera)
                    {
                        err_right = cudaMemcpyAsync(state.data_ptr_right.get(),
                            raw_ptr_right,
                            data_size_right, cudaMemcpyDeviceToHost, cudaStream);
                    }

                    if (err_left != cudaSuccess || err_right != cudaSuccess) {
                        CARB_LOG_ERROR("CUDA memcpy error in streaming thread: %s",
                            cudaGetErrorString(err_left != cudaSuccess ? err_left : err_right));
                        return;
                    }

                    // Wait for GPU operations to complete
                    cudaError_t sync_err = cudaStreamSynchronize(cudaStream);
                    if (sync_err != cudaSuccess) {
                        CARB_LOG_ERROR("[ZED] CUDA stream synchronization error: %s", cudaGetErrorString(sync_err));
                        return;
                    }

                    // Stream the data immediately
                    unsigned long long ts_ns = static_cast<unsigned long long>(timestamp * 1000000000);

                    int stream_status = state.m_zedStreamer.stream(state.m_zedStreamerParams.input_format, state.m_streamer_id,
                        state.data_ptr_left.get(),
                        state.data_ptr_right.get(),
                        ts_ns,
                        static_cast<float>(converted_orientation.GetReal()),
                        -static_cast<float>(converted_orientation.GetImaginary()[0]),
                        -static_cast<float>(converted_orientation.GetImaginary()[1]),
                        static_cast<float>(converted_orientation.GetImaginary()[2]),
                        static_cast<float>(converted_lin_acc[0]),
                        static_cast<float>(converted_lin_acc[1]),
                        static_cast<float>(converted_lin_acc[2]));
                }

                static void streamingThreadFunc(OgnZEDSimCameraNode& state) {
                    int frame_index = -1;

                    while (!state.m_shouldStop.load())
                    {
                        auto current_frame = state.m_frameBuffer.wait_and_read(state.m_shouldStop, frame_index);
                        if (!current_frame || !current_frame->valid)
                        {
                            continue;
                        }

                        streamFrame(state, current_frame);
                    }
                }

public:

                OgnZEDSimCameraNode()
                {
                    m_zedStreamerInitStatus = 0;
                    m_cudaStreamNotCreated = true;
                    m_shouldStop = false;

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

                    m_zedStreamer.unload();
                    m_valid = false;
                    streamer_id -= 1;
                }


                // called every time a new frame is rendered
                static bool compute(OgnZEDSimCameraNodeDatabase& db)
                {
                    auto& state = db.perInstanceState<OgnZEDSimCameraNode>();
                    if (!state.m_valid || !db.inputs.stream()) {
                        CARB_LOG_WARN("INVALID STATE OR STREAMING DISABLED");
                        return false;
                    }

                    // Done once, init the streamer and start a stream
                    if (state.m_zedStreamerInitStatus != 1)
                    {
                        float warmup = 1.0f;
                        if (db.inputs.simulationTime() < warmup) return true;

                        state.m_zedStreamer.load_api();

                        if (available_zed_cameras.empty())
                        {
                            populateAvailableCameras(state.m_zedStreamer);
                            remaining_serial_numbers = available_zed_cameras;
                        }

                        state.m_stereo_camera = db.inputs.bufferSizeRight() > 0 && reinterpret_cast<void*>(db.inputs.dataPtrRight()) != nullptr;

                        std::string camera_model = db.inputs.cameraModel();
                        if (!state.m_stereo_camera)
                        {
                            CARB_LOG_INFO("[ZED] Opening mono camera %s", camera_model.c_str());
                        } else {
                            CARB_LOG_INFO("[ZED] Opening stereo camera %s", camera_model.c_str());
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

                            removeStreamer(camera_model, serial_number);
                            return false;
                        }

                        int transport_layer_mode = transportLayerModeToInt(db.tokenToString(db.inputs.transportLayerMode()));

#ifdef _WIN32
                        // 0 = Network, 1 = IPC, 2 = Both
                        transport_layer_mode = 0;

                        CARB_LOG_WARN("[ZED] IPC mode is not available on Windows. Switching back to network streaming...");
#endif
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
                        state.m_zedStreamerParams.serial_number = serial_number;
                        state.m_zedStreamerParams.port = port;
                        state.m_zedStreamerParams.verbose = 0;
                        state.m_streamer_id = streamer_id++;
                        state.m_zedStreamerInitStatus = state.m_zedStreamer.initStreamer(state.m_streamer_id, &state.m_zedStreamerParams);

                        if (state.m_zedStreamerInitStatus > 0)
                        {
                            CARB_LOG_INFO("[ZED] ZED Streamer initialized successfully with ID %d", state.m_streamer_id);

                            // Create CUDA stream
                            CUDA_CHECK(cudaStreamCreate(&state.m_cudaStream));
                            state.m_cudaStreamNotCreated = false;

                            // Start streaming thread
                            // state.m_streamingThread = std::thread(&OgnZEDSimCameraNode::streamingThreadFunc, std::ref(state));
                        }
                        else {
                            CARB_LOG_ERROR("Error during zed streamer initialization %d", state.m_zedStreamerInitStatus);
                            removeStreamer(camera_model, serial_number);
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
                        streamFrame(state, new_frame);
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