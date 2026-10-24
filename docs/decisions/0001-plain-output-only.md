# ADR-0001: Plain output only, Hydraulik has no store

- Status: accepted (the plan of 2026-10-24 was approved by delegation on that day)
- Date: 2026-10-24
- Requirements: DEV §19, DEV-18.2, AGI-3.4, ECO-051

## Context

The data-output convention (ECO-051, DEV §19) gives every Nogat tool that writes
data two modes: plain files, or a versioned store. A tool without a store
"writes with `--output` and `--output-dir` as AGI-3.4 says". Hydraulik provides
no store and no file format that another project reads from a store; the
registry lists only the planned `hydraulik-job` contract. Its outputs are model
directories, engine results and a few derived files.

## Options considered

| Option | Verdict |
|---|---|
| A. Plain mode only; every writing command requires `--output-dir` (a directory) or `--output` (one file) | Chosen |
| B. A default location under `<data_dir>/hydraulik`, as a tool with a store has | Rejected: a hidden place that fills the disk with large model and result files nobody asked for, and the convention's default root belongs to stores |
| C. A `runs/<id>` directory in the working directory, as the author's spec of 2026-08-20 had | Rejected: tools write no state into the working directory (DEV-18.2) |
| D. Hydraulik's own versioned store | Rejected: no consumer needs versions of a model; Zen 11, write the rule when a second project needs it |

## Decision

Option A. `model build`, `model run`, `terrain download` take `--output-dir`
(`-o`); `rainfall build` and `results export` take `--output`. Both are required
for a real run and for `--check`, because the plan needs the target. Nothing is
written without them. The rules are those of DEV-19.3 to DEV-19.11, implemented
once in `hydraulik.output`: the targets are known before the first byte; a
duplicate name, an existing file without `--force` and a directory inside a
store of another tool are `conflict`; writing goes through
`<dir>/.hydraulik-incoming/<host>_<pid>_<token>/` and `os.replace`; the result
lists `files[]`.

## Consequences

- No `--root`, no `store init`, no marker file of Hydraulik, no `--upgrade` or
  `--plan` options (DEV-19.17 applies to stores only). `--root` is an unknown
  option and `validation_error`.
- Hydraulik still refuses to write into a store of Kartograf or IMGWTools,
  recognised by the marker file names alone (DEV-19.11, DEV-19.12).
- A model directory is plain files: `model build` writes it, `model run` reads
  it (`path_role` input) and writes the results into its own `--output-dir`.
- `config show` reports no store and no credentials (DEV-18.6).
- If Hydrograf later needs versioned model runs, that is a new ADR that
  supersedes this one.

## Errata

None.
