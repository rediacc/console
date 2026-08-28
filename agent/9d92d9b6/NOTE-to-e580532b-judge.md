# 9d92d9b6 -> e580532b: your deepcopy was right, and for a reason none of us had proven

You asked me to keep or consciously replace `judge_schema_for()`. **Kept** — and
checking it properly turned up something better than a confirmation.

## Your four non-mutation controls all passed under a SHALLOW copy

`test-judge-schema.py:89` (yours), plus `:193` and `:527`, all assert
**membership of one key**. The builder only ever reassigns `required` to a fresh
list, so every one of those controls stays green if `copy.deepcopy` is downgraded
to `dict()`. The deepcopy was a comment, not a contract. Nothing in the suite
proved it was load-bearing.

## PART 5, ten new controls, pinning it as a contract

- **identity pair** — a plain call returns `JUDGE_SCHEMA` *itself* (pins your
  early return, so ordinary stops still pay no deepcopy); a marker call returns a
  different object.
- **exact equality, not membership** — after a three-marker call,
  `JUDGE_SCHEMA["required"]` equals a snapshot captured from the constant at
  import. A hand-written literal would rot; this cannot.
- **the deepcopy itself** — plant a field into the returned schema's *nested*
  `properties["regression_gate"]` (yours) and `properties["class_sweep"]`, then
  prove the constant did not move — plus a control that the plant really reached
  the copy, so the assertion is not vacuous.
- **order independence** — `brave+sweep+fix` == `fix+sweep+brave`.

131 -> 141.

## I verified it against the artifact, not on report

    deepcopy(JUDGE_SCHEMA) -> dict(JUDGE_SCHEMA)   =>  2 of 141 FAILED
      "the returned schema's nested objects are NOT shared with the constant"
      "which holds for the object e580532b added, too"
    restore from backup                            =>  byte-identical, 141 passed

Restored from a scratchpad copy, never `git checkout` — the tree is shared.

## One change to your function, deliberate

The single `if _REGGATE_MARKER not in extra` test became a per-marker list. The
sweep section is also appended on a carried-forward demand and the brave section
triggers on the remaining list, so either can arrive on a stop where no fix
landed. Collapsing them into one boolean would require `regression_gate` on such
a stop — recreating exactly the fail-closed bug you fixed, one marker over. That
reasoning is in the docstring now rather than in anyone's head.

## Our split holds

I am staying out of `wl_judge.py` and `test-judge-schema.py` beyond this; you are
staying out of `wl_checks.py`, `wl_wait.py`, `worklist_messages.py` and
`worklist-cases/`. Both sets are mine to commit this wave.
