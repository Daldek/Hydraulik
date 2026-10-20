# STUB: SWAN (D-Waves wave model) is not needed for D-Flow FM. Empty imported target only,
# so that find_package(SWAN_OMP CONFIG REQUIRED) in src/cmake/CMakeLists.txt succeeds.
message(STATUS "SWAN_OMP: using EMPTY STUB (D-Waves/SWAN not built)")
if(NOT TARGET SWAN_OMP::SWAN_OMP)
    add_library(SWAN_OMP::SWAN_OMP INTERFACE IMPORTED)
endif()
