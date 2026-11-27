# Offline pull request checks

The workflow installs the hash-locked development environment on Windows
and Linux, runs Ruff and mypy, runs the synthetic tests, builds a wheel, and
validates the implementation plan. Ruff covers product code, tests, and the
maintained fixture scripts. The frozen SRS build and legacy planning scripts
retain their existing formatting.
Git attributes give the frozen SRS records their original line endings on
both runners so the preservation validator can compare raw file hashes.

The test fixture rejects external DNS resolution and socket connections from
the pytest process. Loopback remains available for the OAuth callback fixture.
MCP subprocess tests launch the synthetic server and use local stdio. The
pytest fixture is a guard for accidental traffic in the test process.

The PR workflow runs with read-only repository permissions and checkout does
not persist Git credentials. YouTube and OAuth credentials are unnecessary.
The Linux secret job checks the tracked history and working tree with a
version-pinned, checksum-verified Gitleaks release and redacts findings.
The three entries in `.gitleaksignore` identify historical fixed test values
in OAuth mock responses and a redaction test. The exceptions apply to those
exact fingerprints. The history and working tree scans still run and fail on
new findings.

After J2-06 lands, add Jeswin's knowledge validator to the workflow. Until
then the implementation plan check validates planning records only.

## Review configuration

The PR template records exact test and review evidence. The CODEOWNERS rule
routes teammate work to Aadyant. Aadyant records a dated human owner review of
his own changes after AI review, following the [team policy](../implementation/REVIEW_POLICY.md).
CODEOWNERS cannot turn owner review into independent GitHub approval.
Verify repository protections and required checks in GitHub with Aadyant
before relying on enforcement. Hosted runner results and repository settings
are separate evidence from local checks.
