"""Ported operator tools (`scripts/ops/`).

NOT gates and NOT workflow steps. Everything here is a tool a human runs by hand: no workflow, npm key, run.sh verb or gate invokes any of it, which `scripts/data/domains.json:118` records as the surveyed shape of that directory. The subpackage exists because ruling 7 (docs/ci-overhaul/04-decisions.md) was widened on 2026-09-21 to cover `scripts/ops/`, `scripts/drills/`
and `scripts/dev/`, and a ported operator tool needs an address that is neither `quality/` (a registered CI check) nor `infra/` (a workflow's stack lifecycle).

The consequence worth stating: nothing in CI runs these modules, so `check-dead-python`'s `wired` route is unavailable to them by construction. They are reached the way the bash originals were, through the `mentioned` route, and the survey entry in `scripts/data/domains.json` is what carries it.
"""

__all__: list[str] = []
