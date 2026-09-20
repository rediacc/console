"""`rediacc_ci.quality.command_tree`, driven directly.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-command-tree.sh` over a fixture whose `npm` and `npx` were shims, with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. The committed ledger (`.ci/shadow/w7p2-cmdtree.observations.jsonl`) recorded the same comparison over K distinct trees, one of which
exceeds the `head -40` cap, and licensed the port at K=5. The twin was retired in W7 P5 and the comparison cases went with it; what a fixture pair could say about the two implementations is in the ledger, and what remains here is the derivation the gate's anti-vacuity floor rests on plus the gate's own controls.
"""

import json

from rediacc_ci.quality import command_tree as gate


def tree(names: list[str]) -> str:
    return json.dumps({"name": "rdc", "subcommands": [{"name": n} for n in names]}, indent=2) + "\n"


def test_node_count_counts_the_whole_tree() -> None:
    assert gate.node_count_of(tree(["a", "b"])) == 3
    assert gate.node_count_of('{"name":"rdc"}') == 1
    assert gate.node_count_of("[]") == 0
    assert gate.node_count_of("not json") == 0


def test_selftest_passes() -> None:
    assert gate.selftest() == 0
