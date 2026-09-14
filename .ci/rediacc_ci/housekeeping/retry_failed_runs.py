#!/usr/bin/env python3
"""Port of `.ci/scripts/housekeeping/retry-failed-runs.sh`.

Nightly sweep that re-runs the failed jobs of workflow runs that failed for a
reason a rerun can fix. Usage: `retry_failed_runs.py [--dry-run]`.

THE FILTERS ARE THE FEATURE, and the twin's 40-line banner is the evidence for
each one: three measured days of runs held 64 failures, 63 of them
watchdog-monitor.yml failing BY DESIGN. So `cancelled` is never retried, the
watchdog is excluded BY PATH rather than by its generated display name, a run
whose head is no longer any branch tip is treated as superseded, and both an
attempt cap and an age floor apply. All five are reproduced exactly; dropping
any one turns a sweeper with an expected yield of ~1 per night into one that
retries 63 deliberate failures.

EXPECTED YIELD IS ~1 PER NIGHT, AND THE SUMMARY LINE IS WHAT MAKES A ZERO
READABLE. `considered=.. excluded=.. too-old=.. attempt-capped=.. dead-head=..
retried=..` prints on every run, including the ones that retry nothing, because
a sweeper that legitimately does nothing must be distinguishable from a broken
one. The port prints the same six numbers.

TWO LOGGERS, BECAUSE THE TWIN HAS TWO. `source common.sh 2>/dev/null || { ... }`
gives this script common.sh's stderr loggers when the library is present and a
private `echo`-based set when it is not, and the two are NOT cosmetic variants
of each other:

    level   common.sh                     fallback
    info    "✓ <msg>"  -> stderr     "  <msg>"        -> STDOUT
    warn    "⚠ <msg>"  -> stderr     "  WARN: <msg>"  -> stderr
    step    "→ <msg>"  -> stderr     "==> <msg>"      -> STDOUT
    error   "✗ <msg>"  -> stderr     "<msg>"          -> stderr

`_Loggers.for_root()` picks the pair off the same single input the twin picks it
off (does `<root>/.ci/scripts/lib/common.sh` exist), and the differential drives
BOTH by copying each subject into a fixture tree with no lib directory. A port
that implemented only the library path would be byte-identical in CI and put
every line on the wrong stream on a fresh clone.

`jq`, `date` AND `gh` ARE STILL SHELLED OUT TO, each for a different reason.
`gh` is the API. `date -u -d "$created"` accepts GNU's whole free-form date
grammar and returns 0 on strings no Python parser agrees about, and the twin's
`|| echo 0` turns exactly that answer into the too-old skip, so the port asks
the same `date`. `jq -r '... | @tsv'` is the record splitter, and its escaping
of a tab or newline INSIDE a workflow name is what keeps one run on one line;
re-implementing it would put the port's idea of `@tsv` against the twin's.

THE TAB SPLIT IS NOT A TAB SPLIT, and `read_fields` exists because of it. The
twin reads with `IFS=$'\\t'`, and TAB IS AN IFS WHITESPACE CHARACTER in bash, so
runs of tabs collapse into one delimiter and leading and trailing tabs are
dropped. A run whose `.name` is null therefore does NOT yield an empty second
field: every later field shifts left by one, and the script reads the workflow
PATH as the name. Driven against real bash, reproduced rather than repaired,
and pinned in both directions by `test_read_fields_collapses_runs_of_tabs`.

K=5 LEDGER: `.ci/shadow/w7p6-retry-failed-runs.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import time

from rediacc_ci import log

# `${RETRY_REPO:-rediacc/console}` and the three numeric knobs (:66-69).
DEFAULT_REPO = "rediacc/console"
DEFAULT_MAX_AGE_HOURS = 48
DEFAULT_MAX_ATTEMPT = 3
DEFAULT_MAX_RETRIES_PER_RUN = 5

# `EXCLUDED_PATHS` (:74-76). BY PATH, NEVER BY DISPLAY NAME: watchdog-monitor's
# name is generated per run ("Watchdog: run <id> (gen N)"), so a name match is
# unwritable, and without this entry 63 of 64 candidates are noise.
EXCLUDED_PATHS = (".github/workflows/watchdog-monitor.yml",)

# `gh api ... --jq` (:91) and (:97-98), and the `jq -r` record splitter (:153).
BRANCHES_JQ = ".[].commit.sha"
RUNS_JQ = "[.workflow_runs[] | {id, name, path, head_sha, run_attempt, created_at}]"
TSV_JQ = ".[] | [.id, .name, .path, .head_sha, .run_attempt, .created_at] | @tsv"

# `|| echo '[]'` (:98): the fallback for a runs listing that could not be read.
EMPTY_RUNS = "[]"

# The six fields `read -r` names, in order.
FIELD_COUNT = 6


class _Loggers:
    """The twin's two logging worlds, chosen the way the twin chooses them."""

    def __init__(self, *, common_sh: bool) -> None:
        self.common_sh = common_sh

    @classmethod
    def for_root(cls, root: pathlib.Path) -> _Loggers:
        return cls(common_sh=(root / ".ci" / "scripts" / "lib" / "common.sh").is_file())

    def info(self, message: str) -> None:
        if self.common_sh:
            log.info(message)
        else:
            print("  %s" % message, flush=True)

    def warn(self, message: str) -> None:
        if self.common_sh:
            log.warn(message)
        else:
            print("  WARN: %s" % message, file=sys.stderr, flush=True)

    def step(self, message: str) -> None:
        if self.common_sh:
            log.step(message)
        else:
            print("==> %s" % message, flush=True)

    def error(self, message: str) -> None:
        if self.common_sh:
            log.error(message)
        else:
            print(message, file=sys.stderr, flush=True)

    def require_cmd(self, cmd: str) -> bool:
        """Both worlds print the same words; only the decoration differs.

        The fallback defines its OWN `require_cmd` (:55-60) rather than calling
        common.sh's, and the twin says why in a comment: a fallback for
        "common.sh is missing" that called common.sh's helper would die at 127
        while reporting nothing about the dependency it exists to report.
        """
        if shutil.which(cmd) is not None:
            return True
        self.error("Required command '%s' is not available" % cmd)
        return False


def console_root() -> pathlib.Path:
    """`SCRIPT_DIR/../../..` from `.ci/scripts/housekeeping/`.

    This module sits one directory deeper, so it is `parents[3]` against the
    twin's `parents[2]`; both land on the repository root.
    """
    return pathlib.Path(__file__).resolve().parents[3]


def is_excluded(path: str) -> bool:
    """`is_excluded` (:78-84). Exact string equality against the list."""
    return path in EXCLUDED_PATHS


def read_fields(line: str, count: int = FIELD_COUNT) -> list[str]:
    """`IFS=$'\\t' read -r a b c d e f`, tab-as-IFS-whitespace included.

    THREE RULES, ALL FROM BASH AND NONE FROM `str.split`:

      1. Leading and trailing tabs are DROPPED, because tab is an IFS
         whitespace character.
      2. A RUN of tabs is ONE delimiter, for the same reason. This is the
         field-shifting hazard the module docstring names.
      3. The LAST variable absorbs the remainder including its internal
         delimiters, with trailing IFS whitespace stripped.

    Short lines pad with empty strings, which is what bash does to the
    variables it did not reach.
    """
    stripped = line.strip("\t")
    if not stripped:
        return [""] * count
    parts: list[str] = []
    rest = stripped
    while len(parts) < count - 1 and "\t" in rest:
        head, _, tail = rest.partition("\t")
        parts.append(head)
        rest = tail.lstrip("\t")
    parts.append(rest.rstrip("\t"))
    while len(parts) < count:
        parts.append("")
    return parts


def env_int(name: str, default: int, env: dict[str, str] | None = None) -> int:
    """`${RETRY_MAX_AGE_HOURS:-48}` reaching a bash arithmetic context.

    An unset OR EMPTY value takes the default, which is what `:-` means. A value
    bash would read as something other than a decimal integer (`0x10`, `010`,
    a bare identifier) is NOT reproduced: bash would treat those as hex, octal
    and a variable reference respectively, nothing in this repository sets them
    that way, and inventing an answer here would be a second arithmetic
    evaluator. Such a value is refused loudly rather than folded into the
    default, because a knob that silently means 48 when the operator wrote
    something else is how a sweeper quietly stops sweeping.
    """
    e = dict(os.environ) if env is None else env
    raw = e.get(name, "")
    if raw == "":
        return default
    try:
        return int(raw, 10)
    except ValueError:
        raise ValueError(
            "%s=%r is not a decimal integer; the twin would hand it to bash "
            "arithmetic and this port will not guess what that means" % (name, raw)
        ) from None


def _gh_or_empty(args: list[str], fallback: str) -> str:
    """`$(gh ... 2>/dev/null || echo <fallback>)`.

    Both halves write to the same captured stdout, so a call that printed
    something AND failed contributes both, exactly as bash concatenates them,
    and command substitution then strips every trailing newline.
    """
    proc = subprocess.run(
        ["gh", *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False
    )
    text = proc.stdout
    if proc.returncode != 0:
        text += fallback + "\n" if fallback else ""
    return text.rstrip("\n")


def tsv_records(runs_json: str) -> list[str]:
    """`echo "$RUNS" | jq -r '<TSV_JQ>'`, one line per record.

    jq's STDERR IS INHERITED, as it is in the twin: a malformed `$RUNS` prints
    jq's own complaint and yields no records, and the process substitution's
    exit status is never checked on either side.
    """
    proc = subprocess.run(
        ["jq", "-r", TSV_JQ],
        input=runs_json + "\n",
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.stdout.split("\n")


def created_epoch(created: str) -> int:
    """`date -u -d "$created" +%s 2>/dev/null || echo 0`.

    ZERO IS THE FAILURE VALUE AND THE TWIN THEN TREATS IT AS TOO-OLD, which is
    the safe direction: an unparseable timestamp must not license a rerun.
    """
    proc = subprocess.run(
        ["date", "-u", "-d", created, "+%s"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return 0
    text = proc.stdout.rstrip("\n")
    try:
        return int(text, 10)
    except ValueError:
        return 0


def head_is_live(head: str, live_heads: str) -> bool:
    """`grep -qx "$head" <<<"$LIVE_HEADS"`.

    `-x` WITHOUT `-F` means the head is a BASIC REGULAR EXPRESSION anchored to
    the whole line. For the only value that ever arrives, a 40-character hex
    object name, a BRE and a literal are the same string, so this compares
    whole lines. A head containing a regex metacharacter would diverge, and git
    cannot produce one.
    """
    return head in live_heads.split("\n")


def main(argv: list[str]) -> int:
    root = console_root()
    out = _Loggers.for_root(root)

    if not out.require_cmd("gh"):
        return 1
    if not out.require_cmd("jq"):
        return 1

    repo = os.environ.get("RETRY_REPO") or DEFAULT_REPO
    try:
        max_age_hours = env_int("RETRY_MAX_AGE_HOURS", DEFAULT_MAX_AGE_HOURS)
        max_attempt = env_int("RETRY_MAX_ATTEMPT", DEFAULT_MAX_ATTEMPT)
        max_retries = env_int("RETRY_MAX_PER_RUN", DEFAULT_MAX_RETRIES_PER_RUN)
    except ValueError as exc:
        out.error(str(exc))
        return 1

    # `[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true` (:71). ONLY argv[1], and
    # only that exact spelling: `retry-failed-runs.sh -n` is a silent live run.
    dry_run = bool(argv) and argv[0] == "--dry-run"

    out.step("Nightly retry: failed runs in %s (last %dh)" % (repo, max_age_hours))

    # FAIL CLOSED (:88-95). Without the branch tips a superseded run is
    # indistinguishable from a current one, and retrying a superseded run is the
    # expensive mistake, so an unreadable listing exits 0 having done nothing.
    live_heads = _gh_or_empty(
        ["api", "repos/%s/branches?per_page=100" % repo, "--paginate", "--jq", BRANCHES_JQ], ""
    )
    if not live_heads:
        out.warn("could not list branch tips; skipping rather than retrying on incomplete data")
        return 0

    runs = _gh_or_empty(
        ["api", "repos/%s/actions/runs?status=failure&per_page=100" % repo, "--jq", RUNS_JQ],
        EMPTY_RUNS,
    )

    now = int(time.time())
    considered = 0
    skip_excluded = 0
    skip_old = 0
    skip_attempt = 0
    skip_dead_head = 0
    retried = 0

    for line in tsv_records(runs):
        run_id, name, wpath, head, attempt, created = read_fields(line)
        if not run_id:
            continue
        considered += 1

        if is_excluded(wpath):
            skip_excluded += 1
            continue

        epoch = created_epoch(created)
        if epoch == 0 or now - epoch > max_age_hours * 3600:
            skip_old += 1
            continue

        if _as_int(attempt) >= max_attempt:
            skip_attempt += 1
            out.info(
                "skip %s (%s): already at attempt %s; a rerun is not fixing this"
                % (run_id, name, attempt)
            )
            continue

        if not head_is_live(head, live_heads):
            skip_dead_head += 1
            continue

        if retried >= max_retries:
            out.warn("hit RETRY_MAX_PER_RUN=%d; the rest wait for tomorrow" % max_retries)
            break

        if dry_run:
            out.info(
                "[DRY-RUN] would rerun %s (%s, attempt %s, head %s)"
                % (run_id, name, attempt, head[:8])
            )
            retried += 1
            continue

        rerun_path = "repos/%s/actions/runs/%s/rerun-failed-jobs" % (repo, run_id)
        rc = subprocess.run(
            ["gh", "api", "-X", "POST", rerun_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        if rc == 0:
            out.info("reran %s (%s, was attempt %s)" % (run_id, name, attempt))
            retried += 1
        else:
            # A run still winding down answers 403 "already running" -- not an
            # error worth failing the job over, and tomorrow picks it up.
            out.warn("could not rerun %s (%s); likely still in progress" % (run_id, name))

    out.info(
        "considered=%d excluded=%d too-old=%d attempt-capped=%d dead-head=%d retried=%d"
        % (considered, skip_excluded, skip_old, skip_attempt, skip_dead_head, retried)
    )
    if retried == 0:
        out.info("nothing to retry -- on this repo's baseline that is the normal night")
    return 0


def _as_int(text: str) -> int:
    """`[[ "$attempt" -ge "$MAX_ATTEMPT" ]]`, for the one field gh supplies.

    `.run_attempt` is a JSON number, so `@tsv` renders a decimal integer, and
    the only way anything else arrives is the field shift the module docstring
    describes: a null `.name` slides the TIMESTAMP into this column.

    THE ONE DELIBERATE DIVERGENCE IN THIS PORT, and it is named rather than
    hidden. `[[ "2026-09-13T10:20:30Z" -ge 3 ]]` makes bash write `value too
    great for base (error token is "09")` to stderr and then evaluate FALSE.
    Reading 0 here reaches the same FALSE, and the same verdict, without
    carrying a bash arithmetic evaluator into this module for the sake of a
    diagnostic line that could not be byte-identical anyway (it names the
    script and the line). The two agree on the exit code, the six counters and
    every gh call; they differ by that one line, and
    `test_divergence_a_null_workflow_name_shifts_the_fields_and_only_bash_complains`
    asserts both halves.

    The residue, stated so it is not discovered later: with
    `RETRY_MAX_ATTEMPT=0` the two would also disagree on the VERDICT, because
    `0 >= 0` is true here and bash's error is false. Nothing sets it to 0, and
    a 0 cap would disable the sweeper outright.
    """
    try:
        return int(text, 10)
    except ValueError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
