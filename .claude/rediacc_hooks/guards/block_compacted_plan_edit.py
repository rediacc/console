"""Deny a tool edit that would rewrite the SPINE of a compacted plan record.

WHY THIS EXISTS. `agent/PLAN-*.md` files can be COMPACTED (W12,
.claude/hooks/stop/wl_planrec.py): the file keeps its path, so the 2,539
citations of those paths still resolve, and its full text moves into a git
BLOB. The header then carries the only pointer back to that text:

    Status: compacted
    Full-Text: <sha9> <path>
    Full-Text-Blob: <40 hex>
    Record-Sig: <8 hex>

Rewrite that header by hand and the pointer is gone. Nothing errors. The file
still looks like a document, `git show` on the old blob still works for
whoever remembers the id, and nobody does -- so the plan's full text becomes
unreachable in practice while the record goes on advertising a recovery
command that returns nothing. That is strictly worse than the deletion this
whole mechanism exists to avoid: a deleted plan announces its own absence.

WHY A GUARD AND NOT A GATE ALONE. check:ci-plan-record already catches a
broken pointer, and catching it in CI is a round trip AFTER the plan text is
only in an object nobody can name any more. The blob is still reachable at
that point -- `git log --find-object` will find it if you know to look -- but
the session that made the edit has moved on, and the next reader inherits a
file whose header is self-consistent and wrong. The cheap moment to refuse is
the edit.

WHY IT DENIES THE SPINE AND NOT THE WHOLE FILE, which was the first design and
was wrong. A record is meant to be SHARPENED: `Record-Sig` deliberately
canonicalises status, pointer and the box table and NOT the prose, exactly so
`## Why`, `## Outcome` and `## Lessons` stay editable in place -- that is the
"sharpen; edit in place when wrong" lifetime agent/README.md:57 assigns to a
durable design. A guard that refused every edit would make the record the one
document in this tree nobody may correct, and an uncorrectable document is one
people route around. So:

  DENIED   a Write (whole-file replacement always carries the spine), and any
           Edit/MultiEdit/NotebookEdit whose old or new text contains a header
           field, a checkbox line, or a `(record)` annotation line.
  ALLOWED  a prose edit, silently. That is the common case and it must stay
           frictionless.

THE TWO LEGITIMATE WAYS TO CHANGE A SPINE both go through Python and neither
touches the Edit tool, so neither is affected by this guard:

    worklist.py --plan-revive  <me> <path> --write   full text back from the blob
    worklist.py --plan-compact <me> <path> --write   re-derive the record

FAILS OPEN, on purpose and in every direction: no jq, no file, an unreadable
payload, a path that is not a plan, a plan that is not a record. This guard
can only ever turn an allowed edit into a refused one, so every uncertainty
resolves to `exit 0`. The gate is the backstop.

RESIDUAL, named rather than implied: a session can still `cat > file` from
Bash, which this chain never sees. That is not a hole worth a second guard --
check:ci-plan-record fails on the result, and the pre-bash chain already
refuses the shapes worth refusing. What this closes is the ACCIDENT, which is
the one that actually happens: an Edit aimed at prose that swallows the header
because the old_string was anchored one line too high.

PORT NOTE ON `set -uo pipefail`. `-u` turns an unset variable into an error and
`pipefail` gives a pipeline the status of its first failing stage. Neither has
an observable effect on this guard's three outputs -- every variable it reads is
assigned first, and every pipeline's status is discarded or already handled by a
`|| exit 0` -- and neither concept exists in Python, so the line survives only
here. It is worth recording because it is the ONLY guard in this chain that sets
either option, which is a fact about the file rather than about bash.

PORT NOTE ON `${#_body}`. bash counts CHARACTERS in the current locale, so the
12-character floor below is a byte count under `LC_ALL=C` (which the
differential exports) and a codepoint count under a UTF-8 session. The port
spells it as `len()` on the string, i.e. the UTF-8 reading, because that is the
locale a session actually runs in; the two answers can only differ for a box
body that is non-ASCII AND within a few characters of the floor.

PORT NOTE ON `break 2`. The bash breaks out of BOTH loops at once, which is why
the box search cannot report a second match. The port returns the reason
straight out of a helper instead, which is the same control flow with the
nesting made explicit rather than counted.
"""

import os
import re
import tempfile

from rediacc_hooks import hookio

CHAIN = "pre-edit"
TWIN = "pre-edit/block-compacted-plan-edit.sh"
ORDER = 11

# The blob VALUE test, and the reason the value tests exist at all. Reproduced
# 2026-09-06 against this hook with real payloads: four of five spine-destroying
# edits passed the line-anchored patterns, including `old_string: "<40 hex>"` --
# which is the SHORTEST unique string in a record and therefore the one the Edit
# tool's "minimal unique old_string" advice leads you straight to.
DEFECT = ("hookio.grep_q(blob, fragments, fixed=True)", "False")

PLAN_GLOBS = ("*/agent/PLAN-*.md", "agent/PLAN-*.md")

# The same 10-line header window every status regex in this repo reads
# (wl_checks.PLAN_HEADER_LINES).
HEADER_LINES = 10

RECORD_STATUS = hookio.rx(r"^Status:[{S}]*(compacted|parked)[{S}]*$")
BLOB_FIELD = hookio.rx(r"^Full-Text-Blob:[{S}]*([0-9a-f]{40}).*")
SIG_FIELD = hookio.rx(r"^Record-Sig:[{S}]*([0-9a-f]{8}).*")

HEADER_FIELD = r"^(Status|Owner|Full-Text|Full-Text-Blob|Record-Sig):"
DONE_ATTESTATION = r"done=([0-9a-f]{9}|open|abandoned)"
BOX_LINE = hookio.rx(r"^[{S}]*[-*+][{S}]+\[[ xX]\][{S}]")
RECORD_LINE = hookio.rx(r"^[{S}]{4}\(record\)[{S}]")

# The 12-character floor keeps a short body from matching ordinary prose.
MIN_BODY = 12

SPINE_WRITE = "the whole file -- a Write replaces the header, the boxes and the signature at once"
SPINE_HEADER = "the header block (Status / Full-Text / Full-Text-Blob / Record-Sig)"
SPINE_BLOB = "the Full-Text-Blob VALUE, which is the only pointer to the plan's text"
SPINE_SIG = "the Record-Sig VALUE, which check:ci-plan-record recomputes and compares"
SPINE_DONE = "a done= attestation, which is proved against the committed box ledger"
SPINE_BOX = "a checkbox line under ## Boxes"
SPINE_RECORD = "a (record) attestation line"
SPINE_BODY = "the TEXT of a box line, which moves its ledger signature"

MESSAGE = """❌ BLOCKED: %(file)s is a COMPACTED PLAN RECORD, and this edit rewrites %(spine)s.

The plan's full text is not in this file any more. It is in a git blob, and the
header you are editing is the only pointer to it:

    git show %(blob)s
    git log --find-object=%(blob)s --all

Rewrite that header by hand and nothing errors -- the file still reads as a
document, and the text simply becomes unreachable to everyone who does not
already know the blob id. A record that advertises a recovery command returning
nothing is worse than the deleted plan it replaced.

WHAT TO DO INSTEAD.

  Working on the plan again? Restore the full text first, then edit it as an
  ordinary plan. This puts it back on the housekeeping clock, which is correct:

      .claude/hooks/stop/worklist.py --plan-revive <you> %(file)s --write

  Re-deriving the record (the boxes moved, the ledger caught up)? Revive it,
  make the change in the real plan, COMMIT, then compact again. The commit is
  not optional -- --plan-compact refuses a dirty path, because the record's
  pointer is the hash of the bytes on disk and the record then overwrites them.
  The compact verb recomputes the blob, the box attestations and the signature
  together, which is the only way they stay consistent:

      .claude/hooks/stop/worklist.py --plan-revive  <you> %(file)s --write
      # ... edit the plan, then commit it ...
      .claude/hooks/stop/worklist.py --plan-compact <you> %(file)s --why auto
      .claude/hooks/stop/worklist.py --plan-compact <you> %(file)s --write

  Only sharpening the prose? That is ALLOWED and this guard does not fire on it.
  Edit ## Why, ## Outcome or ## Lessons and leave the header, the boxes and the
  (record) lines alone -- Record-Sig deliberately does not cover the prose, so
  correcting it costs nothing and needs no re-derivation.
"""

# ---------------------------------------------------------------------------
# The fixture world
# ---------------------------------------------------------------------------
#
# Every branch of this guard is behind `[ -f "$FILE" ]` and reads the record out
# of the file on disk, so the differential cannot reach any of them without a
# real record at a path the payload names literally. Same deterministic-temp-dir
# arrangement as block_roundlog_write.py, and for the same reason: the repo's
# own agent/PLAN-*.md files would make the answer depend on which plans happen
# to be compacted today.
WORLD = os.path.join(tempfile.gettempdir(), "rediacc-guard-records")
RECORD = "%s/agent/PLAN-a-compacted-record.md" % WORLD
PLAIN = "%s/agent/PLAN-not-a-record.md" % WORLD

BLOB = "c129f44d1b7e4a0f8d3c25e6b91af07d2c5e0168"
SIG = "9a3f0b1d"
BOX_BODY = "Rotate the namespace and update all four consumers"

RECORD_TEXT = (
    "# A compacted plan record\n"
    "\n"
    "Status: compacted\n"
    "Owner: d1589e0b\n"
    "Full-Text: c129f44d1 agent/PLAN-a-compacted-record.md\n"
    "Full-Text-Blob: %s\n"
    "Record-Sig: %s\n"
    "\n"
    "## Boxes\n"
    "\n"
    "- [x] %s\n"
    "    (record) done=c129f44d1 landed in the same change\n"
    "- [ ] Delete the compatibility shim once nothing reads it\n"
    "\n"
    "## Why\n"
    "\n"
    "Prose that Record-Sig deliberately does not cover, so it stays editable in\n"
    "place and this guard must not fire on a change to it.\n"
) % (BLOB, SIG, BOX_BODY)

PLAIN_TEXT = "# An ordinary plan\n\nStatus: active\n\n## Tasks\n\n- [ ] Do the thing properly\n"


def _record_world(_unused):
    """One compacted record and one ordinary plan, at fixed paths."""
    os.makedirs(os.path.join(WORLD, "agent"), exist_ok=True)
    for path, text in ((RECORD, RECORD_TEXT), (PLAIN, PLAIN_TEXT)):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    return WORLD


FIXTURES = {"record-world": _record_world}

# The variable is never read by this guard; resolving the token is what builds
# the world before any case runs.
ENVS = [("records", {"REDIACC_RECORD_WORLD": "{FIXTURE:record-world}"}, {})]

EDGE_CASES = [
    (
        "a Write replaces the spine outright",
        {"tool_name": "Write", "tool_input": {"file_path": RECORD, "content": "# rewritten\n"}},
    ),
    (
        "an edit quoting a whole header line",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": RECORD,
                "old_string": "Status: compacted",
                "new_string": "Status: active",
            },
        },
    ),
    # The 2026-09-06 reproduction: a MINIMAL unique old_string with no line
    # prefix at all, which every line-anchored pattern above misses.
    (
        "the bare 40-hex blob as old_string",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "old_string": BLOB}},
    ),
    (
        "the bare 8-hex signature as old_string",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "old_string": SIG}},
    ),
    (
        "a done= attestation",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "new_string": "done=abandoned"}},
    ),
    (
        "a checkbox line",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "new_string": "- [ ] a new box"}},
    ),
    (
        "a (record) attestation line",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": RECORD, "new_string": "    (record) done=open"},
        },
    ),
    # BOTH DIRECTIONS of the box-body containment test.
    (
        "a box body quoted whole",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "old_string": BOX_BODY}},
    ),
    (
        "the shortest distinguishing part of a box body",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "old_string": BOX_BODY[:20]}},
    ),
    # ... and its floor: a needle under 12 characters is ordinary prose.
    (
        "a needle under the twelve-character floor",
        {"tool_name": "Edit", "tool_input": {"file_path": RECORD, "old_string": "Rotate the"}},
    ),
    # The common case, which must stay frictionless.
    (
        "sharpening the prose is allowed",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": RECORD,
                "old_string": "Prose that Record-Sig deliberately does not cover",
                "new_string": "Prose the signature deliberately leaves alone",
            },
        },
    ),
    # Both halves of the record test are required.
    (
        "a plan that is not a record",
        {"tool_name": "Write", "tool_input": {"file_path": PLAIN, "content": "# rewritten\n"}},
    ),
    (
        "a record path that does not exist",
        {"tool_name": "Write", "tool_input": {"file_path": "agent/PLAN-absent.md", "content": "x"}},
    ),
    ("a document that is not a plan", {"tool_name": "Write", "tool_input": {"file_path": "a.md"}}),
]


def _field(pattern, head10):
    """`sed -n 's/^Field:[[:space:]]*\\(...\\)/\\1/p' | head -1`.

    sed prints ONLY the lines its substitution matched, and `head -1` keeps the
    first of them; the command substitution then strips the newline. A record
    with two `Full-Text-Blob:` lines therefore takes the first, which is the
    behaviour the port has to keep rather than the one a dict lookup would give.
    """
    records, _ = hookio._records(head10)
    for record in records:
        match = re.match(pattern, record)
        if match:
            return match.group(1)
    return ""


def _box_body_hit(file_text, fragments):
    """The `break 2` double loop: does any fragment name a box's TEXT?

    BOTH DIRECTIONS, because an Edit quotes a MINIMAL unique substring and a
    one-direction test misses half the cases. `old_string` may be the whole box
    body (body inside the fragment) or the shortest distinguishing part of it
    (fragment inside the body).
    """
    lines = hookio.grep_lines(BOX_LINE, file_text)
    pieces, _ = hookio._records(hookio._here_string(fragments))
    for line in lines:
        # `${_bl#*] }` -- everything after the FIRST "] ", or the whole line
        # when there is none.
        cut = line.find("] ")
        body = line[cut + 2 :] if cut >= 0 else line
        if len(body) < MIN_BODY:
            continue
        for piece in pieces:
            if len(piece) < MIN_BODY:
                continue
            if body in piece or piece in body:
                return True
    return False


def run(ev):
    if not hookio.have("jq"):
        return hookio.ALLOW

    file_path = ev.first(("tool_input", "file_path"), ("tool_input", "notebook_path"))
    if file_path == "":
        return hookio.ALLOW
    if not hookio.case_glob(file_path, *PLAN_GLOBS):
        return hookio.ALLOW
    if not os.path.isfile(file_path):
        return hookio.ALLOW

    try:
        with open(file_path, encoding="utf-8", errors="surrogateescape") as handle:
            file_text = handle.read()
    except OSError:
        return hookio.ALLOW

    # IS IT A RECORD? Both halves are required: a plan may legitimately say
    # `parked` in prose, and a `Full-Text-Blob:` with no record status is not a
    # record either.
    head10 = hookio._command_substitution(
        "".join(file_text.splitlines(keepends=True)[:HEADER_LINES])
    )
    if not hookio.grep_q(RECORD_STATUS, head10):
        return hookio.ALLOW
    blob = _field(BLOB_FIELD, head10)
    if blob == "":
        return hookio.ALLOW
    sig = _field(SIG_FIELD, head10)

    tool = ev.field("tool_name")

    # The four-tool payload union: `content` is Write, `new_string`/`old_string` are
    # Edit, `new_source` is NotebookEdit, `edits[]` is MultiEdit. old_string is in
    # here deliberately -- an Edit that DELETES the header names it only there.
    fragments = ev.texts(
        ("tool_input", "content"),
        ("tool_input", "new_string"),
        ("tool_input", "old_string"),
        ("tool_input", "new_source"),
        ("tool_input", "edits", "[]?", "new_string"),
        ("tool_input", "edits", "[]?", "old_string"),
    )
    if fragments == "":
        return hookio.ALLOW

    # TWO KINDS OF TEST, and the first version had only the first kind. The
    # line-anchored patterns catch an edit that quotes a WHOLE line; the VALUES
    # are tested by substring, read out of the FILE rather than pattern-matched
    # out of the payload, which is what makes them exact.
    if tool == "Write":
        spine = SPINE_WRITE
    elif hookio.grep_q(HEADER_FIELD, fragments):
        spine = SPINE_HEADER
    elif hookio.grep_q(blob, fragments, fixed=True):
        spine = SPINE_BLOB
    elif sig != "" and hookio.grep_q(sig, fragments, fixed=True):
        spine = SPINE_SIG
    elif hookio.grep_q(DONE_ATTESTATION, fragments):
        spine = SPINE_DONE
    elif hookio.grep_q(BOX_LINE, fragments):
        spine = SPINE_BOX
    elif hookio.grep_q(RECORD_LINE, fragments):
        spine = SPINE_RECORD
    # THE BOX BODIES, by substring, for the same reason as the blob above:
    # rewriting a box's TEXT moves its ledger signature, and
    # check_plan_boxes.py's A1 reports a moved signature as a box that VANISHED.
    elif _box_body_hit(file_text, fragments):
        spine = SPINE_BODY
    else:
        spine = ""

    if spine == "":
        return hookio.ALLOW

    ev.warn_raw(MESSAGE % {"file": file_path, "spine": spine, "blob": blob})
    return hookio.DENY
