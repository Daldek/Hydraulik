# STUB: inja (C++ template engine) is only used by D-Waves (wave_data). Empty imported target only.
message(STATUS "inja: using EMPTY STUB (only needed by D-Waves)")
if(NOT TARGET pantor::inja)
    add_library(pantor::inja INTERFACE IMPORTED)
endif()
