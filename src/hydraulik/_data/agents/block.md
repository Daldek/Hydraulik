<!-- BEGIN hydraulik -->
## Hydraulik: SFINCS flood models and a SWMM sewer coupling

Builds SFINCS regular-grid models from terrain, land cover and design rainfall,
runs the external SFINCS engine, reads the results and can couple SFINCS with SWMM.
Engines are external and never installed by the tool; settings are in `hydraulik config show`.

- Discover: `hydraulik commands list --json`, `hydraulik commands schema --command '<group> <verb>' --json`.
- Every writing command has `--check` (plan, no effects); data goes only to `--output-dir` or `--output`.
- `--json` prints one envelope `hydraulik-result/1`; errors end stderr with `hydraulik-error/1`.

{{command_lines}}

Full guide: https://raw.githubusercontent.com/Daldek/Hydraulik/main/AGENTS.md
<!-- END hydraulik -->
