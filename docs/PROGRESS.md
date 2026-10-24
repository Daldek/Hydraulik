# Progress

## Status

| Component | State | Note |
|---|---|---|
| Tooling: uv, gate, CI, Dependabot, repository files | done | `scripts/gate.sh`, `.github/` |
| Extraction note and plan | done | `docs/plans/2026-10-24-sfincs-swmm-*.md`; the plan awaits `Approved:` |
| Error registry (`schemas/nogat/`, `_errors.py`, `exceptions.py`) | done | copies from Nogat `cc656e7` |
| Settings, output writer | planned | plan steps 5 and 6 |
| Command catalog, CLI, generated AGENTS.md and llms.txt | planned | plan step 7 |
| SWMM, SFINCS, coupler, data adapters, model commands | planned | plan steps 8 to 13 |
| Live tests | planned | plan step 14 |
| Phase 2 items that need the author | blocked | see Open questions |

## Next

1. Plan step 5 (settings: `nogat.toml`, `HYDRAULIK_*`, `config show`), then steps
   6 to 14 of `docs/plans/2026-10-24-sfincs-swmm-integration.md`.

## Open questions

- Approve the plan `docs/plans/2026-10-24-sfincs-swmm-integration.md` (adds the
  `Approved:` line, DEV-17.4).
- Q1: is the SWMM coupling part of the product? SCOPE.md (uncommitted, author's)
  keeps full 1D sewer coupling out of the MVP.
- The author's uncommitted files overlap what this branch adds (`CLAUDE.md`,
  `docs/PROGRESS.md`, `.gitignore`): move them aside before merging.
- Skipped because they need the author: history rewrite (ADOPTION_PLAN phase 1),
  `main` as default branch, GitHub rulesets, Dependabot security updates and
  private vulnerability reporting (DEV-3.6, DEV-13.6, DEV-13.7), licence and CLA
  text, tags, pushes, committing the proof of concept from the worktree (DEV-3.5).
