# Self-improvement log

One line per landed enhancement, newest last. The point of the file is that the
NEXT session picks a different angle instead of re-deriving the same insight, and
that the operator sees the shape of the improvement over time rather than one
commit at a time.

Angles: DUPLICATION, VACUITY, BLIND SPOT, INSTRUMENT HONESTY, ERGONOMICS,
DELETION, SPEED, DOCUMENTATION DEBT.

    YYYY-MM-DD | ANGLE | <commit> | <what changed and what it now prevents>

2026-09-01 | INSTRUMENT HONESTY | b95507436 | wl_classsweep validates the command it orders a session to run; a nonexistent path or a truncated command is dropped (never the demand) instead of sending the session after grep's error line, which one stop read as a finding.
2026-09-01 | INSTRUMENT HONESTY | 3c7943c29 | the same validator now checks what a proposed sweep command DOES, not only whether it runs: destructive verbs, the nine git subcommands that discard work, find -delete, sed -i and > redirection are refused, so the stop hook cannot order a session to damage the tree.
