# ADR-0003: Engines are found on the user's machine, never bundled, installed or pulled

- Status: accepted (the plan of 2026-10-24 was approved by delegation on that day)
- Date: 2026-10-24
- Requirements: ECO-041, DEV-13.5, DEV-6.5, ERR-5; extraction note 5

## Context

SFINCS source is GPL-3.0; its executables and the `deltares/sfincs-cpu` image are
Deltares Freeware (commercial use and research publishing allowed, no distribution,
no modification). ECO-041 keeps Hydraulik MIT and says users run SFINCS themselves.
The coupling needs more than the image has: the SFINCS shared library with the BMI,
which the experiment built from source. SWMM comes with the `pyswmm` wheel.

## Options considered

| Option | Verdict |
|---|---|
| A. Find the engines: a setting, then `PATH`, then a Docker image that is already present; report what was found and say what to do when nothing was | Chosen |
| B. Bundle the executables or the library in the package or in an image | Rejected: Deltares Freeware forbids distribution |
| C. Install or pull what is missing (`pip install`, `docker pull`) | Rejected: a download, a disk cost and an acceptance of licence terms that the user did not choose |
| D. Docker only, as the proof of concept | Rejected: the image has no BMI library, and Windows users run the executable |

## Decision

Option A (`hydraulik.engines.detect`). The order for SFINCS is `sfincs.exe`
(`HYDRAULIK_SFINCS_EXE`, never replaced by another when it names a missing file),
`sfincs` on `PATH`, then the image `sfincs.image` (default
`deltares/sfincs-cpu:sfincs-v2.4.1`, the release the author pinned) when `docker`
reports it. The version is the banner a program prints when started in an empty
directory; an image is only inspected. The library of the coupling is
`sfincs.library`, and `sfincs.qext_unit` says whether its `qext` is `m3s` (SFINCS
main since PR 355) or `ms` (v2.4.1). A missing engine is `missing_dependency` with
the install command in the hint; `engines check` reports all of them.

## Consequences

- The default image is the release without the new `qext` unit and without a
  library, so the coupling always needs a build made by the user.
- Detection spawns the programs and takes a few seconds at most; `config show`
  does not.
- CI runners have no SFINCS: tests that use it are `live` and skip without
  `HYDRAULIK_SFINCS_EXE`.
- Only Linux builds of the library were exercised (extraction note 7).

## Errata

None.
