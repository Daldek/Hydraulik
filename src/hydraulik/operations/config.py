"""``config show``: the settings of Hydraulik with their sources (DEV-18.6)."""

from __future__ import annotations

from hydraulik.documents import ConfigDocument
from hydraulik.settings import load_settings

__all__ = ["show_config"]


def show_config() -> ConfigDocument:
    """Return every setting with its value and source, and the file looked for.

    Returns
    -------
    ConfigDocument
        ``hydraulik-config/1``; ``credentials`` and ``store`` are empty because
        Hydraulik has neither (ADR-0001).

    Raises
    ------
    NotFoundError
        If ``NOGAT_CONFIG`` names a file that does not exist.
    InputDataError
        If the settings file is not valid TOML.
    InvalidInputError
        If a setting has an invalid value.

    Examples
    --------
    >>> show_config().to_dict()["credentials"]
    []
    """
    body = load_settings().as_document()
    return ConfigDocument(
        config_file=body["config_file"],
        settings=body["settings"],
        credentials=body["credentials"],
        store=body["store"],
    )
