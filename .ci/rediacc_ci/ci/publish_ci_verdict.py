#!/usr/bin/env python3
"""Publish the neutral `CI Verdict` check-run for one Console CI run (agent/plans/PLAN-ci-verdict.md, box D).

WHAT IT POSTS. One check-run named `CI Verdict` on the run's head SHA, always `conclusion: neutral`:

    output.title    one line naming the cause ("cancelled by watchdog budget: '<job>' ran 20.1m (budget 20m)")
    output.summary  `ci_diagnose.render(d, budget_lines=12)`, the compact diagnosis a session reads
    output.text     the `ci-verdict/v1` JSON, which the tracer and the Stop hook parse

WHY NEUTRAL, ALWAYS. The verdict OBSERVES Console CI; it never gates it. A red `CI Verdict` would be a second, confusing red on a head that already has one, and a green one could read as a pass for a run that never finished. Every reader treats the context as non-blocking (`wl_ci.CI_NONBLOCKING_CONTEXTS`, the watchdog and nightly exclude lists, `budget_report.CRITICAL_PATH_EXCLUDE`).

UPSERT, NEWEST WINS. The check-run is PATCHed when one already exists on the SHA and POSTed otherwise. A green attempt therefore overwrites a stale red one. An OLDER (run, attempt) never overwrites a newer one: a late-finishing publish for attempt 1 must not bury attempt 2's answer, and the existing check-run's own JSON says which attempt it describes.

A FAILED DIAGNOSIS STILL POSTS. `diagnose()` reads logs and job lists over the network; when it raises, the publisher posts `verdict: unknown` naming the error rather than crashing, because a missing check-run is indistinguishable from one that has not run yet, and a session would wait on it.

SANITISED. Excerpts are CI log text. Before anything goes up, ANSI escapes and control characters are stripped and token-shaped strings are masked, so a log line that echoed a credential is not republished onto the PR.

`--dry-run` prints the payload and the upsert decision instead of writing, which is how this is proved locally: the workflow that calls it only runs from the default branch after merge.

Exit: 0 posted (or dry-run printed, or skipped for a newer attempt); 1 an argument error or a failed write.
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import json
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any

from rediacc_ci import log
from rediacc_ci.core import ghx
from rediacc_ci.well_known import GH_REPO

if TYPE_CHECKING:
    from collections.abc import Callable

CHECK_NAME = "CI Verdict"
SCHEMA = "ci-verdict/v1"
GENERATOR = "rediacc_ci.ci.publish_ci_verdict"
WORKFLOW = "Console CI"
TITLE_MAX = 200
# GitHub refuses output.summary / output.text above 65535 characters.
OUTPUT_MAX = 65000
RENDER_BUDGET_LINES = 12

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
SECRET_RES = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)\b(authorization:\s*(?:bearer|token|basic)\s+)\S+"),
    re.compile(r"(?i)\b((?:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*)\S{6,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
)
MASK = "***"


# --------------------------------------------------------------------------- sanitising


def sanitise_text(text: str) -> str:
    """ANSI and control characters out, token-shaped strings masked. Newlines and tabs survive."""
    out = ANSI_RE.sub("", str(text))
    out = CONTROL_RE.sub("", out)
    for pattern in SECRET_RES:
        if pattern.groups:
            out = pattern.sub(lambda m: m.group(1) + MASK, out)
        else:
            out = pattern.sub(MASK, out)
    return out


def sanitise(value: Any) -> Any:
    """`sanitise_text` over every string inside a JSON-shaped value."""
    if isinstance(value, str):
        return sanitise_text(value)
    if isinstance(value, list):
        return [sanitise(v) for v in value]
    if isinstance(value, dict):
        return {k: sanitise(v) for k, v in value.items()}
    return value


# --------------------------------------------------------------------------- the verdict


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def unknown_verdict(
    run_id: str, attempt: str, head_sha: str, error: str, conclusion: str = ""
) -> dict:
    """The `ci-verdict/v1` document posted when `diagnose()` itself failed."""
    return {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "generated_at": _now(),
        "head_sha": head_sha,
        "run_id": _int_or(run_id),
        "attempt": _int_or(attempt),
        "workflow": WORKFLOW,
        "conclusion": conclusion,
        "verdict": "unknown",
        "cause": None,
        "first_failure": None,
        "gaps": [],
        "next": "diagnosis failed (%s); run .ci/scripts/ci/ci-trace.py --why locally" % error,
    }


def _int_or(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _fmt_min(value: Any) -> str:
    try:
        return "%.1fm" % float(value)
    except (TypeError, ValueError):
        return "?m"


def title_for(d: dict, headline: str = "") -> str:
    """One line, at most TITLE_MAX characters, naming the cause first.

    The contract's default title is `render()`'s headline, and that is what a verdict with neither a cause nor a failed job gets. A cancelled or red verdict leads with its cause instead, because the headline ("CANCELLED  Console CI run ... -> cancelled") repeats the conclusion the checks list already shows and hides the one fact a reader opened the check for.
    """
    verdict = str(d.get("verdict") or "unknown")
    cause = d.get("cause") or {}
    kind = str(cause.get("kind") or "")
    ff = d.get("first_failure") or {}
    if kind == "watchdog-budget" and cause.get("job"):
        line = "cancelled by watchdog budget: '%s' ran %s (budget %sm)" % (
            cause.get("job"),
            _fmt_min(cause.get("minutes")),
            cause.get("budget_min") if cause.get("budget_min") is not None else "?",
        )
    elif ff and ff.get("name"):
        step = " -- step '%s'" % ff["step"] if ff.get("step") else ""
        cat = " (%s)" % ff["category"] if ff.get("category") else ""
        line = "%s: %s%s%s" % (verdict, ff["name"], step, cat)
    elif kind:
        what = cause.get("job") or cause.get("detail")
        line = "%s: %s%s" % (verdict, kind, " -- %s" % what if what else "")
    elif headline:
        line = headline
    else:
        line = "%s: %s run %s attempt %s" % (
            verdict,
            d.get("workflow") or WORKFLOW,
            d.get("run_id", "?"),
            d.get("attempt", "?"),
        )
    line = " ".join(sanitise_text(line).split())
    return line if len(line) <= TITLE_MAX else line[: TITLE_MAX - 3] + "..."


def _fallback_render(d: dict) -> str:
    return "\n".join(
        [
            title_for(d),
            "run %s attempt %s, conclusion %s"
            % (d.get("run_id"), d.get("attempt"), d.get("conclusion") or "?"),
            "next: %s" % (d.get("next") or "-"),
        ]
    )


def _clip(text: str) -> str:
    return text if len(text) <= OUTPUT_MAX else text[: OUTPUT_MAX - 20] + "\n... (clipped)"


def verdict_json(d: dict) -> str:
    """The text field. Excerpts and gaps are dropped, not cut mid-JSON, if the document is too large."""
    text = json.dumps(d, sort_keys=True)
    if len(text) <= OUTPUT_MAX:
        return text
    slim = dict(d, gaps=[])
    if isinstance(slim.get("first_failure"), dict):
        slim["first_failure"] = dict(slim["first_failure"], excerpt=[])
    return json.dumps(slim, sort_keys=True)


def build_payload(d: dict, rendered: str, head_sha: str) -> dict:
    """The check-run body. `head_sha` is stripped again for a PATCH, which rejects it."""
    clean = sanitise(d)
    rendered = sanitise_text(rendered)
    headline = " ".join(rendered.split("\n", 1)[0].split())
    return {
        "name": CHECK_NAME,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": "neutral",
        "output": {
            "title": title_for(clean, headline),
            "summary": _clip(rendered or _fallback_render(clean)),
            "text": verdict_json(clean),
        },
    }


# --------------------------------------------------------------------------- GitHub I/O (injectable)


class GitHub:
    """The four calls the publisher makes. Tests pass a fake with the same methods."""

    def __init__(self, repo: str) -> None:
        self.repo = repo

    def get(self, path: str) -> Any:
        return ghx.api_json(path, attempts=3)

    def write(self, method: str, path: str, payload: dict) -> int:
        try:
            proc = subprocess.run(
                ["gh", "api", "-X", method, path, "--input", "-"],
                input=json.dumps(payload).encode("utf-8"),
                stdout=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            return 127
        return proc.returncode


def existing_check(gh: Any, repo: str, head_sha: str) -> dict | None:
    """The newest `CI Verdict` check-run github-actions posted on the SHA, or None. A failed lookup is None (POST is the safe direction)."""
    try:
        body = gh.get(
            "repos/%s/commits/%s/check-runs?check_name=%s&per_page=100"
            % (repo, head_sha, "CI%20Verdict")
        )
    except ghx.GhError as exc:
        log.warn("check-run lookup failed, will POST: %s" % str(exc)[:200])
        return None
    runs = [
        r
        for r in (body or {}).get("check_runs") or []
        if (r.get("app") or {}).get("slug") == "github-actions"
    ]
    return runs[-1] if runs else None


def _key(d: Any) -> tuple[int, int]:
    try:
        return int(d.get("run_id") or 0), int(d.get("attempt") or 0)
    except (TypeError, ValueError, AttributeError):
        return 0, 0


def is_newer(existing: dict | None, mine: dict) -> bool:
    """True when the existing check-run describes a NEWER (run, attempt) than `mine`."""
    if not existing:
        return False
    try:
        theirs = json.loads(((existing.get("output") or {}).get("text")) or "{}")
    except ValueError:
        return False
    if not isinstance(theirs, dict) or theirs.get("schema") != SCHEMA:
        return False
    return _key(theirs) > _key(mine)


def upsert(
    gh: Any, repo: str, payload: dict, verdict: dict, *, dry_run: bool = False, out=None
) -> int:
    """PATCH the existing check-run, else POST one. Returns an exit code."""
    out = out or sys.stdout
    head_sha = payload["head_sha"]
    found = existing_check(gh, repo, head_sha)
    if found is not None and is_newer(found, verdict):
        log.info("check-run %s already describes a newer run/attempt; leaving it" % found.get("id"))
        if dry_run:
            out.write("would SKIP: check-run %s describes a newer run/attempt\n" % found.get("id"))
        return 0
    if found:
        method, path, body = (
            "PATCH",
            "repos/%s/check-runs/%s" % (repo, found["id"]),
            {k: v for k, v in payload.items() if k != "head_sha"},
        )
    else:
        method, path, body = "POST", "repos/%s/check-runs" % repo, payload
    if dry_run:
        out.write("would %s %s\n" % (method, path))
        out.write(json.dumps(body, indent=2) + "\n")
        return 0
    rc = gh.write(method, path, body)
    if rc != 0:
        log.error("%s %s failed with exit %d" % (method, path, rc))
        return 1
    log.info("%s %s: %s = neutral (%s)" % (method, path, CHECK_NAME, payload["output"]["title"]))
    return 0


# --------------------------------------------------------------------------- orchestration


def load_diagnose() -> Any:
    """`rediacc_ci.ci.ci_diagnose`, imported late so a test can inject a stub and a broken import posts `unknown`."""
    return importlib.import_module("rediacc_ci.ci.ci_diagnose")


def resolve_run(
    gh: Any, repo: str, run_id: str, attempt: str, head_sha: str
) -> tuple[str, str, str, str]:
    """Fill an empty attempt / head SHA from the run itself (the workflow_dispatch path). Returns (attempt, head_sha, pr_head, conclusion)."""
    run: dict = {}
    if not (attempt and head_sha):
        run = gh.get("repos/%s/actions/runs/%s" % (repo, run_id)) or {}
    attempt = attempt or str(run.get("run_attempt") or "")
    head_sha = head_sha or str(run.get("head_sha") or "")
    pr_head = head_sha
    prs = run.get("pull_requests") or []
    if prs and isinstance(prs[0], dict):
        pr_head = str(((prs[0].get("head") or {}).get("sha")) or head_sha)
    return attempt, head_sha, pr_head, str(run.get("conclusion") or "")


def make_fetch(mod: Any, repo: str) -> Any:
    """`GhFetcher` everywhere. `gh` is on every runner, ubuntu-slim included, and reads `GH_TOKEN` itself, so the publisher never holds the token and the local dry-run and the CI run read through the same client."""
    return mod.GhFetcher(repo)


def compute(
    run_id: str,
    attempt: str,
    head_sha: str,
    pr_head: str,
    loader: Callable[[], Any] = load_diagnose,
    repo: str = GH_REPO,
) -> tuple[dict, str]:
    """(verdict, rendered). Never raises: a failed diagnose becomes `verdict: unknown`."""
    try:
        mod = loader()
        d = mod.diagnose(
            make_fetch(mod, repo),
            int(run_id),
            attempt=int(attempt) if str(attempt).isdigit() else None,
            pr_head=pr_head or head_sha,
        )
        if not isinstance(d, dict):
            raise TypeError("diagnose returned %s, not a dict" % type(d).__name__)
    except Exception as exc:  # noqa: BLE001 -- the whole point: post `unknown`, never crash
        d = unknown_verdict(
            run_id, attempt, head_sha, "%s: %s" % (type(exc).__name__, str(exc)[:300])
        )
        return d, _fallback_render(d)
    d.setdefault("schema", SCHEMA)
    d.setdefault("head_sha", head_sha)
    if attempt and not d.get("attempt"):
        d["attempt"] = _int_or(attempt)
    try:
        rendered = mod.render(d, budget_lines=RENDER_BUDGET_LINES)
    except Exception as exc:  # noqa: BLE001 -- a render bug must not lose the verdict
        log.warn("render failed (%s: %s); posting the fallback summary" % (type(exc).__name__, exc))
        rendered = _fallback_render(d)
    return d, rendered


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="publish_ci_verdict", description=__doc__.split("\n", 1)[0])
    p.add_argument("--run-id", required=True, help="Console CI run id")
    p.add_argument("--attempt", default="", help="run attempt (empty: read from the run)")
    p.add_argument("--head-sha", default="", help="head SHA to post on (empty: read from the run)")
    p.add_argument(
        "--pr-head",
        default="",
        help="the PR's current head, for superseded attribution (empty: from the run)",
    )
    p.add_argument("--repo", default=GH_REPO, help="owner/name (default: the well-known repo)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the payload and the upsert decision; write nothing",
    )
    return p.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    gh: Any = None,
    loader: Callable[[], Any] = load_diagnose,
    out=None,
) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not args.run_id.isdigit():
        log.error("--run-id must be numeric, got %r" % args.run_id)
        return 1
    repo = args.repo or GH_REPO
    gh = gh or GitHub(repo)
    try:
        attempt, head_sha, pr_head, conclusion = resolve_run(
            gh, repo, args.run_id, args.attempt, args.head_sha
        )
    except ghx.GhError as exc:
        log.error("could not read run %s: %s" % (args.run_id, str(exc)[:300]))
        return 1
    if not head_sha:
        log.error(
            "run %s has no head SHA; refusing to post a check-run with no anchor" % args.run_id
        )
        return 1
    d, rendered = compute(args.run_id, attempt, head_sha, args.pr_head or pr_head, loader, repo)
    if conclusion and not d.get("conclusion"):
        d["conclusion"] = conclusion
    payload = build_payload(d, rendered, head_sha)
    return upsert(gh, repo, payload, d, dry_run=args.dry_run, out=out)


if __name__ == "__main__":
    raise SystemExit(main())
