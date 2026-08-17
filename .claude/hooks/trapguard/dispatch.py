#!/usr/bin/env python3
"""trapguard: the PostToolUse surface for misread-outcome traps.

Two modes. `--posttool` is the live one, running the misread-outcome rules below.
`--probe-payload` is a retired diagnostic, kept because the next rule that wants
a payload field should re-run it rather than trust this docstring.

THE PROBE CAME FIRST, AND THAT ORDER WAS THE POINT. No hook in this repo had ever
read `tool_response`; the only evidence it arrives was a docstring
(`wl_wait.py:139-143`) recording a payload someone captured. That is a ruling
from an artifact, which is itself a trap in this corpus, so it was probed before
anything depended on it (plan section 7.1). Writing the rules first would have
been building a check on an unverified payload shape, which is how a check that
cannot fire ships believing it works.

WHAT THE PROBE ANSWERED, on real payloads, 2026-08-09: the field arrives as a
dict; a planted nonce reached the hook, so it carries actual output rather than
merely existing; and hooks fire for subagents. It also corrected that docstring
twice -- `isImage` and `noOutputExpected` were undocumented, and `agent_id` and
`agent_type` are ABSENT on main-loop calls, appearing only for subagents, so a
rule keyed on them would have silently never matched in the main loop.

WHAT THE PROBE RECORDS, AND WHAT IT REFUSES TO. Key names, lengths and booleans
only. No tool output is ever written to disk: a hook that logged tool responses
would be a durable copy of everything every session reads. The single exception
is a nonce planted deliberately, matched by pattern rather than stored. It is
unregistered in settings.json; a diagnostic on every tool call is a standing cost.

NEVER FAILS A TOOL CALL. PostToolUse runs after the tool has already executed, so
nothing here can deny anything, and a hook that broke a session's turn because a
log directory was read-only would be a self-inflicted outage. Every path exits 0.
"""

import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

# The only string this file ever matches. Planted by hand to prove that stdout
# genuinely reaches the hook (assertion P2), not merely that a key named
# tool_response exists (assertion P1). The two are different claims and the
# whole tier depends on the second one.
NONCE_RE = re.compile(r"trapguard-probe-[0-9a-zA-Z]+")

PROBE_PATH = pathlib.Path(
    os.environ.get("TRAPGUARD_PROBE_PATH")
    or (pathlib.Path.home() / ".claude" / "trapguard" / "probe.jsonl")
)


def _response_facts(resp):
    """(type-name, length, key-names) for whatever tool_response turned out to be.

    Written to survive being wrong about the shape, because being wrong about the
    shape is precisely what the probe exists to discover. A dict, a string, a
    list and an absent field each answer differently rather than raising.
    """
    if resp is None:
        return "absent", 0, []
    if isinstance(resp, dict):
        try:
            length = len(json.dumps(resp))
        except (TypeError, ValueError):
            length = -1
        return "dict", length, sorted(str(k) for k in resp)
    if isinstance(resp, str):
        return "str", len(resp), []
    if isinstance(resp, list):
        return "list", len(resp), []
    return type(resp).__name__, -1, []


# ---- the misread-outcome rules ----------------------------------------------
#
# These read `tool_response` and INJECT context; they cannot deny, because the
# command already ran. That is the correct semantics: in both traps below the
# command was fine and only the READING of its output was wrong, which is
# exactly the failure no other surface can catch. A CI gate is far too late and
# a PreToolUse hook is too early: at request time neither trap is visible.
#
# Each rule is (applies, verdict). `applies` narrows on the command so the
# response is not scanned for every tool call; `verdict` keys on the RESPONSE,
# never on the command alone, because a command is not wrong here, an inference
# from its output is.

STAT_DELETIONS = re.compile(r"(\d+) deletions?\(-\)")
STAT_INSERTIONS = re.compile(r"(\d+) insertions?\(\+\)")
# ` path/to/file.py | 462 ------` and `--- a/path`, the two shapes git uses.
STAT_PATH = re.compile(r"^\s*(\S+)\s*\|\s*\d+", re.MULTILINE)
DIFF_PATH = re.compile(r"^(?:---|\+\+\+) [ab]/(\S+)", re.MULTILINE)


def _response_text(resp):
    """Whatever the tool printed, as one string, without caring about shape.

    The probe established tool_response is a dict of stdout/stderr/interrupted/
    isImage/noOutputExpected, but this stays shape-tolerant on purpose: the
    payload gained two keys nobody had documented, so assuming today's exact
    shape is how a rule silently stops matching after a harness update.
    """
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        return "\n".join(str(resp.get(k) or "") for k in ("stdout", "stderr"))
    return ""


def rule_cancelled_run_not_passed(cmd, out, _root, _resp):
    """A cancelled run is not a passed run.

    Corpus entry: docs/agent-reference/TRAPS.md, "A cancelled run is not a
    passed run, and it is not a failed one either". Cited by HEADING rather
    than by line: the two trap corpora were merged into that one file, so every
    line number in it moved, and a citation that silently drifts one entry over
    is worse than none.

    Cost when missed: three consecutive CI rounds that measured nothing while
    being counted as "did not recur". The watchdog cancels siblings on the first
    real failure, so a job that never ran looks identical to a job that passed
    in every run-level summary.
    """
    if not re.search(r"gh\s+run\b|actions/runs|actions/jobs", cmd):
        return None

    # TWO SHAPES, and the second one was DEAD CODE until review caught it. The
    # first version gated everything behind "the word cancelled appears in the
    # output", then checked the empty-failure-filter case behind that gate. But
    # a `--jq select(.conclusion=="failure")` query that comes back `[]`
    # BECAUSE the job was cancelled rather than failed contains no such word by
    # construction: the filter removed it. So the branch could never be reached
    # for the case it existed to catch, and once the gate passed it could not
    # change the verdict either. A documented detection shape that cannot fire,
    # inside the change whose whole subject is checks that cannot fire.
    #
    # They are now independent alternatives, which is what they always were.
    # A COUNT of zero cancelled jobs is the OPPOSITE of this trap: it is a session
    # performing exactly the check this rule asks for and finding nothing. Observed
    # live within the hour, warning about output that read `cancelled=0`. Strip the
    # zero-count shapes before deciding, so the rule stays quiet on the good
    # behaviour it exists to encourage. A real `"conclusion":"cancelled"` survives.
    counted_zero = re.sub(r"cancelled\W{0,4}0\b", "", out, flags=re.IGNORECASE)
    saw_cancelled = bool(re.search(r"cancelled", counted_zero, re.IGNORECASE))
    empty_failure_filter = bool(
        re.search(r'conclusion\s*==\s*["\']?failure', cmd)
        and re.search(r"^\[\s*\]$|^\s*$", out.strip())
    )
    if not (saw_cancelled or empty_failure_filter):
        return None
    if empty_failure_filter and not saw_cancelled:
        return (
            "trapguard[cancelled-run-not-passed]: this query filtered for "
            "conclusion==failure and came back EMPTY, which is not the same as "
            "nothing being wrong. A job the watchdog CANCELLED has no failure "
            "conclusion, so it is invisible to this filter while still being a "
            "gate that did not report. Count the cancelled jobs before reading "
            "an empty failure list as a clean run."
        )
    return (
        "trapguard[cancelled-run-not-passed]: this output contains a CANCELLED "
        "conclusion. A cancelled job did not pass, it did not run, and in a run "
        "summary the two look identical. Distinguish the two shapes before "
        "concluding anything: cancelled siblings WITH a failed job means the "
        "watchdog killed the run for that failure, while cancelled with ZERO "
        "failures and a newer commit means the run was superseded. Read the "
        "JOB's own conclusion rather than the run's, and treat a job that was "
        "cancelled as a gate that did not report."
    )


def rule_phantom_deletion_diff(cmd, out, root, _resp):
    """An all-deletions diff for a file that is still on disk.

    Corpus entry: docs/agent-reference/TRAPS.md, "`git diff <branch>` reads as
    DELETED for a file the worktree never tracked". By heading, not line, for
    the reason given on rule_cancelled_run_not_passed above.

    Observed 2026-08-09: an intact 462-line wl_checklist.py printed
    `1 file changed, 462 deletions(-)` because the branch was built with git
    plumbing, so the file was untracked relative to HEAD and absent from the
    index git compares against. The reflex read is that a sub-agent deleted it,
    and the near-miss is a destructive repair of a file that was never damaged.

    TWO TESTS, AND THE FIRST ONE ALONE WAS WRONG. This rule briefly shipped
    keyed on "the file still exists", which fires on ANY deletions-only change
    to a tracked file. It false-positived within the hour on
    `git diff --stat package-lock.json`, a peer's ordinary 27-line removal. A
    rule that fires on common, correct shapes trains sessions to discount it,
    which is worse than not having it.

    Existence narrows; TRACKED-NESS decides. The phantom exists because the file
    is untracked relative to HEAD, so git compares against an index with no
    entry for it and calls the whole thing removed. A tracked file losing lines
    is just a diff. Cost is one stat plus one `git ls-files` per named path, and
    if git cannot answer the rule stays silent rather than guessing.
    """
    if not re.search(r"\bgit\s+(-[A-Za-z-]+\s+\S+\s+)*diff\b", cmd):
        return None
    if re.search(r"--cached|--staged", cmd):
        return None
    if not STAT_DELETIONS.search(out) or STAT_INSERTIONS.search(out):
        return None
    paths = set(STAT_PATH.findall(out)) | set(DIFF_PATH.findall(out))
    alive = [p for p in paths if p not in ("a", "b") and (pathlib.Path(root) / p).exists()]
    if not alive:
        return None
    # EXISTS-ON-DISK IS NOT ENOUGH, and this rule shipped briefly believing it was.
    # It fired on `git diff --stat package-lock.json` for a tracked file a peer had
    # simply removed lines from: deletions, no insertions, file obviously present.
    # Any deletions-only change to a tracked file looks like that, which is common,
    # and a rule that fires on ordinary shapes teaches sessions to ignore it -- the
    # precision decay the plan names as this tier's main risk.
    #
    # The real discriminator is TRACKED-NESS. The phantom happens because the file
    # is untracked relative to HEAD, so git compares against an index that has no
    # entry and reports the whole file as removed. A tracked file losing lines is
    # just a diff. `git ls-files --error-unmatch` answers exactly that question.
    untracked = []
    for p in alive:
        try:
            rc = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", p],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            ).returncode
        except (OSError, subprocess.SubprocessError):
            return None  # cannot tell: stay silent rather than cry wolf
        if rc != 0:
            untracked.append(p)
    if not untracked:
        return None
    alive = untracked
    return (
        "trapguard[phantom-deletion-diff]: this diff reports deletions and no "
        "insertions, but %s still exist(s) on disk. Before concluding anything "
        "was deleted: `git diff <commit>` compares against the INDEX, so a file "
        "that is untracked relative to HEAD reads as fully deleted while sitting "
        "intact in the worktree. This is the normal state for a branch built "
        "with git plumbing. Ask the content, not the index: "
        "`git show <branch>:<path> | diff - <path>`." % ", ".join(sorted(alive)[:3])
    )


# The tail steps that exist to undo an earlier one. Deliberately a short, named
# set rather than "anything destructive": the rule must stay quiet on ordinary
# interrupted commands, and every entry here is a shape whose whole purpose is
# putting something back.
RESTORE_TAIL = re.compile(
    r"\bcp\b[^\n;&|]*\.(?:orig|bak|prev|save)\b"
    r"|\bmv\b[^\n;&|]*\.(?:orig|bak|prev|save)\b"
    r"|\bgit\s+(?:checkout|restore)\b"
    r"|\bgit\s+stash\s+pop\b"
    r"|\bunset\b[^\n;&|]*(?:MUTAT|TRAPGUARD)",
    re.IGNORECASE,
)


def rule_interrupted_cleanup_skipped(cmd, out, _root, resp):
    """A killed command did not run its own cleanup (this session, 2026-08-09).

    The output of an interrupted command is a truthful account of a partial run,
    which is exactly what makes it dangerous: it ends mid-script, having printed
    a restore step that may never have run.

    Paid for immediately, in the session that wrote the other two rules: a
    mutation test neutered a guard in the live tree, ran the suite, and restored
    it on the next line. The suite outlived the 2-minute tool timeout, the whole
    command took SIGTERM, and the restore never happened. What came back was
    `mutated: guard neutered` and a truncated log -- output that reads like a
    completed step, because every line it printed was true. The tree sat with a
    disabled guard in it.

    Why this is a hook and not a note: the failure is invisible at exactly the
    moment you are reading output, which is the faculty that already failed. The
    two conditions are independent alternatives on purpose, since the harness
    reports a kill through `interrupted` on some paths and through the timeout
    text on others, and gating either behind the other is how the sibling rule
    above ended up with a branch that could not fire.
    """
    killed = bool(resp.get("interrupted")) if isinstance(resp, dict) else False
    timed_out = bool(re.search(r"timed out after|Exit code 143|\bSIGTERM\b", out))
    if not (killed or timed_out):
        return None
    # Only worth a word if a LATER step was supposed to undo an earlier one. The
    # first statement cannot be a tail, so a bare `git restore ...` that was
    # itself the interrupted command is not this shape.
    first_sep = re.search(r";|&&|\|\||\n", cmd)
    if not first_sep:
        return None
    tail = cmd[first_sep.end() :]
    m = RESTORE_TAIL.search(tail)
    if not m:
        return None
    return (
        "trapguard[interrupted-cleanup-skipped]: this command was KILLED, and a "
        "later step in it looks like a restore (%r). A kill does not run the rest "
        "of the script, so whatever an earlier step moved, mutated or disabled is "
        "very likely still that way -- while the output you just read is a "
        "truthful, complete-looking account of the part that DID run. Check the "
        "state the restore was meant to return to before trusting anything here, "
        "and prefer mutating a sandbox copy over the live tree so a kill can "
        "strand nothing." % m.group(0).strip()[:60]
    )


RULES = (
    rule_cancelled_run_not_passed,
    rule_phantom_deletion_diff,
    rule_interrupted_cleanup_skipped,
)


def run_posttool():
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 -- a warning layer must never break a turn
        return 0
    if not isinstance(event, dict):
        return 0
    cmd = ""
    ti = event.get("tool_input")
    if isinstance(ti, dict):
        cmd = str(ti.get("command") or "")
    if not cmd:
        return 0
    resp = event.get("tool_response")
    out = _response_text(resp)
    root = event.get("cwd") or os.getcwd()
    notes = []
    for rule in RULES:
        try:
            note = rule(cmd, out, root, resp)
        except Exception:  # noqa: BLE001 -- one broken rule must not silence the others
            note = None
        if note:
            notes.append(note)
    if not notes:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "\n\n".join(notes),
                }
            }
        )
    )
    return 0


def main():
    if "--posttool" in sys.argv[1:]:
        return run_posttool()
    if "--probe-payload" not in sys.argv[1:]:
        return 0
    try:
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001 -- a probe must never break a turn
        return 0
    try:
        event = json.loads(raw) if raw.strip() else {}
    except ValueError:
        # An unparseable payload is itself a finding, so it is recorded rather
        # than dropped: "the field never arrived" and "the whole event was
        # malformed" are different answers to P1.
        event = {"__unparseable__": True}

    resp = event.get("tool_response")
    rtype, rlen, rkeys = _response_facts(resp)

    # The nonce is matched against the RAW event text, so it is found wherever
    # the harness happens to put stdout inside tool_response. Matching a parsed
    # sub-field would make a negative result ambiguous between "no content" and
    # "content lives somewhere I did not look".
    row = {
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_name": str(event.get("tool_name") or ""),
        "payload_keys": sorted(str(k) for k in event) if isinstance(event, dict) else [],
        "response_type": rtype,
        "response_len": rlen,
        "response_keys": rkeys,
        "nonce_found": bool(NONCE_RE.search(raw)),
        "agent_id": "present" if event.get("agent_id") else "absent",
        "agent_type": str(event.get("agent_type") or ""),
    }
    try:
        PROBE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PROBE_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
