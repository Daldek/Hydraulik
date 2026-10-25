# ADR-0010: Test against the testing modules of the producers where they build what Hydraulik reads

- Status: accepted (delegated approval of the plan, 2026-10-24)
- Date: 2026-10-25
- Requirements: DEV-10.6, ADR-0006, ADR-0009

## Context

DEV-10.6: a producer ships a public `<package>.testing` that builds small valid instances of
every format another project reads from its files, and a consumer's contract tests use it, at
the producer version the consumer pins, instead of hand-written copies of the formats. Hydraulik
read three producers through hand-made test data: Hydrolog (the tables of `route network
--output-dir`, the `precip hietogram` envelope), Kartograf (the program, through a fake
`kartograf` script) and IMGWTools (`imgwtools.fetch_pmaxtp` replaced by a fake, and a
`pmaxtp_fetch.json`).

## Decision

- **Hydrolog: use `hydrolog.testing`** (Hydrolog ADR-0011) in `tests/contract/test_hydrolog_testing.py`.
  The case it builds (`build_network_fixture`) equals, byte for byte, the recorded fixture of
  `tests/fixtures/hydrolog` (network, inflows and the five tables), every built table is read by
  `read_hydrograph` with the peak, time and volume of the record, a routed network built from the
  builders keeps its volume, and a built `precip hietogram` envelope gives the rain of the recorded
  one and goes through `rainfall build --hietogram`. The recorded fixtures stay: they prove what
  one Hydrolog commit wrote; the builders prove what the pinned Hydrolog writes.
- **The module imports `hydrolog.testing` and does not skip.** It skipped while the `rainfall`
  extra pinned Hydrolog v0.7.0; ADR-0011 moved the pin to the commit of `feature/routing-network`,
  which has the module, so a pin without it fails the gate.
- **The hand-written hydrograph tables of the SWMM and coupling tests stay.** They are inputs in
  Hydraulik's own table format and several are wrong on purpose for Hydrolog (a negative discharge,
  a step of 0.05 min, a table that starts at 1 min); Hydrolog's builders refuse them, so they
  cannot become builders.
- **The Kartograf fake stays.** `tests/fake_kartograf_program.py` models the protocol of the program
  (`commands schema`, `--check` plans, error documents and exit codes, `files[]`), not the content of
  a store. `kartograf.testing` builds versioned stores, sidecars and project files, which Hydraulik
  never reads (ADR-0001, ADR-0006) and cannot import (Kartograf is not a dependency).
- **The IMGWTools fake and `pmaxtp_fetch.json` stay.** `fetch_pmaxtp` is faked at the function
  boundary of a network call, and `imgwtools.testing` builds a fixture store from recorded HTTP
  answers (`build_fixture_store`); it has no builder of the `imgw-result/1` envelope of `imgw pmaxtp
  fetch`, which is what `pmaxtp_fetch.json` is. Its `imgw-pmaxtp/1` example is the store document, a
  different layout. Switch when IMGWTools adds a builder for that envelope (a `request` issue, DEV-17.5).

## Consequences

- A format change in Hydrolog breaks `test_hydrolog_testing.py` when the pin moves.
