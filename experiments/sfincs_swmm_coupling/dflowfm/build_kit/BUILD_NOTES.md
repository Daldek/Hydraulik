# Building D-Flow FM (Delft3D FM) with free tools only

Date: 2026-10-20. Machine: Ubuntu 24.04, 4 CPUs, 15 GB RAM. Source: Delft3D clone at
`/home/user/sfincs_feas/d3d_check/Delft3D` (commit 54e33a7, 2026-10-19).

**Result:** a working `dflowfm` CLI built with GNU gfortran/gcc 13.3 and Open MPI 4.1.6. No Intel,
Deltares-container, Nexus or other non-free component was used.

- Binary: `/home/user/sfincs_feas/dflowfm_build/build_ninja/dflowfm_cli_exe/dflowfm` (16 MB, with `-g` debug info)
- Wrapper: `/home/user/sfincs_feas/dflowfm_build/run_dflowfm.sh`
- `dflowfm --version` reports: `D-Flow FM Version 1.2.184.Unknown`, with OpenMP, MPI, PETSc, METIS, PROJ,
  Shapelib and GDAL compiled in.
- Example `examples/dflowfm/01_dflowfm_sequential` (f34, 2D, 6882 cells, 25 h simulated, 3018 time steps)
  runs to completion in **8.3 s wall time** (1 thread). It writes `f34_map.nc`, `f34_his.nc`, 3× `_rst.nc`
  and `f34.dia`. The water levels are plausible (tidal, −1.54 … 1.90 m, no NaN).
- **Not done:** `libdflowfm.so` / BMI (CMake target `dflowfm_dll`). It was never built because I was told
  to stop before that step. It should come out of the same tree with
  `cmake --build build_ninja --target dflowfm_dll`, but this is untested.
- **1D / 1D2D not validated.** The repo ships no runnable 1D example; the test data are on Deltares'
  servers.
  - I tried a 1D network from the unit-test data (`src/test/.../test_data/observations_snapped`). It
    needed two obsolete MDU keywords removed and has no cross sections.
  - I added two hand-written cross-section files to it. It initialised (after fix 21 below), but made
    no reported time-step progress within 500 s and was killed.
  - I cannot tell whether my ad-hoc input or the gfortran build is the cause.

## 1. Commands, in order

```bash
# 1a. System packages (Ubuntu 24.04 apt). gfortran/gcc/cmake/libnetcdf(f)-dev/libhdf5-dev were preinstalled.
sudo apt-get update
sudo apt-get install -y --no-install-recommends libopenmpi-dev openmpi-bin libgdal-dev libproj-dev \
  libtiff-dev libgtest-dev libeigen3-dev libxml2-dev libopenblas-dev liblapack-dev libboost-dev \
  libboost-filesystem-dev libboost-date-time-dev libboost-program-options-dev libboost-log-dev \
  libboost-test-dev libboost-thread-dev libboost-system-dev uuid-dev zlib1g-dev pkg-config \
  python3-venv ninja-build
sudo apt-get install -y netcdf-bin gdb        # only for checking output / debugging
```

Versions: gfortran/gcc 13.3.0, Open MPI 4.1.6, netCDF-C 4.9.2, netCDF-Fortran **4.5.4** (Deltares
uses 4.6.2), HDF5 1.10.10, GDAL 3.8.4, PROJ 9.4.0, libtiff 4.5.1, expat 2.6.1, Boost 1.83, GTest 1.14,
Eigen 3.4.0, libxml2 2.9.14, OpenBLAS 0.3.26, ninja 1.11.1.

```bash
B=/home/user/sfincs_feas/dflowfm_build; SRC=/home/user/sfincs_feas/d3d_check/Delft3D
# 1b. CMake >= 3.30 is required (Ubuntu has 3.28) -> private venv
python3 -m venv $B/tools-venv && $B/tools-venv/bin/pip install cmake==4.1.2

# 1c. PETSc 3.25.3 (same version + sha256 as Deltares' conan recipe; that recipe is Intel-only).
#     Source = PyPI sdist (web.cels.anl.gov is blocked here; gitlab.com also works).
#     Took 9 min.
curl -L -o petsc-3.25.3.tar.gz <files.pythonhosted.org URL from https://pypi.org/pypi/petsc/3.25.3/json>
tar xzf petsc-3.25.3.tar.gz && cd petsc-3.25.3
python3 ./configure --prefix=$B/deps/petsc --with-cc=mpicc --with-cxx=mpicxx --with-fc=mpif90 \
  --with-debugging=0 COPTFLAGS=-O3 CXXOPTFLAGS=-O3 FOPTFLAGS=-O3 --with-shared-libraries=1 \
  --with-scalar-type=real --with-precision=double --with-64-bit-indices=0 \
  --with-blaslapack-lib=-lopenblas --with-x=0
make PETSC_DIR=$PWD PETSC_ARCH=arch-linux-c-opt all -j4 && make PETSC_DIR=$PWD PETSC_ARCH=arch-linux-c-opt install

# 1d. preCICE 3.4.1 (options as in Deltares' conan recipe). Took 1 min 47 s.
git clone --depth 1 --branch v3.4.1 https://github.com/precice/precice.git
cmake -S precice -B precice-build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$B/deps/precice \
  -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_C_COMPILER=mpicc -DCMAKE_CXX_COMPILER=mpicxx -DCMAKE_Fortran_COMPILER=mpif90 \
  -DPRECICE_FEATURE_MPI_COMMUNICATION=ON -DPRECICE_FEATURE_PETSC_MAPPING=OFF -DPRECICE_FEATURE_PYTHON_ACTIONS=OFF \
  -DPRECICE_CONFIGURE_PACKAGE_GENERATION=OFF -DBUILD_TESTING=OFF -DPRECICE_HIDE_SYMBOLS=OFF
cmake --build precice-build --parallel 3 && cmake --install precice-build

# 1e. triangle, from the repo's own src/third_party_open/triangle (the same source the conan recipe uses)
cmake -S $SRC/src/third_party_open/triangle -B triangle-build -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=gcc \
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DCMAKE_INSTALL_PREFIX=$B/deps/triangle -DCMAKE_INSTALL_LIBDIR=lib
cmake --build triangle-build && cmake --install triangle-build

# 1f. CMake shim packages for the find_package(... CONFIG REQUIRED) calls (see section 2)
#     -> $B/cmake_shims/lib/cmake/{ZLIB,HDF5,TIFF,netCDF-Fortran,PETSc,triangle,SWAN_MPI,SWAN_OMP,inja}
# 1g. Apply the source/CMake patches:  cd $SRC && git apply $B/patches.diff   (part 1 only)

# 1h. Configure and build D-Flow FM
source $B/env.sh      # PATH (cmake 4.1), CC=mpicc CXX=mpicxx FC=mpif90, CMAKE_PREFIX_PATH=shims:precice, LD_LIBRARY_PATH
mkdir -p $B/build_ninja/conan/generators && touch $B/build_ninja/conan/generators/conan.stamp  # satisfies conan.lock check
cmake -S $SRC/src/cmake -B $B/build_ninja -G Ninja -DCONFIGURATION_TYPE=dflowfm -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=$B/install -DCMAKE_Fortran_FLAGS_RELEASE="-O2 -g"
cmake --build $B/build_ninja --target dflowfm-cli --parallel 4     # target name: dflowfm-cli -> output "dflowfm"

# 1i. Run
$B/run_dflowfm.sh --version
cd <model dir> && OMP_NUM_THREADS=1 $B/run_dflowfm.sh --autostartstop f34.mdu
```

Notes on these commands:

- `CONFIGURATION_TYPE=dflowfm` builds only D-Flow FM. It excludes D-Waves/SWAN, standalone D-WAQ, DIMR
  and Delft3D 4. D-WAQ online-coupling libraries are still compiled as kernel dependencies.
- **Use the Ninja generator.** With "Unix Makefiles", CMake's single-threaded Fortran dependency scan of
  `dflowfm_kernel` (1485 Fortran files) ran for over 20 minutes without finishing, so I abandoned it.
- **Build time on 4 cores, from a clean tree with all patches:** about 15 minutes of machine time in total.
  - PETSc: 9 min
  - preCICE: 1.8 min
  - D-Flow FM: about 3 min wall (about 8 min CPU)
  - apt: about 2 min

  My total elapsed time, including all the debugging, was about 1 h 45 min (18:31 to 20:15).

## 2. Stubs and shims (in `cmake_shims/`, which is part 2 of `patches.diff`)

| Package | How it is provided | What is lost |
|---|---|---|
| ZLIB, HDF5, TIFF | wrappers around CMake's Find modules (Ubuntu ships no CONFIG files) | nothing |
| netCDF-Fortran | imported target `netCDF::netcdff` → `/usr/lib/x86_64-linux-gnu/libnetcdff.so`, `.mod` files in `/usr/include` | nothing known (version 4.5.4 instead of 4.6.2) |
| PETSc | imported target → `deps/petsc` | nothing (real PETSc 3.25.3) |
| triangle | imported static library → `deps/triangle` | nothing |
| precice | real `preciceConfig.cmake` from `deps/precice` | nothing (real preCICE 3.4.1) |
| netCDF-C, expat, PROJ, GDAL, Boost, GTest | Ubuntu's own CMake configs | nothing |
| SWAN_MPI, SWAN_OMP, inja | **empty stub** imported targets | D-Waves (SWAN wave coupling); not linked by D-Flow FM |

MPI comes from Open MPI's compiler wrappers. Deltares uses Intel MPI through mpiifx/mpiicx, and the
Linux CMake never links MPI targets explicitly.

## 3. Source/CMake patches (37 files, +148/−92 lines, `patches.diff` part 1)

Every change is either a gfortran portability fix or a latent bug that ifx tolerates. None of them
disables any functionality.

### Build-system patches

1. `cmake/compiler_options/gnu.cmake`
   - The file had bit-rotted. It now defines `openmp_flag` (a missing value made configure fail),
     `real_size_64_flag` (polypack needs `-r8` semantics), and a few other flag variables that only
     `intel.cmake` defined.
   - It uses `-ffree-line-length-none`, because some lines are longer than 512 characters.
   - It adds `-D__linux__`. Intel's fpp predefines this macro; gfortran's cpp does not. Without it,
     `system_utils.F90` compiled as **Windows** and used `\` path separators, so the run failed when
     creating `output\`.
2. `flow1d_implicit/CMakeLists.txt`: the preprocessed files were listed as `.f`, but they had been
   renamed to `.f90`.

### Non-standard Fortran that ifx accepts and gfortran 13 (and 14) rejects

3. A `USE ..., ONLY:` list naming a symbol that does not exist (`m_alloc.f90`, `unstruc_model.f90`,
   `fm_external_forcings.f90`, `fm_external_forcings_update.f90`).
4. Character array constructors with unequal string lengths and no type-spec (`unit_utils.f90`,
   `caching.f90`).
5. `VALUE` on assumed-length `character(*)` dummy arguments (`structures.f90`, `m_map_his_precision.f90`,
   `read_statistical_output.f90`). These now use a local copy.
6. Integer used as a logical (`if (jampi)`, `if (ja_icecover)`, `jaspacevarcharn .and.`,
   `if (jasfer3D)`), and `logical == .false.`.
   - **Caveat:** with ifx, `if (ja_icecover)` tested the low bit, so ice model 2 counted as "off". It is
     now `/= 0`, as the rest of the code intends.
7. A function declared `integer` that returns a logical (`is_allocated_icecover`).
8. `form='binary'` (Intel extension) replaced by `form='unformatted', access='stream'` (legacy SOBEK
   1D-implicit files).
9. Trailing comma in argument lists (4 files in `flow1d_implicit`).
10. `0.0_dp` used without importing `dp` (`rdmor.f90`, `fm_external_forcings_update.f90`).
11. `!$OMP SIMD ASSERT` (Intel-only clause) → `!$OMP SIMD`.
12. Indented `#if` directives (`intini.F90`).
13. F2018 typed implied-do `[(x, integer :: i=1,n)]` (35×, `unc_write_his.F90`,
    `fm_external_forcings_init.f90`). Even gfortran 14 does not support this.
14. Re-`USE` of `dp` inside a submodule, and `IMPORT` inside non-interface procedures
    (`m_dambreak_breach_submodule.f90`).
15. A generic interface named like its specific procedure, used in a type-bound binding (`laterals.f90`).
16. A procedure name passed to an `intent(in)` procedure-pointer dummy, an F2008 feature gfortran lacks
    (`fm_statistical_output.f90`, 3×). These now go through a local procedure pointer.
17. `c_loc` / `c_f_pointer` imported explicitly from `iso_c_binding`
    (`flow_init_structurecontrol_implementation.f90`).
18. `integer, external :: irand` → `intrinsic irand` under `#ifdef __GFORTRAN__` (`saadf.F90`).

### Run-time crashes from latent bugs (benign with Intel, segfaults with gfortran)

All were found with gdb on the f34 example and the 1D test network.

19. Use of unallocated arrays or undefined pointers:
    - assigning a scalar to an unallocated array
    - `size()` of an unallocated or unassociated array (Intel returns 0, gfortran returns 1)
    - local pointers passed to `reallocP` before being nullified

    Affected files: `nearfield.f90`, `ini_transport.f90` (5 arrays), `inifcori.f90`,
    `icecover_module.f90`, `caching.f90` (thin dams, fixed weirs, dry points), `set_model_boundingbox.F90`.
20. A pointer component without `=> null()` (`netcdf_utils.F90`, `nc_att_set%atts`).
21. A component without default initialisation (`ec_typedefs.f90`, `tEcBCBlock%timecolumn`). This
    crashed reading a `function = constant` `.bc` block.
22. A gfortran zero-trip implied-do evaluates the element length of `trimexact(...)`. Fixed with
    `[character(len=strlen_netcdf) :: ...]` in `unc_write_his.F90`.

Tools I wrote to find these: `$B/tools/*.py` (character-constructor scan, trailing-comma scan, typed
implied-do rewrite, missing-`dp` insertion).

## 4. Assessment

- **Is it possible with free tools only?** Yes. Every dependency is free (apt, PyPI, GitHub). No
  Intel/oneAPI component was used, and there is no MKL: PETSc uses OpenBLAS.
- **Is it practical for an ordinary user?** No. **It is hard: an expert-level task.**
  - The official build path needs Intel compilers and Deltares containers.
  - The Conan recipes for PETSc and the Linux profiles are Intel-only.
  - The GNU compiler file is stale.
  - The current Fortran code is not gfortran-clean: about 20 compile-error classes in about 30 files.
  - About 10 latent memory bugs only crash with gfortran, and they need gdb to locate.

  Someone with strong Fortran and CMake skills needs roughly half a day to a day. A typical hydrologist
  would not get through it. `patches.diff` + `env.sh` + the shims make it repeatable in about 15 minutes.
- **Robustness risk.** Only one 2D example was verified end-to-end.
  - Patterns like 19–22 almost certainly exist in code paths I did not exercise: other structures,
    sediment, waves, 1D features, MPI-parallel runs.
  - Results were not compared against an Intel build.
  - Treat this binary as experimental until a broader test set (Deltares testbench data, which are not
    public here) has been run.
- **Run-time notes:**
  - OpenMP stays off unless `OMP_NUM_THREADS>1` is set.
  - `run_dflowfm.sh` sets `ulimit -s unlimited`, `LD_LIBRARY_PATH` and the Open MPI root flags.
  - `DFM_NP=n` runs through `mpirun`; this is untested.
  - The version string shows `Unknown` for the commit hash because no git metadata was passed to CMake.

## 5. Intel build (Intel oneAPI 2024.2, Deltares' official compilers; free of charge but proprietary)

**Result:** a `dflowfm` CLI built from the **unmodified** Deltares sources (commit 54e33a7). It needed
**zero source or CMake patches.** The GNU build in `build_ninja/` and `deps/` was left untouched.

- Binary: `/home/user/sfincs_feas/dflowfm_build/build_intel/dflowfm_cli_exe/dflowfm` (21 MB). It reports
  1.2.184 with OpenMP, MPI, PETSc, METIS, PROJ and Shapelib.
- Wrapper: `run_dflowfm_intel.sh`. It has the same interface as `run_dflowfm.sh`, sources `setvars.sh`,
  sets `LD_LIBRARY_PATH` and runs `ulimit -s unlimited`; `DFM_NP=n` uses Intel `mpirun`.
- As instructed, **no models were run.** So it is still open whether the gfortran-only crashes (section 3,
  items 19–22) and the stalled 1D case behave differently with the Intel build.

### Packages and versions

From `apt.repos.intel.com`. apt needs `-o Acquire::https::Proxy=http://127.0.0.1:41225` here.

- `intel-oneapi-compiler-fortran-2024.2` and `intel-oneapi-compiler-dpcpp-cpp-2024.2` (ifx/icx/icpx 2024.2.1)
- `intel-oneapi-mpi-devel-2021.13` (Intel MPI 2021.13)
- 739 MB download, 3.3 GB on disk; no MKL.

The C-only libraries are reused from Ubuntu apt: netCDF-C, HDF5, GDAL, PROJ, TIFF, expat, Boost,
OpenBLAS.

### Commands

```bash
curl -fsSL https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | gpg --dearmor \
  | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" \
  | sudo tee /etc/apt/sources.list.d/oneAPI.list
sudo apt-get -o Acquire::https::Proxy=http://127.0.0.1:41225 update
sudo apt-get -o Acquire::https::Proxy=http://127.0.0.1:41225 install -y --no-install-recommends \
  intel-oneapi-compiler-fortran-2024.2 intel-oneapi-compiler-dpcpp-cpp-2024.2 intel-oneapi-mpi-devel-2021.13
git -C $SRC worktree add --detach /home/user/sfincs_feas/d3d_check/Delft3D_intel 54e33a7   # clean sources
source $B/env_intel.sh     # setvars.sh, CC=mpiicx CXX=mpicxx FC="mpiifx -I$DEPS_INTEL/netcdf-fortran/include", prefix paths
# netCDF-Fortran 4.6.2 (Ubuntu's netcdf.mod is gfortran-only); its own netCDF-FortranConfig.cmake is used, no shim. 18 s
git clone --depth 1 --branch v4.6.2 https://github.com/Unidata/netcdf-fortran.git
cmake -S netcdf-fortran -B nff-build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_Fortran_COMPILER=ifx -DCMAKE_C_COMPILER=icx \
  -DCMAKE_INSTALL_PREFIX=$DEPS_INTEL/netcdf-fortran -DCMAKE_INSTALL_LIBDIR=lib -DBUILD_SHARED_LIBS=ON -DENABLE_TESTS=OFF
cmake --build nff-build --parallel 4 && cmake --install nff-build
# PETSc 3.25.3: same configure line as section 1c, but with Intel MPI; took 3 min 38 s
python3 ./configure --prefix=$DEPS_INTEL/petsc --with-cc=mpiicx --with-cxx=mpiicpx --with-fc=mpiifx <rest as in 1c>
# preCICE 3.4.1 with icx/icpx/ifx and MPI communication OFF (avoids mixing MPIs); took 2 min 55 s
cmake -S precice -B precice-build -G Ninja -DCMAKE_C_COMPILER=icx -DCMAKE_CXX_COMPILER=icpx -DCMAKE_Fortran_COMPILER=ifx \
  -DPRECICE_FEATURE_MPI_COMMUNICATION=OFF <other options as in 1d> -DCMAKE_INSTALL_PREFIX=$DEPS_INTEL/precice
# triangle with icx -> $DEPS_INTEL/triangle (as in 1e)
mkdir -p $B/build_intel/conan/generators && touch $B/build_intel/conan/generators/conan.stamp
cmake -S $DELFT3D_SRC_INTEL/src/cmake -B $B/build_intel -G Ninja -DCONFIGURATION_TYPE=dflowfm -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=$B/install_intel
cmake --build $B/build_intel --target dflowfm-cli --parallel 4      # 2 min 37 s wall, 7 min 16 s CPU
```

### What was still needed with Intel

None of these are source patches. They are in `patches_intel.diff` as new files.

- **CMake shims** (`cmake_shims_intel/`, copied from the GNU set):
  - ZLIB, HDF5 and TIFF wrappers
  - PETSc and triangle pointing to `deps_intel`
  - empty SWAN_MPI, SWAN_OMP and inja stubs

  The netCDF-Fortran shim is not needed.
- **`conan.stamp`** in the build directory.
- **`FC` with the netCDF-Fortran include dir.** The apt netCDF-C and GDAL targets add
  `-isystem /usr/include`, and Ubuntu's `libnetcdff-dev` (installed for the GNU build) puts a
  gfortran-only `netcdf.mod` there. ifx then stops with "error #7013: This module file was not generated by
  any release of this compiler". This is an artefact of keeping both toolchains on one machine; a clean
  Intel-only machine would not hit it.

Not needed with Intel: every item in section 3. That includes `-D__linux__` (Intel fpp predefines it),
the `gnu.cmake` fixes, the `flow1d_implicit` CMake file list, all the Fortran-standard fixes and all the
memory-bug fixes. The Makefile-generator slowness was avoided by using Ninja again.

### Build time

| Step | Time |
|---|---|
| Intel apt install | about 3 min |
| netCDF-Fortran | 18 s |
| PETSc | 3.6 min |
| preCICE | 2.9 min |
| D-Flow FM | 2.6 min |
| **Total machine time** | **about 13 min** |
| My elapsed time, including one wrong first configure | about 30 min |

**Assessment:** with Intel oneAPI from apt, building D-Flow FM is a routine build for anyone comfortable
with CMake. The only extra work is the missing CMake config packages and building PETSc, preCICE and
netCDF-Fortran with the same compiler. The code itself needs no changes, which confirms that Deltares
develops and tests only with Intel on Linux. The cost is a proprietary (though free-of-charge) compiler
stack of about 3.3 GB.
