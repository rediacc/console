"""Port of `.ci/scripts/autopilot/sweep-collect.sh`.

Collects every PR the 2-hourly sweeper should re-dispatch: LABEL-ARMED UNION CAMPAIGN-ARMED, one number per line in `--out`.

THE UNION IS THE FIX, in the twin's words: the sweep used to list label-armed PRs only, and its own comment admitted the gap. A PR armed only by an open campaign carries no label, so campaign rounds rode their own `workflow_run` events -- and those events are exactly what a sweeper exists to survive the loss of. The sweep was reaching the arming path that needs it least.

READ-ONLY. Listing PRs and reading comments needs no app token; the dispatch that follows is a separate step with a separate credential. Trust in a campaign comes from the campaign scanner, which this script SHELLS OUT TO rather than reimplements (see below), because console is public and a lookalike comment claiming `campaign: open` is the obvious way to make the sweeper dispatch
rounds nobody armed.

-----------------------------------------------------------------------------
WHAT IS PORTED AND WHAT IS DELIBERATELY STILL A SUBPROCESS
-----------------------------------------------------------------------------
`sweep_campaigns.py` STILL A SUBPROCESS, invoked in the command form its
                      own K=5 ledger licensed and resolved from this file's own
                      location, the way the twin resolved its bash sibling from
                      `SCRIPT_DIR`. It is a separate program with a separate
                      port box and a separate owner; spawning it is what the
                      twin did, and reimplementing its trust rule here would
                      put two copies of a SECURITY decision in the tree that
                      can disagree.
`jq` STILL jq, for both filters. The comment transform's
                      output is a FILE another program reads, so its bytes
                      (jq's two-space pretty printing, its key order, its
                      trailing newline) are part of the interface. A
                      hand-rolled `json.dumps` would produce a different file
                      that happens to parse the same, and any comparison of
                      the intermediate artifacts would then be meaningless.
`gh` STILL `gh`, through a transliteration of `common.sh`'s
                      `_gh_probe`: three attempts, a `log_warn` between them,
                      a 3-then-6-second backoff, JSON validity checked only
                      for the `gh_json` call, and the captured stderr replayed
                      indented four spaces on final failure.

`jq -e` IS NOT `json.loads`, AND THE DIFFERENCE IS A RETRY. `_gh_probe` validates with `jq -e .`, whose exit status is 1 when the LAST OUTPUT VALUE is `null` or `false`. So a `gh` call that exits 0 with the body `null` is classified UNUSABLE and retried three times before the script dies, where a port validating with `json.loads` alone would accept it and write `null` into
`prs.json`. `_json_usable` below implements jq's rule, not Python's.

-----------------------------------------------------------------------------
FILE CREATION ORDER IS OBSERVABLE, AND IT IS BASH'S, NOT THE SCRIPT'S
-----------------------------------------------------------------------------
`gh_json ... >"$WORK/prs.json"` opens and TRUNCATES the target before `gh` runs. When the call then fails after three attempts, the script exits 1 having left an EMPTY `prs.json` behind -- not an absent one. A later step, or a human, that tests for the file's existence sees a different world in each case, so every redirection here is opened at the same point in the sequence the
twin opens it.

-----------------------------------------------------------------------------
THE UNION IS BUILT WITH A LEXICOGRAPHIC SORT, WHICH IS NOT A NUMERIC ONE
-----------------------------------------------------------------------------
`LC_ALL=C sort -u` puts `10` before `9`, and `--out` is therefore in string
order rather than PR order. Preserved: the caller re-dispatches every line and does not care about order, but a port that "fixed" it would change a committed artifact's bytes for no reason. `grep -E '^[0-9]+$'` then drops anything that is not a bare number, which is the last line of defence between a comment body and a dispatch target.

-----------------------------------------------------------------------------
TWO DEFECTS IN THE TWIN, REPRODUCED AND NAMED, both pinned by tests
-----------------------------------------------------------------------------
DEFECT 1: A MALFORMED `prs.json` SCANS ZERO PRS AND STILL SUCCEEDS. The PR number loop reads from a PROCESS SUBSTITUTION (`done < <(jq -r ... )`), whose exit status bash never checks and `pipefail` cannot reach. If that jq fails, the loop body runs zero times, no comment dump is written, the campaign scanner reports no campaigns, and the sweep exits 0 announcing "0 armed PR(s)".
The label-armed half still works, which is what makes it look plausible. `gh_json` validating the body makes this hard to reach today, and "hard to reach" is not
"cannot happen": a body of `{}` parses, satisfies `jq -e`, and then breaks
`.[].number`.

DEFECT 2: `--out` IN AN UNWRITABLE PLACE IS ANNOUNCED AS AN EMPTY SWEEP. The final pipeline carries `|| true`, which swallows a REDIRECTION failure just as happily as `grep`'s no-match exit 1. The count then comes from `$(grep -c . "$OUT" || true)` on a file that does not exist, so the summary
line reads `sweeper:  armed PR(s) = ...` with an empty number where the total
should be. Both halves are reproduced; only bash's own diagnostic text for the failed redirection differs, which the differential compares by shape.

K=5 LEDGER: `.ci/shadow/w7p6-sweep-collect.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "sweep-collect.py"

USAGE = (
    "usage: sweep-collect.sh --repo <owner/name> --label <name> --bot <login> "
    "--work <dir> --out <file>"
)

# `${ARG_LABEL:-autopilot}`.
DEFAULT_LABEL = "autopilot"

# `_gh_probe`'s loop shape (common.sh:434-473).
GH_ATTEMPTS = 3
GH_BACKOFF_SECONDS = 3

# The comment transform, verbatim. `--slurp` wrapped the pages, `.[][]` flattens them back; see the twin's comment on why `--paginate --jq` cannot be used here (the runner's gh refuses `--slurp` with `--jq`, proven live on the first canary dispatch 2026-08-09).
COMMENT_FILTER = "[.[][] | {id, author: .user.login, body}]"

# The PR number extractor for the loop.
NUMBER_FILTER = ".[].number"


def campaign_argv() -> list[str]:
    """The campaign scanner, in the command form its own K=5 ledger licensed.

    ITS BASH TWIN IS GONE (`.ci/shadow/w7p6-sweep-campaigns.observations.jsonl` recorded the port against it five times over, and W7P5 batch M3 deleted it), so the spawn names the port by PATH, the exact spelling that ledger carries. `-m` is deliberately not used: `check:ci-parity`'s tokenizer cannot read it.

    Still SPAWNED rather than imported, for the reason this module's header gives: the trust rule is the product, and it stays in one program with one exit status this one propagates.

    `rediacc_ci.paths.repo_root()` is deliberately not used: it honours `$REDIACC_CI_ROOT`, the twin had no such override, and a fixture that moved one and not the other would diverge for a reason unrelated to this script.
    """
    return [sys.executable, str(pathlib.Path(__file__).resolve().parent / "sweep_campaigns.py")]


def child_env() -> dict[str, str]:
    """This process's environment with `rediacc_ci` importable by the child.

    The parent is reached through `PYTHONPATH=.ci` with the checkout as the working directory, and a child started from anywhere else would not inherit a usable one, so the absolute path is computed here rather than trusted.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(pathlib.Path(__file__).resolve().parents[2])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _json_usable(body: bytes) -> bool:
    """`[[ -n "$out" ]] && jq -e . <<<"$out"`.

    `jq -e` exits 1 when the last output value is `null` or `false`, so those two bodies are UNUSABLE even though they are valid JSON. Anything jq cannot parse at all is unusable too.
    """
    if not body:
        return False
    try:
        value = json.loads(body)
    except ValueError:
        return False
    return value is not None and value is not False


def gh_probe(
    require_json: bool, what: str, args: list[str], *, sleeper=time.sleep
) -> tuple[bool, bytes]:
    """`common.sh`'s `_gh_probe`, transliterated. (ok, stdout bytes).

    BYTES, because `$(...)` is bytes: a comment body is whatever somebody typed. The one transformation bash applies is stripping TRAILING NEWLINES
    from the substitution, which `rstrip(b"\\n")` reproduces; `printf '%s'`
    then writes the result with no newline of its own, which is why every file this script writes through `gh` lacks a final newline.
    """
    rc = 0
    err = b""
    out = b""
    attempt = 1
    while attempt <= GH_ATTEMPTS:
        try:
            proc = subprocess.run(
                ["gh", *args],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            # `gh` missing entirely: bash's command-not-found is 127 with its own message on stderr, which `2>"$err"` captures and the final failure replays.
            rc, out, err = 127, b"", b"gh: command not found\n"
        else:
            rc = proc.returncode
            out = (proc.stdout or b"").rstrip(b"\n")
            err = proc.stderr or b""
        if rc == 0 and (not require_json or _json_usable(out)):
            return True, out
        if attempt < GH_ATTEMPTS:
            log.warn(
                "%s: gh call failed or returned unusable output (attempt %d/3), retrying..."
                % (what, attempt)
            )
            sleeper(attempt * GH_BACKOFF_SECONDS)
        attempt += 1
    log.error("%s: gh failed after %d attempts (last exit %d)." % (what, GH_ATTEMPTS, rc))
    if err:
        # `[[ -s "$err" ]] && sed 's/^/ /' "$err" >&2`: every line, including a trailing empty one, gets the four spaces.
        text = err.decode("utf-8", "replace")
        parts = text.split("\n")
        # GNU sed PRESERVES a missing final newline, so the replay of a stderr that did not end in one does not invent one either.
        incomplete = parts[-1] != ""
        if not incomplete:
            parts.pop()
        for index, line in enumerate(parts):
            tail = "" if incomplete and index == len(parts) - 1 else "\n"
            print("    %s" % line, end=tail, file=sys.stderr)
        sys.stderr.flush()
    return False, b""


def grep_count(path: str) -> str:
    """`$(grep -c . "$path" || true)`: how many NON-EMPTY lines the file has.

    Returns the text the command substitution would capture, so a MISSING file yields the empty string (grep writes its complaint to stderr and prints nothing) rather than a zero. That empty string is defect 2's visible half.
    """
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        print(
            "grep: %s: %s" % (path, os.strerror(exc.errno) if exc.errno else str(exc)),
            file=sys.stderr,
            flush=True,
        )
        return ""
    return str(count_nonempty(data))


def count_nonempty(data: bytes) -> int:
    """`grep -c .`: lines with at least one character.

    A file with no trailing newline still ends in a line, and an empty file has none. `.` does not match a newline, so a line that is only a newline is not counted.
    """
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    return sum(1 for line in lines if line)


def sort_unique(chunks: list[bytes]) -> list[bytes]:
    """`LC_ALL=C sort -u <a> <b>`: byte order, duplicates collapsed.

    LEXICOGRAPHIC, so `10` sorts before `9`. Each input's final unterminated line is still a line, which is exactly the shape `printf '%s'` leaves behind.
    """
    lines: list[bytes] = []
    for chunk in chunks:
        parts = chunk.split(b"\n")
        if parts and parts[-1] == b"":
            parts.pop()
        lines.extend(parts)
    return sorted(set(lines))


def digits_only(lines: list[bytes]) -> list[bytes]:
    """`grep -E '^[0-9]+$'`. The last line of defence before a dispatch."""
    return [line for line in lines if line and all(0x30 <= b <= 0x39 for b in line)]


def _write(path: str, data: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(data)


def main(argv: list[str], *, sleeper=time.sleep) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    repo = args.get("ARG_REPO", "")
    label = args.get("ARG_LABEL") or DEFAULT_LABEL
    bot = args.get("ARG_BOT", "")
    work = args.get("ARG_WORK", "")
    out_path = args.get("ARG_OUT", "")

    if not (repo and bot and work and out_path):
        log.error(USAGE)
        return 2

    comments_dir = "%s/comments" % work
    try:
        os.makedirs(comments_dir, exist_ok=True)
    except OSError as exc:
        # `mkdir -p` failing is a `set -e` exit 1 carrying coreutils' message.
        print(
            "mkdir: cannot create directory '%s': %s"
            % (comments_dir, os.strerror(exc.errno) if exc.errno else str(exc)),
            file=sys.stderr,
            flush=True,
        )
        return 1

    prs_json = "%s/prs.json" % work
    label_armed = "%s/label-armed.txt" % work
    campaign_armed = "%s/campaign-armed.txt" % work

    # Opened and truncated BEFORE the call, as bash does.
    _write(prs_json, b"")
    ok, body = gh_probe(
        True,
        "sweeper open PR list",
        ["pr", "list", "--repo", repo, "--state", "open", "--limit", "50", "--json", "number"],
        sleeper=sleeper,
    )
    if not ok:
        return 1
    _write(prs_json, body)

    _write(label_armed, b"")
    ok, body = gh_probe(
        False,
        "sweeper label-armed list",
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--label",
            label,
            "--state",
            "open",
            "--json",
            "number",
            "--jq",
            ".[].number",
        ],
        sleeper=sleeper,
    )
    if not ok:
        return 1
    _write(label_armed, body)

    # DEFECT 1 lives here: this jq's exit status is discarded by the process substitution, so a `prs.json` that cannot be indexed scans zero PRs and the sweep still succeeds. stderr is INHERITED, matching `<(...)`.
    numbers = (
        subprocess.run(
            ["jq", "-r", NUMBER_FILTER, prs_json],
            stdout=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            check=False,
        ).stdout
        or b""
    )

    for raw in numbers.split(b"\n"):
        if not raw:
            continue  # `[[ -n "$n" ]] || continue`
        number = raw.decode("utf-8", "surrogateescape")
        raw_path = "%s/%s.raw.json" % (comments_dir, number)
        _write(raw_path, b"")
        ok, body = gh_probe(
            False,
            "comments for PR #%s" % number,
            [
                "api",
                "repos/%s/issues/%s/comments" % (repo, number),
                "--paginate",
                "--slurp",
            ],
            sleeper=sleeper,
        )
        if not ok:
            return 1
        _write(raw_path, body)
        with open("%s/%s.json" % (comments_dir, number), "wb") as handle:
            rc = subprocess.run(
                ["jq", COMMENT_FILTER, raw_path],
                stdout=handle,
                stdin=subprocess.DEVNULL,
                check=False,
            ).returncode
        if rc != 0:
            # `set -e`: jq's own message has already reached stderr.
            return rc

    with open(campaign_armed, "wb") as handle:
        rc = subprocess.run(
            [
                *campaign_argv(),
                "--prs",
                prs_json,
                "--comments-dir",
                comments_dir,
                "--bot",
                bot,
            ],
            stdout=handle,
            stdin=subprocess.DEVNULL,
            check=False,
            env=child_env(),
        ).returncode
    if rc != 0:
        return rc

    union = digits_only(
        sort_unique(
            [pathlib.Path(label_armed).read_bytes(), pathlib.Path(campaign_armed).read_bytes()]
        )
    )
    try:
        _write(out_path, b"".join(line + b"\n" for line in union))
    except OSError as exc:
        # DEFECT 2: `|| true` swallows this. bash's diagnostic carries the twin's path and line number; this one carries the same errno.
        print(
            "%s: %s: %s" % (SELF, out_path, os.strerror(exc.errno) if exc.errno else str(exc)),
            file=sys.stderr,
            flush=True,
        )

    log.info(
        "sweeper: %s armed PR(s) = %s label-armed U %s campaign-armed"
        % (grep_count(out_path), grep_count(label_armed), grep_count(campaign_armed))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
