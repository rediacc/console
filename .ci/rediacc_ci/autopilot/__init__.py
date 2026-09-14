"""Python ports of `.ci/scripts/autopilot/*.sh`, the autopilot round helpers.

NOT a gate package. Everything under `.ci/rediacc_ci/quality/` is a registered
CI CHECK that asserts something and can fail a run; everything here is a step
in the autopilot workflow that PREPARES a round -- it composes the prompt the
model is handed and resolves the argument list the CLI is invoked with. Read it
with `.ci/rediacc_ci/infra/__init__.py`'s distinction in mind: an "exit 1" here
is a refusal to start a round, not a red gate, and the anti-vacuity and exit-77
conventions in `docs/agent-reference/ci-gates.md` are deliberately absent
because these modules are not supposed to have them.

The bash twins are NOT deleted (W7 phase-5 decision, same as `quality/`,
`infra/`, `release/` and `deploy/`): both copies live side by side until a
differential ledger over K distinct trees exists, per
`scripts/lib/shadow-gate.ts`. The workflow cutover from the `.sh` call sites is
a separate, later box.
"""

__all__: list[str] = []
