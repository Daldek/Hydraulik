#!/usr/bin/env bash
# Run the D-Flow FM CLI built with the free GNU toolchain (see BUILD_NOTES.md).
#
# Usage:
#   run_dflowfm.sh [dflowfm arguments...]
#   run_dflowfm.sh --version
#   run_dflowfm.sh --autostartstop model.mdu          # run a model to completion (current dir = model dir)
#   OMP_NUM_THREADS=4 run_dflowfm.sh --autostartstop model.mdu
#   DFM_NP=4 run_dflowfm.sh --autostartstop model.mdu  # MPI-parallel run (model must be partitioned first,
#                                                    #  e.g. run_dflowfm.sh --partition:ndomains=4 model.mdu)
#
# Environment overrides:
#   DFM_HOME   root of this build kit (default: directory of this script)
#   DFM_NP     number of MPI processes; if set (>1) the run goes through Open MPI's mpirun
set -euo pipefail

DFM_HOME="${DFM_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
DFM_BIN="${DFM_HOME}/build_ninja/dflowfm_cli_exe/dflowfm"

if [[ ! -x "${DFM_BIN}" ]]; then
    echo "run_dflowfm.sh: executable not found: ${DFM_BIN}" >&2
    exit 1
fi

# Libraries built from source for this kit (PETSc 3.25.3, preCICE 3.4.1, libdflowfm.so).
# Everything else (netCDF, HDF5, GDAL, PROJ, Open MPI, OpenBLAS, Boost, gfortran runtime) comes from Ubuntu apt.
export LD_LIBRARY_PATH="${DFM_HOME}/deps/petsc/lib:${DFM_HOME}/deps/precice/lib:${DFM_HOME}/build_ninja/dflowfm_lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

# D-Flow FM uses deep recursion / large automatic arrays: raise the stack limit as Deltares' run scripts do.
ulimit -s unlimited 2>/dev/null || true
export OMP_STACKSIZE="${OMP_STACKSIZE:-20M}"
# Open MPI refuses to run as root unless told otherwise (containers / this VM run as root).
if [[ "$(id -u)" == "0" ]]; then
    export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
fi

if [[ -n "${DFM_NP:-}" && "${DFM_NP}" -gt 1 ]]; then
    exec mpirun -np "${DFM_NP}" "${DFM_BIN}" "$@"
else
    exec "${DFM_BIN}" "$@"
fi
