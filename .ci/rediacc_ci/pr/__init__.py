"""Ported PR-support tooling (`.ci/scripts/pr/`).

Not a quality gate: `sync_epic_block` is a maintenance script a human or
automation runs to rebuild the worklist epic block in a PR description; its
"failure" is a real error (no snapshot, git/gh failure), not a finding. The bash twin is NOT deleted (W7 phase-6 decision, same as `quality/`): both copies live side by side until a differential ledger over K distinct trees exists, per `scripts/lib/shadow-gate.ts`.
"""

__all__: list[str] = []
