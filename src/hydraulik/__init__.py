"""Hydraulik: SFINCS flood models, an EPA SWMM sewer network and their coupling.

The package builds SFINCS models from terrain, land cover and design rainfall,
runs the external SFINCS and SWMM engines and reads their results. The engines
are never bundled: they are found on the user's machine (see ``engines check``).
"""

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
