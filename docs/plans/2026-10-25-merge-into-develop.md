# Merge plan: `feature/sfincs-swmm` into `develop`

Written on 2026-10-25 as a section of `docs/PROGRESS.md`; moved here on 2026-11-10 to keep
that file within its line budget (DOC-1.7), with the state below refreshed on that day. A
record for the author, not an approved plan: the merge and every step on the main tree are
the author's (DEV-3.3).

State on 2026-11-10, read only. The main tree `~/workspace/Hydraulik` is on `develop` at
`3703913` (Initial commit: README, LICENSE, CONTRIBUTING, CONTRIBUTORS, `docs/CLA.md`),
which is also `origin/develop`. `feature/sfincs-swmm` is 50 commits ahead of that same
commit and is on `origin`, so `develop` can fast-forward to it; nothing is tagged or merged.
`origin/claude/elegant-planck-v242bb` (the SWMM coupling experiment, extraction note
section 1) is not part of this plan.

**The author's uncommitted files in the main tree and the branch**

| File | Main tree | Branch | Overlap |
|---|---|---|---|
| `.gitignore` | empty | 52 lines | path collision |
| `CLAUDE.md` | 25 lines, Polish, "Faza badawcza, brak kodu"; hydromt_sfincs adapter, container only | 114 lines, English, the working rules of the code | path collision; its statements are out of date |
| `docs/PROGRESS.md` | 50 lines, Polish: the research (2026-08-19) and brainstorming (2026-08-20) sessions, spec "waits for review" | the progress of this branch | path collision; their sessions exist nowhere on the branch |
| `docs/PRD.md`, `docs/SCOPE.md`, `docs/research/`, `docs/superpowers/` | Polish: the product requirements and the MVP scope of the urban pluvial screening of eastern Poznań (2026-10-15, the subject of the proof of concept), the feasibility report (2026-08-19) and the design spec (2026-08-20) | none | no collision; they stay as untracked files |
| `.claude/worktrees/poc-poznan-screening` | the proof of concept, branch `worktree-poc-poznan-screening` at `3703913`, uncommitted | none | see below |

Git refuses to overwrite the three colliding untracked files (tried in a scratch clone:
`git merge --ff-only` stops and names `.gitignore`, `CLAUDE.md`, `docs/PROGRESS.md`).
Procedure that worked in that clone: move those three aside, `git merge --ff-only
feature/sfincs-swmm`, and the other untracked files stay where they are. The branch's
`.gitignore` ignores `.claude/`, so the PoC worktree disappears from `git status`; it
stays registered as a worktree.

**Where the content contradicts the branch** (the author's decisions, not mine)

- Builder. `SCOPE.md` and the spec say HydroMT-SFINCS with subgrid behind an adapter
  (`hydromt_sfincs==2.0.0rc3`, GPL-3.0). The branch writes regular-grid models itself
  and has no `hydromt_sfincs` (ADR-0004, ECO-041), so no subgrid and no quadtree.
  Mountain flash floods, the main goal of the old `CLAUDE.md`, need what the branch
  lacks (the spec's pilot is the Biala Ladecka, July 1997).
- Sewer. `SCOPE.md` keeps the 1D sewer coupling out of the MVP and takes a constant
  capture capacity subtracted from the rain. The branch has the coupling, as an optional
  feature (decided 2026-10-24), and no constant capacity.
- Interface. The spec has a YAML scenario, a run directory with `metadata.json`, an
  `Engine` protocol and a Polish CLI; the branch has the Nogat command catalog, plain
  files and English machine output. Polish text exists in human output only.
- Licence and repository. The old `PROGRESS.md` says private repository without a
  licence; the old `CLAUDE.md` says MIT (2026-08-21); the branch is MIT.
- Aligned: BDOT10k, NMT and PMAXTP as inputs, buildings by raising the terrain
  (`--building-raise-m`), the Hydrolog hyetograph, `deltares/sfincs-cpu:sfincs-v2.4.1`.
- Not on the branch at all: the correction of the terrain and culvert detection, the
  division into catchments, the scenario matrix and the ensemble, passability and
  exposure, scenario cards, the QA report.

**The proof of concept** is a package with the SAME import name `hydraulik`, with
`hydromt_sfincs==2.0.0rc3` and `kartograf` as dependencies. Its paths collide with the
branch in `pyproject.toml`, `.gitignore`, `README.md` (modified there too),
`src/hydraulik/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, and a module of
the PoC is a package on the branch for `catalog`, `cli`, `data` and `terrain`.

**Recommended order**

1. Commit the PoC on its own branch from its worktree (DEV-3.5) and do not merge it into
   `develop`: two packages named `hydraulik` cannot live in one tree, and its GPL-3.0
   dependency is what the branch avoids on purpose.
2. Move `.gitignore` (empty), `CLAUDE.md` and `docs/PROGRESS.md` of the main tree aside
   and fast-forward `develop` to this branch. Then add the author's research and
   brainstorming sessions to `docs/PROGRESS.md` as an appendix (they are history), and
   commit `docs/PRD.md`, `docs/SCOPE.md`, `docs/research/` and `docs/superpowers/` in a
   docs commit, with a note in `SCOPE.md` for the contradictions above. The old
   `CLAUDE.md` is replaced by the branch's.
3. Decide for each contradiction above which side wins before more code: either the
   branch gains a subgrid adapter (the open `hydromt_sfincs` question) or `SCOPE.md` is
   changed to say what the branch is.
