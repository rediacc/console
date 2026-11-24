"""The edit/shell write rules: one row per protected write, read by both chains (PLAN-tooling-code-reduction CR5, D5).

WHY ONE TABLE. Six policies are enforced twice, once per tool surface: the Edit/Write/MultiEdit/NotebookEdit half on `pre-edit` and the Bash half on `pre-bash`. A guard declares one chain, so each policy is two modules, and before this table each pair kept its own copy of the path pattern, the refusal text and the sanctioned writer. A copy edited on one side only is a
policy that differs by tool. Each row below is the single declaration both halves read:

    id          the policy, named after its pair
    path        the landing test, a compiled pattern over the path a write lands on
    passes      the edit tools the edit half lets through (None: none, every write tool is judged)
    exempt      a landing the policy leaves alone although `path` matches it
    message     the edit half's refusal and the shell half's, (edit, shell)
    sanctioned  the one writer the refusal points at

Three rows are judged by path alone (review_file, live_proof_ledger, roundlog): their edit half is one `edit_run(ev, RULE)` call and nothing else (the round log's passes `exists_only=True, raw=False`, the two options its own reading needs). Three judge the CONTENT a write leaves (user_only_command, suppressions, protected_files), so their row carries `path=None` and their predicate stays in the guard, where its DEFECT plant reaches it; the row still names the pair and its
sanctioned door, so `ROWS` enumerates every twin.

THE SHELL HALVES READ THE SAME ROW. A shell half binds the row's landing test and its shell message, and asks the test of each word it reads as a write target. The walk itself is `shellscan.event_write_records(ev)` (`shellscan.write_records`, made once per Event: each write's path, reading, word, run, argv index and append flag), which block_live_proof_ledger_shell_write reads for every shell shape but interpreter code, and block_suppressions_shell_write and block_user_only_command_shell_write for their word writes; each guard keeps the
readings the walk does not make or makes too loosely for it (a Python program judged by scope, a listing that feeds review paths, a copy whose source is read from disk), and a guard adopting `writes` proves the swap with a side-by-side probe of its old and new copies, not with its suite alone: the ledger suite stayed green while `F=<ledger>; touch $F` was lost.

THE PLANTS STAY IN THE GUARDS. `check:ci-guard-mutations` plants a guard's DEFECT into a scratch copy of the GUARD's source, so a predicate living here would be unplantable. An edit half binds its row in one line (`RULE = _write_rules.ROWS[...]`) and its DEFECT swaps that row for `NOTHING`, the row no path matches: with it every write passes, which the suite must catch.

SHARED HELPERS. `result_text` (the text an edit leaves, formerly copied into three guards), `literals` and `code_writes_through_disk` (formerly copied into the review-file and user-only shell halves). Each guard keeps its own `_LITERAL` compile, because check:ci-guard-mention-anchoring declares that pattern per guard file.
"""

import os
import re
from typing import NamedTuple

from rediacc_hooks import hookio, shellscan

EDIT_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")


class Rule(NamedTuple):
    id: str
    path: "re.Pattern[str] | None"
    passes: "tuple[str, ...] | None"
    exempt: "re.Pattern[str] | None"
    message: "tuple[str, str]"
    sanctioned: str


_REVIEW_BODY = (
    "\n"
    "Review files are written by the reviewer and closed only through the verb, which checks\n"
    "the fix before it records it. A hand edit is how a high finding disappears without a fix.\n"
    "\n"
    "  close a finding:  .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> fixed <sha>\n"
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> not-a-bug <evidence path:line>\n"
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> waived #<item> ASKED:<YYYY-MM-DDTHH:MM>Z\n"
    "  re-review:        python3 .claude/hooks/stop/wl_review.py --run <sha> --branch <branch>\n"
)

LEDGER_RECORDER = "PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record --plan <rel> --box <sig> --target bench|hostinger --check <id> --write"

_LEDGER_BODY = (
    "\n"
    "CI trusts agent/ledgers/live-proof.jsonl without re-running anything, so a row is written\n"
    "only by the recorder, after the live run it describes; a hand-written row with a recomputed\n"
    "id is the forgery this guard exists to stop.\n"
    "\n"
    "  record a receipt:  " + LEDGER_RECORDER + "\n"
    "  judge the ledger:  PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify\n"
)

_ROUNDLOG_EDIT = (
    "❌ BLOCKED: a whole-file write to a pr-babysit round log. Its STATUS block is spliced "
    "in place, and the obvious splice (text[:i] + new) deletes the entire round history "
    "below it -- which is what happened on 2026-08-19, silently, to a file with no backup. "
    "To refresh STATUS use the verb, which replaces ONLY that block and reports the bytes "
    "it kept above and below:  .claude/hooks/stop/worklist.py --roundlog <branch> <<'EOF' "
    "... EOF   The tool writes the '## STATUS (round N, <utc>)' heading itself: the round "
    "auto-increments, and the stamp is machine-written because a watchdog reads it to "
    "decide whether this loop is wedged. To append to the history or amend the wave "
    "header, use Edit -- targeted edits are deliberately allowed, because they cannot "
    "swallow an appendix they never named."
)

_ROUNDLOG_SHELL = (
    "❌ BLOCKED: this Bash command can replace a pr-babysit round log wholesale. That is "
    "how the round history was destroyed on 2026-08-19: a python heredoc doing "
    "p.write_text(s[:i] + new), which replaces from the STATUS heading to END OF FILE and "
    "takes the entire appendix with it, silently, on a file with no backup. To refresh "
    "STATUS use the verb, which replaces ONLY that block and prints the bytes it kept "
    "above and below:  .claude/hooks/stop/worklist.py --roundlog <branch> <<'EOF' ... EOF   "
    "To add to the history appendix, append instead ('>>' and 'tee -a' are deliberately "
    "allowed, since they cannot truncate). To amend the wave header, use the Edit tool -- "
    "targeted edits are allowed for the same reason."
)

ROWS = {
    "review_file": Rule(
        id="review_file",
        path=re.compile(r"(\A|/)agent/reviews/"),
        passes=None,
        exempt=None,
        message=(
            "BLOCKED: %s of a per-commit review record (%s).\n" + _REVIEW_BODY,
            "BLOCKED: this command writes a per-commit review record by hand (%s).\n"
            + _REVIEW_BODY
            + "  record them:      .claude/hooks/stop/worklist.py --review-commit <me>\n",
        ),
        sanctioned="wl_review.py, worklist.py --review-mark/--review-commit/--review-run",
    ),
    "live_proof_ledger": Rule(
        id="live_proof_ledger",
        path=re.compile(r"(\A|/)agent/ledgers/live-proof\.jsonl\Z"),
        passes=None,
        exempt=None,
        message=(
            "BLOCKED: %s of the live-proof ledger (%s).\n" + _LEDGER_BODY,
            "BLOCKED: this command writes the live-proof ledger by hand (%s).\n" + _LEDGER_BODY,
        ),
        sanctioned=LEDGER_RECORDER,
    ),
    "roundlog": Rule(
        id="roundlog",
        path=re.compile(r"(\A|/)reports/pr-babysit-[^/]+\.md\Z"),
        # Targeted edits cannot silently truncate; only whole-file writes can.
        passes=("Edit", "MultiEdit"),
        exempt=re.compile(r"-briefing\.md\Z"),
        message=(_ROUNDLOG_EDIT, _ROUNDLOG_SHELL),
        sanctioned=".claude/hooks/stop/worklist.py --roundlog <branch>",
    ),
    "user_only_command": Rule(
        id="user_only_command",
        path=None,
        passes=None,
        exempt=None,
        message=("", ""),
        sanctioned="the operator's own `!` command (model-invocation-exceptions.json)",
    ),
    "suppressions": Rule(
        id="suppressions",
        path=None,
        passes=None,
        exempt=None,
        message=("", ""),
        sanctioned="a per-file entry in the linter's own config, carrying a BLOCKER: reason",
    ),
    "protected_files": Rule(
        id="protected_files",
        path=None,
        passes=None,
        exempt=None,
        message=("", ""),
        sanctioned="the operator's own `!` command",
    ),
}

# The row no landing matches: an edit half's DEFECT binds it in place of the guard's own row.
NOTHING = Rule(
    id="nothing",
    path=re.compile(r"(?!)"),
    passes=None,
    exempt=None,
    message=("", ""),
    sanctioned="",
)


def edit_landing(ev):
    """`(absolute, judged, shown)` for the file an edit tool was handed, or None for a payload naming none."""
    given = ev.first(("tool_input", "file_path"), ("tool_input", "notebook_path"))
    if not given or given == "null":
        return None
    # Judged where the write LANDS (`hookio.landing`, the one reading every pre-edit guard shares, 9c6817f3.8): a symlink into the directory, or `x/../`, is judged where the kernel puts it.
    return hookio.landing(given, ev.field("cwd") or None)


def matches(rule, landing):
    """Does the row's landing test hold for either form of `landing` (absolute, or relative to the checkout), the row's exemption aside?"""
    if rule.path is None:
        return False
    absolute, judged, _shown = landing
    forms = [f for f in (judged, absolute) if f]
    if not any(rule.path.search(f) for f in forms):
        return False
    return not (rule.exempt is not None and any(rule.exempt.search(f) for f in forms))


def edit_run(ev, rule, exists_only=False, raw=True):
    """The whole edit half of a path-judged row: refuse a write that lands on the row's path, unless its tool is one the row passes. `exists_only` passes a write that CREATES the file (the round log's contract: the verb cannot create one, so the first write must be a tool write). `raw` sends the row's edit message through `warn_raw` with the tool and the shown path filled in; the round log's message is a fixed sentence sent through `warn`."""
    landing = edit_landing(ev)
    if landing is None:
        return hookio.ALLOW
    tool = ev.field("tool_name")
    if rule.passes is not None and hookio.case_glob(tool, *rule.passes):
        return hookio.ALLOW
    if not matches(rule, landing):
        return hookio.ALLOW
    if exists_only and not os.path.exists(landing[0]):
        return hookio.ALLOW
    if raw:
        ev.warn_raw(rule.message[0] % (tool or "a write", landing[2]))
    else:
        ev.warn(rule.message[0])
    return hookio.DENY


def result_text(doc, path):
    """`(text, why)`: the text the edit call would leave at `path`, or `(None, why)` when the call fails on its own and there is nothing to judge.

    Read the way the tools apply it: a Write's `content`, a NotebookEdit's `new_source`, else each `old_string` replaced in order (all of them under `replace_all`), and an `old_string` that is absent fails the whole call.
    """
    tin = doc.get("tool_input") or {}
    if not isinstance(tin, dict):
        return None, "no tool_input"
    if doc.get("tool_name") == "NotebookEdit":
        return str(tin.get("new_source") or ""), ""
    if "content" in tin:
        return str(tin.get("content") or ""), ""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, "the file does not exist, so the Edit fails on its own"
    edits = tin.get("edits")
    if not isinstance(edits, list):
        edits = [tin]
    for edit in edits:
        if not isinstance(edit, dict):
            return None, "an edit is not an object"
        old = str(edit.get("old_string") or "")
        new = str(edit.get("new_string") or "")
        if not old or old not in text:
            return None, "old_string is absent, so the Edit fails on its own"
        text = text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)
    return text, ""


def literals(text, pattern):
    """Every quoted string literal `pattern` finds in `text` (its first non-empty group), unescaped no further."""
    for m in pattern.finditer(text):
        yield next(g for g in m.groups() if g is not None)


def code_writes_through_disk(code, *, spells, lands, write_code, literal, program=None):
    """Interpreter code that writes, through a link, to a guarded path its text never spells: `open('lnk/x.md','w')` with `lnk` a link into the guarded directory (reviews 84fdeff8.1, 84fdeff8.2). A literal `spells` names is the precise readings' to judge; one that `lands` in the guarded place on disk is this reading's. `shellscan.code_writes_through_disk` does the walk."""
    return shellscan.code_writes_through_disk(
        code,
        lambda value: isinstance(value, str) and not spells(value) and lands(value),
        write_code,
        literal,
        program,
    )
