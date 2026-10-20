# Shim: Ubuntu's libhdf5-dev (autotools build) ships no CMake config package; wrap CMake's FindHDF5 module.
# HDF5_NO_FIND_PACKAGE_CONFIG_FILE stops FindHDF5 from calling find_package(HDF5 CONFIG) again (infinite recursion).
set(HDF5_NO_FIND_PACKAGE_CONFIG_FILE TRUE)
find_package(HDF5 MODULE REQUIRED COMPONENTS C HL)
