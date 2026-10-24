"""The error module is generated from the vendored Nogat registry (ERR-3)."""

import importlib.util
import json
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

from hydraulik import _errors
from hydraulik.exceptions import (
    ERROR_CODES,
    CalculationError,
    CancelledError,
    ConflictError,
    EngineError,
    ForbiddenPathError,
    InputDataError,
    InvalidInputError,
    MissingDependencyError,
    NoDataError,
    NotFoundError,
    OutputError,
    SourceUnavailableError,
    TerminatedError,
    UnsupportedError,
    error_document,
)

from . import _nogat

REGISTRY = _nogat.SCHEMAS / "error_registry.json"


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_errors", _nogat.ROOT / "scripts" / "generate_errors.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_error_module_equals_the_generator_output() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    generated = _generator().render(registry)

    module = _nogat.ROOT / "src" / "hydraulik" / "_errors.py"
    assert module.read_text(encoding="utf-8") == generated


def test_error_module_carries_every_code_and_outcome_of_the_registry() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    assert [c.code for c in _errors.CODES] == [e["code"] for e in registry["errors"]]
    assert {
        o["status"]: o["exit_code"] for o in registry["outcomes"]
    } == _errors.OUTCOMES


@pytest.mark.parametrize("name", _nogat.NAMES)
def test_vendored_schema_is_a_valid_json_schema(name: str) -> None:
    Draft202012Validator.check_schema(_nogat.load(name))


def test_vendored_error_schema_lists_the_registry_codes() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    schema = _nogat.load("error-1")

    assert schema["$defs"]["code"]["enum"] == [e["code"] for e in registry["errors"]]


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        (InvalidInputError, "validation_error"),
        (NotFoundError, "not_found"),
        (ConflictError, "conflict"),
        (SourceUnavailableError, "source_unavailable"),
        (MissingDependencyError, "missing_dependency"),
        (InputDataError, "data_error"),
        (OutputError, "io_error"),
        (ForbiddenPathError, "forbidden"),
        (CalculationError, "calculation_error"),
        (EngineError, "calculation_error"),
        (CancelledError, "cancelled"),
        (TerminatedError, "terminated"),
        (NoDataError, "no_data"),
        (UnsupportedError, "unsupported"),
    ],
)
def test_default_code_of_every_exception_class_is_a_registry_code(
    cls: type[Exception], code: str
) -> None:
    exc = cls("message")

    assert exc.code == code  # type: ignore[attr-defined]
    assert exc.code in ERROR_CODES  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "exc",
    [
        InvalidInputError("bad", details={"option": "dx_m"}, reason="out_of_range"),
        InvalidInputError("bad", hint="Use a positive number."),
        NotFoundError("missing", details={"path": "dem.tif"}),
        ConflictError("exists", reason="output_exists", details={"paths": ["a"]}),
        MissingDependencyError("engine", hint="Set HYDRAULIK_SFINCS_EXE."),
        InputDataError("malformed"),
        OutputError("not writable"),
        ForbiddenPathError("outside"),
        CalculationError("no convergence"),
        EngineError("sfincs exited with 1"),
        NoDataError("empty", reason="skipped_incomplete"),
        UnsupportedError("subgrid"),
        CancelledError("declined"),
        TerminatedError("SIGTERM"),
        InvalidInputError(),
        RuntimeError("bug"),
        FileNotFoundError(2, "No such file", "dem.tif"),
        PermissionError(13, "Permission denied", "out"),
        KeyboardInterrupt(),
    ],
)
@pytest.mark.parametrize("lang", ["en", "pl"])
def test_error_documents_validate_against_the_error_schema(
    exc: BaseException, lang: str
) -> None:
    document = error_document(exc, command="model build", lang=lang)  # type: ignore[arg-type]

    _nogat.validator("error-1").validate(document)
    assert document["exit_code"] == _errors.BY_CODE[document["code"]].exit_code
