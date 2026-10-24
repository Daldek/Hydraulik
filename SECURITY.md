# Security policy

## Supported versions

Security fixes go into the latest release of Hydraulik and into the development
branch `develop`. Older releases are not patched.

## Reporting a vulnerability

Please do not report vulnerabilities in public issues or pull requests.

Use GitHub's private vulnerability reporting: open the **Security** tab of
<https://github.com/Daldek/Hydraulik>, choose **Report a vulnerability** and
describe the problem, the affected version and, if possible, how to reproduce
it. A fix is released as a patch version and credited in the CHANGELOG unless
you prefer otherwise.

## Scope

Hydraulik runs external programs (SFINCS, Kartograf, Docker) with arguments it
builds from user input, reads and writes files in directories the user names and
loads a shared library the user points to. Reports about command construction,
path handling (directories outside the requested output directory), unsafe
loading of the shared library, or the supply chain of the package are in scope.
The engines and the data tools have their own policies.
