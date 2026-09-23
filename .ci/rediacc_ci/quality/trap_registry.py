r"""docs/agent-reference/TRAPS.md is a REGISTRY, not a pile of prose.

Ported from `.ci/scripts/quality/check-trap-registry.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__`.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED ACROSS.
-----------------------------------------------------------------------------

Gate: every `## ` entry declares which instrument enforces it, that pointer resolves, and that instrument is LIVE.

WHY THIS EXISTS. A trap that names no enforcement is indistinguishable from one that is fully mechanized, so the unprotected surface cannot be measured and the stop-hook judge briefs every session from headings it is already protected against. `agent/plans/PLAN-trap-enforcement.md` section 3 is the specification; this is its W1.

THE HAZARD THE PLAN NAMES, AND WHY LIVENESS IS THE POINT (plan section 3.2): "a gate that demands every trap name an enforced_by creates pressure to name one, and the cheapest thing to name is a grep that pattern-matches the trap's title." A gate that only checked PRESENCE would industrialize the corpus's own most expensive entry, manufacturing checks that cannot fail at a rate of
one per trap and reporting 100% coverage while doing it. So every pointer is checked twice: it must RESOLVE (F4) and it must be LIVE (F5).

ASSERTIONS
  F1  POPULATION FLOOR. At least TRAP_FLOOR entries. An emptied, truncated or
      relocated corpus reds instead of passing vacuously.
  F2  IDENTITY. Every entry carries a Trap-Id; ids are unique and match
      ^[a-z0-9][a-z0-9-]{2,48}$.
  F3  DISPOSITION. Every entry carries an Enforced-By and a Residue LINE. The
      disposition is either >=1 pointer or the single token JUDGMENT-ONLY, and
      JUDGMENT-ONLY requires a non-empty Residue.
  F4  POINTERS RESOLVE. gate: exists in the ci-runner manifest AND in
      package.json; hook: exists in the trapguard dispatcher's RULES tuple;
      file: exists on disk, and its :line is within the file and non-blank.
  F5  POINTERS ARE LIVE.
        gate: the manifest entry declares `gate: true`, i.e. `npm run ci`
              actually schedules it. This is the same claim
              wl_reggate.gate_reachable makes: `ci` is the ci-runner
              dispatcher, so manifest membership IS reachability.
        hook: the rule has BOTH a firing case and a silent case in the hook
              suite. One-sided coverage is how a rule that always fires, or
              never fires, passes as covered.
        file: the file is reachable from something that runs it, in at most
              two hops from .claude/settings.json or the ci-runner manifest.
  F6  SELF-CONTROL, FIRST. Every assertion above is planted against a mktemp
      fixture and required to red WITH THE MATCHING MESSAGE, and two clean
      fixtures are required to stay green. If any control misbehaves the gate
      exits non-zero WITHOUT judging the real tree. The count is printed rather
      than written here, because a hardcoded count decays silently.

DEVIATIONS FROM THE PLAN, CHOSEN AND STATED (plan section 3.1 left these open):
  * The plan's pointer grammar is `gate:` / `hook:` / `suite:<harness>#<case>`.
    `suite:` is NOT implemented, because the one entry that would use it points
    at a case inside .claude/hooks/stop/worklist-cases/, and
    `file:<path>:<line>` already resolves and proves liveness for it through the
    same two-hop rule. A third pointer kind with its own resolution path would
    be one more thing to get wrong for zero extra coverage. Add it when
    something needs it.
  * `file:<path>` without a line is accepted, and is the preferred form for a
    whole guard script: the script IS the instrument, and a line number there
    would decay on every edit for no gain. Use `file:<path>:<line>` only when
    one specific site is the enforcement.
  * F3b (a `block`-tier hook rule must declare certain_failure or a policy) is
    NOT implemented: the trapguard dispatcher has no tiers today. Every rule is
    a PostToolUse injector that cannot deny anything, so there is no block tier
    to police. Restore F3b in the same commit that adds one.

-----------------------------------------------------------------------------
THE RATCHET, AND WHY THE FLOOR IS A CONSTANT AND NOT A DERIVED NUMBER.
-----------------------------------------------------------------------------

A RATCHET, not a target. 48 entries on 2026-08-27, 49 on 2026-08-28. Raising it is the only direction that keeps meaning something: lowering it to get past a red is how a corpus shrinks silently, so lowering it requires saying why, out loud, in the commit that does it.

THE RATCHET MUST MOVE WITH THE CORPUS, and this is what it costs when it does not. Commit 0b47292e1 added a 49th entry and left the floor at 48, so F1's control -- delete one entry, expect a red -- landed on exactly 48, which is not BELOW 48. The gate stopped being able to detect a deletion at all, and CI reported it as "a shrinking corpus must red (F1): expected 1, got 0". An
unratcheted floor does not merely lag; it disarms the check it belongs to.

AND IT HAPPENED AGAIN, 2026-08-31, with the paragraph above already on the page: `mark-done-all-stale-is-a-bulk-verb` became the 50th entry and the floor stayed at 49, producing the identical CI line. `check:ci-trap-registry` was GREEN throughout -- a floor only fails when the corpus is below it, so an unratcheted floor is invisible to the gate and visible only to its own control.
Adding an entry means bumping this number in the same commit; there is no other signal.

THAT IS ALSO WHY THE FLOOR IS NOT DERIVED FROM THE CORPUS. A floor computed
from the file it guards cannot fail, which is the whole class of defect this
estate exists to refuse. It is a written number, moved by hand, in the commit that adds an entry, and the twin and this port must carry the SAME number: it was 75, then 76, then 77 within one session on 2026-09-06 as two entries landed. Read `.ci/scripts/quality/check-trap-registry.sh` line 108 before changing it here; a differential over a fixture corpus cannot see a divergence in
the default, because every fixture sets `TRAP_FLOOR` explicitly.

-----------------------------------------------------------------------------
THE OTHER INLINE NOTES, carried across.
-----------------------------------------------------------------------------

THE PARSER TRACKS FENCED CODE BLOCKS for the reason the plan gives at section 3.1: once every `## ` entry must carry a Trap-Id, a `## ` inside a fenced example in a trap body becomes a phantom entry with no id, and the gate reds on a document that is correct. Trap bodies routinely carry markdown examples. Trailer lines are read only from the block between the heading and the first
blank line, so a body paragraph beginning "Residue:" is body.

US (0x1f) RATHER THAN TAB as the field separator: tab is IFS whitespace in bash, so a run of two tabs COLLAPSES and an entry with an empty Residue silently reads as an entry with no Residue LINE. Found by the clean-corpus control going red.

`gate_is_live` IS SCOPED TO THE BLOCK between this id and the next one, or a neighbouring entry's `gate: true` would answer for it.

`hook_resolves` DEMANDS BOTH a definition and a listing in RULES. A defined-but-unlisted rule is dead code that never runs, which is the whole hazard.

A SUITE CASE IS ATTRIBUTED TO A RULE when the string it asserts on appears in that rule's body: the needle is text the rule PRODUCES, so matching it is evidence the case exercises that rule and not a neighbour. Attribution by section order alone would credit any rule with its neighbour's coverage. Firing cases carry the needle as their last quoted argument; silent cases carry no
needle at all, so they are attributed to the most recent firing case that resolved to a rule. That is the file's actual layout (one rule per contiguous block) and it fails SAFE: an unattributable silent case credits nobody rather than crediting the wrong rule. The suite writes them across continuation lines, so an unjoined read would see every needle as belonging to no call at all.

TWO HOPS IS THE WHOLE RULE for `file:` liveness, deliberately: hop 1 is a file named in settings.json or the manifest (registered hook, gate script, gate-test), so something runs it directly; hop 2 is a file named by a hop-1 file (a lib a guard sources, a case file a suite runner globs in, a gate a gate-test drives). A deeper closure would eventually call anything reachable from
anything "live", which is how a liveness check stops meaning anything.

F1 IS CHECKED LAST so a truncated corpus reports its content problems too. Zero entries is a FAILURE, never a pass: a gate that saw nothing has verified nothing.

NOT `return "$errors"`. A shell return is taken mod 256, so exactly 256 findings would return 0 and read as a clean scan. Only the STATUS is made boolean; the count itself is still printed with the findings.

A RED CONTROL MUST RED FOR THE RIGHT REASON. Three plants in a neighbouring session were themselves invalid and still "passed" as controls, so the needle is mandatory: a fixture that reds because its filler count is wrong proves nothing about the assertion it was written for.

THE UNRATCHETED-FLOOR ADVISORY IS AN ADVISORY, NOT A FAILURE, because making it
fatal means asserting `n_entries == TRAP_FLOOR`, and several of the control
fixtures are deliberately built at floor+1 to exercise other rules. Tightening it means auditing every one of those first; the line costs nothing and puts the number in the sub-second lane where the mistake is made. Without it the signal arrives ~45 minutes later, from CI, as "a shrinking corpus must red (F1): expected 1, got 0", which names neither the floor nor the entry that
moved.

`--scan-only` EXISTS FOR THE GATE TEST and for debugging a single fixture: it runs the scan WITHOUT the controls. Nothing in package.json or CI uses it, deliberately. The controls are not an option on the real run.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE US SEPARATOR IS GONE, and that is the one deliberate shape change. It exists
only because the twin passes six fields through `IFS=$'\037' read`, and Python
returns a tuple. The BUG it was introduced to fix -- an empty Residue collapsing into "no Residue line" -- cannot occur here, because `residue` and `residue_seen` are separate values rather than adjacent fields in a string. The comment is kept so the next reader knows why the bash looks the way it does.

`case " $seen_ids " in *" $id "*)` IS A SUBSTRING TEST WITH SPACE PADDING, which is the shell's idiom for set membership. A `set` is the same claim without the padding, and the padding is what stops `foo` from matching inside `foobar`.

`for ptr in ${enf//,/ }` IS WORD SPLITTING, so a disposition is split on BOTH
commas and whitespace, and repeated separators collapse. `str.replace(",", " ")` then `.split()` is exactly that.

`[[ "$enf" == *JUDGMENT-ONLY* ]]` FIRES ON A SUBSTRING, so
`Enforced-By: JUDGMENT-ONLY, gate:x` is caught as a MIX even though the first branch already tested for equality. The order of those two branches is the contract.

`grep -qF "id: '$1'," MANIFEST && grep -qF "\"$1\":" PACKAGE_JSON` is a FIXED STRING search including the trailing comma and the closing quote-colon, so a prefix id cannot satisfy a longer one. Both halves are required, and that is F4
for a `gate:` pointer.

`wc -l <file` COUNTS NEWLINES, so a `file:path:N` pointing at the last line of a file with no final newline is out of range. That is the twin's arithmetic and it is preserved; see `rediacc_ci.quality.shell_size` for the same point.

`[ -n "${text// /}" ]` STRIPS ONLY SPACES, not tabs, so a tab-only line counts
as non-blank. Carried unchanged, because narrowing it would re-decide which `file:` pointers resolve.

STREAMS. `err()` is `log_error` (stderr, `✗ <msg>`) plus a counter; the shape line and the ratchet advisory are `log_info` (stderr, `✓ <msg>`). `rediacc_ci.log` reproduces both.
"""

import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The corpus and the artifacts pointers resolve against. Every one is a seam so the controls can drive the whole gate against fixtures instead of the real tree. The environment variable names are the twin's.
SEAMS = {
    "TRAP_CORPUS": ("docs", "agent-reference", "TRAPS.md"),
    "TRAP_MANIFEST": ("scripts", "ci-runner", "manifest.ts"),
    "TRAP_PACKAGE_JSON": ("package.json",),
    "TRAP_DISPATCH": (".claude", "hooks", "trapguard", "dispatch.py"),
    # THE SUITE MOVED, AND THE SPELLING DID NOT. `hook_is_live` asks whether a trapguard rule has both a firing and a silent `check_inject` case; those cases were ported out of `.claude/hooks/test-hooks.sh` into this module, which keeps `check_inject fires` / `check_inject silent` and the needle as the LAST quoted argument on the same line for exactly this reader. Its own docstring
    # records the formatter accident that separated the two and turned all five rules one-sided, so the shape is deliberate on both ends.
    "TRAP_HOOK_SUITE": (".claude", "rediacc_hooks", "tests", "test_hooks_trapguard.py"),
    "TRAP_SETTINGS": (".claude", "settings.json"),
    "TRAP_FILE_ROOT": (),
}

# THE RATCHET. A written number, moved by hand; see the header for why it is not derived and for the two occasions an unratcheted floor disarmed F1's control. Must equal `.ci/scripts/quality/check-trap-registry.sh` line 108.
TRAP_FLOOR_DEFAULT = 96

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,48}$")


class Entry:
    """One `## ` heading and its three-line trailer."""

    __slots__ = ("enforced_by", "line", "residue", "residue_seen", "title", "trap_id")

    def __init__(
        self,
        line: int,
        trap_id: str,
        enforced_by: str,
        residue: str,
        residue_seen: bool,
        title: str,
    ) -> None:
        self.line = line
        self.trap_id = trap_id
        self.enforced_by = enforced_by
        self.residue = residue
        self.residue_seen = residue_seen
        self.title = title


FENCE_RE = re.compile(r"^[ \t]*(```+|~~~+)")


def parse_corpus(text: str) -> list[Entry]:
    """The `## ` entries, skipping anything inside a fenced code block.

    Shared shape with wl_store.trap_headings. Trailer lines are read only from the block between the heading and the first blank line.
    """
    entries: list[Entry] = []
    fence = ""
    current: Entry | None = None
    in_trailer = False
    for number, line in enumerate(text.split("\n"), start=1):
        match = FENCE_RE.match(line)
        if match:
            marker = re.sub(r"[ \t]", "", match.group(0))
            char = marker[0]
            fence = char if fence == "" else ("" if fence == char else fence)
            continue
        if fence != "":
            continue
        if line.startswith("## ") and not line.startswith("### "):
            if current is not None:
                entries.append(current)
            current = Entry(number, "", "", "", False, line[3:])
            in_trailer = True
            continue
        if in_trailer and current is not None:
            if line == "":
                in_trailer = False
                continue
            if line.startswith("Trap-Id:"):
                current.trap_id = line[8:].lstrip(" ")
                continue
            if line.startswith("Enforced-By:"):
                current.enforced_by = line[12:].lstrip(" ")
                continue
            if line.startswith("Residue:"):
                current.residue = line[8:].lstrip(" ")
                current.residue_seen = True
                continue
            in_trailer = False
    if current is not None:
        entries.append(current)
    return entries


def read_text(path: pathlib.Path) -> str:
    """A file's contents, or "" when it cannot be read."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


class Registry:
    """The five artifacts a pointer resolves against, resolved once."""

    def __init__(self, seams: dict[str, pathlib.Path]) -> None:
        self.corpus = seams["TRAP_CORPUS"]
        self.manifest = seams["TRAP_MANIFEST"]
        self.package_json = seams["TRAP_PACKAGE_JSON"]
        self.dispatch = seams["TRAP_DISPATCH"]
        self.hook_suite = seams["TRAP_HOOK_SUITE"]
        self.settings = seams["TRAP_SETTINGS"]
        self.file_root = seams["TRAP_FILE_ROOT"]
        self._live_l1: list[pathlib.Path] | None = None

    # -- F4/F5 for `gate:` --------------------------------------------------

    def gate_resolves(self, gate_id: str) -> bool:
        """The manifest declares this id AND package.json defines the script."""
        return "id: '%s'," % gate_id in read_text(self.manifest) and (
            '"%s":' % gate_id in read_text(self.package_json)
        )

    def gate_is_live(self, gate_id: str) -> bool:
        """`gate: true` inside THIS entry's block, not a neighbour's."""
        want = "id: '%s'," % gate_id
        in_block = False
        for line in read_text(self.manifest).split("\n"):
            if not in_block:
                if want in line:
                    in_block = True
                continue
            if "id: '" in line:
                return False
            if "gate: true" in line:
                return True
        return False

    # -- F4/F5 for `hook:` --------------------------------------------------

    def hook_resolves(self, rule: str) -> bool:
        """The dispatcher DEFINES the rule and LISTS it in RULES."""
        fn = "rule_%s" % rule.replace("-", "_")
        text = read_text(self.dispatch)
        if not re.search(r"(?m)^def %s\(" % re.escape(fn), text):
            return False
        in_block = False
        for line in text.split("\n"):
            if not in_block:
                if line.startswith("RULES = ("):
                    in_block = True
                continue
            if line.startswith(")"):
                return False
            if fn in line:
                return True
        return False

    def rule_body(self, rule: str) -> str:
        """The rule's own source text, up to the next `def` or `RULES =`."""
        fn = "rule_%s" % rule.replace("-", "_")
        start_re = re.compile(r"^def %s\(" % re.escape(fn))
        out: list[str] = []
        inside = False
        for line in read_text(self.dispatch).split("\n"):
            if start_re.search(line):
                inside = True
            elif inside and (
                (line.startswith("def ") and not start_re.search(line))
                or line.startswith("RULES = ")
            ):
                break
            if inside:
                out.append(line)
        return "\n".join(out)

    def inject_cases(self) -> list[tuple[str, str]]:
        """`check_inject <fires|silent>` calls, with the needle, continuations joined."""
        text = read_text(self.hook_suite)
        lines = text.split("\n")
        out: list[tuple[str, str]] = []
        index = 0
        while index < len(lines):
            joined = lines[index]
            while joined.endswith("\\"):
                joined = joined[:-1]
                index += 1
                if index >= len(lines):
                    break
                joined = joined + " " + lines[index]
            index += 1
            if not re.search(r"check_inject[ \t]+(fires|silent)", joined):
                continue
            kind = "fires" if re.search(r"check_inject[ \t]+fires", joined) else "silent"
            needle = ""
            # awk: match(line, /"[^"]*"[^"]*$/) then the first quoted run inside that tail. The LAST quoted argument on the line.
            tail_match = re.search(r'"[^"]*"[^"]*$', joined)
            if tail_match:
                inner = re.search(r'"[^"]*"', tail_match.group(0))
                if inner:
                    needle = inner.group(0)[1:-1]
            out.append((kind, needle))
        return out

    def hook_is_live(self, rule: str) -> bool:
        """BOTH a firing case and a silent case for this rule in the suite."""
        if not self.hook_suite.is_file():
            return False
        body = self.rule_body(rule)
        if body == "":
            return False
        fires = 0
        silent = 0
        current = False
        for kind, needle in self.inject_cases():
            if kind == "fires":
                current = bool(needle) and needle in body
                if current:
                    fires += 1
            elif current:
                silent += 1
        return fires > 0 and silent > 0

    # -- F4/F5 for `file:` --------------------------------------------------

    def file_resolves(self, spec: str) -> bool:
        """`path` or `path:line`; the line must be in range and non-blank."""
        path, _, line = spec.partition(":")
        target = self.file_root / path
        if not target.is_file():
            return False
        if line == "":
            return True
        if not line.isdigit():
            return False
        number = int(line)
        text = read_text(target)
        # `wc -l` counts NEWLINES; see the port notes.
        total = text.count("\n")
        if number < 1 or number > total:
            return False
        body = text.split("\n")[number - 1]
        # `${text// /}` strips SPACES only, not tabs.
        return body.replace(" ", "") != ""

    def live_l1_files(self) -> list[pathlib.Path]:
        """Files that settings.json and the manifest name directly: hop 1."""
        if self._live_l1 is not None:
            return self._live_l1
        blob = ""
        if self.settings.is_file():
            blob += read_text(self.settings)
        if self.manifest.is_file():
            blob += read_text(self.manifest)
        names = sorted(
            {
                re.sub(r"^.*CLAUDE_PROJECT_DIR/", "", name)
                for name in re.findall(r"[A-Za-z0-9_./-]+\.(?:sh|py|ts|js|mjs|cjs)", blob)
            }
        )
        out = [self.file_root / name for name in names if (self.file_root / name).is_file()]
        self._live_l1 = out
        return out

    def file_is_live(self, spec: str) -> bool:
        """Reachable in at most two hops from settings.json or the manifest."""
        path = spec.split(":", 1)[0]
        base = os.path.basename(path)
        if self.settings.is_file() and base in read_text(self.settings):
            return True
        if self.manifest.is_file() and base in read_text(self.manifest):
            return True
        for candidate in self.live_l1_files():
            if candidate == self.file_root / path:
                continue
            if base in read_text(candidate):
                return True
        return False


class Shape:
    """The counts the success line prints, so a reader can see one collapse."""

    def __init__(self) -> None:
        self.entries = 0
        self.judgment = 0
        self.residue = 0
        self.gate = 0
        self.hook = 0
        self.file = 0


def scan(registry: Registry, floor: int, shape: Shape, report=None) -> int:
    """Every finding, printed. Returns the finding COUNT.

    NOT a boolean and not a shell return: a shell return is taken mod 256, so exactly 256 findings would read as a clean scan. The caller turns this into a status; the count itself is printed with the findings.
    """
    errors = 0
    emit = report if report is not None else log.error

    def err(message: str) -> None:
        nonlocal errors
        emit(message)
        errors += 1

    if not registry.corpus.is_file():
        err(
            "the corpus is not at %s. The gate cannot see the tree, so its green would "
            "mean nothing." % registry.corpus
        )
        return errors

    seen_ids: set[str] = set()
    for entry in parse_corpus(read_text(registry.corpus)):
        shape.entries += 1
        where = "%s:%d" % (registry.corpus, entry.line)

        # F2 IDENTITY
        if entry.trap_id == "":
            err(
                "%s: entry '%s' has no Trap-Id. Add the three-line trailer "
                "(Trap-Id / Enforced-By / Residue) directly under the heading."
                % (where, entry.title)
            )
            continue
        if not ID_RE.match(entry.trap_id):
            err(
                "%s: Trap-Id '%s' is not kebab-case within 3..49 characters "
                "(^[a-z0-9][a-z0-9-]{2,48}$)." % (where, entry.trap_id)
            )
        if entry.trap_id in seen_ids:
            err(
                "%s: Trap-Id '%s' is a DUPLICATE. Ids are permanent and unique; never "
                "reuse a retired one." % (where, entry.trap_id)
            )
        else:
            seen_ids.add(entry.trap_id)

        # F3 DISPOSITION
        if not entry.residue_seen:
            err(
                "%s: '%s' has no Residue line. Write 'Residue:' with nothing after it "
                "when the instruments cover the whole trap." % (where, entry.trap_id)
            )
        if entry.enforced_by == "":
            err(
                "%s: '%s' has no Enforced-By. Name a pointer (gate:/hook:/file:) or "
                "declare JUDGMENT-ONLY with a Residue." % (where, entry.trap_id)
            )
            continue
        if entry.enforced_by == "JUDGMENT-ONLY":
            shape.judgment += 1
            if entry.residue == "":
                err(
                    "%s: '%s' is JUDGMENT-ONLY with an empty Residue. Say what no "
                    "instrument reaches; that sentence is the only record of the "
                    "unprotected surface." % (where, entry.trap_id)
                )
        elif "JUDGMENT-ONLY" in entry.enforced_by:
            err(
                "%s: '%s' mixes JUDGMENT-ONLY with pointers. It is a terminal "
                "disposition: name the instruments, and put what they do not reach in "
                "Residue." % (where, entry.trap_id)
            )
        if entry.residue != "":
            shape.residue += 1

        # F4 + F5, per pointer. `${enf//,/ }` then word splitting.
        for ptr in entry.enforced_by.replace(",", " ").split():
            if ptr == "JUDGMENT-ONLY":
                continue
            if ptr.startswith("gate:"):
                shape.gate += 1
                gid = ptr[len("gate:") :]
                if not registry.gate_resolves(gid):
                    err(
                        "%s: '%s' names gate:%s, which is not both a manifest entry and a "
                        "package.json script. A dangling pointer is a lie about coverage."
                        % (where, entry.trap_id, gid)
                    )
                elif not registry.gate_is_live(gid):
                    err(
                        "%s: '%s' names gate:%s, which the manifest does not mark "
                        "'gate: true', so 'npm run ci' never schedules it. A gate nobody "
                        "runs is not an instrument." % (where, entry.trap_id, gid)
                    )
            elif ptr.startswith("hook:"):
                shape.hook += 1
                hid = ptr[len("hook:") :]
                if not registry.hook_resolves(hid):
                    err(
                        "%s: '%s' names hook:%s, which is not a rule listed in RULES in %s."
                        % (where, entry.trap_id, hid, registry.dispatch)
                    )
                elif not registry.hook_is_live(hid):
                    err(
                        "%s: '%s' names hook:%s, which lacks a FIRING case or a SILENT case "
                        "in %s. One-sided coverage cannot tell a rule that always fires from "
                        "one that never does." % (where, entry.trap_id, hid, registry.hook_suite)
                    )
            elif ptr.startswith("file:"):
                shape.file += 1
                fspec = ptr[len("file:") :]
                if not registry.file_resolves(fspec):
                    err(
                        "%s: '%s' names file:%s, which does not resolve (missing file, or a "
                        "line number past the end, or a blank line)."
                        % (where, entry.trap_id, fspec)
                    )
                elif not registry.file_is_live(fspec):
                    err(
                        "%s: '%s' names file:%s, which nothing registered or scheduled "
                        "reaches within two hops of .claude/settings.json or the ci-runner "
                        "manifest. Point at something that RUNS." % (where, entry.trap_id, fspec)
                    )
            else:
                err(
                    "%s: '%s' has an unknown pointer '%s'. Use gate:<check id>, "
                    "hook:<trapguard rule>, file:<path>[:line], or JUDGMENT-ONLY."
                    % (where, entry.trap_id, ptr)
                )

    # F1 POPULATION FLOOR, last so a truncated corpus reports its content problems too.
    if shape.entries < floor:
        err(
            "the corpus holds %d entries, below the floor of %d. Either the parser "
            "stopped seeing the tree, or entries were deleted; both are reds."
            % (shape.entries, floor)
        )
    return errors


# -- F6: the controls ---------------------------------------------------------


def fixture_corpus(extra: str, count: int) -> str:
    """`count` filler entries plus `extra`, built by CONSTRUCTION.

    Never by substituting into a copy of the real file, so the plant cannot silently fail to apply.
    """
    out: list[str] = []
    for i in range(1, count + 1):
        out.append("## filler trap %d" % i)
        out.append("Trap-Id: filler-trap-%d" % i)
        out.append("Enforced-By: JUDGMENT-ONLY")
        out.append("Residue: nothing reaches this filler.")
        out.append("")
        out.append("body")
        out.append("")
    out.append(extra)
    out.append("")
    return "\n".join(out)


CONTROL_MANIFEST = """export const GATES = [
  {
    id: 'check:ctl-live',
    run: 'npm run check:ctl-live',
    gate: true,
    leaves: ['sub/ctl-guard.sh'],
  },
  {
    id: 'check:ctl-dark',
    run: 'npm run check:ctl-dark',
    gate: false,
    leaves: ['nothing.sh'],
  },
];
"""

CONTROL_DISPATCH = """def rule_ctl_two_sided(cmd, out, root, resp):
    return "trapguard[ctl-two-sided]: fired"


def rule_ctl_one_sided(cmd, out, root, resp):
    return "trapguard[ctl-one-sided]: fired"


def rule_ctl_unlisted(cmd, out, root, resp):
    return "trapguard[ctl-unlisted]: fired"


RULES = (
    rule_ctl_two_sided,
    rule_ctl_one_sided,
)
"""

CONTROL_SUITE = """check_inject fires "$(inject_json 'x' 'y')" \\
    "ctl: the two-sided rule fires" "trapguard[ctl-two-sided]"
check_inject silent "$(inject_json 'x' '')" \\
    "ctl CONTROL: the two-sided rule stays silent"
check_inject fires "$(inject_json 'x' 'y')" \\
    "ctl: the one-sided rule fires" "trapguard[ctl-one-sided]"
"""


class Controls6:
    """F6's tally: reds that must red for the RIGHT reason, greens that must not."""

    def __init__(self) -> None:
        self.failures = 0
        self.red = 0
        self.green = 0


def _control_run(registry: Registry, corpus: pathlib.Path) -> tuple[int, list[str]]:
    """Run `scan` against one fixture corpus, capturing its findings.

    A subshell in the twin, so the seams and the finding counter cannot leak between controls. A fresh Registry and a captured sink are the same isolation.
    """
    findings: list[str] = []
    scoped = Registry(
        {
            "TRAP_CORPUS": corpus,
            "TRAP_MANIFEST": registry.manifest,
            "TRAP_PACKAGE_JSON": registry.package_json,
            "TRAP_DISPATCH": registry.dispatch,
            "TRAP_HOOK_SUITE": registry.hook_suite,
            "TRAP_SETTINGS": registry.settings,
            "TRAP_FILE_ROOT": registry.file_root,
        }
    )
    count = scan(scoped, 5, Shape(), report=findings.append)
    return count, findings


def run_controls(control_dir: pathlib.Path) -> bool:
    """Every assertion planted and required to red with its own message.

    True when the controls behaved. On False the caller must NOT judge the real tree: a gate whose controls are broken cannot report anything about anything.
    """
    # NO `registry` ARGUMENT. F6 builds its OWN registry out of the fixtures below and never consults the real one: a control that read the real manifest would go red the day someone renamed a gate, which is a finding about the tree wearing the costume of a broken control.
    tally = Controls6()
    files = control_dir / "files"
    (files / "sub").mkdir(parents=True, exist_ok=True)

    # A live pointer target for the positive controls: named by a fake manifest, so it is live at hop 1.
    (files / "sub" / "ctl-guard.sh").write_text("#!/bin/bash\necho real\n", encoding="utf-8")
    (files / "sub" / "ctl-orphan.sh").write_text("x\n", encoding="utf-8")
    (control_dir / "manifest.ts").write_text(CONTROL_MANIFEST, encoding="utf-8")
    (control_dir / "package.json").write_text(
        '{ "scripts": { "check:ctl-live": "true", "check:ctl-dark": "true" } }\n',
        encoding="utf-8",
    )
    (control_dir / "settings.json").write_text('{ "hooks": {} }\n', encoding="utf-8")
    (control_dir / "dispatch.py").write_text(CONTROL_DISPATCH, encoding="utf-8")
    (control_dir / "test-hooks.sh").write_text(CONTROL_SUITE, encoding="utf-8")

    scoped = Registry(
        {
            "TRAP_CORPUS": control_dir / "unused.md",
            "TRAP_MANIFEST": control_dir / "manifest.ts",
            "TRAP_PACKAGE_JSON": control_dir / "package.json",
            "TRAP_DISPATCH": control_dir / "dispatch.py",
            "TRAP_HOOK_SUITE": control_dir / "test-hooks.sh",
            "TRAP_SETTINGS": control_dir / "settings.json",
            "TRAP_FILE_ROOT": files,
        }
    )

    def write(name: str, extra: str, count: int) -> pathlib.Path:
        path = control_dir / name
        path.write_text(fixture_corpus(extra, count), encoding="utf-8")
        return path

    def expect_red(label: str, corpus: pathlib.Path, needle: str) -> None:
        tally.red += 1
        count, findings = _control_run(scoped, corpus)
        if count == 0:
            log.error(
                "CONTROL FAILED (%s): the planted defect did not red the gate, so its "
                "verdict on the real tree means nothing" % label
            )
            tally.failures += 1
        elif not any(needle in line for line in findings):
            joined = " ".join(findings)[:300]
            log.error(
                "CONTROL FIRED FOR THE WRONG REASON (%s): expected a finding containing "
                "'%s', got: %s" % (label, needle, joined)
            )
            tally.failures += 1

    def expect_green(label: str, corpus: pathlib.Path) -> None:
        tally.green += 1
        count, findings = _control_run(scoped, corpus)
        if count != 0:
            joined = " ".join(findings)[:300]
            log.error(
                "CONTROL FAILED (%s): a clean fixture went red (%d finding(s)), so this "
                "gate would flag correct corpora: %s" % (label, count, joined)
            )
            tally.failures += 1

    # -- the converse FIRST: a correct corpus must stay GREEN ---------------
    expect_green(
        "clean corpus, one pointer of each kind",
        write(
            "clean.md",
            "## a clean mechanized entry\n"
            "Trap-Id: ctl-clean\n"
            "Enforced-By: gate:check:ctl-live, hook:ctl-two-sided, file:sub/ctl-guard.sh\n"
            "Residue:\n\nbody\n",
            5,
        ),
    )

    # -- the fence control --------------------------------------------------
    expect_green(
        "a fenced ## heading is an example, not an entry",
        write(
            "fenced.md",
            "## a real entry with a fenced example\n"
            "Trap-Id: ctl-fenced\n"
            "Enforced-By: JUDGMENT-ONLY\n"
            "Residue: the example below must not become an entry.\n\n"
            "```markdown\n## Not A Trap\n```\n\n~~~\n## Also Not A Trap\n~~~\n",
            5,
        ),
    )
    expect_red(
        "an unfenced ## with no trailer is a finding (F2)",
        write("unfenced.md", "## Not A Trap\n", 5),
        "has no Trap-Id",
    )

    # -- F1 -----------------------------------------------------------------
    empty = control_dir / "empty.md"
    empty.write_text("", encoding="utf-8")
    expect_red("an empty corpus reds instead of passing vacuously (F1)", empty, "below the floor")
    expect_red("a corpus below the floor reds (F1)", write("short.md", "", 3), "below the floor")
    expect_red(
        "a missing corpus reds (F1)", control_dir / "does-not-exist.md", "the corpus is not at"
    )

    # -- F2 -----------------------------------------------------------------
    expect_red(
        "a duplicate Trap-Id reds (F2)",
        write(
            "dup.md",
            "## duplicate id\nTrap-Id: filler-trap-1\nEnforced-By: JUDGMENT-ONLY\nResidue: x.\n",
            5,
        ),
        "DUPLICATE",
    )
    expect_red(
        "a non-kebab Trap-Id reds (F2)",
        write(
            "badid.md",
            "## bad id\nTrap-Id: Not_Kebab_Case\nEnforced-By: JUDGMENT-ONLY\nResidue: x.\n",
            5,
        ),
        "is not kebab-case",
    )

    # -- F3 -----------------------------------------------------------------
    expect_red(
        "an entry with no Enforced-By reds (F3)",
        write("nodisp.md", "## no disposition\nTrap-Id: ctl-no-disposition\nResidue: x.\n", 5),
        "has no Enforced-By",
    )
    expect_red(
        "JUDGMENT-ONLY with an empty Residue reds (F3)",
        write(
            "nores.md",
            "## judgment with no residue\nTrap-Id: ctl-no-residue\n"
            "Enforced-By: JUDGMENT-ONLY\nResidue:\n",
            5,
        ),
        "with an empty Residue",
    )
    expect_red(
        "a missing Residue LINE reds (F3)",
        write(
            "noresline.md",
            "## no residue line at all\nTrap-Id: ctl-no-residue-line\n"
            "Enforced-By: gate:check:ctl-live\n",
            5,
        ),
        "has no Residue line",
    )
    expect_red(
        "JUDGMENT-ONLY mixed with a pointer reds (F3)",
        write(
            "mixed.md",
            "## mixed disposition\nTrap-Id: ctl-mixed\n"
            "Enforced-By: JUDGMENT-ONLY, gate:check:ctl-live\nResidue: x.\n",
            5,
        ),
        "mixes JUDGMENT-ONLY",
    )

    # -- F4 -----------------------------------------------------------------
    expect_red(
        "a gate: pointer at a non-existent id reds (F4)",
        write(
            "badgate.md",
            "## dangling gate\nTrap-Id: ctl-dangling-gate\n"
            "Enforced-By: gate:check:does-not-exist\nResidue:\n",
            5,
        ),
        "is not both a manifest entry",
    )
    expect_red(
        "a hook: pointer at a non-existent rule reds (F4)",
        write(
            "badhook.md",
            "## dangling hook\nTrap-Id: ctl-dangling-hook\nEnforced-By: hook:no-such-rule\n"
            "Residue:\n",
            5,
        ),
        "not a rule listed in RULES",
    )
    expect_red(
        "a hook: rule missing from RULES reds (F4)",
        write(
            "unlisted.md",
            "## rule defined but not dispatched\nTrap-Id: ctl-unlisted-rule\n"
            "Enforced-By: hook:ctl-unlisted\nResidue:\n",
            5,
        ),
        "not a rule listed in RULES",
    )
    expect_red(
        "a file: pointer at a missing path reds (F4)",
        write(
            "badfile.md",
            "## dangling file\nTrap-Id: ctl-dangling-file\nEnforced-By: file:no/such/guard.sh\n"
            "Residue:\n",
            5,
        ),
        "does not resolve",
    )
    expect_red(
        "a file: pointer past the end of the file reds (F4)",
        write(
            "badline.md",
            "## line past the end\nTrap-Id: ctl-line-past-end\n"
            "Enforced-By: file:sub/ctl-guard.sh:9999\nResidue:\n",
            5,
        ),
        "does not resolve",
    )
    expect_red(
        "an unknown pointer kind reds (F4), which is what stops 'name a grep' from being "
        "the cheap answer",
        write(
            "unknown.md",
            "## unknown pointer kind\nTrap-Id: ctl-unknown-kind\n"
            "Enforced-By: grep:the-trap-title\nResidue:\n",
            5,
        ),
        "unknown pointer",
    )

    # -- F5 -----------------------------------------------------------------
    expect_red(
        "a gate: pointer at a manifest entry with gate:false reds (F5)",
        write(
            "darkgate.md",
            "## a gate nobody runs\nTrap-Id: ctl-dark-gate\nEnforced-By: gate:check:ctl-dark\n"
            "Residue:\n",
            5,
        ),
        "does not mark 'gate: true'",
    )
    expect_red(
        "a hook: rule with a firing case and no silent case reds (F5)",
        write(
            "onesided.md",
            "## a rule with no silent case\nTrap-Id: ctl-one-sided\n"
            "Enforced-By: hook:ctl-one-sided\nResidue:\n",
            5,
        ),
        "lacks a FIRING case or a SILENT case",
    )
    expect_red(
        "a file: pointer nothing reaches within two hops reds (F5)",
        write(
            "orphanfile.md",
            "## a file nothing runs\nTrap-Id: ctl-orphan-file\n"
            "Enforced-By: file:sub/ctl-orphan.sh\nResidue:\n",
            5,
        ),
        "within two hops",
    )

    if tally.failures > 0:
        log.error(
            "%d of the gate's own controls misbehaved. NOT judging the real tree: a gate "
            "whose controls are broken cannot report anything about anything." % tally.failures
        )
        return False
    log.info(
        "controls: %d planted defects red (each matched against the finding it was "
        "written for), %d clean fixtures green" % (tally.red, tally.green)
    )
    return True


def resolve_seams(root: pathlib.Path, env: dict[str, str] | None = None) -> dict[str, pathlib.Path]:
    """The seven seams, each overridable by its own environment variable."""
    environ = os.environ if env is None else env
    out: dict[str, pathlib.Path] = {}
    for name, parts in SEAMS.items():
        override = environ.get(name, "")
        out[name] = pathlib.Path(override) if override else root.joinpath(*parts)
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the controls, then the scan. 0 clean, 1 finding or broken control."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    registry = Registry(resolve_seams(root))
    floor = int(os.environ.get("TRAP_FLOOR", "") or TRAP_FLOOR_DEFAULT)

    # `--scan-only` runs the scan WITHOUT the controls. Nothing in package.json or CI uses it, deliberately.
    if args[:1] != ["--scan-only"]:
        with tempfile.TemporaryDirectory() as tmp:
            if not run_controls(pathlib.Path(tmp)):
                return 1

    shape = Shape()
    count = scan(registry, floor, shape)

    # A DEFECT IN THE TWIN, PRESERVED RATHER THAN REPAIRED, and it is worth naming precisely because the comment next to it explains the OPPOSITE intent. `scan` in bash ends with `[ "$errors" -eq 0 ]`, so what `main`
    # captures in `found=$?` is a BOOLEAN, not the finding count -- deliberately,
    # because "a shell return is taken mod 256, so exactly 256 findings would
    # return 0 and read as a clean scan". But `main` then prints that boolean as
    # `"$found trap-registry finding(s)"`, so the summary line says "1 finding(s)" no matter how many there are. The findings themselves are all printed above it, so nothing is hidden; the count is simply wrong.
    #
    # A port that printed the real count would be NON-EQUIVALENT to the gate CI runs, and the shadow ledger would attest to a summary line the twin never emits. Measured: the first recording of this pair reported MISMATCH_FINDINGS on four of five fixture trees for exactly this line. Fixing it belongs in a change that touches BOTH files.
    found = 1 if count > 0 else 0
    if found > 0:
        log.error(
            "%d trap-registry finding(s) in %s. Fix the disposition, do not delete the "
            "entry and do not point at something that cannot fire." % (found, registry.corpus)
        )
        return 1

    # Print the SHAPE, not just the verdict: a reader can notice when a number collapses, and "OK" tells nobody that the corpus stopped being parsed.
    log.info(
        "trap registry OK: %d entries (floor %d), %d JUDGMENT-ONLY, %d carrying residue, "
        "%d live pointers (%d gate, %d hook, %d file)"
        % (
            shape.entries,
            floor,
            shape.judgment,
            shape.residue,
            shape.gate + shape.hook + shape.file,
            shape.gate,
            shape.hook,
            shape.file,
        )
    )

    # THE UNRATCHETED FLOOR, SAID OUT LOUD WHERE THE AUTHOR IS LOOKING. An ADVISORY, not a failure; see the header for why.
    if shape.entries > floor:
        log.info(
            "  ratchet: %d entries against a floor of %d. Bump TRAP_FLOOR to %d in this "
            "commit, or gate-test:trap-registry (F1) reds in CI."
            % (shape.entries, floor, shape.entries)
        )
    return 0


def selftest() -> int:
    """Both directions on the parser and on every resolver.

    The twin's F6 controls run INLINE on every real invocation and are preserved above. What they cannot reach is the PARSER's edges and the resolvers driven directly, which is what this adds.
    """
    ctl = Controls("trap-registry", floor=38, verbose=True)

    # -- the parser ---------------------------------------------------------
    doc = (
        "## first\nTrap-Id: first-trap\nEnforced-By: JUDGMENT-ONLY\nResidue: nothing.\n\n"
        "body\n\n## second\nTrap-Id: second-trap\nEnforced-By: gate:check:x\nResidue:\n"
    )
    entries = parse_corpus(doc)
    ctl.check("CONTROL: two headings parse to two entries", len(entries), 2)
    ctl.check("CONTROL: the id is read", entries[0].trap_id, "first-trap")
    ctl.check("CONTROL: the disposition is read", entries[1].enforced_by, "gate:check:x")
    ctl.truthy("CONTROL: an EMPTY Residue is still a Residue LINE", entries[1].residue_seen)
    ctl.check("CONTROL: and its value is empty", entries[1].residue, "")
    ctl.check("CONTROL: the heading line number is recorded", entries[0].line, 1)

    fenced = (
        "## real\nTrap-Id: real-trap\nEnforced-By: JUDGMENT-ONLY\nResidue: x.\n\n"
        "```markdown\n## Not A Trap\n```\n\n~~~\n## Also Not A Trap\n~~~\n"
    )
    ctl.check(
        "CONTROL: a ``` fenced heading is an example, not an entry", len(parse_corpus(fenced)), 1
    )
    ctl.check(
        "CONTROL: a ~~~ fenced heading is too",
        len(parse_corpus("## r\nTrap-Id: r\n\n~~~\n## X\n~~~\n")),
        1,
    )
    ctl.check("MIRROR: `### ` is not an entry", len(parse_corpus("### not an entry\n")), 0)
    ctl.check(
        "MIRROR: a body paragraph beginning 'Residue:' is body, not a trailer",
        parse_corpus("## t\nTrap-Id: t\n\nResidue: this is prose\n")[0].residue_seen,
        False,
    )
    ctl.check("VACUITY: an empty corpus parses to no entries", len(parse_corpus("")), 0)

    # -- the id grammar -----------------------------------------------------
    ctl.truthy(
        "CONTROL: a kebab id is valid", bool(ID_RE.match("mark-done-all-stale-is-a-bulk-verb"))
    )
    ctl.falsy("PLANT: an underscored id is not", bool(ID_RE.match("Not_Kebab_Case")))
    ctl.falsy("PLANT: a two-character id is too short", bool(ID_RE.match("ab")))
    ctl.truthy("BOUNDARY: three characters is the minimum", bool(ID_RE.match("abc")))
    ctl.falsy("PLANT: a leading hyphen is not valid", bool(ID_RE.match("-abc")))

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        files = base / "files"
        (files / "sub").mkdir(parents=True)
        (files / "sub" / "ctl-guard.sh").write_text("#!/bin/bash\necho real\n", encoding="utf-8")
        (files / "sub" / "ctl-orphan.sh").write_text("x\n", encoding="utf-8")
        (files / "sub" / "blank.sh").write_text("a\n\nc\n", encoding="utf-8")
        (base / "manifest.ts").write_text(CONTROL_MANIFEST, encoding="utf-8")
        (base / "package.json").write_text(
            '{ "scripts": { "check:ctl-live": "true", "check:ctl-dark": "true" } }\n',
            encoding="utf-8",
        )
        (base / "settings.json").write_text('{ "hooks": {} }\n', encoding="utf-8")
        (base / "dispatch.py").write_text(CONTROL_DISPATCH, encoding="utf-8")
        (base / "test-hooks.sh").write_text(CONTROL_SUITE, encoding="utf-8")
        registry = Registry(
            {
                "TRAP_CORPUS": base / "corpus.md",
                "TRAP_MANIFEST": base / "manifest.ts",
                "TRAP_PACKAGE_JSON": base / "package.json",
                "TRAP_DISPATCH": base / "dispatch.py",
                "TRAP_HOOK_SUITE": base / "test-hooks.sh",
                "TRAP_SETTINGS": base / "settings.json",
                "TRAP_FILE_ROOT": files,
            }
        )

        # -- gate: -----------------------------------------------------------
        ctl.truthy(
            "CONTROL: a gate in both the manifest and package.json resolves",
            registry.gate_resolves("check:ctl-live"),
        )
        ctl.falsy("PLANT: an id in neither does not resolve", registry.gate_resolves("check:nope"))
        ctl.truthy(
            "CONTROL: `gate: true` inside the entry's own block is live",
            registry.gate_is_live("check:ctl-live"),
        )
        ctl.falsy(
            "PLANT: `gate: false` is NOT live, so npm run ci never schedules it",
            registry.gate_is_live("check:ctl-dark"),
        )

        # -- hook: -----------------------------------------------------------
        ctl.truthy(
            "CONTROL: a defined AND listed rule resolves", registry.hook_resolves("ctl-two-sided")
        )
        ctl.falsy(
            "PLANT: a rule defined but NOT in RULES is dead code",
            registry.hook_resolves("ctl-unlisted"),
        )
        ctl.falsy(
            "PLANT: a rule that does not exist does not resolve",
            registry.hook_resolves("no-such-rule"),
        )
        ctl.truthy(
            "CONTROL: a rule with a firing AND a silent case is live",
            registry.hook_is_live("ctl-two-sided"),
        )
        ctl.falsy(
            "PLANT: a rule with only a firing case is one-sided",
            registry.hook_is_live("ctl-one-sided"),
        )

        # -- file: -----------------------------------------------------------
        ctl.truthy("CONTROL: a bare path resolves", registry.file_resolves("sub/ctl-guard.sh"))
        ctl.truthy(
            "CONTROL: a path with an in-range non-blank line resolves",
            registry.file_resolves("sub/ctl-guard.sh:2"),
        )
        ctl.falsy(
            "PLANT: a line past the end does not resolve",
            registry.file_resolves("sub/ctl-guard.sh:9999"),
        )
        ctl.falsy("PLANT: a BLANK line does not resolve", registry.file_resolves("sub/blank.sh:2"))
        ctl.falsy("PLANT: a missing file does not resolve", registry.file_resolves("no/such.sh"))
        ctl.falsy(
            "PLANT: a non-numeric line does not resolve",
            registry.file_resolves("sub/ctl-guard.sh:x"),
        )
        ctl.truthy(
            "CONTROL: a file the manifest names is live at hop 1",
            registry.file_is_live("sub/ctl-guard.sh"),
        )
        ctl.falsy(
            "PLANT: a file nothing names is not live", registry.file_is_live("sub/ctl-orphan.sh")
        )

        # -- the whole scan, both directions --------------------------------
        shape = Shape()
        (base / "corpus.md").write_text(
            fixture_corpus(
                "## a clean mechanized entry\nTrap-Id: ctl-clean\n"
                "Enforced-By: gate:check:ctl-live, hook:ctl-two-sided, file:sub/ctl-guard.sh\n"
                "Residue:\n\nbody\n",
                5,
            ),
            encoding="utf-8",
        )
        findings: list[str] = []
        ctl.check(
            "CONTROL: a clean corpus scans with no findings",
            scan(registry, 5, shape, findings.append),
            0,
        )
        ctl.check(
            "CONTROL: and the shape counts one pointer of each kind",
            (shape.gate, shape.hook, shape.file),
            (1, 1, 1),
        )
        shape = Shape()
        findings = []
        ctl.check(
            "VACUITY: the SAME corpus under a floor above it is a FAILURE",
            scan(registry, 999, shape, findings.append),
            1,
        )
        ctl.truthy(
            "CONTROL: and the finding names the floor",
            any("below the floor" in f for f in findings),
        )

        # -- F6 itself, both directions -------------------------------------
        control_dir = base / "f6"
        control_dir.mkdir()
        ctl.truthy("CONTROL: the gate's own F6 controls all behave", run_controls(control_dir))

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
