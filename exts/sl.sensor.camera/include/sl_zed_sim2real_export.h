// Shared symbol-visibility macro for the sl_zed_sim2real shared library.
// The build defines SL_ZED_SIM2REAL_BUILD; consumers (the Isaac Sim plugin, the
// Python ctypes binding) do not.
#pragma once

#if defined(_WIN32)
  #if defined(SL_ZED_SIM2REAL_BUILD)
    #define SL_ZED_SIM2REAL_API __declspec(dllexport)
  #else
    #define SL_ZED_SIM2REAL_API __declspec(dllimport)
  #endif
#else
  #define SL_ZED_SIM2REAL_API __attribute__((visibility("default")))
#endif
