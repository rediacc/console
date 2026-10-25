#!/usr/bin/env python3
"""Port of `.ci/scripts/security/check-ci-workflow-invariants.sh`.

W7P6 wave 27. The bash twin stays the LIVE registered gate; this module is its VERIFIED-EQUIVALENT ALTERNATIVE, proved byte-for-byte on both streams by
`.ci/rediacc_ci/tests/test_security_ci_workflow_invariants.py` and by the K=5
shadow ledger `.ci/shadow/w7p6-check-ci-workflow-invariants.observations.jsonl`. Nothing is repointed at this file. Cutover is a separate, later, driver-only step.

NAMING. `check_` is dropped from the module name to match the closest sibling already in this package, `rediacc_ci.security.workflow_gates` (the port of `check-workflow-gates.sh`). `check_commands.py` and `rdc_sh_env_check.py` kept their prefixes; the package is not internally consistent, so the rule applied here is "match the nearest shape", not "match the package".

WHAT THE TWIN DOES, AND HOW MUCH OF IT IS ALREADY PYTHON. 224 lines, of which 103 (`:66-168`) are the body of a `python3 - <<'PY'` heredoc that parses the workflow with PyYAML and prints tab-separated findings on stdout. The bash around it does three things and no more: resolve `$WORKFLOW_FILE`, refuse a missing file, and translate each finding kind into one long `log_error`
sentence. So this port is a transcription of the heredoc plus a translation of the ~40-line orchestrator.

THE SIX INVARIANTS, all read from the PARSED document rather than grepped, so a reflowed `if:` or a reordered `with:` map cannot silently unenforce one:

  1. `channel-as-docker-tag` -- a job passing a channel-derived `docker_tag`
     must refuse an empty channel in its `if:`.
  2. `no-candidates` -- and if NO job passes one, the gate has verified nothing
     and says so instead of printing an unearned green.
  3. `skip-release` -- the bump-none decision is declared once in `initialize`,
     passed to every caller of `cd-stage.yml`, gates both pre-publish
     validators, and is not re-decided in `finalize-release-sentinel`.
  4. `no-jobs` -- a workflow with no jobs is a failure, never a pass.
  5. `workflow-missing` -- likewise a missing file.
  6. an unparseable workflow is a failure, never a pass.
  7. `root-ancestor-conditional` -- no ancestor of `initialize` (a job in its
     transitive `needs`) carries a job-level `if:`. Added after the twin was
     deleted, so no differential covers it: a job's implicit `success()` reads
     every ANCESTOR, so a skipped ancestor skips every job downstream of
     `initialize` that has no status function, with `initialize` itself
     green. PR #597's run 37465283674 (2026-10-06): `duplicate-run` ran on
     push only, skipped on the PR, and `run-sh-tests` skipped with it.

THE RELEASE-ORDER PHASE (added 2026-10-08, PLAN-cd-errors-in-ci W5 + the W4 pins), also after the twin, also with no differential. It reads three files, `ci.yml`, `cd-v2.yml` and `.github/actions/app-token/action.yml`, and refuses any job graph in which ci.yml's finalize-release-sentinel has sealed `cli/v<V>/.released` and cd-v2's version-tag step can still be skipped by a failure or by retry_mode.
CD run 37749637824 is the case: the tag lived in `tag-and-release`, behind post-publish install validation, a Rocky 9 DNF stall reddened that validation, and the sealed v2.2.0 sentinel was left with no tag. Its kinds are `RELEASE_KINDS`:

  * `release-order-no-sentinel-writer` / `release-order-no-tag-step` -- the
    premise is gone (no sealing step in ci.yml, or no `git tag -a` + `git push
    origin v...` step in cd-v2.yml), so the phase checked nothing. Vacuity is red.
  * `release-order-dispatch-split` -- the dispatch step does not IMMEDIATELY
    follow the seal under the identical `if:`.
  * `release-order-tag-behind-job` -- the job holding the tag step has a
    transitive `needs` outside `TAG_ALLOWED_ANCESTORS` (anything that can fail
    or skip after the seal).
  * `release-order-tag-skipped-on-retry` -- that job's or step's `if:` reads
    `retry_mode`.
  * `cd-contents-write` -- any cd-v2 job, or the workflow, holds `contents:
    write`; every write rides the cd App token instead.
  * `cd-push-not-app-token` -- a cd-v2 `git push` whose job mints no cd-preset
    App token before it, or whose last checkout before it carries another token.
  * `cd-preset-no-workflows` -- app-token's `cd` preset no longer requests
    `workflows: write`, or the mint no longer passes `permission-workflows`. A
    tag over a range that touches .github/workflows is then refused (v1.3.11,
    v1.3.8).

THE CD-PREFLIGHT PINS (PLAN-cd-errors-in-ci W4) ride the same phase and read a fourth file, `housekeeping.yml` (`HOUSEKEEPING_WORKFLOW_FILE` overrides it). `rediacc_ci.release.cd_preflight` must run at three sites, each with at least the checks `PREFLIGHT_REQUIRED_CHECKS` names (`cd-preflight-narrowed` otherwise):

  * `cd-preflight-no-pr-job` / `cd-preflight-not-on-pr` -- a ci.yml job runs
    `--phase pr`, and its `if:` admits pull_request. A push-only preflight is the
    main-only blind spot that let the 10-07 drift reach main.
  * `cd-preflight-no-cd-step` / `cd-preflight-before-tag` -- a cd-v2 step runs
    `--phase cd` in the version tag step's job, AFTER it: v<V> is sealed and
    untagged until that step, so a preflight before it reds every release.
  * `cd-preflight-no-housekeeping-step` / `cd-preflight-housekeeping-bypassed` --
    a preflight step precedes every `cleanup_versions` step in its job, and
    neither carries an `if:` that would run the cleanup past a red preflight.

THE EXTERNAL-GATE PINS (operator rulings 2026-10-13, "Everything fails closed, nightly included", and 2026-10-14, "Extend to all seven") ride the same phase and read a fifth file, `ci-quality.yml` (`QUALITY_WORKFLOW_FILE` overrides it). Every gate that asks a host outside the repository (`UPSTREAM_GATES`: the four pin freshness gates, actions, external links, DKIM, Go dependencies and npm dependencies) is hard on a pull request, on the nightly and on a dispatch.
`analyse_upstream_gates` refuses: a gate with no step; an `if:` other than the lane guard plus the label hold (a gate-bind shard conjunct `matrix.shard == N` is allowed, since it cannot tell one cadence from another); a job whose announcer does not name the gate under `no-external-quality`; and a ci.yml whose `external_quality` can resolve to `skip` off a pull request.

THE WORKFLOW-ESTATE PINS (2026-10-23) ride the same phase and read EVERY workflow and composite action (`estate_files`, the set `check:ci-workflows` walks): `pipe-no-pipefail` refuses a `run:` that pipes with no pipefail in force (commit 41437ea6f), and `dispatch-write-off-default-branch` refuses a write-capable job in a `workflow_dispatch` workflow without `DEFAULT_BRANCH_GUARD` as a top-level `&&` conjunct of its `if:` (commit f8d184807). Zero files or zero run steps is red. The comment block above `PIPEFAIL_KINDS` carries the rules.

WHEN IT RUNS. Only when the ci.yml under test IS the real one, or when `CD_WORKFLOW_FILE` is set explicitly. The recorded fixture cases point `WORKFLOW_FILE` at a synthetic ci.yml; judging the live cd-v2.yml beside a synthetic ci.yml would mix two worlds, and adding bytes to those runs would falsify the twin's goldens. `npm run check:ci-workflow-invariants` and the gate test both drive the real ci.yml, so both run this phase,
and its success line prints the shape (tag job, its ancestors, job count, push count) so a collapse is visible.

NO EXTERNAL PROCESS IS INVOLVED, ON EITHER SIDE. The twin shells out to exactly
one thing, `python3`, and only to run the heredoc that is transcribed below;
there is no `yq`, no `jq`, no `gh`, no network. That is why the differential needs no recording fakes at all and drives both sides over fixture YAML through `$WORKFLOW_FILE`, which the twin already exposes for its own gate test.

PORT NOTES -- unless an item says otherwise it is REPRODUCED, not repaired. Fixing one only HERE would make the differential lie.

  * THE `python3` PROBE IS KEPT, and it is the one line of the twin that cannot
    literally hold here: `command -v python3 || exit 2` runs before the heredoc,
    and this module IS python3. It is reproduced anyway (`shutil.which`) so the
    exit-2 setup-error path stays reachable and stays differential-comparable,
    rather than becoming a branch only one side has. See
    `test_missing_python3_is_a_setup_error`.

  * A HEREDOC CRASH IS EXIT 1, NOT A PROPAGATED 2. When the inner Python raises,
    bash's `|| { rc=$?; log_error ...; exit 1; }` swallows the code and exits 1,
    having printed the traceback (which is NOT captured by the command
    substitution, so it reaches the terminal) followed by the INVARIANT-FAIL
    line. `_guarded` below reproduces that shape exactly, including the ordering
    of traceback-then-message. The two tracebacks name different files, so
    `test_a_scalar_document_crashes_the_analysis_on_both_sides` compares the
    exit code and stdout byte-for-byte and the stderr with the traceback block
    elided; everything else in the differential is byte-for-byte on both
    streams with nothing elided.

  * SETUP EXIT 2 FROM THE HEREDOC BECOMES EXIT 1 TOO. `sys.exit(2)` for an
    unimportable PyYAML or an unparseable document is caught by the same `||`,
    so the twin's own "Exit ... 2 setup error" header comment is only true of
    the `command -v python3` probe. Reproduced, not repaired.

  * `${WORKFLOW_FILE:-...}` IS AN EMPTY-OR-UNSET DEFAULT. `os.environ.get(name)
    or default`, never `os.environ.get(name, default)`: an exported-empty
    `WORKFLOW_FILE` must fall back, not resolve to the repository root.

ONE NAMED DIVERGENCE THIS PORT ADDS, the same one `workflow_gates` documents: `paths.repo_root()` honours `$REDIACC_CI_ROOT` and the twin's
`${BASH_SOURCE[0]}/../../..` does not. The differential never sets it, and the
two files sit at the same depth (`.ci/scripts/security/x.sh` and `.ci/rediacc_ci/security/x.py` are both three levels below the root), so a fixture that copies both to their real relative paths gets the same answer from each.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import traceback
import typing

from rediacc_ci import log, paths

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    from types import ModuleType

# The finding kinds this gate can emit, in the order the analysis emits them. Listed as a constant so a reader can see the whole vocabulary without walking the analysis, and so `main`'s translation table can be checked against it.
KINDS = (
    "no-jobs",
    "ungated",
    "no-candidates",
    "skip-release-not-passed",
    "skip-release-no-output",
    "skip-release-no-init",
    "skip-release-no-stage",
    "skip-release-missing-job",
    "skip-release-validator-ungated",
    "skip-release-second-decision",
    "root-ancestor-conditional",
)


class SetupExitError(Exception):
    """The heredoc's `sys.stderr.write(...); sys.exit(2)` pair, as an object.

    Carried rather than raised as SystemExit so `_guarded` can tell a deliberate setup exit from a crash: bash treats them identically (both take the `||` branch and both become exit 1), but the STDERR differs -- a setup exit writes one `SETUP: ...` line and a crash writes a traceback -- and a port that conflated them would print the wrong bytes on one of the two paths.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def load_workflow(path: str) -> dict:
    """`:66-78`: import PyYAML, then parse the file. Both failures are SETUP.

    Returns whatever `yaml.safe_load` returned, which is deliberately NOT narrowed to a dict: the twin passes the raw value straight to
    `(doc or {}).get("jobs")`, so a scalar or a list crashes with an
    AttributeError there rather than being rejected here, and that crash is a reproduced behaviour (see the module docstring).
    """
    yaml = _import_yaml()
    if yaml is None:
        raise SetupExitError("SETUP: PyYAML is not importable\n")
    try:
        # `io.open(path, encoding="utf-8")` in the twin. The handle is left to
        # the garbage collector there; closed properly here, which changes no observable byte.
        with open(path, encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except Exception as exc:  # the twin catches bare `Exception` here too
        raise SetupExitError("SETUP: %s does not parse as YAML: %s\n" % (path, exc)) from exc


def _import_yaml() -> ModuleType | None:
    try:
        import yaml
    except ImportError:
        return None
    return yaml


def analyse(doc: object) -> list[tuple[str, str]]:
    """`:80-168`, verbatim in behaviour: the parsed document to (kind, name) pairs.

    Exported so the selftest can drive every branch without a subprocess. The
    return value is the tab-separated stdout of the heredoc, split -- one tuple
    per printed line, IN THE PRINTED ORDER, because the twin's translation loop emits one `log_error` per line in exactly that order and a reordering would be a visible difference.
    """
    out: list[tuple[str, str]] = []
    # A non-mapping document raises here, exactly as the twin's heredoc does;
    # the crash is reproduced, not repaired. See the module docstring.
    jobs = typing.cast("dict[str, object]", doc or {}).get("jobs") or {}
    if not isinstance(jobs, dict) or not jobs:
        out.append(("no-jobs", "<none>"))
        return out

    candidates = 0
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        with_map = job.get("with")
        tag = (with_map if isinstance(with_map, dict) else {}).get("docker_tag")
        if not isinstance(tag, str) or "channel" not in tag:
            continue
        candidates += 1
        cond = job.get("if")
        cond = "" if cond is None else str(cond)
        # Accept any spelling that requires the channel to be non-empty.
        ok = ("channel != ''" in cond.replace('"', "'")) or (
            "channel!=''" in cond.replace('"', "").replace(" ", "")
        )
        if not ok:
            out.append(("ungated", str(name)))

    if candidates == 0:
        out.append(("no-candidates", "<none>"))

    # ---------------------------------------------------------------- skip-release Scoped by the UPLOADER PATH, not by job name: a workflow with no `initialize` job is a different workflow, not a broken ci.yml, and keying on the names hard-failed every synthetic fixture the twin's gate test drives through WORKFLOW_FILE.
    stagers = [
        n
        for n, j in jobs.items()
        if isinstance(j, dict) and str(j.get("uses") or "").endswith("cd-stage.yml")
    ]

    if stagers:
        for n in stagers:
            w = jobs[n].get("with")
            if not isinstance(w, dict) or "skip_release" not in w:
                out.append(("skip-release-not-passed", str(n)))

        init = jobs.get("initialize")
        if isinstance(init, dict):
            outs = init.get("outputs")
            if not isinstance(outs, dict) or "skip_release" not in outs:
                out.append(("skip-release-no-output", "initialize"))
        else:
            out.append(("skip-release-no-init", "initialize"))
    elif "finalize-release-sentinel" in jobs:
        out.append(("skip-release-no-stage", "<no job uses cd-stage.yml>"))

    if stagers:
        for vname in ("validate-install", "validate-promote"):
            v = jobs.get(vname)
            if not isinstance(v, dict):
                out.append(("skip-release-missing-job", vname))
                continue
            cond = v.get("if")
            cond = "" if cond is None else str(cond).replace('"', "'")
            if "skip_release" not in cond:
                out.append(("skip-release-validator-ungated", vname))

    out.extend(
        ("root-ancestor-conditional", name)
        for name in _root_ancestors(jobs, "initialize")
        if "if" in jobs[name]
    )

    fin = jobs.get("finalize-release-sentinel")
    if isinstance(fin, dict):
        steps = fin.get("steps")
        steps = steps if isinstance(steps, list) else []
        for st in steps:
            if isinstance(st, dict) and "--decide-only" in str(st.get("run") or ""):
                out.append(("skip-release-second-decision", "finalize-release-sentinel"))
                break

    return out


def _needs(job: dict) -> list[str]:
    needs = job.get("needs")
    if isinstance(needs, str):
        return [needs]
    return [str(n) for n in needs] if isinstance(needs, list) else []


def _root_ancestors(jobs: dict, root: str) -> list[str]:
    """Every job `root` needs, transitively, in discovery order; [] when `root` is absent."""
    start = jobs.get(root)
    if not isinstance(start, dict):
        return []
    seen: list[str] = []
    todo = _needs(start)
    while todo:
        name = todo.pop(0)
        job = jobs.get(name)
        if name in seen or not isinstance(job, dict):
            continue
        seen.append(name)
        todo.extend(_needs(job))
    return seen


def message_for(kind: str, name: str, workflow_file: str) -> str | None:
    """`:179-216`, the `case` that turns one finding into one `log_error` line.

    None means the twin's `case` has no arm for that kind, which is a silent skip there and must stay a silent skip here.
    """
    if kind == "ungated":
        return (
            "INVARIANT-FAIL: channel-as-docker-tag: job '%s' passes the channel as docker_tag "
            "but its `if:` does not require `needs.initialize.outputs.channel != ''`. With an "
            "empty channel (every schedule run) constants.sh:27 rewrites the tag to 'latest', "
            "so the job validates the last RELEASED image while asserting the next version." % name
        )
    if kind == "no-jobs":
        return (
            "INVARIANT-FAIL: no-jobs: %s declares no jobs (nothing to check cannot pass)"
            % workflow_file
        )
    if kind == "skip-release-no-output":
        return (
            "INVARIANT-FAIL: skip-release: job '%s' declares no `skip_release` output. The "
            "bump-none decision is made there and read by five consumers; without the output "
            "every one of them sees an empty string and RELEASES." % name
        )
    if kind == "skip-release-not-passed":
        return (
            "INVARIANT-FAIL: skip-release: job '%s' does not pass `skip_release` in its "
            "`with:`. upload_to_r2.py's guard then never fires, and a bump-none commit advances "
            "cli/<channel>/manifest.json to a version that will never be tagged." % name
        )
    if kind == "skip-release-validator-ungated":
        return (
            "INVARIANT-FAIL: skip-release: validator '%s' does not gate on `skip_release`. With "
            "the channel pointer withheld it asserts the NEW version against the OLD published "
            "one and goes red on exactly the commits that behaved correctly." % name
        )
    if kind == "skip-release-second-decision":
        return (
            "INVARIANT-FAIL: skip-release: job '%s' still runs `dispatch-release.sh "
            "--decide-only`. The decision must be made ONCE, in initialize, and merely read "
            "here -- asking twice can answer differently if a label moves in between." % name
        )
    if kind in ("skip-release-no-init", "skip-release-no-stage", "skip-release-missing-job"):
        return (
            "INVARIANT-FAIL: skip-release: expected job '%s' is absent from %s, so this "
            "invariant checked nothing. Retarget it deliberately rather than letting it pass "
            "over a renamed job." % (name, workflow_file)
        )
    if kind == "root-ancestor-conditional":
        return (
            "INVARIANT-FAIL: root-ancestor-conditional: job '%s' is an ancestor of "
            "`initialize` and has a job-level `if:`. When it skips, every job downstream of "
            "`initialize` without its own status function skips too (a job's implicit "
            "`success()` reads all ancestors), and CI Complete fails on a hard-required skip. "
            "Run it on every event and decide inside its steps." % name
        )
    if kind == "no-candidates":
        # Vacuity guard. If nobody passes a channel-derived docker_tag any more, this gate is asserting nothing and must say so rather than printing a green nobody earned.
        return (
            "INVARIANT-FAIL: no-candidates: no job in %s passes a channel-derived `docker_tag`, "
            "so this gate verified nothing. Retarget or remove it deliberately." % workflow_file
        )
    return None


# --------------------------------------------------------------------------- the release-order phase (see the module docstring)

RELEASE_KINDS = (
    "release-order-no-sentinel-writer",
    "release-order-dispatch-split",
    "release-order-no-tag-step",
    "release-order-tag-behind-job",
    "release-order-tag-skipped-on-retry",
    "cd-contents-write",
    "cd-push-not-app-token",
    "cd-preset-no-workflows",
)

# The ONLY job the version-tag step may sit behind. `init` resolves the version and runs two read-only guards (check-existing-release, assert-artifact-version); every other cd-v2 job publishes, deploys or validates, and each of those can fail or skip after the sentinel is sealed.
TAG_ALLOWED_ANCESTORS = frozenset({"init"})

SENTINEL_JOB = "finalize-release-sentinel"
SENTINEL_WRITER = "write_release_sentinel"
SENTINEL_DISPATCH = "dispatch_release"
APP_MINT_ACTION = "./.github/actions/app-token"

# `git tag -a`, allowing `git -c k=v ... tag -a`, and a push of a `v$...` ref: the version tag, not a submodule's.
_TAG_CREATE_RE = re.compile(r"\bgit\b[^\n]*?\btag\s+-a\b")
_TAG_PUSH_RE = re.compile(r"\bgit\s+push\s+origin\s+\"?v\$")
_PUSH_RE = re.compile(r"\bgit\s+push\b")


def _steps(job: object) -> list[dict]:
    steps = job.get("steps") if isinstance(job, dict) else None
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _step_label(job: str, index: int, step: dict) -> str:
    return "%s step %d (%s)" % (job, index + 1, step.get("name") or step.get("uses") or "unnamed")


def version_tag_steps(cd_doc: object) -> list[tuple[str, int, dict]]:
    """Every (job, index, step) in cd-v2 whose `run:` both creates an annotated tag and pushes a `v$...` ref."""
    jobs = (cd_doc or {}).get("jobs") if isinstance(cd_doc, dict) else None
    if not isinstance(jobs, dict):
        return []
    out = []
    for name, job in jobs.items():
        for i, st in enumerate(_steps(job)):
            run = _text(st.get("run"))
            if _TAG_CREATE_RE.search(run) and _TAG_PUSH_RE.search(run):
                out.append((str(name), i, st))
    return out


def _sentinel_findings(ci_doc: object) -> list[tuple[str, str]]:
    jobs = (ci_doc or {}).get("jobs") if isinstance(ci_doc, dict) else None
    fin = jobs.get(SENTINEL_JOB) if isinstance(jobs, dict) else None
    steps = _steps(fin)
    seal = [i for i, s in enumerate(steps) if SENTINEL_WRITER in _text(s.get("run"))]
    if not seal:
        return [("release-order-no-sentinel-writer", SENTINEL_JOB)]
    i = seal[-1]
    nxt = steps[i + 1] if i + 1 < len(steps) else None
    if (
        nxt is None
        or SENTINEL_DISPATCH not in _text(nxt.get("run"))
        or _text(nxt.get("if")) != _text(steps[i].get("if"))
    ):
        return [("release-order-dispatch-split", _step_label(SENTINEL_JOB, i, steps[i]))]
    return []


def _tag_findings(cd_doc: object) -> list[tuple[str, str]]:
    jobs = cd_doc.get("jobs") if isinstance(cd_doc, dict) else None
    if not isinstance(jobs, dict):
        return [("release-order-no-tag-step", "<no jobs>")]
    found = version_tag_steps(cd_doc)
    if not found:
        return [("release-order-no-tag-step", "<none>")]
    out = []
    for job, _i, st in found:
        behind = [a for a in _root_ancestors(jobs, job) if a not in TAG_ALLOWED_ANCESTORS]
        if behind:
            out.append(("release-order-tag-behind-job", "%s behind %s" % (job, ", ".join(behind))))
        for where, cond in (("job", jobs[job].get("if")), ("step", st.get("if"))):
            if "retry_mode" in _text(cond):
                out.append(("release-order-tag-skipped-on-retry", "%s (%s if:)" % (job, where)))
    return out


def _writes_contents(perms: object) -> bool:
    if isinstance(perms, str):
        return perms.strip() == "write-all"
    return isinstance(perms, dict) and _text(perms.get("contents")).strip() == "write"


def _permission_findings(cd_doc: object) -> list[tuple[str, str]]:
    if not isinstance(cd_doc, dict):
        return []
    out = []
    if _writes_contents(cd_doc.get("permissions")):
        out.append(("cd-contents-write", "<workflow>"))
    jobs = cd_doc.get("jobs")
    for name, job in (jobs if isinstance(jobs, dict) else {}).items():
        if isinstance(job, dict) and _writes_contents(job.get("permissions")):
            out.append(("cd-contents-write", str(name)))
    return out


def _push_findings(cd_doc: object) -> tuple[list[tuple[str, str]], int]:
    """(findings, pushes seen). A push must follow a cd-preset app-token mint, and the last checkout before it must carry that token: actions/checkout's persisted extraheader beats the global insteadOf the action writes."""
    jobs = cd_doc.get("jobs") if isinstance(cd_doc, dict) else None
    out, seen = [], 0
    for name, job in (jobs if isinstance(jobs, dict) else {}).items():
        token_ids: list[str] = []
        last_checkout: dict | None = None
        for i, st in enumerate(_steps(job)):
            uses = _text(st.get("uses"))
            raw_with = st.get("with")
            with_map = raw_with if isinstance(raw_with, dict) else {}
            if uses == APP_MINT_ACTION and _text(with_map.get("preset")).strip() == "cd":
                token_ids.append(_text(st.get("id")))
            if uses.startswith("actions/checkout@"):
                last_checkout = st
            if not _PUSH_RE.search(_text(st.get("run"))):
                continue
            seen += 1
            co_with = (last_checkout or {}).get("with")
            co_token = _text(co_with.get("token")) if isinstance(co_with, dict) else ""
            if not any(t and "steps.%s.outputs.token" % t in co_token for t in token_ids):
                out.append(("cd-push-not-app-token", _step_label(str(name), i, st)))
    return out, seen


def _cd_arm(run: str) -> str:
    match = re.search(r"^\s*cd\)\s*$(.*?)^\s*;;", run, re.MULTILINE | re.DOTALL)
    if match is None:
        return ""
    return "\n".join(ln for ln in match.group(1).splitlines() if not ln.strip().startswith("#"))


def _preset_findings(action_doc: object) -> list[tuple[str, str]]:
    runs = action_doc.get("runs") if isinstance(action_doc, dict) else None
    steps = _steps(runs)
    perms = [s for s in steps if _text(s.get("id")) == "perms"]
    if not perms or "perm-workflows=write" not in _cd_arm(_text(perms[0].get("run"))):
        return [("cd-preset-no-workflows", "the `cd)` arm of step `perms`")]
    mint = [s for s in steps if "create-github-app-token" in _text(s.get("uses"))]
    with_map = mint[0].get("with") if mint else None
    passed = _text(with_map.get("permission-workflows")) if isinstance(with_map, dict) else ""
    if "steps.perms.outputs.perm-workflows" not in passed:
        return [
            ("cd-preset-no-workflows", "the create-github-app-token step's `permission-workflows`")
        ]
    return []


def analyse_release(
    ci_doc: object, cd_doc: object, action_doc: object
) -> tuple[list[tuple[str, str]], dict[str, object]]:
    """The release-order phase over three parsed documents: (findings, shape). Pure; the selftest drives it with literal dicts."""
    findings = _sentinel_findings(ci_doc) + _tag_findings(cd_doc)
    findings += _permission_findings(cd_doc)
    push_findings, pushes = _push_findings(cd_doc)
    findings += push_findings + _preset_findings(action_doc)
    jobs = cd_doc.get("jobs") if isinstance(cd_doc, dict) else None
    tags = version_tag_steps(cd_doc)
    shape: dict[str, object] = {
        "jobs": len(jobs) if isinstance(jobs, dict) else 0,
        "pushes": pushes,
        "tag": [
            (job, st.get("name") or "unnamed", _root_ancestors(jobs, job)) for job, _i, st in tags
        ]
        if isinstance(jobs, dict)
        else [],
    }
    return findings, shape


def release_message_for(kind: str, name: str, files: dict[str, str]) -> str | None:
    ci, cd, action = files["ci"], files["cd"], files["action"]
    if kind == "release-order-no-sentinel-writer":
        return (
            "INVARIANT-FAIL: release-order: no step in %s job '%s' runs %s, so the release-order "
            "check has no seal to order the tag against and verified nothing. Retarget it "
            "deliberately." % (ci, name, SENTINEL_WRITER)
        )
    if kind == "release-order-dispatch-split":
        return (
            "INVARIANT-FAIL: release-order: %s seals the sentinel, but the very next step is not "
            "the %s dispatch under the identical `if:`. Anything between them, or a different "
            "guard, can seal cli/v<V>/.released and never start the run that tags v<V>. Put the "
            "dispatch directly after the seal with the same `if:`." % (name, SENTINEL_DISPATCH)
        )
    if kind == "release-order-no-tag-step":
        return (
            "INVARIANT-FAIL: release-order: no step in %s both creates an annotated tag (`git tag "
            "-a`) and pushes `v$...` (%s), so nothing was checked. The version tag must exist "
            "somewhere in CD; retarget this check if it moved." % (cd, name)
        )
    if kind == "release-order-tag-behind-job":
        return (
            "INVARIANT-FAIL: release-order: the version tag step in %s sits in %s. ci.yml has "
            "already sealed cli/v<V>/.released when CD starts, so any of those jobs failing or "
            "skipping leaves a sentinel with no tag, the bijection break Check Release State "
            "reddens main on (CD run 37749637824, v2.2.0). Create the tag in a job that needs "
            "only %s." % (cd, name, ", ".join(sorted(TAG_ALLOWED_ANCESTORS)))
        )
    if kind == "release-order-tag-skipped-on-retry":
        return (
            "INVARIANT-FAIL: release-order: the version tag step in %s is skipped on retry_mode "
            "(%s). A retry of a sealed version must re-ensure its tag (idempotently), never "
            "skip it. Drop retry_mode from that `if:`." % (cd, name)
        )
    if kind == "cd-contents-write":
        return (
            "INVARIANT-FAIL: cd-permissions: %s %s holds `contents: write`. Every CD write rides "
            "the cd-preset App token, so the job is all-or-nothing on one credential; a second "
            "write-scoped credential is how a tag landed without its Release (v1.3.11, v1.3.8). "
            "Remove the scope." % (cd, name)
        )
    if kind == "cd-push-not-app-token":
        return (
            "INVARIANT-FAIL: cd-push-token: %s %s runs `git push`, but its job mints no "
            "`preset: cd` App token before it, or the last actions/checkout before it does not "
            "pass `token: ${{ steps.<app-token id>.outputs.token }}` (checkout's persisted "
            "github.token header would win). Push on the App token." % (cd, name)
        )
    if kind == "cd-preset-no-workflows":
        return (
            "INVARIANT-FAIL: cd-preset: %s no longer requests `workflows: write` for the cd "
            "preset (%s). Without it GitHub refuses `git push origin v<X>` whenever the tagged "
            "range touches .github/workflows, and the release half-completes (runs 34019022671, "
            "34003183456). Restore `perm-workflows=write` and `permission-workflows`."
            % (action, name)
        )
    return None


# --------------------------------------------------------------------------- the cd-preflight pins (PLAN-cd-errors-in-ci W4)

PREFLIGHT_KINDS = (
    "cd-preflight-no-pr-job",
    "cd-preflight-not-on-pr",
    "cd-preflight-no-cd-step",
    "cd-preflight-before-tag",
    "cd-preflight-no-housekeeping-step",
    "cd-preflight-housekeeping-bypassed",
    "cd-preflight-narrowed",
)

PREFLIGHT_MODULE = "rediacc_ci.release.cd_preflight"
HOUSEKEEPING_DESTRUCTIVE = "rediacc_ci.housekeeping.cleanup_versions"

# The checks each site must run. A site may run more; dropping one is a finding, so a narrowed `--checks` cannot quietly turn a site into a partial check. `homebrew` is deliberately absent everywhere: the PR job deselects it (ci.yml says why), and CD runs update_homebrew_tap itself.
PREFLIGHT_REQUIRED_CHECKS = {
    "pr": frozenset({"a", "b", "c", "d", "promotion"}),
    "cd": frozenset({"a", "c", "d"}),
    "housekeeping": frozenset({"a", "c"}),
}

# A status function in a step `if:` runs the step after an earlier one failed, which is exactly how a red preflight would stop nothing.
_STATUS_FN_RE = re.compile(r"\b(always|failure|cancelled)\s*\(")
_CHECKS_RE = re.compile(r"--checks[=\s]+\"?([A-Za-z0-9_,]+)")
_PHASE_RE = re.compile(r"--phase[=\s]+\"?([a-z]+)")


def preflight_steps(doc: object) -> list[tuple[str, int, dict, str]]:
    """Every (job, index, step, phase) whose `run:` invokes the preflight module."""
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    out = []
    for name, job in (jobs if isinstance(jobs, dict) else {}).items():
        for i, st in enumerate(_steps(job)):
            run = _text(st.get("run"))
            if PREFLIGHT_MODULE in run:
                match = _PHASE_RE.search(run)
                out.append((str(name), i, st, match.group(1) if match else ""))
    return out


def _narrowed(site: str, label: str, step: dict) -> list[tuple[str, str]]:
    match = _CHECKS_RE.search(_text(step.get("run")))
    if match is None:
        return []  # no --checks runs every check
    missing = PREFLIGHT_REQUIRED_CHECKS[site] - set(match.group(1).split(","))
    if not missing:
        return []
    return [("cd-preflight-narrowed", "%s drops %s" % (label, ",".join(sorted(missing))))]


# `event_name == 'pull_request'` (either operand order). `!=` never matches because the operator must be `==`, and a text-only "contains pull_request" test would pass `github.event_name != 'pull_request'`, the main-only blind spot. A match preceded by `!` through any run of spaces and `(`, or enclosed by a parenthesised group that itself follows `!`, is a negation and does not count.
_PR_EQ_RE = re.compile(
    r"github\.event_name\s*==\s*['\"]pull_request['\"]"
    r"|['\"]pull_request['\"]\s*==\s*github\.event_name"
)


def _is_negated(cond: str, start: int) -> bool:
    """True when the test beginning at `start` sits under an odd number of `!` negations: a `!` directly before it (through spaces), or one before any parenthesised group that encloses it, at any distance."""
    i = start - 1
    while i >= 0 and cond[i] in " \t\n":
        i -= 1
    negations = 1 if i >= 0 and cond[i] == "!" else 0
    depth = 0
    for j in range(start - 1, -1, -1):
        ch = cond[j]
        if ch == ")":
            depth += 1
        elif ch == "(":
            if depth:
                depth -= 1
                continue
            k = j - 1
            while k >= 0 and cond[k] in " \t\n":
                k -= 1
            if k >= 0 and cond[k] == "!":
                negations += 1
    return negations % 2 == 1


def _admits_pr(cond: str) -> bool:
    """True when `cond` holds a positive, non-negated `event_name == 'pull_request'` test."""
    return any(not _is_negated(cond, m.start()) for m in _PR_EQ_RE.finditer(cond))


def _step_excludes_pr(cond: str) -> bool:
    """A step-level `if:` that tests the event yet does not admit pull_request; an `if:` that never names the event (`always()`, `success()`) leaves the job's verdict alone."""
    return "event_name" in cond and not _admits_pr(cond)


def analyse_preflight(
    ci_doc: object, cd_doc: object, hk_doc: object
) -> tuple[list[tuple[str, str]], list[str]]:
    """(findings, shape lines) for the three preflight sites. Pure; the tests drive it with literal dicts.

    ci.yml: a job runs `--phase pr` and its `if:` admits pull_request (a push-only job is the main-only blind spot that let the 10-07 drift reach main). cd-v2.yml: a `--phase cd` step sits in the version tag step's job, AFTER it. housekeeping.yml: a preflight step precedes every cleanup_versions step in the same job, and that cleanup step carries no status function that would run it past a red preflight.
    """
    out: list[tuple[str, str]] = []
    shape: list[str] = []

    pr = [s for s in preflight_steps(ci_doc) if s[3] == "pr"]
    if not pr:
        out.append(("cd-preflight-no-pr-job", "<none>"))
    jobs = ci_doc.get("jobs") if isinstance(ci_doc, dict) else None
    ci_jobs: dict[str, typing.Any] = jobs if isinstance(jobs, dict) else {}
    for job, i, st, _phase in pr:
        job_if = _text(ci_jobs[job].get("if")).strip()
        # A job with no `if:` runs on every event, pull_request included.
        if (job_if and not _admits_pr(job_if)) or _step_excludes_pr(_text(st.get("if"))):
            out.append(("cd-preflight-not-on-pr", job))
        out += _narrowed("pr", _step_label(job, i, st), st)
        shape.append("ci.yml job %s runs it on pull_request" % job)

    tags = version_tag_steps(cd_doc)
    cd = [s for s in preflight_steps(cd_doc) if s[3] == "cd"]
    if not cd:
        out.append(("cd-preflight-no-cd-step", "<none>"))
    for job, i, st, _phase in cd:
        after = [t for t in tags if t[0] == job and t[1] < i]
        if not after:
            out.append(("cd-preflight-before-tag", _step_label(job, i, st)))
        else:
            shape.append("cd-v2 %s step %d after the tag step %d" % (job, i + 1, after[0][1] + 1))
        out += _narrowed("cd", _step_label(job, i, st), st)

    hk_jobs = hk_doc.get("jobs") if isinstance(hk_doc, dict) else None
    destructive = [
        (str(name), i, st)
        for name, job in (hk_jobs if isinstance(hk_jobs, dict) else {}).items()
        for i, st in enumerate(_steps(job))
        if HOUSEKEEPING_DESTRUCTIVE in _text(st.get("run"))
    ]
    if not destructive:
        out.append(("cd-preflight-no-housekeeping-step", "<no %s step>" % HOUSEKEEPING_DESTRUCTIVE))
    hk_pre = preflight_steps(hk_doc)
    for job, i, st in destructive:
        before = [p for p in hk_pre if p[0] == job and p[1] < i]
        if not before:
            out.append(("cd-preflight-no-housekeeping-step", _step_label(job, i, st)))
            continue
        _j, pi, pst, _ph = before[-1]
        if _STATUS_FN_RE.search(_text(st.get("if"))) or _text(pst.get("if")).strip():
            out.append(("cd-preflight-housekeeping-bypassed", _step_label(job, i, st)))
        out += _narrowed("housekeeping", _step_label(job, pi, pst), pst)
        shape.append("housekeeping %s step %d before cleanup step %d" % (job, pi + 1, i + 1))
    return out, shape


def preflight_message_for(kind: str, name: str, files: dict[str, str]) -> str | None:
    ci, cd, hk = files["ci"], files["cd"], files["housekeeping"]
    if kind == "cd-preflight-no-pr-job":
        return (
            "INVARIANT-FAIL: cd-preflight: no step in %s runs `%s --phase pr`, so a PR merges "
            "without the CD failures it causes being predicted (PLAN-cd-errors-in-ci W4). "
            "Restore the cd-preflight job." % (ci, PREFLIGHT_MODULE)
        )
    if kind == "cd-preflight-not-on-pr":
        return (
            "INVARIANT-FAIL: cd-preflight: %s job %s runs the preflight but its `if:` never "
            "admits pull_request. A main-only check is how the 10-07 bijection drift was first "
            "seen after PR #599 merged. Keep the same-repo pull_request arm." % (ci, name)
        )
    if kind == "cd-preflight-no-cd-step":
        return (
            "INVARIANT-FAIL: cd-preflight: no step in %s runs `%s --phase cd`, so CD publishes "
            "without judging the release state first. Restore it in init, after `Create version "
            "tag`." % (cd, PREFLIGHT_MODULE)
        )
    if kind == "cd-preflight-before-tag":
        return (
            "INVARIANT-FAIL: cd-preflight: %s %s is not after the version tag step in the same "
            "job. v<V> is sealed by ci.yml and untagged until that step, so a preflight before it "
            "reds every release. Move it after `Create version tag`." % (cd, name)
        )
    if kind == "cd-preflight-no-housekeeping-step":
        return (
            "INVARIANT-FAIL: cd-preflight: %s %s deletes releases, tags and R2 objects with no "
            "`%s` step before it in its job, so a broken or unreadable release state is pruned "
            "further instead of refused. Add the read-only preflight step before it."
            % (hk, name, PREFLIGHT_MODULE)
        )
    if kind == "cd-preflight-housekeeping-bypassed":
        return (
            "INVARIANT-FAIL: cd-preflight: %s %s runs even when the preflight before it is red "
            "(a status function in its `if:`, or an `if:` on the preflight step). Housekeeping "
            "must fail closed: drop the status function." % (hk, name)
        )
    if kind == "cd-preflight-narrowed":
        return (
            "INVARIANT-FAIL: cd-preflight: %s. A narrowed --checks prints SKIPPED where a check "
            "used to run. Restore the check, or change PREFLIGHT_REQUIRED_CHECKS in %s on "
            "purpose." % (name, "ci_workflow_invariants.py")
        )
    return None


# --------------------------------------------------------------------------- the external gates are hard on every cadence (operator rulings 2026-10-13 and 2026-10-14)

UPSTREAM_GATE_KINDS = (
    "upstream-gate-missing",
    "upstream-gate-conditional",
    "upstream-gate-job-conditional",
    "upstream-gate-unannounced",
    "upstream-gate-schedule-skipped",
)

# Every gate that asks a host outside the repository. "Everything fails closed, nightly included" and "Extend to all seven": each one is hard on a pull request, on the nightly and on a dispatch, and the no-external-quality label is the one way a step does not run. check:deps asks the npm registry and was always hard on the nightly; it joined the label hold on 2026-10-14, when the doc that listed it as label-held turned out to describe a step that was not.
UPSTREAM_GATES = (
    "check:ci-embed-asset-freshness",
    "check:ci-devcontainer-pins",
    "check:ci-real-provider-pins",
    "check:actions",
    "check:ci-pin-freshness",
    "check:ci-external-links",
    "check:ci-dkim-notify",
    "check:ci-go-deps",
    "check:deps",
)
UPSTREAM_GATE_LABEL = "no-external-quality"
UPSTREAM_GATE_ANNOUNCER = "rediacc_ci.quality.announce_gate_skips"
# The one `if:` an external step may carry: the lane's standard guard and the label hold, nothing that can tell a schedule from a pull request. Compared with parentheses removed, because gate-bind wraps its `when:` conjunct in them, and with at most one gate-bind shard conjunct (`matrix.shard == N`) removed, because a shard index cannot tell a cadence either.
UPSTREAM_GATE_IF = (
    "!cancelled() && steps.setup.outcome == 'success' && inputs.external_quality != 'skip'"
)
# The one job-level `if:` a job holding external steps may carry: the bot guard every quality lane has. Any other job condition (`github.event_name == 'pull_request'`) would skip its gates, and the announcer beside them, on the nightly while every step-level check here still passed.
UPSTREAM_GATE_JOB_IF = "inputs.is_bot != 'true'"
_SHARD_CONJUNCT_RE = re.compile(r" && matrix\.shard == \d+$")
# What the announcer is handed: the label's `skip`, and `hard` for every other value, `soft` included, because these steps run hard under `soft`.
UPSTREAM_GATE_ANNOUNCE_MODE = "inputs.external_quality == 'skip' && 'skip' || 'hard'"
# ci.yml's external_quality: every event that is not a pull request resolves to a value the external steps RUN under. `'skip'` there would remove them from the nightly without a word.
_NON_PR_MODE_RE = re.compile(
    r"github\.event_name\s*!=\s*'pull_request'\s*&&\s*'(soft|hard)'\s*\|\|"
)


def _expr(value: object) -> str:
    """An `if:` or env value with its `${{ }}` wrapper and outer whitespace removed, inner runs of whitespace collapsed."""
    text = " ".join(_text(value).split())
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2].strip()
    return text


def _env(step: dict) -> dict:
    """A step's `env:` mapping, or an empty one when it has none."""
    env = step.get("env")
    return env if isinstance(env, dict) else {}


def _reduced(text: str) -> str:
    """An expression with every parenthesis dropped and whitespace collapsed, so `a && (b)` and `a && b` compare equal. `!cancelled()` reduces the same way on both sides."""
    return " ".join(text.replace("(", " ").replace(")", " ").split())


def _guard(value: object) -> str:
    """An `if:` reduced for comparison with UPSTREAM_GATE_IF: no parentheses, no trailing gate-bind shard conjunct."""
    return _SHARD_CONJUNCT_RE.sub("", _reduced(_expr(value)))


def upstream_gate_steps(quality_doc: object) -> dict[str, list[tuple[str, int, dict]]]:
    """gate id -> every (job, step index, step) in ci-quality.yml whose `run:` invokes `npm run <id>`."""
    found: dict[str, list[tuple[str, int, dict]]] = {gate: [] for gate in UPSTREAM_GATES}
    jobs = quality_doc.get("jobs") if isinstance(quality_doc, dict) else None
    for job, body in (jobs if isinstance(jobs, dict) else {}).items():
        for i, st in enumerate(_steps(body)):
            run = _text(st.get("run"))
            for gate in UPSTREAM_GATES:
                if re.search(r"\bnpm run %s(?![\w:-])" % re.escape(gate), run):
                    found[gate].append((job, i, st))
    return found


def _announced(job_steps: list[dict], gate: str) -> bool:
    """Does an UNCONDITIONAL announcer in this job name `gate` under the label, with the mode the external steps really run under?"""
    for st in job_steps:
        run = _text(st.get("run"))
        words = run.split()
        if (
            UPSTREAM_GATE_ANNOUNCER not in run
            or UPSTREAM_GATE_LABEL not in words
            or gate not in words
        ):
            continue
        env = _env(st)
        if "external_quality" in _text(st.get("if")):
            continue
        if _expr(env.get("GATE_SKIP_MODE")) == UPSTREAM_GATE_ANNOUNCE_MODE:
            return True
    return False


def analyse_upstream_gates(
    ci_doc: object, quality_doc: object
) -> tuple[list[tuple[str, str]], list[str]]:
    """(findings, shape lines) for every external gate. Pure; the tests drive it with literal dicts.

    ci-quality.yml: each gate has a step; its `if:` reduces to UPSTREAM_GATE_IF; and an unconditional announcer in the same job names it under the label. ci.yml: `external_quality` never resolves to `skip` off a pull request.
    """
    out: list[tuple[str, str]] = []
    shape: list[str] = []
    jobs = quality_doc.get("jobs") if isinstance(quality_doc, dict) else None
    quality_jobs: dict[str, typing.Any] = jobs if isinstance(jobs, dict) else {}
    job_checked: set[str] = set()
    for gate, sites in upstream_gate_steps(quality_doc).items():
        if not sites:
            out.append(("upstream-gate-missing", gate))
            continue
        for job, i, st in sites:
            if job not in job_checked:
                job_checked.add(job)
                body = quality_jobs.get(job)
                condition = _expr(body.get("if")) if isinstance(body, dict) else ""
                if condition not in ("", UPSTREAM_GATE_JOB_IF):
                    out.append(("upstream-gate-job-conditional", job))
            label = "%s (%s)" % (gate, _step_label(job, i, st))
            if _guard(st.get("if")) != _reduced(UPSTREAM_GATE_IF):
                out.append(("upstream-gate-conditional", label))
            if not _announced(_steps(quality_jobs.get(job)), gate):
                out.append(("upstream-gate-unannounced", label))
            shape.append("%s in %s" % (gate, job))

    ci_jobs = ci_doc.get("jobs") if isinstance(ci_doc, dict) else None
    init = (ci_jobs if isinstance(ci_jobs, dict) else {}).get("initialize")
    outputs = init.get("outputs") if isinstance(init, dict) else None
    mode = _expr((outputs if isinstance(outputs, dict) else {}).get("external_quality"))
    if not _NON_PR_MODE_RE.search(mode):
        out.append(("upstream-gate-schedule-skipped", mode or "<no external_quality output>"))
    return out, shape


def upstream_gate_message_for(kind: str, name: str, files: dict[str, str]) -> str | None:
    ci, quality = files["ci"], files["quality"]
    if kind == "upstream-gate-missing":
        return (
            "INVARIANT-FAIL: upstream-gates: no step in %s runs `npm run %s`, so that external "
            "gate runs on no cadence at all (nothing to check cannot pass). Restore its step."
            % (quality, name)
        )
    if kind == "upstream-gate-conditional":
        return (
            "INVARIANT-FAIL: upstream-gates: %s in %s has an `if:` other than `%s` (a gate-bind "
            "shard conjunct aside). Any other condition can keep the step from running on a "
            "cadence without a word, and the label is the only hold these gates have."
            % (name, quality, UPSTREAM_GATE_IF)
        )
    if kind == "upstream-gate-job-conditional":
        return (
            "INVARIANT-FAIL: upstream-gates: job %s in %s carries an `if:` other than `%s`. "
            "External steps and their announcer live in it, so a job condition that can tell a "
            "schedule from a pull request skips those gates on the nightly without a word, "
            "whatever each step's own `if:` says." % (name, quality, UPSTREAM_GATE_JOB_IF)
        )
    if kind == "upstream-gate-unannounced":
        return (
            "INVARIANT-FAIL: upstream-gates: %s in %s is held by the %s label with no announcer "
            "naming it: a skipped step prints nothing and its job stays green. Its job needs a "
            "step with no external_quality `if:` running `%s %s <gates>` with GATE_SKIP_MODE "
            "`%s`."
            % (
                name,
                quality,
                UPSTREAM_GATE_LABEL,
                UPSTREAM_GATE_ANNOUNCER,
                UPSTREAM_GATE_LABEL,
                UPSTREAM_GATE_ANNOUNCE_MODE,
            )
        )
    if kind == "upstream-gate-schedule-skipped":
        return (
            "INVARIANT-FAIL: upstream-gates: %s initialize.outputs.external_quality is `%s`, which "
            "does not resolve every event other than pull_request to 'soft' or 'hard'. The external "
            "steps run under both and are skipped under 'skip', so this would take them off the "
            "nightly." % (ci, name)
        )
    return None


def _upstream_gate_phase(ci_file: str, quality_file: str) -> tuple[list[str], list[str]]:
    """(errors, info lines) for the external gates. A missing file is an error, never a pass."""
    files = {"ci": ci_file, "quality": quality_file}
    docs = {}
    for key, path in files.items():
        if not os.path.isfile(path):
            return [
                "INVARIANT-FAIL: upstream-gates: no file at %s (nothing to check cannot pass)"
                % path
            ], []
        try:
            docs[key] = load_workflow(path)
        except SetupExitError as exc:
            return ["INVARIANT-FAIL: upstream-gates: %s" % exc.message.strip()], []
    findings, shape = analyse_upstream_gates(docs["ci"], docs["quality"])
    errors = [m for k, n in findings if (m := upstream_gate_message_for(k, n, files)) is not None]
    if errors:
        return errors, []
    return [], [
        "external gates hold (%d gate(s), %d step(s)): %s; each runs unwrapped (hard on "
        "pull_request, schedule and dispatch), is held only by the %s label, and is named by "
        "its job's announcer"
        % (len(UPSTREAM_GATES), len(shape), "; ".join(shape), UPSTREAM_GATE_LABEL)
    ]


def _preflight_phase(ci_file: str, cd_file: str, hk_file: str) -> tuple[list[str], list[str]]:
    """(errors, info lines) for the cd-preflight pins. A missing file is an error, never a pass."""
    files = {"ci": ci_file, "cd": cd_file, "housekeeping": hk_file}
    docs = {}
    for key, path in files.items():
        if not os.path.isfile(path):
            return [
                "INVARIANT-FAIL: cd-preflight: no file at %s (nothing to check cannot pass)" % path
            ], []
        try:
            docs[key] = load_workflow(path)
        except SetupExitError as exc:
            return ["INVARIANT-FAIL: cd-preflight: %s" % exc.message.strip()], []
    findings, shape = analyse_preflight(docs["ci"], docs["cd"], docs["housekeeping"])
    errors = [m for k, n in findings if (m := preflight_message_for(k, n, files)) is not None]
    if errors:
        return errors, []
    return [], ["cd-preflight holds: " + "; ".join(shape)]


def _release_phase(ci_file: str, cd_file: str, action_file: str) -> tuple[list[str], list[str]]:
    """(errors, info lines). Missing or unparseable inputs are errors: unread is never fine."""
    files = {"ci": ci_file, "cd": cd_file, "action": action_file}
    docs = {}
    for key, path in files.items():
        if not os.path.isfile(path):
            return [
                "INVARIANT-FAIL: release-order: no file at %s (nothing to check cannot pass)" % path
            ], []
        try:
            docs[key] = load_workflow(path)
        except SetupExitError as exc:
            return ["INVARIANT-FAIL: release-order: %s" % exc.message.strip()], []
    findings, shape = analyse_release(docs["ci"], docs["cd"], docs["action"])
    errors = [m for k, n in findings if (m := release_message_for(k, n, files)) is not None]
    if errors:
        return errors, []
    tag_rows = typing.cast("list[tuple[str, str, list[str]]]", shape["tag"])
    tag = "; ".join(
        "%s step '%s' (needs: %s)" % (job, step, ", ".join(anc) or "nothing")
        for job, step, anc in tag_rows
    )
    return [], [
        "release order holds: %s creates the version tag, not behind any job that can fail "
        "after the seal and not skipped on retry_mode; %s dispatches CD in the step right after "
        "the seal under the same if:; %d cd-v2 jobs, none holding contents: write; %d `git "
        "push` step(s), each on the cd App token; the cd preset requests workflows: write"
        % (
            tag,
            SENTINEL_JOB,
            typing.cast("int", shape["jobs"]),
            typing.cast("int", shape["pushes"]),
        )
    ]


# THE PINS-SOAKED PINS (PLAN-pins-command T11). `pins-soaked.yml` reports soaked pins as an artifact and opens nothing: no pull request, no push, no token beyond `contents: read`, the one minted token being the read-only checkout token of the 2026-10-23 ruling (`_pins_checkout_token`). The phase reads that file and refuses any shape that could write, or that no longer runs the verb or uploads its output.
PINS_SOAKED_KINDS = (
    "pins-soaked-triggers",
    "pins-soaked-permissions",
    "pins-soaked-writes",
    "pins-soaked-no-apply",
    "pins-soaked-no-upload",
    "pins-soaked-no-red-path",
)

PINS_SOAKED_WORKFLOW = "CI - OBS Mirror"
_PINS_APPLY_RE = re.compile(r"\bpins\s+--\s+apply-soaked\b")
# CASE. GitHub resolves context names and the steps context without regard to case (actions/runner DictionaryContextData looks keys up with StringComparer.OrdinalIgnoreCase, and ExecutionContext.ExpressionValues and StepsContext are built from it), and the env context too on a Windows runner (StepsRunner.cs, `#if OS_WINDOWS`).
# So every pattern below that recognises a READ (secrets, steps, env, BWS_* names, write commands, write actions) matches in any case, since a missed spelling is a hole; every pattern that ADMITS a shape (the access-token, client-id, private-key and token expressions, the preset, the action paths, the blanking and scrub lines) stays exact, since a refused spelling only costs a rewrite.
# Write commands match in any case as well: a Windows runner resolves `Git` to git. A curl write is a method named by `-X`/`--request` or a body flag (`-d`, `-F`, `-T`, alone, attached to its value as in `-d@body`, or ending a cluster as in `-sSd`, and `-X` likewise as in `-sSX POST`; `--data*`, `--form`, `--form-string`, `--upload-file`, `--json`), read only within the curl command itself (up to a `|`, `;` or `&` OUTSIDE quotes, `_pins_writes` blanks those inside quoted arguments first, so `curl ... | cut -d:` is a read), never a method word elsewhere on the line, so a URL such as `.../delete-notes` is a read; the short flags stay case-exact because curl's `-x` is the proxy and `-D` dumps headers.
_PINS_WRITE_RE = re.compile(
    r"\bgit\s+(push|commit|tag)\b|\bgh\s+(pr|api|release|workflow|issue)\b"
    r"|\bcurl\b[^\n|;&]*(?:\s(?-i:-[A-Za-z]*X)\s*|--request(?:=|\s+))['\"]?(POST|PUT|PATCH|DELETE)\b"
    r"|\bcurl\b[^\n|;&]*\s(?-i:-[A-Za-z]*[dFT])"
    r"|\bcurl\b[^\n|;&]*\s(?:--data(?:-[a-z]+)?|--form(?:-string)?|--upload-file|--json)(?=[\s=]|$)",
    re.IGNORECASE,
)
_PINS_QUOTED_RE = re.compile(r"'[^'\n]*'|\"(?:[^\"\\\n]|\\.)*\"")


def _pins_writes(run: str) -> bool:
    """True when a run script holds a write command. The curl clauses stop at a command separator (`|`, `;`, `&`), so a separator INSIDE a quoted argument, such as the `&` of `"https://x?a=1&b=2"`, is blanked first; otherwise the scan would end inside the URL and miss a later `-X POST` or `-d`."""
    blanked = _PINS_QUOTED_RE.sub(lambda m: re.sub(r"[|;&]", "_", m.group(0)), run)
    return bool(_PINS_WRITE_RE.search(blanked))


# The secrets context can only be read inside an expression: a `${{ }}` anywhere, or a bare `if:` condition. Any use of the word there counts (`secrets.NAME`, `secrets['NAME']`, `toJSON(secrets)`, `secrets == ''`) except `secrets.GITHUB_TOKEN`, read-only under `contents: read`. The workflow needs no secret, so the check does not judge which one could write.
_PINS_EXPR_RE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
# The exemption is an ADMITTING shape, so it stays exact inside the case-insensitive read pattern: `secrets.github_token` is refused and costs a rewrite.
_PINS_SECRET_RE = re.compile(r"\bsecrets\b(?!\s*\.\s*(?-i:GITHUB_TOKEN)\b)", re.IGNORECASE)


def _pins_secret(value: object, condition: object = None) -> bool:
    """True when `value` holds an expression reading the secrets context, or `condition` (a bare `if:`) does."""
    exprs = _PINS_EXPR_RE.findall(_text(value))
    if isinstance(condition, str):
        exprs.append(condition)
    return any(_PINS_SECRET_RE.search(e) for e in exprs)


_PINS_RC_CAPTURE_RE = re.compile(r"^\s*rc=\$\?\s*$")
# Anything on the apply line that lets `$?` be another command's status: a pipe (no pipefail under the default shell), `||`, `;`, a background or `&&` operator, or a line continuation. A `>&`, `&>` or `>|` redirection is not one.
_PINS_MASK_RE = re.compile(r"(?<!>)\||;|(?<![>&])&(?![>&])|&&|\\\s*$")
# The write is a whole line of exactly this form, so nothing can share the line with it.
# Each operand is either fully double-quoted or bare, so a quote cannot swallow the `>>` into the echoed string.
_PINS_RC_OUT_RE = re.compile(
    r"""^\s*echo\s+(?:"rc=\$(?:rc|\{rc\})"|rc=\$(?:rc|\{rc\}))\s*>>\s*(?:"\$(?:GITHUB_OUTPUT|\{GITHUB_OUTPUT\})"|\$(?:GITHUB_OUTPUT|\{GITHUB_OUTPUT\}))\s*$"""
)
_PINS_RC_WORD_RE = re.compile(r"\brc\b")
# The apply line starts with the command itself. Only `!` inverts the status and `if`/`while` move it into a condition, but the rule is a closed form rather than a list of known-bad prefixes, so `time`, `exec` and an assignment prefix are refused too.
_PINS_APPLY_START_RE = re.compile(r"^\s*npm\s+run\b")
_PINS_NOT_COMMAND_RE = re.compile(r"^\s*(#|echo\b|printf\b)")


def _pins_publishes_rc(run: str) -> bool:
    """True when the apply command's own exit status becomes the `rc` step output: the apply line starts with `npm run` and nothing on it can mask the status (`_PINS_MASK_RE`), the next non-blank line is `rc=$?`, a later line is exactly the write (`echo "rc=$rc" >> "$GITHUB_OUTPUT"`, with `${rc}` or `${GITHUB_OUTPUT}` allowed and each operand fully quoted or bare) with nothing else on it, and no line after the capture other than that write names `rc`, so nothing can reassign it. A comment or echo naming the verb is not the apply line."""
    lines = run.split("\n")
    for i, line in enumerate(lines):
        if not _PINS_APPLY_RE.search(line) or _PINS_NOT_COMMAND_RE.match(line):
            continue
        if _PINS_MASK_RE.search(line) or not _PINS_APPLY_START_RE.match(line):
            return False
        rest = [ln for ln in lines[i + 1 :] if ln.strip()]
        if not rest or not _PINS_RC_CAPTURE_RE.match(rest[0]):
            return False
        writes = [ln for ln in rest[1:] if _PINS_RC_OUT_RE.match(ln)]
        others = [ln for ln in rest[1:] if _PINS_RC_WORD_RE.search(ln) and ln not in writes]
        return bool(writes) and not others
    return False


def _pins_red_if_re(step_id: str) -> re.Pattern[str]:
    """The red path's condition: the apply step's own `rc` output is not 0, quoted or bare."""
    return re.compile(r"\bsteps\.%s\.outputs\.rc\s*!=\s*(?:'0'|\"0\"|0\b)" % re.escape(step_id))


_PINS_EXIT_RE = re.compile(r"\bexit\s+1\b")
_PINS_WRITE_USES = ("app-token", "create-pull-request", "github-script", "bws-secrets")


def _pins_triggers(doc: dict) -> dict:
    # PyYAML reads the bare key `on` as the boolean True.
    on = doc.get("on", doc.get(True))
    return on if isinstance(on, dict) else {}


def _read_only(perms: object) -> bool:
    return isinstance(perms, dict) and perms == {"contents": "read"}


# THE ONE ADMITTED TOKEN (operator ruling 2026-10-23, "Admit a read-only checkout token"). The private submodules hold sites the drivers read, so a job may mint a checkout token through exactly one closed shape, each step contiguous: a bws-secrets step fetching only the App id and key with `secrets.BWS_ACCESS_TOKEN`, an app-token step with an `id` and `preset: readonly` (contents: read, `.github/actions/app-token/action.yml` lines 20 and 55), a step blanking both BWS_* values in `$GITHUB_ENV`, and that token read only as `with.token` of a SHA-pinned `actions/checkout`.
# The blanking step is the price of the ruling's own rule that no other step reads a BWS_* value: bws-secrets exports both to `$GITHUB_ENV` for the rest of the job (fetch.sh), so without it the apply step, which runs freshly bumped dependency code, would hold the App private key in its environment and could mint any preset. Any other shape, a second pair, or a token read anywhere else leaves both steps refused.
_PINS_BWS_USES = "./.github/actions/bws-secrets"
_PINS_APP_USES = "./.github/actions/app-token"
_PINS_BWS_MAP = {
    "GITHUB_APP_PRIVATE_KEY": "BWS_GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_ID": "BWS_APP_ID",
}
_PINS_BWS_ACCESS = "${{secrets.BWS_ACCESS_TOKEN}}"
_PINS_TOKEN_KEY_INPUTS = {
    "client-id": "${{env.BWS_APP_ID}}",
    "private-key": "${{env.BWS_GITHUB_APP_PRIVATE_KEY}}",
}
_PINS_SCRUB_LINES = frozenset('echo "%s=" >> "$GITHUB_ENV"' % v for v in _PINS_BWS_MAP.values())
# app-token writes its token into the GLOBAL git config as a `url.<...x-access-token...>.insteadof` key (`.github/actions/app-token/action.yml` line 126), and a checkout that persists credentials leaves it in .git/config, so either way every later step could read the private repos without naming the token.
# So each token-taking checkout says `persist-credentials: false`, they run back to back after the blanking step, and the step right after the last of them is exactly these lines, which unset every such key and fail the job if any trace remains.
# actions/checkout fetches submodules under its own temporary auth and removes it at the end of the step when persist-credentials is false (src/git-source-provider.ts lines 150, 277-284 and 316-324 at the pinned SHA), so the submodule checkout does not need the persisted header.
_PINS_GIT_SCRUB_LINES = (
    "while read -r key; do",
    'case "$key" in *x-access-token*) git config --global --unset-all "$key" ;; esac',
    "done < <(git config --global --name-only --get-regexp '^url\\..*\\.insteadof$')",
    "if git config --global --get-regexp 'x-access-token' >/dev/null || git config --global --get-regexp '.' 'x-access-token' >/dev/null; then",
    'echo "::error::an x-access-token entry is still in the global git config"; exit 1',
    "fi",
)
_PINS_CHECKOUT_RE = re.compile(r"actions/checkout@[0-9a-f]{40}")
_PINS_BWS_LINE_RE = re.compile(r"([A-Za-z0-9_.=:-]+)\s*>\s*([A-Za-z_][A-Za-z0-9_]*)")
_PINS_STEP_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
# `steps.<id>` names one step; `steps[...]`, `toJSON(steps)` or a bare `steps` can reach any, so they count as a read of the token.
_PINS_STEPS_RE = re.compile(r"\bsteps\b(?:\s*\.\s*([A-Za-z_][A-Za-z0-9_-]*))?", re.IGNORECASE)
# Any case, in shell text too: a Linux shell's `$bws_app_id` is another variable, but nothing here pins the runner to Linux, and on Windows `$env:bws_app_id` and `%bws_app_id%` read BWS_APP_ID; a refused lowercase `bws_` costs a rename.
_PINS_BWS_NAME_RE = re.compile(r"\bBWS_\w*", re.IGNORECASE)
# The env context read whole (`toJSON(env)`, `env[...]`) can reach a BWS_* value as surely as naming it.
_PINS_ENV_WHOLE_RE = re.compile(r"\benv\b(?!\s*\.\s*[A-Za-z_])", re.IGNORECASE)


def _leaves(value: object, path: tuple = ()) -> typing.Iterator[tuple[tuple, str]]:
    """Every (path, text) scalar under `value`, so a check cannot miss a key it did not think to name."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _leaves(v, (*path, k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _leaves(v, (*path, i))
    elif value is not None:
        yield path, _text(value)


def _exprs(path: tuple, text: str) -> list[str]:
    """The expressions in one scalar; an `if:` value is an expression whether or not it is wrapped."""
    found = _PINS_EXPR_RE.findall(text)
    if path and path[-1] == "if":
        found.append(text)
    return found


def _squash(value: object) -> str:
    return re.sub(r"\s+", "", _text(value))


def _pins_reads_bws(value: object) -> bool:
    """True when anything under `value` names a BWS_* variable or reads the env context whole."""
    for path, text in _leaves(value):
        if _PINS_BWS_NAME_RE.search(text):
            return True
        if any(_PINS_ENV_WHOLE_RE.search(e) for e in _exprs(path, text)):
            return True
    return False


def _pins_bws_shape(step: dict) -> str | None:
    """Why this bws-secrets step is not the admitted one, or None."""
    extra = sorted(str(k) for k in step if k not in ("name", "uses", "with"))
    if extra:
        return "bws-secrets step carries %s" % ", ".join(extra)
    with_ = step.get("with")
    if not isinstance(with_, dict) or set(with_) != {"access-token", "secrets"}:
        return "bws-secrets `with:` must hold exactly access-token and secrets"
    if _squash(with_.get("access-token")) != _PINS_BWS_ACCESS:
        return "bws-secrets access-token must be ${{ secrets.BWS_ACCESS_TOKEN }}"
    wanted = _text(with_.get("secrets"))
    if "$" in wanted or "#" in wanted:
        return "bws-secrets `secrets:` must be the two literal lines, with no expression or comment"
    pairs: dict[str, str] = {}
    lines = [ln.strip() for ln in wanted.split("\n") if ln.strip()]
    for ln in lines:
        m = _PINS_BWS_LINE_RE.fullmatch(ln)
        if m:
            pairs[m.group(1)] = m.group(2)
    if len(lines) != len(_PINS_BWS_MAP) or pairs != _PINS_BWS_MAP:
        return "bws-secrets may fetch only %s" % ", ".join(
            "%s > %s" % kv for kv in _PINS_BWS_MAP.items()
        )
    return None


def _pins_token_shape(step: dict) -> str | None:
    """Why this app-token step is not the admitted one, or None."""
    extra = sorted(str(k) for k in step if k not in ("name", "uses", "with", "id"))
    if extra:
        return "app-token step carries %s" % ", ".join(extra)
    if not _PINS_STEP_ID_RE.fullmatch(_text(step.get("id"))):
        return "app-token step has no `id`"
    with_ = step.get("with")
    if not isinstance(with_, dict):
        return "app-token step has no `with:`"
    allowed = (*_PINS_TOKEN_KEY_INPUTS, "preset", "repositories")
    extra = sorted(str(k) for k in with_ if k not in allowed)
    if extra:
        return "app-token `with:` carries %s" % ", ".join(extra)
    if "preset" not in with_:
        return "app-token has no `preset:`; it must say `preset: readonly`"
    if with_.get("preset") != "readonly":
        return "app-token preset is %r, not readonly" % with_.get("preset")
    for key, want in _PINS_TOKEN_KEY_INPUTS.items():
        if _squash(with_.get(key)) != want:
            return "app-token %s must be %s" % (key, want)
    if "$" in _text(with_.get("repositories")):
        return "app-token repositories must be a literal list"
    return None


def _pins_is_scrub(step: dict) -> bool:
    """The closed form of the step that blanks both BWS_* values for the rest of the job."""
    if any(k not in ("name", "run") for k in step):
        return False
    lines = [ln.strip() for ln in _text(step.get("run")).split("\n") if ln.strip()]
    return len(lines) == len(_PINS_SCRUB_LINES) and set(lines) == _PINS_SCRUB_LINES


def _pins_is_git_scrub(step: dict) -> bool:
    """The closed form of the step that removes the token app-token left in the global git config, line for line."""
    if any(k not in ("name", "run") for k in step):
        return False
    lines = tuple(ln.strip() for ln in _text(step.get("run")).split("\n") if ln.strip())
    return lines == _PINS_GIT_SCRUB_LINES


def _pins_token_read_at(path: tuple, text: str, ctx: tuple) -> int | None:
    """The step index when this read of the token is `with.token` of a SHA-pinned checkout after the blanking step, else None."""
    jname, raw, position, scrub, sid = ctx
    if len(path) != 6 or path[:3] != ("jobs", jname, "steps") or path[4:] != ("with", "token"):
        return None
    k = path[3]
    st = raw[k] if isinstance(raw, list) and isinstance(k, int) and k < len(raw) else None
    at = position.get(id(st), -1) if isinstance(st, dict) else -1
    if (
        isinstance(st, dict)
        and at > scrub
        and _PINS_CHECKOUT_RE.fullmatch(_text(st.get("uses")).strip()) is not None
        and _squash(text) == "${{steps.%s.outputs.token}}" % sid
    ):
        return at
    return None


def _pins_checkout_token(doc: dict, jname: str, job: dict) -> tuple[set[int], dict[int, str]]:
    """(admitted step indices, refusal reason per refused bws-secrets/app-token step) for one job; see the ruling above."""
    steps = list(_steps(job))
    bws = [i for i, s in enumerate(steps) if _text(s.get("uses")).strip() == _PINS_BWS_USES]
    tok = [i for i, s in enumerate(steps) if _text(s.get("uses")).strip() == _PINS_APP_USES]
    if not bws and not tok:
        return set(), {}

    def refuse(why: str) -> tuple[set[int], dict[int, str]]:
        return set(), dict.fromkeys(bws + tok, why)

    if len(bws) != 1 or len(tok) != 1:
        return refuse(
            "the read-only checkout token needs exactly one bws-secrets and one app-token step in the job, found %d and %d"
            % (len(bws), len(tok))
        )
    b, t = bws[0], tok[0]
    if t != b + 1:
        return refuse("app-token must directly follow bws-secrets")
    why = _pins_bws_shape(steps[b]) or _pins_token_shape(steps[t])
    if why:
        return refuse(why)
    s = t + 1
    if s >= len(steps) or not _pins_is_scrub(steps[s]):
        return refuse(
            "the step right after app-token must be exactly `%s`, since bws-secrets exports both to the rest of the job"
            % "; ".join(sorted(_PINS_SCRUB_LINES))
        )
    sid = _text(steps[t].get("id"))
    ctx = (jname, job.get("steps"), {id(st): i for i, st in enumerate(steps)}, s, sid)
    used: set[int] = set()
    for path, text in _leaves(doc):
        for expr in _exprs(path, text):
            for m in _PINS_STEPS_RE.finditer(expr):
                if m.group(1) is not None and m.group(1).lower() != sid.lower():
                    continue
                at = _pins_token_read_at(path, text, ctx)
                if at is None:
                    return refuse(
                        "steps.%s is read at %s, not only as `with.token` of a SHA-pinned actions/checkout after the blanking step"
                        % (sid, ".".join(str(p) for p in path))
                    )
                used.add(at)
    if not used:
        return refuse("no SHA-pinned actions/checkout after the blanking step takes the token")
    for at in sorted(used):
        with_ = steps[at].get("with")
        persist = with_.get("persist-credentials") if isinstance(with_, dict) else None
        folded = [str(k).lower() for k in with_] if isinstance(with_, dict) else []
        if len(folded) != len(set(folded)):
            return refuse(
                "the token-taking checkout at step %d spells one input twice in different case; action inputs are case-insensitive, so which one wins is not visible here"
                % (at + 1)
            )
        if persist is not False and persist != "false":
            return refuse(
                "the token-taking checkout at step %d must set `persist-credentials: false`, or the token stays in .git/config for every later step"
                % (at + 1)
            )
    last = max(used)
    if sorted(used) != list(range(s + 1, last + 1)):
        return refuse(
            "the token-taking checkouts must run back to back right after the blanking step, so no other step runs while the token is in the global git config"
        )
    g = last + 1
    if g >= len(steps) or not _pins_is_git_scrub(steps[g]):
        return refuse(
            "the step right after the last token-taking checkout must be exactly the global git config scrub (`_PINS_GIT_SCRUB_LINES`), since app-token leaves the token there for every later step"
        )
    return {b, t, s, g}, {}


def analyse_pins_soaked(doc: object) -> tuple[list[tuple[str, str]], list[str]]:
    """(findings, shape) for pins-soaked.yml. A non-mapping document is every kind of failure at once."""
    out: list[tuple[str, str]] = []
    if not isinstance(doc, dict):
        return [("pins-soaked-triggers", "<not a mapping>")], []
    on = _pins_triggers(doc)
    sched = on.get("schedule")
    crons = [c.get("cron") for c in sched if isinstance(c, dict)] if isinstance(sched, list) else []
    run_on = on.get("workflow_run")
    watched = run_on.get("workflows") if isinstance(run_on, dict) else None
    for missing, ok in (
        ("schedule", bool(crons)),
        ("workflow_dispatch", "workflow_dispatch" in on),
        (
            "workflow_run of %s" % PINS_SOAKED_WORKFLOW,
            isinstance(watched, list) and PINS_SOAKED_WORKFLOW in watched,
        ),
    ):
        if not ok:
            out.append(("pins-soaked-triggers", missing))
    if not _read_only(doc.get("permissions")):
        out.append(("pins-soaked-permissions", "workflow level"))
    raw_jobs = doc.get("jobs")
    jobs: dict = raw_jobs if isinstance(raw_jobs, dict) else {}
    outside_jobs = {k: v for k, v in doc.items() if k != "jobs"}
    if _pins_secret(outside_jobs) or _pins_reads_bws(outside_jobs):
        out.append(("pins-soaked-writes", "workflow level"))
    applies = uploads = reds = tokens = 0
    for jname, job in jobs.items():
        if not isinstance(job, dict):
            continue
        # env, container, services and the rest of the job outside its steps; a `secrets:` block of any form hands secrets to a called workflow.
        outside = {k: v for k, v in job.items() if k != "steps"}
        if "secrets" in job or _pins_secret(outside, job.get("if")) or _pins_reads_bws(outside):
            out.append(("pins-soaked-writes", "job %s" % jname))
        steps = list(_steps(job))
        admitted, refused = _pins_checkout_token(doc, jname, job)
        tokens += bool(admitted)
        apply_ids = [
            _text(st.get("id"))
            for st in steps
            if _text(st.get("id")) and _pins_publishes_rc(_text(st.get("run")))
        ]
        red_ifs = [_pins_red_if_re(sid) for sid in apply_ids]
        if "permissions" in job and not _read_only(job.get("permissions")):
            out.append(("pins-soaked-permissions", "job %s" % jname))
        for i, st in enumerate(steps):
            run, uses = _text(st.get("run")), _text(st.get("uses"))
            label = _step_label(jname, i, st)
            if i in admitted:
                pass
            elif (
                _pins_writes(run)
                or any(w in uses.lower() for w in _PINS_WRITE_USES)
                or _pins_secret(st, st.get("if"))
            ):
                why = refused.get(i)
                out.append(("pins-soaked-writes", "%s [%s]" % (label, why) if why else label))
            elif _pins_reads_bws(st):
                out.append(
                    (
                        "pins-soaked-writes",
                        "%s [reads a BWS_* value or the whole env context; only the admitted checkout token steps may]"
                        % label,
                    )
                )
            cond = _text(st.get("if"))
            if any(r.search(cond) for r in red_ifs) and _PINS_EXIT_RE.search(run):
                reds += 1
            if _PINS_APPLY_RE.search(run) and "--out" in run and "--json" in run:
                applies += 1
            if "actions/upload-artifact@" in uses:
                uploads += 1
    if not applies:
        out.append(("pins-soaked-no-apply", "<no `pins -- apply-soaked --json --out` step>"))
    if not uploads:
        out.append(("pins-soaked-no-upload", "<no upload-artifact step>"))
    if not reds:
        out.append(
            (
                "pins-soaked-no-red-path",
                "<no `if: steps.<apply id>.outputs.rc != '0'` step ending in `exit 1`, where the apply step has an id, runs `rc=$?` on the line after the apply with no `||` on it, and writes rc=$rc to $GITHUB_OUTPUT>",
            )
        )
    return out, [
        "%d cron(s), %d apply step(s), %d upload step(s), contents: read only"
        % (len(crons), applies, uploads),
        "%d read-only checkout token(s) (bws-secrets, app-token preset readonly, BWS_* blanked, checkout with.token only and persist-credentials false, global git config scrubbed)"
        % tokens,
    ]


def pins_soaked_message_for(kind: str, name: str, path: str) -> str | None:
    head = "INVARIANT-FAIL: pins-soaked: "
    if kind == "pins-soaked-triggers":
        return head + "%s is missing the trigger `%s`; the daily report would stop arriving." % (
            path,
            name,
        )
    if kind == "pins-soaked-permissions":
        return (
            head
            + "%s (%s) grants more than `contents: read`; the workflow reports and opens nothing."
            % (path, name)
        )
    if kind == "pins-soaked-writes":
        return (
            head
            + "%s: %s can write (a push, commit, tag, gh call, minted token, PR action or a secret passed in); this workflow is artifact-only, and the one token it may mint is the read-only checkout token of the 2026-10-23 ruling (bws-secrets with only GITHUB_APP_PRIVATE_KEY and GITHUB_APP_ID, app-token with an id and preset: readonly, a step blanking both BWS_* values in $GITHUB_ENV, the token only as with.token of SHA-pinned actions/checkout steps with persist-credentials: false run back to back, then the step scrubbing x-access-token from the global git config)."
            % (path, name)
        )
    if kind == "pins-soaked-no-apply":
        return head + "%s has %s, so it reports nothing (nothing to check cannot pass)." % (
            path,
            name,
        )
    if kind == "pins-soaked-no-upload":
        return head + "%s has %s, so the report is lost with the runner." % (path, name)
    if kind == "pins-soaked-no-red-path":
        return head + "%s has %s, so a refused or failed apply would end the run green." % (
            path,
            name,
        )
    return None


def _pins_soaked_phase(pins_file: str) -> tuple[list[str], list[str]]:
    """(errors, info lines). A missing or unparseable file is an error, never a pass."""
    if not os.path.isfile(pins_file):
        return [
            "INVARIANT-FAIL: pins-soaked: no file at %s (nothing to check cannot pass)" % pins_file
        ], []
    try:
        doc = load_workflow(pins_file)
    except SetupExitError as exc:
        return ["INVARIANT-FAIL: pins-soaked: %s" % exc.message.strip()], []
    findings, shape = analyse_pins_soaked(doc)
    errors = [m for k, n in findings if (m := pins_soaked_message_for(k, n, pins_file)) is not None]
    if errors:
        return errors, []
    return [], ["pins-soaked holds: " + "; ".join(shape)]


# THE WORKFLOW-ESTATE PINS (2026-10-23, asked for by the Stop hook's regression judge). Two fixes landed that day that no check could catch, so both are pinned here over EVERY workflow and composite action, not one named file:
#
#   * `pipe-no-pipefail` (commit 41437ea6f). A `run:` with no explicit `shell:` runs under `bash -e {0}`, which has NO pipefail, so `report | tee -a "$GITHUB_STEP_SUMMARY"` took tee's exit 0 and a failing report passed green. A run that contains a shell pipe must run under the bare `shell: bash` (GitHub expands it to `bash --noprofile --norc -eo pipefail {0}`), under a custom shell line naming pipefail, or `set -o pipefail` (any `set` spelling carrying it) on or before the pipe's line. Every pipe counts, not only a final `tee`: `cmd | tail` and `cmd | grep` lose the exit code the same way.
#   * `dispatch-write-off-default-branch` (commit f8d184807). `workflow_dispatch` runs the file from the branch the dispatcher selects, so a write-capable job in a dispatchable workflow runs unreviewed code with a write credential unless its `if:` carries `DEFAULT_BRANCH_GUARD` as a top-level conjunct. Write-capable means: a step minting the app-token action with any preset outside `READ_PRESETS` (the same action path and `preset:` key the pins-soaked rules read; an absent preset is the action's `readonly` default, an expression preset is not provably read-only), an effective `contents: write` (or `write-all`) at job or workflow level, or a call to a local reusable workflow holding such a job.
PIPEFAIL_KINDS = ("pipe-no-pipefail", "estate-no-files", "estate-no-runs")
DISPATCH_KINDS = ("dispatch-write-off-default-branch",)
DEFAULT_BRANCH_GUARD = (
    "github.ref == format('refs/heads/{0}', github.event.repository.default_branch)"
)
READ_PRESETS = frozenset({"readonly", "pr-read"})
# Shells whose run body is not a POSIX shell script, so a `|` in it is not a pipeline. `pwsh` is also the implicit shell on a windows runner.
_NON_SH_SHELLS = ("pwsh", "powershell", "cmd", "python", "node")
_PIPEFAIL_SET_RE = re.compile(r"\bset\b[^\n;#|&]*?-[A-Za-z]*o\s+pipefail\b")
# `(?<!<)` keeps a here-string (`<<<foo`) from matching as a heredoc whose delimiter is `foo`.
_HEREDOC_RE = re.compile(r"(?<!<)<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
_EXPR_SPAN_RE = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)


def _shell_skeleton(script: str) -> list[str]:
    """The script with quoted text, comments, heredoc bodies and `${{ }}` expressions blanked, one entry per source line, so only operators the shell itself reads survive.

    A `$(...)` is shell code wherever it sits, inside double quotes included (`x="$(a | b)"` is a pipeline whose status the assignment takes), so it is kept. A state stack tracks quotes, command substitutions and heredocs across lines; backticks are not read.
    """
    text = _EXPR_SPAN_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), script)
    out: list[str] = []
    heredoc: tuple[str, bool] | None = None
    # Each frame is a state: "n" top-level code, "c" inside $( ), "a" inside $(( )), '"' or "'" inside quotes. A "c" or "a" frame carries its own paren depth.
    stack: list[list] = [["n", 0]]
    for line in text.split("\n"):
        if heredoc is not None:
            delim, dash = heredoc
            if (line.lstrip("\t") if dash else line).rstrip() == delim:
                heredoc = None
            out.append("")
            continue
        kept: list[str] = []
        i = 0
        pending: tuple[str, bool] | None = None
        while i < len(line):
            ch = line[i]
            state = stack[-1][0]
            if state == "'":
                if ch == "'":
                    stack.pop()
                kept.append(" ")
                i += 1
                continue
            if state == "a":
                # $(( )) arithmetic: `|` there is bitwise OR, never a pipe.
                if ch == "(":
                    stack[-1][1] += 1
                elif ch == ")":
                    if stack[-1][1] == 0 and line.startswith("))", i):
                        stack.pop()
                        kept.append("  ")
                        i += 2
                        continue
                    stack[-1][1] -= 1
                kept.append(" ")
                i += 1
                continue
            if state == '"':
                if ch == "\\":
                    kept.append("  ")
                    i += 2
                elif line.startswith("$(", i) and not line.startswith("$((", i):
                    stack.append(["c", 0])
                    kept.append("  ")
                    i += 2
                else:
                    if ch == '"':
                        stack.pop()
                    kept.append(" ")
                    i += 1
                continue
            # code: "n" or "c"
            if ch == "\\":
                kept.append("  ")
                i += 2
                continue
            if ch in "'\"":
                stack.append([ch, 0])
                kept.append(" ")
                i += 1
                continue
            if ch == "#" and (i == 0 or line[i - 1] in " \t;|&("):
                break
            if line.startswith("$((", i):
                stack.append(["a", 0])
                kept.append("   ")
                i += 3
                continue
            if line.startswith("$(", i):
                stack.append(["c", 0])
                kept.append("  ")
                i += 2
                continue
            if state == "c" and ch == "(":
                stack[-1][1] += 1
            elif state == "c" and ch == ")":
                if stack[-1][1] == 0:
                    stack.pop()
                    kept.append(" ")
                    i += 1
                    continue
                stack[-1][1] -= 1
            m = _HEREDOC_RE.match(line, i)
            if m:
                pending = (m.group(3), bool(m.group(1)))
                kept.append(" " * (m.end() - i))
                i = m.end()
                continue
            kept.append(ch)
            i += 1
        out.append("".join(kept))
        if pending is not None and stack[-1][0] in ("n", "c"):
            heredoc = pending
    return out


_PIPE_RE = re.compile(r"(?<![|>])\|(?!\|)")


def _case_pattern_lines(skeleton: list[str]) -> set[int]:
    """Indices of lines inside a `case ... in ... esac` whose `|` belongs to a pattern (`a|b)`), not a pipeline."""
    lines: set[int] = set()
    depth = 0
    for idx, line in enumerate(skeleton):
        if re.search(r"\bcase\b.*\bin\b", line):
            depth += 1
        if depth and re.match(r"^\s*[^()]*\)", line) and not re.match(r"^\s*\S+\s*\(\)", line):
            head = line.split(")", 1)[0]
            if "|" in head:
                lines.add(idx)
        if re.search(r"\besac\b", line):
            depth = max(0, depth - 1)
    return lines


def pipe_lines(script: str) -> list[int]:
    """1-based line numbers of the script's shell pipe operators (`|` and `|&`, never `||` or the `>|` clobber)."""
    skeleton = _shell_skeleton(script)
    case_lines = _case_pattern_lines(skeleton)
    found: list[int] = []
    for idx, line in enumerate(skeleton):
        probe = line
        if idx in case_lines:
            probe = line.split(")", 1)[1] if ")" in line else ""
        if _PIPE_RE.search(probe):
            found.append(idx + 1)
    return found


def pipefail_line(script: str) -> int | None:
    """The 1-based line of the first `set` that turns pipefail on, outside quotes and comments; None when none does."""
    for idx, line in enumerate(_shell_skeleton(script)):
        if _PIPEFAIL_SET_RE.search(line):
            return idx + 1
    return None


def _pipefail_precedes_pipe(script: str, line_no: int) -> bool:
    """True when, on the shared 1-based line, the pipefail `set` starts before the first pipe operator (`set -o pipefail; a | b`)."""
    line = _shell_skeleton(script)[line_no - 1]
    setting = _PIPEFAIL_SET_RE.search(line)
    pipe = _PIPE_RE.search(line)
    return setting is not None and (pipe is None or setting.start() < pipe.start())


def _defaults_shell(node: object) -> str:
    defaults = node.get("defaults") if isinstance(node, dict) else None
    run = defaults.get("run") if isinstance(defaults, dict) else None
    return _text(run.get("shell")).strip() if isinstance(run, dict) else ""


def _shell_verdict(shell: str, runs_on: str, script: str) -> str | None:
    """None when the run is safe, otherwise why its pipe loses the exit code."""
    lines = pipe_lines(script)
    if not lines:
        return None
    if shell == "bash" or "pipefail" in shell:
        return None
    if not shell and "windows" in runs_on.lower() and "${{" not in runs_on:
        return None
    first = shell.split(maxsplit=1)[0].lower() if shell else ""
    if first and any(first.startswith(s) for s in _NON_SH_SHELLS):
        return None
    on = pipefail_line(script)
    if on is not None and (
        on < lines[0] or (on == lines[0] and _pipefail_precedes_pipe(script, on))
    ):
        return None
    where = "line %d" % lines[0]
    if on is not None:
        return "%s pipes before `set -o pipefail` on line %d" % (where, on)
    return "%s pipes under %s with no pipefail" % (
        where,
        "`shell: %s`" % shell if shell else "the implicit `bash -e {0}`",
    )


def analyse_pipefail(doc: object) -> tuple[list[tuple[str, str]], int, int]:
    """(findings, runs read, runs that pipe) for one workflow or composite action document."""
    if not isinstance(doc, dict):
        return [], 0, 0
    out: list[tuple[str, str]] = []
    runs = pipes = 0
    top_shell = _defaults_shell(doc)
    units: list[tuple[str, str, str, list]] = []
    jobs = doc.get("jobs")
    if isinstance(jobs, dict):
        for jname, job in jobs.items():
            if not isinstance(job, dict):
                continue
            shell = _defaults_shell(job) or top_shell
            units.append((str(jname), shell, _text(job.get("runs-on")), _steps(job)))
    action_runs = doc.get("runs")
    if isinstance(action_runs, dict) and isinstance(action_runs.get("steps"), list):
        units.append(("<composite>", "", "", _steps(action_runs)))
    for jname, shell, runs_on, steps in units:
        for i, st in enumerate(steps):
            script = st.get("run")
            if not isinstance(script, str):
                continue
            runs += 1
            pipes += bool(pipe_lines(script))
            why = _shell_verdict(_text(st.get("shell")).strip() or shell, runs_on, script)
            if why:
                out.append(("pipe-no-pipefail", "%s: %s" % (_step_label(jname, i, st), why)))
    return out, runs, pipes


def _strip_expr(cond: str) -> str:
    cond = cond.strip()
    if cond.startswith("${{") and cond.endswith("}}"):
        cond = cond[3:-2]
    return " ".join(cond.split())


def _top_level_split(expr: str, op: str) -> list[str]:
    parts: list[str] = []
    depth, quote, start, i = 0, "", 0, 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            if ch == quote:
                quote = ""
        elif ch == "'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and expr.startswith(op, i):
            parts.append(expr[start:i])
            i += len(op)
            start = i
            continue
        i += 1
    parts.append(expr[start:])
    return [p.strip() for p in parts]


def _unparen(expr: str) -> str:
    """`expr` without parentheses that enclose ALL of it; `(a) && (b)` is left alone."""
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        for i, ch in enumerate(expr):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and i < len(expr) - 1:
                return expr
        expr = expr[1:-1].strip()
    return expr


_GUARD_FORMS = frozenset(
    {
        DEFAULT_BRANCH_GUARD,
        "format('refs/heads/{0}', github.event.repository.default_branch) == github.ref",
    }
)


def has_default_branch_guard(cond: object) -> bool:
    """True when `cond` is a conjunction with `DEFAULT_BRANCH_GUARD` as one of its top-level conjuncts; a guard under `||` or `!` guards nothing."""
    expr = _unparen(_strip_expr(_text(cond)))
    if not expr or len(_top_level_split(expr, "||")) > 1:
        return False
    return any(_unparen(c) in _GUARD_FORMS for c in _top_level_split(expr, "&&"))


def _writes_contents_any(perms: object) -> bool:
    if isinstance(perms, str):
        return perms.strip() == "write-all"
    return isinstance(perms, dict) and _text(perms.get("contents")).strip() == "write"


def _write_token_steps(job: dict) -> list[str]:
    found = []
    for i, st in enumerate(_steps(job)):
        if _text(st.get("uses")).strip() != APP_MINT_ACTION:
            continue
        with_ = st.get("with")
        preset = _text(with_.get("preset")).strip() if isinstance(with_, dict) else ""
        if (preset or "readonly") not in READ_PRESETS:
            found.append("step %d mints app-token preset %s" % (i, preset))
    return found


def _job_write_reasons(
    doc: dict, job: dict, load: typing.Callable[[str], object] | None, seen: frozenset = frozenset()
) -> list[str]:
    reasons = list(_write_token_steps(job))
    perms = job["permissions"] if "permissions" in job else doc.get("permissions")
    if _writes_contents_any(perms):
        reasons.append("holds contents: write")
    uses = _text(job.get("uses")).strip()
    if uses.startswith("./.github/workflows/") and load is not None and uses not in seen:
        callee = load(uses[2:])
        if isinstance(callee, dict):
            cjobs = callee.get("jobs")
            for cname, cjob in cjobs.items() if isinstance(cjobs, dict) else ():
                if isinstance(cjob, dict) and _job_write_reasons(callee, cjob, load, seen | {uses}):
                    reasons.append("calls %s, whose job %s can write" % (uses, cname))
                    break
    return reasons


def analyse_dispatch(
    doc: object, load: typing.Callable[[str], object] | None = None
) -> tuple[list[tuple[str, str]], int]:
    """(findings, write-capable dispatchable jobs) for one workflow. `load` reads a repo-relative path, for local reusable workflows; None skips that leg."""
    if not isinstance(doc, dict) or "workflow_dispatch" not in _pins_triggers(doc):
        return [], 0
    out: list[tuple[str, str]] = []
    writers = 0
    jobs = doc.get("jobs")
    for jname, job in jobs.items() if isinstance(jobs, dict) else ():
        if not isinstance(job, dict):
            continue
        reasons = _job_write_reasons(doc, job, load)
        if not reasons:
            continue
        writers += 1
        if not has_default_branch_guard(job.get("if")):
            out.append(
                ("dispatch-write-off-default-branch", "job %s (%s)" % (jname, "; ".join(reasons)))
            )
    return out, writers


def estate_files(root_dir: str) -> list[str]:
    """Every workflow (`.github/workflows/*.yml|yaml`) and every composite action at any depth (`.github/actions/**/action.yml|yaml`), sorted, as repo-relative paths: the same set `check:ci-workflows` reads."""
    found = []
    wf = os.path.join(root_dir, ".github", "workflows")
    if os.path.isdir(wf):
        found += [
            ".github/workflows/" + n for n in sorted(os.listdir(wf)) if re.match(r".+\.ya?ml$", n)
        ]
    actions = os.path.join(root_dir, ".github", "actions")
    for dirpath, dirnames, filenames in os.walk(actions):
        dirnames.sort()
        for leaf in ("action.yml", "action.yaml"):
            if leaf in filenames:
                found.append(
                    os.path.relpath(os.path.join(dirpath, leaf), root_dir).replace(os.sep, "/")
                )
    return sorted(found)


def estate_message_for(kind: str, name: str, path: str) -> str | None:
    if kind == "pipe-no-pipefail":
        return (
            "INVARIANT-FAIL: pipe-no-pipefail: %s: %s. Without pipefail the step takes the LAST "
            "command's exit code, so a failing producer piped into tee/tail/grep ends green "
            "(commit 41437ea6f). Fix: add `shell: bash` to the step (GitHub runs it as "
            "`bash -eo pipefail`), or put `set -o pipefail` before the pipe." % (path, name)
        )
    if kind == "dispatch-write-off-default-branch":
        return (
            "INVARIANT-FAIL: dispatch-write-off-default-branch: %s: %s is write-capable in a "
            "workflow_dispatch workflow, and dispatch runs the file from whichever branch the "
            "dispatcher selects, so unreviewed code would hold the write credential (commit "
            "f8d184807). Fix: make `%s` a top-level `&&` conjunct of the job's `if:`."
            % (path, name, DEFAULT_BRANCH_GUARD)
        )
    if kind == "estate-no-files":
        return (
            "INVARIANT-FAIL: workflow-estate: no workflow or action file under %s (nothing to check cannot pass)"
            % path
        )
    if kind == "estate-no-runs":
        return (
            "INVARIANT-FAIL: workflow-estate: %d file(s) read but no `run:` step found (the pipefail pin checked nothing)"
            % int(name)
        )
    return None


def _estate_phase(root_dir: str) -> tuple[list[str], list[str]]:
    """(errors, info lines) for both estate pins. Zero files, zero runs or an unparseable file is an error."""
    files = estate_files(root_dir)
    if not files:
        return [estate_message_for("estate-no-files", "", root_dir + "/.github") or ""], []
    cache: dict[str, object] = {}

    def load(rel: str) -> object:
        if rel not in cache:
            path = os.path.join(root_dir, rel)
            cache[rel] = load_workflow(path) if os.path.isfile(path) else None
        return cache[rel]

    errors: list[str] = []
    runs = pipes = dispatchable = writers = 0
    for rel in files:
        try:
            doc = load(rel)
        except SetupExitError as exc:
            errors.append("INVARIANT-FAIL: workflow-estate: %s" % exc.message.strip())
            if "not importable" in exc.message:
                # One line, not one per file: no file can parse.
                return errors, []
            continue
        found, r, p = analyse_pipefail(doc)
        runs, pipes = runs + r, pipes + p
        try:
            dfound, w = analyse_dispatch(doc, load)
        except SetupExitError as exc:
            errors.append("INVARIANT-FAIL: workflow-estate: %s" % exc.message.strip())
            continue
        if isinstance(doc, dict) and "workflow_dispatch" in _pins_triggers(doc):
            dispatchable += 1
        writers += w
        errors += [m for k, n in found + dfound if (m := estate_message_for(k, n, rel)) is not None]
    if runs == 0:
        errors.append(estate_message_for("estate-no-runs", str(len(files)), "") or "")
    if errors:
        return errors, []
    return [], [
        "workflow estate holds: %d file(s), %d run step(s), %d piping, each under shell: bash "
        "or set -o pipefail; %d workflow_dispatch workflow(s), %d write-capable job(s), each "
        "guarded to the default branch" % (len(files), runs, pipes, dispatchable, writers),
        (
            "  Blind spot: a pipe inside backticks is not read, nor a pipe in a script a run "
            "step calls, nor a job with no permissions block on a repository whose default "
            "token can write."
        ),
    ]


def _guarded(path: str) -> tuple[list[tuple[str, str]] | None, int]:
    """Run the analysis the way bash runs the heredoc: any failure is rc != 0.

    Returns (findings, rc). rc is 0 on success, 2 for a SETUP exit and 1 for a crash, mirroring the inner Python's own `sys.exit` codes -- the caller then reports `(exit %d)` with that number, which is the only place the 1-vs-2 distinction is observable from outside.
    """
    try:
        doc = load_workflow(path)
        return analyse(doc), 0
    except SetupExitError as exc:
        sys.stderr.write(exc.message)
        sys.stderr.flush()
        return None, 2
    except BaseException:
        traceback.print_exc()
        sys.stderr.flush()
        return None, 1


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments and parses none

    root_dir = str(paths.repo_root())
    real_ci = os.path.join(root_dir, ".github", "workflows", "ci.yml")
    workflow_file = os.environ.get("WORKFLOW_FILE") or real_ci
    cd_file = os.environ.get("CD_WORKFLOW_FILE") or ""
    # The release-order phase: on the real ci.yml, or when a cd-v2 file is named explicitly. See the module docstring for why a synthetic ci.yml fixture does not get it.
    release_phase = bool(cd_file) or os.path.realpath(workflow_file) == os.path.realpath(real_ci)
    cd_file = cd_file or os.path.join(root_dir, ".github", "workflows", "cd-v2.yml")
    action_file = os.environ.get("APP_TOKEN_ACTION_FILE") or os.path.join(
        root_dir, ".github", "actions", "app-token", "action.yml"
    )
    hk_file = os.environ.get("HOUSEKEEPING_WORKFLOW_FILE") or os.path.join(
        root_dir, ".github", "workflows", "housekeeping.yml"
    )
    pins_file = os.environ.get("PINS_SOAKED_WORKFLOW_FILE") or os.path.join(
        root_dir, ".github", "workflows", "pins-soaked.yml"
    )
    quality_file = os.environ.get("QUALITY_WORKFLOW_FILE") or os.path.join(
        root_dir, ".github", "workflows", "ci-quality.yml"
    )

    # Anti-vacuity: a missing workflow means the gate checked nothing, and nothing checked must never read as green.
    if not os.path.isfile(workflow_file):
        log.error(
            "INVARIANT-FAIL: workflow-missing: no file at %s (nothing to check cannot pass)"
            % workflow_file
        )
        return 1

    # `command -v python3 >/dev/null 2>&1 || { log_error ...; exit 2; }`. Kept
    # even though this module already IS python3; see the module docstring.
    if shutil.which("python3") is None:
        log.error("python3 is required to parse %s" % workflow_file)
        return 2

    findings, rc = _guarded(workflow_file)
    if findings is None:
        log.error(
            "INVARIANT-FAIL: analysis of %s failed (exit %d); an unparsed workflow cannot pass"
            % (workflow_file, rc)
        )
        return 1

    failed = 0
    for kind, name in findings:
        if not kind:
            continue
        message = message_for(kind, name, workflow_file)
        if message is None:
            continue
        log.error(message)
        failed = 1

    release_info: list[str] = []
    if release_phase:
        release_errors, release_info = _release_phase(workflow_file, cd_file, action_file)
        preflight_errors, preflight_info = _preflight_phase(workflow_file, cd_file, hk_file)
        upstream_errors, upstream_info = _upstream_gate_phase(workflow_file, quality_file)
        pins_errors, pins_info = _pins_soaked_phase(pins_file)
        estate_errors, estate_info = _estate_phase(root_dir)
        release_info += preflight_info + upstream_info + pins_info + estate_info
        for message in (
            release_errors + preflight_errors + upstream_errors + pins_errors + estate_errors
        ):
            log.error(message)
            failed = 1

    if failed != 0:
        log.error("ci workflow invariants FAILED")
        return 1
    log.info(
        "ci workflow invariants hold: every channel-derived docker_tag job refuses an empty "
        "channel; the bump-none skip_release decision is declared once in initialize, passed "
        "to stage-artifacts, gates both pre-publish validators, and is not re-decided in "
        "finalize-release-sentinel"
    )
    # The fixture runs keep the twin's recorded bytes exactly; the real-tree run says which phase is ci.yml-only.
    scope = "the ci.yml phase reads ci.yml only" if release_phase else "this reads ci.yml only"
    log.info(
        "  Blind spot: %s. It cannot see whether cd-stage.yml FORWARDS "
        "skip_release to the upload scripts (check-workflow-gates.sh CHECK 2b/2c covers the "
        "input contract), nor whether the scripts honour it (their own gate test covers that)."
        % scope
    )
    for line in release_info:
        log.info(line)
    if release_phase:
        log.info(
            "  Blind spot: the release-order phase reads the job GRAPH. It cannot see a tag "
            "step that exits 0 without pushing, nor init failing before its tag step, "
            "nor a push made inside a script a cd-v2 step runs; "
            "Check Release State covers the live state."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
