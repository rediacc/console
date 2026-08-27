## SESSION 9d92d9b6 2026-08-27T21:34:53Z

Wave 0827-1 — epic `f2757830`, PR #579. Round log under `reports/`.

## ONE COMMAND BLOCKS EVERYTHING

The operator answered "amend it" for `0081ab315`'s lost `PR-TASK` trailer.
`block-git-amend.sh` is an unconditional exit 2 with no override, so the operator
runs it via the `!` prefix. It must land while `0081ab315` is still HEAD:

    git commit --amend -F <scratchpad>/amend-msg.txt

That file differs from the current message by EXACTLY the two trailer lines
(proved by `diff`). All six commit messages are written (`m1`..`m6.txt`); the
renet fix is already committed on its own branch. Nothing else is outstanding.

## Lane: 254 gates, 252 ok, ONE red

`check:ci-pr-task-trailers` — the amend above. That is the whole list.
`check:ci-python-lint` is BLOCKED (no ruff on this host); it passes in the devbox
and in CI. `check:ci-renet` is now `slow`, so it is deferred from `--quick`; it is
still red in a whole run at host go1.26.4, which the operator authorised carrying.

## Findings, all fixed and verified

- **Four guards were reading a NAME as a TARGET.**
  `block-bash-write-to-running-script.sh:81` and
  `block-roundlog-truncate.sh:116` refused writes that merely MENTIONED a
  protected file. Both now resolve targets by position (assignment, `open(`,
  `Path(`) and by redirect at any extension, falling back to the broad scan only
  when nothing resolves. 7/7 controls each, 6 cases; suite 1555/0.
- **`check:ci-renet` never reached govulncheck.** It died at exit 127 —
  `go install` writes to `$(go env GOPATH)/bin`, on no PATH. FOUR instances
  (`format.sh`, `lint.sh`, `deadcode.sh`, `run-tests.sh`); fixed once in
  `common.sh`, which all six source. Committed as renet `3f49e09` on branch
  `0827-1` (the name MUST match the console branch or /pr-merge drops it).
  CI never saw it: `actions/setup-go` adds that directory itself.
- **Its "fast" tier was the cost of CRASHING early.** Once it ran, 40.4s — over
  the lane budget. Now `slow: true`; the oracle caught this itself.
- **Three of six routing-table entries were wrong.** shell-lint, shell-format and
  actionlint self-provision their PINNED tool, so routing them refused gates that
  work — all three verified exit 0 here with neither binary on PATH. Criterion now
  IN the file, plus 3 controls (10/0).
- **My own hook executed backticks.** Its refusal heredocs are unquoted (they
  interpolate `$NEED`), so `` `devbox remove` `` RAN — printing
  "devbox: command not found" above the refusal and eating the sentence. Same
  trap that ate the PR-TASK trailer, twice in one night. Backticks removed from
  both bodies; a `\\` continuation was also joining lines.
- **`shfmt.sh` exit 1 → 77** for an unusable toolchain. Reached on a WRONG
  premise (shfmt self-provisions); still right, since a missing tool is no verdict.

## Corrections I owe the operator

1. "CI builds its image from that Dockerfile" — FALSE. `ci-quality.yml:1631` uses
   `go-version-file: private/renet/go.mod` (`toolchain go1.25.13`). The
   `GO_VERSION` bump reaches the devbox only, and CI was never red on those vulns.
2. "The rebuild will clear `check:ci-renet`" — FALSE twice. `devbox remove && up`
   does not rebuild the image (`devbox_ensure_image` short-circuits, and re-pulls
   if deleted); and the HOST runs that gate anyway, at its own go1.26.4.
3. A probe I quoted had `$PWD` left inside the submodule, so it mounted a
   nonexistent path and returned "no go.mod". Re-run absolute, same moment:
   go1.26.4 = 9 vulns, go1.26.6 = 2 (both `Fixed in: N/A`, suppressed).

## Next action

1. Stage the 62 paths into the six themed commits (messages already written);
   they land the moment the operator's amend above clears.
2. Renet branch push + pointer bump, then whole-lane receipt → push → CI →
   `gh pr ready` → review → threads. **No merge.**
3. Do NOT switch `ci-quality.yml`'s Go step to `'stable'`: that pin is
   load-bearing (Go 1.27.0 broke golangci-lint's typecheck 2026-08-20).
