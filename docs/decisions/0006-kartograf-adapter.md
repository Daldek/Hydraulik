# ADR-0006: Fetch the data through the Kartograf program and the data-output convention

- Status: accepted (delegated approval of the plan, 2026-10-24; the author reviews the
  open questions in PROGRESS)
- Date: 2026-10-25
- Requirements: ECO-051, DEV-19.1 to DEV-19.19, AGI-3.1, AGI-4.2, ADR-0001, ADR-0003

## Context

A model needs the terrain (NMT), the land cover (BDOT10k) and the soil groups (HSG),
and Kartograf is the tool of the ecosystem that downloads them. Hydraulik writes plain
files only (ADR-0001) and never bundles or imports what it does not own (ADR-0003).
On 2026-10-25 the working tree of Kartograf 0.8.0.dev0 has no plain mode: its
`output_dir` is `path_role: root`, the root of a versioned store, the plan option is
`check_updates` and a file entry is `{unit, country, file: {path, status, label,
sha256}}`. The convention of the ecosystem (ECO-051, DEV section 19) changes all three
before Kartograf 0.8.0 is tagged: `output_dir` is a directory of plain files
(`path_role: output`), the plan is `--check`, a file entry is `{path, size_bytes,
sha256, status}` and `skipped[]` is `{id, reason, message}`.

## Options considered

| Option | Verdict |
|---|---|
| A. Call `kartograf ... --output-dir DIR --json` as a program, written against the convention, discovering what the installed one offers from `kartograf commands schema` and refusing clearly when `output_dir` is not a plain target | Chosen |
| B. Call today's Kartograf with its store root and read the store layout (what the proof of concept did) | Rejected: a store is hard-linked versions with sidecars; Hydraulik would depend on the layout of another tool and write a store where ADR-0001 says it has none |
| C. Import Kartograf as a library | Rejected: its dependencies (GDAL stack, the network clients) would become Hydraulik's, and the library has the same store semantics as the program |
| D. Download from GUGiK and ISRIC in Hydraulik | Rejected: duplicates Kartograf; the README sends the user to Kartograf for data |

## Decision

Option A (`hydraulik.data.kartograf`, `hydraulik.operations.terrain`, command
`terrain download`).

- **Discovery.** The options come from `kartograf commands schema --command "<group>
  <verb>" --json` (`result.commands[0].options[]`: `name`, `path_role`, `enum`), the flag
  of an option is its name with dashes (AGI-3.1), and an argument is built only from an
  option that the schema declares, in the form `--flag=value` (a bounding box may begin
  with a minus). A value outside a declared `enum` is refused as well.
- **Refusal.** A Kartograf whose `output_dir` is not `path_role: output` is
  `missing_dependency`, reason `engine_incompatible`, and nothing is fetched: with such a
  Kartograf `--output-dir` would write a store into the directory of the user. The same
  reason covers a Kartograf without `commands schema`, `check` or `force` (the options
  the call needs). `engines check` reports it with the same text (`find_kartograf`
  looks at the schema), so `engines check --require 'terrain download'` and the command
  agree.
- **Products.** `elevation` is `elevation download --product nmt --country pl --cutout
  --horizontal-crs EPSG:2180 --vertical-crs EVRF2007` (one GeoTIFF with a CRS; sheets
  are ASC files without one), `landcover` is `landcover download --product bdot10k`,
  `soil` is `soil hsg --depth 0-5cm` (uint8, 1 A to 4 D, 0 no data). Each goes to its own
  sub-directory of `--output-dir`, because the names of two products can collide
  (DEV-19.5).
- **Preflight.** Before the first byte the plan (`--check`) of every product is read, and
  a `conflict` in any of them fails the whole call with `details.paths` listing all of
  them (DEV-19.6). The plan has no fixed field names, so every entry anywhere in it with
  an `action` of `write`, `replace` or `conflict` and a `path` is a target; a plan
  without such entries lists nothing and the products' own preflights remain.
- **Outcome.** Kartograf's exit codes 0, 10 and 11 are outcomes and give the
  `files[]`, `skipped[]`, `items[]` and notices of its envelope; the unit ids get the
  product in front. A product that raises (an error document on stderr) is one failed
  item with its registry code, rebuilt as the same exception class. The result is `ok`,
  `partial` (some unit failed after another succeeded) or `failed` (nothing succeeded
  of several products); a single product that fails raises its error.
- **Terms.** Plain files carry no sidecar, so the result names provider, licence and
  attribution of what was fetched (`sources[]`, values from Kartograf's registry:
  GUGiK `PL-PGiK-40a`, ISRIC SoilGrids `CC-BY-4.0`) and a notice asks to print them.
- **Process.** Kartograf runs with `kartograf.timeout_s` per call, its stderr goes to the
  log at INFO, SIGINT and SIGTERM stop it (it removes its staging, DEV-19.7).

## Consequences

- Nothing can be fetched with the real Kartograf until it implements the convention:
  tests use a fake program that answers by the convention
  (`tests/fake_kartograf_program.py`), and the live test skips itself with the reason
  (`tests/integration/test_terrain_live.py`). The first run on the real tool may find
  differences in the field names of the plan and of the items; the adapter reads what
  DEV-19.19 and AGI-4.2 fix and nothing else.
- A Kartograf that adds a store mode keeps working: only `--output-dir` is used.
- Only Poland is covered: the BDOT10k package and the NMT cutout are GUGiK data.

## Errata

None.
