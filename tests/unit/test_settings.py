"""Resolution of the settings: precedence, sources and validation (DEV-18.1)."""

from pathlib import Path

import pytest

from hydraulik.exceptions import InputDataError, InvalidInputError, NotFoundError
from hydraulik.settings import SETTINGS, config_file_path, load_settings


def _file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "nogat.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_apply_without_file_option_or_environment(tmp_path: Path) -> None:
    settings = load_settings(environ={}, config_file=tmp_path / "absent.toml")

    assert settings.value("lang") == "pl"
    assert settings.source("lang") == "default"
    assert settings.value("sfincs.exe") is None
    assert settings.config_file_exists is False


def test_precedence_runs_option_environment_file_default(tmp_path: Path) -> None:
    path = _file(tmp_path, '[hydraulik]\nlog_level = "error"\n')
    env = {"HYDRAULIK_LOG_LEVEL": "info"}

    from_file = load_settings(environ={}, config_file=path)
    from_env = load_settings(environ=env, config_file=path)
    from_option = load_settings({"log_level": "debug"}, environ=env, config_file=path)

    assert (from_file.value("log_level"), from_file.source("log_level")) == (
        "error",
        "file:[hydraulik]",
    )
    assert (from_env.value("log_level"), from_env.source("log_level")) == (
        "info",
        "env:HYDRAULIK_LOG_LEVEL",
    )
    assert (from_option.value("log_level"), from_option.source("log_level")) == (
        "debug",
        "option",
    )


def test_shared_key_reads_the_nogat_variable_and_table_after_its_own(
    tmp_path: Path,
) -> None:
    path = _file(tmp_path, '[nogat]\nlang = "en"\n')

    shared_file = load_settings(environ={}, config_file=path)
    shared_env = load_settings(environ={"NOGAT_LANG": "en"}, config_file=tmp_path)
    own_env = load_settings(
        environ={"NOGAT_LANG": "en", "HYDRAULIK_LANG": "pl"}, config_file=path
    )

    assert shared_file.source("lang") == "file:[nogat]"
    assert shared_env.source("lang") == "env:NOGAT_LANG"
    assert (own_env.value("lang"), own_env.source("lang")) == (
        "pl",
        "env:HYDRAULIK_LANG",
    )


def test_a_key_that_is_not_shared_ignores_the_nogat_table_and_variable(
    tmp_path: Path,
) -> None:
    path = _file(tmp_path, '[nogat]\nlog_level = "debug"\n')

    settings = load_settings(environ={"NOGAT_LOG_LEVEL": "debug"}, config_file=path)

    assert settings.source("log_level") == "default"


def test_empty_environment_variable_counts_as_unset(tmp_path: Path) -> None:
    settings = load_settings(
        environ={"HYDRAULIK_LANG": ""}, config_file=tmp_path / "absent.toml"
    )

    assert settings.source("lang") == "default"


def test_nested_tables_and_dotted_keys_are_the_same_setting(tmp_path: Path) -> None:
    nested = _file(tmp_path, '[hydraulik.sfincs]\nexe = "/opt/sfincs"\n')
    dotted = tmp_path / "dotted.toml"
    dotted.write_text('[hydraulik]\nsfincs.exe = "/opt/sfincs"\n', encoding="utf-8")

    assert load_settings(environ={}, config_file=nested).value("sfincs.exe") == (
        "/opt/sfincs"
    )
    assert load_settings(environ={}, config_file=dotted).value("sfincs.exe") == (
        "/opt/sfincs"
    )


def test_unknown_key_in_the_file_names_the_key_and_the_allowed_ones(
    tmp_path: Path,
) -> None:
    path = _file(tmp_path, "[hydraulik]\nsfincs_exe = 1\n")

    with pytest.raises(InvalidInputError) as caught:
        load_settings(environ={}, config_file=path)

    assert caught.value.details["option"] == "sfincs_exe"
    assert caught.value.details["reason"] == "unknown_setting"
    assert "sfincs.exe" in caught.value.details["allowed"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("lang", "de"),
        ("sfincs.threads", "0"),
        ("sfincs.threads", "two"),
        ("sfincs.timeout_s", "-5"),
        ("sfincs.qext_unit", "m2s"),
    ],
)
def test_invalid_environment_value_names_the_setting(key: str, value: str) -> None:
    spec = next(s for s in SETTINGS if s.key == key)

    with pytest.raises(InvalidInputError) as caught:
        load_settings(environ={spec.env[0]: value}, config_file=Path("absent.toml"))

    assert caught.value.details["option"] == key
    assert caught.value.details["reason"] == "invalid_setting"


def test_numbers_are_converted_to_their_type(tmp_path: Path) -> None:
    settings = load_settings(
        environ={"HYDRAULIK_SFINCS_THREADS": "4", "HYDRAULIK_SFINCS_TIMEOUT_S": "90.5"},
        config_file=tmp_path / "absent.toml",
    )

    assert settings.value("sfincs.threads") == 4
    assert settings.value("sfincs.timeout_s") == 90.5


def test_invalid_toml_is_a_data_error_with_the_path(tmp_path: Path) -> None:
    path = _file(tmp_path, "[hydraulik\n")

    with pytest.raises(InputDataError) as caught:
        load_settings(environ={}, config_file=path)

    assert caught.value.details["path"] == str(path)
    assert caught.value.details["reason"] == "invalid_settings_file"


def test_nogat_config_pointing_to_a_missing_file_is_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "gone.toml"

    with pytest.raises(NotFoundError) as caught:
        load_settings(environ={"NOGAT_CONFIG": str(missing)})

    assert caught.value.details["path"] == str(missing)


def test_nogat_config_selects_the_file(tmp_path: Path) -> None:
    path = _file(tmp_path, '[hydraulik]\nlang = "en"\n')

    settings = load_settings(environ={"NOGAT_CONFIG": str(path)})

    assert settings.value("lang") == "en"
    assert settings.config_file_source == "NOGAT_CONFIG"


def test_default_settings_file_is_nogat_toml_in_the_user_configuration_folder() -> None:
    path, source = config_file_path({})

    assert (path.parent.name, path.name, source) == ("nogat", "nogat.toml", "default")


def test_unknown_key_in_a_lookup_is_refused(tmp_path: Path) -> None:
    settings = load_settings(environ={}, config_file=tmp_path / "absent.toml")

    with pytest.raises(InvalidInputError):
        settings.value("sfincs.exee")


def test_document_lists_every_setting_with_source_and_environment_names(
    tmp_path: Path,
) -> None:
    document = load_settings(
        environ={"HYDRAULIK_SFINCS_EXE": "/opt/sfincs"},
        config_file=tmp_path / "absent.toml",
    ).as_document()

    by_key = {item["key"]: item for item in document["settings"]}
    assert [item["key"] for item in document["settings"]] == [s.key for s in SETTINGS]
    assert by_key["sfincs.exe"]["value"] == "/opt/sfincs"
    assert by_key["sfincs.exe"]["source"] == "env:HYDRAULIK_SFINCS_EXE"
    assert by_key["lang"]["env"] == ["HYDRAULIK_LANG", "NOGAT_LANG"]
    assert document["credentials"] == []
    assert document["store"] is None


def test_every_variable_is_listed_in_env_example() -> None:
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text(
        encoding="utf-8"
    )

    for spec in SETTINGS:
        for name in spec.env:
            assert f"\n{name}=" in text
