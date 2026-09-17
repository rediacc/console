"""Port of `.ci/scripts/autopilot/compose-prompt.sh`.

Composes one autopilot round's prompt from the trusted template plus the gate's fixtures, writes it to `--out`, and publishes it as a step output.

THE INJECTED BLOCKS ARE THE MODEL'S ONLY STATE CHANNEL, and that is why this script is more than a `cat`. Agent mode inlines no PR text at all (03-v2-autonomy.md wall 1), so everything a round needs rides in this file: the decision, the state comment, the failed-job list, and -- for a review-response round -- the author-filtered review payload the gate built.

A REVIEW ROUND WITH NO PAYLOAD REFUSES, exit 1. The gate treats a failed thread fetch as a warning so one GraphQL hiccup cannot stop fix rounds; the cost of that choice is paid here, where a missing payload would mean answering findings the round never read. Note the ORDER, which the port keeps: the refusal happens AFTER `--out` has already been written with the state and
failed-jobs blocks, so a refused review round still leaves a partial prompt file on disk.

THE HEREDOC DELIMITER IS RANDOM PER RUN, and it is a security control rather than a flourish. The prompt carries review-thread text an outsider can influence by replying into a trusted thread; a FIXED marker appearing in that text would close the `prompt` output early and let the remainder of the comment declare step outputs of its own. The twin draws it from `head -c 16
/dev/urandom | od -An -tx1 | tr -d ' \\n'`, which is 32 lowercase hex characters. This port uses `secrets.token_hex(16)`: same 16 bytes, same alphabet, same length, from the same kernel CSPRNG, without three processes. The differential asserts the SHAPE (prefix plus 32 hex characters) and that two runs differ, because asserting the value would be asserting that a random number
generator repeats itself.

`cat` IS NOT EXECUTED, AND ITS ERRORS ARE REPRODUCED BY HAND. The twin runs five `cat` calls whose failures are load-bearing: `$FX/decision.json` has NO `require_file` in front of it, so a missing decision file is a raw `cat: <path>: No such file or directory` on stderr and a `set -e` exit 1, with `--out` half written. That is a hazard (see below) and reproducing it means
reproducing coreutils' message, which is `cat: %s: %s` with `strerror(errno)` as the tail. Doing that in Python costs one f-string; shelling out to `cat` five times to get it for free would make a pure string-assembly script spawn processes, and would make the port's behaviour depend on which `cat` is on PATH.

THE HAZARD, PRESERVED AND REPORTED, not repaired here. Three of the five inputs are checked and two are not:

  checked      $PROMPTS (require_dir), $FX (require_dir),
               $PROMPTS/$TEMPLATE (require_file)
  UNCHECKED    $FX/decision.json -- `cat` fails, `set -e` exits 1, and the
               message a workflow log shows is coreutils' rather than this
               script's. Every other missing input names itself and says what
               it was for.
  optional     $FX/state.txt, $FX/failed-jobs.txt -- guarded with `[[ -f ]]`
               and genuinely optional.

`decision.json` reads like the one fixture that must exist, so the asymmetry is almost certainly an oversight rather than a decision; fixing it means editing a live workflow step, which is the cutover box's call, not this one's.

BASH REDIRECTION FAILURE IS A DIVERGENCE IN TEXT ONLY. `>"$OUT"` into a nonexistent directory is a bash diagnostic carrying the twin's path and line number; this port opens the same file at the same point (before any content is produced, because bash sets up a group's redirection before running the group) and reports the same errno with the same exit code 1.

K=5 LEDGER: `.ci/shadow/w7p6-compose-prompt.observations.jsonl`.
"""

from __future__ import annotations

import os
import secrets
import sys

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "compose-prompt.py"

USAGE = (
    "usage: compose-prompt.sh --prompts <dir> --fx <dir> --template <file> "
    "--mode <mode> --out <file>"
)

# The mode that requires a review payload. One name, one place; the twin compares the literal in two spots and this port compares it in one.
REVIEW_MODE = "review-response"

# The `prompt` heredoc marker's fixed half. The random half is appended per run.
DELIM_PREFIX = "AUTOPILOT_PROMPT_EOF_"

# Bytes of entropy in the random half. 16 bytes -> 32 hex characters, matching `head -c 16 /dev/urandom`.
DELIM_BYTES = 16


def delimiter() -> str:
    """`AUTOPILOT_PROMPT_EOF_<32 lowercase hex>`, fresh every call."""
    return DELIM_PREFIX + secrets.token_hex(DELIM_BYTES)


def _cat(path: str) -> bytes:
    """`cat "$path"` -- the bytes, or coreutils' own error and exit 1.

    BYTES, NOT TEXT, throughout the composition. A prompt carries review-thread text written by whoever replied to the thread, so it can hold anything a UTF-8 decoder objects to. `cat` does not decode, and a port that did would fail a round on a stray byte the twin passed through untouched.
    """
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
        raise common.RefusalError(
            "cat: %s: %s" % (path, os.strerror(exc.errno) if exc.errno else str(exc)),
            code=1,
        ) from exc


def compose_chunks(prompts: str, fx: str, template: str):
    """The main block, YIELDED PIECE BY PIECE in the twin's order.

    A GENERATOR RATHER THAN ONE RETURNED BUFFER, and the differential is what
    made that necessary rather than a preference. `{ cat a; printf x; cat b; }
    >"$OUT"` writes each command's output to the file AS IT RUNS, so when `cat "$FX/decision.json"` fails the file already holds the template and the opening `<autopilot_state>` tag. The first version of this port composed the whole thing in memory and wrote once at the end, which left a ZERO-BYTE `--out` on that path; `test_missing_inputs` caught it on the first run. The partial
    file is not cosmetic: a workflow step that inspects `--out` after a failed compose sees what the twin left, and a port that truncates it changes what that step reads.

    PATHS ARE CONCATENATED, NOT `os.path.join`-ed, and that is deliberate: `"$PROMPTS/$TEMPLATE"` in bash always glues the two with a slash, while `os.path.join(prompts, template)` DISCARDS `prompts` entirely when `template` is absolute. `--template /etc/passwd` would therefore read a different file in the port than in the twin, which is a sandbox escape a reader would never spot
    in a helper call.

    Reproduces `{ cat template; printf ...; cat decision; [-f] cat state; ... }`
    exactly, including the two `printf '\\n<tag>\\n'` forms that put a BLANK LINE before `<autopilot_state>` and `<failed_jobs>` but not before the closing tags. That asymmetry is in the twin's printf strings and is preserved literally rather than tidied, because the template's trailing newline (or absence of one) plus these leading newlines is what the model actually sees.
    """
    yield _cat("%s/%s" % (prompts, template))
    yield b"\n<autopilot_state>\n"
    yield _cat("%s/decision.json" % fx)
    state = "%s/state.txt" % fx
    if os.path.isfile(state):
        yield _cat(state)
    yield b"</autopilot_state>\n"
    yield b"\n<failed_jobs>\n"
    failed = "%s/failed-jobs.txt" % fx
    if os.path.isfile(failed):
        yield _cat(failed)
    yield b"</failed_jobs>\n"


def compose(prompts: str, fx: str, template: str) -> bytes:
    """`compose_chunks` joined. For a caller that wants the whole block and has no file to stream it into, which is the pure-helper case the selftest and `test_pure_helpers_are_exercised_directly` drive."""
    return b"".join(compose_chunks(prompts, fx, template))


def review_block(fx: str) -> bytes:
    """The `<review_payload>` block appended for a review-response round.

    Note the leading newline INSIDE the closing tag's printf (`printf '\\n</review_payload>\\n'`): the payload is JSON with no trailing newline of its own, so without it the closing tag would sit on the same line as the final brace.
    """
    return b"\n<review_payload>\n" + _cat("%s/review-payload.json" % fx) + b"\n</review_payload>\n"


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        # QUIRK 3 of the twin's parse_args: `printf -v` refuses a key that is not a valid shell identifier and takes the script down with exit 2.
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    prompts = args.get("ARG_PROMPTS", "")
    fx = args.get("ARG_FX", "")
    template = args.get("ARG_TEMPLATE", "")
    mode = args.get("ARG_MODE", "")
    out_path = args.get("ARG_OUT", "")

    if not (prompts and fx and template and mode and out_path):
        log.error(USAGE)
        return 2

    try:
        common.require_dir(prompts)
        common.require_dir(fx)
        common.require_file("%s/%s" % (prompts, template))
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    # OPENED BEFORE ANYTHING IS COMPOSED, matching bash: a group's redirection is established before the group runs, so an unwritable `--out` fails first and `cat` never runs. The OSError arm therefore covers BOTH the open and every write, which is right: bash reports a redirection failure and a write failure the same way, with the same exit code.
    try:
        with open(out_path, "wb") as handle:
            try:
                for chunk in compose_chunks(prompts, fx, template):
                    handle.write(chunk)
                    # FLUSHED PER CHUNK, matching a fresh `cat` process per input: the bytes must be on the fd before the NEXT input gets a chance to fail.
                    handle.flush()
            except common.RefusalError as exc:
                # `cat`'s own message, on stderr, exit 1, with the file left exactly as far along as bash would have left it. Nothing is cleaned up, on purpose: the twin leaves the partial file too, and a port that deleted it would hide the evidence.
                print(exc.lines[0], file=sys.stderr, flush=True)
                return exc.code
    except OSError as exc:
        print(
            "%s: %s: %s" % (SELF, out_path, os.strerror(exc.errno) if exc.errno else str(exc)),
            file=sys.stderr,
            flush=True,
        )
        return 1

    if mode == REVIEW_MODE:
        payload = "%s/review-payload.json" % fx
        # `[[ ! -s ... ]]`: missing OR empty. An empty payload file is the shape a failed fetch leaves behind, so size is the right test, not existence.
        if not (os.path.isfile(payload) and os.path.getsize(payload) > 0):
            log.error(
                "review-response round with no review payload fixture at %s; "
                "refusing to run a review round blind" % payload
            )
            return 1
        try:
            with open(out_path, "ab") as fh:
                fh.write(review_block(fx))
        except common.RefusalError as exc:
            print(exc.lines[0], file=sys.stderr, flush=True)
            return exc.code
        except OSError as exc:
            print(
                "%s: %s: %s" % (SELF, out_path, os.strerror(exc.errno) if exc.errno else str(exc)),
                file=sys.stderr,
                flush=True,
            )
            return 1

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        delim = delimiter()
        body = _cat(out_path)
        with open(github_output, "ab") as fh:
            fh.write(("prompt<<%s\n" % delim).encode("utf-8"))
            fh.write(body)
            fh.write(("%s\n" % delim).encode("utf-8"))

    size = os.path.getsize(out_path)
    log.info("composed the %s prompt (%d bytes) from %s" % (mode, size, template))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
