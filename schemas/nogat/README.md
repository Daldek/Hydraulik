# Copies of the Nogat standard

Verbatim copies (ERR-3, AGI-4.1) of the files below, from the standard 2.1 of the
[Nogat](https://github.com/Daldek/Nogat) repository at commit `cc656e7` (the tag
`std-2.1` does not exist yet; replace the copies by the tag when it does):

- `error_registry.json` (Nogat `standards/error_registry.json`): error codes, exit
  codes and HTTP statuses. `src/hydraulik/_errors.py` is generated from it with
  `uv run scripts/generate_errors.py`.
- `result-1.schema.json`, `error-1.schema.json`, `commands-1.schema.json` (Nogat
  `schemas/agent/`): the schemas of the result envelope, the error document and the
  command catalog. `tests/contract/` validates Hydraulik's documents against them.

Do not edit these files; copy them again when the standard changes.
