#!/usr/bin/env bash
# Run the D-Flow FM CLI built with Intel oneAPI 2024.2 (ifx/icx) + Intel MPI 2021.13 (see BUILD_NOTES.md, "Intel build").
# Same interface as run_dflowfm.sh:
#   run_dflowfm_intel.sh --version
#   run_dflowfm_intel.sh --autostartstop model.mdu
#   OMP_NUM_THREADS=4 run_dflowfm_intel.sh --autostartstop model.mdu
#   DFM_NP=4 run_dflowfm_intel.sh --autostartstop model.mdu   # MPI run via Intel mpirun (model must be partitioned)

# Intel runtime (libifcoremt, libiomp5, libimf, libsvml, Intel MPI). setvars.sh is not 'set -u' safe: source it first.
source /opt/intel/oneapi/setvars.sh --force > /dev/null 2>&1
set -euo pipefail

DFM_HOME="${DFM_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
DFM_BIN="${DFM_HOME}/build_intel/dflowfm_cli_exe/dflowfm"
if [[ ! -x "${DFM_BIN}" ]]; then
    echo "run_dflowfm_intel.sh: executable not found: ${DFM_BIN}" >&2
    exit 1
fi

# Libraries built from source with the Intel toolchain for this kit.
export LD_LIBRARY_PATH="${DFM_HOME}/deps_intel/petsc/lib:${DFM_HOME}/deps_intel/precice/lib:${DFM_HOME}/deps_intel/netcdf-fortran/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

ulimit -s unlimited 2>/dev/null || true
export OMP_STACKSIZE="${OMP_STACKSIZE:-20M}"

if [[ -n "${DFM_NP:-}" && "${DFM_NP}" -gt 1 ]]; then
    exec mpirun -np "${DFM_NP}" "${DFM_BIN}" "$@"
else
    exec "${DFM_BIN}" "$@"
fi
