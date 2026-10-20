# Shim: triangle built from src/third_party_open/triangle (same source the Deltares Conan recipe uses).
set(TRIANGLE_DIR "/home/user/sfincs_feas/dflowfm_build/deps/triangle" CACHE PATH "triangle install prefix")
if(NOT TARGET triangle::triangle)
    add_library(triangle::triangle STATIC IMPORTED)
    set_target_properties(triangle::triangle PROPERTIES
        IMPORTED_LOCATION "${TRIANGLE_DIR}/lib/libtriangle.a"
        INTERFACE_INCLUDE_DIRECTORIES "${TRIANGLE_DIR}/include"
        INTERFACE_LINK_LIBRARIES m)
endif()
