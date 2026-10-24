"""Envelopes and error documents of the CLI validate against the Nogat schemas."""

import json
from typing import Any

import pytest

from hydraulik.catalog.envelope import build_envelope, exit_code_of
from hydraulik.cli import main
from hydraulik.documents import ConfigDocument, PlanDocument

from . import _nogat


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize(
    "args",
    [
        ("config", "show", "--json"),
        ("commands", "list", "--json"),
        ("commands", "schema", "--command", "config show", "--json"),
        ("commands", "guide", "--format", "llms", "--json"),
    ],
)
def test_cli_envelope_validates_against_the_result_schema(
    capsys: pytest.CaptureFixture[str], args: tuple[str, ...]
) -> None:
    code, out, _ = _run(capsys, *args)

    _nogat.validator("result-1").validate(json.loads(out))
    assert code == 0


@pytest.mark.parametrize(
    "args",
    [
        ("commands", "schema", "--command", "x y", "--json"),
        ("commands", "guide", "--format", "pdf", "--json"),
        ("nonsense", "--json"),
    ],
)
def test_cli_error_document_validates_against_the_error_schema(
    capsys: pytest.CaptureFixture[str], args: tuple[str, ...]
) -> None:
    code, out, err = _run(capsys, *args)

    document = json.loads(err.strip().splitlines()[-1])
    _nogat.validator("error-1").validate(document)
    assert out == ""
    assert code == document["exit_code"]


def _document(status: str, items: list[dict[str, Any]] | None) -> ConfigDocument:
    document = ConfigDocument(config_file={}, settings=[])
    document.status = status
    document.items = items or []
    return document


def test_partial_envelope_carries_both_kinds_of_item() -> None:
    items = [
        {"id": "a", "status": "ok"},
        {"id": "b", "status": "failed", "code": "no_data"},
    ]

    envelope = build_envelope("terrain download", _document("partial", items))

    _nogat.validator("result-1").validate(envelope)
    assert exit_code_of(envelope["status"]) == 10


def test_failed_envelope_has_no_ok_item() -> None:
    items = [{"id": "b", "status": "failed", "code": "source_unavailable"}]

    envelope = build_envelope("terrain download", _document("failed", items))

    _nogat.validator("result-1").validate(envelope)
    assert exit_code_of(envelope["status"]) == 11


def test_envelope_without_a_result_is_valid() -> None:
    envelope = build_envelope("config show", None, status="cancelled")

    _nogat.validator("result-1").validate(envelope)
    assert exit_code_of("cancelled") == 130


def test_envelope_of_a_plan_is_marked_as_check() -> None:
    plan = PlanDocument(output_dir="out", force=False, targets=[], conflicts=[])

    envelope = build_envelope("model build", plan, check=True)

    _nogat.validator("result-1").validate(envelope)
    assert envelope["check"] is True
