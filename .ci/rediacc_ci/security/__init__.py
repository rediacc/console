"""Ported security-quality tooling (`.ci/scripts/security/`).

`check_commands` is a REGISTERED CI gate (`check:ci-shell-commands`,
`ci-quality.yml:351`); its bash twin is NOT deleted (W7 phase-6 decision, same
as `quality/`): both copies live side by side until a differential ledger over K distinct trees exists, per `scripts/lib/shadow-gate.ts`.
"""

__all__: list[str] = []
