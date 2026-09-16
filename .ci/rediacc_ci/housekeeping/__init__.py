"""Python ports of `.ci/scripts/housekeeping/*.sh`.

Housekeeping scripts run on repository EVENTS rather than in the gate lanes --
PR close, scheduled sweeps -- so none of them carries a `---- gate ----`
header and none is registered in `scripts/ci-runner/manifest.ts`. They are
ported for the same reason the gates are: they are live, they touch the
GitHub API, and until now none of them had a test of any kind.

As everywhere else in this workstream the bash twin remains the call site; a
port is an alternative proven equivalent against it, and the cutover is a
separate, later, explicitly tracked step.
"""

__all__: list[str] = []
