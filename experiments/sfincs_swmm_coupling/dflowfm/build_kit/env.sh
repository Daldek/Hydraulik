# Source this file before configuring/building D-Flow FM with the free GNU toolchain.
#   source /home/user/sfincs_feas/dflowfm_build/env.sh
export DFM_BUILD_ROOT=/home/user/sfincs_feas/dflowfm_build
export DELFT3D_SRC=/home/user/sfincs_feas/d3d_check/Delft3D
# CMake >= 3.30 is required by src/cmake/CMakeLists.txt (Ubuntu 24.04 ships 3.28) -> CMake from PyPI in a private venv
export PATH=$DFM_BUILD_ROOT/tools-venv/bin:$PATH
# Delft3D's Linux CMake never links MPI targets explicitly; it relies on MPI compiler wrappers
# (Deltares uses mpiifx/mpiicx/mpicxx). Free equivalent: Open MPI wrappers around gcc/g++/gfortran 13.
export CC=mpicc
export CXX=mpicxx
export FC=mpif90
export PETSC_DIR=$DFM_BUILD_ROOT/deps/petsc
export PRECICE_DIR=$DFM_BUILD_ROOT/deps/precice
export CMAKE_PREFIX_PATH=$DFM_BUILD_ROOT/cmake_shims:$PRECICE_DIR
export LD_LIBRARY_PATH=$PETSC_DIR/lib:$PRECICE_DIR/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
