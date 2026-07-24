#ifndef ZED_INTERFACE_LOADER_HPP
#define ZED_INTERFACE_LOADER_HPP

#include <string>
#include <iostream>

#include "types_c.h"

#ifdef _WIN32
#include <windows.h>
using LibHandle = HMODULE;
#define LoadLib(path) LoadLibraryA(path)
#define GetFunc GetProcAddress
#define CloseLib FreeLibrary
#else
#include <dlfcn.h>
using LibHandle = void*;
#define LoadLib(path) dlopen(path, RTLD_LAZY)
#define GetFunc dlsym
#define CloseLib dlclose
#endif

#define ZED_SDK_VERSION_MAJOR 5
#define ZED_SDK_VERSION_MINOR 4
#define ZED_SDK_VERSION_PATCH 1

namespace sl
{
    // Returns the directory containing this plugin's shared library,
    // so the bundled sl_zed library can be loaded by absolute path
    // (a bare name would let the dynamic linker pick up a ZED SDK
    // system install via LD_LIBRARY_PATH/ldconfig instead).
    inline std::string get_current_module_dir()
    {
#ifdef _WIN32
        HMODULE hModule = nullptr;
        GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                           GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)&get_current_module_dir, &hModule);
        char path[MAX_PATH] = {0};
        if (!hModule || GetModuleFileNameA(hModule, path, MAX_PATH) == 0) {
            return std::string();
        }
        std::string dir(path);
        size_t pos = dir.find_last_of("\\/");
        return (pos != std::string::npos) ? dir.substr(0, pos) : std::string();
#else
        Dl_info info{};
        if (dladdr((void*)&get_current_module_dir, &info) && info.dli_fname) {
            std::string dir(info.dli_fname);
            size_t pos = dir.find_last_of('/');
            return (pos != std::string::npos) ? dir.substr(0, pos) : std::string();
        }
        return std::string();
#endif
    }

    class ZedStreamer {
    private:
        LibHandle hLibrary;

        typedef int (*GetSDKVersion)(int&, int&, int&);
        typedef int (*InitStreamerFunc)(int, struct StreamingParameters*);
        typedef int (*StreamRGBFunc)(int, unsigned char*, unsigned char*, long long, float, float, float, float, float, float, float);
        typedef int (*StreamYUVFunc)(int, unsigned char*, unsigned char*, long long, float, float, float, float, float, float, float);
        typedef int (*StreamLeftAndDepthFunc)(int, unsigned char*, float*, long long, float, float, float, float, float, float, float);
        typedef void (*CloseStreamerFunc)(int);
        typedef void (*DestroyInstanceFunc)();
        typedef int (*IngestImuFunc)(int, long long, float, float, float, float, float, float, float, float, float, float);
        typedef bool (*IsSNValidFunc)(int);
        typedef SimCameraInfo* (*GetVirtualCameraInfoFunc)(int*);

        GetSDKVersion get_sdk_version;
        InitStreamerFunc init_streamer;
        StreamRGBFunc stream_rgb;
        StreamYUVFunc stream_yuv;
        StreamLeftAndDepthFunc stream_left_and_depth;
        CloseStreamerFunc close_streamer;
        DestroyInstanceFunc destroy_instance;
        GetVirtualCameraInfoFunc get_virtual_camera_info;
        IngestImuFunc ingest_imu;
        IsSNValidFunc is_sn_valid;

        bool loaded;

    public:
        ZedStreamer() : hLibrary(nullptr), loaded(false) {
            get_sdk_version = nullptr;
            init_streamer = nullptr;
            stream_rgb = nullptr;
            stream_yuv = nullptr;
            stream_left_and_depth = nullptr;
            close_streamer = nullptr;
            destroy_instance = nullptr;
            get_virtual_camera_info = nullptr;
            ingest_imu = nullptr;
            is_sn_valid = nullptr;
        }

        ~ZedStreamer() {
            unload();
        }

        bool load_lib(const std::string& zed_lib_path)
        {
            // load the lib
            hLibrary = LoadLib(zed_lib_path.c_str());
            if (!hLibrary) {
                loaded = false;
                CARB_LOG_ERROR("[ZED] Error during lib loading: %s", zed_lib_path.c_str());
                return false;
            }

            CARB_LOG_INFO("[ZED] %s successfully loaded", zed_lib_path.c_str());
            loaded = true;
            return true;
        }

        bool load_api()
        {
            init_streamer = (InitStreamerFunc)GetFunc(hLibrary, "init_streamer");
            stream_rgb = (StreamRGBFunc)GetFunc(hLibrary, "stream_rgb");
            stream_yuv = (StreamYUVFunc)GetFunc(hLibrary, "stream_yuv");
            stream_left_and_depth = (StreamLeftAndDepthFunc)GetFunc(hLibrary, "stream_left_and_depth");
            close_streamer = (CloseStreamerFunc)GetFunc(hLibrary, "close_streamer");
            destroy_instance = (DestroyInstanceFunc)GetFunc(hLibrary, "destroy_instance");
            get_virtual_camera_info = (GetVirtualCameraInfoFunc)GetFunc(hLibrary, "get_virtual_camera_info");
            ingest_imu = (IngestImuFunc)GetFunc(hLibrary, "ingest_imu");
            is_sn_valid = (IsSNValidFunc)GetFunc(hLibrary, "is_sn_valid");

            loaded = true;
            return true;
        }

        void unload()
        {
            if (hLibrary) {
                CloseLib(hLibrary);
                hLibrary = nullptr;
            }
            loaded = false;

            get_sdk_version = nullptr;
            init_streamer = nullptr;
            stream_rgb = nullptr;
            stream_yuv = nullptr;
            stream_left_and_depth = nullptr;
            close_streamer = nullptr;
            destroy_instance = nullptr;
            get_virtual_camera_info = nullptr;
            ingest_imu = nullptr;
            is_sn_valid = nullptr;
        }

        bool isLoaded() const {
            return loaded;
        }
        // 0 is success, -1 if zed sdk was not found
        int getSDKVersion(int& major, int& minor, int& patch)
        {
            if (!isLoaded())
            {
                std::cerr << "[ZED] Error trying to get installed SDK version but the lib is not loaded" << std::endl;
                return -1;
            }

            get_sdk_version = (GetSDKVersion)GetFunc(hLibrary, "getZEDSDKRuntimeVersion_C");

            if (!get_sdk_version)
            {
                std::cerr << "[ZED] Error with get_sdk_version function call" << std::endl;
                return -1;
            }

            return get_sdk_version(major, minor, patch);
        }


        bool isZEDSDKCompatible()
        {
            if (isLoaded())
            {
                int major = 0, minor = 0, patch = 0;

                int res = getSDKVersion(major, minor, patch);
                if (res == 0)
                {
                    CARB_LOG_INFO("[ZED] Found SDK v%d.%d.%d", major, minor, patch);

                    if (major > ZED_SDK_VERSION_MAJOR) return true;
                    if (major < ZED_SDK_VERSION_MAJOR) return false;
                    // if major are equals, compare minor
                    if (minor > ZED_SDK_VERSION_MINOR) return true;
                    if (minor < ZED_SDK_VERSION_MINOR) return false;
                    // if minor are equals, compare patch
                    return patch >= ZED_SDK_VERSION_PATCH;
                }
                return false;
            }

            return false;
        }

        int initStreamer(int streamer_id, struct StreamingParameters* streaming_params) {
            if (!loaded || !init_streamer) {
                std::cerr << "[ZED] Error with init_streamer function call" << std::endl;
                return -1;
            }

            if (streaming_params->transport_layer_mode == 1)
            {
                CARB_LOG_INFO("IPC stream enabled");
            }
            CARB_LOG_WARN("[ZED] Initializing streamer with ID %d on port %d", streamer_id, streaming_params->port);

            return init_streamer(streamer_id, streaming_params);
        }

        int stream(sl::INPUT_FORMAT input, int streamer_id, unsigned char* left, unsigned char* right,
                       long long timestamp_ns, float qw, float qx, float qy, float qz,
                       float lin_acc_x, float lin_acc_y, float lin_acc_z)
        {
            if (input == sl::INPUT_FORMAT::RGB || input == sl::INPUT_FORMAT::BGR)
            {
                if (!loaded || !stream_rgb) {
                    std::cerr << "[ZED] Error with stream_rgb function call" << std::endl;
                    return -1;
                }
                return stream_rgb(streamer_id, left, right, timestamp_ns, qw, qx, qy, qz,
                    lin_acc_x, lin_acc_y, lin_acc_z);
            }
            else
            {
                if (!loaded || !stream_yuv) {
                    std::cerr << "[ZED] Error with stream_yuv function call" << std::endl;
                    return -1;
                }
                return stream_yuv(streamer_id, left, right, timestamp_ns, qw, qx, qy, qz,
                    lin_acc_x, lin_acc_y, lin_acc_z);
            }
        }

        int streamLeftAndDepth(int streamer_id, unsigned char* left, float* depth,
                       long long timestamp_ns, float qw, float qx, float qy, float qz,
                       float lin_acc_x, float lin_acc_y, float lin_acc_z)
        {
            if (!loaded || !stream_left_and_depth) {
                std::cerr << "[ZED] Error with stream_left_and_depth function call" << std::endl;
                return -1;
            }
            return stream_left_and_depth(streamer_id, left, depth, timestamp_ns, qw, qx, qy, qz,
                lin_acc_x, lin_acc_y, lin_acc_z);
        }

        void closeStreamer(int streamer_id) {
            if (!loaded || !close_streamer) {
                std::cerr << "[ZED] Error with close_streamer function call" << std::endl;
                return;
            }
            close_streamer(streamer_id);
        }

        void destroyInstance() {
            if (!loaded || !destroy_instance) {
                std::cerr << "[ZED] Error with destroy_instance function call" << std::endl;
                return;
            }
            destroy_instance();
        }

        bool isSNValid(int serial_number) {
            if (!loaded || !is_sn_valid) {
                std::cerr << "[ZED] Error with is_sn_valid function call" << std::endl;
                return false;
            }
            return is_sn_valid(serial_number);
        }

        SimCameraInfo* getVirtualCameraInfo(int* size_out) {
            if (!loaded || !get_virtual_camera_info) {
                std::cerr << "[ZED] Error with get_virtual_camera_info function call" << std::endl;
                if (size_out) *size_out = 0;
                return nullptr;
            }
            return get_virtual_camera_info(size_out);
        }

        int ingestIMU(int streamer_id, long long timestamp_ns, float vx, float vy, float vz,
                      float lin_acc_x, float lin_acc_y, float lin_acc_z,
                      float qw, float qx, float qy, float qz) {
            if (!loaded || !ingest_imu) {
                std::cerr << "[ZED] Error with ingest_imu function call " << std::endl;
                return -1;
            }
            return ingest_imu(streamer_id, timestamp_ns, vx, vy, vz,
                             lin_acc_x, lin_acc_y, lin_acc_z, qw, qx, qy, qz);
        }
    };

}
#endif // ZED_INTERFACE_LOADER_HPP
