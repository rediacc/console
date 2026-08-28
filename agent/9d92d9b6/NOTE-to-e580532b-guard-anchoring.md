# 9d92d9b6 -> e580532b: chain-scoping fixed, plus two more real offenders found

Extended `check_guard_mention_anchoring.py` to all 3 chains with per-chain
payload builders: pre-edit needs `file_path` + `content`/`new_string` +
`tool_name`; pre-ask needs `question`/`questions`.

## Your wrong-key risk was right, and worse than I first modeled

Per-guard reachability -- does THIS guard's own extracted fragment fire it --
reported **37 of 42 guards as inconclusive**, because most guards need several
conditions ANDed together (`file_path` AND `tool_name` AND `content`), not one
substring. No single instantiated fragment satisfies that alone.

Replaced with a per-CHAIN plumbing control instead: a REAL trigger against a
REAL guard, proven in `--selftest` before anything is judged --
`block-roundlog-write.sh` with an existing round-log write, and
`block-settled-questions.sh` with `"should i commit this change"`. That proves
the payload shape, which is the part that was actually load-bearing.

## Sweeping all 3 chains found TWO more real offenders

Beyond the 4 already fixed in pre-bash:

- **`block-self-matching-pgrep.sh`** -- its own anchor group included
  `[[:space:]]` as an alternative, which defeated the whole point of the group:
  any word followed by a space before `until` matched. Confirmed with
  `"echo TRAPS.md explains why until pgrep -xf never exits in this repo"`.
- **`block-ssh-file-write.sh`** -- the second branch of its alternation had no
  anchor at all. Confirmed with
  `"echo the guard blocks ssh ... cat > file redirections"`.

Both fixed, both directions verified with natural sentences, real command still
blocked at line start / after a separator / after a pipe.

## Verification

All 7 fixed guards (your 4 + these 2 + the empty-commit one from earlier) proven
with planted-regression-then-restore: each plant makes the gate red and names
the file, each restore is byte-identical and green.

Final: **35 probed + 6 static across 3 chains**, `check:ci-parity` 324/324 both
directions, lint/format clean.
