#!/usr/bin/env python3
"""Entry point for the ported command-tree freshness gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.command_tree`, which pytest and
the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 3). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.command_tree` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly three fields -- `step`, `needs`, `selftest` -- and NO `lane:`, no `emit:`, no `blocker:`, no `id:`, no `run:`, no `why:`. The absent `lane:` is the twin's shape, deliberately preserved: the manifest puts this gate in `quality-code`, and pinning a lane here
would be a new assertion rather than a carried one. The batch before this one lost `emit: false` and a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the three workflow-region checks (`gate-bind.ts:1724`)
while the registration assertions above them still ran and still agreed.

`needs: node` IS LOAD-BEARING AFTER THE MOVE. `bind()` unions the declared needs
with `inferredNeeds(source)`, and the twin got `node` for free from its own
`npx tsx` call; this entry point runs neither, and `inferredNeeds` strips Python
docstrings as prose (`gate-header.ts:300`), so it infers nothing. Carried whole,
both sides resolve to {node}, unchanged.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`), so for a `.py` gate it decides nothing. It is true of the port regardless.

DRIVEN, on this tree, both streams captured SEPARATELY. Both run the real `npm run build:packages` and the real exporter, both exit 0, and both write EMPTY stdout, because the twin's `>/dev/null` on each child is reproduced. The pass line differs on stderr only: the port's carries the command count (208 on this tree) so a collapsed export is visible, which is the anti-vacuity floor
`node_count` exists for.

DRIVEN RED, which is where this gate's stdout actually lives. Against a fixture root holding a copy of `.ci`, a copy of `packages/cli/scripts/command-tree.json`
with one command renamed, and PATH shims for the builder and the exporter (the
exporter shim writes the UNRENAMED tree, so the committed copy is genuinely the stale one), both sides exit 1 and print 19 stdout lines of which EIGHTEEN are byte-identical, the capped 40-line indented `diff` block included.

ONE DELIBERATE STDOUT DIVERGENCE, ON THE FAILING PATH ONLY, and it is recorded here rather than left for a future reader to call a regression. The twin's stale message spells that clause with a U+2014 EM DASH between "fails OPEN" and "they
keep passing while checking nothing"; this repository forbids em dashes in
authored text, so the port writes "fails OPEN, they keep passing while checking nothing" with a comma. The character is named rather than reproduced here, for the same reason. Everything else on that path, the header, the fix recipe and the 40-line indented diff, is byte for byte the twin's, and the clean path's stdout is empty on both sides.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-command-tree.sh` is NOT
deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- step: Command tree needs: node selftest: true ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import command_tree

if __name__ == "__main__":
    raise SystemExit(command_tree.main(sys.argv[1:]))
