#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/scope-shadow.sh` (588 lines).

The scope engine, LIVE: it decides which CI jobs may skip. See the twin's own header for the contract, the three kill switches, the fail-open asymmetry
("it NEVER writes `run_<key>=true`") and why the deciding plan is the baseline
plan rather than the merge-base classify. None of that is restated here.

LIVE CALLER, not repointed: `.github/workflows/ci.yml:348`
`run: OUTPUT_FILE="$GITHUB_OUTPUT" .ci/scripts/ci/scope-shadow.sh`, inside the
`initialize` job every other job depends on. `ci.yml:356-373` then uploads
`.ci/cache/scope-shadow/{scope-classify,scope-baseline,plan}.json`.

-----------------------------------------------------------------------------
THE FIVE INLINE `node -e` PROGRAMS ARE NOT REWRITTEN, THEY ARE CARRIED
-----------------------------------------------------------------------------
`write_plan`, `emit_outputs`, the greenlight `pending` query, the greenlight `applied` rewrite and the conditions summary are each a JavaScript program the twin passes to `node -e`. They call into `skip-plan-reconcile.cjs`, `scope-map.cjs`, `scope-engine.cjs` and `greenlight.cjs`, which are the real decision logic and stay exactly where they are. Reimplementing them in Python would
be porting the ENGINE, which this file is not, and would put a second reader of `JOB_SURFACES` and `CLOSURES` in the tree -- the precise drift the twin's `emit_outputs` refuses at :247-249.

So the five bodies below are byte-for-byte copies, generated out of the twin rather than retyped, and `test_ci_scope_shadow.py::test_the_five_node_programs _are_verbatim` re-reads the twin on every run and fails if either side moves.

-----------------------------------------------------------------------------
`bounded` CALLS THE REAL `timeout(1)`, IT DOES NOT EMULATE ONE
-----------------------------------------------------------------------------
The twin is `bounded() { timeout "$SCOPE_TIMEOUT" "$@"; }`. A
`subprocess.run(timeout=...)` would be an emulation that has to guess three
things: 124 for a killed child, 125 plus `timeout: invalid time interval` for a malformed `SCOPE_SHADOW_TIMEOUT`, and 127 for a missing binary. Prefixing the real `timeout` gets all three for free and cannot drift from the twin. It is
also what makes `SCOPE_SHADOW_TIMEOUT=0.2` a usable lever in the differential.

-----------------------------------------------------------------------------
`emit` DUPLICATES ITSELF WHEN `GITHUB_STEP_SUMMARY` IS UNSET, AND SO DOES THIS
-----------------------------------------------------------------------------
Identical shape to the already-ported sibling: `SUMMARY="${GITHUB_STEP_SUMMARY:-
/dev/stdout}"` and `emit` is `printf '%s\\n' "$@" | tee -a "$SUMMARY"`, so with
no summary file every line is written twice to the same fd. `_dual_write` reproduces that.

THE SAME RESIDUAL DIVERGENCE APPLIES AND IS NOT RE-DERIVED HERE: with `GITHUB_STEP_SUMMARY` unset AND stdout redirected to a regular file, the twin's own output is deterministically garbled by a kernel file-offset race between `tee -a /dev/stdout`'s reopened description and the inherited one. See `rediacc_ci.ci.scope_reconcile_shadow`'s docstring for the measurement. The branch is
unreachable in production (`ci.yml:348` runs under Actions, which always sets `GITHUB_STEP_SUMMARY`), every differential case sets a real summary file, and the port duplicates cleanly instead.

-----------------------------------------------------------------------------
TWO REAL DEFECTS IN THE TWIN, REPRODUCED RATHER THAN FIXED
-----------------------------------------------------------------------------
Invariant 5: this file's twin is live at `ci.yml:348` and changing its bytes changes what CI skips. Both are pinned by tests.

  1. A CRASHED OR TIMED-OUT `pending` QUERY IS REPORTED AS "NOTHING TO ASK"
     (`scope-shadow.sh:394-406`). The query is
     `pending="$(bounded node -e ... 2>"$OUT_DIR/greenlight.err")" || pending=""`,
     and the very next line treats an empty `pending` as
     `_greenlight: nothing to ask (every eligible key is already planned to
     skip)._` Two states collapse into one sentence, and the sentence asserts
     the one that is false: a node crash, a malformed plan.json, or `bounded`
     killing the child at 120s all print a line claiming every key was already
     skipped. The engine's stderr IS captured, into
     `.ci/cache/scope-shadow/greenlight.err`, and then never read by anything --
     the function returns before the digest that would have surfaced it. So the
     failure is invisible in the job log and invisible in the step summary,
     which is the "unreadable instrument" failure this same file's header
     (`:96-104`) was written to fix, arriving through the back door.
     Blast radius, measured not estimated: the greenlight half is skipped
     silently, so every key it would have granted RUNS. That is the fail-open
     direction, which is why this is a diagnosability defect and not a
     correctness one -- but it is also why nobody would notice. On the run
     range the twin's own comment cites (`:293`, 14 consecutive PR runs), a
     permanently-crashing pending query and a genuinely-empty one would have
     produced identical logs.
  2. `|| emit "(no output)"` IS DEAD ON BOTH ARMS (`:522` and `:538`). The
     shell creates `scope-classify.json` / `scope-baseline.json` with the
     redirection BEFORE node runs, so the file always exists by the time
     `head -c 4000 "$file" 2>/dev/null | tee -a "$SUMMARY"` runs; `head` on an
     existing-but-empty file exits 0, and `tee` exits 0, so under `pipefail`
     the pipeline is 0 and the `||` arm cannot be reached. An engine that
     crashed and wrote nothing therefore renders as an EMPTY fenced block, not
     as `(no output)`. Reproduced exactly: `_tee_head` returns False only when
     the file cannot be opened at all, which is the same condition `head`
     fails on.

-----------------------------------------------------------------------------
ONE ORDERING DIFFERENCE THAT IS ARGUED, NOT ASSUMED
-----------------------------------------------------------------------------
`bounded node -e '<conditions>' plan.json | tee -a "$SUMMARY"` (:563-573) is the only place a node process's stdout is STREAMED through `tee` rather than redirected to a file first. `_conditions_block` collects that stdout and then writes it, so if node were to interleave a slow stdout with its own inherited stderr the two sides could order those bytes differently. It cannot here:
the program is a single `process.stdout.write` of one JSON blob at the end, with no stderr on the success path. Stated because the general claim would be false.

K=5 LEDGER: `.ci/shadow/w7p6-scope-shadow.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

# --------------------------------------------------------------------------- The five inline node programs, copied verbatim out of the twin.
#
# ONE ESCAPED LITERAL EACH, ON ONE LINE, and that is deliberate: they were generated by slicing the twin rather than retyped, so there is no place a hand-wrapped continuation could lose a backslash. Reflowing them into adjacent literals would preserve the VALUE and is harmless, but there is nothing to gain
# from it -- the readable copy is the twin, and
# `test_the_five_node_programs_are_verbatim` is what keeps the two the same. ---------------------------------------------------------------------------

# `write_plan` (:190-210).
WRITE_PLAN_JS = '\nconst fs = require("fs");\nconst { annotatePlan } = require(process.argv[1]);\nconst src = process.argv[2];\nconst plan =\n  src === "FORCED"\n    ? require(process.argv[6]).forcedFullPlan("operator-forced-full")\n    : JSON.parse(fs.readFileSync(src, "utf8"));\nplan.run_id = Number(process.env.GITHUB_RUN_ID || 0);\nplan.base_sha = process.argv[3] || null;\nplan.head_sha = process.argv[4] || null;\nconst tri = (v) => (v === "true" ? true : v === "false" ? false : undefined);\nannotatePlan(plan, {\n  full_suite: tri(process.env.FULL_SUITE),\n  pointer_bump_only: tri(process.env.POINTER_BUMP_ONLY),\n  is_bot: tri(process.env.IS_BOT),\n});\nfs.writeFileSync(process.argv[5], JSON.stringify(plan, null, 2));'

# `emit_outputs` (:236-256).
EMIT_OUTPUTS_JS = '\nconst fs = require("fs");\nconst { JOB_SURFACES } = require(process.argv[1]);\nconst plan = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));\nconst mode = plan.mode;\nif (mode !== "full" && mode !== "reduced") {\n  throw new Error(`unusable plan mode: ${JSON.stringify(mode)}`);\n}\nconst jobs = plan.jobs && typeof plan.jobs === "object" ? plan.jobs : {};\nconst planned = Object.keys(jobs).sort().join(",");\nconst known = Object.keys(JOB_SURFACES).sort().join(",");\nif (planned !== known) {\n  throw new Error(`plan key set drifted from scope-map\\n  plan: ${planned}\\n  map:  ${known}`);\n}\nconst lines = [];\nfor (const key of Object.keys(JOB_SURFACES)) {\n  if (jobs[key] && jobs[key].run === false) lines.push(`run_${key}=false`);\n}\nlines.push(`scope_mode=${mode}`);\nprocess.stdout.write(`${lines.join("\\n")}\\n`);'

# `apply_greenlight`'s pending query (:394-401).
PENDING_JS = '\nconst fs = require("fs");\nconst { CLOSURES } = require(process.argv[1]);\nconst plan = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));\nconst jobs = (plan && plan.jobs) || {};\nconst pending = Object.keys(CLOSURES).filter((k) => jobs[k] && jobs[k].run !== false);\nprocess.stdout.write(pending.join(" "));'

# `apply_greenlight`'s plan rewrite (:444-475).
APPLY_JS = '\nconst fs = require("fs");\nconst planPath = process.argv[1];\nconst plan = JSON.parse(fs.readFileSync(planPath, "utf8"));\nconst emitted = fs.readFileSync(process.argv[2], "utf8");\nconst evidence = {};\nconst granted = [];\nfor (const line of emitted.split("\\n")) {\n  let m = /^run_([a-z0-9_]+)=false$/.exec(line);\n  if (m) {\n    granted.push(m[1]);\n    continue;\n  }\n  m = /^evidence_([a-z0-9_]+)=([0-9]+)$/.exec(line);\n  if (m) evidence[m[1]] = m[2];\n}\nconst applied = [];\nfor (const key of granted) {\n  const job = plan.jobs && plan.jobs[key];\n  // An unknown key, an already-skipped one, or a grant with no evidence run\n  // attached is ignored rather than guessed at.\n  if (!job || job.run === false || !evidence[key]) continue;\n  job.run = false;\n  job.reason = `greenlight:${evidence[key]}`;\n  applied.push(`${key}=${evidence[key]}`);\n}\nif (applied.length > 0) {\n  plan.mode = "reduced";\n  fs.writeFileSync(planPath, JSON.stringify(plan, null, 2));\n}\nprocess.stdout.write(applied.join(" "));'

# The pre-existing-conditions summary (:563-573).
CONDITIONS_JS = '\nconst p = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));\nconst exempt = Object.entries(p.jobs || {})\n  .filter(([, v]) => v && v.preexisting_skip)\n  .map(([k, v]) => `${k}:${v.preexisting_skip}`);\nprocess.stdout.write(JSON.stringify({\n  conditions: p.conditions,\n  exempt_keys: exempt,\n  planned_keys: Object.keys(p.jobs || {}).length,\n}, null, 2) + "\\n");'

# `SCOPE_TIMEOUT="${SCOPE_SHADOW_TIMEOUT:-120}"` (:115).
DEFAULT_SCOPE_TIMEOUT = "120"

# `head -c 4000` (:522, :538) and `head -c 1000` (:259, :507, :542, :559).
WIDE_HEAD_BYTES = 4000
NARROW_HEAD_BYTES = 1000

# `--limit 60 --budget 90` (:436). Named so a test can assert the twin still carries the numbers its own comment argues for at :414-435.
GREENLIGHT_LIMIT = "60"
GREENLIGHT_BUDGET = "90"


def _console_root() -> pathlib.Path:
    """The twin's `SCRIPT_DIR/../..` root.

    This file is `<root>/.ci/rediacc_ci/ci/scope_shadow.py`; the twin is
    `<root>/.ci/scripts/ci/scope-shadow.sh`. `paths.repo_root()` is deliberately not used: it honours $REDIACC_CI_ROOT and the twin has no such override, so a fixture pointing one side at a tree and not the other would diverge silently.
    """
    return pathlib.Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- greenlight_digest (:326-374), the one non-trivial pure transformation here. ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"^greenlight\[")
_JOBS_RE = re.compile(r"^greenlight\[[^\]]*\] jobs=")
_PINS_RE = re.compile(r"^greenlight\[[^\]]*\] pins=")
_CLOSURE_RE = re.compile(r"^greenlight\[[^\]]*\] closure=")
_RUNID_HEADER_RE = re.compile(r"^ +run id")
_TRAIL_ROW_RE = re.compile(r"^ +[0-9]+ +")
_VERDICT_RE = re.compile(r"^greenlight\[[^\]]*\] VERDICT: ")
_ONELINER_RE = re.compile(r"^greenlight\[[^\]]*\]: (GREENLIT by run|no greenlight)")
_BLANK_RE = re.compile(r"^[ \t\n\r\f\v]*$")

_STRIP_TO_CLOSURE_RE = re.compile(r"^.*closure=")
_STRIP_FROM_SPACE_RE = re.compile(r" .*$")
_STRIP_TO_VERDICT_RE = re.compile(r"^.*VERDICT: ")
_STRIP_ROW_PREFIX_RE = re.compile(r"^ +[0-9]+ +[0-9a-f]* +")


def greenlight_digest(text: str) -> str:
    """`greenlight_digest` (:326-374), transliterated from its awk.

    ONE LINE PER KEY instead of the raw trail; see the twin's comment at
    :310-325 for why (~450 rows at eighteen keys truncated mid-line under the old `head -c 3000`, so sixteen keys were simply absent).

    FOUR AWK BEHAVIOURS ARE REPRODUCED DELIBERATELY, and each one is a place a Python rewrite naturally differs:

      * THE FIRST RULE HAS NO `next` (:328-332). Every line starting with
        `greenlight[` updates `key` AND then falls through to the rules below,
        including the final catch-all `{ print }`. A `greenlight[x] something
        unrecognised` line therefore both re-keys the digest and is echoed.
      * `sub(/\\].*/, "", key)` cuts at the FIRST `]`, and awk's `sub` is a
        substring operation, not an anchored match.
      * AN UNINITIALISED AWK VARIABLE IS "" IN `%s` AND 0 IN `%d`. A key whose
        VERDICT line never arrived prints an empty verdict column, and a key
        with no trail rows prints `walked=0`, rather than raising a KeyError.
      * `newest[key] = $1 " " row` reads `$1` from the ORIGINAL record, so the
        run id appears twice in the source line and once in the output.

    `key` starts as awk's uninitialised "" so a trail row arriving before any `greenlight[` header is counted under the empty key exactly as awk counts it, rather than crashing.
    """
    order: list[str] = []
    seen: set[str] = set()
    walked: dict[str, int] = {}
    newest: dict[str, str] = {}
    verdict: dict[str, str] = {}
    closure_hash: dict[str, str] = {}
    out: list[str] = []
    key = ""

    for line in text.split("\n")[:-1] if text.endswith("\n") else text.split("\n"):
        if _KEY_RE.match(line):
            key = _KEY_RE.sub("", line, count=1)
            key = re.sub(r"\].*", "", key, count=1)
        if _JOBS_RE.match(line) or _PINS_RE.match(line):
            continue
        if _CLOSURE_RE.match(line):
            if key not in seen:
                order.append(key)
                seen.add(key)
            h = _STRIP_TO_CLOSURE_RE.sub("", line, count=1)
            h = _STRIP_FROM_SPACE_RE.sub("", h, count=1)
            closure_hash[key] = h[:12]
            continue
        if _RUNID_HEADER_RE.match(line):
            continue
        if _TRAIL_ROW_RE.match(line):
            walked[key] = walked.get(key, 0) + 1
            if key not in newest:
                row = _STRIP_ROW_PREFIX_RE.sub("", line, count=1)
                newest[key] = "%s %s" % (line.split()[0], row)
            continue
        if _VERDICT_RE.match(line):
            verdict[key] = _STRIP_TO_VERDICT_RE.sub("", line, count=1)
            continue
        if _ONELINER_RE.match(line):
            continue
        if _BLANK_RE.match(line):
            continue
        out.append(line)

    for k in order:
        out.append(
            "%-22s %-28s closure=%s walked=%d"
            % (k, verdict.get(k, ""), closure_hash.get(k, ""), walked.get(k, 0))
        )
        if k in newest:
            out.append("%-22s   newest %s" % ("", newest[k]))
    return "".join(line + "\n" for line in out)


def shallow_report(shallow: str, grafts: str) -> str:
    """`:148`. `rev-parse` says true but the graft list is empty -> say so.

    Split out because the twin's own comment (:137-143) argues this line is what tells a reader whether to trust everything below it, and a test can then assert the sentence rather than a run producing it by accident.
    """
    if shallow == "true" and grafts == "0":
        return "false (empty graft list; rev-parse says true)"
    return shallow


def main(argv: list[str]) -> int:
    """The twin's whole body, in its order. It takes no arguments, as there."""
    del argv
    root = _console_root()
    script_dir = root / ".ci" / "scripts" / "ci"
    engine = script_dir / "scope-engine.cjs"
    greenlight = script_dir / "greenlight.cjs"
    reconciler = script_dir / "skip-plan-reconcile.cjs"
    scope_map = script_dir / "scope-map.cjs"

    summary_env = os.environ.get("GITHUB_STEP_SUMMARY")
    summary_path = pathlib.Path(summary_env) if summary_env else None

    out_dir_env = os.environ.get("SCOPE_SHADOW_OUT")
    out_dir = (
        pathlib.Path(out_dir_env)
        if out_dir_env
        else script_dir / ".." / ".." / "cache" / "scope-shadow"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    def _dual_write(text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()
        if summary_path is not None:
            with open(summary_path, "a", encoding="utf-8", errors="surrogateescape") as fh:
                fh.write(text)
        else:
            # `SUMMARY` defaults to `/dev/stdout`, so `tee -a` writes the same bytes to the same fd a second time.
            sys.stdout.write(text)
            sys.stdout.flush()

    def emit(*lines: str) -> None:
        """`emit() { printf '%s\\n' "$@" | tee -a "$SUMMARY"; }` (:104-106)."""
        _dual_write("".join(line + "\n" for line in lines))

    def tee_head(path: pathlib.Path, count: int) -> bool:
        """`head -c N "$path" | tee -a "$SUMMARY"`. False when `head` would fail.

        RAW BYTES, no trailing newline added and none stripped: this is a `cat`-shaped pipeline, not an `emit` call.
        """
        try:
            data = path.read_bytes()[:count]
        except OSError:
            return False
        _dual_write(data.decode("utf-8", errors="surrogateescape"))
        return True

    def tee_file(path: pathlib.Path) -> None:
        """`cat "$path" | tee -a "$SUMMARY"` (:265). Whole file, raw bytes."""
        try:
            data = path.read_bytes()
        except OSError:
            return
        _dual_write(data.decode("utf-8", errors="surrogateescape"))

    scope_timeout = os.environ.get("SCOPE_SHADOW_TIMEOUT") or DEFAULT_SCOPE_TIMEOUT

    def bounded(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        """`bounded() { timeout "$SCOPE_TIMEOUT" "$@"; }` (:116), the real binary."""
        return subprocess.run(
            ["timeout", scope_timeout, *args],
            check=False,
            **kwargs,  # type: ignore[arg-type]
        )

    def _git(args: list[str], *, quiet: bool) -> tuple[int, str]:
        """`$(git ... 2>/dev/null)` -- ALL trailing newlines stripped, as `$()` does."""
        proc = subprocess.run(
            ["git", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if quiet else None,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout.rstrip("\n")

    # --- base/head/shallow (:134-148) --------------------------------------
    merge_sha = os.environ.get("MERGE_SHA", "")
    rc, base = _git(["rev-parse", "--verify", "-q", merge_sha + "^1"], quiet=True)
    if rc != 0:
        base = ""
    rc, head = _git(["rev-parse", "--verify", "-q", merge_sha + "^2"], quiet=True)
    if rc != 0:
        head = ""
    if not head:
        head = os.environ.get("HEAD_SHA", "")

    rc, shallow = _git(["rev-parse", "--is-shallow-repository"], quiet=True)
    if rc != 0:
        shallow = "unknown"
    rc, shallow_file = _git(["rev-parse", "--git-path", "shallow"], quiet=True)
    if rc != 0:
        shallow_file = ""
    grafts = "0"
    if shallow_file:
        candidate = pathlib.Path(shallow_file)
        try:
            raw = candidate.read_bytes()
        except OSError:
            raw = b""
        if raw:
            # `wc -l <"$shallow_file"` counts NEWLINES, so a final line with no terminator is not counted -- which is what a graft file never has.
            grafts = str(raw.count(b"\n"))
    shallow = shallow_report(shallow, grafts)

    emit(
        "### Scope engine (LIVE: this decides which jobs run)",
        "",
        "shallow: `%s`, grafts: `%s` (grafts must be 0, or nothing below is meaningful)"
        % (shallow, grafts),
        "base: `%s`  head: `%s`" % (base or "unknown", head or "unknown"),
        "",
    )

    plan_json = out_dir / "plan.json"
    plan_write_err = out_dir / "plan-write.err"

    def write_plan(source: str) -> bool:
        """`write_plan` (:189-210). stdout inherited; stderr to plan-write.err."""
        with open(plan_write_err, "wb") as errfh:
            proc = bounded(
                [
                    "node",
                    "-e",
                    WRITE_PLAN_JS,
                    str(reconciler),
                    source,
                    base,
                    head,
                    str(plan_json),
                    str(engine),
                ],
                stderr=errfh,
            )
        return proc.returncode == 0

    def emit_outputs() -> int:
        """`emit_outputs` (:233-267)."""
        output_file = os.environ.get("OUTPUT_FILE", "")
        if not output_file:
            return 0
        buf = out_dir / "gh-output.txt"
        emit_err = out_dir / "output-emit.err"
        with open(buf, "wb") as outfh, open(emit_err, "wb") as errfh:
            proc = bounded(
                ["node", "-e", EMIT_OUTPUTS_JS, str(scope_map), str(plan_json)],
                stdout=outfh,
                stderr=errfh,
            )
        if proc.returncode != 0:
            emit(
                "_**the output emitter FAILED**: no run_* line was written, so every job",
                "runs. This is a full round with a stated reason, not a silent one._",
                "```",
            )
            tee_head(emit_err, NARROW_HEAD_BYTES)
            emit("```", "")
            return 1
        try:
            with open(output_file, "ab") as fh:
                fh.write(buf.read_bytes())
        except OSError:
            return 1
        emit("**outputs written to $GITHUB_OUTPUT**", "", "```")
        tee_file(buf)
        emit("```", "")
        return 0

    def apply_greenlight() -> int:
        """`apply_greenlight` (:376-485)."""
        if not greenlight.is_file():
            return 0
        try:
            if plan_json.stat().st_size == 0:
                return 0
        except OSError:
            return 0

        gl_err = out_dir / "greenlight.err"
        gl_out = out_dir / "greenlight.out"
        with open(gl_err, "wb") as errfh:
            proc = bounded(
                ["node", "-e", PENDING_JS, str(greenlight), str(plan_json)],
                stdout=subprocess.PIPE,
                stderr=errfh,
                text=True,
            )
        # `pending="$(...)" || pending=""`. DEFECT 1 lives on the next two
        # lines: a crash and a genuinely empty list are the same state here.
        pending = proc.stdout.rstrip("\n") if proc.returncode == 0 else ""

        if not pending:
            emit(
                "_greenlight: nothing to ask (every eligible key is already planned to skip)._",
                "",
            )
            return 0

        args: list[str] = []
        for key in pending.split():
            args.extend(["--key", key])

        with open(gl_out, "wb") as outfh, open(gl_err, "wb") as errfh:
            proc = bounded(
                [
                    "node",
                    str(greenlight),
                    "--repo",
                    os.environ.get("GITHUB_REPOSITORY", ""),
                    "--limit",
                    GREENLIGHT_LIMIT,
                    "--budget",
                    GREENLIGHT_BUDGET,
                    "--debug",
                    *args,
                ],
                stdout=outfh,
                stderr=errfh,
            )
        if proc.returncode != 0:
            emit(
                "_greenlight: the engine did not complete (timeout or crash), so no key was",
                "greenlit and the scope verdict stands unchanged._",
                "",
            )
            return 0

        with open(gl_err, "ab") as errfh:
            proc = bounded(
                ["node", "-e", APPLY_JS, str(plan_json), str(gl_out)],
                stdout=subprocess.PIPE,
                stderr=errfh,
                text=True,
            )
        applied = proc.stdout.rstrip("\n") if proc.returncode == 0 else ""

        emit("**cross-PR greenlight** (asked about: %s)" % pending, "", "```")
        try:
            trail = gl_err.read_text(encoding="utf-8", errors="surrogateescape")
        except OSError:
            trail = ""
        _dual_write(greenlight_digest(trail))
        emit("```")
        if applied:
            emit("**greenlit, and the plan now says so**: `%s`" % applied, "")
        else:
            emit("_no key was greenlit; the scope engine's verdict stands unchanged._", "")
        return 0

    # --- KILL SWITCH, CHECKED BEFORE THE ENGINE (:496-511) ------------------
    if (
        os.environ.get("FORCE_FULL_CI", "") == "true"
        or os.environ.get("FULL_CI_LABEL", "") == "true"
    ):
        override_reason = "the FULL_CI repository variable"
        if os.environ.get("FULL_CI_LABEL", "") == "true":
            override_reason = "the full-ci PR label"
        emit(
            "**OPERATOR OVERRIDE: full CI forced** by %s." % override_reason,
            "The engine did not run: no baseline walk, no classify, no reduction.",
            "",
        )
        if write_plan("FORCED"):
            emit_outputs()
        else:
            emit(
                "_**the forced-full plan writer FAILED**: no attested plan will be",
                "uploaded for this run, so the reconcile step will report 'no attested",
                "plan' and that will be a GAP IN THE EVIDENCE, not a clean result._",
                "```",
            )
            tee_head(plan_write_err, NARROW_HEAD_BYTES)
            emit("```", "")
        return 0

    # --- DIAGNOSTIC ONLY (:513-526) -----------------------------------------
    classify_json = out_dir / "scope-classify.json"
    if base and head:
        changed_raw = out_dir / "changed.raw"
        with open(changed_raw, "wb") as outfh:
            subprocess.run(
                ["git", "diff-tree", "-r", "--raw", "--no-commit-id", base, head],
                stdout=outfh,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        with open(classify_json, "wb") as outfh:
            bounded(
                ["node", str(engine), "--classify", "--files", str(changed_raw)],
                stdout=outfh,
                stderr=subprocess.DEVNULL,
            )
        emit(
            "**--classify over the merge-base delta** (diagnostic; decides nothing)", "", "```json"
        )
        if not tee_head(classify_json, WIDE_HEAD_BYTES):
            # DEFECT 2: unreachable, because the redirection above created the file whether or not node wrote to it.
            emit("(no output)")
        emit("```", "")
    else:
        emit("_skipped --classify: no base/head pair resolved_", "")

    # --- THE DECIDING PLAN (:528-547) ---------------------------------------
    baseline_json = out_dir / "scope-baseline.json"
    baseline_err = out_dir / "scope-baseline.err"
    if head:
        with open(baseline_json, "wb") as outfh, open(baseline_err, "wb") as errfh:
            bounded(
                [
                    "node",
                    str(engine),
                    "--resolve-baseline",
                    "--repo",
                    os.environ.get("GITHUB_REPOSITORY", ""),
                    "--head",
                    head,
                    "--merge-sha",
                    merge_sha,
                ],
                stdout=outfh,
                stderr=errfh,
            )
        emit("**--resolve-baseline** (THIS is the plan that gates jobs)", "", "```json")
        if not tee_head(baseline_json, WIDE_HEAD_BYTES):
            emit("(no output)")
        emit("```")
        if baseline_err.exists() and baseline_err.stat().st_size > 0:
            emit("stderr:", "```")
            tee_head(baseline_err, NARROW_HEAD_BYTES)
            emit("```")
    else:
        emit("_skipped --resolve-baseline: no head sha resolved, so this round is full_", "")

    # --- write, greenlight, emit (:549-583) ---------------------------------
    if baseline_json.exists() and baseline_json.stat().st_size > 0:
        if not write_plan(str(baseline_json)):
            emit(
                "_**the plan writer FAILED**: no attested plan will be uploaded for this",
                "run and NO run_* output was written, so every job runs and the reconcile",
                "step will report 'no attested plan'. That is a GAP IN THE EVIDENCE, not a",
                "clean result._",
                "```",
            )
            tee_head(plan_write_err, NARROW_HEAD_BYTES)
            emit("```", "")
        else:
            emit("**pre-existing skip conditions recorded in the plan**", "", "```json")
            proc = bounded(
                ["node", "-e", CONDITIONS_JS, str(plan_json)],
                stdout=subprocess.PIPE,
                text=True,
            )
            _dual_write(proc.stdout)
            emit("```", "")
            # AFTER the plan is written and BEFORE anything is emitted.
            apply_greenlight()
            emit_outputs()
    else:
        emit("_no baseline plan was produced, so no run_* output was written: full round._", "")

    # Always green. This script decides what runs; it must never be what fails.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
