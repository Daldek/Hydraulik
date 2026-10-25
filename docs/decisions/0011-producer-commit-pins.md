# ADR-0011: The `rainfall` extra pins the producers' development heads by commit and declares their development range

- Status: accepted (delegated approval of the plan, 2026-10-24)
- Date: 2026-10-25
- Requirements: REL-5.3, REL-5.6, DEV-10.6, ECO-051, ECO-053, ADR-0010

## Context

The `rainfall` extra pinned the tags Hydrolog v0.7.0 and IMGWTools v2.1.1. Both are behind the
data-output convention: v0.7.0 has no `route network` and no `hydrolog.testing` (the contract
module of ADR-0010 skipped), and IMGWTools 3.0.0 made `method` of `fetch_pmaxtp` keyword-only.
The releases that carry these changes (Hydrolog 1.0.0, IMGWTools 3.0.0) are not tagged and the
commits are not pushed.

## Decision

- **Pin the commits** (REL-5.3): Hydrolog `0719c41825416c208f0980f6a76b14dc4e1663b7` (branch
  `feature/routing-network`, 1.0.0.dev0) and IMGWTools `7b117550103a3d8d46afc97043b90f0e93314c8b`
  (branch `feature/data-output`, 3.0.0). The pins are in `[tool.uv.sources]` and `uv.lock`.
- **Declare the range in the extra** (REL-5.6): `hydrolog>=1.0.0.dev0,<2` and
  `imgwtools>=3.0.0.dev0,<4`. A direct URL requirement cannot carry a version range, so the range
  stays in the requirement and the commit moves to `[tool.uv.sources]`; the published metadata
  then holds only the range. Hydraulik checks no producer version at run time (`engines check`
  reports the installed versions); if a check is added it reads this range with
  `SpecifierSet(range).contains(version, prereleases=True)`, not a copy of it.
- **The release pull request** narrows the ranges to `>=1.0.0,<2` and `>=3.0.0,<4`, deletes the two
  `[tool.uv.sources]` entries (or points them at the tags) and runs `uv lock` and the gate.
- **`tests/contract/test_hydrolog_testing.py` imports `hydrolog.testing`** and no longer skips; a
  pin without it fails the gate.
- **`fetch_pmaxtp` passes `method` by keyword.** The unit-test fakes of the function take `method`
  as keyword-only too, so a positional call fails in the tests as it does against the real
  function.
- **`hietogram_euler_ii.json` is re-recorded** from the real command (it now has the `inputs`
  member of the envelope).

## Consequences

- `uv lock` and `uv sync --locked` resolve the two commits only on a machine whose uv git cache
  holds them (PROGRESS, "Resolving the pins"); CI and the Docker build fail until the producers
  push the commits.
- The gate shows no skipped contract module.

## Errata

**Erratum 1 (2026-10-25):** both producers pushed their heads, so GitHub has the commits and `uv
lock`, `uv sync --locked`, CI and the Docker build resolve them without a local git cache. The
pins are Hydrolog `5fa22b35e5e1ec9076c41d0be04d2a99458f5049` (branch `feature/routing-schematic`, 1.0.0.dev0; it holds
`feature/routing-network` and the schematic) and IMGWTools `3f7de36f98f1ba40d72ab5556942567cfbc55b92` (branch
`feature/data-output`, 3.0.0). The `Consequences` item about unpushed commits no longer applies.
IMGWTools accepts a fractional PMAXTP probability in `get_precipitation` since `9291eb3`;
Hydraulik does not call it and reads the tables itself, which had read a key as its digits only
(`"0.5"` became 5 and met `"5"` of the same table). `_quantiles` now keeps the fraction (a whole
percentage stays an `int`, so `row.get(50)` finds `"50"`); the options of `rainfall build` still
take the six whole probabilities of the catalog.
