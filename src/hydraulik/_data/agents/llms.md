# Hydraulik

> {{summary}}

Hydraulik builds SFINCS flood models from terrain, land cover and design
rainfall, runs the external SFINCS engine and reads its results, and can couple
SFINCS with an EPA SWMM sewer network. It is a CLI and a Python library; the
engines are external and never bundled.

Every command is declared once in a catalog (`hydraulik commands list --json`);
every command that writes has `--check`. Data is written only to `--output-dir`
or `--output`.

## Documentation

{{links}}
