# STUB: SWAN (D-Waves wave model) is not needed for D-Flow FM. Empty imported target only,
# so that find_package(SWAN_MPI CONFIG REQUIRED) in src/cmake/CMakeLists.txt succeeds.
message(STATUS "SWAN_MPI: using EMPTY STUB (D-Waves/SWAN not built)")
if(NOT TARGET SWAN_MPI::SWAN_MPI)
    add_library(SWAN_MPI::SWAN_MPI INTERFACE IMPORTED)
endif()
