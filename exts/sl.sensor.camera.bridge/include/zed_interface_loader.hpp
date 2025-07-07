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
#define ZED_SDK_VERSION_MINOR 1
#define ZED_SDK_VERSION_PATCH 0

namespace sl
{
    class ZedStreamer {
    private:
        LibHandle hLibrary;
    
        typedef int (*GetSDKVersion)(int&, int&, int&);
        typedef bool (*InitStreamerFunc)(int, struct StreamingParameters*);
        typedef int (*StreamRGBFunc)(int, unsigned char*, unsigned char*, long long, float, float, float, float, float, float, float);
        typedef int (*StreamYUVFunc)(int, unsigned char*, unsigned char*, long long, float, float, float, float, float, float, float);
        typedef void (*CloseStreamerFunc)(int);
        typedef void (*DestroyInstanceFunc)();
        typedef int* (*GetVirtualCameraIdentifiersFunc)(int*);
        typedef int (*IngestImuFunc)(int, long long, float, float, float, float, float, float, float, float, float, float);
    
        GetSDKVersion get_sdk_version;
        InitStreamerFunc init_streamer;
        StreamRGBFunc stream_rgb;
        StreamYUVFunc stream_yuv;
        CloseStreamerFunc close_streamer;
        DestroyInstanceFunc destroy_instance;
        GetVirtualCameraIdentifiersFunc get_virtual_camera_identifiers;
        IngestImuFunc ingest_imu;
    
        bool loaded;

    public:
        ZedStreamer() : hLibrary(nullptr), loaded(false) {
            get_sdk_version = nullptr;
            init_streamer = nullptr;
            stream_rgb = nullptr;
            stream_yuv = nullptr;
            close_streamer = nullptr;
            destroy_instance = nullptr;
            get_virtual_camera_identifiers = nullptr;
            ingest_imu = nullptr;
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

            //CARB_LOG_INFO("[ZED] %s successfully loaded", zed_lib_path.c_str());
            loaded = true;
            return true;
        }
    
        bool load_api() 
        {   
            init_streamer = (InitStreamerFunc)GetFunc(hLibrary, "init_streamer");
            stream_rgb = (StreamRGBFunc)GetFunc(hLibrary, "stream_rgb");
            stream_yuv = (StreamYUVFunc)GetFunc(hLibrary, "stream_yuv");
            close_streamer = (CloseStreamerFunc)GetFunc(hLibrary, "close_streamer");
            destroy_instance = (DestroyInstanceFunc)GetFunc(hLibrary, "destroy_instance");
            get_virtual_camera_identifiers = (GetVirtualCameraIdentifiersFunc)GetFunc(hLibrary, "get_virtual_camera_identifiers");
            ingest_imu = (IngestImuFunc)GetFunc(hLibrary, "ingest_imu");
                
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
            close_streamer = nullptr;
            destroy_instance = nullptr;
            get_virtual_camera_identifiers = nullptr;
            ingest_imu = nullptr;
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
    
        bool initStreamer(int streamer_id, struct StreamingParameters* streaming_params) {
            if (!loaded || !init_streamer) {
                std::cerr << "[ZED] Error with init_streamer function call" << std::endl;
                return false;
            }
            return init_streamer(streamer_id, streaming_params);
        }
    
        int stream(sl::INPUT_FORMAT input, int streamer_id, unsigned char* left, unsigned char* right,
                       long long timestamp_ns, float qw, float qx, float qy, float qz, 
                       float lin_acc_x, float lin_acc_y, float lin_acc_z) {

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
    
        int* getVirtualCameraIdentifiers(int* size_out) {
            if (!loaded || !get_virtual_camera_identifiers) {
                std::cerr << "[ZED] Error with get_virtual_camera_identifiers function call" << std::endl;
                return nullptr;
            }
            return get_virtual_camera_identifiers(size_out);
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