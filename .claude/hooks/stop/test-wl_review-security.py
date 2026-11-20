#!/usr/bin/env python3
"""Controls for the per-commit review's `security` class and checklist (operator ruling 2026-11-19, worklist #bbd0f487).

    python3 .claude/hooks/stop/test-wl_review-security.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/).

WHAT EACH SECTION PINS, and what turns it red:
  1. blocking    an open `security` finding below `block_at` blocks (branch_state, push_refusals, surface_new); an open `other` low finding and a fixed `security` one do not. Red when finding_blocks drops the class test.
  2. schema      `security` is in the schema enum, validate keeps it, and the enum equals wl_reviewclass.CLASS_NAMES.
  3. classifier  the keyword table sends concrete security claims to `security` and leaves "lease token" and "auth flow" claims alone.
  4. prompt      a real run_review hands the reviewer a prompt carrying the rendered checklist, and the shipped checklist renders under its cap, with learned lines only for touched files and the cap holding under a flood of learned rows.
"""

import atexit
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import wl_review as R
import wl_reviewclass as C
import wl_reviewsec as S

_SCRATCH = pathlib.Path(tempfile.mkdtemp(prefix="review-security-"))
atexit.register(shutil.rmtree, _SCRATCH, True)
# ONE PRIVATE TMPDIR: wl_review's locks and slots live under `$TMPDIR/claude-worklist`, read at call time.
os.environ["TMPDIR"] = str(_SCRATCH)
tempfile.tempdir = str(_SCRATCH)

REAL_ROOT = R.CONSOLE_ROOT
SHA = "a" * 40
FIX = "b" * 40
ISO = "2026-11-19T12:00:00Z"


class Tally:
    count = 0
    fails = 0


def control(label, got, want):
    Tally.count += 1
    if got != want:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted %r" % (label, got, want), file=sys.stderr)


def finding(n, sev, klass, resolution="open"):
    return R.Finding(
        id="%s.%d" % (SHA[:8], n),
        severity=sev,
        file="src/app.py",
        line=3,
        anchor="in-diff",
        claim="claim number %d about the changed line." % n,
        resolution=resolution,
        klass=klass,
    )


def state_of(name, findings):
    root = _SCRATCH / name
    review = R.Review(
        sha=SHA,
        subject="s",
        branch="0101-1",
        reviewed_at=ISO,
        model="m",
        verdict="findings",
        findings=findings,
    )
    R.write_atomic(R.review_path(root, "0101-1", SHA), R.render(review))
    cfg = dict(R.DEFAULTS, model="m")
    return root, R.branch_state(root, "0101-1", cfg=cfg, repos=()), cfg


# --------------------------------------------------------------------------- 1. blocking

_root, st, _cfg = state_of("sec-low", [finding(1, "low", "security")])
control("a low security finding blocks", [f.id for _p, f in st["blocking"]], [SHA[:8] + ".1"])
control("and is not advisory", st["advisory"], [])
control("push_refusals names it", "blocking" in R.push_refusals(st, console_push=False), True)
control("no record is malformed", st["malformed"], [])

_root, st, _cfg = state_of("sec-medium", [finding(1, "medium", "security")])
control("a medium security finding blocks", len(st["blocking"]), 1)

_root, st, _cfg = state_of("other-low", [finding(1, "low", "other")])
control("CONTROL: an open other low finding does not block", st["blocking"], [])
control("CONTROL: it is advisory", len(st["advisory"]), 1)
control("CONTROL: push_refusals is empty", R.push_refusals(st, console_push=False), [])

_root, st, _cfg = state_of("other-high", [finding(1, "high", "other")])
control("CONTROL: a high finding still blocks by severity", len(st["blocking"]), 1)

fixed = "fixed %s | 1234abcd %s" % (FIX, ISO)
_root, st, _cfg = state_of("sec-fixed", [finding(1, "low", "security", fixed)])
control("CONTROL: a fixed security finding does not block", st["blocking"], [])

nab = "not-a-bug | src/app.py:3 the value is a public digest, not a secret | 1234abcd %s" % ISO
_root, st, _cfg = state_of("sec-nab", [finding(1, "low", "security", nab)])
control("CONTROL: a not-a-bug security finding does not block", st["blocking"], [])

root, _st, cfg = state_of("surface", [finding(1, "low", "security"), finding(2, "low", "other")])
lines = R.surface_new(root, "0101-1", "sess", cfg=cfg)
control(
    "surface_new counts the security finding as blocking",
    any("1 at or above high or of class security (1" in ln for ln in lines),
    True,
)
control(
    "surface_new prints the security finding", any(SHA[:8] + ".1 src" in ln for ln in lines), True
)
control(
    "CONTROL: surface_new does not print the low other finding",
    any(SHA[:8] + ".2 src" in ln for ln in lines),
    False,
)

high = R.SEV_RANK["high"]
control("finding_blocks: security low", R.finding_blocks(finding(1, "low", "security"), high), True)
control(
    "CONTROL finding_blocks: other low", R.finding_blocks(finding(1, "low", "other"), high), False
)
control(
    "CONTROL finding_blocks: unclassified legacy low",
    R.finding_blocks(finding(1, "low", ""), high),
    False,
)

# --------------------------------------------------------------------------- 2. schema

schema: Any = R.SCHEMA
enum = schema["properties"]["findings"]["items"]["properties"]["class"]["enum"]
control("security is in the schema enum", "security" in enum, True)
control("the enum equals the class table", set(enum), set(C.CLASS_NAMES))
diff = "diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n@@ -1,2 +1,4 @@\n a\n+b\n+c\n d\n"
item = {
    "severity": "low",
    "file": "src/app.py",
    "line": 2,
    "claim": "the token is printed in plaintext.",
    "class": "security",
}
_verdict, kept, _labels, dropped = R.validate(
    {"verdict": "findings", "findings": [item]}, ["src/app.py"], diff, SHA
)
control("validate keeps a security finding", ([f.klass for f in kept], dropped), (["security"], 0))

# --------------------------------------------------------------------------- 3. classifier

for claim, want in (
    ("The API key is printed in plaintext in the error message.", "security"),
    ("The repo name reaches the ssh command unquoted, a shell injection.", "security"),
    ("A path with .. is a path traversal out of the sync target.", "security"),
    ("The workflow now runs on pull_request_target with the head checked out.", "security"),
    ("The redaction misses nested fields below the parent pointer.", "security"),
    ("The guard change bypasses the gate on a read error.", "security"),
    ("A lease token is not refreshed before the deadline.", "other"),
    ("The auth flow returns a 302 instead of a 303.", "other"),
    ("The env var is not restored after the case.", "seam-not-restored"),
):
    control("classify %r" % claim[:40], C.classify(claim), want)

# --------------------------------------------------------------------------- 4. prompt and cap

checklist = S.load_checklist(REAL_ROOT)
cap = checklist["render_cap_chars"]
control("the shipped cap is at most 2500 chars", cap <= 2500, True)
base = S.render(checklist, [], ["src/app.py"])
control(
    "the shipped base renders at most 80%% of the cap (%d chars)" % len(base),
    len(base) <= cap * 0.8,
    True,
)
control(
    "the base carries every item",
    all(("- %s [" % i["id"]) in base for i in checklist["items"]),
    True,
)
control("the base carries the b940b84b3 example", "/credentials" in base, True)


def learned(n, path, kind):
    row = {
        "v": 1,
        "kind": "applied",
        "type": kind,
        "key": "%s:%04d" % (kind, n),
        "ts": "2026-11-19T12:%02d:00Z" % (n % 60),
        "file": path,
    }
    if kind == "candidate":
        row.update(
            fix=FIX,
            missed=SHA,
            fix_subject="fix(cli): redact the secret %d " % n + "x" * 80,
            area="secrets",
        )
    else:
        row.update(claim="claim %d " % n + "y" * 150)
    return row


flood = [learned(n, "src/app.py", k) for n in range(40) for k in ("candidate", "fp-note")]
heavy = S.render(checklist, flood, ["src/app.py"])
control(
    "a flood of learned rows stays under the cap (%d chars)" % len(heavy.rstrip("\n")),
    len(heavy.rstrip("\n")) <= cap,
    True,
)
control("the flood still renders a learned line", "- learned [secrets] src/app.py" in heavy, True)
roomy = S.render(dict(checklist, render_cap_chars=100000), flood, ["src/app.py"])
control(
    "render_learned caps the learned lines",
    roomy.count("- learned ["),
    int(checklist["learn"]["render_learned"]),
)
control(
    "render_fp_notes caps the notes",
    roomy.count("refuted before"),
    int(checklist["learn"]["render_fp_notes"]),
)
control(
    "CONTROL: an untouched file gets no learned line",
    "- learned [" in S.render(checklist, flood, ["other/thing.ts"]),
    False,
)
control(
    "CONTROL: an untouched file gets no fp note",
    "refuted before" in S.render(checklist, flood, ["other/thing.ts"]),
    False,
)
control(
    "a sibling in the same directory gets the learned line",
    "- learned [" in S.render(checklist, flood, ["src/other.py"]),
    True,
)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


repo = _SCRATCH / "prompt-repo"
(repo / ".claude" / "config").mkdir(parents=True)
shutil.copy(REAL_ROOT / S.CONFIG_REL, repo / S.CONFIG_REL)
git(repo, "init", "-q", "-b", "0101-1")
git(repo, "config", "user.email", "t@example.invalid")
git(repo, "config", "user.name", "t")
(repo / "src").mkdir()
(repo / "src" / "app.py").write_text("a = 1\n", encoding="utf-8")
git(repo, "add", "-A")
git(repo, "commit", "-q", "-m", "base")
(repo / "src" / "app.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
git(repo, "commit", "-q", "-am", "feat: add b")
head = git(repo, "rev-parse", "HEAD")
seen: list = []


def reviewer(prompt, _cfg, _log):
    seen.append(prompt)
    return {
        "verdict": "clean",
        "findings": [],
        "labels": {"bump": "none", "kind": [], "why": "w"},
    }, ""


logs: list = []
R.run_review(
    repo,
    "console",
    head,
    "0101-1",
    cfg=dict(R.DEFAULTS, model="m"),
    reviewer=reviewer,
    log=logs.append,
)
control("run_review called the reviewer once", len(seen), 1)
control("the prompt carries the checklist header", bool(seen) and S.HEADER in seen[0], True)
control(
    "the checklist sits before the commit message",
    bool(seen) and seen[0].index(S.HEADER) < seen[0].index("COMMIT MESSAGE:"),
    True,
)
control(
    "the prompt offers the security class",
    bool(seen) and "security (a defect from the SECURITY CHECKLIST below)" in seen[0],
    True,
)
control("no checklist failure was logged", [ln for ln in logs if "checklist unavailable" in ln], [])

(repo / S.CONFIG_REL).write_text("{", encoding="utf-8")
logs.clear()
control(
    "CONTROL: a broken checklist renders nothing",
    R.security_text(repo, ["src/app.py"], logs.append),
    "",
)
control("CONTROL: and says so on the log", any("checklist unavailable" in ln for ln in logs), True)

# --------------------------------------------------------------------------- 5. the --run path wires the learner

# `main --run` hands the committed record to wl_reviewsec.maybe_learn once the review is written: a record can only teach the checklist when the call is wired, and a learner that raises never changes the review's exit.
_calls: list = []
_real_run_review, _real_maybe_learn = R.run_review, S.maybe_learn
R.run_review = lambda *_a, **_k: None
S.maybe_learn = lambda root, **_k: _calls.append(str(root))
try:
    rc_ok = R.main(["--run", SHA, "--root", str(_SCRATCH), "--branch", "0101-1"])

    def _boom(*_a, **_k):
        raise OSError("disk gone")

    S.maybe_learn = _boom
    rc_boom = R.main(["--run", SHA, "--root", str(_SCRATCH), "--branch", "0101-1"])
finally:
    R.run_review, S.maybe_learn = _real_run_review, _real_maybe_learn
control("main --run calls the security learner once with the root", _calls, [str(_SCRATCH)])
control("main --run exits 0 after a learning pass", rc_ok, 0)
control("CONTROL: a learner that raises is logged and the exit stays 0", rc_boom, 0)

print("%d control(s), %d failed" % (Tally.count, Tally.fails))
sys.exit(1 if Tally.fails else 0)
