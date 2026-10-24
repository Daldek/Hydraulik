"""Hydraulik: SFINCS flood models, an EPA SWMM sewer network and their coupling.

The package builds SFINCS models from terrain, land cover and design rainfall,
runs the external SFINCS and SWMM engines and reads their results. The engines
are never bundled: they are found on the user's machine (see ``engines check``).

The public API is exactly ``__all__``: the five functions that drive any command
generically, one function per command, the documents they return and the base
exception (AGI-7.1, AGI-7.2). Importing the package does no network access, writes
no file and imports no heavy dependency (AGI-7.3).
"""

__version__ = "0.1.0.dev0"

from hydraulik.catalog.dispatch import (
    check_command,
    command_schema,
    list_commands,
    run_command,
    validate_command,
)
from hydraulik.documents import (
    CommandsDocument,
    ConfigDocument,
    Document,
    GuideDocument,
    PlanDocument,
)
from hydraulik.exceptions import HydraulikError
from hydraulik.operations.config import show_config
from hydraulik.operations.meta import render_guide

__all__ = [
    "CommandsDocument",
    "ConfigDocument",
    "Document",
    "GuideDocument",
    "HydraulikError",
    "PlanDocument",
    "__version__",
    "check_command",
    "command_schema",
    "list_commands",
    "render_guide",
    "run_command",
    "show_config",
    "validate_command",
]
