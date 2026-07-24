#ifndef SL_ZED_SIM2REAL_LOADER_HPP
#define SL_ZED_SIM2REAL_LOADER_HPP

// Runtime loader for the sl_zed_sim2real shared library (the ZED Sim2Real camera model).
// Mirrors zed_interface_loader.hpp: the library is loaded by absolute path from the
// plugin's own directory and its C ABI is resolved with GetProcAddress/dlsym, so the
// plugin build links nothing from it (only cudart) and the sim2real degrades gracefully
// to "unavailable" if the library is missing.

#include <string>
#include "zed_interface_loader.hpp"   // reuse sl::get_current_module_dir() + Lib macros
#include "sl_zed_sim2real.h"

namespace sl {

class ZedSim2Real {
public:
    using AbiVersion        = int (*)();
    using EngineCreate      = sl_zed_sim2real_engine* (*)();
    using EngineDestroy     = void (*)(sl_zed_sim2real_engine*);
    using StateCreate       = sl_zed_sim2real_state* (*)(unsigned int);
    using StateDestroy      = void (*)(sl_zed_sim2real_state*);
    using ProcessDeviceOut  = const void* (*)(sl_zed_sim2real_engine*, sl_zed_sim2real_state*,
                                              const void*, int, int, void*, int, float, int);
    using ProcessHost       = int (*)(sl_zed_sim2real_state*, unsigned char*, int, int, int, float, int);
    using StateSetAeTarget  = void (*)(sl_zed_sim2real_state*, float);

    EngineCreate     engine_create{ nullptr };
    EngineDestroy    engine_destroy{ nullptr };
    StateCreate      state_create{ nullptr };
    StateDestroy     state_destroy{ nullptr };
    ProcessDeviceOut process_device_out{ nullptr };
    ProcessHost      process_host{ nullptr };
    // v0.2.0 additive export: may be null on older libraries (callers must check)
    StateSetAeTarget state_set_ae_target{ nullptr };

    ~ZedSim2Real() { unload(); }

    bool available() const { return loaded_; }

    // Load the library from the plugin's directory. Idempotent; returns false (and logs
    // once) if the library or any expected symbol is missing.
    bool load() {
        if (loaded_) return true;
        if (load_failed_) return false;
#ifdef _WIN32
        const std::string name = "sl_zed_sim2real.dll";
        const char sep = '\\';
#else
        const std::string name = "libsl_zed_sim2real.so";
        const char sep = '/';
#endif
        const std::string dir = get_current_module_dir();
        const std::string path = dir.empty() ? name : dir + sep + name;
        h_ = LoadLib(path.c_str());
        if (!h_) {
            CARB_LOG_WARN("[ZED] sl_zed_sim2real not loaded (%s); ZED Sim2Real disabled", path.c_str());
            load_failed_ = true;
            return false;
        }
        // ABI handshake: refuse a library built against a different C ABI than we vendor.
        auto abi = (AbiVersion)GetFunc(h_, "sl_zed_sim2real_abi_version");
        if (!abi || abi() != SL_ZED_SIM2REAL_ABI_VERSION) {
            CARB_LOG_ERROR("[ZED] sl_zed_sim2real ABI mismatch (lib %d, expected %d); ZED Sim2Real disabled",
                           abi ? abi() : -1, SL_ZED_SIM2REAL_ABI_VERSION);
            CloseLib(h_); h_ = nullptr;
            load_failed_ = true;
            return false;
        }
        engine_create      = (EngineCreate)     GetFunc(h_, "sl_zed_sim2real_engine_create");
        engine_destroy     = (EngineDestroy)    GetFunc(h_, "sl_zed_sim2real_engine_destroy");
        state_create       = (StateCreate)      GetFunc(h_, "sl_zed_sim2real_state_create");
        state_destroy      = (StateDestroy)     GetFunc(h_, "sl_zed_sim2real_state_destroy");
        process_device_out = (ProcessDeviceOut) GetFunc(h_, "sl_zed_sim2real_process_device_out");
        process_host       = (ProcessHost)      GetFunc(h_, "sl_zed_sim2real_process_host");
        // additive (v0.2.0) — intentionally NOT part of the loaded_ requirement
        state_set_ae_target = (StateSetAeTarget) GetFunc(h_, "sl_zed_sim2real_state_set_ae_target");
        loaded_ = engine_create && engine_destroy && state_create && state_destroy &&
                  process_device_out && process_host;
        if (!loaded_) {
            CARB_LOG_ERROR("[ZED] sl_zed_sim2real is missing expected symbols; ZED Sim2Real disabled");
            load_failed_ = true;
        } else {
            CARB_LOG_INFO("[ZED] %s successfully loaded", path.c_str());
        }
        return loaded_;
    }

    void unload() {
        if (h_) { CloseLib(h_); h_ = nullptr; }
        loaded_ = false;
    }

private:
    LibHandle h_{ nullptr };
    bool loaded_{ false };
    bool load_failed_{ false };
};

} // namespace sl
#endif // SL_ZED_SIM2REAL_LOADER_HPP
