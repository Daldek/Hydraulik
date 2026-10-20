# Shim: Ubuntu's libnetcdff-dev (netcdf-fortran 4.5.4, autotools build) ships no CMake config package.
# Provides the imported target netCDF::netcdff that the Delft3D CMake code links against.
if(NOT TARGET netCDF::netcdf)
    find_package(netCDF CONFIG REQUIRED)
endif()
if(NOT TARGET netCDF::netcdff)
    find_library(NETCDFF_LIBRARY NAMES netcdff REQUIRED)
    find_path(NETCDFF_MODULE_DIR NAMES netcdf.mod PATHS /usr/include REQUIRED)
    add_library(netCDF::netcdff SHARED IMPORTED)
    set_target_properties(netCDF::netcdff PROPERTIES
        IMPORTED_LOCATION "${NETCDFF_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${NETCDFF_MODULE_DIR}"
        INTERFACE_LINK_LIBRARIES netCDF::netcdf)
endif()
