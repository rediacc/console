"""The Python home of the `.claude` hook program.

WHAT LIVES HERE. W5 of the tooling transformation ports `.claude/hooks/**` from
bash to Python. This package is the destination: shared libraries first, then the
guards themselves, then the registry that replaces the hand-listed chains in
`.claude/settings.json`.

WHY IT IS A PACKAGE AND `.claude/hooks/stop` IS NOT. The Stop-hook modules are
reached by a `sys.path` hop into their own directory, which is why `INP001` is
ignored repo-wide in `pyproject.toml` with a note naming this phase as its expiry
date. Everything here is imported as `rediacc_hooks.<module>` with `.claude` on
`sys.path`, so the hop does not reappear.

NOTHING IN THIS PACKAGE IS WIRED UP YET. Phases 0 and 1 land the shared scanner
and the process reader plus their proofs; the guards keep sourcing the bash
originals until a later phase cuts them over one at a time. That ordering is
deliberate: the differential in `tests/` is only evidence while BOTH
implementations are present and can be fed the same input.
"""
