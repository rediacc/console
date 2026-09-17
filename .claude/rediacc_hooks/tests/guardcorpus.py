"""The guard differential's corpus: every case the real suite already pairs
with the guard it was written for.

WHY THIS AND NOT `corpus.harvest()`. That harvester answers "what command
strings has this repo ever fed a hook", which is the right question for
`shellscan`, whose subject is one text filter applied to all of them. A guard
is different: it is 46 separate programs, each with its own preamble, its own
event shape and its own message, and the thing worth proving is that EACH port
answers as its own twin does. `.claude/hooks/test-hooks.sh` already holds that
pairing, and holds it as the accumulated record of every bypass and every
over-block this repo has paid for:

    check 2 guards/block_raw_pr_body_edit.py "$(bash_json 'gh pr edit ...')" "label"
    ^     ^ ^                                 ^                              ^
    verb  | the guard                         the event                      why

so one pass over the file yields (guard, payload) for every call site. Those
are the inputs; the ORACLE is the bash guard itself, run on the same bytes.

THE KEY SPELLING CHANGED AT THE P7 CUTOVER and the reason is not cosmetic. A
case names its guard by the key `check-hook-integrity.sh` inventories it under,
so that one spelling drives the suite, credits the coverage assertion and keys
this corpus. The guards are Python modules now, living at
`.claude/rediacc_hooks/guards/`, so the key is `guards/<module>.py`; the bash
original the differential compares against was moved to
`.claude/oracles/<chain>/<name>.sh` and is reached through the
port module's own TWIN field rather than by rewriting the key.

THE EXPECTED EXIT CODE IN COLUMN 2 IS DELIBERATELY NOT THE ORACLE, and that is
the difference between a differential and a re-run of the suite. Several
payloads interpolate suite-local variables (`$PB_DIR`, `$PLAN_TMP`, `$BW_TMP`)
that this module does not reconstruct, so the bytes it recovers are not always
the bytes the suite fed. That weakens nothing: both implementations receive the
IDENTICAL bytes, and disagreement between them is the finding. It also means a
payload reconstructed imperfectly is still a perfectly good differential input,
which is why no attempt is made to run the suite.

CROSS-FEEDING IS HALF THE CORPUS. A guard tested only on the events it was
written for is tested only where it says no. Over-blocking is the failure mode
that gets a guard deleted -- `check-hook-integrity.sh` says so in as many
words, "an over-blocking guard is one that gets deleted, which is how the rule
dies" -- and it only shows up on somebody else's input. So every guard is also
run against a deterministic sample of the WHOLE payload pool.
"""

import hashlib
import json
import pathlib
import re

from rediacc_hooks.tests import corpus

SUITE = corpus.SUITE
repo_root = corpus.repo_root

# The suite's payload builders, and the event each one produces. Reading them
# out of the suite would be the purer move; they are transcribed here because
# they are seven one-line `printf` functions, and a parser for them would be more code than they are. `test_builders_match_the_suite` compares this table against the real definitions on every run, so a change to either side is a failure rather than a silent drift.
BUILDERS = {
    "bash_json": lambda a: {"tool_input": {"command": a[0]}},
    "bash_bg_json": lambda a: {"tool_input": {"command": a[0], "run_in_background": True}},
    "edit_json": lambda a: {"tool_input": {"new_string": a[0]}},
    "multiedit_json": lambda a: {"tool_input": {"edits": [{"new_string": a[0]}]}},
    "wf_edit_json": lambda a: {"tool_input": {"file_path": a[0], "new_string": a[1]}},
    "tool_json": lambda a: {"tool_name": a[0], "tool_input": {"file_path": a[1], a[2]: a[3]}},
    "ask_json": lambda a: {"tool_input": {"questions": [{"question": a[0], "header": "x"}]}},
}

# The shapes each builder's `printf` must have for the table above to be a faithful transcription. Compared against the suite on every run.
BUILDER_SHAPES = {
    "bash_json": '{"tool_input":{"command":%s}}',
    "bash_bg_json": '{"tool_input":{"command":%s,"run_in_background":true}}',
    "edit_json": '{"tool_input":{"new_string":%s}}',
    "multiedit_json": '{"tool_input":{"edits":[{"new_string":%s}]}}',
    "wf_edit_json": '{"tool_input":{"file_path":%s,"new_string":%s}}',
    "tool_json": '{"tool_name":%s,"tool_input":{"file_path":%s,%s:%s}}',
    "ask_json": '{"tool_input":{"questions":[{"question":%s,"header":"x"}]}}',
}

# Vacuity floors, both corpus-derived rather than hand-typed (driver contract section 6). The first is a RATIO of the call sites counted in the same pass,
# so adding suite cases raises it; the second is the base case that stops the
# ratio meaning anything over a gutted file, exactly as `corpus.MIN_COMMANDS` is for the shellscan corpus.
RECOVERY_FLOOR = 0.85
MIN_CASES = 300

# How many foreign payloads each guard is additionally run against. Drawn by a stable hash rather than at random, so a failure reproduces and a rerun compares the same set.
CROSS_SAMPLE = 40


def _skip_blanks(src, i):
    r"""Whitespace, INCLUDING a backslash-newline continuation.

    Dozens of the call sites wrap their arguments across lines, and a skipper
    that did not know about `\` + newline would read the backslash as the start
    of the next word and recover that many payloads of garbage.
    """
    while i < len(src):
        if src[i] in " \t":
            i += 1
        elif src[i] == "\\" and i + 1 < len(src) and src[i + 1] == "\n":
            i += 2
        else:
            break
    return i


def _raw_word(src, i):
    """The SOURCE SLICE of one shell word, quotes and all.

    `corpus._read_word` unquotes as it goes, which is what the shellscan corpus
    wants and precisely not what this one does: a payload argument is
    `"$(bash_json 'x')"`, and the builder name is only visible BEFORE the
    unquoting removes the substitution. So the span is measured first and
    interpreted afterwards.
    """
    start = i
    n = len(src)
    while i < n:
        c = src[i]
        if c in " \t\n":
            break
        if c == "'":
            end = src.find("'", i + 1)
            i = n if end == -1 else end + 1
        elif c == "$" and i + 1 < n and src[i + 1] == "'":
            _, i = corpus._read_ansi_c(src, i)
        elif c == "$" and i + 1 < n and src[i + 1] == "(":
            i = corpus._skip_substitution(src, i + 1)
        elif c == '"':
            i += 1
            while i < n and src[i] != '"':
                if src[i] == "$" and i + 1 < n and src[i + 1] == "(":
                    i = corpus._skip_substitution(src, i + 1)
                    continue
                i += 2 if src[i] == "\\" else 1
            i += 1
        elif c == "\\" and i + 1 < n:
            i += 2
        else:
            i += 1
    return src[start:i], i


def _words(src, i):
    """Every remaining word of a `$( ... )` body, unquoted."""
    out = []
    n = len(src)
    while i < n:
        if src[i] in " \t\n":
            i += 1
            continue
        if src[i] == ")":
            break
        word, i = corpus._read_word(src, i, stop_at_paren=True)
        out.append(word)
    return out


def _payload_from(raw, names):
    """One payload argument, as the JSON text the guard will read on stdin.

    Returns None for a shape this does not reconstruct, which is counted
    against the recovery ratio rather than guessed at.
    """
    text = raw.strip()
    if len(text) > 1 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    bare = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", text)
    if bare:
        value = names.get(bare.group(1))
        return value if value and value.lstrip().startswith("{") else None
    match = re.match(r"\$\(\s*([A-Za-z_][A-Za-z0-9_]*)\b", text)
    if match:
        builder = BUILDERS.get(match.group(1))
        if builder is None:
            return None
        args = _words(text, match.end())
        try:
            doc = builder(args)
        except IndexError:
            return None
        return json.dumps(doc)
    body, _ = corpus._read_word(raw, 0)
    return body if body.lstrip().startswith("{") else None


def harvest_cases():
    """`[(guard, payload, label, suite_rc)]` plus the stats the floors read.

    `guard` is the key `check-hook-integrity.sh` inventories the guard under --
    `guards/block_x.py` for a port, `pre-bash/block-x.sh` for one still in bash
    -- because "two chains can never collide on one basename" is a property
    worth keeping in both places, and because one spelling driving the suite and
    keying the coverage gate is what stops the two drifting.
    """
    src = SUITE.read_text(encoding="utf-8")
    names = corpus._assignments(src)
    sites = 0
    cases = []
    for m in re.finditer(r"(?m)^[ \t]*(check|check_out|check_nojq)[ \t]+", src):
        i = _skip_blanks(src, m.end())
        rc_word, i = _raw_word(src, i)
        if not re.fullmatch(r"[0-9]+", rc_word):
            continue
        i = _skip_blanks(src, i)
        guard_word, i = _raw_word(src, i)
        # `.py` AS WELL AS `.sh`, and `guards/` as well as a chain name. The
        # ported guards are modules; a reader anchored to the old spelling would
        # recover ZERO cases for all 46 of them and the recovery ratio below would be the only thing that said so.
        if not re.fullmatch(r"[a-z_-]+/[A-Za-z0-9_.-]+\.(?:sh|py)", guard_word):
            continue
        sites += 1
        i = _skip_blanks(src, i)
        raw, _ = _raw_word(src, i)
        payload = _payload_from(raw, names)
        if payload is None:
            continue
        # The differential frames its stream with these two control characters (the same guard `corpus.harvest` states), so a payload carrying one would corrupt the frame instead of failing a comparison.
        if "\x1e" in payload or "\x1f" in payload:
            continue
        line = src.count("\n", 0, m.start()) + 1
        cases.append((guard_word, payload, "%s@%d" % (m.group(1), line), rc_word))
    stats = {
        "call_sites": sites,
        "recovered": len(cases),
        "guards_named": len({g for g, _, _, _ in cases}),
        "source": str(SUITE),
    }
    return cases, stats


def builder_shape_drift():
    """Every builder whose real `printf` no longer matches BUILDER_SHAPES.

    The transcription above is the only place this corpus decides what event a
    suite case produces. If the suite changes a builder and this table does not,
    every payload for that builder is silently the wrong shape, both sides get
    it, and the differential goes on passing while testing something else.
    """
    src = SUITE.read_text(encoding="utf-8")
    drift = []
    for name, shape in sorted(BUILDER_SHAPES.items()):
        m = re.search(r"(?m)^%s\(\) \{ printf '([^']*)'" % re.escape(name), src)
        if m is None:
            drift.append((name, "<no definition found in the suite>", shape))
        elif m.group(1) != shape:
            drift.append((name, m.group(1), shape))
    return drift


def cross_sample(payloads, guard, limit=CROSS_SAMPLE):
    """A deterministic slice of the whole payload pool, per guard.

    Keyed by a hash of the guard name AND the payload, so two guards get
    DIFFERENT foreign samples. A single shared sample would mean every guard
    tested against the same forty strings, and a shape absent from those forty
    would be absent from the whole cross-feed.
    """
    scored = []
    for payload in payloads:
        digest = hashlib.sha256(("%s\x00%s" % (guard, payload)).encode("utf-8")).hexdigest()
        scored.append((digest, payload))
    scored.sort()
    return [payload for _, payload in scored[:limit]]


# Event shapes no suite case produces, and every one of them is a shape a guard can be handed by the real harness. The suite's builders always emit a
# well-formed document; the harness does not promise one, and `jq -r` answers
# each of these differently (see `hookio._jq_raw`, whose four-way asymmetry is what these pin).
DEGENERATE_PAYLOADS = [
    ("empty stdin", ""),
    ("malformed json", "{not json"),
    ("top-level null", "null"),
    ("top-level number", "42"),
    ("top-level array", "[1]"),
    ("top-level string", '"s"'),
    ("empty object", "{}"),
    ("null tool_input", '{"tool_input":null}'),
    ("numeric tool_input", '{"tool_input":5}'),
    ("empty tool_input", '{"tool_input":{}}'),
    ("null command", '{"tool_input":{"command":null}}'),
    ("empty command", '{"tool_input":{"command":""}}'),
    ("numeric command", '{"tool_input":{"command":42}}'),
    ("false command", '{"tool_input":{"command":false}}'),
    ("command with a newline", '{"tool_input":{"command":"echo a\\ngit push --force"}}'),
    ("command with a carriage return", '{"tool_input":{"command":"git push --force\\r"}}'),
    ("file_path only", '{"tool_input":{"file_path":"packages/cli/src/x.ts"}}'),
    ("new_string only", '{"tool_input":{"new_string":"x"}}'),
    ("edits array", '{"tool_input":{"edits":[{"new_string":"x"},{"new_string":"y"}]}}'),
    ("edits not an array", '{"tool_input":{"edits":5}}'),
    ("cwd present", '{"cwd":"/tmp","tool_input":{"command":"git status"}}'),
    ("tool_name present", '{"tool_name":"Write","tool_input":{"file_path":"a.md","content":"x"}}'),
    ("questions array", '{"tool_input":{"questions":[{"question":"q","header":"h"}]}}'),
    ("questions empty", '{"tool_input":{"questions":[]}}'),
    ("background flag", '{"tool_input":{"command":"read -t 600 x","run_in_background":true}}'),
]


# The retired bash originals. They are NOT hooks and nothing registers them; see
# `.claude/oracles/README.md` for why they are kept and why they had to leave `.claude/hooks/`.
ORACLES = "oracles"


def guard_path(root, twin):
    """The bash original on disk, from a port module's chain-qualified TWIN."""
    return pathlib.Path(root) / ".claude" / ORACLES / twin
