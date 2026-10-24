"""The translation resources of the human-readable output are complete (DEV-2.3)."""

from hydraulik.cli.messages import EN, PL, REASONS_PL, reason_text, text


def test_polish_and_english_have_the_same_keys() -> None:
    assert set(EN) == set(PL)


def test_polish_differs_from_english_where_it_is_translated() -> None:
    assert text("error.label", "pl") != text("error.label", "en")


def test_polish_reason_texts_exist_only_for_polish() -> None:
    assert reason_text("output_exists", "en") is None
    assert reason_text("output_exists", "pl") == REASONS_PL["output_exists"]
    assert reason_text("no_such_reason", "pl") is None
    assert reason_text(None, "pl") is None
