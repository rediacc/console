"""Ported CI infrastructure scripts (`.ci/scripts/infra/`).

NOT the quality-gate package. Everything under `.ci/rediacc_ci/quality/` is a
registered CI CHECK -- it asserts something and can fail a run. Everything here
is operational tooling a workflow step runs to bring a stack up or down; its
"failure" mode is a best-effort teardown that still prints what it could not do,
not a red gate. Kept in its own subpackage rather than folded into `quality/` so
a reader does not mistake `docs/agent-reference/ci-gates.md` conventions
(anti-vacuity, MIN floors, exit 77) for properties these modules are supposed to
have -- most of them explicitly do not (`ci_stop_elite.main` always returns 0,
matching its twin's `set -e` plus universal `|| true` guards).

The bash twins are NOT deleted (W7 phase-5 decision, same as `quality/`): both
copies live side by side until a differential ledger over K distinct trees
exists, per `scripts/lib/shadow-gate.ts`.
"""

__all__: list[str] = []
