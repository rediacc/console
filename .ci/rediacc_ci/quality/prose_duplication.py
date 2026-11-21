r"""check:ci-prose-duplication: the PR loop's docs carry no passage word for word in two files.

WHY THIS EXISTS (agent/plans/PLAN-pr-loop-single-source.md D6). Four files drive the PR loop: CLAUDE.md, the /pr-babysit launcher, the pr-babysitter agent and /pr-merge. Measured 2026-11-20 at 2876cc6b5, the launcher repeated 231 normalized words of /pr-merge and 152 of the agent file, and no gate compared prose passages (check:ci-shape-duplication reads TypeScript only). A copy nobody re-reads drifts, so
the plan keeps each rule in one D1 home and points from every other file; this gate keeps a passage from growing back.

THE FAMILY (`FAMILY`) is fixed in code, not in a registry, so no config can switch the gate off; widening it is a one-tuple change, and the success line prints it. All six pairs are compared. The output style and the pr-epics skill hold registered verbatim mirrors, which check:ci-scope-mirrors judges, and docs/agent-reference/ci-gates.md is the guard reference; none is in the family.

THE UNIT is a run of normalized words. Each word goes through `scope_mirrors.normalize` (comments stripped, `**`, `__` and backticks dropped, quotes and dashes folded, casefolded), so the repository has one normalization and a passage rewrapped in bold or code spans still matches. A token that is markdown structure only (a list bullet, a numbered-list marker, a table pipe, a heading hash, a front-matter
fence) is dropped, so a list rewritten as a paragraph still matches.

EXCLUDED TEXT IS A RUN BREAK, never a join: a run cannot continue across it.

  * gen-docs regions (`scope_mirrors.GEN_DOCS_RE`): generated, and identical by construction where two files render the same table;
  * fenced and indented code (`scope_mirrors.md_blocks`, kind `fence`): commands and config examples, not restatements.

REGISTERED SCOPE SPANS ARE EXEMPT ONLY FROM EACH OTHER. check:ci-scope-mirrors judges the registered copies of a clause (its canonical span and its declared mirror spans), so a shared run is dropped where BOTH words sit in registered spans of the same clause, and nowhere else. The span's words stay in the corpus: a canonical span copied into unregistered text elsewhere is red, and so is the same text under a span of a different clause. Excluding the spans outright was a blind spot
(measured on the landed tree 2026-11-21: the agent file's `pr.sibling-repos` paragraph appended to the launcher stayed green). A span counts as registered when `.ci/config/scope-mirrors.json` names its (path, clause): the clause's `canonical` file (the clause key, else the registry key, else CLAUDE.md), where the span runs from the open to the next close, or a `mirrors` entry with no `where`, where the span follows `scope_mirrors.mirror_spans`.
Text under an anchor the registry does NOT name is plain prose (and is red on C10 there).

Front matter is INCLUDED: the skill loader shows the `description` key on every invocation.

THRESHOLD (`THRESHOLD`) is 25 words. Plan D6 expects the longest legitimate shared run among the four under 20 once the loop docs are rewritten. Never raise it to make a finding go away: move the passage to its D1 home and point at it.

FINDING: `<path_a>:<line> ~ <path_b>:<line> <n> words: "<first 12 words> ..."`, then the fix. There is no baseline: the rewrite removes every hit and the gate lands in the same batch.

ANTI-VACUITY. A missing family file, a missing or unreadable registry, or a family file with zero extracted words is exit 2, never a pass: a gate that compared nothing has no verdict.

BLIND SPOTS (`BLIND_SPOTS`, printed on every green): a paraphrase (the scope-mirrors C9 sentinels cover registered clauses), files outside the family, and shared passages under the threshold.

Exit codes: 0 clean, 1 finding, 2 broken controls, usage error or a gate that could not see its inputs.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import pathlib
import re
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls, controls_first, plant
from rediacc_ci.quality import scope_mirrors as sm

ENTRY_REL = ".ci/scripts/quality/check_prose_duplication.py"

# The loop's reading set (plan D6). Fixed in code so no config can shrink it.
FAMILY = (
    "CLAUDE.md",
    ".claude/commands/pr-babysit.md",
    ".claude/agents/pr-babysitter.md",
    ".claude/commands/pr-merge.md",
)

THRESHOLD = 25
QUOTE_WORDS = 12

# A token that is markdown structure and nothing else: bullets, numbered-list markers, table pipes, heading hashes, blockquote marks, rules and the front-matter fence (an em dash folds to `--`, which this drops too).
STRUCTURE_RE = re.compile(r"^(?:[-*+>#|=:]+|\d+[.)])$")
WORD_RE = re.compile(r"\S+")

BLIND_SPOTS = (
    "Blind: a paraphrase (scope-mirrors C9 sentinels cover registered clauses), files outside "
    "the family, and shared passages under %d words." % THRESHOLD
)

FIX = (
    "fix: keep the passage in its D1 home (agent/plans/PLAN-pr-loop-single-source.md) and replace "
    "the other copy with a one-line pointer to that file; never raise the threshold."
)


# --------------------------------------------------------------------------- words


@dataclasses.dataclass(frozen=True)
class Word:
    text: str  # normalized
    line: int
    segment: int  # words of different segments never join one run
    clauses: frozenset[str] = frozenset()  # registered scope spans this word sits in


@dataclasses.dataclass
class Extract:
    path: str
    words: list[Word]
    gen_docs: int = 0
    code: int = 0
    spans: int = 0


def _blank(text: str, start: int, end: int) -> str:
    """`text` with [start, end) replaced by spaces, newlines kept, so offsets and line numbers hold."""
    return text[:start] + re.sub(r"[^\n]", " ", text[start:end]) + text[end:]


def registered_ids(registry: dict, path: str) -> tuple[set[str], set[str]]:
    """(clauses canonical in `path`, clauses `path` mirrors inline) by the registry."""
    default = registry.get("canonical") or sm.DEFAULT_CANONICAL
    canonical: set[str] = set()
    mirrored: set[str] = set()
    clauses = registry.get("clauses")
    if not isinstance(clauses, dict):
        return canonical, mirrored
    for clause, spec in clauses.items():
        if not isinstance(spec, dict):
            continue
        if (spec.get("canonical") or default) == path:
            canonical.add(clause)
        for mirror in spec.get("mirrors") or []:
            if isinstance(mirror, dict) and mirror.get("path") == path and not mirror.get("where"):
                mirrored.add(clause)
    return canonical, mirrored


def scope_ranges(text: str, path: str, registry: dict) -> tuple[list[tuple[int, int, str]], int]:
    """((start, end, clause) of every REGISTERED scope span in `text`; how many spans). An unregistered anchor yields nothing."""
    canonical, mirrored = registered_ids(registry, path)
    ranges: list[tuple[int, int, str]] = []
    count = 0
    markers = sm.parse_anchors(text)
    # Where a closed canonical span starts, so the mirror reading does not count it twice.
    strict: set[int] = set()
    for i, mk in enumerate(markers):
        if mk.kind != "open" or mk.clause not in canonical:
            continue
        close = next((m for m in markers[i + 1 :] if m.kind == "close"), None)
        # A canonical span with no close is red on C1 in scope-mirrors; here it falls back to the mirror reading below.
        if close is not None:
            ranges.append((mk.end, close.start, mk.clause))
            strict.add(mk.end)
            count += 1
    for span in sm.mirror_spans(text, path):
        if span.start in strict:
            continue
        if span.clause in mirrored or span.clause in canonical:
            ranges.append((span.start, span.end, span.clause))
            count += 1
    return ranges, count


def extract(text: str, path: str, registry: dict) -> Extract:
    """The normalized words of `text`: excluded regions become segment breaks, and each word carries the registered spans it sits in."""
    out = Extract(path, [])
    excluded: list[tuple[int, int]] = []
    for m in sm.GEN_DOCS_RE.finditer(text):
        excluded.append((m.start(), m.end()))
        out.gen_docs += 1
    for block in sm.md_blocks(text):
        if block.kind == "fence":
            excluded.append((block.start, block.end))
            out.code += 1
    scopes, out.spans = scope_ranges(text, path, registry)
    # HTML comments are not prose (normalize drops them); blank them so a comment's words never count.
    work = text
    for m in sm.COMMENT_RE.finditer(text):
        work = _blank(work, m.start(), m.end())
    excluded.sort()
    segment = 0
    cursor = 0
    pieces: list[tuple[int, int, int]] = []
    for start, end in excluded:
        if start > cursor:
            pieces.append((cursor, start, segment))
        segment += 1
        cursor = max(cursor, end)
    pieces.append((cursor, len(work), segment))
    for start, end, seg in pieces:
        for m in WORD_RE.finditer(work, start, end):
            token = sm.normalize(m.group(0))
            if not token or STRUCTURE_RE.match(token):
                continue
            at = m.start()
            inside = frozenset(c for a, b, c in scopes if a <= at < b)
            out.words.append(Word(token, sm.line_of(text, at), seg, inside))
    return out


# --------------------------------------------------------------------------- runs


@dataclasses.dataclass
class Run:
    path_a: str
    line_a: int
    path_b: str
    line_b: int
    words: list[str]

    def render(self) -> str:
        head = " ".join(self.words[:QUOTE_WORDS])
        tail = " ..." if len(self.words) > QUOTE_WORDS else ""
        return '%s %s:%d ~ %s:%d %d words: "%s%s"' % (
            sm.CROSS,
            self.path_a,
            self.line_a,
            self.path_b,
            self.line_b,
            len(self.words),
            head,
            tail,
        )


def shared_runs(a: Extract, b: Extract, threshold: int | None = None) -> list[Run]:
    """Every MAXIMAL run of at least `threshold` (default `THRESHOLD`) words that `a` and `b` share, inside one segment of each.

    A word pair where both sides sit in registered spans of the same clause is not a shared word: scope-mirrors judges that copy. Such a pair splits a run, so the registered copy is exempt and any unregistered stretch around it is still compared.
    """
    if threshold is None:
        threshold = THRESHOLD
    if threshold < 1:
        raise ValueError("threshold must be at least 1")
    aw, bw = a.words, b.words

    def gram_ok(words: list[Word], i: int) -> bool:
        return i + threshold <= len(words) and words[i].segment == words[i + threshold - 1].segment

    def same(i: int, j: int, i0: int, j0: int) -> bool:
        """Text-equal and in the same segments as the run's first pair (i0, j0)."""
        return (
            0 <= i < len(aw)
            and 0 <= j < len(bw)
            and aw[i].text == bw[j].text
            and aw[i].segment == aw[i0].segment
            and bw[j].segment == bw[j0].segment
        )

    index: dict[tuple[str, ...], list[int]] = {}
    for i in range(len(aw)):
        if gram_ok(aw, i):
            index.setdefault(tuple(w.text for w in aw[i : i + threshold]), []).append(i)
    runs: list[Run] = []
    for j in range(len(bw)):
        if not gram_ok(bw, j):
            continue
        for i in index.get(tuple(w.text for w in bw[j : j + threshold]), []):
            # Maximal only: a match whose predecessor also matches is the tail of a text run already taken.
            if same(i - 1, j - 1, i, j):
                continue
            n = threshold
            while same(i + n, j + n, i, j):
                n += 1
            # Split the text run at every pair both registered under one clause; keep the stretches that remain.
            start = 0
            for k in range(n + 1):
                exempt = k < n and bool(aw[i + k].clauses & bw[j + k].clauses)
                if k == n or exempt:
                    if k - start >= threshold:
                        runs.append(
                            Run(
                                a.path,
                                aw[i + start].line,
                                b.path,
                                bw[j + start].line,
                                [w.text for w in aw[i + start : i + k]],
                            )
                        )
                    start = k + 1
    return runs


# --------------------------------------------------------------------------- the verdict


@dataclasses.dataclass
class Verdict:
    runs: list[Run]
    extracts: list[Extract]
    problems: list[str]  # refusals: the gate could not see its inputs


def judge(root: pathlib.Path, family: tuple[str, ...] = FAMILY) -> Verdict:
    registry, err = sm.load_registry(root)
    problems: list[str] = []
    if registry is None:
        problems.append(
            "%s; without it no scope span can be told registered from unregistered" % err
        )
    extracts: list[Extract] = []
    for rel in family:
        path = root / rel
        if not path.is_file():
            problems.append("%s is missing; the family is fixed in %s" % (rel, ENTRY_REL))
            continue
        ex = extract(path.read_text(encoding="utf-8"), rel, registry or {})
        if not ex.words:
            problems.append(
                "%s yields zero words; the gate is not seeing the file and its green would mean nothing"
                % rel
            )
        extracts.append(ex)
    if problems:
        return Verdict([], extracts, problems)
    runs: list[Run] = []
    for x in range(len(extracts)):
        for y in range(x + 1, len(extracts)):
            runs.extend(shared_runs(extracts[x], extracts[y]))
    return Verdict(runs, extracts, [])


def report(root: pathlib.Path, family: tuple[str, ...] = FAMILY) -> int:
    verdict = judge(root, family)
    if verdict.problems:
        for problem in verdict.problems:
            print("%s prose duplication: %s" % (sm.CROSS, problem), file=sys.stderr)
        return 2
    exs = verdict.extracts
    pairs = len(exs) * (len(exs) - 1) // 2
    shape = (
        "%d files (%s), %d pairs, %d words, excluded %d gen-docs, %d code; "
        "%d registered scope spans exempt only from their own clause's copies"
    ) % (
        len(exs),
        ", ".join(e.path for e in exs),
        pairs,
        sum(len(e.words) for e in exs),
        sum(e.gen_docs for e in exs),
        sum(e.code for e in exs),
        sum(e.spans for e in exs),
    )
    if verdict.runs:
        for run in verdict.runs:
            print(run.render(), file=sys.stderr)
        print(
            "%s prose duplication: %d shared run(s) of %d+ words; %s"
            % (sm.CROSS, len(verdict.runs), THRESHOLD, shape),
            file=sys.stderr,
        )
        print(FIX, file=sys.stderr)
        return 1
    print("%s prose duplication: %s; no shared run of %d+ words" % (sm.TICK, shape, THRESHOLD))
    print(BLIND_SPOTS)
    return 0


# --------------------------------------------------------------------------- selftest

CLAUDE_MD, FIX_LAUNCHER, FIX_AGENT, FIX_MERGE = FAMILY

# Thirty words no fixture file carries until a control plants them.
PASSAGE = (
    "the sibling repositories under the private directory are cloned beside the console and each "
    "one carries its own branch named after the console branch with the same date and counter"
)

FIX_FILES = {
    "CLAUDE.md": (
        "# Fixture rules\n\n"
        "Alpha bravo charlie delta echo foxtrot golf hotel india juliet.\n\n"
        "- <!-- scope: pr.fix-rule -->Kilo lima mike november oscar papa.<!-- /scope -->\n"
    ),
    FIX_LAUNCHER: (
        "---\ndescription: Start the fixture loop and read the agent file.\n---\n\n"
        "# Launcher\n\nQuebec romeo sierra tango uniform victor whiskey.\n"
    ),
    FIX_AGENT: (
        "---\nname: fixture-agent\ndescription: The fixture loop end to end.\n---\n\n"
        "# Agent\n\nXray yankee zulu one two three four five six.\n\n"
        "- <!-- scope: pr.fix-rule -->Kilo lima mike november oscar papa.\n"
    ),
    FIX_MERGE: "# Merge\n\nSeven eight nine ten eleven twelve thirteen fourteen.\n",
}


def fixture_registry() -> dict:
    return {
        "floors": {"clauses": 1, "mirror_checks": 1},
        "clauses": {
            "pr.fix-rule": {
                "sha": "0" * 12,
                "atoms": ["kilo lima"],
                "sentinels": ["kilo lima"],
                "mirrors": [{"path": FIX_AGENT, "mode": "terms"}],
            }
        },
    }


def build_fixture(root: pathlib.Path, registry: dict | None = None) -> pathlib.Path:
    for rel, text in FIX_FILES.items():
        _write(root, rel, text)
    _write(root, sm.REGISTRY_REL, json.dumps(registry or fixture_registry(), indent=2) + "\n")
    return root


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _append(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _mutate(root: pathlib.Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    path.write_text(plant(path.read_text(encoding="utf-8"), old, new), encoding="utf-8")


def _words(n: int, stem: str = "w") -> str:
    return " ".join("%s%d" % (stem, i) for i in range(n))


def selftest(verbose: bool = True) -> int:
    """Control-first: the clean fixture, then each D6 control planted with `plant`, in both directions."""
    ctl = Controls("prose-duplication", floor=30, verbose=verbose)
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        made = [0]

        def fresh(registry: dict | None = None) -> pathlib.Path:
            made[0] += 1
            return build_fixture(base / ("t%d" % made[0]), registry)

        def red(root: pathlib.Path) -> list[Run]:
            return judge(root).runs

        def pair(runs: list[Run]) -> list[tuple[str, str]]:
            return sorted({(r.path_a, r.path_b) for r in runs})

        # -- pure helpers ----------------------------------------------------
        reg = fixture_registry()
        ex = extract("- one **two** `three`\n1. four | five\n", "x.md", reg)
        ctl.check(
            "markdown structure tokens drop and markup normalizes",
            [w.text for w in ex.words],
            ["one", "two", "three", "four", "five"],
        )
        ex = extract("a b\n\n```\nc d\n```\n\ne f\n", "x.md", reg)
        ctl.check(
            "fenced words are not extracted", [w.text for w in ex.words], ["a", "b", "e", "f"]
        )
        ctl.truthy(
            "a fence is a run break: the words around it sit in two segments",
            ex.words[1].segment != ex.words[2].segment,
        )
        a = Extract("a", [Word("w%d" % i, 1, 0) for i in range(30)])
        b = Extract("b", [Word("w%d" % i, 1, 0) for i in range(30)])
        ctl.check(
            "a shared 30-word run is ONE maximal run",
            [len(r.words) for r in shared_runs(a, b)],
            [30],
        )
        b2 = Extract(
            "b",
            [Word("w%d" % i, 1, 0) for i in range(15)]
            + [Word("w%d" % i, 1, 1) for i in range(15, 30)],
        )
        ctl.check("a run cut by a segment break does not join", shared_runs(a, b2), [])
        ctl.check(
            "an unregistered anchor yields no excluded range",
            scope_ranges("<!-- scope: pr.nobody -->x y\n", "x.md", reg),
            ([], 0),
        )

        # -- the fixture -----------------------------------------------------
        root = fresh()
        ctl.check("CONTROL: the clean fixture is green", _report_rc(root), 0)
        ctl.check("the clean fixture finds no run", red(root), [])

        root = fresh()
        _append(root, FIX_LAUNCHER, "\n" + PASSAGE + "\n")
        _append(root, FIX_AGENT, "\n" + PASSAGE + "\n")
        found = red(root)
        ctl.check(
            "a 30-word passage in launcher and agent is red, naming both",
            pair(found),
            [(FIX_LAUNCHER, FIX_AGENT)],
        )
        ctl.check("and the finding counts all 30 words", [len(r.words) for r in found], [30])
        ctl.check("and the gate exits 1", _report_rc(root), 1)

        root = fresh()
        _append(root, FIX_MERGE, "\n" + _words(24) + "\n")
        _append(root, "CLAUDE.md", "\n" + _words(24) + "\n")
        ctl.check("a 24-word shared run is green", red(root), [])
        root = fresh()
        _append(root, FIX_MERGE, "\n" + _words(25) + "\n")
        _append(root, "CLAUDE.md", "\n" + _words(25) + "\n")
        ctl.check("a 25-word shared run is red", pair(red(root)), [("CLAUDE.md", FIX_MERGE)])

        root = fresh()
        words = PASSAGE.split()
        rewrapped = " ".join(
            "**%s**" % w if i % 5 == 0 else ("`%s`" % w if i % 7 == 0 else w)
            for i, w in enumerate(words)
        )
        _append(root, FIX_LAUNCHER, "\n" + PASSAGE + "\n")
        _append(root, FIX_AGENT, "\n" + plant(rewrapped, " the ", "\nthe ", 2) + "\n")
        ctl.check(
            "the passage rewrapped with ** and backticks is still red",
            pair(red(root)),
            [(FIX_LAUNCHER, FIX_AGENT)],
        )

        root = fresh()
        _append(root, FIX_LAUNCHER, "\n```\n" + PASSAGE + "\n```\n")
        _append(root, FIX_AGENT, "\n```text\n" + PASSAGE + "\n```\n")
        ctl.check("the passage inside a fence in both files is green", red(root), [])
        root = fresh()
        _append(root, FIX_LAUNCHER, "\n    " + PASSAGE + "\n")
        _append(root, FIX_AGENT, "\n    " + PASSAGE + "\n")
        ctl.check("the passage as indented code in both files is green", red(root), [])

        root = fresh()
        region = "\n<!-- >>> gen-docs:fixture -->\n%s\n<!-- <<< gen-docs -->\n" % PASSAGE
        _append(root, FIX_LAUNCHER, region)
        _append(root, FIX_AGENT, region)
        ctl.check("the passage inside a gen-docs region in both files is green", red(root), [])

        root = fresh()
        _mutate(root, "CLAUDE.md", "papa.<!-- /scope -->", "papa " + PASSAGE + "<!-- /scope -->")
        _mutate(root, FIX_AGENT, "oscar papa.\n", "oscar papa " + PASSAGE + "\n")
        ctl.check(
            "the passage inside registered spans of one clause in both files is green",
            red(root),
            [],
        )
        _append(root, FIX_LAUNCHER, "\n" + PASSAGE + "\n")
        found_pairs = pair(red(root))
        ctl.check(
            "a canonical span copied into unregistered text elsewhere is red, naming both",
            (CLAUDE_MD, FIX_LAUNCHER) in found_pairs and (FIX_LAUNCHER, FIX_AGENT) in found_pairs,
            True,
        )
        ctl.check(
            "and the registered pair (canonical and its mirror) stays exempt",
            (CLAUDE_MD, FIX_AGENT) in found_pairs,
            False,
        )

        root = fresh()
        _mutate(
            root,
            "CLAUDE.md",
            "papa.<!-- /scope -->",
            "papa " + PASSAGE + "<!-- /scope -->\n\n" + _words(30, "tail"),
        )
        _mutate(
            root,
            FIX_AGENT,
            "oscar papa.\n",
            "oscar papa " + PASSAGE + "\n" + _words(30, "tail") + "\n",
        )
        found = red(root)
        ctl.check(
            "a registered pair splits a run: the unregistered 30-word stretch beside it is red alone",
            [(r.path_a, r.path_b, len(r.words)) for r in found],
            [(CLAUDE_MD, FIX_AGENT, 30)],
        )

        root = fresh()
        _append(root, FIX_LAUNCHER, "\n- <!-- scope: pr.fix-rule -->" + PASSAGE + "\n")
        _append(root, FIX_AGENT, "\n" + PASSAGE + "\n")
        ctl.check(
            "the passage under an anchor the registry does not name for that file is red",
            pair(red(root)),
            [(FIX_LAUNCHER, FIX_AGENT)],
        )
        root = fresh()
        _append(root, FIX_LAUNCHER, "\n- <!-- scope: pr.unknown-rule -->" + PASSAGE + "\n")
        _append(root, FIX_AGENT, "\n- <!-- scope: pr.unknown-rule -->" + PASSAGE + "\n")
        ctl.check(
            "the passage under an unregistered anchor in both files is red",
            pair(red(root)),
            [(FIX_LAUNCHER, FIX_AGENT)],
        )

        # A clause canonical in the agent file (the per-clause `canonical` key): its closed span is excluded there.
        moved = fixture_registry()
        moved["clauses"]["pr.agent-rule"] = {
            "canonical": FIX_AGENT,
            "sha": "0" * 12,
            "atoms": ["x"],
            "sentinels": ["x"],
            "mirrors": [{"path": FIX_MERGE, "mode": "ref"}],
        }
        root = fresh(moved)
        _append(root, FIX_AGENT, "\n<!-- scope: pr.agent-rule -->" + PASSAGE + "<!-- /scope -->\n")
        _append(root, FIX_MERGE, "\n<!-- scope: pr.agent-rule -->" + PASSAGE + "\n")
        ctl.check(
            "a clause canonical in the agent file is exempt against its registered mirror copy",
            red(root),
            [],
        )
        root = fresh(moved)
        _append(root, FIX_AGENT, "\n<!-- scope: pr.agent-rule -->" + PASSAGE + "<!-- /scope -->\n")
        _append(root, FIX_MERGE, "\n- <!-- scope: pr.fix-rule -->" + PASSAGE + "\n")
        ctl.check(
            "the same text under a span of a DIFFERENT clause is red",
            pair(red(root)),
            [(FIX_AGENT, FIX_MERGE)],
        )
        root = fresh(moved)
        _append(root, FIX_AGENT, "\n<!-- scope: pr.agent-rule -->" + PASSAGE + "<!-- /scope -->\n")
        _append(root, FIX_LAUNCHER, "\n" + PASSAGE + "\n")
        ctl.check(
            "the agent's canonical span appended to the launcher unregistered is red (the T2 shape)",
            pair(red(root)),
            [(FIX_LAUNCHER, FIX_AGENT)],
        )
        root = fresh()
        _append(root, FIX_AGENT, "\n<!-- scope: pr.agent-rule -->" + PASSAGE + "<!-- /scope -->\n")
        _append(root, FIX_MERGE, "\n" + PASSAGE + "\n")
        ctl.check(
            "the same span is red while the registry does not name it",
            pair(red(root)),
            [(FIX_AGENT, FIX_MERGE)],
        )

        root = fresh()
        _append(root, FIX_LAUNCHER, "\n" + PASSAGE[: len(PASSAGE) // 2] + "\n\n")
        _append(root, FIX_AGENT, "\n" + PASSAGE[: len(PASSAGE) // 2] + "\n")
        ctl.check("half the passage, under the threshold, is green", red(root), [])

        # -- refusals ----------------------------------------------------------
        root = fresh()
        (root / FIX_MERGE).unlink()
        ctl.check("a missing family file is rc 2, never a pass", _report_rc(root), 2)
        root = fresh()
        _write(root, FIX_MERGE, "<!-- nothing but a comment -->\n```\ncode\n```\n")
        ctl.check("a family file with zero words is rc 2", _report_rc(root), 2)
        root = fresh()
        (root / sm.REGISTRY_REL).unlink()
        ctl.check("a missing scope registry is rc 2", _report_rc(root), 2)
        empty = base / "empty"
        empty.mkdir()
        ctl.check("an empty root is rc 2", _report_rc(empty), 2)

    return 0 if ctl.report() else 1


def _report_rc(root: pathlib.Path) -> int:
    """`report` with its chatter captured."""
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        return report(root)


# --------------------------------------------------------------------------- entry

USAGE = "usage: check_prose_duplication.py [--root DIR] [--selftest]"


def main(argv: list[str] | None = None, root: pathlib.Path | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args == ["--selftest"]:
        return selftest()
    tree = root if root is not None else paths.repo_root()
    if "--root" in args:
        i = args.index("--root")
        if i + 1 >= len(args):
            print(USAGE, file=sys.stderr)
            return 2
        tree = pathlib.Path(args[i + 1]).resolve()
        del args[i : i + 2]
    if args:
        print(USAGE, file=sys.stderr)
        return 2
    rc = controls_first("prose duplication", lambda: selftest(verbose=False))
    if rc:
        return rc
    return report(tree)


__all__ = [
    "FAMILY",
    "THRESHOLD",
    "Extract",
    "Run",
    "Word",
    "extract",
    "judge",
    "main",
    "registered_ids",
    "report",
    "scope_ranges",
    "selftest",
    "shared_runs",
]
