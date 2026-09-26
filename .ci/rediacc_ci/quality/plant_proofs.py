r"""check:ci-plant-proofs -- a control that PLANTS a defect must prove the plant landed.

THE CLASS. A control earns a gate's green by feeding it a MUTATED fixture and requiring the opposite verdict. If the mutation silently does nothing -- because the needle it replaces has been reworded, deleted or moved -- the control scans the UNMUTATED text, asserts the opposite verdict about identical input, and PASSES FOR FREE. The gate then reports that it can detect a defect it
has never once been shown.

WHY THIS FILE EXISTS AND WHAT IT IS NOT DUPLICATING. On 2026-09-09 the class was swept across all three languages in this tree and came back uneven:

  * PYTHON is covered, by `check:ci-python-control-plants`. Its rule is "use the
    HARNESS": `rediacc_ci.controls.plant` raises `VacuousPlantError` when the
    needle is absent, so a compliant Python control cannot go vacuous by
    construction. That gate is rc=0 over its corpus.
  * BASH gate scripts under `.ci/scripts/quality/check-*.sh` are covered, by
    `check:ci-control-vacuity` (and its Python port `rediacc_ci.quality.
    control_vacuity`). Its scope is stated in its own success line and it is
    exactly those 82 files.
  * EVERYTHING ELSE WAS UNCOVERED. Measured that day: `grep -rn 'CONTROL PLANT
    DID NOT LAND' --include='*.sh' .` found TWO sites in the entire repository,
    both in one file, while `sed -i` and `perl -pi` plants sat across the gate
    TEST corpus with no proof at all. TypeScript had no gate of any kind; two
    control sites existed, one occurrence-checked by hand and one not.

WHY THREE ARMS AND NOT ONE WIDENED GATE. This was decided on evidence, not taste, and the evidence is three specific obstacles:

  1. THE PYTHON PREDICATE CANNOT BE THE BASH PREDICATE. Python's rule is "call
     the harness". Bash has no harness and cannot get one: ruling 7
     (docs/ci-overhaul/04-decisions.md) freezes the tracked `.sh` surface under
     `.ci` and `.claude` SHRINK-ONLY, so a shared `plant.sh` library is a file
     that may not be added. The only enforceable bash rule is therefore the
     in-place one -- prove the plant landed -- which is `control_vacuity`'s
     predicate, not `python_control_plants`'s.
  2. `control_vacuity` CANNOT BE WIDENED CHEAPLY. Its Python port is held to a
     BYTE-IDENTICAL differential against its live bash twin
     (`.ci/rediacc_ci/tests/test_quality_control_vacuity.py`), and invariant 5
     forbids deleting the twin yet. Widening the port means widening a bash
     implementation of heredoc- and quote-aware scanning, which is the
     false-positive machine that argument already lost once.
  3. WIDENING `check_python_control_plants.py` MEANS RENAMING IT, because a gate
     id is DERIVED from its entry-point filename (`scripts/lib/gate-header.ts`
     `derivedId`). A rename churns package.json, the manifest, the lock and the
     workflow for a gate that is currently green, to merge two predicates that
     stay different anyway.

So: this gate owns BASH and TYPESCRIPT, everywhere in the tracked tree, and it DELEGATES Python -- with an assertion, not a comment. If the Python gate's entry point stops existing or stops being registered, this gate REFUSES rather than quietly leaving a third of the class unscanned. That refusal is the whole difference between a delegation and a hole; the 2026-09-08 note in
`check_python_control_plants.py` records what happened the last time a coverage boundary was documented in prose instead of asserted ("21 became 50, and it changed silently").

-----------------------------------------------------------------------------
THE BASH PREDICATE
-----------------------------------------------------------------------------

A PLANT is an IN-PLACE mutation of a named file: `sed -i`, `sed -E -i`, `sed --in-place`, or `perl -i`/`perl -pi`/`perl -ni`. The target is the last word of the command SEGMENT (the logical line split on unquoted `;`, `&&`, `||` and `|`), so `for e in "$@"; do sed -i "$e" "$dst"; done` yields `"$dst"` and not `done`.

A PROOF is a `grep -q`/`grep -c`/`cmp`/`diff` within eight logical lines either side of the plant, naming the SAME target, on a line that is not building a string. Both directions count, and both are in real use here:

    # BEFORE: the needle exists to be replaced
    grep -qE '^PORTED_VERBS=\(' "$ctl/run.sh" || fail "PLANT DID NOT LAND"
    # AFTER: the replacement is present
    grep -q '^PORTED_VERBS=(quality)$' "$ctl/run.sh" || fail "PLANT DID NOT LAND"

THE `<<<` AND `$(` EXCLUSION ON A PROOF LINE IS NOT COSMETIC, and it is the one tightening this gate needed most. `test-run-sh.sh:441` reads

    if grep -q '^documented-but-unreachable clean$' <<<"$(verb_findings "$ctl/run.sh" "$ctl/legacy.sh")"

which contains `grep -q` and names the target, and is the CONTROL'S VERDICT, not a proof of anything. Counting it turned two genuinely unproven plants at `test-run-sh.sh:439` and `:448` into false greens -- measured, in the first version of this file. A proof must grep the FILE.

TWO EXEMPTIONS, both because the mutation CANNOT go vacuous:

  * A PREFIX SUBSTITUTION, `s/^/.../`, has an empty needle anchored at line
    start. It always matches. Carried verbatim from `control_vacuity`, which
    paid for it with two false positives on 2026-08-26.
  * A PASS-THROUGH WRAPPER, whose only operand is `"$@"` (`sed -i "$@"`,
    `sed -i '' "$@"`, the BSD/GNU shim in `.ci/scripts/lib/common.sh`). There is
    no needle on that line; the needle is the caller's, and the caller is where
    the proof belongs.

-----------------------------------------------------------------------------
THE TYPESCRIPT PREDICATE
-----------------------------------------------------------------------------

Inside a CONTROL REGION, `IDENT.replace(NEEDLE, ...)` where IDENT is a BARE NAME must be accompanied, in the same region, by an OCCURRENCE CHECK on the SAME needle text: `IDENT.split(NEEDLE).length`, `IDENT.match(...)`, or `IDENT.indexOf(NEEDLE)`.

THE REGION RESTRICTION IS THE EXEMPTION MECHANISM, exactly as the bare-Name restriction is in the Python gate, and it is why there is no allowlist file. Measured over the 175 tracked `.ts` files under `scripts/`: 197 bare-identifier `.replace(` calls, nearly all of them PARSING -- normalising a path, stripping a suffix, indenting a message. Requiring an occurrence check on those
would be absurd. Scoped to control regions the number collapses to the handful that are actually building a mutant.

A CONTROL REGION is opened by either of two markers and closed by the brace depth returning to where the marker found it:

    // ── Control: the extractor, both directions, before it is trusted ──
    {  ...  }                                   a comment naming a control

    function selftestFoo() { ... }              a declaration named for one
    const controlBar = () => { ... }

Both shapes are in the tree. `scripts/gates/check-backup-bucket-conformance.ts:145` is the first; `scripts/gates/check-guard-mutations.ts` reaches its mutant builder from the second.

-----------------------------------------------------------------------------
THE SHELL LEXER, AND WHY IT REPORTS ITS OWN DEGRADATION
-----------------------------------------------------------------------------

Deciding whether a `sed -i` is CODE or a STRING needs quote state, and quote state in bash crosses lines. Three measured false positives depended on getting this right; two are still in the tree, and the third left it with its file:

    check-control-vacuity.sh:83   grep -qE '...|sed -i'      inside one line's quotes
    test-install-methods.sh:807   [ -f \"\$f\" ] && sed -i   inside a multi-line "..."

The third was `test-media-portable.sh:272`, a fixture ROW reading `'sed -i "s/a/b/" f'` rather than a command, retired with that twin in W7 P5. Its Python port is outside this corpus, which scans `.sh` and `.ts` only.

So the lexer carries quote state and heredoc state across lines. It is not a bash parser: it does not model `$( )` nesting, and on eight of the 520 tracked shell files the state does not return to neutral at EOF. Those files are scanned in DEGRADED mode -- per line, quote state reset each line -- and the count of them is PRINTED. Degraded scanning over-reports rather than
under-reports, which is the direction this gate wants: a spurious "add a proof" costs one line, a missed vacuous plant costs a gate that cannot fail. Measured 2026-09-09: the eight degraded files contain ZERO plants under either reading, so the choice is currently free.

-----------------------------------------------------------------------------
THE BASELINE
-----------------------------------------------------------------------------

`.ci/config/plant-proof-baseline.json` freezes today's unproven plants. It is SHRINK-ONLY and SET-EQUAL IN BOTH DIRECTIONS, and the second direction is the half that usually goes missing:

  * a plant with NO proof that is NOT in the baseline is a finding (a new
    vacuous control -- or, identically, someone DELETED a baseline row while the
    plant is still unproven, so trimming the file cannot buy a green);
  * a baseline row whose plant is now PROVEN or GONE is also a finding, telling
    the author to drain with `--write-baseline` (so the set has to shrink, and
    a row cannot be pre-banked for a violation that does not exist).

`--write-baseline` REFUSES any reseed that would ADD a row. A drain that removes thirty and adds one has still added one, and comparing totals is not the same claim as comparing sets. To admit a genuinely new row it must be typed:

    check_plant_proofs.py --write-baseline --allow-new <id>

and `--allow-new` is itself checked against the derived set, so it cannot pre-load a row for a plant that does not exist.

IDS ARE HASHED OVER THE TEXT, NEVER THE LINE NUMBER. A line number churns when a paragraph moves above it, and a churning baseline gets reseeded wholesale, which silently re-absorbs every other writer's fresh findings. The id covers the language, the file and the WHITESPACE-NORMALISED command text, so a row survives a MOVE and re-keys on a REWRITE -- a rewrite being exactly when a
human should look at the plant again. When a re-key happens, hand-edit the single row; do not run `--write-baseline`.

---------------------------------------------------------------------------
ANTI-VACUITY, and every clause is written for the FINISH LINE as well as today
---------------------------------------------------------------------------

  * zero tracked files, zero `.sh` scanned, or zero `.ts` scanned: REFUSE. The
    gate is not seeing the tree.
  * zero PLANTS discovered across the whole shell corpus: REFUSE. The day
    `sed -i` stops being the spelling, every file looks compliant.
  * the Python delegate's entry point missing, or not named in package.json:
    REFUSE. A third of the class would be unscanned with nothing said.
  * zero UNPROVEN plants with a NON-EMPTY baseline: not a refusal, a FINDING --
    every baseline row reports as drainable, which is the correct and loud
    result. An empty baseline with zero unproven plants is the terminal state
    this gate is aiming at, and it passes, printing zero.

There is deliberately NO `> 0` floor on the unproven count. That is the clause that reds at the finish line, and three of them shipped in this repo in three days.
"""

import hashlib
import json
import pathlib
import re
import subprocess

from rediacc_ci import log, paths
from rediacc_ci.controls import controls_first

BASELINE_REL = ".ci/config/plant-proof-baseline.json"
KEY = "plants"

# The Python arm, delegated and ASSERTED. Both halves are checked: the entry point must exist, and package.json must still run it.
PYTHON_DELEGATE = ".ci/scripts/quality/check_python_control_plants.py"
PYTHON_DELEGATE_ID = "check:ci-python-control-plants"

# How far from a plant a proof may sit, in LOGICAL lines. Eight covers every real shape here (the widest genuine gap measured is four) without letting an unrelated grep two controls away launder a plant.
PROOF_WINDOW = 8

# A TypeScript control region opened by a comment gets this many lines when the brace depth never rises, i.e. the marker introduces a plain statement run rather than a block.
TS_FLAT_REGION = 25
TS_MAX_REGION = 120


class RefusalError(Exception):
    """The gate cannot produce a verdict. Never folded into 'no findings'."""


# --------------------------------------------------------------------------- the shell lexer ---------------------------------------------------------------------------

_HEREDOC = re.compile(r"<<-?\s*(\\?)(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def shell_rows(text):
    """[(lineno, code, mask)] plus whether the file needed DEGRADED scanning.

    `code` is the line with any trailing comment removed; `mask[i]` is True when `code[i]` sits inside a quoted string. Heredoc bodies are dropped entirely: they are data, not commands.

    Quote and heredoc state carry ACROSS lines, which is what a bash quote does. When the state has not returned to neutral at EOF the file is rescanned line by line and the second element of the return is True -- see the module docstring on why over-reporting is the safe direction.
    """
    rows, quote, pending = _shell_rows_once(text)
    if quote is None and pending is None:
        return rows, False
    degraded = []
    for index, raw in enumerate(text.split("\n"), 1):
        one, _, _ = _shell_rows_once(raw)
        degraded.extend((index, code, mask) for _, code, mask in one)
    return degraded, True


def _shell_rows_once(text):
    rows = []
    queued = []
    active = None
    quote = None
    for index, raw in enumerate(text.split("\n"), 1):
        if active is not None:
            if raw.strip() == active:
                active = None
            continue
        cursor = 0
        mask = []
        cut = None
        while cursor < len(raw):
            char = raw[cursor]
            if quote is None:
                if char == "#" and (cursor == 0 or raw[cursor - 1] in " \t"):
                    cut = cursor
                    break
                if char in "'\"":
                    quote = char
                    mask.append(True)
                    cursor += 1
                    continue
                if char == "\\":
                    mask.append(False)
                    if cursor + 1 < len(raw):
                        mask.append(False)
                    cursor += 2
                    continue
                mask.append(False)
                cursor += 1
                continue
            if char == quote:
                quote = None
                mask.append(True)
                cursor += 1
                continue
            if char == "\\" and quote == '"':
                mask.append(True)
                if cursor + 1 < len(raw):
                    mask.append(True)
                cursor += 2
                continue
            mask.append(True)
            cursor += 1
        code = raw if cut is None else raw[:cut]
        mask = (mask + [False] * len(code))[: len(code)]
        found = _HEREDOC.search(code)
        if found and "<<<" not in code and not mask[found.start()]:
            queued.append(found.group(3))
        if code.strip():
            rows.append((index, code, mask))
        if queued and active is None:
            active = queued.pop(0)
    return rows, quote, active


def logical_rows(rows):
    """Join backslash-continued lines into one row, keeping the FIRST lineno."""
    out = []
    held = None
    for index, code, mask in rows:
        body = code.rstrip()
        cont = body.endswith("\\")
        if cont:
            body = body[:-1]
        span = mask[: len(body)]
        if held is None:
            held = [index, body, list(span)]
        else:
            lead = len(body) - len(body.lstrip())
            held[1] += " " + body.lstrip()
            held[2] += [False, *list(span)[lead:]]
        if not cont:
            held[2] = (held[2] + [False] * len(held[1]))[: len(held[1])]
            out.append((held[0], held[1], held[2]))
            held = None
    if held is not None:
        held[2] = (held[2] + [False] * len(held[1]))[: len(held[1])]
        out.append((held[0], held[1], held[2]))
    return out


def shell_words(code, mask):
    """Split into shell-ish words. Whitespace inside quotes does not split."""
    words = []
    current = ""
    for index, char in enumerate(code):
        if not mask[index] and char in " \t":
            if current:
                words.append(current)
                current = ""
            continue
        current += char
    if current:
        words.append(current)
    return words


_SEGMENT = re.compile(r"&&|\|\||[;|]")


def command_segment(code, mask, at):
    """The command around offset `at`, cut at unquoted `;`, `&&`, `||`, `|`.

    Without this the target of `for e in "$@"; do sed -i "$e" "$dst"; done` is the word `done`, and a proof naming `"$dst"` would never be matched to it.
    """
    start = 0
    end = len(code)
    for found in _SEGMENT.finditer(code):
        if mask[found.start()]:
            continue
        if found.end() <= at:
            start = found.end()
        elif found.start() > at:
            end = found.start()
            break
    return code[start:end], mask[start:end]


# --------------------------------------------------------------------------- the bash predicate ---------------------------------------------------------------------------

# `sed` carrying an in-place flag anywhere in its options, and `perl -...i...`.
_SED_INPLACE = re.compile(r"(?:^|[|;&(`]|\s)sed\b[^|;&<>]*?\s-{1,2}[A-Za-z-]*i\b")
_PERL_INPLACE = re.compile(r"(?:^|[|;&(`]|\s)perl\s+-[A-Za-z]*i")

# A prefix substitution always matches, so it cannot go vacuous.
_PREFIX_SUB = re.compile(r"s([/@|#!,])\^\1")

# The proof shapes. `test -s` is deliberately absent: a non-empty file proves nothing about WHICH bytes changed.
_PROOF = re.compile(
    r"\bgrep\s+-[A-Za-z]*[qc]"
    r"|\bcmp\b"
    r"|\bdiff\b"
    r'|\[\[ "\$[A-Za-z_][A-Za-z0-9_]*" == "\$[A-Za-z_][A-Za-z0-9_]*" \]\]'
)


def shell_plants(text):
    """([(lineno, normalised_text, target, proven)], degraded) for one shell file."""
    rows, degraded = shell_rows(text)
    rows = logical_rows(rows)
    out = []
    for position, (index, code, mask) in enumerate(rows):
        match = None
        for pattern in (_SED_INPLACE, _PERL_INPLACE):
            found = pattern.search(code)
            if found is None:
                continue
            head = found.start() + (0 if code[found.start()] in "sp" else 1)
            if head < len(mask) and not mask[head]:
                match = found
            break
        if match is None:
            continue
        segment, segment_mask = command_segment(code, mask, match.start())
        if _PREFIX_SUB.search(segment):
            continue
        words = shell_words(segment, segment_mask)
        target = words[-1] if words else ""
        if target in ('"$@"', "$@"):
            continue
        needle_words = _words(segment, exclude=(target,))
        proven = _has_shell_proof(rows, position, target, needle_words)
        out.append((index, normalise(code), target, proven))
    return out, degraded


# Words a plant or a proof shares. Three characters is the floor: `-q`, `-i`, `-E` and the `s`/`d`/`g` of a sed expression are all shorter and would correlate everything with everything.
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_NOISE = frozenset(
    {"sed", "perl", "grep", "cmp", "diff", "awk", "then", "fail", "echo", "exit", "local"}
)

# A whole-file comparison needs no pattern correlation: it proves the bytes moved, whatever the needle was.
_WHOLE_FILE_PROOF = re.compile(
    r'\bcmp\b|\bdiff\b|\[\[ "\$[A-Za-z_][A-Za-z0-9_]*" == "\$[A-Za-z_][A-Za-z0-9_]*" \]\]'
)


def _words(text, exclude=()):
    excluded = set()
    for item in exclude:
        excluded |= {w.lower() for w in _WORD.findall(item)}
    return {
        w.lower()
        for w in _WORD.findall(text)
        if w.lower() not in _NOISE and w.lower() not in excluded
    }


def grep_pattern(code, mask):
    """The first non-flag operand after `grep`, i.e. the PATTERN. '' when absent."""
    words = shell_words(code, mask)
    for position, word in enumerate(words):
        if word.split("/")[-1] != "grep":
            continue
        for candidate in words[position + 1 :]:
            if candidate.startswith("-"):
                continue
            return candidate
        return ""
    return ""


def _has_shell_proof(rows, position, target, needle_words):
    """A proof must name the SAME target AND correlate with the SAME needle.

    THE CORRELATION IS THE HALF THIS GATE SHIPPED WITHOUT AND HAD TO ADD, and it was found by planting on the real tree rather than in a fixture. Stripping both proof lines off control (b) in `test-run-sh.sh` did NOT turn it red: control (c), six logical lines later, greps the SAME `"$ctl/legacy.sh"` copy
    for a completely different line, and a target-only rule let (c)'s proof
    launder (b)'s plant. A proof proves ONE mutation, and the thing that ties them together is the needle.

    A whole-file `cmp`/`diff`/`[[ "$a" == "$b" ]]` is accepted without
    correlation: it proves the bytes moved, whatever the needle was.
    """
    if not target:
        return False
    low = max(0, position - PROOF_WINDOW)
    high = min(len(rows), position + PROOF_WINDOW + 1)
    for other in range(low, high):
        if other == position:
            continue
        code, mask = rows[other][1], rows[other][2]
        if "<<<" in code or "$(" in code:
            continue
        if target not in code:
            continue
        if _WHOLE_FILE_PROOF.search(code):
            return True
        if not _PROOF.search(code):
            continue
        pattern = grep_pattern(code, mask)
        if pattern and needle_words and _words(pattern, exclude=(target,)) & needle_words:
            return True
    return False


# --------------------------------------------------------------------------- the typescript predicate ---------------------------------------------------------------------------


# A `/` opens a REGEX LITERAL rather than a division when the last significant character before it is one of these. Without this the lexer reads the three
# quotes in `/^(\w+)\s*=\s*"([^"]*)"/` as a string that never closes, and every
# line after it in the file is blanked. That is not hypothetical: it is why the first version of this arm scanned `check-backup-bucket-conformance.ts` and found NOTHING in the very control the arm exists for.
_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%~^<>") | {""}


def ts_rows(source):
    """[(lineno, code, comment, balanced)] with strings, regexes and comments blanked.

    `comment` is the raw comment text on that line, kept because a control region can be OPENED by a comment. `balanced` is False on the LAST row of a file whose quote, template or block-comment state never returned to neutral, which is the lexer reporting that it could not read the file rather than reporting a clean one.

    TEMPLATE LITERALS ARE NESTABLE and they nest through `${...}`, so the
    backtick state is a STACK of substitution depths and not a flag. Measured:
    a flag mis-read `${process.env.X ?? `${process.env.HOME}/.rediacc`}/staging`
    in packages/e2e-tests as a template that closed at the inner backtick, and blanked the remaining 200 lines of the file -- an UNDER-report, which is the dangerous direction for this gate.
    """
    out = []
    quote = None  # "'" or '"' when inside an ordinary string
    tmpl = []  # substitution depth per open template literal
    block_comment = False
    for index, raw in enumerate(source.split("\n"), 1):
        code = []
        comment = ""
        cursor = 0
        while cursor < len(raw):
            char = raw[cursor]
            pair = raw[cursor : cursor + 2]
            if block_comment:
                comment += char
                if pair == "*/":
                    block_comment = False
                    comment += "/"
                    cursor += 2
                    continue
                cursor += 1
                continue
            if quote is not None:
                if char == "\\":
                    code.append(" ")
                    if cursor + 1 < len(raw):
                        code.append(" ")
                    cursor += 2
                    continue
                if char == quote:
                    quote = None
                code.append(" ")
                cursor += 1
                continue
            if tmpl and tmpl[-1] == 0:
                # inside template TEXT (not a substitution)
                if char == "\\":
                    code.append(" ")
                    if cursor + 1 < len(raw):
                        code.append(" ")
                    cursor += 2
                    continue
                if pair == "${":
                    tmpl[-1] = 1
                    code.append(" ")
                    code.append(" ")
                    cursor += 2
                    continue
                if char == "`":
                    tmpl.pop()
                    code.append(" ")
                    cursor += 1
                    continue
                code.append(" ")
                cursor += 1
                continue
            # CODE, which includes the inside of a `${ ... }` substitution
            if pair == "//":
                comment += raw[cursor:]
                break
            if pair == "/*":
                block_comment = True
                cursor += 2
                continue
            if char == "/":
                prior = "".join(code).rstrip()
                if _opens_regex(prior):
                    cursor = _skip_regex(raw, cursor, code)
                    continue
            if char == "`":
                tmpl.append(0)
                code.append(" ")
                cursor += 1
                continue
            if char in "'\"":
                quote = char
                code.append(" ")
                cursor += 1
                continue
            if tmpl:
                if char == "{":
                    tmpl[-1] += 1
                elif char == "}":
                    tmpl[-1] -= 1
                    if tmpl[-1] == 0:
                        code.append(" ")
                        cursor += 1
                        continue
            code.append(char)
            cursor += 1
        out.append((index, "".join(code), comment, True))
    if out and (quote is not None or tmpl or block_comment):
        last = out[-1]
        out[-1] = (last[0], last[1], last[2], False)
    return out


# A `/` opens a REGEX LITERAL rather than a division when the last significant character before it is one of these, OR when the preceding word is a keyword that cannot be followed by division. Without the KEYWORD half the lexer read `return /['"]video['"]/.test(x)` as a division and then as an unterminated string, blanking the rest of
# `packages/www/scripts/check-solution-videos.ts`.
_REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%~^<>")
_REGEX_KEYWORDS = (
    "return",
    "typeof",
    "instanceof",
    "case",
    "throw",
    "new",
    "delete",
    "void",
    "in",
    "of",
    "do",
    "else",
    "yield",
    "await",
)


def _opens_regex(prior):
    if not prior:
        return True
    if prior[-1] in _REGEX_PRECEDERS:
        return True
    word = re.search(r"([A-Za-z_$][A-Za-z0-9_$]*)$", prior)
    return word is not None and word.group(1) in _REGEX_KEYWORDS


def _skip_regex(raw, cursor, code):
    """Blank a `/.../flags` literal. Returns the new cursor.

    A `[` class suspends the meaning of `/`, which is what makes `/[^/]*/` parse. An unterminated literal (a lone `/` the preceder heuristic guessed wrong about) blanks to end of line and no further.
    """
    code.append(" ")
    cursor += 1
    in_class = False
    while cursor < len(raw):
        char = raw[cursor]
        code.append(" ")
        if char == "\\":
            if cursor + 1 < len(raw):
                code.append(" ")
            cursor += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            cursor += 1
            while cursor < len(raw) and raw[cursor].isalpha():
                code.append(" ")
                cursor += 1
            return cursor
        cursor += 1
    return cursor


# A DECLARATION only. `^\s*NAME\s*\(` -- a bare call at line start -- was tried first and matched 482 "regions" across the 1049 tracked .ts files, which is every helper invocation in the tree.
_TS_NAMED_REGION = re.compile(r"\b(?:function|const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)")

# THE COMMENT MUST OPEN WITH THE MARKER, not merely contain the word. Measured: matching `control` anywhere in a comment turned every prose paragraph that says "the control below" into a region and produced 21 false positives, all of them ordinary parsing (`line.replace(/^\t+/, '')`).
_TS_COMMENT_REGION = re.compile(
    r"^[\s/*\u2500\u2502\u2014\-=+#]*(?:INSTRUMENT\s+)?(?:CONTROL|Control|SELFTEST|SelfTest|Selftest)\b"
)


def _is_control_name(name):
    """A declaration whose NAME says it is a control, or builds a control mutant.

    The second half is not decoration. `scripts/gates/check-guard-mutations.ts` reaches its `source.replace(m.find, m.replace)` from `applyMutation`, a helper the control calls rather than a control itself, and a rule keyed only on `control*`/`selftest*` walks straight past the one TypeScript site in this tree that already does the right thing -- which would leave the arm with a
    single positive and no proof that the PROVEN branch can ever be reached.
    """
    lowered = name.lower()
    if lowered.startswith(("selftest", "control", "plant")):
        return True
    return "mutant" in lowered or "mutation" in lowered


def ts_control_regions(rows):
    """[(start_index, end_index)] over `rows`, half-open, for control regions."""
    depths = []
    depth = 0
    for _, code, _, _ in rows:
        depths.append(depth)
        depth += code.count("{") + code.count("(") - code.count("}") - code.count(")")
    regions = []
    for position, (_, code, comment, _) in enumerate(rows):
        opener = False
        if comment and _TS_COMMENT_REGION.search(comment):
            opener = True
        else:
            found = _TS_NAMED_REGION.search(code)
            if found is not None:
                name = found.group(1) or found.group(2) or ""
                opener = _is_control_name(name)
        if not opener:
            continue
        base = depths[position]
        rose = False
        end = min(len(rows), position + TS_FLAT_REGION)
        for other in range(position + 1, min(len(rows), position + TS_MAX_REGION)):
            if depths[other] > base:
                rose = True
            elif rose and depths[other] <= base:
                end = other
                break
        else:
            if rose:
                end = min(len(rows), position + TS_MAX_REGION)
        regions.append((position, end))
    return _merge(regions)


def _merge(spans):
    out = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


_TS_REPLACE = re.compile(
    r"(?<![\w.$)\]])([A-Za-z_$][A-Za-z0-9_$]*)\.replace\(\s*([A-Za-z_$][A-Za-z0-9_$.]*)\s*,"
)


def ts_plants(source):
    """([(lineno, text, needle, proven)], balanced, region_count) for one .ts file.

    The region count comes back with the plants rather than being recomputed by the caller: lexing 1049 files twice cost three of the gate's six seconds.
    """
    rows = ts_rows(source)
    balanced = bool(rows) and rows[-1][3]
    regions = ts_control_regions(rows)
    out = []
    for start, end in regions:
        for position in range(start, end):
            index, code = rows[position][0], rows[position][1]
            found = _TS_REPLACE.search(code)
            if found is None:
                continue
            needle = found.group(2)
            proven = _has_ts_proof(rows, start, end, needle)
            out.append((index, normalise(code), needle, proven))
    return out, balanced, len(regions)


def _has_ts_proof(rows, start, end, needle):
    """An occurrence check on the SAME needle, anywhere in the same region."""
    if not needle:
        # A regex or inline literal needle. There is nothing to correlate, so a bare occurrence check in the region is not accepted as a proof for it.
        return False
    checks = (
        r"\.split\(\s*%s\s*\)" % re.escape(needle),
        r"\.indexOf\(\s*%s\s*\)" % re.escape(needle),
        r"\.match\(\s*%s\s*\)" % re.escape(needle),
        r"\.matchAll\(\s*%s\s*\)" % re.escape(needle),
        r"\.includes\(\s*%s\s*\)" % re.escape(needle),
    )
    for position in range(start, end):
        code = rows[position][1]
        for check in checks:
            if re.search(check, code):
                return True
    return False


# --------------------------------------------------------------------------- identity ---------------------------------------------------------------------------


def normalise(text):
    """Collapse whitespace runs. The id must survive reindentation, not rewrite."""
    return " ".join(text.split())


def finding_id(lang, rel, text, ordinal=0):
    """sha256 over language, path, NORMALISED TEXT and a duplicate ordinal.

    NEVER A LINE NUMBER: a line number churns when a paragraph moves above it, and a churning baseline gets reseeded wholesale, which is how a fresh finding gets absorbed.

    THE ORDINAL IS NOT A LINE NUMBER IN DISGUISE, and it exists because the first version of this file did not have one. `test-runner-advice.sh` plants `sed -i 's/"format": 1,/"format": 2,/' "$d/base.json"` at line 371 and again at line 505 -- byte-identical text in the same file. Keyed on text alone the two collapsed to one id, the seeded baseline read 24 where the scan reported
    25, and the second site was permanently invisible. The ordinal counts IDENTICAL texts within one file, so it is stable under any move that does not add or remove one of the duplicates.
    """
    payload = "\0".join((lang, rel, normalise(text), str(ordinal)))
    return hashlib.sha256(payload.encode("utf-8", "surrogateescape")).hexdigest()[:16]


# --------------------------------------------------------------------------- the corpus ---------------------------------------------------------------------------


def tracked_files(root):
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RefusalError(
            "git is not on PATH, so the tracked corpus this gate is built on cannot be "
            "enumerated. Install git, or run from a checkout."
        ) from exc
    if proc.returncode != 0:
        raise RefusalError(
            "`git ls-files` failed in %s (exit %d). Without a corpus there is no verdict, "
            "and reporting zero findings would be reporting zero inputs." % (root, proc.returncode)
        )
    return [p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def scan(root):
    """(plants, stats). `plants` is a list of dicts; every one carries its id."""
    root = pathlib.Path(root)
    files = tracked_files(root)
    if not files:
        raise RefusalError(
            "`git ls-files` returned ZERO paths, so this gate is not seeing the tree; "
            "its green would mean nothing"
        )
    plants = []
    unreadable = []
    stats = {"sh": 0, "ts": 0, "degraded": 0, "sh_total": 0, "ts_total": 0, "regions": 0}
    for rel in files:
        if rel.endswith(".sh"):
            source = _read(root / rel)
            if source is None:
                continue
            stats["sh"] += 1
            found, degraded = shell_plants(source)
            if degraded:
                stats["degraded"] += 1
            stats["sh_total"] += len(found)
            seen = {}
            for line, text, target, proven in found:
                ordinal = seen.get(text, 0)
                seen[text] = ordinal + 1
                plants.append(_row("bash", rel, line, text, target, proven, ordinal))
        elif rel.endswith(".ts") and not rel.endswith(".d.ts"):
            source = _read(root / rel)
            if source is None:
                continue
            stats["ts"] += 1
            found, balanced, regions = ts_plants(source)
            stats["regions"] += regions
            if not balanced:
                unreadable.append(rel)
            stats["ts_total"] += len(found)
            seen = {}
            for line, text, needle, proven in found:
                ordinal = seen.get(text, 0)
                seen[text] = ordinal + 1
                plants.append(_row("ts", rel, line, text, needle, proven, ordinal))
    if stats["sh"] == 0:
        raise RefusalError(
            "ZERO tracked .sh files were scanned. The shell arm of this gate is blind, "
            "and a green from a blind arm is worse than a red."
        )
    if stats["ts"] == 0:
        raise RefusalError(
            "ZERO tracked .ts files were scanned. The TypeScript arm of this gate is "
            "blind, and a green from a blind arm is worse than a red."
        )
    if unreadable:
        raise RefusalError(
            "the TypeScript lexer could not balance %d file(s), so their control regions "
            "were computed from BLANKED code and any plant in them was silently missed:\n"
            "%s\n"
            "  Under-reporting is the direction this gate must never take, so this is a "
            "refusal rather than a count. Teach `ts_rows` the construct it choked on."
            % (len(unreadable), "\n".join("    %s" % u for u in unreadable))
        )
    if stats["ts_total"] == 0:
        raise RefusalError(
            "ZERO TypeScript control plants found across %d tracked .ts file(s) and %d "
            "control region(s). Either `.replace()` with a NAMED needle has stopped being "
            "how this tree builds a control mutant, or the region detector has stopped "
            "recognising a control -- and in the second case the whole TypeScript arm is "
            "reporting a green it never earned. If the sites are genuinely gone, say so "
            "here rather than lowering the clause quietly." % (stats["ts"], stats["regions"])
        )
    ids = [row["id"] for row in plants]
    if len(set(ids)) != len(ids):
        raise RefusalError(
            "the id scheme COLLAPSED %d distinct plant(s) onto a shared key. A baseline "
            "keyed that way covers one site and silences the others invisibly, which is "
            "the failure the duplicate ordinal in `finding_id` exists to prevent."
            % (len(ids) - len(set(ids)))
        )
    if stats["sh_total"] == 0:
        raise RefusalError(
            "ZERO in-place shell mutations found across %d tracked .sh file(s). Either "
            "`sed -i`/`perl -i` has stopped being how this tree plants a defect, or the "
            "detector has stopped recognising it -- and in the second case every control "
            "in the repository reads as compliant." % stats["sh"]
        )
    return plants, stats


def _read(path):
    try:
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return None


def _row(lang, rel, line, text, subject, proven, ordinal=0):
    return {
        "id": finding_id(lang, rel, text, ordinal),
        "lang": lang,
        "file": rel,
        "line": line,
        "text": normalise(text)[:200],
        "subject": subject,
        "proven": proven,
    }


# --------------------------------------------------------------------------- the delegate ---------------------------------------------------------------------------


def python_delegate_state(root):
    """(exists, registered). Both must be true or the Python arm is a hole."""
    root = pathlib.Path(root)
    exists = (root / PYTHON_DELEGATE).is_file()
    manifest = root / "package.json"
    registered = False
    if manifest.is_file():
        try:
            scripts = json.loads(manifest.read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, ValueError):
            scripts = {}
        name = PYTHON_DELEGATE_ID.split(":", 1)[1]
        registered = PYTHON_DELEGATE in str(scripts.get("check:%s" % name, ""))
    return exists, registered


# --------------------------------------------------------------------------- the baseline ---------------------------------------------------------------------------

NOTE = (
    "SHRINK-ONLY, AND GENERATED -- do not hand-edit except to re-key a single row. "
    "Every entry is a control that PLANTS a defect by in-place mutation (bash) or by "
    "`.replace()` (TypeScript) and does NOT prove the plant landed. A plant whose needle "
    "has gone mutates nothing, so the control asserts the opposite verdict about "
    "identical input and passes for free. This list may only lose members: a NEW id is "
    "refused by .ci/scripts/quality/check_plant_proofs.py even when the total shrinks, "
    "because composition is the claim and a total is not. Drain it by ADDING THE PROOF "
    "and then running `--write-baseline`, never to make a red go away."
)


def baseline_path(root=None):
    """`<root>/.ci/config/plant-proof-baseline.json`, and DELIBERATELY no env override.

    An override would be an undeclared input (`check:ci-python-env-registry` would have to carry it) bought for nothing: every caller here already threads an explicit `root`, which is what the fixtures use.
    """
    return pathlib.Path(root or paths.repo_root()) / BASELINE_REL


def read_baseline(path):
    """{id: row} or None when the file is absent (which is STRICT MODE)."""
    path = pathlib.Path(path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RefusalError(
            "%s exists but cannot be read (%s). A corrupt baseline is not an empty one: "
            "treating it as empty would report every frozen plant as brand new. Repair "
            "the JSON; do not delete the file." % (BASELINE_REL, exc)
        ) from exc
    rows = data.get(KEY)
    if not isinstance(rows, list):
        raise RefusalError(
            "%s has no `%s` array. Refusing to guess what the frozen set was." % (BASELINE_REL, KEY)
        )
    out = {}
    for row in rows:
        if not isinstance(row, dict) or "id" not in row:
            raise RefusalError(
                "%s holds a row with no `id`. Every row is keyed on a hash of the "
                "finding's TEXT; a row without one cannot be matched to anything." % BASELINE_REL
            )
        out[str(row["id"])] = row
    return out


def evaluate(baseline, plants):
    """(findings, stats). Set equality in BOTH directions over the unproven set."""
    unproven = {row["id"]: row for row in plants if not row["proven"]}
    proven = [row for row in plants if row["proven"]]
    findings = []
    if baseline is None:
        findings.extend(_new_finding(row) for row in sorted(unproven.values(), key=_sortkey))
        return findings, {
            "unproven": len(unproven),
            "proven": len(proven),
            "baselined": 0,
            "drainable": 0,
        }
    added = [row for key, row in unproven.items() if key not in baseline]
    stale = [key for key in baseline if key not in unproven]
    findings.extend(_new_finding(row) for row in sorted(added, key=_sortkey))
    for key in sorted(stale, key=lambda k: (baseline[k].get("file", ""), k)):
        row = baseline[key]
        findings.append(
            "%s: the baselined plant `%s` no longer reports as unproven (id %s).\n"
            "      Either it now proves the plant landed, or it is gone. Either way the "
            "baseline has to shrink:\n"
            "        .ci/scripts/quality/check_plant_proofs.py --write-baseline\n"
            "      If you got here by EDITING the plant rather than proving it, the id "
            "re-keyed: hand-edit that one row instead of reseeding, or a blanket reseed "
            "will absorb every other writer's fresh finding."
            % (row.get("file", "?"), row.get("text", "?")[:120], key)
        )
    return findings, {
        "unproven": len(unproven),
        "proven": len(proven),
        "baselined": len(baseline),
        "drainable": len(stale),
    }


def _sortkey(row):
    return (row.get("file", ""), row.get("line", 0))


def _new_finding(row):
    if row["lang"] == "bash":
        fix = (
            "        grep -q '<the planted text>' %s || fail 'CONTROL PLANT DID NOT LAND'\n"
            "      or, before the mutation, assert the NEEDLE is there to be replaced."
            % (row["subject"] or '"$target"')
        )
        what = "mutates %s in place and never proves the mutation landed" % (
            row["subject"] or "a file"
        )
    else:
        fix = (
            "        const hits = <subject>.split(%s).length - 1;\n"
            "        if (hits !== 1) throw new Error('the needle is not there exactly once');"
            % (row["subject"] or "NEEDLE")
        )
        what = "builds a control mutant with .replace() and never counts the needle"
    return (
        "%s:%d  %s\n"
        "      %s\n"
        "      A needle that has gone leaves the fixture UNCHANGED, so the control "
        "asserts the opposite verdict about identical input and passes for free.\n"
        "      Add the proof:\n%s\n"
        "      Do NOT add it to %s. (id %s)"
        % (row["file"], row["line"], row["text"][:140], what, fix, BASELINE_REL, row["id"])
    )


# --------------------------------------------------------------------------- --write-baseline ---------------------------------------------------------------------------


def baseline_additions(old, new):
    """Keys `new` carries that `old` did not -- the DIFF half of the shrink-only guard.

    Named the way `.ci/scripts/quality/check_language_policy.py:442` names it, and extracted from the call site rather than left inline, because the composition gate, whose cases moved to `.ci/rediacc_ci/tests/gates/test_gate_shrink_only_composition.py` when W7 P5 retired the bash twin that carried them at `test-shrink-only-composition.sh:148`, requires a writer to DEFINE the
    diff, CALL the verdict, and compute both -- a writer that reseeds without a named diff can drain thirty findings, absorb
    one brand new one, and print a smaller number while doing it.
    """
    return [] if old is None else [k for k in new if k not in old]


def write_verdict(*, exists, first_seed, additions, allowed):
    """None means the write is allowed. Order is load-bearing: missing FIRST."""
    if not exists and not first_seed:
        return "missing-baseline"
    if not exists:
        return None
    unallowed = [key for key in additions if key not in set(allowed)]
    if unallowed:
        return "would-grow"
    bogus = [key for key in allowed if key not in set(additions)]
    if bogus:
        return "bogus-allow-new"
    return None


def write_baseline(root=None, *, first_seed=False, allowed=()):
    root = pathlib.Path(root or paths.repo_root())
    path = baseline_path(root)
    previous = read_baseline(path)
    exists = previous is not None
    plants, _ = scan(root)
    unproven = {row["id"]: row for row in plants if not row["proven"]}
    additions = baseline_additions(previous, unproven)
    verdict = write_verdict(
        exists=exists, first_seed=first_seed, additions=additions, allowed=allowed
    )
    if verdict is not None:
        log.error(
            _explain(verdict, additions, allowed, len(previous or {}), len(unproven), unproven)
        )
        return 1
    rows = [
        {
            "id": row["id"],
            "lang": row["lang"],
            "file": row["file"],
            "text": row["text"],
        }
        for row in sorted(unproven.values(), key=_sortkey)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"note": NOTE, KEY: rows}, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    log.success(
        "wrote %s: %d unproven plant(s), was %d" % (BASELINE_REL, len(rows), len(previous or {}))
    )
    return 0


def _explain(verdict, additions, allowed, previous, current, unproven):
    if verdict == "missing-baseline":
        return (
            "Refusing to write the baseline: %s does not exist.\n"
            "  With no previous baseline there is nothing to compare against, so all %d "
            "plant(s)\n  would be frozen as debt with no check on what is among them, and "
            "DELETING the file\n  is therefore the cheapest way to switch this rule off. If "
            "this really is a first\n  seed, say so: --write-baseline --first-seed."
            % (BASELINE_REL, current)
        )
    if verdict == "bogus-allow-new":
        bogus = [key for key in allowed if key not in set(additions)]
        return (
            "Refusing to write the baseline: %d --allow-new id(s) are not additions.\n%s\n"
            "  --allow-new admits a plant the scanner can SEE and that is not already "
            "frozen.\n  It is not a way to pre-load a row for a violation that does not "
            "exist." % (len(bogus), "\n".join("    %s" % b for b in bogus))
        )
    named = "\n".join(
        "    %s  %s:%s" % (key, unproven[key]["file"], unproven[key]["line"])
        for key in additions
        if key in unproven
    )
    return (
        "Refusing to write the baseline: it would GAIN %d unproven plant(s).\n%s\n\n"
        "  The baseline shrinks. It never grows. A reseed that drains 30 and adds 1 still\n"
        "  LOOKS like progress in the totals (%d -> %d), which is exactly how a brand new\n"
        "  vacuous control gets enshrined as permanent, invisible debt.\n\n"
        "  Add the proof instead. If a row genuinely belongs, type it:\n"
        "    --write-baseline %s"
        % (
            len(additions),
            named,
            previous,
            current,
            " ".join("--allow-new %s" % a for a in additions),
        )
    )


# --------------------------------------------------------------------------- the run ---------------------------------------------------------------------------


def run(root=None):
    root = pathlib.Path(root or paths.repo_root())
    exists, registered = python_delegate_state(root)
    if not exists:
        raise RefusalError(
            "the Python arm of this class is delegated to %s and that file is GONE. "
            "Python controls would be unscanned by every gate in the tree, with nothing "
            "said. Restore it, or absorb its predicate here." % PYTHON_DELEGATE
        )
    if not registered:
        raise RefusalError(
            "%s exists but package.json no longer runs it as `%s`. A delegate nothing "
            "invokes is a hole with a file in it." % (PYTHON_DELEGATE, PYTHON_DELEGATE_ID)
        )
    plants, stats = scan(root)
    baseline = read_baseline(baseline_path(root))
    findings, tally = evaluate(baseline, plants)
    stats.update(tally)
    return findings, stats


def main(argv=None):
    argv = list(argv or [])
    if "--selftest" in argv:
        return 1 if selftest() else 0
    if "--write-baseline" in argv:
        allowed = []
        for position, arg in enumerate(argv):
            if arg != "--allow-new":
                continue
            if position + 1 >= len(argv) or argv[position + 1].startswith("--"):
                log.error("--allow-new needs an <id> argument after it")
                return 1
            allowed.append(argv[position + 1])
        try:
            return write_baseline(first_seed="--first-seed" in argv, allowed=allowed)
        except RefusalError as exc:
            log.error("plant proofs: %s" % exc)
            return 1
    rc = controls_first("plant proofs", selftest)
    if rc:
        return rc
    try:
        findings, stats = run()
    except RefusalError as exc:
        log.error("plant proofs: %s" % exc)
        return 1
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error(
            "%d finding(s): a control that plants a defect must prove the plant landed."
            % len(findings)
        )
        return 1
    log.success(
        "plant proofs: %d plant(s) across %d tracked .sh + %d tracked .ts "
        "(%d TS control region(s)); %d prove the plant landed, %d frozen in %s, "
        "%d shell file(s) scanned degraded; python delegated to %s"
        % (
            stats["sh_total"] + stats["ts_total"],
            stats["sh"],
            stats["ts"],
            stats["regions"],
            stats["proven"],
            stats["baselined"],
            BASELINE_REL,
            stats["degraded"],
            PYTHON_DELEGATE_ID,
        )
    )
    return 0


# --------------------------------------------------------------------------- controls
#
# BOTH DIRECTIONS EVERYWHERE. A gate with only positive controls will happily flag the whole tree, and this one has two detectors and a baseline, so each of the three gets a must-fire case AND a must-not-fire case. Every mutant below is built with `rediacc_ci.controls.plant`, which raises when the needle is gone -- the Python spelling of the rule this file enforces on bash and .ts.
# ---------------------------------------------------------------------------

_SH_PLAIN = """#!/usr/bin/env bash
cp "$REAL" "$tmp/copy.sh"
sed -i 's/NEEDLE/PLANTED/' "$tmp/copy.sh"
run_gate "$tmp/copy.sh"
"""

_SH_QUOTED = """#!/usr/bin/env bash
# a comment mentioning sed -i, which is prose and not a command
grep -qE 'something|sed -i' "$f"
log_pass "no file names sed -i outside the seam"
rows=('sed -i "s/a/b/" f' 'readlink -f f')
"""

_SH_HEREDOC = """#!/usr/bin/env bash
cat >"$tmp/inner.sh" <<'EOF'
sed -i 's/a/b/' /etc/hosts
EOF
echo done
"""

_TS_PLAIN = """const fixture = readFileSync('f', 'utf8');
// CONTROL: the extractor, both directions, before it is trusted
{
  const NEEDLE = 'binding = "X"';
  const broken = extract(fixture.replace(NEEDLE, ''));
  if (broken !== null) throw new Error('control did not fire');
}
export function parse(line: string): string {
  return line.replace(SUFFIX, '');
}
"""

_TS_TRICKY = """const p = `${process.env.HOME ?? `${ROOT}/fallback`}/x`;
function probe(src: string): boolean {
  return /CephImagePin\\s*=\\s*"([^"]+)"/.test(src);
}
// CONTROL: a region whose needle IS counted
{
  const N = 'a';
  const hits = src.split(N).length - 1;
  if (hits !== 1) throw new Error('needle gone');
  use(src.replace(N, 'b'));
}
"""

_STUB_DELEGATE = '"""stub"""\n'


def _sh_unproven(source):
    return [row for row in shell_plants(source)[0] if not row[3]]


def _fixture(tmp, *, sh=_SH_PLAIN, ts=_TS_PLAIN, baseline=None, delegate=True, scripts=None):
    """A real git repository, because `scan` reads `git ls-files`."""
    root = pathlib.Path(tmp)
    (root / "s").mkdir(parents=True, exist_ok=True)
    (root / "s" / "gate.sh").write_text(sh, encoding="utf-8")
    (root / "s" / "gate.ts").write_text(ts, encoding="utf-8")
    if delegate:
        target = root / PYTHON_DELEGATE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_STUB_DELEGATE, encoding="utf-8")
    if scripts is None:
        scripts = {PYTHON_DELEGATE_ID: PYTHON_DELEGATE}
    (root / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    if baseline is not None:
        path = root / BASELINE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"note": NOTE, KEY: baseline}), encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A", "-f"]):
        subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)
    return root


def _quiet(fn, *args, **kwargs):
    """Run `fn`, returning `(result, everything it logged)` and printing none of it."""
    import io  # noqa: PLC0415

    buf = io.StringIO()
    log.reset(stream=buf, colour=False)
    try:
        return fn(*args, **kwargs), buf.getvalue()
    finally:
        log.reset()


def _refuses(root):
    try:
        run(root)
    except RefusalError as exc:
        return str(exc)
    return ""


def selftest():
    """True when a control FAILED, which is what `controls_first` expects."""
    import tempfile  # noqa: PLC0415

    from rediacc_ci.controls import Checker, plant  # noqa: PLC0415

    check = Checker()

    # -- the shell detector, must fire --------------------------------------
    check(
        "SHELL PLANT: a `sed -i` with no proof anywhere near it is a finding",
        len(_sh_unproven(_SH_PLAIN)) == 1,
    )
    check(
        "SHELL PLANT: and the target is the file, not the sed expression",
        _sh_unproven(_SH_PLAIN)[0][2] == '"$tmp/copy.sh"',
    )
    check(
        "SHELL PLANT: `perl -pi -e` counts as an in-place mutation too",
        len(_sh_unproven(plant(_SH_PLAIN, "sed -i 's/NEEDLE/PLANTED/'", "perl -pi -e 's/N/P/'")))
        == 1,
    )

    # -- the shell detector, must NOT fire ----------------------------------
    after = plant(
        _SH_PLAIN,
        'run_gate "$tmp/copy.sh"',
        'grep -q PLANTED "$tmp/copy.sh" || fail "CONTROL PLANT DID NOT LAND"\nrun_gate x',
    )
    check(
        "SHELL PROOF: a post-mutation grep of the SAME target clears it", _sh_unproven(after) == []
    )
    before = plant(
        _SH_PLAIN,
        "sed -i",
        'grep -q NEEDLE "$tmp/copy.sh" || fail "PLANT DID NOT LAND"\nsed -i',
    )
    check(
        "SHELL PROOF: a pre-mutation grep for the NEEDLE clears it too", _sh_unproven(before) == []
    )
    herestring = plant(
        _SH_PLAIN,
        'run_gate "$tmp/copy.sh"',
        'grep -q PLANTED <<<"$(run_gate "$tmp/copy.sh")"',
    )
    check(
        'SHELL PROOF: a `grep -q ... <<<"$(gate ...)"` is the control\'s VERDICT, '
        "not a proof, and does NOT clear it",
        len(_sh_unproven(herestring)) == 1,
    )

    launder = plant(
        _SH_PLAIN,
        'run_gate "$tmp/copy.sh"',
        'grep -q UNRELATED "$tmp/copy.sh" || fail "a DIFFERENT control\'s proof"',
    )
    check(
        "SHELL PROOF: a neighbouring control's grep of the SAME file for a DIFFERENT "
        "needle does not launder this plant (found by planting on the real tree)",
        len(_sh_unproven(launder)) == 1,
    )
    whole = plant(
        _SH_PLAIN,
        'run_gate "$tmp/copy.sh"',
        'cmp -s "$REAL" "$tmp/copy.sh" && fail "the plant changed nothing"',
    )
    check(
        "SHELL PROOF: a whole-file `cmp` needs no needle correlation, because it "
        "proves the bytes moved whatever the needle was",
        _sh_unproven(whole) == [],
    )

    # -- the shell exemptions ------------------------------------------------
    check(
        "SHELL EXEMPT: `s/^/.../` always matches, so it cannot go vacuous",
        _sh_unproven(plant(_SH_PLAIN, "s/NEEDLE/PLANTED/", "s/^/    /")) == [],
    )
    check(
        'SHELL EXEMPT: a pass-through wrapper `sed -i "$@"` carries no needle',
        _sh_unproven(plant(_SH_PLAIN, "'s/NEEDLE/PLANTED/' \"$tmp/copy.sh\"", '"$@"')) == [],
    )
    check(
        "SHELL LEXER: `sed -i` inside quotes or a comment is prose, not a command",
        shell_plants(_SH_QUOTED)[0] == [],
    )
    check(
        "SHELL LEXER: `sed -i` inside a heredoc BODY is data, not a command",
        shell_plants(_SH_HEREDOC)[0] == [],
    )
    segmented = '#!/usr/bin/env bash\nfor e in "$@"; do sed -i "$e" "$dst"; done\n'
    check(
        'SHELL TARGET: a `;`-separated segment yields "$dst", not the word `done`',
        _sh_unproven(segmented)[0][2] == '"$dst"',
    )
    check(
        "SHELL LEXER: an unbalanced file is scanned DEGRADED rather than skipped",
        shell_rows('x="open\n' + _SH_PLAIN)[1] is True,
    )

    # -- the typescript detector, both directions ---------------------------
    ts_rows_plain = ts_plants(_TS_PLAIN)[0]
    check(
        "TS PLANT: a `.replace(NEEDLE, ...)` in a control region is a finding",
        len(ts_rows_plain) == 1,
    )
    check("TS PLANT: and the needle is named in the finding", ts_rows_plain[0][2] == "NEEDLE")
    check(
        "TS SCOPE: the SAME call outside a control region is invisible (it is parsing)",
        all(row[0] != 9 for row in ts_rows_plain),
    )
    counted = plant(
        _TS_PLAIN,
        "  const broken = extract(",
        "  const hits = fixture.split(NEEDLE).length - 1;\n"
        "  if (hits !== 1) throw new Error('needle gone');\n"
        "  const broken = extract(",
    )
    check(
        "TS PROOF: an occurrence check on the SAME needle clears it",
        [row for row in ts_plants(counted)[0] if not row[3]] == [],
    )
    check(
        "TS PROOF: a count of a DIFFERENT needle does NOT clear it",
        len(
            [
                row
                for row in ts_plants(
                    plant(counted, "fixture.split(NEEDLE)", "fixture.split(OTHER)")
                )[0]
                if not row[3]
            ]
        )
        == 1,
    )
    tricky = ts_rows(_TS_TRICKY)
    check("TS LEXER: a nested template literal does not unbalance the file", tricky[-1][3] is True)
    check(
        "TS LEXER: `return /re/.test(x)` is a regex, not a division into a string",
        tricky[-1][3] is True and "CephImagePin" not in tricky[2][1],
    )
    check(
        "TS PROOF: the tricky fixture's counted region is clean",
        [row for row in ts_plants(_TS_TRICKY)[0] if not row[3]] == [],
    )

    # -- identity ------------------------------------------------------------
    first = finding_id("bash", "a.sh", "sed -i 's/a/b/' f")
    check(
        "ID: survives a MOVE (reindentation changes nothing)",
        finding_id("bash", "a.sh", "        sed -i 's/a/b/'   f") == first,
    )
    check(
        "ID: re-keys on a REWRITE, which is when a human should look again",
        finding_id("bash", "a.sh", "sed -i 's/a/c/' f") != first,
    )
    check(
        "ID: a different file is a different finding",
        finding_id("bash", "b.sh", "sed -i 's/a/b/' f") != first,
    )
    check(
        "ID: two BYTE-IDENTICAL plants in one file get two ids, not one",
        finding_id("bash", "a.sh", "sed -i 's/a/b/' f", 1) != first,
    )
    with tempfile.TemporaryDirectory() as tmp:
        twice = _SH_PLAIN + "sed -i 's/NEEDLE/PLANTED/' \"$tmp/copy.sh\"\n"
        root = _fixture(tmp, sh=twice)
        plants, _ = scan(root)
        check(
            "ID: and the corpus reports BOTH of them (the 2026-09-09 collapse, as a fixture)",
            len([r for r in plants if r["lang"] == "bash"]) == 2
            and len({r["id"] for r in plants}) == len(plants),
        )

    # -- the corpus, the baseline and the refusals ---------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        findings, stats = run(root)
        check("CORPUS: an unbaselined unproven plant is reported", len(findings) == 2)
        check(
            "CORPUS: and the scan is NOT trivially empty",
            (stats["sh"], stats["ts"], stats["sh_total"], stats["ts_total"]) == (1, 1, 1, 1),
        )
        check(
            "CORPUS: the failure names the fix, not just a count",
            any("CONTROL PLANT DID NOT LAND" in f for f in findings)
            and any("Do NOT add it to" in f for f in findings),
        )

        plants, _ = scan(root)
        rows = [
            {"id": r["id"], "lang": r["lang"], "file": r["file"], "text": r["text"]}
            for r in plants
            if not r["proven"]
        ]
        (root / BASELINE_REL).parent.mkdir(parents=True, exist_ok=True)
        (root / BASELINE_REL).write_text(json.dumps({"note": NOTE, KEY: rows}), encoding="utf-8")
        findings, _ = run(root)
        check("BASELINE: a frozen plant is not reported again", findings == [])

        (root / BASELINE_REL).write_text(
            json.dumps({"note": NOTE, KEY: rows[:1]}), encoding="utf-8"
        )
        findings, _ = run(root)
        check(
            "BASELINE: DELETING a row whose plant still has no proof RE-REPORTS it",
            len(findings) == 1,
        )

        (root / BASELINE_REL).write_text(
            json.dumps(
                {
                    "note": NOTE,
                    KEY: [*rows, {"id": "0" * 16, "lang": "bash", "file": "ghost.sh", "text": "x"}],
                }
            ),
            encoding="utf-8",
        )
        findings, _ = run(root)
        check(
            "BASELINE: a row nothing matches is a finding too, so it cannot be pre-banked",
            len(findings) == 1 and "no longer reports as unproven" in findings[0],
        )
        check(
            "BASELINE: and the drain instruction names --write-baseline",
            "--write-baseline" in findings[0],
        )

    # -- --write-baseline, the composition trap ------------------------------
    check(
        "WRITE: no baseline and no --first-seed is refused",
        write_verdict(exists=False, first_seed=False, additions=[], allowed=[])
        == "missing-baseline",
    )
    check(
        "WRITE: --first-seed is how a first seed is typed",
        write_verdict(exists=False, first_seed=True, additions=[], allowed=[]) is None,
    )
    check(
        "WRITE: a blanket reseed that would ADD one row is refused, however much it drains",
        write_verdict(exists=True, first_seed=False, additions=["aa"], allowed=[]) == "would-grow",
    )
    check(
        "WRITE: --allow-new admits exactly the row it names",
        write_verdict(exists=True, first_seed=False, additions=["aa"], allowed=["aa"]) is None,
    )
    check(
        "WRITE: --allow-new for a row that is NOT an addition is refused",
        write_verdict(exists=True, first_seed=False, additions=[], allowed=["aa"])
        == "bogus-allow-new",
    )
    check(
        "WRITE: a pure drain is allowed",
        write_verdict(exists=True, first_seed=False, additions=[], allowed=[]) is None,
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, baseline=[])
        rc, said = _quiet(write_baseline, root)
        check("WRITE: the drive path refuses a growing reseed with exit 1", rc == 1)
        check(
            "WRITE: and the refusal names the composition trap, not just the totals",
            "drains 30 and adds 1" in said and "--allow-new" in said,
        )

    # -- the refusals --------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, delegate=False)
        check(
            "VACUITY: the Python delegate missing is a REFUSAL, not a silent hole",
            "delegated" in _refuses(root),
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, scripts={})
        check(
            "VACUITY: the delegate present but UNREGISTERED is a refusal too",
            "package.json no longer runs it" in _refuses(root),
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, sh="#!/usr/bin/env bash\necho hi\n")
        check(
            "VACUITY: zero shell plants in the whole corpus is a REFUSAL",
            "ZERO in-place shell mutations" in _refuses(root),
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, ts="export const x = 1;\n")
        check(
            "VACUITY: zero TypeScript plants in the whole corpus is a REFUSAL",
            "ZERO TypeScript control plants" in _refuses(root),
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, ts="const s = `${`unclosed;\n// CONTROL\nx.replace(N, '');\n")
        check(
            "VACUITY: a .ts the lexer cannot balance is a REFUSAL, because blanked "
            "code UNDER-reports",
            "could not balance" in _refuses(root),
        )

    return not check.ok
