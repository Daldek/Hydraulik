# Contributing to Hydraulik

Thanks for your interest in improving Hydraulik! Contributions of all kinds —
bug reports, fixes, features, and documentation — are welcome.

## Getting started

```bash
# Install the project and its development tools from the lock file
uv sync --locked --all-extras

# Run the gate before opening a pull request; contributors keep their own git
# identity, so the author check is switched off
GATE_CHECK_AUTHOR=0 scripts/gate.sh
```

The gate runs `ruff format --check`, `ruff check`, `mypy`, the offline tests
with coverage and the commit-message check, in that order.

Please keep pull requests focused, follow the existing code style, and use
[Conventional Commits](https://www.conventionalcommits.org/) for commit messages
(no AI attribution trailers).

## Contributor License Agreement (CLA)

Before your first contribution can be merged, we ask you to sign our
**Contributor License Agreement**. In plain terms:

- **What it is.** A short agreement in which you confirm that you wrote (or have
  the right to submit) your contribution, and that you grant the necessary rights
  to use and redistribute it. The full text is in [`docs/CLA.md`](docs/CLA.md).

- **Why it is required.** It keeps the project's licensing on solid legal footing
  and preserves the option to relicense in the future if that ever becomes
  necessary. Without it, a single contribution with unclear rights could block
  such a change for everyone.

- **Your contribution stays MIT.** Signing the CLA does **not** change the
  licence. The project is and remains distributed under the [MIT Licence](LICENSE),
  and so is your contribution.

- **Signing is one comment — the process is manual.** There is no bot and no
  form. When your pull request is ready, add a comment on it with exactly this
  text:

  > I have read the CLA document and hereby sign it.

  When the maintainer merges your pull request, they record your signature —
  your GitHub handle, the date, and the pull-request number — in
  [`CONTRIBUTORS.md`](CONTRIBUTORS.md). You only have to sign once; it also covers
  your future contributions.

Please also tick the CLA box in the pull-request template.

## Reporting security issues

Do not file vulnerabilities as public issues; see [SECURITY.md](SECURITY.md).

## Reporting issues

Found a bug or have a feature idea? Please open an issue at
<https://github.com/Daldek/Hydraulik/issues> with as much detail as you can
(steps to reproduce, expected vs. actual behaviour, environment).
