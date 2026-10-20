# Source this file before configuring/building D-Flow FM with the Intel oneAPI 2024.2 toolchain.
#   source /home/user/sfincs_feas/dflowfm_build/env_intel.sh
source /opt/intel/oneapi/setvars.sh --force > /dev/null 2>&1   # ifx/icx/icpx 2024.2 + Intel MPI 2021.13
export DFM_BUILD_ROOT=/home/user/sfincs_feas/dflowfm_build
export DELFT3D_SRC_INTEL=/home/user/sfincs_feas/d3d_check/Delft3D_intel   # clean git worktree @ 54e33a7
export DEPS_INTEL=$DFM_BUILD_ROOT/deps_intel
export PATH=$DFM_BUILD_ROOT/tools-venv/bin:$PATH                         # CMake 4.1.2 (>= 3.30 required)
# Same wrappers as Deltares' third-party-libs container: FC=mpiifx, CC=mpiicx, CXX=mpicxx (g++ underneath)
export CC=mpiicx CXX=mpicxx
# The Intel netcdf.mod dir must be searched before "-isystem /usr/include" (added by the apt netCDF-C/GDAL
# targets), because Ubuntu's libnetcdff-dev puts a gfortran-only netcdf.mod there.
export FC="mpiifx -I$DEPS_INTEL/netcdf-fortran/include"
export PETSC_DIR=$DEPS_INTEL/petsc
export CMAKE_PREFIX_PATH=$DFM_BUILD_ROOT/cmake_shims_intel:$DEPS_INTEL/precice:$DEPS_INTEL/netcdf-fortran
export LD_LIBRARY_PATH=$DEPS_INTEL/petsc/lib:$DEPS_INTEL/precice/lib:$DEPS_INTEL/netcdf-fortran/lib:$LD_LIBRARY_PATH
