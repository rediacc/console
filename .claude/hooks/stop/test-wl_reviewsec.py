#!/usr/bin/env python3
"""Controls for wl_reviewsec's learner: false-positive notes, missed-fix candidates, dedupe, the cap and the cadence (operator ruling 2026-11-19, worklist #bbd0f487).

    python3 .claude/hooks/stop/test-wl_reviewsec.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/).

WHAT EACH SECTION PINS:
  1. fp-note     a security finding a person closed not-a-bug becomes one proposal; an oracle refutation, a non-security not-a-bug and an open security finding do not.
  2. candidate   in a real git fixture, a `fix` commit naming a secret that touches a file whose previous commit a model review called clean becomes a candidate; a security finding on that file in the review, a non-security fix subject, an unreviewed or skipped previous commit, and a test file do not.
  3. plan        a new key appends a proposal and an applied row; a known key appends nothing; past the cap the oldest active row is retired, and a retired key is never re-learned.
  4. learn       a write-mode pass on a fixture root writes the ledger, a second pass appends nothing, and the learned rows render for the touched file.
  5. cadence     maybe_learn runs once, stays quiet inside every_h, and runs again after it.
"""

import atexit
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import wl_review as R
import wl_reviewsec as S

_SCRATCH = pathlib.Path(tempfile.mkdtemp(prefix="reviewsec-"))
atexit.register(shutil.rmtree, _SCRATCH, True)
# ONE PRIVATE TMPDIR: wl_review's locks live under `$TMPDIR/claude-worklist`, read at call time.
os.environ["TMPDIR"] = str(_SCRATCH)
tempfile.tempdir = str(_SCRATCH)

REAL_ROOT = R.CONSOLE_ROOT
ISO = "2026-11-19T12:00:00Z"
NOW = "2026-11-19T13:00:00Z"


class Tally:
    count = 0
    fails = 0


def control(label, got, want):
    Tally.count += 1
    if got != want:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted %r" % (label, got, want), file=sys.stderr)


def finding(n, klass, resolution, path="src/app.py", sha="a" * 40):
    return R.Finding(
        id="%s.%d" % (sha[:8], n),
        severity="low",
        file=path,
        line=3,
        anchor="in-diff",
        claim="the value %d printed here is a secret." % n,
        resolution=resolution,
        klass=klass,
    )


def review(sha, findings=(), verdict=None):
    return R.Review(
        sha=sha,
        subject="s",
        branch="0101-1",
        reviewed_at=ISO,
        model="m",
        verdict=verdict or ("findings" if findings else "clean"),
        findings=list(findings),
    )


NAB = "not-a-bug | src/app.py:3 the value is a public digest, not a secret | 1234abcd %s" % ISO
ORACLE = "not-a-bug | src/app.py:3 the name is bound on line 1 of the file | oracle %s" % ISO

# --------------------------------------------------------------------------- 1. fp-note

records = [
    ("0101-1", review("a" * 40, [finding(1, "security", NAB)])),
    ("0101-1", review("c" * 40, [finding(2, "security", ORACLE, sha="c" * 40)])),
    ("0101-1", review("d" * 40, [finding(3, "other", NAB, sha="d" * 40)])),
    ("0101-1", review("e" * 40, [finding(4, "security", "open", sha="e" * 40)])),
]
fps = S.fp_proposals(records, NOW)
control("one fp-note proposal", len(fps), 1)
control("it names the finding", fps[0]["finding"] if fps else "", "0101-1/aaaaaaaa.1")
control(
    "it carries the refutation evidence",
    "public digest" in (fps[0]["evidence"] if fps else ""),
    True,
)
control(
    "CONTROL: the oracle, a non-security and an open finding add nothing",
    [p["finding"] for p in fps],
    ["0101-1/aaaaaaaa.1"],
)

# --------------------------------------------------------------------------- 2. candidate


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(repo, files, message):
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def fixture(name):
    repo = _SCRATCH / name
    (repo / ".claude" / "config").mkdir(parents=True)
    shutil.copy(REAL_ROOT / S.CONFIG_REL, repo / S.CONFIG_REL)
    git(repo, "init", "-q", "-b", "0101-1")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    return repo


repo = fixture("cand")
base = commit(
    repo,
    {"src/app.py": "a = 1\n", "src/plain.py": "p = 1\n", "tests/test_app.py": "t = 1\n"},
    "chore: base",
)
missed = commit(
    repo,
    {"src/app.py": "a = 1\nprint(secret)\n", "tests/test_app.py": "t = 2\n"},
    "feat: print the config",
)
other = commit(repo, {"src/plain.py": "p = 2\n"}, "feat: plain change")
fix = commit(
    repo,
    {"src/app.py": "a = 1\nprint(redact(secret))\n", "tests/test_app.py": "t = 3\n"},
    "fix(cli): redact the secret in the config output",
)
plainfix = commit(repo, {"src/plain.py": "p = 3\n"}, "fix(cli): off by one in the plain counter")


def cands(recs):
    return S.candidate_proposals(repo, recs, NOW, 50)


got = cands([("0101-1", review(missed))])
control(
    "one candidate from the missed review",
    [(c["file"], c["missed"], c["fix"]) for c in got],
    [("src/app.py", missed, fix)],
)
control("its area is secrets", [c["area"] for c in got], ["secrets"])
control(
    "CONTROL: the test file is never a candidate",
    any(c["file"].startswith("tests/") for c in got),
    False,
)
control(
    "CONTROL: a security finding on the file in that review means it was not missed",
    cands([("0101-1", review(missed, [finding(1, "security", "open", sha=missed)]))]),
    [],
)
control(
    "a security finding on ANOTHER file does not excuse the miss",
    len(
        cands(
            [
                (
                    "0101-1",
                    review(
                        missed, [finding(1, "security", "open", path="src/plain.py", sha=missed)]
                    ),
                )
            ]
        )
    ),
    1,
)
control("CONTROL: an unreviewed previous commit adds nothing", cands([]), [])
control(
    "CONTROL: a skipped review is not a clean call",
    cands([("0101-1", review(missed, verdict="skipped (no-review)"))]),
    [],
)
control("CONTROL: a non-security fix subject adds nothing", cands([("0101-1", review(other))]), [])
control(
    "is_security_fix: Plan-Box security",
    S.is_security_fix("fix(x): y\n\nPlan-Box: none -- security: leak"),
    True,
)
control(
    "is_security_fix: Security-Fix trailer",
    S.is_security_fix("refactor: y\n\nSecurity-Fix: S4"),
    True,
)
control(
    "CONTROL is_security_fix: feat naming a secret",
    S.is_security_fix("feat(cli): add a secret store"),
    False,
)
control("CONTROL is_security_fix: plain fix", S.is_security_fix("fix: off by one"), False)

# --------------------------------------------------------------------------- 3. plan

checklist = S.load_checklist(REAL_ROOT)
rows = S.plan([], fps + got, checklist, NOW)
control(
    "a new key appends a proposal and an applied row each",
    [r["kind"] for r in rows],
    ["proposal", "applied", "proposal", "applied"],
)
control(
    "every applied row names its reason",
    all(r.get("reason") for r in rows if r["kind"] == "applied"),
    True,
)
control("dedupe: a known key appends nothing", S.plan(rows, fps + got, checklist, NOW), [])
control(
    "dedupe: a repeated proposal in one pass is taken once",
    len(S.plan([], fps + fps, checklist, NOW)),
    2,
)
small = dict(checklist, learn=dict(checklist["learn"], max_fp_notes=2))
many = [dict(fps[0], key="fp:%d" % n, ts="2026-11-19T12:0%d:00Z" % n) for n in range(3)]
capped = S.plan([], many, small, NOW)
retired = [r for r in capped if r["kind"] == "retired"]
control("past the cap one row is retired", [r["key"] for r in retired], ["fp:0"])
control("the retirement names the cap", "cap 2" in (retired[0]["reason"] if retired else ""), True)
control("two notes stay active", sorted(r["key"] for r in S.active_rows(capped)), ["fp:1", "fp:2"])
control("CONTROL: a retired key is never re-learned", S.plan(capped, many[:1], small, NOW), [])

# --------------------------------------------------------------------------- 4. learn on a fixture root

R.write_atomic(R.review_path(repo, "0101-1", missed), R.render(review(missed)))
nab_review = review("f" * 40, [finding(1, "security", NAB, sha="f" * 40)])
R.write_atomic(R.review_path(repo, "0101-1", "f" * 40), R.render(nab_review))
logs: list = []
first = S.learn(repo, write=True, log=logs.append)
types = sorted({r["type"] for r in first["new"]})
control("the first pass learns both types", types, ["candidate", "fp-note"])
control("the first pass logs no problem", logs, [])
ledger = (repo / S.LEDGER_REL).read_text(encoding="utf-8").splitlines()
control("the ledger holds the rows written", len(ledger), len(first["new"]))
control("every ledger row parses", all(isinstance(json.loads(x), dict) for x in ledger), True)
second = S.learn(repo, write=True, log=logs.append)
control("a second pass appends nothing", second["new"], [])
text = S.security_text(repo, ["src/app.py"], log=logs.append)
control(
    "the learned line renders for the touched file", "- learned [secrets] src/app.py" in text, True
)
control("the fp note renders for the touched file", "refuted before" in text, True)
control(
    "CONTROL: an untouched file gets neither",
    ("- learned" in S.security_text(repo, ["x/y.go"])),
    False,
)
(repo / S.LEDGER_REL).write_text("\n".join([*ledger, "{not json"]) + "\n", encoding="utf-8")
_rows, problems = S.read_ledger(repo)
control("a malformed ledger line is named, not dropped silently", len(problems), 1)

# --------------------------------------------------------------------------- 5. cadence

repo2 = fixture("cadence")
commit(repo2, {"src/a.py": "a\n"}, "chore: base")
t0 = 1_800_000_000.0
every = float(checklist["learn"]["every_h"]) * 3600
control(
    "maybe_learn runs when no stamp exists",
    S.maybe_learn(repo2, now=t0, log=logs.append) is not None,
    True,
)
control(
    "CONTROL: maybe_learn stays quiet inside every_h",
    S.maybe_learn(repo2, now=t0 + every - 60, log=logs.append),
    None,
)
control(
    "maybe_learn runs again after every_h",
    S.maybe_learn(repo2, now=t0 + every + 60, log=logs.append) is not None,
    True,
)

# --------------------------------------------------------------------------- 6. the cap bounds the returned block; an unreadable fix is named

_first_lines = [S.HEADER] + [S._item_line(i) for i in checklist["items"][:2]]
_tight = sum(len(line) + 1 for line in _first_lines)
# 200 is the smallest cap load_checklist accepts, and HEADER plus its two newlines is exactly that long, so the header alone fits and the block is never empty.
for cap in (200, _tight, _tight + 1, 400, 777, 2500):
    capped_checklist = dict(checklist, render_cap_chars=cap)
    block = S.render(capped_checklist, [], ["src/app.py"])
    control("render stays within render_cap_chars=%d" % cap, len(block) <= cap, True)
control(
    "the smallest valid cap keeps the header",
    S.render(dict(checklist, render_cap_chars=200), [], ["src/app.py"]).startswith(S.HEADER),
    True,
)
_roomy_block = S.render(dict(checklist, render_cap_chars=100000), [], ["src/app.py"])
control(
    "CONTROL: a roomy cap still renders the whole checklist, every item and nothing else",
    _roomy_block == "\n".join([S.HEADER] + [S._item_line(i) for i in checklist["items"]]) + "\n\n",
    True,
)

_rv = S._review_module()
_real_git = _rv.git


def _git_without_show(repo_arg, *args):
    if args and args[0] == "show":
        return 1, ""
    return _real_git(repo_arg, *args)


skipped: list = []
_rv.git = _git_without_show
try:
    lost = S.candidate_proposals(repo, [("0101-1", review(missed))], NOW, 50, None, skipped)
finally:
    _rv.git = _real_git
control("a fix whose file list git cannot read yields no candidate", lost, [])
control("its sha is named in `skipped`", skipped, [fix[:12]])
skipped_ok: list = []
S.candidate_proposals(repo, [("0101-1", review(missed))], NOW, 50, None, skipped_ok)
control("CONTROL: readable fixes skip nothing", skipped_ok, [])

print("%d control(s), %d failed" % (Tally.count, Tally.fails))
sys.exit(1 if Tally.fails else 0)
