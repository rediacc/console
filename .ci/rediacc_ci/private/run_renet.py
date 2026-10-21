#!/usr/bin/env python3
"""Port of `.ci/scripts/private/run-renet.sh`, the registered gate `check:ci-renet`.

A thin wrapper: check that the `private/renet` submodule is checked out, pin `GOTOOLCHAIN`, and hand one stage name to the submodule's own `private/renet/.ci/ci.sh`. It reimplements nothing that script does.

THIS MODULE IS WHAT `check:ci-renet` RUNS, since W7P4-W. `package.json` spells the gate `PYTHONPATH=.ci python3 -m rediacc_ci.private.run_renet quality`, `scripts/ci-runner/manifest.ts` names this file as the gate's `leaf` and in its `paths`, and both `.github/workflows/ci-quality.yml` (quality) and `.github/workflows/ct-tests.yml` (test) run the module form. The licence is
`.ci/shadow/w7p4b-run-renet.observations.jsonl`, nine clean trees at `--assert --k 5`.

THE `---- gate ----` HEADER MOVED HERE when the twin was retired, the way `rediacc_ci.quality.staging_tag_guard` carries its own. `scripts/gate-bind.ts` resolves a gate by where its header lives, so one file claims `id: check:ci-renet` and it is this one; the header's `run:` was already the module form, which is what the binder emits into the workflow.

-----------------------------------------------------------------------------
THE SUBMODULE GUARD IS THE ONLY DECISION IN THE FILE, AND IT HAS THREE ARMS
-----------------------------------------------------------------------------
`common.sh:488-502`, reached here through `rediacc_ci.core.common .require_submodule` rather than re-derived, because that function is already differentially checked against the same twin and a second copy would be a second answer to one question:

  marker present        -> run the stage
  absent, `CI` == true  -> three `log_error` lines and EXIT 1
  absent, otherwise     -> one `log_warn` and EXIT 0

The middle arm is the whole reason the guard is not a bare `[[ -e ]] || exit 0`, and `common.sh` says why in its own comment: these gates carry govulncheck, deadcode and golangci-lint, and all three would report success while checking nothing. The third arm keeps a fresh clone without `--recursive` workable, and it is a REAL HOLE IN THE LOCAL GATE that is documented rather than
closed (the retired `.ci/scripts/test/gates/test-gate-anti-vacuity.sh:317`, now ported to `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py`, recorded that this script used to exit 0 silently in CI too). `npm run check:ci-renet` on a machine with no submodule prints one warning and exits 0.

`CI` is tested as the LITERAL `"${CI:-false}" == "true"`, not through an
is-CI helper, so `GITHUB_ACTIONS=true` with `CI` unset takes the LOCAL arm. That
inconsistency belongs to the twin and is reproduced, not harmonised.

THE MARKER TEST IS `-e`, NOT `-f`. An uninitialised submodule leaves its mount point behind as an empty directory, so existence is the right question for the DIRECTORY case; the consequence at the FILE level is that a directory named `ci.sh` passes the guard and then fails at exec time with `Is a directory` and status 126. Both sides do that, and the differential pins it.

-----------------------------------------------------------------------------
GOTOOLCHAIN IS EXPORTED, NOT PASSED
-----------------------------------------------------------------------------
`export GOTOOLCHAIN="${GOTOOLCHAIN:-auto}"` is reproduced as a mutation of
`os.environ`, which is what an export IS: the child inherits it and so would any
further child. Writing it into a per-call `env=` dict would look equivalent and
would not be, for a `ci.sh` that spawns its own helpers.

`:-` means UNSET OR EMPTY both become `auto`. `GOTOOLCHAIN=""` therefore does
not disable the pin, it selects `auto`, and the port reads the variable directly at the call site (`os.environ.get("GOTOOLCHAIN", "")`) rather than through any
`env = dict(os.environ)` alias, so the env-manifest reader can see the name.

WHY `auto` AND NOT A PINNED VERSION: the twin's own comment records that this used to pin `go1.25.10+auto` while `private/renet/go.mod` declared `go1.25.12`, already diverged and masked only because the `+auto` suffix silently upgrades. `go.mod`'s `toolchain` directive is the single source of truth.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO
-----------------------------------------------------------------------------
Exactly one thing: `private/renet/.ci/ci.sh <stage>`, with the parent's cwd, stdout and stderr, and its exit status returned unchanged. NO `cd` HAPPENS FIRST, in either implementation, so the stage inherits whatever directory the caller was in; `ci.sh` locates itself. The differential (`.ci/rediacc_ci/tests/test_private_run_renet.py`) puts a recording `ci.sh` in the fixture and
compares its argv, cwd and inherited `GOTOOLCHAIN`, because a port that printed the same banner while never invoking the stage would satisfy a stdout-only comparison and run no Go tests at all.

TWO GATES RUN THROUGH IT. `check:ci-renet` hands over `quality`; `check:ci-renet-govulncheck` (step `Renet govulncheck`, hand-registered, so it carries no header of its own) hands over `govulncheck`, the stage `ci.sh` split out of quality on 2026-10-21 (PLAN-plan-per-pr-loop R1 B): an advisory published after the commit landed is upstream drift, and inside `quality` it both stopped `i18n.sh` under `set -e` and left the nightly soak waiver (`rediacc_ci.release.nightly_tested_edge`) unable to tell it from a lint failure in the same step.

EXTRA ARGUMENTS ARE DROPPED IN SILENCE. `run-renet.sh quality test` runs `quality` and says nothing about `test`; so does this. Reproduced deliberately, not endorsed.

CONSOLE ROOT comes from this file's own location (`parents[3]`), matching the twin's `get_repo_root`; `rediacc_ci.paths.repo_root()` is not used because it honours `$REDIACC_CI_ROOT` and the twin honours nothing.

-----------------------------------------------------------------------------
EVERY GOLANGCI EXCLUSION RULE CARRIES A BLOCKER REASON
-----------------------------------------------------------------------------
NEW behaviour with no twin (PLAN-inline-suppressions WD2). Before a stage that lints (`all`, `quality`), `private/renet/.golangci.yml` is read line by line and every item of `linters.exclusions.rules` must sit under a comment block holding a `# BLOCKER: <reason>` line; the reason runs from that line to the end of the block and goes through `rediacc_ci.core.allowlist.validate_reason`, the one implementation of the quality rules. A
rule with no reason, a reason the quality rules refuse, a missing config file, or a config in which no rule is found at all is a failure before `ci.sh` runs: zero rules read is CANNOT VERIFY, never a pass. The other half, a rule or one linter of a rule that skipped nothing on every release GOOS, is `private/renet/.ci/scripts/quality/lint.sh`'s, because only the golangci-lint run it already makes can see it; it lints a copy of the config split one rule per linter, since golangci-lint counts skips per rule.

---- gate ----
step: Run renet quality
needs: none
id: check:ci-renet
run: PYTHONPATH=.ci python3 -m rediacc_ci.private.run_renet quality
lane: quality-go
---- end gate ----
"""

from __future__ import annotations

import inspect
import json
import os
import pathlib
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import allowlist, common

# `STAGE="${1:-all}"`. The twin documents four (all, quality, test, build) and
# validates none of them: an unknown stage is forwarded to `ci.sh`, which is where the twin leaves the decision, so no validation is invented here either.
DEFAULT_STAGE = "all"

# The label `require_submodule` puts in front of both its CI error and its local warning. Verbatim from the twin, because a caller greps the warning.
SUBMODULE_LABEL = "Renet submodule"

# The stages whose `ci.sh` arm runs golangci-lint, so the exclusion rules it reads are checked first.
LINT_STAGES = frozenset({"all", "quality"})

# The golangci config, relative to the renet submodule root, and the label findings name it by.
GOLANGCI_CONFIG = ".golangci.yml"
GOLANGCI_LABEL = "private/renet/.golangci.yml"

BLOCKER_PREFIX = "# BLOCKER:"


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_item(stripped: str) -> bool:
    """A YAML sequence item: `- x`, or a bare `-` whose body follows on the next lines (review e7aa60fa.1)."""
    return stripped == "-" or stripped.startswith("- ")


def _rules_block(lines: list[str]) -> tuple[int, int] | None:
    """`(first, end)` line indexes of the items under `linters:` > `exclusions:` > `rules:`, or None when that path is absent."""
    path = ("linters:", "exclusions:", "rules:")
    depth, parent_indent = 0, -1
    # The indent of the current parent's direct children, learned from its first content line.
    child_indent: int | None = 0
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        ind = _indent(raw)
        if depth and ind <= parent_indent:
            return None
        if child_indent is None:
            child_indent = ind
        if stripped == path[depth] and ind == child_indent:
            depth, parent_indent, child_indent = depth + 1, ind, None
            if depth == len(path):
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    body = lines[j].strip()
                    # A sequence may sit at the same indent as its `rules:` key (valid YAML), so a `- ` line at that indent is still an item.
                    if (
                        body
                        and not body.startswith("#")
                        and _indent(lines[j]) <= ind
                        and not (_indent(lines[j]) == ind and _is_item(body))
                    ):
                        end = j
                        break
                return i + 1, end
    return None


def exclusion_rule_findings(text: str, label: str = GOLANGCI_LABEL) -> tuple[list[str], int]:
    """`(findings, rules_read)` for the `linters.exclusions.rules` items of a golangci config.

    An item is a `- ` line at the indent of the block's first item. Its reason is the `# BLOCKER:` line in the run of comment lines directly above it, plus the comment lines that follow that line in the same run. A blank line ends the run, so a reason never reaches across to the next rule.
    """
    lines = text.splitlines()
    block = _rules_block(lines)
    if block is None:
        return [
            "%s: no linters.exclusions.rules list was found, so no rule can be verified" % label
        ], 0
    first, end = block
    item_indent: int | None = None
    findings: list[str] = []
    rules = 0
    for i in range(first, end):
        stripped = lines[i].strip()
        if not _is_item(stripped):
            continue
        if item_indent is None:
            item_indent = _indent(lines[i])
        if _indent(lines[i]) != item_indent:
            continue
        rules += 1
        run: list[str] = []
        j = i - 1
        while j >= first and lines[j].strip().startswith("#"):
            run.insert(0, lines[j].strip())
            j -= 1
        starts = [k for k, c in enumerate(run) if c.startswith(BLOCKER_PREFIX)]
        entry = "rule at line %d (%s)" % (i + 1, stripped[2:].strip())
        if not starts:
            findings.append(
                "%s:%d: %s carries no `%s <reason>` comment" % (label, i + 1, entry, BLOCKER_PREFIX)
            )
            continue
        tail = run[starts[-1] :]
        parts = [tail[0][len(BLOCKER_PREFIX) :]] + [c.lstrip("#") for c in tail[1:]]
        reason = " ".join(p.strip() for p in parts if p.strip())
        rejection = allowlist.validate_reason(entry, reason, label)
        if rejection is not None:
            findings.append("%s:%d: %s" % (label, i + 1, rejection.message.strip()))
    if rules == 0:
        findings.append("%s: linters.exclusions.rules holds no rule, so CANNOT VERIFY" % label)
    return findings, rules


def check_exclusion_rules(renet_dir: pathlib.Path) -> list[str]:
    """The findings for the submodule's golangci config; a missing or unreadable file is one finding."""
    path = renet_dir / GOLANGCI_CONFIG
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [
            "%s: cannot be read (%s), so no exclusion rule can be verified"
            % (GOLANGCI_LABEL, getattr(exc, "strerror", None) or exc)
        ]
    return exclusion_rule_findings(text)[0]


def console_root() -> pathlib.Path:
    """The repository root, derived the way the twin derives it: from the subject file's own path, never from cwd and never from an env override."""
    # This file: <root>/.ci/rediacc_ci/private/run_renet.py
    return pathlib.Path(__file__).resolve().parents[3]


def _shell_diagnostic(message: str) -> str:
    """`<$0>: line <n>: <message>`, the shape bash puts on a script's stderr.

    The line number is the CALLER's, taken from the live frame rather than hard-coded, so it cannot go stale when this file is reflowed.
    """
    frame = inspect.currentframe()
    back = frame.f_back if frame is not None else None
    lineno = back.f_lineno if back is not None else 0
    return "%s: line %d: %s" % (sys.argv[0], lineno, message)


def stage_of(argv: list[str]) -> str:
    """`"${1:-all}"`: unset OR EMPTY yields `all`, and `$2` onward is ignored."""
    return argv[0] if argv and argv[0] else DEFAULT_STAGE


class ShardManifestError(ValueError):
    """A malformed or inapplicable `--shard-manifest`/`--shard` pair.

    Always caught in `main`, never left to raise a traceback: every other guard in this
    file (the submodule arms, the exec failures) reports a clean one-line diagnostic and a
    real exit code, and a stack trace here would be the odd one out.
    """


def parse_shard_spec(spec: str) -> tuple[int, int]:
    """`"i/N"`, 1-based -- the same shape `--shard` takes everywhere else in this codebase
    (`scripts/ci-runner/run.ts`'s own `--shard` parsing, `shard-manifest.ts`'s `legIds`)."""
    left, sep, right = spec.partition("/")
    if not sep:
        raise ShardManifestError('--shard must be "i/N" (1-based), got %r' % (spec,))
    try:
        index, of = int(left), int(right)
    except ValueError:
        raise ShardManifestError('--shard must be "i/N" (1-based), got %r' % (spec,)) from None
    if of < 1 or index < 1 or index > of:
        raise ShardManifestError("--shard %r: index must be between 1 and %d" % (spec, of))
    return index, of


def leg_ids(manifest_text: str, manifest_path: str, index: int, of: int) -> list[str]:
    """The exact ids one leg of a committed `.ci/config/shards/<lane>.json` manifest holds
    (`test-e2e-workers.json`'s own shape: `{lane, of, generatedAt, legs:[{index, ids}]}`).

    An independent Python reading of the same language-agnostic JSON `legIds`
    (`scripts/ci-runner/shard-manifest.ts`) reads, not a port of it: this mirrors its three
    refusals (an `of` mismatch, a missing leg, an EMPTY leg -- a leg that would report green
    having run nothing) rather than importing TypeScript into a Python gate.
    """
    try:
        data = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise ShardManifestError("%s is not valid JSON: %s" % (manifest_path, exc)) from None
    if not isinstance(data, dict) or not isinstance(data.get("legs"), list):
        raise ShardManifestError('%s is missing "legs"' % (manifest_path,))
    manifest_of = data.get("of")
    if not isinstance(manifest_of, int) or manifest_of != of:
        raise ShardManifestError(
            "%s has %r leg(s) on record; asked for shard %d/%d"
            % (manifest_path, manifest_of, index, of)
        )
    matches = [leg for leg in data["legs"] if isinstance(leg, dict) and leg.get("index") == index]
    if not matches:
        known = sorted(
            leg["index"]
            for leg in data["legs"]
            if isinstance(leg, dict) and isinstance(leg.get("index"), int)
        )
        raise ShardManifestError(
            "%s has no leg %d (of %d); legs on record: %s"
            % (manifest_path, index, of, ", ".join(str(i) for i in known))
        )
    ids = matches[0].get("ids")
    if not isinstance(ids, list) or not ids:
        raise ShardManifestError("%s leg %d is EMPTY" % (manifest_path, index))
    return [str(x) for x in ids]


def parse_argv(argv: list[str]) -> tuple[str, str | None, str | None]:
    """The stage, plus an optional `--shard-manifest PATH --shard i/N` pair.

    EVERYTHING ELSE AFTER THE STAGE IS STILL DROPPED IN SILENCE: this only recognises the
    two new flags by exact token match and never turns an unrecognised trailing argument
    into an error, which is what keeps `"extra arguments are dropped"` true for every argv
    this file was already driven with before this box.
    """
    stage = stage_of(argv)
    rest = argv[1:] if argv else []
    manifest_path: str | None = None
    shard_spec: str | None = None
    i = 0
    while i < len(rest):
        if rest[i] == "--shard-manifest" and i + 1 < len(rest):
            manifest_path = rest[i + 1]
            i += 2
            continue
        if rest[i] == "--shard" and i + 1 < len(rest):
            shard_spec = rest[i + 1]
            i += 2
            continue
        i += 1
    return stage, manifest_path, shard_spec


def main(argv: list[str]) -> int:
    stage, manifest_path, shard_spec = parse_argv(argv)

    # PLAN-ci-time-budget T2.14. `--shard-manifest PATH --shard i/N` (both or neither,
    # the same conjunct `scripts/ci-runner/run.ts` enforces for its own `--lane`/`--shard`)
    # reads one leg of a committed go-package manifest and exports it as RENET_TEST_PKGS,
    # which `private/renet/.ci/scripts/test/run-tests.sh` reads in place of `./pkg/...
    # ./cmd/...`. An EXPORT, like GOTOOLCHAIN below: `ci.sh test` is the direct child that
    # sources run-tests.sh, not a grandchild, but the pattern is one this file already
    # uses and a per-call `env=` would be the same trap noted there.
    if manifest_path is not None or shard_spec is not None:
        if manifest_path is None or shard_spec is None:
            print(
                _shell_diagnostic("--shard-manifest and --shard must both be given, or neither"),
                file=sys.stderr,
                flush=True,
            )
            return 1
        try:
            index, of = parse_shard_spec(shard_spec)
            ids = leg_ids(
                pathlib.Path(manifest_path).read_text(encoding="utf-8"), manifest_path, index, of
            )
        except ShardManifestError as exc:
            print(_shell_diagnostic(str(exc)), file=sys.stderr, flush=True)
            return 1
        except OSError as exc:
            print(
                _shell_diagnostic("%s: %s" % (manifest_path, exc.strerror or exc)),
                file=sys.stderr,
                flush=True,
            )
            return 1
        os.environ["RENET_TEST_PKGS"] = " ".join(ids)

    renet_dir = console_root() / "private" / "renet"
    ci_sh = renet_dir / ".ci" / "ci.sh"

    try:
        present = common.require_submodule(ci_sh, SUBMODULE_LABEL)
    except common.RefusalError as exc:
        # The CI arm: three lines through `log_error`, then the twin's status 1.
        exc.report()
        return exc.code
    if not present:
        # `require_submodule ... || exit 0`. The warning was already printed.
        return 0

    log.step("Running renet CI (stage: %s)..." % stage)

    if stage in LINT_STAGES:
        findings = check_exclusion_rules(renet_dir)
        if findings:
            for finding in findings:
                log.error(finding)
            return 1

    # An EXPORT, not a per-call env: `ci.sh` spawns its own children.
    os.environ["GOTOOLCHAIN"] = os.environ.get("GOTOOLCHAIN", "") or "auto"

    try:
        completed = subprocess.run([str(ci_sh), stage], check=False)
    except PermissionError:
        # MEASURED, NOT ASSUMED. `execve` on a DIRECTORY returns EACCES, so Python raises PermissionError for both the unreadable file and the directory; bash stats the target and says `Is a directory` for the second. Driven both ways against bash before this branch was written. The status is 126 either way.
        why = "Is a directory" if ci_sh.is_dir() else "Permission denied"
        print(_shell_diagnostic("%s: %s" % (ci_sh, why)), file=sys.stderr, flush=True)
        return 126
    except OSError:
        # bash's "command not found" status for a path it cannot execute. The guard above already proved the path EXISTS, so this arm is reachable only for an exotic failure (a dangling symlink, a bad interpreter line); it is here so such a case exits like the twin rather than raising a traceback that reads as flake.
        print(
            _shell_diagnostic("%s: No such file or directory" % ci_sh), file=sys.stderr, flush=True
        )
        return 127

    # `set -e`: the stage's own status, unchanged, and nothing added on success.
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
