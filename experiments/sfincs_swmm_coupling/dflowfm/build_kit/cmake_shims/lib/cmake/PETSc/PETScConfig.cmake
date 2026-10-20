# Shim: PETSc (built from source with gfortran/OpenMPI) has no CMake config package.
# Provides PETSc::PETSc (shared libpetsc + C headers + Fortran .mod files in <prefix>/include).
set(PETSC_DIR "/home/user/sfincs_feas/dflowfm_build/deps/petsc" CACHE PATH "PETSc install prefix")
if(NOT TARGET PETSc::PETSc)
    find_library(PETSC_LIBRARY NAMES petsc PATHS "${PETSC_DIR}/lib" NO_DEFAULT_PATH REQUIRED)
    add_library(PETSc::PETSc SHARED IMPORTED)
    set_target_properties(PETSc::PETSc PROPERTIES
        IMPORTED_LOCATION "${PETSC_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${PETSC_DIR}/include")
endif()
