#!/usr/bin/env python3
"""Port of `.ci/scripts/security/check-workflow-gates.sh` (`check:ci-workflow-gates`).

Six structural invariants over GitHub Actions workflow YAML that only a real parser can see. The twin is 1108 lines, of which only 125 are bash: 788 lines already live inside six `python3 - ... <<'PYEOF'` heredocs. So this is not a translation of 1108 lines of shell, it is a translation of the 125-line orchestrator plus a transcription of six Python programs that were already
Python. Each `sys.exit(N)` below became `return N`; nothing else about the six programs' logic moved.

LIVE CALLERS OF THE TWIN, none repointed by this port:
  * `package.json:44` -- `"check:ci-workflow-gates": ".ci/scripts/security/check-workflow-gates.sh"`
  * `scripts/ci-runner/manifest.ts:2966-2975` -- gate entry, `leaves:
    ['.ci/scripts/security/check-workflow-gates.sh']`, bound to
    `.github/workflows/ci-quality.yml`, job `quality-code`, step
    `Workflow structural gates`.
  * `.ci/rediacc_ci/tests/gates/test_gate_workflow_contracts.py:44`,
    `test_gate_slim_timeout.py:29` and `test_gate_watchdog_monitor_ordering.py:35`
    each drive the real twin against fixture trees through `WORKFLOWS_DIR`.

THE SIX CHECKS, and what each one reads:

  1. job-level `if:` referencing `needs.*.result` must carry an
     `always()`/`!cancelled()`/`failure()`/`success()` override. Reads
     `$WORKFLOWS_DIR`, RECURSIVELY.
  2. the reusable-workflow secret/input contract, four arms: (a) a callee may
     not read an undeclared secret, (a2) a callee may not declare a secret it
     never reads, (a3) every `DECLARED_UNUSED_OK` exemption must be pinned alive
     by `.github/external-callers.yml` and vice versa, (b)/(c) caller <-> callee.
     Reads `$WORKFLOWS_DIR` FLAT, plus the registry.
  3. every `ubuntu-slim` job declares `timeout-minutes <= $SLIM_TIMEOUT_MAX`.
     Reads `$WORKFLOWS_DIR` FLAT.
  4. `.github/external-callers.yml` against the callees' real signatures, the
     callers' real files when a submodule is checked out, and completeness over
     `private/*/.github/workflows`.
  5. every Bitwarden-fetching job with a sparse checkout must include
     `.ci/config` in the cone. Reads `$ROOT_DIR`, NOT `$WORKFLOWS_DIR`.
  6. nothing optional may precede the watchdog's monitor step. Reads
     `$ROOT_DIR/.github/workflows/watchdog-monitor.yml`, NOT `$WORKFLOWS_DIR`.

PORT NOTES -- unless an item says otherwise it is REPRODUCED, not repaired. Fixing one only HERE would make the differential lie, so the two ways an item can end are: reproduced in both sides, or fixed in BOTH SIDES IN LOCKSTEP in one change that also flips its differential test and re-records the shadow ledger. CHECK 6's checkout exemption took the second route on 2026-09-10;
everything else below is still the first.

CHECK 1 WALKS, CHECKS 2 AND 3 DO NOT. `check-workflow-gates.sh:164` (`os.walk(workflows_dir)`) descends into subdirectories; `:236` (`os.listdir`) and `:527` (`os.listdir`) are flat. A workflow YAML in a subdirectory of `$WORKFLOWS_DIR` is therefore audited for the `always()` rule and NOT for the secret contract or the slim timeout. Measured: `.github/workflows` has no subdirectory
today, so the blast radius on the real tree is zero and the divergence is only reachable through a fixture. `test_check1_walks_and_check3_does_not` pins it.

CHECKS 5 AND 6 IGNORE `$WORKFLOWS_DIR` ENTIRELY. `check-workflow-gates.sh:886` and `:1012` pass `"$ROOT_DIR"`, so a gate test pointing `WORKFLOWS_DIR` at a fixture tree still runs CHECK 5 and CHECK 6 against the REAL repository. That is why `test_gate_slim_timeout.py` and friends can only assert on the checks they target: the other two run for real underneath them every time.
Reproduced here by resolving the root the same way the twin does and never letting `workflows_dir` reach `check5`/`check6`.

CHECK 5 GLOBS `*.yml` ONLY. `:894-895` uses `.glob("*.yml")` for both `.github/workflows` and `.ci/breakpoint/workflow`; a `.yaml` workflow is invisible to CHECK 5 while CHECKS 1/2/3 all accept both extensions. Measured: 0 `.yaml` files under either directory today.

CHECK 6's CHECKOUT EXEMPTION WAS FIXED IN BOTH SIDES ON 2026-09-10, in lockstep. It used to test the step's *NAME*, not its `uses:`: `names` was built as `step.get("name") or str(step.get("uses",""))` and the exemption then asked `"actions/checkout" in name`, so a checkout step that HAS a `name:` lost the exemption unless the name itself contained `actions/checkout`. Measured on
the real tree: 139 of the 144 `actions/checkout` steps under `.github/workflows` are unnamed (so they were exempt by the `uses:` fallback) and 5 are named (so they were not). `watchdog-monitor.yml`'s own checkout is unnamed, which is why the gate was green while one ordinary `name: Checkout` edit would have turned it red on the single workflow it guards. It now reads `uses:` and
nothing else, and the same code path grew the type guards it never had: a non-str `name:` used to raise `TypeError` and an empty or malformed watchdog YAML used to raise `AttributeError`, both surfacing as a traceback under bash's "move the step after the monitor" message. Both now report cleanly and still exit 1. `test_check6_a_named_checkout_is_exempt`,
`test_check6_a_non_string_step_name` and `test_check6_a_malformed_workflow_reports_cleanly` pin all three on both sides.

`SLIM_TIMEOUT_MAX` IS `int()`-ED WITH NO GUARD. `:520` (`int(sys.argv[2])`) raises `ValueError` on a non-numeric override, the heredoc dies with a traceback and exit 1, and bash then prints "ubuntu-slim timeout violations (see above)" -- a message about violations for what is a configuration error. Reproduced: the port lets the same `ValueError` escape `check3`, prints its own
traceback and returns 1. The traceback TEXT necessarily differs (different file, different line); the exit code and the bash-level message do not.

`${VAR:-default}` TREATS EMPTY AS UNSET. `SLIM_TIMEOUT_MAX=` exported empty is
14, not "". `_env` below is that operator. `CI` is compared with `==` rather
than through `:-` semantics (`:60`), so `CI=` empty means colour ON.

THE COLOUR CODES ARE EMITTED, not stripped. `:63` sets `RED='\\033[0;31m'` and
`log_error` uses `echo -e`, so the real bytes are ESC-bracket sequences whenever
`CI != "true"`. A port that printed plain text would differ from the twin on
every single line outside CI.

THE PYYAML BOOTSTRAP IS A REAL SUBPROCESS CHAIN. `:130` runs `python3 -c "import yaml" || pip install --user --quiet pyyaml || pip3 install
--user --quiet pyyaml || { log_error; exit 2; }`. Reproduced as a real
`pip`/`pip3` attempt rather than a bare `ImportError`, because "the gate exits 2 saying pyyaml is missing" and "the gate dies with a traceback" are different failures to the operator reading CI.

ONE NAMED DIVERGENCE THIS PORT ADDS: `paths.repo_root()` honours
`$REDIACC_CI_ROOT`, and the twin's `ROOT_DIR` (derived from `${BASH_SOURCE[0]}`,
`:57-58`) does not. Set that variable and the two sides read different trees. It is the package-wide convention (`paths.py`'s own header argues for exactly one such name), and the differential harness never sets it.

Exit: 0 all six clean, 1 any offender, 2 setup error (pyyaml).
"""

from __future__ import annotations

import contextlib
import glob
import importlib
import os
import pathlib
import re
import site
import subprocess
import sys
import traceback
import typing

from rediacc_ci import paths

if typing.TYPE_CHECKING:  # pragma: no cover - typing only
    from types import ModuleType

# --------------------------------------------------------------------------- The bash preamble (check-workflow-gates.sh:55-135) ---------------------------------------------------------------------------


def _env(name: str, default: str) -> str:
    """`${name:-default}`: an exported-but-empty value is UNSET, not "".

    `os.environ.get(name, default)` would return "" for `FOO=`, which is the
    opposite answer, and every one of the six overrides below is a path or a boolean where "" means something different from the default.
    """
    value = os.environ.get(name)
    return value or default


class _Palette:
    """`RED`/`GREEN`/`YELLOW`/`NC` and the four `log_*` helpers (`:60-69`)."""

    def __init__(self, ci: str) -> None:
        # `[[ "${CI:-}" == "true" ]]`. Note this is an equality test, not a
        # truthiness one: CI=1 keeps the colours on.
        if ci == "true":
            self.red = self.green = self.yellow = self.nc = ""
        else:
            self.red = "\033[0;31m"
            self.green = "\033[0;32m"
            self.yellow = "\033[1;33m"
            self.nc = "\033[0m"

    def error(self, msg: str) -> None:
        print("%serror: %s%s" % (self.red, msg, self.nc), file=sys.stderr, flush=True)

    def success(self, msg: str) -> None:
        print("%ssuccess: %s%s" % (self.green, msg, self.nc), flush=True)

    def warn(self, msg: str) -> None:
        print("%swarn: %s%s" % (self.yellow, msg, self.nc), flush=True)

    def info(self, msg: str) -> None:
        # `log_info` is a plain `echo`, with no colour and no `-e`.
        print("info: %s" % msg, flush=True)


def _ensure_yaml(palette: _Palette) -> ModuleType | None:
    """`:130-133`, the pyyaml bootstrap, as the same three-step `||` chain.

    Returns the module, or None after having printed the twin's exit-2 error.
    """
    try:
        import yaml  # noqa: PLC0415 - deliberately late, this IS the bootstrap
    except ImportError:
        pass
    else:
        return yaml

    for installer in ("pip", "pip3"):
        try:
            proc = subprocess.run(
                [installer, "install", "--user", "--quiet", "pyyaml"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        # A `--user` install lands in a site directory this interpreter resolved before the install ran. The twin gets this for free by starting a new `python3` for every check; in-process the caches have to be dropped by hand or the import below finds nothing that was just written.
        with contextlib.suppress(AttributeError, OSError):  # defensive
            site.main()
        importlib.invalidate_caches()
        try:
            import yaml  # noqa: PLC0415
        except ImportError:
            continue
        return yaml

    palette.error("Unable to install pyyaml (needed for workflow parsing)")
    return None


# --------------------------------------------------------------------------- CHECK 1 -- job-level if: needs always() (check-workflow-gates.sh:140-200) ---------------------------------------------------------------------------
#
# --- carried verbatim from check-workflow-gates.sh, lines 6-20 --------------------- CHECK 1 -- job-level if: needs always() Audit JOB-LEVEL if: blocks that reference needs.*.result. Prevents the transitive-skip propagation bug (finding J): a downstream job whose if:
#   references needs.X.result == 'success' without an always() / !cancelled() /
# !failure() prefix will silently skip whenever any upstream in X's transitive needs: chain skipped, even if X itself concluded as success.
#
# Only job-level if: blocks are audited. Step-level if: runs inside an already-running job, so the transitive-skip concern doesn't apply.
#
# Tolerated overrides (any one is enough to force evaluation): always() -- canonical GHA idiom
#     !cancelled()  -- common variant; matches success+failure+skipped
#     failure()     -- runs only on failure; implicitly overrides
# success() -- evaluates unconditionally (implicit default, but listing it here keeps us permissive)

OVERRIDE_RE = re.compile(r"(always\(\)|!\s*cancelled\(\)|failure\(\)|success\(\))")
NEEDS_RESULT_RE = re.compile(r"needs\.[A-Za-z0-9_-]+\.result")


def check1(yaml: ModuleType, workflows_dir: str) -> int:
    offenders: list[tuple[str, str, str]] = []
    parsed = 0

    def check_if_expr(path: str, job_name: str, expr: object) -> None:
        if not isinstance(expr, str):
            return
        if not NEEDS_RESULT_RE.search(expr):
            return
        if OVERRIDE_RE.search(expr):
            return
        offenders.append((path, job_name, expr.strip()[:160]))

    # RECURSIVE, unlike checks 2 and 3. See the module docstring.
    for root, _dirs, files in os.walk(workflows_dir):
        for fname in sorted(files):
            if not fname.endswith((".yml", ".yaml")):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path) as f:
                    doc = yaml.safe_load(f)
            except yaml.YAMLError as e:
                print("%s: YAML parse error: %s" % (path, e), file=sys.stderr, flush=True)
                offenders.append((path, "<yaml-error>", str(e)))
                continue
            parsed += 1
            if not isinstance(doc, dict):
                continue
            jobs = doc.get("jobs") or {}
            if not isinstance(jobs, dict):
                continue
            for job_name, job_spec in jobs.items():
                if not isinstance(job_spec, dict):
                    continue
                if "if" in job_spec:
                    check_if_expr(path, job_name, job_spec["if"])

    if parsed == 0:
        print(
            "%s: no workflow YAML parsed -- this check is blind" % workflows_dir,
            file=sys.stderr,
            flush=True,
        )
        return 3

    if offenders:
        for path, job_name, expr in offenders:
            rel = os.path.relpath(path, os.path.dirname(os.path.dirname(workflows_dir)))
            print(
                "%s: job '%s' has if: without always()/!cancelled()" % (rel, job_name),
                file=sys.stderr,
                flush=True,
            )
            print("    expr: %s" % expr, file=sys.stderr, flush=True)
        return 1

    return 0


# --------------------------------------------------------------------------- CHECK 2 -- reusable-workflow call contract (check-workflow-gates.sh:217-484) ---------------------------------------------------------------------------
#
# --- carried verbatim from check-workflow-gates.sh, lines 22-34 --------------------- CHECK 2 -- reusable-workflow call contract Inside a reusable workflow, `secrets.FOO` for a secret that is NOT declared under on.workflow_call.secrets evaluates to the EMPTY STRING. No warning, no failure -- the deploy just ships a blank credential. That is exactly how
#   OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA} came to be read by cd-deploy-account.yml
#   while being declared by nobody, so every deployed account Worker ran with
#   OBS_OTLP_CREDENTIALS="" and shipped no telemetry. Nothing caught it
# because an empty secret is indistinguishable from a working one at the YAML layer. So assert the contract in both directions: a) a reusable workflow may not read a secret it does not declare b) a caller must pass every required secret/input the callee declares c) a caller may not pass a secret/input the callee never declares (dead wiring: it looks like the value flows, and it
# does not)

# `secrets.X`, but not when it is part of a path or filename -- otherwise "set-account-worker-secrets.sh" reads as a reference to a secret named `sh`.
USE_RE = re.compile(r"(?<![\w./-])secrets\.([A-Za-z_][A-Za-z0-9_]*)")

# Always available inside a workflow; never declared under workflow_call.
IMPLICIT = {"GITHUB_TOKEN"}

# A LIST, converted to a set below, deliberately: `{...}` with its last member
# deleted is `{}`, which is an empty DICT, and the set arithmetic in arm (a3)
# then dies with a TypeError while `in` and `sorted()` degrade to silently matching nothing. Draining this list to empty is the declared endgame (W8 P1b), so the empty form has to be the safe one. Carried verbatim from the twin (`:302-319`), INCLUDING its emptiness: the last entry was drained 2026-09-08.
_DECLARED_UNUSED_OK: list[tuple[str, str]] = [
    # DRAINED 2026-09-08, and the premise this entry rested on was FALSE. It said the consumer "fetches this from Bitwarden now, so the passed value IS
    # unused". Measured: the fetch step is guarded on `github.repository ==
    # 'rediacc/console'`, and in a REUSABLE workflow `github.repository` is the CALLER's repo -- so for rediacc/account and rediacc/renet that step never ran and the token was EMPTY. The passed secret was unread not because their half of the migration had landed but because it had never been written, and deleting the declaration would have made a live outage permanent.
    # `claude-review-reusable.yml` now reads `env.BWS_... || secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`, which restores the read for both callers, and that is what makes this exemption genuinely removable.
]


def strip_comment_lines(text: str) -> str:
    """`:256-258`. COMMENTS ARE NOT USES.

    `texts` feeds `USE_RE`, which decides whether a workflow "reads" a secret, and a raw read counted `# ... secrets.X ...` as a use. So a comment RECORDING that some `secrets.X` was removed made the callee look like it still consumed the name, and the contract check then demanded a declaration for something nothing reads.

    Only a WHOLE-LINE comment is blanked -- `lstrip().startswith("#")`. A trailing `foo: bar # secrets.X` still reads as a use, on both sides.
    """
    return "\n".join("" if ln.lstrip().startswith("#") else ln for ln in text.split("\n"))


def workflow_call(doc: object) -> dict:
    """`on:` is parsed as the boolean True by YAML 1.1, so look under both keys."""
    if not isinstance(doc, dict):
        return {}
    on = doc.get("on", doc.get(True)) or {}
    if not isinstance(on, dict):
        return {}
    wc = on.get("workflow_call") or {}
    return wc if isinstance(wc, dict) else {}


def check2(yaml: ModuleType, workflows_dir: str, real_tree: bool, registry_file: str) -> int:
    docs: dict[str, object] = {}
    texts: dict[str, str] = {}
    # FLAT, unlike check 1.
    for fname in sorted(os.listdir(workflows_dir)):
        if not fname.endswith((".yml", ".yaml")):
            continue
        path = os.path.join(workflows_dir, fname)
        try:
            with open(path) as f:
                text = f.read()
            docs[fname] = yaml.safe_load(text)
            texts[fname] = strip_comment_lines(text)
        except (yaml.YAMLError, OSError) as e:
            print("%s: unreadable (%s)" % (fname, e), file=sys.stderr, flush=True)
            return 1

    if not docs:
        print(
            "%s: no workflow YAML parsed -- this check is blind" % workflows_dir,
            file=sys.stderr,
            flush=True,
        )
        return 3

    offenders: list[str] = []

    # (a) a reusable workflow may not read a secret it does not declare
    for fname, doc in docs.items():
        wc = workflow_call(doc)
        if not wc:
            continue
        declared = set((wc.get("secrets") or {}).keys())
        used = set(USE_RE.findall(texts[fname])) - IMPLICIT
        offenders.extend(
            "%s: reads secrets.%s but does not declare it under "
            'on.workflow_call.secrets -- it will silently evaluate to ""' % (fname, name)
            for name in sorted(used - declared)
        )

    # --- carried verbatim from check-workflow-gates.sh, lines 294-306 --------------------- (a2) a reusable workflow may not DECLARE a secret nothing in it reads.
    #
    # THE ARM THAT WAS MISSING, and its absence is measurable: 57 such declarations had accumulated by 2026-09-06, left behind when consumers moved to Bitwarden, and were removed in one sweep. (a) catches a read with no declaration; nothing caught a declaration with no read, so dead scaffolding grew quietly on the one surface where a stale secret name is most misleading -- a caller
    # reads the declaration and passes a value that goes nowhere.
    # A LIST, converted below, deliberately: `{...}` with its last member deleted is
    # `{}`, which is an empty DICT, and the set arithmetic in arm (a3) then dies with
    # a TypeError while `in` and `sorted()` above degrade to silently matching nothing. Draining this list to empty is the declared endgame (W8 P1b), so the empty form has to be the safe one. Found by planting exactly that drain.
    declared_unused_ok = set(_DECLARED_UNUSED_OK)
    if len(declared_unused_ok) != len(_DECLARED_UNUSED_OK):
        print("DECLARED_UNUSED_OK contains a duplicate entry", file=sys.stderr, flush=True)
        return 1
    for fname, doc in docs.items():
        wc = workflow_call(doc)
        if not wc:
            continue
        declared = set((wc.get("secrets") or {}).keys())
        used = set(USE_RE.findall(texts[fname])) - IMPLICIT
        for name in sorted(declared - used):
            if (fname, name) in declared_unused_ok:
                continue
            offenders.append(
                "%s: declares secret %s under workflow_call but never reads it -- "
                "a caller passing it sends a value nowhere; delete the declaration" % (fname, name)
            )

    # --- carried verbatim from check-workflow-gates.sh, lines 337-347 --------------------- An exemption naming a declaration that is gone, or one that IS read, excuses nothing and would sit forever looking like coverage.
    #
    # SCOPED TO THE REAL TREE, and that scoping is not a nicety. The exemptions name files in .github/workflows; a CHECK 1/CHECK 3 fixture tree contains two or three synthetic YAMLs and none of them. Sweeping there reported every exemption as dangling, which made this script exit 1 on EVERY fixture tree and turned two unrelated gate tests red for a file their fixtures were never
    # meant to have -- test-slim-timeout.sh and test-workflow-contracts.sh, nightly run 34014201256. A liveness probe that cannot see the thing it probes for must stay silent, not condemn it.
    if real_tree:
        for fname, name in sorted(declared_unused_ok):
            doc = docs.get(fname)
            if doc is None:
                offenders.append("DECLARED_UNUSED_OK names %s, which does not exist" % fname)
                continue
            declared = set((workflow_call(doc).get("secrets") or {}).keys())
            used = set(USE_RE.findall(texts[fname])) - IMPLICIT
            if name not in declared:
                offenders.append(
                    "DECLARED_UNUSED_OK: %s no longer declares %s; drop the exemption"
                    % (fname, name)
                )
            elif name in used:
                offenders.append(
                    "DECLARED_UNUSED_OK: %s now READS %s; drop the exemption" % (fname, name)
                )

    # --- carried verbatim from check-workflow-gates.sh, lines 361-374 --------------------- (a3) every DECLARED_UNUSED_OK exemption must be PINNED ALIVE by a real entry in .github/external-callers.yml, and every pair that registry pins alive must be named by the exemption list. Set equality, both directions.
    #
    # WHY: the only legitimate reason to keep a declaration nothing reads is that a caller in ANOTHER repository still passes it, so deleting the declaration breaks their next run rather than this PR. Until now that justification lived in a COMMENT above the set. A comment cannot go stale loudly: retire the external caller and the exemption stays, looking like coverage, protecting
    # a declaration nothing on earth passes any more.
    #
    # Scoped exactly like the liveness sweep above, and for the same reason: a CHECK 1/2/3 fixture tree has no registry, and an arm that cannot see the thing it probes for must stay silent rather than condemn it.
    if real_tree and registry_file:
        reg_offenders: list[str] = []
        registry: object = None
        try:
            with open(registry_file) as fh:
                registry = yaml.safe_load(fh.read())
        except (yaml.YAMLError, OSError) as exc:
            reg_offenders.append(
                "arm (a3): %s unreadable (%s) -- the exemption list "
                "cannot be justified against a registry that will not parse" % (registry_file, exc)
            )
            registry = None
        reg_entries = (registry or {}).get("callers") or []
        if not reg_offenders and (not isinstance(reg_entries, list) or not reg_entries):
            # Zero inputs is a failure, never a pass.
            reg_offenders.append(
                "arm (a3): %s declares no callers -- "
                "nothing can pin an exemption alive, so this arm is blind"
                % os.path.basename(registry_file)
            )
            reg_entries = []

        pinned_unused: set[tuple[str, str]] = set()
        for entry in reg_entries:
            if not isinstance(entry, dict) or "calls" not in entry:
                continue  # CHECK 4 owns the shape of a registry entry
            callee = os.path.basename(entry["calls"])
            doc = docs.get(callee)
            if doc is None:
                continue  # CHECK 4 reports a registered call to a callee that is gone
            declared = set((workflow_call(doc).get("secrets") or {}).keys())
            used = set(USE_RE.findall(texts[callee])) - IMPLICIT
            passed = entry.get("passes_secrets")
            names = declared if passed == "inherit" else set(passed or [])
            pinned_unused |= {(callee, n) for n in (names & declared) - used}

        for fname, name in sorted(declared_unused_ok - pinned_unused):
            reg_offenders.append(
                "DECLARED_UNUSED_OK exempts %s/%s, but no entry in "
                "%s pins it alive -- nothing outside this "
                "repo passes it, so delete the declaration and the exemption, not the check"
                % (fname, name, os.path.basename(registry_file))
            )
        for fname, name in sorted(pinned_unused - declared_unused_ok):
            reg_offenders.append(
                "%s pins %s/%s alive (an external "
                "caller passes a secret %s declares and never reads), but "
                "DECLARED_UNUSED_OK does not name it -- reconcile the two, or delete the "
                "declaration and the registry entry together"
                % (os.path.basename(registry_file), fname, name, fname)
            )

        offenders.extend(reg_offenders)
        if not reg_offenders:
            print(
                "info: arm (a3): %d declared-unused exemption(s) == "
                "%d pinned alive by %d external-caller "
                "entr%s"
                % (
                    len(declared_unused_ok),
                    len(pinned_unused),
                    len(reg_entries),
                    "y" if len(reg_entries) == 1 else "ies",
                ),
                flush=True,
            )

    # (b)/(c) caller <-> callee contract
    for fname, doc in docs.items():
        # The isinstance guard was an UNRECORDED DIVERGENCE until 2026-09-10: the twin
        # had only `(doc or {})`, which covers an empty file and not a workflow whose
        # YAML parses to a scalar or a list, so the twin died with `AttributeError: 'str' object has no attribute 'get'` where the port passed. Found while testing CHECK 6's guard; the twin now carries the same guard (check-workflow-gates.sh, CHECK 2's (b)/(c) loop) and `test_check2_a_workflow_that_is_not_a_mapping` pins the pair.
        jobs = (doc or {}).get("jobs") or {} if isinstance(doc, dict) else {}
        if not isinstance(jobs, dict):
            continue
        for jid, job in jobs.items():
            if not isinstance(job, dict):
                continue
            uses = job.get("uses", "")
            if not isinstance(uses, str) or not uses.startswith("./.github/workflows/"):
                continue
            callee = os.path.basename(uses)
            if callee not in docs:
                offenders.append("%s: job '%s' calls %s, which does not exist" % (fname, jid, uses))
                continue
            wc = workflow_call(docs[callee])
            dsec = wc.get("secrets") or {}
            dinp = wc.get("inputs") or {}

            passed = job.get("secrets")
            if passed != "inherit":
                got = set((passed or {}).keys())
                required = {k for k, v in dsec.items() if isinstance(v, dict) and v.get("required")}
                offenders.extend(
                    "%s: job '%s' -> %s: does not pass required secret %s"
                    % (fname, jid, callee, name)
                    for name in sorted(required - got)
                )
                offenders.extend(
                    "%s: job '%s' -> %s: passes secret %s, which %s "
                    "never declares -- the value goes nowhere" % (fname, jid, callee, name, callee)
                    for name in sorted(got - set(dsec))
                )

            got = set((job.get("with") or {}).keys())
            required = {k for k, v in dinp.items() if isinstance(v, dict) and v.get("required")}
            offenders.extend(
                "%s: job '%s' -> %s: does not pass required input %s" % (fname, jid, callee, name)
                for name in sorted(required - got)
            )
            offenders.extend(
                "%s: job '%s' -> %s: passes input %s, which %s "
                "never declares -- the value goes nowhere" % (fname, jid, callee, name, callee)
                for name in sorted(got - set(dinp))
            )

    if offenders:
        for line in offenders:
            print(line, file=sys.stderr, flush=True)
        return 1

    return 0


# --------------------------------------------------------------------------- CHECK 3 -- ubuntu-slim timeouts (check-workflow-gates.sh:501-592) ---------------------------------------------------------------------------
#
# --- carried verbatim from check-workflow-gates.sh, lines 36-42 --------------------- CHECK 3 -- ubuntu-slim jobs declare a timeout under the platform cap ubuntu-slim has a HARD 15-minute job cap. Exceeding it marks the job CANCELLED with no failed step, which reads as neither pass nor fail: it poisons CI Complete and leaves the watchdog nothing to classify. quality-security hit
# this twice in three runs. Requiring an explicit
#   timeout-minutes <= 14 turns that silent kill into an ordinary timeout
# failure naming the step that hung.
#
# --- carried verbatim from check-workflow-gates.sh, lines 502-515 --------------------- ubuntu-slim is a 1-vCPU runner with a HARD 15-minute job cap enforced by the platform, not by us. When a job hits it the run does not fail -- the job is marked CANCELLED with no failed step, which poisons CI Complete and gives the watchdog nothing to classify. quality-security hit this twice in
# three runs during the 0722-1 wave before it was moved to ubuntu-latest.
#
# So every slim job must declare its own timeout BELOW the cap. Then a hang fails as a timeout, in the job that owns it, with a message naming the step. 12 rather than 15 leaves room for the runner's own setup/teardown, which is outside the steps but inside the cap.
#
# A job that legitimately needs longer does not get a bigger number here: it gets ubuntu-latest. That is the whole point -- the number is not a dial, it is an assertion that this job fits on this runner.

SLIM = "ubuntu-slim"


def check3(yaml: ModuleType, workflows_dir: str, limit_raw: str, require_coverage: bool) -> int:
    # `int(sys.argv[2])` with no guard (`:520`). A non-numeric override raises here exactly as it does in the twin; `main` turns the traceback into exit 1.
    limit = int(limit_raw)
    offenders: list[str] = []
    checked = 0

    names = sorted(f for f in os.listdir(workflows_dir) if f.endswith((".yml", ".yaml")))
    if not names:
        print("no workflow files under %s" % workflows_dir, file=sys.stderr, flush=True)
        return 3

    for fname in names:
        with open(os.path.join(workflows_dir, fname)) as fh:
            try:
                doc = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                print("%s: unparseable YAML: %s" % (fname, exc), file=sys.stderr, flush=True)
                return 3
        if not isinstance(doc, dict):
            continue

        for jid, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            runs_on = job.get("runs-on")
            # Matrix-driven runners (`runs-on: ${{ matrix.runner }}`) are not
            # resolvable here; a literal slim label is.
            labels = runs_on if isinstance(runs_on, list) else [runs_on]
            if SLIM not in [x for x in labels if isinstance(x, str)]:
                continue

            checked += 1
            # --- carried verbatim from check-workflow-gates.sh, lines 555-561 --------------------- Named `declared`, not `timeout`: check-commands.sh scans this file as bash and has no heredoc scoping, so a Python line reading
            # `timeout = ...` is indistinguishable from the bash command invocation
            # `timeout = ...` actually is. That gate is RIGHT about bash and must not
            # be taught to skip heredoc bodies -- a `ssh host <<'EOF' ... timeout 5` body is exactly the remote-minimal-environment case it exists to catch. Avoiding the collision is the fix; widening the gate is not.
            declared = job.get("timeout-minutes")
            if declared is None:
                offenders.append(
                    "%s: job '%s' runs on %s without timeout-minutes -- "
                    "a hang rides to the platform's 15-minute cap and reports as "
                    "cancelled, not failed" % (fname, jid, SLIM)
                )
            elif not isinstance(declared, int):
                offenders.append(
                    "%s: job '%s' has a non-literal timeout-minutes "
                    "(%r); this gate cannot verify it stays under the cap" % (fname, jid, declared)
                )
            elif declared > limit:
                offenders.append(
                    "%s: job '%s' declares timeout-minutes: %s on "
                    "%s, above the %s-minute ceiling -- move it to "
                    "ubuntu-latest instead of raising the number"
                    % (fname, jid, declared, SLIM, limit)
                )

    if not checked and require_coverage:
        print(
            "no %s jobs found under %s -- this check is blind" % (SLIM, workflows_dir),
            file=sys.stderr,
            flush=True,
        )
        return 3

    if offenders:
        for line in offenders:
            print(line, file=sys.stderr, flush=True)
        return 1

    return 0


# --------------------------------------------------------------------------- CHECK 4 -- external-caller contracts (check-workflow-gates.sh:626-847) ---------------------------------------------------------------------------
#
# --- carried verbatim from check-workflow-gates.sh, lines 44-51 --------------------- CHECK 4 -- external-caller contracts (.github/external-callers.yml) CHECK 2 scans .github/workflows only, so it cannot see callers in OTHER repositories -- and those are the only callers that can actually break, because a same-repo caller moves with its callee in one commit while a cross-repo one
# resolves `@main` at run time. `.github/external-callers.yml`
#   declares them; this runs CHECK 2's contract against each declaration,
# re-checks the declaration against the caller's real file when the submodule is checked out, and fails on any external caller that is not registered.
#
# --- carried verbatim from check-workflow-gates.sh, lines 607-620 --------------------- CHECK 2 above scans WORKFLOWS_DIR only, so it is structurally blind to callers that live in OTHER repositories -- which are the only callers that can suffer the breakage it exists to prevent. A same-repo caller moves with its callee in one commit; a cross-repo caller resolves `@main` at run
# time, so a callee edit merged here breaks the other repo's next run, an hour later, in a log nobody on this PR is reading.
#
# .github/external-callers.yml declares them. CHECK 4 runs CHECK 2's three-way contract against each declaration, verifies the declaration still matches the caller's real file when the submodule is checked out, and refuses to let an undeclared external caller exist. EXTERNAL_CALLERS_ROOT / EXTERNAL_CALLERS_FILE are resolved near the top of the file, because CHECK 2's arm (a3) needs
# the same registry and must resolve it the same way rather than growing a second copy of the rule.

REQUIRED_FIELDS = ("caller", "repo", "pinned_at", "calls", "passes_inputs", "passes_secrets")
CONSOLE_PREFIX = "rediacc/console/"


class _BlindError(Exception):
    """`die_blind` (`:637-639`), which is a `sys.exit(3)` in the twin."""


def check4(yaml: ModuleType, workflows_dir: str, registry_file: str, scan_root: str) -> int:
    try:
        return _check4(yaml, workflows_dir, registry_file, scan_root)
    except _BlindError as blind:
        print("%s -- this check is blind" % blind.args[0], file=sys.stderr, flush=True)
        return 3


def _check4(yaml: ModuleType, workflows_dir: str, registry_file: str, scan_root: str) -> int:
    offenders: list[str] = []

    def load(path: str) -> object:
        with open(path) as fh:
            return yaml.safe_load(fh.read())

    if not os.path.isfile(registry_file):
        raise _BlindError("%s: no external-caller registry" % registry_file)

    try:
        registry = load(registry_file)
    except (yaml.YAMLError, OSError) as exc:
        print("%s: unreadable (%s)" % (registry_file, exc), file=sys.stderr, flush=True)
        return 1

    entries = (registry or {}).get("callers") or []
    if not isinstance(entries, list) or not entries:
        raise _BlindError("%s: declares no callers" % registry_file)

    # --- (a) the declared contract must hold against the callee's real signature
    registered: set[tuple[str, str]] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            offenders.append("%s: caller #%d is not a mapping" % (registry_file, i))
            continue
        missing = [f for f in REQUIRED_FIELDS if f not in entry]
        if missing:
            offenders.append(
                "%s: caller #%d is missing %s" % (registry_file, i, ", ".join(missing))
            )
            continue

        caller = entry["caller"]
        calls = entry["calls"]
        registered.add((caller, calls))

        callee_path = os.path.join(workflows_dir, os.path.basename(calls))
        if not os.path.isfile(callee_path):
            offenders.append(
                "%s -> %s: the callee does not exist in this repo. "
                "An external caller pinned at %s will fail on its "
                "next run; restore the workflow or update the caller first."
                % (caller, calls, entry["pinned_at"])
            )
            continue

        wc = workflow_call(load(callee_path))
        if not wc:
            offenders.append(
                "%s -> %s: the callee declares no on.workflow_call block, "
                "so it cannot be called from another repository at all" % (caller, calls)
            )
            continue

        dinp = wc.get("inputs") or {}
        dsec = wc.get("secrets") or {}
        got_inp = set(entry["passes_inputs"] or [])
        got_sec_raw = entry["passes_secrets"]
        inherits = got_sec_raw == "inherit"
        got_sec = set() if inherits else set(got_sec_raw or [])

        offenders.extend(
            "%s -> %s: does not pass required input %s" % (caller, calls, name)
            for name in sorted(
                {k for k, v in dinp.items() if isinstance(v, dict) and v.get("required")} - got_inp
            )
        )
        offenders.extend(
            "%s -> %s: passes input %s, which %s "
            "never declares -- the value goes nowhere"
            % (caller, calls, name, os.path.basename(calls))
            for name in sorted(got_inp - set(dinp))
        )
        if not inherits:
            offenders.extend(
                "%s -> %s: does not pass required secret %s. Making it "
                '`required: false` in the callee is not a fix -- it ships "".'
                % (caller, calls, name)
                for name in sorted(
                    {k for k, v in dsec.items() if isinstance(v, dict) and v.get("required")}
                    - got_sec
                )
            )
            offenders.extend(
                "%s -> %s: passes secret %s, which "
                "%s never declares -- the value goes nowhere"
                % (caller, calls, name, os.path.basename(calls))
                for name in sorted(got_sec - set(dsec))
            )

    # --- (b) the declaration must match the caller's real file, when we have it
    verified = 0
    for entry in entries:
        if not isinstance(entry, dict) or any(f not in entry for f in REQUIRED_FIELDS):
            continue
        caller = entry["caller"]
        abs_caller = os.path.join(scan_root, caller)
        # The submodule holding this caller may simply not be checked out. That is not a finding; a checked-out submodule that has LOST the file is.
        repo_tree = os.path.join(scan_root, caller.split("/.github/")[0], ".github", "workflows")
        if not os.path.isfile(abs_caller):
            if os.path.isdir(repo_tree):
                offenders.append(
                    "%s: registered here but absent from a checked-out tree -- "
                    "delete the entry or restore the file" % caller
                )
            continue

        try:
            doc = load(abs_caller)
        except (yaml.YAMLError, OSError) as exc:
            offenders.append("%s: unreadable (%s)" % (caller, exc))
            continue

        want_uses_prefix = CONSOLE_PREFIX + entry["calls"] + "@"
        found = False
        for jid, job in ((doc or {}).get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            uses = job.get("uses")
            if not isinstance(uses, str) or not uses.startswith(want_uses_prefix):
                continue
            found = True
            ref = uses.split("@", 1)[1]
            if ref != entry["pinned_at"]:
                offenders.append(
                    "%s: job '%s' pins %s@%s, registry says "
                    "@%s" % (caller, jid, entry["calls"], ref, entry["pinned_at"])
                )
            real_inp = set((job.get("with") or {}).keys())
            passed = job.get("secrets")
            real_sec: object = "inherit" if passed == "inherit" else set((passed or {}).keys())
            if real_inp != set(entry["passes_inputs"] or []):
                offenders.append(
                    "%s: job '%s' passes inputs %s, registry "
                    "declares %s"
                    % (caller, jid, sorted(real_inp), sorted(entry["passes_inputs"] or []))
                )
            declared_sec = entry["passes_secrets"]
            norm_declared: object = (
                "inherit" if declared_sec == "inherit" else set(declared_sec or [])
            )
            if real_sec != norm_declared:
                offenders.append(
                    "%s: job '%s' passes secrets "
                    "%s, registry "
                    "declares %s"
                    % (
                        caller,
                        jid,
                        real_sec if real_sec == "inherit" else sorted(real_sec),
                        norm_declared if norm_declared == "inherit" else sorted(norm_declared),
                    )
                )
            verified += 1
        if not found:
            offenders.append(
                "%s: no job calls %s%s -- the registry "
                "entry describes a call that is not there"
                % (caller, CONSOLE_PREFIX, entry["calls"])
            )

    # --- carried verbatim from check-workflow-gates.sh, lines 797-801 --------------------- --- (c) completeness: every external caller on disk must be registered A blind leg is reported only when there is nothing else to say. A concrete offender IS evidence the check ran, and burying it under "this check is blind" was how the first version of CHECK 4 reported a stale registry
    # entry as a missing submodule.
    blind: list[str] = []
    trees = sorted(glob.glob(os.path.join(scan_root, "private", "*", ".github", "workflows")))
    if not trees:
        blind.append(
            "no private/*/.github/workflows tree under %s: the completeness "
            "scan cannot see whether an unregistered external caller exists" % scan_root
        )

    for tree in trees:
        for path in sorted(
            glob.glob(os.path.join(tree, "*.yml")) + glob.glob(os.path.join(tree, "*.yaml"))
        ):
            rel = os.path.relpath(path, scan_root)
            try:
                doc = load(path)
            except (yaml.YAMLError, OSError):
                continue
            for jid, job in ((doc or {}).get("jobs") or {}).items():
                if not isinstance(job, dict):
                    continue
                uses = job.get("uses")
                if not isinstance(uses, str) or not uses.startswith(CONSOLE_PREFIX):
                    continue
                calls = uses[len(CONSOLE_PREFIX) :].split("@", 1)[0]
                if (rel, calls) not in registered:
                    offenders.append(
                        "%s: job '%s' calls %s but is not declared in "
                        "%s -- an unregistered external "
                        "caller is exactly what this check exists to prevent"
                        % (rel, jid, calls, os.path.basename(registry_file))
                    )

    if not verified:
        blind.append(
            "no registered external caller could be checked against its real file "
            "(no submodule containing one is checked out)"
        )

    if offenders:
        for line in offenders:
            print(line, file=sys.stderr, flush=True)
        return 1

    if blind:
        raise _BlindError("; ".join(blind))

    print(
        "info: %d external caller call-site(s) verified against their real files" % verified,
        flush=True,
    )
    return 0


# --------------------------------------------------------------------------- CHECK 5 -- Bitwarden jobs check out the map (check-workflow-gates.sh:886-955) ---------------------------------------------------------------------------
#
# --- carried verbatim from check-workflow-gates.sh, lines 864-883 ---------------------
# =============================================================================
# CHECK 5: a job that fetches from Bitwarden must CHECK OUT the map it resolves with.
#
# ./.github/actions/bws-secrets translates NAMES to UUIDs out of .ci/config/bws-secret-map.json before it calls sm-action, because sm-action addresses secrets by UUID only and 197 raw UUIDs across 63 job blocks would be unreviewable. So the map is a RUNTIME input to the composite, not documentation.
#
# A sparse checkout that stops at `.github/actions` therefore produces a job that looks deliberately scoped and fails with "bws-secret-map.json not found at ..." -- and it fails at the fetch step, in whatever job first needs a secret, which on the CD path is a production deploy. Found on 2026-09-02 in TWO jobs at once (backfill-release-sentinel `backfill`, cd-deploy-account
# `deploy`), both of which grew their `uses:` line long after their cone was written. Nothing connected the two edits, which is exactly what this check is for.
#
# The rule is deliberately narrow: it fires only when a sparse checkout EXISTS. A full checkout has everything, and demanding a `.ci/config` line there would be noise that teaches people to ignore the message.
# =============================================================================

MAP_DIR = ".ci/config"


def check5(yaml: ModuleType, root_dir: str) -> int:
    root = pathlib.Path(root_dir)
    # `*.yml` ONLY, on both directories. A `.yaml` workflow is invisible here.
    files = sorted((root / ".github" / "workflows").glob("*.yml"))
    files += sorted((root / ".ci" / "breakpoint" / "workflow").glob("*.yml"))

    offenders: list[str] = []
    checked = 0
    for path in files:
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print("error: %s does not parse (%s)" % (path.name, exc), file=sys.stderr, flush=True)
            return 1
        if not isinstance(doc, dict):
            continue
        for job_id, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
            if not any("bws-secrets" in str(s.get("uses", "")) for s in steps):
                continue
            cones = [
                str((s.get("with") or {}).get("sparse-checkout"))
                for s in steps
                if "actions/checkout" in str(s.get("uses", ""))
                and (s.get("with") or {}).get("sparse-checkout")
            ]
            if not cones:
                continue
            checked += 1
            offenders.extend(
                "%s: job '%s' fetches from Bitwarden but its sparse "
                "checkout does not include %s. "
                "./.github/actions/bws-secrets reads %s/bws-secret-map.json "
                "at run time and will fail with 'bws-secret-map.json not found'."
                % (path.name, job_id, MAP_DIR, MAP_DIR)
                for cone in cones
                if MAP_DIR not in cone
            )

    # --- carried verbatim from check-workflow-gates.sh, lines 931-939 --------------------- ANTI-VACUITY. This check can only fire on a job that BOTH fetches from Bitwarden and narrows its checkout, which is a small set by construction. If that set empties -- the composite is renamed, the cones are widened, the glob breaks -- the check passes for a reason indistinguishable from
    # correctness, so say which it was.
    if checked == 0:
        # And it FAILS, rather than announcing the vacuity and exiting 0 as it did until 2026-09-09. "This is the vacuous case, not a pass" followed by a green success line is a gate that has stopped meaning its own name: 10 jobs are in this set today, so an empty one is a broken matcher, never a clean tree.
        print(
            "error: no job both fetches from Bitwarden and narrows its checkout, so "
            "CHECK 5 asserted nothing. Ten jobs were in this set on 2026-09-09; an "
            "empty set means the bws-secrets composite was renamed, the sparse-checkout "
            "key moved, or the workflow glob stopped matching. Fix the matcher above.",
            file=sys.stderr,
            flush=True,
        )
        return 1

    for line in offenders:
        print("error: %s" % line, file=sys.stderr, flush=True)
    if offenders:
        return 1
    print("info: %d sparse Bitwarden-fetching job(s) check out the map" % checked, flush=True)
    return 0


# --------------------------------------------------------------------------- CHECK 6 -- nothing optional before the monitor (check-workflow-gates.sh:1012-1098) ---------------------------------------------------------------------------
#
# --- carried verbatim from check-workflow-gates.sh, lines 965-1009 ---------------------
# =============================================================================
# CHECK 6: nothing optional may run in front of the watchdog's monitor step.
#
# The watchdog is the thing that watches every other CI run. Its job therefore has an ordering property nothing else in this repo has: a step that can fail and that the monitor does not need is not merely noisy there, it silently disables the guard. On 2026-09-03 the shadow-secret compare -- a temporary migration scaffold that nothing consumes -- sat at step 7 of 7 ahead of the
# monitor, hit a real mismatch on ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN, and exited 1. Run 33704079162 reported "failure" having monitored NOTHING, and the only symptom was a red watchdog, which reads exactly like the watchdog working.
#
# The rule: a step BEFORE "Monitor jobs and cancel on failure" must either be one the monitor actually needs (the PREREQS allowlist, short on purpose) or be unable to cost the watch at all.
#
# "Unable to cost the watch" is not a name, it is two properties, and both are required because each alone leaves a door open:
#
# continue-on-error: true -- the step cannot FAIL the job, so the 2026-09-03 shape (exit 1 at step 7 of 7, monitor never runs) is structurally impossible rather than promised.
#   timeout-minutes: <= 5    -- the step cannot HANG the job either. The monitor's
# own deadline is 480s inside a 14-minute slim cap, so a step that merely blocks kills the watch just as dead as one that exits 1, and continue-on-error says nothing about that.
#
# This is deliberately stricter than the name list it replaces: a name proves somebody once thought about a step, these two prove the step cannot take the watchdog down no matter what it does. PREREQS stays for the steps that must be allowed to fail, because the monitor cannot run correctly without them.
#
# THE continue-on-error DOOR IS CURRENTLY CLOSED IN THIS REPO, and saying so here matters more than the door itself. check-workflows.sh bans the keyword outright ("Silently ignores step/job failures"), so no workflow can walk through it today -- as this session found by trying: the watchdog's Bitwarden fetch was moved ahead of the monitor with continue-on-error, this check accepted
# it on the property, and the banned-patterns gate refused it four minutes into CI. The move was reverted.
#
# The rule stays as written rather than being narrowed back to a name list, because the property is the thing that is actually true and the other gate's ban is a policy on top of it. If that ban is ever relaxed, this admits the case correctly and its test already proves both answers. Until then, PREREQS is the only way in.
# =============================================================================

MONITOR = "Monitor jobs and cancel on failure"
# Steps the monitor genuinely depends on: the checkout that puts its scripts on disk, and the deterministic attempt cap, which must run first BECAUSE it writes the env var the monitor reads.
PREREQS = {
    "Attempt cap (deterministic backstop)",
    # Added 2026-09-09. The monitor's two classifier tiers read credentials this step exports; without them it does not degrade gracefully, it hands the retry decision to an allowlist nobody reviewed -- which is the harm the workflow's own comment describes. That is the PREREQS contract: allowed to fail BECAUSE the monitor cannot run correctly without it.
    "Fetch secrets from Bitwarden",
}
MAX_TIMEOUT_MINUTES = 5


def harmless(step: dict) -> bool:
    """Can this step neither fail nor hang the job?

    Both answers must come from a LITERAL, never an expression: `continue-on-error:
    ${{ ... }}` is decided at run time, and a rule that reads it as safe is trusting
    a value it cannot see.
    """
    if step.get("continue-on-error") is not True:
        return False
    t = step.get("timeout-minutes")
    return isinstance(t, int) and 0 < t <= MAX_TIMEOUT_MINUTES


def scalar(value: object) -> str | None:
    """A YAML scalar as the string GitHub would render, or None if it is not one.

    YAML hands back whatever was written, so `name: 5` is an int and `name: null` is None. Everything below goes through here rather than assuming str.
    """
    if isinstance(value, str):
        return value or None
    if isinstance(value, (bool, int, float)):
        return str(value)
    return None


def step_label(step: dict) -> str:
    """What to call this step in a message, and what to match the monitor on.

    FIXED 2026-09-10. This was inlined as `s.get("name") or str(s.get("uses", ""))`, which returns a non-str for `name: 5` and then died on `"actions/checkout" in name` with `TypeError: argument of type 'int' is not a container or iterable` -- a traceback under which bash printed "move the step after the monitor", a fix for a crash that has nothing to do with ordering.
    """
    return scalar(step.get("name")) or scalar(step.get("uses")) or ""


def is_checkout(step: dict) -> bool:
    """A repository checkout, decided by `uses:` and NEVER by the display name.

    FIXED 2026-09-10. This used to ask `"actions/checkout" in <label>`, and the label only falls back to `uses:` when the step has no `name:`. So the exemption held for the 139 unnamed checkout steps under .github/workflows and was lost for the 5 named ones. One ordinary edit (`name: Checkout` on watchdog-monitor.yml's own checkout, which is unnamed today) would have turned this
    gate red on the one workflow it exists to guard, with a message telling the author to move the checkout AFTER the monitor and leave the monitor's scripts off disk.
    """
    uses = step.get("uses")
    return isinstance(uses, str) and uses.startswith("actions/checkout")


def check6(yaml: ModuleType, root_dir: str) -> int:
    root = pathlib.Path(root_dir)
    workflow = root / ".github" / "workflows" / "watchdog-monitor.yml"

    if not workflow.exists():
        print("error: %s is missing; CHECK 6 cannot report" % workflow, file=sys.stderr, flush=True)
        return 1

    # FIXED 2026-09-10. THREE of the five ways the monitor anchor can go missing used to end in a traceback rather than in this check's own message: an EMPTY document and a NON-MAPPING document both reached `doc.get("jobs")` and raised `AttributeError`, and a SYNTAX ERROR raised `yaml.YAMLError` out of safe_load. Bash printed "move the step after the monitor" on top of each,
    # telling the operator to reorder a step in a file that has no steps. All three are still failures -- the anti-vacuity rule below cannot be satisfied by a file that did not parse -- but each now names its cause.
    try:
        doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(
            "error: %s is not parseable YAML (%s); CHECK 6 cannot report" % (workflow, exc),
            file=sys.stderr,
            flush=True,
        )
        return 1
    if not isinstance(doc, dict):
        print(
            "error: %s did not parse as a YAML mapping (got %s); CHECK 6 cannot report"
            % (workflow, type(doc).__name__),
            file=sys.stderr,
            flush=True,
        )
        return 1

    offenders: list[str] = []
    found_monitor = False
    jobs = doc.get("jobs")
    for job_id, job in (jobs if isinstance(jobs, dict) else {}).items():
        if not isinstance(job, dict):
            continue
        steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
        names = [step_label(s) for s in steps]
        if MONITOR not in names:
            continue
        found_monitor = True
        cut = names.index(MONITOR)
        # `strict=True`: both slices come from the same list, so an unequal
        # length would be a bug in this function rather than in the input.
        for name, step in zip(names[:cut], steps[:cut], strict=True):
            if name in PREREQS or is_checkout(step) or harmless(step):
                continue
            offenders.append(
                "watchdog-monitor.yml: job '%s' runs %r BEFORE %r, "
                "and it can stop the watch: a failure there ends the job and the watchdog "
                "monitors nothing while reporting a failure that looks like its own. "
                "TWO ways out. Move it after the monitor with `if: always()`; or add it to "
                "PREREQS in CHECK 6 saying why it must be allowed to fail. "
                "A THIRD ROUTE EXISTS IN THIS CHECK'S LOGIC AND IS CLOSED IN THIS REPO: "
                "`continue-on-error: true` with `timeout-minutes: <= %s` "
                "satisfies the property here, but check-workflows.sh bans the keyword "
                "outright, so CI refuses it minutes later. Two sessions have now spent effort "
                "discovering that -- the second on 2026-09-09, because this message advertised "
                "the route while only the comment above recorded the ban. It is named here "
                "rather than hidden so the next reader does not rediscover it a third time."
                % (job_id, name, MONITOR, MAX_TIMEOUT_MINUTES)
            )

    # ANTI-VACUITY: a renamed monitor step would empty this check silently.
    if not found_monitor:
        print(
            "error: no job in watchdog-monitor.yml has a %r step. Either it was "
            "renamed -- update CHECK 6 -- or the watchdog lost its monitor." % MONITOR,
            file=sys.stderr,
            flush=True,
        )
        return 1

    for line in offenders:
        print("error: %s" % line, file=sys.stderr, flush=True)
    if offenders:
        return 1
    print("info: nothing optional precedes the watchdog's monitor step", flush=True)
    return 0


# --------------------------------------------------------------------------- The orchestrator (check-workflow-gates.sh:55-135, 202-212, 486-496, 594-604, 849-862, 957-964, 1100-1108) ---------------------------------------------------------------------------


def _guarded(fn: typing.Callable[[], int]) -> int:
    """Run one check the way bash runs one heredoc: a crash is exit 1.

    An uncaught exception in a `python3 - <<PYEOF` heredoc prints a traceback and
    exits 1, and bash's `RC=$?` then takes the offender branch. In-process an
    exception would abort the whole gate and skip the remaining checks, which is NOT what the twin does.
    """
    try:
        return fn()
    except SystemExit as exc:  # pragma: no cover - defensive
        code = exc.code
        return code if isinstance(code, int) else 1
    except BaseException:  # noqa: BLE001 - a heredoc's traceback is exit 1
        traceback.print_exc()
        sys.stderr.flush()
        return 1


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments
    palette = _Palette(os.environ.get("CI", ""))

    root_dir = str(paths.repo_root())
    default_workflows = os.path.join(root_dir, ".github", "workflows")
    workflows_dir = _env("WORKFLOWS_DIR", default_workflows)

    slim_timeout_max = _env("SLIM_TIMEOUT_MAX", "14")

    # Is this the repo's own workflow tree, or a gate test's fixture tree?
    real_workflow_tree = _env(
        "REAL_WORKFLOW_TREE", "true" if workflows_dir == default_workflows else "false"
    )
    slim_timeout_require_coverage = _env("SLIM_TIMEOUT_REQUIRE_COVERAGE", real_workflow_tree)

    external_callers_root = _env("EXTERNAL_CALLERS_ROOT", root_dir)
    external_callers_file = os.environ.get("EXTERNAL_CALLERS_FILE") or ""
    if not external_callers_file:
        if workflows_dir == default_workflows:
            external_callers_file = os.path.join(root_dir, ".github", "external-callers.yml")
        else:
            # A CHECK 1/2/3 fixture tree has no external callers to speak of.
            external_callers_file = ""

    # Anti-vacuity: nothing to check is a failure, not a pass.
    if not os.path.isdir(workflows_dir):
        palette.error("No workflows directory at %s -- this check is blind" % workflows_dir)
        return 1

    yaml = _ensure_yaml(palette)
    if yaml is None:
        return 2

    failed = 0

    # --- Check 1 ---------------------------------------------------------------
    palette.info(
        "Checking job-level if: blocks for always()/!cancelled() on needs.*.result references"
    )
    rc = _guarded(lambda: check1(yaml, workflows_dir))
    if rc == 0:
        palette.success(
            "All job-level if: blocks using needs.*.result include an "
            "always()/!cancelled() override"
        )
    elif rc == 3:
        palette.error(
            "Fix: point WORKFLOWS_DIR at a tree that contains workflow YAML; "
            "a check with no input cannot pass."
        )
        failed = 1
    else:
        palette.error("Workflow gate audit found offenders (see above).")
        palette.error(
            "Fix: prefix the offending if: with 'always() &&' so transitive skip "
            "propagation cannot silently disable the job."
        )
        failed = 1

    # --- Check 2 ---------------------------------------------------------------
    palette.info("Checking reusable-workflow secret/input contracts")
    rc = _guarded(
        lambda: check2(yaml, workflows_dir, real_workflow_tree == "true", external_callers_file)
    )
    if rc == 0:
        palette.success("Reusable-workflow secret/input contracts hold in both directions")
    elif rc == 3:
        palette.error(
            "Fix: point WORKFLOWS_DIR at a tree that contains workflow YAML; "
            "a check with no input cannot pass."
        )
        failed = 1
    else:
        palette.error("Reusable-workflow contract violations (see above).")
        palette.error(
            "Fix: declare the secret under on.workflow_call.secrets in the callee AND "
            'pass it from every caller. An undeclared secret reads as "" with no error.'
        )
        failed = 1

    # --- Check 3 ---------------------------------------------------------------
    palette.info("Checking every ubuntu-slim job declares timeout-minutes <= %s" % slim_timeout_max)
    rc = _guarded(
        lambda: check3(
            yaml, workflows_dir, slim_timeout_max, slim_timeout_require_coverage == "true"
        )
    )
    if rc == 0:
        palette.success("Every ubuntu-slim job declares timeout-minutes <= %s" % slim_timeout_max)
    elif rc == 3:
        palette.error(
            "Fix: point WORKFLOWS_DIR at a tree that contains ubuntu-slim jobs; "
            "a check with no input cannot pass."
        )
        failed = 1
    else:
        palette.error("ubuntu-slim timeout violations (see above).")
        palette.error(
            "Fix: add 'timeout-minutes: %s' (or less) to the job, or move it to "
            "ubuntu-latest if it genuinely needs longer." % slim_timeout_max
        )
        failed = 1

    # --- Check 4 ---------------------------------------------------------------
    if not external_callers_file:
        palette.info("Skipping external-caller contract check (fixture tree: no registry)")
    else:
        palette.info(
            "Checking external-caller contracts against %s"
            % os.path.basename(external_callers_file)
        )
        rc = _guarded(
            lambda: check4(yaml, workflows_dir, external_callers_file, external_callers_root)
        )
        if rc == 0:
            palette.success(
                "External-caller contracts hold and every external caller is registered"
            )
        elif rc == 3:
            palette.error("Fix: either .github/external-callers.yml declares no callers, or no")
            palette.error("     submodule holding one is checked out (git submodule update --init")
            palette.error("     private/account private/renet). A check with no input cannot pass.")
            failed = 1
        else:
            palette.error("External-caller contract violations (see above).")
            palette.error(
                "Fix: update .github/external-callers.yml AND the caller in the other "
                "repository together. Editing only this repo breaks their next run, "
                "not this PR."
            )
            failed = 1

    # --- Check 5 ---------------------------------------------------------------
    palette.info("Checking that every Bitwarden-fetching job checks out the secret map")
    rc = _guarded(lambda: check5(yaml, root_dir))
    if rc == 0:
        palette.success("Every sparse Bitwarden-fetching job checks out .ci/config")
    else:
        palette.error("Fix: add .ci/config to that job's sparse-checkout list. The cone must be a")
        palette.error("     superset of what every local action in the job READS, not just where")
        palette.error("     those actions live.")
        failed = 1

    # --- Check 6 ---------------------------------------------------------------
    palette.info("Checking that nothing optional precedes the watchdog's monitor step")
    rc = _guarded(lambda: check6(yaml, root_dir))
    if rc == 0:
        palette.success("The watchdog monitors before anything optional can stop it")
    else:
        palette.error("Fix: move the step after 'Monitor jobs and cancel on failure' and give it")
        palette.error(
            "     'if: always()', so a failure there still reports without costing the watch."
        )
        failed = 1

    return failed


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
