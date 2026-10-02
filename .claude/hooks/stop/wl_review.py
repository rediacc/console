#!/usr/bin/env python3
"""Per-commit review: every commit on the live branch gets a haiku review recorded at `agent/reviews/<branch>/<sha40>.md` (agent/plans/PLAN-per-commit-review.md).

WHY. The operator ruled on 2026-10-02 that a per-commit haiku review through a Claude Code hook replaces the PR-level Claude review: the Claude GitHub app is uninstalled, and a whole PR is too big to review in one pass. One commit is a diff a small model can read end to end.

THE FLOW. A `git commit` (or rebase, cherry-pick, merge, revert, pull) in any Bash call fires the post-bash member `.claude/hooks/post-bash/review_commit.py`. It asks `uncovered()` which commits of the branch have no review, takes the per-sha lock for up to `max_spawn_per_trigger` of them and starts this file as a DETACHED child for each (`--run`). The child reads the
commit from the object store, calls haiku with a JSON schema and no tools, validates every finding's anchor against the diff and writes the review file atomically. It never runs `git add`: the index is shared, and the file rides the session's next commit or `worklist.py --review-commit`.

NOTHING HERE DEPENDS ON THE STOP HOOK, which the operator disabled on 2026-10-02. Three readers enforce and surface the record without it: the pre-bash guard `block_push_with_unrecorded_reviews` refuses a push while a commit is unreviewed, a review is unrecorded or a `block_at` finding is open; the post-bash member reports each finished review on the session's next Bash call; and SessionStart prints `session_start_line()`. The Stop hook's `commit-review` keys
read the same `branch_state()` when it is switched back on.

SEALED. Every knob is in `.ci/config/commit-review.json`; the only environment reads are the temp directory and the two recursion guards, so a stray export cannot retune a review.

THE CHILD RUNS NO HOOKS OF THIS REPO. `claude -p` fires the project's hooks when its cwd is inside the repo, so the call runs in `<TMP>/claude-worklist/.review` with `STOPHOOK_CHILD=1` (the Stop hook's own recursion guard) and `COMMIT_REVIEW_CHILD=1` (this feature's), and `--tools ""`, exactly as `wl_judge` does.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
CONSOLE_ROOT = HERE.parents[2]
CONFIG_REL = ".ci/config/commit-review.json"
REVIEWS_REL = "agent/reviews"
SELF = HERE / "wl_review.py"
WORKLIST = HERE / "worklist.py"

DEFAULTS = {
    "model": "claude-haiku-4-5-20251001",
    "budget_usd": 0.3,
    "timeout_s": 240,
    "max_concurrent": 2,
    "slot_wait_s": 900,
    "max_spawn_per_trigger": 5,
    "max_uncovered_scan": 20,
    "diff_cap_bytes": 80000,
    "block_at": "high",
    "review_epoch": "",
    "retention_days": 14,
}

SEVERITIES = ("high", "medium", "low")
SEV_RANK = {"high": 3, "medium": 2, "low": 1}
BUMPS = ("none", "patch", "minor", "major")
KINDS = ("bug", "feature", "docs", "ci")
TRIGGER_SUBS = frozenset({"commit", "rebase", "cherry-pick", "merge", "revert", "pull", "am"})
ANCHOR_SLACK = 8
CLAIM_MAX = 600
WHY_MAX = 200
MAX_FINDINGS = 8
# A reviewer that failed this many times no longer blocks a push: the failure is recorded in the file and named in every surfacing, but a model outage is a broken environment, not a verdict, and the push guard fails open on those.
FAIL_OPEN_AFTER = 2
SPAWN_GRACE_S = 15

SHA40 = re.compile(r"^[0-9a-f]{40}$")
ISOZ = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
ME8 = r"[0-9a-f]{8}"
RESOLUTION_RES = (
    ("open", re.compile(r"^open$")),
    ("fixed", re.compile(r"^fixed ([0-9a-f]{40}) \| (%s) (%s)$" % (ME8, ISOZ))),
    ("not-a-bug", re.compile(r"^not-a-bug \| (.{20,}) \| (%s) (%s)$" % (ME8, ISOZ))),
    ("deferred", re.compile(r"^deferred #([0-9a-f]{6,16}) \| (%s) (%s)$" % (ME8, ISOZ))),
)
VERDICT_RE = re.compile(
    r"^(findings|clean|skipped \((?:gitlink-only|no-review)\)|failed \([^()\n]{1,200}\))$"
)
FINDING_HEAD = re.compile(r"^### ([0-9a-f]{8})\.(\d+) \[(high|medium|low)\] (\S.*):(\d+)$")
HEADER_KEYS = (
    "Commit",
    "Repo",
    "Branch",
    "Parent",
    "Patch-Id",
    "Reviewed-At",
    "Model",
    "Diff",
    "Unreviewed",
    "Verdict",
    "Attempt",
    "Labels",
    "Dropped",
    "Body-Sig",
)
BRANCH_SLUG = re.compile(r"[^A-Za-z0-9._-]+")

PROMPT = """You review ONE git commit of the rediacc console monorepo. You see only its message and diff. Report defects this commit INTRODUCES or EXPOSES, nothing else.
Severity:
high = on the changed path it will produce wrong behaviour, data loss, a security hole, a broken build or a CI gate that can no longer fail;
medium = a real bug only on an edge path, changed behaviour with no test, or a comment that states the wrong behaviour;
low = anything else worth a line.
Style and naming are never above low, and neither is anything in prose (plans, notes, generated ledgers, Markdown). Do not speculate about code you cannot see. Every finding names a file from this diff and a line number in the NEW version of that file. The claim must say what goes wrong and when, in one sentence a reviewer can check. If the commit only moves or renames text, answer clean. Also classify the commit for release labels: bump none (no user-facing change), patch, minor (new capability), major (only recommend); kind from bug, feature, docs, ci.

COMMIT MESSAGE:
%(message)s

STAT:
%(stat)s

DIFF (may be truncated; truncated files: %(truncated)s):
%(diff)s
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "findings", "labels"],
    "properties": {
        "verdict": {"type": "string", "enum": ["findings", "clean"]},
        "findings": {
            "type": "array",
            "maxItems": MAX_FINDINGS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "file", "line", "claim"],
                "properties": {
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "file": {"type": "string"},
                    "line": {"type": "integer", "minimum": 1},
                    "claim": {"type": "string", "maxLength": CLAIM_MAX},
                },
            },
        },
        "labels": {
            "type": "object",
            "additionalProperties": False,
            "required": ["bump", "kind", "why"],
            "properties": {
                "bump": {"type": "string", "enum": list(BUMPS)},
                "kind": {"type": "array", "items": {"type": "string", "enum": list(KINDS)}},
                "why": {"type": "string", "maxLength": WHY_MAX},
            },
        },
    },
}


# --------------------------------------------------------------------------- config and paths


def load_config(root=None):
    cfg = dict(DEFAULTS)
    path = pathlib.Path(root or CONSOLE_ROOT) / CONFIG_REL
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    if isinstance(doc, dict):
        cfg.update({k: v for k, v in doc.items() if k in DEFAULTS})
    if cfg.get("block_at") not in SEV_RANK:
        cfg["block_at"] = "high"
    return cfg


def state_dir():
    """`<TMP>/claude-worklist/reviews`: locks, slots, logs and the per-session surfacing marks. The same temp root the worklist uses (wl_core.worklist_for)."""
    d = (
        pathlib.Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
        / "claude-worklist"
        / "reviews"
    )
    for sub in ("locks", "slots", "logs", "seen"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def branch_slug(branch):
    return BRANCH_SLUG.sub("-", (branch or "").strip()).strip("-.")


def branch_dir(root, branch):
    return pathlib.Path(root) / REVIEWS_REL / branch_slug(branch)


def review_path(root, branch, sha):
    return branch_dir(root, branch) / ("%s.md" % sha)


def git(repo, *args, stdin=None, timeout=30):
    """(rc, stdout) of one git call; rc 127 when git could not run."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return done.returncode, done.stdout


def git_out(repo, *args, **kw):
    rc, out = git(repo, *args, **kw)
    return out.strip() if rc == 0 else ""


def repo_label(console_root, repo):
    """`console` for the console itself, else the path relative to it (`private/account`)."""
    console_root = pathlib.Path(os.path.realpath(console_root))
    repo = pathlib.Path(os.path.realpath(repo))
    if repo == console_root:
        return "console"
    try:
        return str(repo.relative_to(console_root))
    except ValueError:
        return str(repo)


def repo_from_label(console_root, label):
    if label in ("", "console"):
        return pathlib.Path(console_root)
    path = pathlib.Path(label)
    return path if path.is_absolute() else pathlib.Path(console_root) / path


def current_branch(repo):
    """The branch HEAD is on; during a rebase the branch being rebased; "" on any other detached HEAD."""
    name = git_out(repo, "symbolic-ref", "--short", "-q", "HEAD")
    if name:
        return name
    gitdir = git_out(repo, "rev-parse", "--absolute-git-dir")
    for sub in ("rebase-merge", "rebase-apply"):
        head = pathlib.Path(gitdir or "/nonexistent") / sub / "head-name"
        with contextlib.suppress(OSError):
            ref = head.read_text(encoding="utf-8").strip()
            if ref.startswith("refs/heads/"):
                return ref[len("refs/heads/") :]
    return ""


def now_iso(now=None):
    stamp = datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.UTC)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text):
    try:
        return datetime.datetime.fromisoformat(str(text))
    except ValueError:
        return None


# --------------------------------------------------------------------------- the file format (section 2)


@dataclasses.dataclass
class Finding:
    id: str
    severity: str
    file: str
    line: int
    anchor: str
    claim: str
    resolution: str = "open"

    def resolution_kind(self):
        for kind, rx in RESOLUTION_RES:
            if rx.match(self.resolution):
                return kind
        return ""

    def deferred_item(self):
        m = RESOLUTION_RES[3][1].match(self.resolution)
        return m.group(1) if m else ""


@dataclasses.dataclass
class Review:
    sha: str
    subject: str = ""
    repo: str = "console"
    branch: str = ""
    parent: str = "(root)"
    patch_id: str = "(none)"
    reviewed_at: str = ""
    model: str = ""
    diff_bytes: int = 0
    diff_files: int = 0
    truncated: bool = False
    unreviewed: list = dataclasses.field(default_factory=list)
    verdict: str = "clean"
    attempt: int = 1
    labels: dict | None = None
    dropped: int = 0
    findings: list = dataclasses.field(default_factory=list)
    body_sig: str = ""

    @property
    def sha8(self):
        return self.sha[:8]

    def finished(self):
        return not self.verdict.startswith("failed")


def normalise_claim(text, cap=CLAIM_MAX):
    text = str(text or "").replace("\u2014", "--").replace("\u2013", "--")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:cap]


def body_sig(findings):
    """sha256[:16] over `id|severity|file|line|anchor|claim` per finding. Resolution lines are NOT covered, so marking a finding never re-signs the file; a hand edit of a severity or a claim does not match any more."""
    canon = "\n".join(
        "%s|%s|%s|%s|%s|%s" % (f.id, f.severity, f.file, f.line, f.anchor, f.claim)
        for f in findings
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def _labels_text(labels):
    if not labels:
        return "(none)"
    kinds = ",".join(labels.get("kind") or []) or "none"
    why = normalise_claim(labels.get("why", ""), WHY_MAX) or "-"
    return "bump=%s kind=%s why=%s" % (labels.get("bump", "none"), kinds, why)


LABELS_RE = re.compile(r"^bump=(none|patch|minor|major) kind=([a-z,]+) why=(.*)$")


def _parse_labels(text):
    if text == "(none)":
        return None
    m = LABELS_RE.match(text)
    if not m:
        raise ValueError("Labels: is not `bump=<b> kind=<k,...> why=<text>` or `(none)`")
    kinds = [] if m.group(2) == "none" else m.group(2).split(",")
    if any(k not in KINDS for k in kinds):
        raise ValueError("Labels: kind %r is not one of %s" % (m.group(2), ",".join(KINDS)))
    return {"bump": m.group(1), "kind": kinds, "why": m.group(3)}


def render(review):
    """The canonical text of a review. `parse(render(r))` round-trips."""
    review.body_sig = body_sig(review.findings)
    subject = normalise_claim(review.subject, 160) or "(no subject)"
    lines = [
        "# Review %s: %s" % (review.sha8, subject),
        "",
        "Commit: %s" % review.sha,
        "Repo: %s" % review.repo,
        "Branch: %s" % review.branch,
        "Parent: %s" % review.parent,
        "Patch-Id: %s" % review.patch_id,
        "Reviewed-At: %s" % review.reviewed_at,
        "Model: %s" % (review.model or "(none)"),
        "Diff: %d bytes, %d files, truncated: %s"
        % (review.diff_bytes, review.diff_files, "yes" if review.truncated else "no"),
        "Unreviewed: %s" % (", ".join(review.unreviewed) or "(none)"),
        "Verdict: %s" % review.verdict,
        "Attempt: %d" % review.attempt,
        "Labels: %s" % _labels_text(review.labels),
        "Dropped: %d" % review.dropped,
        "Body-Sig: %s" % review.body_sig,
        "",
        "## Findings",
        "",
    ]
    if not review.findings:
        lines += ["(none)", ""]
    for f in review.findings:
        lines += [
            "### %s [%s] %s:%d" % (f.id, f.severity, f.file, f.line),
            "Anchor: %s" % f.anchor,
            "Claim: %s" % f.claim,
            "Resolution: %s" % f.resolution,
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


class MalformedReviewError(ValueError):
    """A review file that does not parse. `line` is the 1-based line the parser stopped at (0 when it is the file as a whole)."""

    def __init__(self, msg, line=0):
        super().__init__(msg)
        self.line = line


def parse(text):
    """A `Review` from file text, or `MalformedReviewError`. Strict: an unknown header, a bad Resolution grammar or a Body-Sig mismatch is malformed, because each is what a hand edit looks like."""
    lines = text.split("\n")
    if not lines or not lines[0].startswith("# Review "):
        raise MalformedReviewError("the first line is not `# Review <sha8>: <subject>`", 1)
    title = lines[0][len("# Review ") :]
    sha8, _, subject = title.partition(": ")
    headers = {}
    i = 1
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    while i < len(lines) and lines[i].strip() != "":
        key, sep, value = lines[i].partition(": ")
        if not sep or key not in HEADER_KEYS:
            raise MalformedReviewError("unknown header line %r" % lines[i][:80], i + 1)
        if key in headers:
            raise MalformedReviewError("header %s appears twice" % key, i + 1)
        headers[key] = value
        i += 1
    missing = [k for k in HEADER_KEYS if k not in headers]
    if missing:
        raise MalformedReviewError("missing header(s): %s" % ", ".join(missing))
    sha = headers["Commit"]
    if not SHA40.match(sha) or sha[:8] != sha8:
        raise MalformedReviewError("Commit: is not the 40-hex sha the title names", 0)
    diff = re.match(r"^(\d+) bytes, (\d+) files, truncated: (yes|no)$", headers["Diff"])
    if not diff:
        raise MalformedReviewError("Diff: is not `<n> bytes, <n> files, truncated: yes|no`")
    if not VERDICT_RE.match(headers["Verdict"]):
        raise MalformedReviewError("Verdict: %r is not a known verdict" % headers["Verdict"])
    try:
        labels = _parse_labels(headers["Labels"])
        attempt = int(headers["Attempt"])
        dropped = int(headers["Dropped"])
    except ValueError as exc:
        raise MalformedReviewError(str(exc)) from None
    review = Review(
        sha=sha,
        subject=subject,
        repo=headers["Repo"],
        branch=headers["Branch"],
        parent=headers["Parent"],
        patch_id=headers["Patch-Id"],
        reviewed_at=headers["Reviewed-At"],
        model=headers["Model"],
        diff_bytes=int(diff.group(1)),
        diff_files=int(diff.group(2)),
        truncated=diff.group(3) == "yes",
        unreviewed=[] if headers["Unreviewed"] == "(none)" else headers["Unreviewed"].split(", "),
        verdict=headers["Verdict"],
        attempt=attempt,
        labels=labels,
        dropped=dropped,
        body_sig=headers["Body-Sig"],
    )
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines) or lines[i] != "## Findings":
        raise MalformedReviewError("no `## Findings` section", i + 1)
    i += 1
    body = [(n + 1, ln) for n, ln in enumerate(lines) if n >= i and ln.strip() != ""]
    if body and body[0][1] == "(none)":
        body = body[1:]
        if body:
            raise MalformedReviewError("text after `(none)`", body[0][0])
    while body:
        if len(body) < 4:
            raise MalformedReviewError(
                "a finding needs a heading, Anchor:, Claim: and Resolution:", body[0][0]
            )
        (hn, head), (an, anchor), (cn, claim), (rn, resolution) = body[:4]
        body = body[4:]
        m = FINDING_HEAD.match(head)
        if not m:
            raise MalformedReviewError(
                "finding heading %r is not `### <sha8>.<n> [sev] <file>:<line>`" % head[:80], hn
            )
        if m.group(1) != sha[:8]:
            raise MalformedReviewError(
                "finding id %s.%s does not belong to this commit" % (m.group(1), m.group(2)), hn
            )
        if not anchor.startswith("Anchor: ") or anchor[8:] not in ("in-diff", "outside-diff"):
            raise MalformedReviewError("expected `Anchor: in-diff|outside-diff`", an)
        if not claim.startswith("Claim: "):
            raise MalformedReviewError("expected `Claim: <text>`", cn)
        if not resolution.startswith("Resolution: "):
            raise MalformedReviewError("expected `Resolution: ...`", rn)
        finding = Finding(
            id="%s.%s" % (m.group(1), m.group(2)),
            severity=m.group(3),
            file=m.group(4),
            line=int(m.group(5)),
            anchor=anchor[8:],
            claim=claim[7:],
            resolution=resolution[12:],
        )
        if not finding.resolution_kind():
            raise MalformedReviewError(
                "Resolution %r is not open | fixed <sha40> | not-a-bug | <evidence> | deferred #<item>, each signed `| <me8> <isoZ>`"
                % finding.resolution[:80],
                rn,
            )
        review.findings.append(finding)
    if body_sig(review.findings) != review.body_sig:
        raise MalformedReviewError(
            "Body-Sig %s does not match the findings (%s): a severity, file, line, anchor or claim was edited by hand"
            % (review.body_sig, body_sig(review.findings))
        )
    return review


def read_review(path):
    """(review, None) or (None, MalformedReviewError)."""
    try:
        return parse(pathlib.Path(path).read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, MalformedReviewError("unreadable: %s" % exc)
    except MalformedReviewError as exc:
        return None, exc


def write_atomic(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)


# --------------------------------------------------------------------------- locks and slots (section 3.2)


def _pid_is_reviewer(pid):
    try:
        pid = int(pid)
        os.kill(pid, 0)
    except (TypeError, ValueError, ProcessLookupError, PermissionError, OSError):
        return False
    try:
        cmdline = pathlib.Path("/proc/%d/cmdline" % pid).read_bytes()
    except OSError:
        return True
    return b"wl_review" in cmdline


def lock_path(sha):
    return state_dir() / "locks" / ("%s.lock" % sha)


def lock_live(sha, now=None):
    """True while a reviewer holds this sha: its pid is a live wl_review, or a spawn is still inside its grace window."""
    try:
        doc = json.loads(lock_path(sha).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(doc, dict):
        return False
    if _pid_is_reviewer(doc.get("pid")):
        return True
    if doc.get("pid") is None:
        return (now or time.time()) - float(doc.get("start") or 0) < SPAWN_GRACE_S
    return False


def acquire_lock(sha, branch, pid=None, now=None):
    """Take the per-sha lock (O_CREAT|O_EXCL); a stale one is replaced once. False when a live reviewer holds it."""
    path = lock_path(sha)
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if lock_live(sha, now):
                return False
            with contextlib.suppress(OSError):
                path.unlink()
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"pid": pid, "start": now or time.time(), "branch": branch}, fh)
        return True
    return False


def set_lock_pid(sha, pid):
    path = lock_path(sha)
    with contextlib.suppress(OSError, ValueError):
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["pid"] = pid
        write_atomic(path, json.dumps(doc))


def release_lock(sha):
    with contextlib.suppress(OSError):
        lock_path(sha).unlink()


def acquire_slot(cfg, sleep=time.sleep, clock=time.monotonic):
    """A model-call slot out of `max_concurrent`, waiting up to `slot_wait_s`. Returns its path, or None on timeout."""
    slots = state_dir() / "slots"
    deadline = clock() + float(cfg["slot_wait_s"])
    while True:
        for n in range(max(1, int(cfg["max_concurrent"]))):
            path = slots / ("%d.slot" % n)
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                try:
                    holder = int(path.read_text(encoding="utf-8").strip() or 0)
                except (OSError, ValueError):
                    holder = 0
                if not _pid_is_reviewer(holder):
                    with contextlib.suppress(OSError):
                        path.unlink()
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(str(os.getpid()))
            return path
        if clock() >= deadline:
            return None
        sleep(2)


# --------------------------------------------------------------------------- coverage (section 3.1)


def base_range(repo, branch):
    """The branch's own commits: `origin/main..HEAD` on main (a hotfix), else `merge-base(origin/main, HEAD)..HEAD`. "" when origin/main is unknown."""
    if not git_out(repo, "rev-parse", "-q", "--verify", "origin/main^{commit}"):
        return ""
    if branch == "main":
        return "origin/main..HEAD"
    base = git_out(repo, "merge-base", "origin/main", "HEAD")
    return "%s..HEAD" % base if base else ""


def branch_commits(repo, rng, limit):
    """Newest first: [{sha, author_date, subject, paths}] for the non-merge commits of `rng`."""
    if not rng:
        return []
    rc, out = git(
        repo,
        "log",
        "--no-merges",
        "-n",
        str(limit),
        "--format=%x1e%H%x1f%aI%x1f%s",
        "--name-only",
        rng,
    )
    if rc != 0:
        return []
    commits = []
    for record in out.split("\x1e"):
        if not record.strip():
            continue
        head, _, rest = record.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 3:
            continue
        paths = [p for p in rest.split("\n") if p.strip()]
        commits.append(
            {"sha": parts[0], "author_date": parts[1], "subject": parts[2], "paths": paths}
        )
    return commits


def reviews_only(paths):
    return bool(paths) and all(p.startswith(REVIEWS_REL + "/") for p in paths)


def before_epoch(author_date, cfg):
    epoch = _parse_iso(cfg.get("review_epoch") or "")
    when = _parse_iso(author_date)
    return bool(epoch and when and when < epoch)


def review_index(root, branch):
    """{sha: path} and {patch_id: path} for the review files in the branch directory, read from headers only."""
    by_sha: dict[str, pathlib.Path] = {}
    by_patch: dict[str, pathlib.Path] = {}
    d = branch_dir(root, branch)
    if not d.is_dir():
        return by_sha, by_patch
    for path in d.glob("*.md"):
        sha = path.stem
        if not SHA40.match(sha):
            continue
        by_sha[sha] = path
        try:
            with path.open(encoding="utf-8") as fh:
                for _ in range(10):
                    line = fh.readline()
                    if line.startswith("Patch-Id: "):
                        pid = line[len("Patch-Id: ") :].strip()
                        if SHA40.match(pid):
                            by_patch.setdefault(pid, path)
                        break
        except OSError:
            continue
    return by_sha, by_patch


def patch_id(repo, sha):
    rc, diff = git(repo, "show", "--format=", "--no-color", sha)
    if rc != 0 or not diff.strip():
        return ""
    rc, out = git(repo, "patch-id", "--stable", stdin=diff)
    return out.split()[0] if rc == 0 and out.split() else ""


def uncovered(root, repo, branch, cfg=None):
    """Commits of the branch, newest first, that have no review file (by sha or patch-id) and no live reviewer.

    Dropped before the question is asked: merge commits, commits that touch only `agent/reviews/` (no review of reviews), empty commits and commits authored before `review_epoch`.
    """
    cfg = cfg or load_config(root)
    commits = branch_commits(repo, base_range(repo, branch), int(cfg["max_uncovered_scan"]))
    by_sha, by_patch = review_index(root, branch)
    out = []
    for c in commits:
        if not c["paths"] or reviews_only(c["paths"]) or before_epoch(c["author_date"], cfg):
            continue
        if c["sha"] in by_sha or lock_live(c["sha"]):
            continue
        if by_patch and patch_id(repo, c["sha"]) in by_patch:
            continue
        out.append(c["sha"])
    return out


def in_scope_shas(root, repo, branch, cfg=None):
    """Every commit of the branch the review applies to (the same filter as `uncovered`, without the coverage test)."""
    cfg = cfg or load_config(root)
    commits = branch_commits(repo, base_range(repo, branch), int(cfg["max_uncovered_scan"]))
    return [
        c["sha"]
        for c in commits
        if c["paths"] and not reviews_only(c["paths"]) and not before_epoch(c["author_date"], cfg)
    ]


def spawn_detached(root, repo, sha, branch, python=None):
    """Take the sha's lock and start the reviewer DETACHED. Returns the child's pid, or 0 when a live reviewer already holds the sha.

    H3 of the plan: the post-bash runner captures each member's pipes, so a child that inherited them would hold the Bash call open for the whole review. DEVNULL in, a log file out, its own session, every other descriptor closed.
    """
    if not acquire_lock(sha, branch):
        return 0
    log = state_dir() / "logs" / ("%s.log" % sha)
    argv = [
        python or sys.executable,
        str(SELF),
        "--run",
        sha,
        "--branch",
        branch,
        "--repo",
        repo_label(root, repo),
        "--root",
        str(root),
        "--lock-held",
    ]
    try:
        with open(log, "ab") as fh:
            proc = subprocess.Popen(
                argv,
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
    except OSError:
        release_lock(sha)
        raise
    set_lock_pid(sha, proc.pid)
    return proc.pid


def trigger(root, repo, cfg=None, spawn=spawn_detached):
    """Start reviewers for up to `max_spawn_per_trigger` uncovered commits of the repo's branch. Returns [(sha, pid)]."""
    cfg = cfg or load_config(root)
    branch = current_branch(repo)
    if not branch:
        return []
    started = []
    for sha in uncovered(root, repo, branch, cfg)[: int(cfg["max_spawn_per_trigger"])]:
        pid = spawn(root, repo, sha, branch)
        if pid:
            started.append((sha, pid))
    return started


# --------------------------------------------------------------------------- the runner (sections 3.2 and 3.3)


def _commit_facts(repo, sha):
    """(paths, gitlink_only, subject, message, parent) for one commit, from the object store."""
    rc, raw = git(repo, "show", "--format=", "--raw", "--no-abbrev", "-M", sha)
    paths, modes = [], []
    if rc == 0:
        for line in raw.splitlines():
            if not line.startswith(":"):
                continue
            meta, _, names = line.partition("\t")
            fields = meta[1:].split()
            modes.append((fields[0], fields[1]) if len(fields) >= 2 else ("", ""))
            paths.append(names.split("\t")[-1])
    gitlink_only = bool(modes) and all("160000" in pair for pair in modes)
    message = git_out(repo, "show", "-s", "--format=%B", sha)
    subject = message.split("\n", 1)[0] if message else ""
    parent = git_out(repo, "rev-parse", "-q", "--verify", "%s^" % sha) or "(root)"
    return paths, gitlink_only, subject, message, parent


def capped_diff(repo, sha, cap):
    """(diff_text, total_bytes, file_count, unreviewed_files). Whole per-file sections are kept until `cap`; the rest are listed, never cut mid-file."""
    rc, diff = git(repo, "show", "-U%d" % ANCHOR_SLACK, "--no-color", "--format=", "-M", sha)
    if rc != 0:
        return "", 0, 0, []
    chunks = re.split(r"(?m)^(?=diff --git )", diff)
    chunks = [c for c in chunks if c.strip()]
    kept, cut, used = [], [], 0
    for chunk in chunks:
        m = re.match(r"diff --git a/(.*?) b/(.*)", chunk)
        name = m.group(2) if m else "?"
        size = len(chunk.encode("utf-8"))
        if used + size <= cap:
            kept.append(chunk)
            used += size
        elif not kept:
            # One file larger than the whole cap: send its head rather than nothing, and say so.
            kept.append(chunk.encode("utf-8")[:cap].decode("utf-8", "ignore"))
            used = cap
            cut.append(name + " (partial)")
        else:
            cut.append(name)
    return "".join(kept), len(diff.encode("utf-8")), len(chunks), cut


def hunk_ranges(diff_text):
    """{path: [(start, end)]} of new-side hunks."""
    ranges: dict[str, list[tuple[int, int]]] = {}
    current = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = target[2:] if target.startswith("b/") else None
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if m and current:
            start = int(m.group(1))
            length = int(m.group(2)) if m.group(2) is not None else 1
            ranges.setdefault(current, []).append((start, start + max(length, 1) - 1))
    return ranges


def validate(structured, paths, diff_text, sha, is_writing=None):
    """(verdict, findings, labels, dropped) from the model's object. A finding whose file is not in the commit is DROPPED and counted; one whose line is outside +-ANCHOR_SLACK of a new-side hunk keeps its severity and is marked outside-diff.

    WRITING IS NEVER ABOVE LOW. `is_writing(path)` is the commit policy's own `no_review_eligible` (agent/**, docs/**, **/*.md, minus .claude/** and CLAUDE.md), so the one definition of "purely writing" decides it. Measured on this feature's first live hour (2026-10-02): haiku rated a session STATE.md heading stamp and a generated agent/INDEX.md footer count `[high]`, and each would have refused the branch's push. A finding about prose stays on the record, as advisory.
    """
    ranges = hunk_ranges(diff_text)
    findings: list[Finding] = []
    dropped = 0
    raw = structured.get("findings") if isinstance(structured, dict) else None
    for item in (raw or [])[:MAX_FINDINGS]:
        if not isinstance(item, dict):
            dropped += 1
            continue
        path = str(item.get("file") or "").strip()
        if path not in paths and path[:2] in ("a/", "b/") and path[2:] in paths:
            path = path[2:]
        sev = item.get("severity")
        try:
            line = int(item.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        claim = normalise_claim(item.get("claim"))
        if path not in paths or sev not in SEV_RANK or line < 1 or not claim:
            dropped += 1
            continue
        if is_writing is not None and sev != "low" and is_writing(path):
            sev = "low"
        inside = any(
            lo - ANCHOR_SLACK <= line <= hi + ANCHOR_SLACK for lo, hi in ranges.get(path, ())
        )
        findings.append(
            Finding(
                id="%s.%d" % (sha[:8], len(findings) + 1),
                severity=sev,
                file=path,
                line=line,
                anchor="in-diff" if inside else "outside-diff",
                claim=claim,
            )
        )
    labels_in = structured.get("labels") if isinstance(structured, dict) else None
    labels = None
    if isinstance(labels_in, dict) and labels_in.get("bump") in BUMPS:
        kinds = [k for k in (labels_in.get("kind") or []) if k in KINDS]
        labels = {
            "bump": labels_in["bump"],
            "kind": sorted(set(kinds), key=KINDS.index),
            "why": normalise_claim(labels_in.get("why", ""), WHY_MAX),
        }
    return ("findings" if findings else "clean"), findings, labels, dropped


def resolve_claude():
    return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def claude_reviewer(prompt, cfg, log=print):
    """(structured_output, why) from one tool-less, schema-constrained haiku call. One retry when the answer carries no structured output."""
    import wl_proc  # noqa: PLC0415 -- only the child ever calls the model; the stop directory is sys.path[0] for the script and already on the path for every importer

    workdir = (
        pathlib.Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
        / "claude-worklist"
        / ".review"
    )
    workdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["STOPHOOK_CHILD"] = "1"
    env["COMMIT_REVIEW_CHILD"] = "1"
    argv = [
        resolve_claude(),
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(SCHEMA),
        "--model",
        str(cfg["model"]),
        "--tools",
        "",
        "--max-budget-usd",
        str(cfg["budget_usd"]),
    ]
    import wl_judge  # noqa: PLC0415 -- same reason as wl_proc above

    def _call():
        return wl_proc.run(argv, timeout=int(cfg["timeout_s"]), env=env, cwd=str(workdir))

    why = ""
    for attempt in (1, 2):
        started = time.time()
        proc = _call()
        if proc.timed_out:
            return None, "model call timed out after %ss" % cfg["timeout_s"]
        if proc.returncode not in (0, wl_proc.SPAWN_FAILED_RC):
            # A schema exhaustion (exit 1, `error_max_structured_output_retries`) is one sample failing, retried once by the shared helper every schema-constrained call site routes through (check:ci-schema-call-sites); any other non-zero exit is reported with the helper's explanation of it, as at the other sites.
            proc, retry_why = wl_judge.retry_schema_exhaustion("commit review", proc, _call)
            if proc is None:
                return None, normalise_claim(retry_why, 300)
        took = time.time() - started
        try:
            envelope = json.loads(proc.stdout or "")
        except ValueError:
            envelope = None
        cost = envelope.get("total_cost_usd") if isinstance(envelope, dict) else None
        log("call %d: rc=%s %.1fs cost=%s" % (attempt, proc.returncode, took, cost))
        if isinstance(envelope, dict) and isinstance(envelope.get("structured_output"), dict):
            return envelope["structured_output"], ""
        if isinstance(envelope, dict):
            why = "no structured output (rc=%s, subtype=%s)" % (
                proc.returncode,
                envelope.get("subtype"),
            )
        else:
            why = "model call failed (rc=%s): %s" % (
                proc.returncode,
                normalise_claim((proc.stderr or proc.stdout or "")[-300:], 160) or "no output",
            )
        if proc.returncode == wl_proc.SPAWN_FAILED_RC:
            break
    return None, why


def _load_commit_policy(root):
    """`.claude/rediacc_hooks/commit_policy.py` loaded BY FILE, as the git-level hooks load it: it is stdlib-only, and no sys.path entry is added."""
    path = pathlib.Path(root) / ".claude" / "rediacc_hooks" / "commit_policy.py"
    spec = importlib.util.spec_from_file_location("commit_policy_for_review", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _writing_test(root):
    """`path -> bool`: is this one path purely writing under the commit policy? None when the policy cannot be read (then no finding is capped)."""
    try:
        policy = _load_commit_policy(root)
        cfg = policy.load_config(str(root)) if policy is not None else None
    except Exception:  # noqa: BLE001 -- an unreadable policy caps nothing
        return None
    if policy is None:
        return None
    return lambda path: bool(policy.no_review_eligible([path], cfg)[0])


def _no_review_skip(root, message, paths):
    """True when the subject carries `[no-review]` and every path is eligible under the commit policy, re-checked here as the commit-policy plan's section 4.2 requires. A `[hotfix]` is always reviewed."""
    try:
        policy = _load_commit_policy(root)
    except (OSError, ImportError, SyntaxError):
        return False
    if policy is None:
        return False
    tags = policy.tags(message or "")
    if "no-review" not in tags or "hotfix" in tags:
        return False
    try:
        cfg = policy.load_config(str(root))
    except Exception:  # noqa: BLE001 -- an unreadable policy means review it
        return False
    eligible, _offenders = policy.no_review_eligible(paths, cfg)
    return bool(eligible)


def run_review(
    root,
    repo_label_text,
    sha,
    branch,
    cfg=None,
    reviewer=None,
    lock_held=False,
    now=None,
    log=print,
):
    """Review one commit and write its file. Returns the path written, or None when nothing was owed (a live reviewer, a rebased copy, a reviews-only commit)."""
    cfg = cfg or load_config(root)
    repo = repo_from_label(root, repo_label_text)
    full = git_out(repo, "rev-parse", "-q", "--verify", "%s^{commit}" % sha)
    if not full:
        log("unknown commit %s in %s" % (sha, repo))
        return None
    if not lock_held and not acquire_lock(full, branch, pid=os.getpid()):
        log("a live reviewer already holds %s" % full)
        return None
    if lock_held:
        set_lock_pid(full, os.getpid())
    slot = None
    try:
        paths, gitlink_only, subject, message, parent = _commit_facts(repo, full)
        if not paths or reviews_only(paths):
            log("nothing to review in %s" % full)
            return None
        out_path = review_path(root, branch, full)
        pid = patch_id(repo, full)
        _by_sha, by_patch = review_index(root, branch)
        twin = by_patch.get(pid) if pid else None
        if twin is not None and twin.stem != full:
            log("rebased copy of %s (patch-id %s); nothing written" % (twin.stem, pid))
            return None
        previous, _err = read_review(out_path) if out_path.exists() else (None, None)
        review = Review(
            sha=full,
            subject=subject,
            repo=repo_label(root, repo),
            branch=branch,
            parent=parent,
            patch_id=pid or "(none)",
            model=str(cfg["model"]),
            attempt=(previous.attempt + 1)
            if previous is not None and not previous.finished()
            else 1,
        )
        if gitlink_only:
            review.verdict, review.model = "skipped (gitlink-only)", "(none)"
        elif _no_review_skip(root, message, paths):
            review.verdict, review.model = "skipped (no-review)", "(none)"
        else:
            diff_text, total, nfiles, cut = capped_diff(repo, full, int(cfg["diff_cap_bytes"]))
            review.diff_bytes, review.diff_files = total, nfiles
            review.truncated, review.unreviewed = bool(cut), cut
            stat = git_out(repo, "show", "--stat", "--format=", full)
            prompt = PROMPT % {
                "message": message or "(empty)",
                "stat": stat or "(empty)",
                "truncated": ", ".join(cut) or "(none)",
                "diff": diff_text or "(empty)",
            }
            slot = acquire_slot(cfg)
            if slot is None:
                review.verdict = "failed (queue timeout)"
            else:
                structured, why = (reviewer or claude_reviewer)(prompt, cfg, log)
                if structured is None:
                    review.verdict = "failed (%s)" % normalise_claim(why, 180).replace(
                        "(", "["
                    ).replace(")", "]")
                else:
                    review.verdict, review.findings, review.labels, review.dropped = validate(
                        structured, paths, diff_text, full, is_writing=_writing_test(root)
                    )
        review.reviewed_at = now_iso(now)
        write_atomic(out_path, render(review))
        log("wrote %s: %s, %d finding(s)" % (out_path, review.verdict, len(review.findings)))
        return out_path
    finally:
        if slot is not None:
            with contextlib.suppress(OSError):
                slot.unlink()
        release_lock(full)


# --------------------------------------------------------------------------- what every reader asks (section 7)


def _untracked_or_modified(root, d):
    rc, out = git(root, "status", "--porcelain", "--untracked-files=all", "--", str(d))
    if rc != 0:
        return set()
    names = set()
    for line in out.splitlines():
        name = line[3:].strip().strip('"')
        names.add(pathlib.Path(root, name).resolve())
    return names


def branch_state(root, branch, cfg=None, items=None, repos=None):
    """Everything a reader needs about the branch's reviews, computed once.

    `items`, when given, is {item_id: state} from the worklist fold: a `deferred #<item>` whose item is gone reopens its finding. Without it a deferral counts as resolved (the mark verb checked the item when it was written).
    `repos`, when given, limits the coverage walk; default: the console plus every repo a review in the directory names.
    """
    cfg = cfg or load_config(root)
    block_rank = SEV_RANK[cfg["block_at"]]
    d = branch_dir(root, branch)
    st = {
        "branch": branch,
        "dir": d,
        "reviews": [],
        "malformed": [],
        "blocking": [],
        "advisory": [],
        "failed": [],
        "failed_stuck": [],
        "in_flight": [],
        "uncommitted": [],
        "uncovered": [],
    }
    dirty = _untracked_or_modified(root, d) if d.is_dir() else set()
    seen_repos = {"console"}
    for path in sorted(d.glob("*.md")) if d.is_dir() else []:
        review, err = read_review(path)
        if review is None:
            st["malformed"].append((path, err))
            continue
        st["reviews"].append((path, review))
        seen_repos.add(review.repo)
        if path.resolve() in dirty:
            st["uncommitted"].append(path)
        if not review.finished():
            (st["failed_stuck"] if review.attempt >= FAIL_OPEN_AFTER else st["failed"]).append(
                (path, review)
            )
        for f in review.findings:
            kind = f.resolution_kind()
            reopened = kind == "deferred" and items is not None and f.deferred_item() not in items
            if kind != "open" and not reopened:
                continue
            (st["blocking"] if SEV_RANK[f.severity] >= block_rank else st["advisory"]).append(
                (path, f)
            )
    for label in sorted(repos if repos is not None else seen_repos):
        repo = repo_from_label(root, label)
        if not (repo / ".git").exists():
            continue
        if current_branch(repo) != branch and label != "console":
            continue
        for sha in in_scope_shas(root, repo, branch, cfg):
            if lock_live(sha):
                st["in_flight"].append((label, sha))
        for sha in uncovered(root, repo, branch, cfg):
            st["uncovered"].append((label, sha))
    return st


def run_command(label, sha, branch):
    return "python3 .claude/hooks/stop/wl_review.py --run %s --branch %s --repo %s" % (
        sha,
        branch,
        label,
    )


def mark_commands(finding_id):
    return (
        "worklist.py --review-mark <me> %s fixed <sha-of-the-fix>" % finding_id,
        "worklist.py --review-mark <me> %s not-a-bug <evidence citing path:line or a sha>"
        % finding_id,
        "worklist.py --review-mark <me> %s deferred #<worklist-item naming %s>"
        % (finding_id, finding_id),
    )


def describe(st, limit=5):
    """The human lines for a state: what blocks, what is advisory, what to run."""
    out = []
    for path, err in st["malformed"][:limit]:
        out.append(
            "MALFORMED %s: %s%s" % (path.name, err, " (line %d)" % err.line if err.line else "")
        )
    for _path, f in st["blocking"][:limit]:
        out.append("OPEN [%s] %s %s:%d -- %s" % (f.severity, f.id, f.file, f.line, f.claim[:160]))
        out.extend("    " + c for c in mark_commands(f.id))
    for label, sha in st["uncovered"][:limit]:
        out.append("UNREVIEWED %s %s: %s" % (label, sha[:8], run_command(label, sha, st["branch"])))
    for label, sha in st["in_flight"][:limit]:
        out.append(
            "IN FLIGHT %s %s: a reviewer is running (log: %s)"
            % (label, sha[:8], state_dir() / "logs" / ("%s.log" % sha))
        )
    for _path, r in st["failed"][:limit]:
        out.append(
            "FAILED %s %s: %s; retry: %s"
            % (r.repo, r.sha8, r.verdict, run_command(r.repo, r.sha, st["branch"]))
        )
    for _path, r in st["failed_stuck"][:limit]:
        out.append(
            "FAILED x%d %s %s: %s (no longer blocks a push)"
            % (r.attempt, r.repo, r.sha8, r.verdict)
        )
    if st["uncommitted"]:
        out.append(
            "UNRECORDED %d finished review file(s) not committed: worklist.py --review-commit <me>"
            % len(st["uncommitted"])
        )
    if st["advisory"]:
        out.append(
            "advisory: %d open finding(s) below %s: %s"
            % (
                len(st["advisory"]),
                "the block threshold",
                ", ".join(f.id for _p, f in st["advisory"][:12]),
            )
        )
    return out


def recordable(st):
    """Review files that are finished (or failed past FAIL_OPEN_AFTER) and not committed: what `--review-commit` would record."""
    done = {p for p, r in st["reviews"] if r.finished() or r.attempt >= FAIL_OPEN_AFTER}
    return [p for p in st["uncommitted"] if p in done and not lock_live(p.stem)]


def push_refusals(st, console_push=True):
    """The reasons a push of this branch must wait, in the order to fix them. Empty means the push may go."""
    reasons = []
    if st["malformed"]:
        reasons.append("malformed")
    if st["blocking"]:
        reasons.append("blocking")
    if st["uncovered"]:
        reasons.append("uncovered")
    if st["in_flight"]:
        reasons.append("in_flight")
    if st["failed"]:
        reasons.append("failed")
    if console_push and recordable(st):
        reasons.append("uncommitted")
    return reasons


def stop_texts(st, limit=5):
    """(block, malformed, note) for the Stop hook: the `commit-review` block, the `commit-review-malformed` block and the advisory, each "" when there is nothing to say."""
    block = malformed = ""
    if st["malformed"]:
        malformed = (
            "PER-COMMIT REVIEW FILE(S) MALFORMED in %s. A file that does not parse, or whose Body-Sig no longer matches its findings, is what a hand edit looks like. Re-review the commit to rewrite it:\n  %s"
            % (
                st["dir"],
                "\n  ".join(
                    "%s: %s%s -- %s"
                    % (
                        p.name,
                        err,
                        " (line %d)" % err.line if getattr(err, "line", 0) else "",
                        run_command("console", p.stem, st["branch"]),
                    )
                    for p, err in st["malformed"][:limit]
                ),
            )
        )
    if st["blocking"]:
        lines = []
        for _p, f in st["blocking"][:limit]:
            lines.append("[%s] %s %s:%d -- %s" % (f.severity, f.id, f.file, f.line, f.claim[:160]))
            lines.extend("    " + c for c in mark_commands(f.id))
        block = (
            "OPEN PER-COMMIT REVIEW FINDING(S) at or above the block threshold on %s (%d). Fix each and mark it, or record why it is not a bug, or defer it to a worklist item that names it:\n  %s"
            % (st["branch"], len(st["blocking"]), "\n  ".join(lines))
        )
    rest = dict(st, malformed=[], blocking=[])
    note_lines = describe(rest, limit)
    note = (
        ("Per-commit reviews on %s:\n  %s" % (st["branch"], "\n  ".join(note_lines)))
        if note_lines
        else ""
    )
    return block, malformed, note


def session_start_line(root, branch, cfg=None):
    """One block for SessionStart: the branch's review state, from disk only (plus local git)."""
    if not branch:
        return ""
    try:
        st = branch_state(root, branch, cfg)
    except Exception as exc:  # noqa: BLE001 -- a SessionStart must never fail on this
        return "Per-commit reviews for %s could not be read (%s: %s)." % (
            branch,
            type(exc).__name__,
            exc,
        )
    lines = describe(st)
    if not lines:
        return ""
    return "Per-commit reviews for %s (agent/reviews/%s/, %d file(s)):\n  %s" % (
        branch,
        branch_slug(branch),
        len(st["reviews"]),
        "\n  ".join(lines),
    )


def surface_new(root, branch, session_id, cfg=None):
    """Lines for review files that FINISHED since this session last heard of them (the next-turn channel while the Stop hook is off). Marks them seen."""
    d = branch_dir(root, branch)
    if not session_id or not d.is_dir():
        return []
    seen_path = state_dir() / "seen" / ("%s.json" % re.sub(r"[^A-Za-z0-9_-]", "_", session_id[:36]))
    try:
        seen = json.loads(seen_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    if not isinstance(seen, dict):
        seen = {}
    fresh = []
    for path in sorted(d.glob("*.md")):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if seen.get(path.name) == mtime:
            continue
        seen[path.name] = mtime
        fresh.append(path)
    if not fresh:
        return []
    write_atomic(seen_path, json.dumps(seen))
    cfg = cfg or load_config(root)
    block_rank = SEV_RANK[cfg["block_at"]]
    lines = []
    for path in fresh:
        review, err = read_review(path)
        if review is None:
            lines.append("review %s is MALFORMED: %s" % (path.name, err))
            continue
        opened = [f for f in review.findings if f.resolution_kind() == "open"]
        blocking = [f for f in opened if SEV_RANK[f.severity] >= block_rank]
        lines.append(
            "review %s (%s): %s, %d open finding(s), %d at or above %s"
            % (
                review.sha8,
                review.repo,
                review.verdict,
                len(opened),
                len(blocking),
                cfg["block_at"],
            )
        )
        for f in blocking[:5]:
            lines.append(
                "  [%s] %s %s:%d -- %s" % (f.severity, f.id, f.file, f.line, f.claim[:200])
            )
            lines.extend("    " + c for c in mark_commands(f.id))
    lines.append(
        "Review files ride the next commit (`git commit -F <msg> -- <paths> %s/`) or `worklist.py --review-commit <me>`; a push waits until they are committed."
        % pathlib.Path(REVIEWS_REL, branch_slug(branch))
    )
    return lines


# --------------------------------------------------------------------------- the verbs (sections 5 and 6)


def find_finding(root, branch, finding_id):
    """(path, review, finding) or raise ValueError naming why."""
    d = branch_dir(root, branch)
    hits: list[tuple[pathlib.Path, Review, Finding]] = []
    for path in sorted(d.glob("%s*.md" % finding_id.split(".")[0])) if d.is_dir() else []:
        review, err = read_review(path)
        if review is None:
            raise ValueError("%s is malformed (%s); it cannot be marked" % (path, err))
        hits.extend((path, review, f) for f in review.findings if f.id == finding_id)
    if len(hits) != 1:
        raise ValueError(
            "finding %s matches %d review file(s) in %s; expected exactly 1"
            % (finding_id, len(hits), d)
        )
    return hits[0]


CITE_PATH = re.compile(r"([A-Za-z0-9_./-]+\.[A-Za-z0-9]+):(\d+)")
CITE_SHA = re.compile(r"\b([0-9a-f]{7,40})\b")


def _citation_ok(repo, evidence):
    for m in CITE_PATH.finditer(evidence):
        path = pathlib.Path(repo) / m.group(1)
        with contextlib.suppress(OSError):
            if path.is_file() and int(m.group(2)) <= len(
                path.read_text(encoding="utf-8", errors="replace").splitlines()
            ):
                return True
    for m in CITE_SHA.finditer(evidence):
        full = git_out(repo, "rev-parse", "-q", "--verify", "%s^{commit}" % m.group(1))
        if full and git(repo, "merge-base", "--is-ancestor", full, "HEAD")[0] == 0:
            return True
    return False


def mark(root, branch, finding_id, kind, args, me, items=None, now=None):
    """Close one finding. Returns the path written; raises ValueError naming the failed check.

    `items` is {item_id: (state, text)} from the worklist fold, needed only for `deferred`.
    """
    path, review, finding = find_finding(root, branch, finding_id)
    repo = repo_from_label(root, review.repo)
    stamp = "%s %s" % (me[:8], now_iso(now))
    if kind == "fixed":
        if len(args) != 1:
            raise ValueError("fixed takes exactly one sha")
        fix = git_out(repo, "rev-parse", "-q", "--verify", "%s^{commit}" % args[0])
        if not fix:
            raise ValueError("%s does not resolve to a commit in %s" % (args[0], review.repo))
        if fix == review.sha:
            raise ValueError("the fix cannot be the reviewed commit itself")
        if git(repo, "merge-base", "--is-ancestor", fix, "HEAD")[0] != 0:
            raise ValueError("%s is not on this branch (not an ancestor of HEAD)" % fix[:12])
        if git(repo, "merge-base", "--is-ancestor", review.sha, fix)[0] != 0:
            raise ValueError(
                "%s does not descend from the reviewed commit %s" % (fix[:12], review.sha8)
            )
        touched = git_out(
            repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--find-renames", fix
        ).splitlines()
        renamed = git_out(
            repo,
            "log",
            "--format=",
            "--name-only",
            "--follow",
            "%s..%s" % (review.sha, fix),
            "--",
            finding.file,
        )
        if finding.file not in touched and not set(renamed.splitlines()) & set(touched):
            raise ValueError("%s does not touch %s" % (fix[:12], finding.file))
        resolution = "fixed %s | %s" % (fix, stamp)
    elif kind == "not-a-bug":
        evidence = normalise_claim(" ".join(args), 400).replace("|", "/")
        if len(evidence) < 20:
            raise ValueError("not-a-bug needs at least 20 characters of evidence")
        if not _citation_ok(repo, evidence):
            raise ValueError(
                "not-a-bug evidence must cite a path:line that exists or a sha on this branch"
            )
        resolution = "not-a-bug | %s | %s" % (evidence, stamp)
    elif kind == "deferred":
        if len(args) != 1 or not re.match(r"^#?[0-9a-f]{6,16}$", args[0]):
            raise ValueError("deferred takes one worklist item id, #<id>")
        item = args[0].lstrip("#")
        rec = (items or {}).get(item)
        if rec is None:
            raise ValueError("worklist item #%s does not exist" % item)
        state, text = rec
        if state not in (" ", "?", ">"):
            raise ValueError("worklist item #%s is not open, [?] or [>] (state %r)" % (item, state))
        if finding_id not in (text or ""):
            raise ValueError("worklist item #%s does not name %s in its text" % (item, finding_id))
        resolution = "deferred #%s | %s" % (item, stamp)
    else:
        raise ValueError("the resolution is fixed, not-a-bug or deferred, not %r" % kind)
    finding.resolution = resolution
    with _mark_lock(review.sha):
        current, err = read_review(path)
        if current is None:
            raise ValueError("%s became malformed (%s)" % (path, err))
        for f in current.findings:
            if f.id == finding_id:
                f.resolution = resolution
        write_atomic(path, render(current))
    return path


@contextlib.contextmanager
def _mark_lock(sha):
    import fcntl  # noqa: PLC0415 -- POSIX only, and only the verb needs it

    with open(state_dir() / "locks" / ("%s.mark" % sha), "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


TRAILER = re.compile(r"(?m)^PR-TASK:[ \t]*([0-9a-f]{6,32})[ \t]*$")


def commit_reviews(root, branch, run=subprocess.run):
    """`git add` + `git commit -F <msg> -- <files>` for the finished, uncommitted review files of the branch. Returns (rc, text)."""
    st = branch_state(root, branch, repos=())
    files = recordable(st)
    if not files:
        return 0, "no finished review file is waiting to be committed in %s" % st["dir"]
    shas = sorted({p.stem for p in files})
    trailer = ""
    for _p, r in sorted(st["reviews"], key=lambda pr: pr[0].stat().st_mtime, reverse=True):
        body = git_out(repo_from_label(root, r.repo), "show", "-s", "--format=%B", r.sha)
        m = TRAILER.search(body)
        if m:
            trailer = m.group(1)
            break
    msg = "chore(reviews): record reviews for %s\n" % " ".join(s[:8] for s in shas)
    if trailer:
        msg += "\nPR-TASK: %s\n" % trailer
    rels = [str(p.relative_to(root)) for p in files]
    fd, msg_path = tempfile.mkstemp(prefix="review-commit-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(msg)
    try:
        add = run(
            ["git", "-C", str(root), "add", "--", *rels],
            capture_output=True,
            text=True,
            check=False,
        )
        if add.returncode != 0:
            return add.returncode, add.stderr
        done = run(
            ["git", "-C", str(root), "commit", "-q", "-F", msg_path, "--", *rels],
            capture_output=True,
            text=True,
            check=False,
        )
        return done.returncode, (
            done.stdout + done.stderr
        ).strip() or "committed %d review file(s): %s" % (len(rels), " ".join(rels))
    finally:
        with contextlib.suppress(OSError):
            os.unlink(msg_path)


# --------------------------------------------------------------------------- verbs behind worklist.py


VERB_USAGE = """usage:
  worklist.py --review-mark <me>                                       list the branch's open findings
  worklist.py --review-mark <me> <finding-id> fixed <sha>              the fix: on the branch, after the reviewed commit, touching the file
  worklist.py --review-mark <me> <finding-id> not-a-bug <evidence...>  >= 20 chars citing an existing path:line or a sha on the branch
  worklist.py --review-mark <me> <finding-id> deferred #<item>         an open worklist item whose text names the finding id
  worklist.py --review-commit <me>                                     commit the finished, unrecorded review files of the branch
  worklist.py --review-run <me> [<sha> [--repo <console|private/x>]]   list unreviewed commits, or review one now in the foreground
"""


def verb(name, me, args, root, items_loader, branch=None):
    """(rc, text) for one worklist review verb. `items_loader()` returns {item_id: (state, text)} from the worklist fold; it is called only when a deferral needs it."""
    root = pathlib.Path(root)
    branch = branch or current_branch(root)
    if name == "--review-mark":
        if not args:
            if not branch:
                return 0, "open per-commit review findings: none (HEAD is on no branch)"
            st = branch_state(root, branch, repos=())
            rows = st["blocking"] + st["advisory"]
            if not rows:
                return 0, "open per-commit review findings for %s: none" % branch
            text = ["open per-commit review findings for %s:" % branch]
            text += [
                "  [%s] %s %s:%d -- %s" % (f.severity, f.id, f.file, f.line, f.claim[:200])
                for _p, f in rows
            ]
            return 0, "\n".join(text)
        if len(args) < 2:
            return 2, VERB_USAGE
        if not branch:
            return 1, "refused: HEAD is on no branch, so no review directory applies"
        items = items_loader() if args[1] == "deferred" else None
        try:
            path = mark(root, branch, args[0], args[1], args[2:], me, items=items)
        except ValueError as exc:
            return 1, "refused: %s" % exc
        return 0, "marked %s %s in %s; the change rides the next commit (or --review-commit)" % (
            args[0],
            args[1],
            path,
        )
    if name == "--review-commit":
        if not branch:
            return 0, "no finished review file is waiting (HEAD is on no branch)"
        return commit_reviews(root, branch)
    if name == "--review-run":
        if not branch:
            return 0, "unreviewed commits: none (HEAD is on no branch)"
        label = _opt(args, "--repo", "console")
        rest = list(args)
        if "--repo" in rest:
            i = rest.index("--repo")
            del rest[i : i + 2]
        shas = rest
        if not shas:
            st = branch_state(root, branch)
            if not st["uncovered"]:
                return 0, "unreviewed commits on %s: none" % branch
            return 0, "unreviewed commits on %s:\n%s" % (
                branch,
                "\n".join(
                    "  %s %s: %s" % (lb, sha[:8], run_command(lb, sha, branch))
                    for lb, sha in st["uncovered"]
                ),
            )
        path = run_review(root, label, shas[0], branch)
        return 0, "review written: %s" % path if path else "nothing written (see the reason above)"
    return 2, VERB_USAGE


# --------------------------------------------------------------------------- CLI

USAGE = """usage:
  wl_review.py --run <sha> --branch <branch> [--repo <console|private/x>] [--root <console>]   review one commit now
  wl_review.py --status [--branch <branch>]                                                    print the branch's review state
"""


def _opt(argv, name, default=""):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main(argv):
    if os.environ.get("COMMIT_REVIEW_CHILD") and "--run" not in argv:
        return 0
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0 if argv else 2
    root = pathlib.Path(_opt(argv, "--root", str(CONSOLE_ROOT)))
    if argv[0] == "--run" and len(argv) >= 2:
        branch = _opt(argv, "--branch") or current_branch(root)
        if not branch:
            sys.stderr.write("no branch: pass --branch\n")
            return 2

        def log(msg):
            print("%s %s" % (now_iso(), msg), flush=True)

        path = run_review(
            root,
            _opt(argv, "--repo", "console"),
            argv[1],
            branch,
            lock_held="--lock-held" in argv,
            log=log,
        )
        print(path or "nothing written")
        return 0
    if argv[0] == "--status":
        branch = _opt(argv, "--branch") or current_branch(root)
        lines = describe(branch_state(root, branch))
        print(
            "per-commit reviews for %s: %s"
            % (branch, "%d line(s) to settle" % len(lines) if lines else "clean")
        )
        for line in lines:
            print("  " + line)
        return 0
    sys.stderr.write(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
