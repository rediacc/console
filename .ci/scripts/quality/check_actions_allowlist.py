#!/usr/bin/env python3
"""check:ci-actions-allowlist -- every third-party action must be one this repo may run.

THE GAP THIS CLOSES, from a measurement rather than from theory. rediacc/console
restricts which actions may run (`allowed_actions: selected`). That constraint lives in
repository SETTINGS, so no gate could see it, and the Bitwarden composite's pinned
sm-action was simply not on the list. CI run 33690518859 failed at the first job with

    The action bitwarden/sm-action@1238aae8... is not allowed in rediacc/console

before any secret was fetched -- an action-resolution error that names no secret, on a
PR whose entire subject is secrets. The cost was a full CI round to learn a fact that is
a pure text comparison once the allowlist is written down.

So `.ci/config/actions-allowlist.json` is a committed copy of the settings, refreshed by
`--refresh` (the ONLY place a token is used), and this gate compares it offline against
every `uses:` in the workflow and composite-action corpus. A gate that needed a token
would degrade to "passed" wherever the token is absent, which is the shape
check_secret_reachability records at its own top and the reason the split exists.

WHAT IT DELIBERATELY DOES NOT CLAIM. `verified_allowed` permits any Marketplace-VERIFIED
creator, and verification status is not knowable offline. An action permitted ONLY by
that route must therefore be listed in `verified_exceptions` with the run that proves it
ran. The list is empty today, and that is the strongest state: every third-party action
here is permitted by a pattern or by being GitHub-owned. If it ever fills up, each entry
is a place where this gate is trusting a record instead of deriving an answer.

PATTERN SEMANTICS, matching GitHub's own: `owner/*`, `owner/repo`, and `owner/repo@ref`.
An `@ref` pattern is EXACT on the ref, which is why allowing
`bitwarden/sm-action@<sha>` rather than `bitwarden/*` makes a pin bump a two-place
change -- deliberate, and stated in the composite's header beside the pin.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("ACTIONS_ALLOWLIST_ROOT") or Path(__file__).resolve().parents[3])
RECORD = ROOT / ".ci" / "config" / "actions-allowlist.json"

# `uses: owner/repo[/path]@ref`. A leading `./` is a local action and never checked --
# it ships in this repo, so the allowlist has nothing to say about it. `docker://` is
# a container reference, also out of scope.
USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^'\"\s#]+)", re.MULTILINE)
# GitHub-owned owners, per the error message's "created by GitHub".
GITHUB_OWNED = frozenset({"actions", "github"})
# Floor: a corpus this small cannot be the whole repo. Measured 2026-09-03: 17 distinct
# third-party actions across 28 workflow files and the composites.
MIN_ACTIONS = int(os.environ.get("ACTIONS_ALLOWLIST_MIN", "8"))


def corpus() -> list[Path]:
    out: list[Path] = []
    for d, pat in (
        (ROOT / ".github" / "workflows", "*.yml"),
        (ROOT / ".ci" / "breakpoint" / "workflow", "*.yml"),
    ):
        if d.is_dir():
            out += sorted(d.glob(pat))
    actions = ROOT / ".github" / "actions"
    if actions.is_dir():
        out += sorted(actions.rglob("action.yml"))
    return out


def used_actions(files: list[Path]) -> dict[str, set[str]]:
    """{owner/repo@ref: {files that use it}}, third-party only."""
    out: dict[str, set[str]] = {}
    for f in files:
        for ref in USES_RE.findall(f.read_text(encoding="utf-8", errors="replace")):
            if ref.startswith((".", "docker://")):
                continue
            out.setdefault(ref, set()).add(str(f.relative_to(ROOT)))
    return out


def permitted(ref: str, record: dict) -> bool:
    """Does `ref` match this repo's policy? Pure, so the controls drive the real rule."""
    owner_repo, _, at_ref = ref.partition("@")
    owner = owner_repo.split("/", 1)[0]
    # A path inside a repo (actions/cache/restore) is governed by the repo.
    base = "/".join(owner_repo.split("/")[:2])
    if record.get("github_owned_allowed") and owner in GITHUB_OWNED:
        return True
    for pat in record.get("patterns_allowed") or []:
        p_repo, _, p_ref = pat.partition("@")
        # An `@ref` pattern is EXACT on the ref; a bare pattern accepts any ref.
        if p_repo in (f"{owner}/*", base, owner_repo) and (not p_ref or p_ref == at_ref):
            return True
    return base in (record.get("verified_exceptions") or {})


def refresh(record_path: Path) -> int:
    repo = json.loads(record_path.read_text(encoding="utf-8")).get("repo", "rediacc/console")
    proc = subprocess.run(
        ["gh", "api", f"/repos/{repo}/actions/permissions/selected-actions"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(f"✗ could not read the allowlist for {repo}: {proc.stderr.strip()}", file=sys.stderr)
        return 1
    live = json.loads(proc.stdout)
    doc = json.loads(record_path.read_text(encoding="utf-8"))
    import datetime as dt

    doc["refreshed_at"] = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for k in ("github_owned_allowed", "verified_allowed", "patterns_allowed"):
        doc[k] = live.get(k)
    record_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"✓ refreshed {record_path.name} from {repo}: {len(doc['patterns_allowed'])} pattern(s)")
    return 0


def selftest(record: dict) -> int:
    """Control-first. The rule is a matcher, so it is proven on both answers."""
    bad = 0
    fake = {
        "github_owned_allowed": True,
        "patterns_allowed": [
            "docker/*",
            "bitwarden/sm-action@abc123",
            "softprops/action-gh-release",
        ],
        "verified_exceptions": {"someone/thing": "reason"},
    }
    cases = [
        ("actions/checkout@v5", True, "a GitHub-owned action is permitted"),
        ("actions/cache/restore@v4", True, "a path inside a GitHub-owned repo is permitted"),
        ("docker/login-action@v3", True, "an owner wildcard matches"),
        ("bitwarden/sm-action@abc123", True, "an @ref pattern matches its exact ref"),
        ("bitwarden/sm-action@deadbee", False, "an @ref pattern does NOT match a different ref"),
        ("bitwarden/other-action@abc123", False, "an @ref pattern does not widen to the owner"),
        ("softprops/action-gh-release@v2", True, "a bare owner/repo pattern accepts any ref"),
        ("someone/thing@v1", True, "a verified_exceptions entry is honoured"),
        ("evil/backdoor@v1", False, "an unlisted third party is refused"),
    ]
    for ref, want, label in cases:
        got = permitted(ref, fake)
        ok = got == want
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            bad += 1
            print(f"        permitted({ref!r}) = {got}, want {want}")
    # The github_owned switch must actually switch.
    if permitted("actions/checkout@v5", dict(fake, github_owned_allowed=False)):
        print("  FAIL  github_owned_allowed=false is ignored")
        bad += 1
    else:
        print("  PASS  CONTROL: github_owned_allowed=false stops permitting actions/*")
    return bad


def main(argv: list[str]) -> int:
    if not RECORD.is_file():
        print(
            f"VACUOUS INPUT: {RECORD.name} is missing, so nothing can be compared", file=sys.stderr
        )
        return 1
    if "--refresh" in argv:
        return refresh(RECORD)
    try:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"VACUOUS INPUT: {RECORD.name} does not parse ({exc})", file=sys.stderr)
        return 1

    print("actions allowlist: controls first, then the verdict")
    if selftest(record):
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2

    files = corpus()
    used = used_actions(files)
    if len(used) < MIN_ACTIONS or not files:
        print(
            f"VACUOUS INPUT: found {len(used)} third-party action(s) across {len(files)} "
            f"file(s), floor is {MIN_ACTIONS}. The corpus scan lost the workflows; "
            f"refusing a verdict rather than reporting a clean allowlist for files "
            f"nobody read",
            file=sys.stderr,
        )
        return 1

    problems = [
        f"{ref} is used by {', '.join(sorted(where))} but this repository may not run "
        f"it. The job fails at action RESOLUTION, before any step, with a message that "
        f"names no secret and no script. Add a pattern to "
        f"/repos/{record.get('repo')}/actions/permissions/selected-actions and re-run "
        f"with --refresh, or use an action that is already permitted."
        for ref, where in sorted(used.items())
        if not permitted(ref, record)
    ]
    if problems:
        print(f"✗ actions allowlist ({len(problems)} problem(s)):", file=sys.stderr)
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        return 1

    print(
        f"✓ actions allowlist: all {len(used)} third-party action(s) across {len(files)} "
        f"file(s) are permitted by {RECORD.name} (floor {MIN_ACTIONS}, "
        f"{len(record.get('patterns_allowed') or [])} pattern(s))"
    )
    ve = record.get("verified_exceptions") or {}
    print(
        f"  Blind spot: `verified_allowed` is {record.get('verified_allowed')}, and "
        f"Marketplace verification is not knowable offline. {len(ve)} action(s) rely on "
        f"it and are listed explicitly; the rest are matched by pattern or GitHub-owned."
    )
    print(f"  The record was refreshed {record.get('refreshed_at')}; re-run with --refresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
