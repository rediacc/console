# W7 P3 batch 5: the brief, and the shadow filter corrected

Written 2026-09-07. This file exists because batch 5 is the first batch whose
selection predicate is written down. Batches 2, 3 and 4 each re-derived it from
memory, and batch 2 got it wrong in a way that only a human caught.

## Where the port stands

Do not trust the numbers below; re-run the derivation. They are recorded so a
reader can tell whether the tree has moved, not so anyone can cite them.

At the time of writing: 148 bash gate tests under `.ci/scripts/test/gates/`,
41 ported under `.ci/rediacc_ci/tests/gates/`, 75 admissible for batch 5.

Invariant 5 holds and must keep holding: all 148 bash originals are still
present. A twin is never deleted in the change that ports it. Deletion is W7 P5.

## What a batch may contain, and why each exclusion exists

A gate test is ADMISSIBLE for a batch when it is none of the following.

1. **Already ported.** Membership is read from the `BASH_TWIN` declaration in
   each `test_gate_*.py`, never from a filename guess. The declaration is what
   `test_twin_parity.py` itself uses, so the two agree by construction.

2. **A real-tree test.** Read FROM `scripts/ci-runner/gates.lock.json`, not from
   the hand-maintained W/S arrays in `run-all.sh`. This only became possible when
   W2.4 landed the `tree:` isolation declarations; before that the lock carried
   no `reads` key at all and the arrays were the only source. Batch 3 was the
   first to read the lock, and its parity driver asserts the disjointness on
   every run.

   The lock names a gate test only by id, so the twin path is `test-<name>.sh` by
   convention. The derivation ASSERTS that convention: every derived name must
   exist on disk, and it refuses rather than continuing if one does not. A
   convention that had silently drifted would otherwise subtract nothing and
   quietly admit a real-tree test into a batch.

3. **Covered by a shadow ledger.** W7 P2 ported 78 gate/twin pairs, each with a
   differential ledger under `.ci/shadow/`. A gate test whose subject is already
   under a shadow pair is excluded, because porting it would put two mechanisms
   on the same subject.

## THE CORRECTION, which is the point of this file

The batch 2 predicate mapped a ledger to the basenames it covers by reading the
paths recorded in each row's `old.cmd` and `new.cmd`. That is right for 77 of
the 78 ledgers and silently wrong for one:

    w6p2-toolchain: .ci/shadow-drivers/toolchain-old.sh
                    .ci/shadow-drivers/toolchain-new.py

`.ci/shadow-drivers/` NO LONGER EXISTS. So the filter resolved nothing for that
ledger, contributed no basenames, and reported a clean derivation. Nobody was
told. `test-toolchain.sh` had to be excluded BY HAND, and a hand exclusion is
exactly the kind of knowledge that does not survive a compaction, which is why
batch 5 nearly repeated it.

A filter that goes quiet on the one input it cannot resolve is worse than no
filter, because it reports success. The correction has two halves:

- A ledger whose recorded paths all resolve contributes its basenames, as before.
- A ledger with NO resolvable recorded path at all is NOT trusted to have
  contributed anything. Its pair slug is used as a fallback instead, and every gate
  test whose name contains that slug token is excluded. Such ledgers are PRINTED, so
  the fallback is visible rather than silent.

**CORRECTED AGAIN 2026-09-07, by the batch 5 writer, and the first correction was
too aggressive.** The rule above originally said ANY unresolvable path made a ledger
untrusted. That is wrong, because a recorded command can name a FIXTURE path that
was always relative to a temp dir and never existed in the repo. `w7p2-rbs` is
exactly that: its unresolvable token is `fx/decide.sh`, a fixture, while the same
ledger also records the perfectly resolvable `check-release-bump-skip.sh` and
`check_release_bump_skip.py`. Under the old rule those REAL contributions were
discarded, and the slug fallback then excluded nothing either, because the token
`rbs` matches no gate-test filename. Net exclusions from that ledger: ZERO, silently
-- the same shape of failure the first correction was written to fix, one level in.

Nothing was wrongly admitted on the day it was found (there is no
`test-release-bump-skip.sh` on disk), but the fallback was inert for that ledger and
would not have protected a future gate test for that subject.

The distinction that matters is ALL versus ANY: a ledger with some resolvable paths
is telling you what it covers, and a fixture path beside them does not make it a
liar. Only a ledger where NOTHING resolves has genuinely lost its subject, which is
`w6p2-toolchain` and its vanished `.ci/shadow-drivers/`.

Run today, the fallback fires on `w6p2-toolchain` and excludes
`test-toolchain.sh` on its own. That is the hand exclusion, derived.

One more trap worth keeping: the path regex must require a slash. Without it,
`python3 -m rediacc_ci.quality.python_lint` matches as the "path"
`rediacc_ci.quality.py`, which resolves to nothing and drags three healthy
ledgers into the fallback for no reason.

## The derivation

Self-contained. Run it from the repo root. It prints the counts, every
unresolvable ledger with its offending paths, what the fallback excluded, and the
admissible list.

```python
"""Derive W7 P3 batch 5's admissible set, with the shadow filter CORRECTED.

Batch 2 had to exclude test-toolchain.sh BY HAND: w6p2-toolchain's ledger records
its commands under .ci/shadow-drivers/, a directory that no longer exists, so a
filter that maps ledger -> covered basenames by looking at the recorded paths
silently saw nothing for that pair. A filter that goes quiet on the one ledger it
cannot resolve is worse than no filter, because it reports a clean derivation.

The correction has two halves:
  1. Resolvable ledgers contribute their recorded basenames, as before.
  2. A ledger with ANY unresolvable recorded path is not trusted to have
     contributed anything. Its pair slug is used instead, and every gate test
     whose stem shares that slug token is excluded. Unresolvable ledgers are
     PRINTED, so the fallback is visible rather than silent.
"""
import json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(".").resolve()
GATES = sorted(p.name for p in (ROOT/".ci/scripts/test/gates").glob("*.sh"))

# --- already ported: BASH_TWIN declarations, not filename guesses -------------
ported = set()
for p in sorted((ROOT/".ci/rediacc_ci/tests/gates").glob("test_gate_*.py")):
    m = re.search(r'^BASH_TWIN\s*=\s*["\'](.+?)["\']', p.read_text(), re.M)
    if m:
        ported.add(pathlib.PurePosixPath(m.group(1)).name)

# --- real-tree members, read FROM THE LOCK ------------------------------------
# A gate-test entry in the lock carries only its id; the twin is `test-<name>.sh`
# by convention, so the mapping is ASSERTED (every derived name must exist on
# disk) rather than assumed. A convention that has silently drifted would
# otherwise subtract nothing and let a real-tree test into the batch.
lock = json.loads((ROOT/"scripts/ci-runner/gates.lock.json").read_text())
realtree, missing = set(), []
for e in lock:
    iso = [*(e.get("mutex") or []), *(e.get("reads") or [])]
    if not any(str(c).startswith("tree:") for c in iso):
        continue
    gid = str(e.get("id", ""))
    if not gid.startswith("gate-test:"):
        continue
    name = "test-" + gid.split(":", 1)[1] + ".sh"
    if (ROOT/".ci/scripts/test/gates"/name).exists():
        realtree.add(name)
    else:
        missing.append((gid, name))
if missing:
    print("REFUSING: lock ids whose twin does not exist on disk:", missing)
    sys.exit(1)

# --- shadow coverage, corrected ----------------------------------------------
# A PATH, not a dotted module name. `python3 -m rediacc_ci.quality.python_lint`
# matches a naive \.py$ pattern as "rediacc_ci.quality.py", which then reads as
# an unresolvable path and drags a perfectly healthy ledger into the fallback.
# Requiring a slash separates the two without losing a real relative path.
PATH_RE = re.compile(r"[\w.-]*/[\w./-]*\.(?:sh|py|ts)")
covered, unresolvable = set(), {}
for led in sorted((ROOT/".ci/shadow").glob("*.observations.jsonl")):
    pair_slug = led.name.split(".")[0]
    bad = []
    resolved_here = False
    for line in led.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        for side in ("old", "new"):
            cmd = (row.get(side) or {}).get("cmd", "")
            for tok in PATH_RE.findall(cmd):
                q = tok[2:] if tok.startswith("./") else tok
                if (ROOT/q).exists():
                    covered.add(pathlib.PurePosixPath(q).name)
                    resolved_here = True
                else:
                    bad.append(tok)
    # ALL, not ANY. A ledger that resolved SOMETHING is telling you what it covers;
    # a fixture path beside those does not make it untrustworthy. Only a ledger where
    # nothing at all resolves has genuinely lost its subject. See the correction note
    # above: the ANY form discarded w7p2-rbs's real contributions and then excluded
    # nothing, which is the very failure this filter exists to prevent.
    if bad and not resolved_here:
        unresolvable[pair_slug] = sorted(set(bad))[:3]

# fallback for unresolvable ledgers: exclude by slug token
slug_excluded = set()
for pair_slug in unresolvable:
    token = re.sub(r"^w\d+p\d+-", "", pair_slug)
    for g in GATES:
        if token and token in g:
            slug_excluded.add(g)

def stem_variants(name):
    s = name[:-3]
    s = s[5:] if s.startswith("test-") else s
    return {name, "check-"+s+".sh", s+".sh"}

admissible = []
for g in GATES:
    if g in ported or g in realtree or g in slug_excluded:
        continue
    if stem_variants(g) & covered:
        continue
    admissible.append(g)

print(f"total gate tests      : {len(GATES)}")
print(f"already ported        : {len(ported)}")
print(f"real-tree (from lock) : {len(realtree)}")
print(f"shadow-covered        : {len(set(GATES) & {g for g in GATES if stem_variants(g) & covered})}")
print(f"UNRESOLVABLE LEDGERS  : {len(unresolvable)} -> {list(unresolvable)}")
for k,v in unresolvable.items():
    print(f"   {k}: {v}")
print(f"slug-excluded by that fallback: {sorted(slug_excluded)}")
print(f"ADMISSIBLE            : {len(admissible)}")
for g in admissible[:60]:
    print("   ", g)
```

## Lane facts a later batch needs, corrected 2026-09-07

`check:ci-pytest` MOVED from `quality-static` to `quality-security`. The old lane
ran no `setup-workspace`, so it had neither node nor submodules, while 23 of the
ported modules shell out to npx/tsx/npm run and 6 reference a submodule path.
Driven with node hidden from PATH exactly as that runner sees it, three of those
modules gave 24 failed / 1 passed; with node, 25 passed. They do not skip, they
fail. CI never caught it because every port is still UNTRACKED.

**Two consequences for selection.** First, a subject needing node or a submodule is
now fine, where before it was a latent CI red. Second, and specifically:
`test-renet-deadcode.sh` was dropped by batch 6 on the reasoning that its twin
skips when `private/renet` is absent and quality-static gives no submodule
checkout. That premise is now FALSE: `quality-security` checks submodules out, so
that subject is admissible again. Re-screen it rather than inheriting the drop.

## Two branches that are UNEXERCISED on this machine (batch 8)

`test_gate_profiler_report.py`'s `test_sampler_reads_a_real_containers_ceiling` takes
its DOCKER branch here, because `/sys/fs/cgroup/memory.max` is unreadable on this box.
The NATIVE branch is present and structurally faithful but has never run, and it is
the one that will be live on ubuntu-slim. The same case's `SKIP`-shaped `log_pass`
arms (no docker, or the container run failing) are carried verbatim from the twin and
are likewise unexercised. **If that port ever reds in CI and passes here, this is why**
-- look at the branch, not at the assertion.

By contrast, one thing batch 8 named as unverified is NOT: it worried the `-n 8`
interaction was inherited rather than measured for its twelve. `check_pytest.py:671`
puts `-n <jobs> --dist loadgroup` on argv with `PYTEST_JOBS_CAP = 8`, so the
`check:ci-pytest` run it drove to exit 0 IS the xdist sweep. No separate run is owed.

## Residues from batch 7 that a later batch must not rediscover

**Six `test-breakpoint-*.sh` subjects are UNPORTABLE by any agent under the standard
brief, and not on merit.** Plant-verifying them means temporarily writing under
`.ci/breakpoint/**`, which invariant 8 forbids any sweep from touching and which every
batch brief lists as must-not-touch. They stay admissible in the derivation, so each
batch will keep selecting and then dropping them. Either give one batch owner that path
explicitly, with the vendored-copy drift gate re-run afterwards, or exclude them in the
derivation with this reason. Do not silently drop them a fourth time.

**`test-scrub-sentinel-empty.sh` stays dropped** while `aws` is absent: the twin takes
its tool-absent branch, so both real cases are unreachable and no plant can turn either
side red. A port would be green-but-unproven. Admissible on a machine with `aws`.

**`test_gate_renet_deadcode.py` DELIBERATELY DIVERGES from its twin in one state.** When
`private/renet` is absent the twin exits 0 with a "skipping" echo; the port refuses
loudly. The argument, recorded in its module docstring, is that `run-all.sh` already
scores an exit-0-with-no-`PASS:`-line run as a FAILURE, so under the battery that
actually runs these files the twin's skip is red too, and only `bash <twin>` driven
directly reads it as green. **That branch is UNEXERCISED here and in `quality-security`,
because the submodule is present in both.** If a future lane ever runs without
submodules, twin and port disagree and the parity driver will say so; that is the
intended alarm, not a regression to suppress.

## What a batch 5 writer must do per subject

Unchanged from batches 2 to 4, and none of it is optional:

- Plant a defect in the REAL subject, drive BOTH sides, and confirm the port goes
  red where the twin goes red. A port that has never been seen red has not been
  shown to assert anything.
- Restore the subject and prove it byte-identical by sha256. Not "looks right".
- Declare `BASH_TWIN`. It is what makes the port discoverable to
  `test_twin_parity.py`; a port without it is invisible and silently uncompared.
- Declare an `xdist_group` if the port binds a port or mutates a module global.
  Batch 4 was the first to run under `-n 8`, so a port that was safe serially can
  flake now.
- Do NOT delete the twin (invariant 5).

## Registration

The 148 `gate-test:*` manifest entries are the largest patch fragment in the
programme. A writer authors its registration as a patch FRAGMENT and the driver
applies it in the same commit as the gate file (invariant 13). Batch registration
must stay batched, or the driver becomes the bottleneck.
