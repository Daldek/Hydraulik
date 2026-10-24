"""Package data is read from the installed package, not from the checkout (DEV-5.4)."""

from importlib import resources


def test_agent_templates_ship_inside_the_package() -> None:
    folder = resources.files("hydraulik").joinpath("_data", "agents")

    for name in ("agents.md", "llms.md", "block.md"):
        assert folder.joinpath(name).read_text(encoding="utf-8").strip()


def test_domain_schemas_ship_inside_the_package() -> None:
    folder = resources.files("hydraulik").joinpath("schemas")

    assert any(item.name.endswith(".schema.json") for item in folder.iterdir())
