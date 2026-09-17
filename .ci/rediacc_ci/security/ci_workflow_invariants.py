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

import io
import os
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
)


class SetupExit(Exception):  # noqa: N818 - it is a control-flow signal, not an error state
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
        raise SetupExit("SETUP: PyYAML is not importable\n")
    try:
        # `io.open(path, encoding="utf-8")` in the twin. The handle is left to
        # the garbage collector there; closed properly here, which changes no observable byte.
        with io.open(path, encoding="utf-8") as handle:  # noqa: UP020 - the twin's spelling
            return yaml.safe_load(handle)
    except Exception as exc:  # the twin catches bare `Exception` here too
        raise SetupExit("SETUP: %s does not parse as YAML: %s\n" % (path, exc)) from exc


def _import_yaml() -> ModuleType | None:
    try:
        import yaml  # noqa: PLC0415 - deliberately late; this IS the twin's probe
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
    jobs = (doc or {}).get("jobs") or {}  # type: ignore[union-attr]
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

    fin = jobs.get("finalize-release-sentinel")
    if isinstance(fin, dict):
        steps = fin.get("steps")
        steps = steps if isinstance(steps, list) else []
        for st in steps:
            if isinstance(st, dict) and "--decide-only" in str(st.get("run") or ""):
                out.append(("skip-release-second-decision", "finalize-release-sentinel"))
                break

    return out


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
            "`with:`. upload-to-r2.sh's guard then never fires, and a bump-none commit advances "
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
    if kind == "no-candidates":
        # Vacuity guard. If nobody passes a channel-derived docker_tag any more, this gate is asserting nothing and must say so rather than printing a green nobody earned.
        return (
            "INVARIANT-FAIL: no-candidates: no job in %s passes a channel-derived `docker_tag`, "
            "so this gate verified nothing. Retarget or remove it deliberately." % workflow_file
        )
    return None


def _guarded(path: str) -> tuple[list[tuple[str, str]] | None, int]:
    """Run the analysis the way bash runs the heredoc: any failure is rc != 0.

    Returns (findings, rc). rc is 0 on success, 2 for a SETUP exit and 1 for a crash, mirroring the inner Python's own `sys.exit` codes -- the caller then reports `(exit %d)` with that number, which is the only place the 1-vs-2 distinction is observable from outside.
    """
    try:
        doc = load_workflow(path)
        return analyse(doc), 0
    except SetupExit as exc:
        sys.stderr.write(exc.message)
        sys.stderr.flush()
        return None, 2
    except BaseException:  # noqa: BLE001 - a heredoc's traceback is exit 1
        traceback.print_exc()
        sys.stderr.flush()
        return None, 1


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments and parses none

    root_dir = str(paths.repo_root())
    workflow_file = os.environ.get("WORKFLOW_FILE") or os.path.join(
        root_dir, ".github", "workflows", "ci.yml"
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

    if failed != 0:
        log.error("ci workflow invariants FAILED")
        return 1
    log.info(
        "ci workflow invariants hold: every channel-derived docker_tag job refuses an empty "
        "channel; the bump-none skip_release decision is declared once in initialize, passed "
        "to stage-artifacts, gates both pre-publish validators, and is not re-decided in "
        "finalize-release-sentinel"
    )
    log.info(
        "  Blind spot: this reads ci.yml only. It cannot see whether cd-stage.yml FORWARDS "
        "skip_release to the upload scripts (check-workflow-gates.sh CHECK 2b/2c covers the "
        "input contract), nor whether the scripts honour it (their own gate test covers that)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
