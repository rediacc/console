"""Every Cloudflare deploy workflow that builds the account portal feeds it the Turnstile site key and proves the build contains it.

WHY. On 2026-09-24 every production login failed with "Captcha verification required": the account worker enforces Turnstile whenever its secret is set (private/account/src/app.ts), but the deployed portal had been built with an empty `VITE_TURNSTILE_SITE_KEY` (the v1.3.12 workflows read the since-deleted `vars.TURNSTILE_SITE_KEY`), so no widget rendered. Nothing in CI could see it: the build succeeds with an empty key, and no gate read the workflows for it.

WHAT IT CHECKS, in every `.github/workflows/cd-deploy-*.yml`: each step that runs `vite build` for the account portal into a `workers/<name>/dist/account` directory must
  1. set `VITE_TURNSTILE_SITE_KEY` from the Bitwarden-fetched env (`env.BWS_TURNSTILE_SITE_KEY`), never from `vars.*` or a literal, and
  2. be followed, in the same job, by a step that fails when the key is empty or absent from that output directory (a `grep` of the key over `<dir>/assets` plus an empty-key `test -n`).

Self-hosted image builds (ci-build-docker.yml) and the CI e2e build (ci.yml) are out of scope: they build keyless or with a per-run widget on purpose.

Exit 0 clean, 1 on findings, 2 when the gate's own controls fail (controls_first convention).
"""

from __future__ import annotations

import copy
import re
import sys
from typing import TYPE_CHECKING, Any

import yaml

from rediacc_ci import paths
from rediacc_ci.controls import controls_first

if TYPE_CHECKING:
    import pathlib

WORKFLOW_GLOB = ".github/workflows/cd-deploy-*.yml"
_OUTDIR = re.compile(r"vite build\b.*?--outDir\s+(?:\.\./)*(workers/[\w.-]+/dist/account)")
_BWS_KEY = re.compile(r"^\$\{\{\s*env\.BWS_TURNSTILE_SITE_KEY\s*\}\}$")


def findings_for(name: str, doc: dict) -> list[str]:
    out: list[str] = []
    for job_id, job in (doc.get("jobs") or {}).items():
        steps = (job or {}).get("steps") or []
        for i, step in enumerate(steps):
            run = str(step.get("run") or "")
            m = _OUTDIR.search(run)
            if not m:
                continue
            outdir = m.group(1)
            label = "%s job %s step %r" % (name, job_id, step.get("name") or i)
            key = str(((step.get("env") or {}).get("VITE_TURNSTILE_SITE_KEY")) or "")
            if not _BWS_KEY.match(key.strip()):
                out.append(
                    "%s: VITE_TURNSTILE_SITE_KEY is %r, not ${{ env.BWS_TURNSTILE_SITE_KEY }}"
                    % (label, key)
                )
            later = " ".join(str(s.get("run") or "") for s in steps[i + 1 :])
            if not (
                re.search(r"test -n \"\$VITE_TURNSTILE_SITE_KEY\"", later)
                and outdir + "/assets" in later
            ):
                out.append(
                    "%s: no later step fails when the site key is empty or missing from %s/assets"
                    % (label, outdir)
                )
    return out


def findings(root: pathlib.Path) -> list[str]:
    files = sorted(root.glob(WORKFLOW_GLOB))
    if not files:
        return ["no %s found: the gate would pass vacuously" % WORKFLOW_GLOB]
    out: list[str] = []
    builds = 0
    for f in files:
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        builds += sum(
            1
            for job in (doc.get("jobs") or {}).values()
            for s in ((job or {}).get("steps") or [])
            if _OUTDIR.search(str(s.get("run") or ""))
        )
        out.extend(findings_for(f.name, doc))
    if builds == 0:
        out.append(
            "no portal build step found in %s: the gate would pass vacuously" % WORKFLOW_GLOB
        )
    return out


_GUARDED: dict[str, Any] = {
    "jobs": {
        "d": {
            "steps": [
                {
                    "name": "Build account portal",
                    "run": "npm install && npx vite build --outDir ../../../workers/account/dist/account",
                    "env": {"VITE_TURNSTILE_SITE_KEY": "${{ env.BWS_TURNSTILE_SITE_KEY }}"},
                },
                {
                    "name": "Portal carries the Turnstile site key",
                    "run": 'test -n "$VITE_TURNSTILE_SITE_KEY" || exit 1\n'
                    'grep -rqF -- "$VITE_TURNSTILE_SITE_KEY" workers/account/dist/account/assets || exit 1',
                },
            ]
        }
    }
}


def selftest() -> bool:
    """True when a control FAILED."""
    failed = False
    if findings_for("ok.yml", _GUARDED):
        print("✗ control: a guarded build read as a finding", file=sys.stderr)
        failed = True
    vars_key = copy.deepcopy(_GUARDED)
    vars_key["jobs"]["d"]["steps"][0]["env"]["VITE_TURNSTILE_SITE_KEY"] = (
        "${{ vars.TURNSTILE_SITE_KEY }}"
    )
    if not findings_for("vars.yml", vars_key):
        print("✗ control: the 2026-09-24 vars.* key source was not reported", file=sys.stderr)
        failed = True
    no_guard = copy.deepcopy(_GUARDED)
    del no_guard["jobs"]["d"]["steps"][1]
    if not findings_for("noguard.yml", no_guard):
        print("✗ control: a build with no key-presence step was not reported", file=sys.stderr)
        failed = True
    return failed


def main(argv: list[str]) -> int:
    rc = controls_first("portal Turnstile site-key guard", selftest)
    if rc or "--selftest" in argv:
        return rc
    found = findings(paths.repo_root())
    if found:
        print("✗ %d portal site-key finding(s):" % len(found), file=sys.stderr)
        for f in found:
            print("    %s" % f, file=sys.stderr)
        return 1
    print(
        "✓ every cd-deploy portal build takes the Bitwarden site key and proves the build contains it"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
