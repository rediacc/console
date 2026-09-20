#!/usr/bin/env python3
"""Entry point for the ported CLI-contract freshness gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.cli_contract`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 3). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.cli_contract` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly four fields -- `step`, `needs`, `selftest`, `lane` -- and no `emit:`, no `blocker:`, no `id:`, no `run:`, no `why:`. The batch before this one lost `emit: false` and a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only
the three workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above them still ran and still agreed.

`needs: node` IS LOAD-BEARING AFTER THE MOVE. `bind()` unions the declared needs
with `inferredNeeds(source)`, and the twin got `node` for free from its own
`npx tsx` call; this entry point runs neither, and `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:300`), so it infers nothing. Carried whole,
both sides resolve to {node}, unchanged.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`), so for a `.py` gate it decides nothing. It is true of the port regardless.

DRIVEN, on this tree, both streams captured SEPARATELY. Both run the real `npm run build:packages` and the real generator, so this is the gate's whole path and not a stubbed one. Both suppress the builder's and the generator's own stdout exactly as the twin's `>/dev/null` does, which is why the comparison of stdout is a comparison of empty streams: the verdict lives on stderr. Both
exit 0, and here the STDERR is byte-identical too, npm's own warnings included.

THE RED DRIVE IS THEREFORE THE LOAD-BEARING ONE. Against a fixture root holding a copy of `.ci`, a copy of `packages/shared/src/cli-contract/data` with a line appended to `contract.generated.ts`, and PATH shims standing in for the builder and the generator (the generator shim writes the UNPLANTED golden data, so the committed copy is genuinely the stale one), both sides exit 1 and
print identical stdout and identical stderr, naming `contract.generated.ts`.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-cli-contract.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: CLI contract
needs: node
selftest: true
lane: quality-packages
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import cli_contract

if __name__ == "__main__":
    raise SystemExit(cli_contract.main(sys.argv[1:]))
