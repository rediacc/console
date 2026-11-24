#!/usr/bin/env python3
"""Census of PreToolUse guard refusals in session transcripts (PLAN-tooling-code-reduction CR5, Context item 7).

WHAT IT COUNTS. A refusal is a `tool_result` block in a `user` record whose text opens with `PreToolUse:<Tool> hook error:`: the harness wrote it because the guard chain exited non-zero and refused the call. Advisory output (`hook additional context`) is not a refusal and is not counted. Each result is counted once, keyed on its `tool_use_id`.

HOW A REFUSAL BECOMES A GUARD. Before CR7 the chain printed no guard name, so the text is the only witness. Every guard module and every helper module a guard imports is parsed with `ast`; its string literals, split at format placeholders and line breaks, become fingerprints. A fragment found in k modules scores len/k, the best-scoring module is taken, and only guards whose CHAIN serves the refused tool are candidates (see `Matcher` for a helper module's text). A refusal no fragment matches is reported as UNMAPPED and never folded into a guard's count.

ANTI-VACUITY. Zero transcripts, zero refusals or zero guards is a failure, never an empty table. An unmapped share above --max-unmapped is a failure too: it means the fingerprints no longer describe the guards. With --ledger, each refusal inside the CR7 ledger's window is joined to its ledger line (same session, same chain, within --join-seconds) and the agreement is printed; a disagreement is a failure.

PRIVACY. The output holds guard names, counts and dates only. No transcript text is written.

  python3 scripts/census/guard-fires.py --selftest
  python3 scripts/census/guard-fires.py [--since 2026-09-15] [--until 2026-11-21] [--write scripts/census/guard-fires.tsv]
  python3 scripts/census/guard-fires.py --since 2026-11-23 --ledger
"""

import argparse
import ast
import collections
import datetime
import json
import pathlib
import re
import sys
import tempfile
from typing import NamedTuple

REPO = pathlib.Path(__file__).resolve().parents[2]
GUARDS = REPO / ".claude" / "rediacc_hooks" / "guards"
DEFAULT_PROJECTS = pathlib.Path.home() / ".claude" / "projects" / "-home-developer-console"
DEFAULT_LEDGER = REPO / ".ci" / "cache" / "hook-ledger" / "chains.jsonl"

TOOL_CHAIN = {
    "Bash": "pre-bash",
    "Edit": "pre-edit",
    "MultiEdit": "pre-edit",
    "Write": "pre-edit",
    "NotebookEdit": "pre-edit",
    "Agent": "pre-agent",
    "Task": "pre-agent",
    # The Bash matcher's chain also judges Monitor commands: the transcripts carry `PreToolUse:Monitor` refusals in pre-bash guards' words.
    "Monitor": "pre-bash",
    "AskUserQuestion": "pre-ask",
}
REFUSAL = re.compile(r"^PreToolUse:(\w+) hook error:")
PLACEHOLDER = re.compile(r"%(?:\([^)]*\))?[-#0 +]*\d*(?:\.\d+)?[sdrfxi%]|\{[^{}]*\}")
MIN_FRAGMENT = 24
# Modules whose strings are plumbing, not refusal text: folding them in would give every guard the same fingerprints.
PLUMBING = ("hookio", "shellscan", "syspath", "guards/tables", "wellknown")
GUARD_PREFIXES = ("block_", "warn_", "require_")
# Guards whose refusal text lives in a file they load by path, which no import statement names. Each path must exist: a moved file fails the census rather than silently unmapping that guard's refusals.
# Each entry is (path, top-level names whose literals are the text), so two guards reading one file keep separate fingerprints.
EXTERNAL = {
    "block_raw_ci_read": (
        (".claude/hooks/lib/sanctioned.py", ("CI_READ_VERBS", "ci_read_use", "ci_read_message")),
    ),
    "block_adhoc_sanctioned": ((".claude/hooks/lib/sanctioned.py", ("REGISTRY", "message")),),
}
UNMAPPED = "(unmapped)"


def _squash(text):
    return " ".join(text.split())


def _top_names(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {t.id for t in node.targets if isinstance(t, ast.Name)}
    return set()


def literals(source, names=None):
    """Every string literal of a module that is not a docstring, f-string constant parts included; with `names`, only those under the named top-level definitions."""
    tree = ast.parse(source)
    if names is not None:
        tree = ast.Module(
            body=[n for n in tree.body if _top_names(n) & set(names)], type_ignores=[]
        )
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                skip.add(id(body[0].value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    skip.add(id(part))
                    out.append(part.value)
        elif (
            isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
        ):
            out.append(node.value)
    return out


def fragments(source, names=None):
    """The fingerprint pieces of a module: literals cut at placeholders and line breaks, squashed, MIN_FRAGMENT chars or more."""
    found = set()
    for lit in literals(source, names):
        for piece in PLACEHOLDER.split(lit):
            for raw in piece.split("\n"):
                line = _squash(raw)
                if len(line) >= MIN_FRAGMENT:
                    found.add(line)
    return found


def _imports(source):
    """Paths (relative to rediacc_hooks/, no suffix) of the rediacc_hooks modules a module imports."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if node.module in ("rediacc_hooks", "rediacc_hooks.guards"):
            prefix = "" if node.module == "rediacc_hooks" else "guards/"
            names.update(prefix + a.name for a in node.names)
        elif node.module.startswith("rediacc_hooks."):
            names.add("/".join(node.module.split(".")[1:]))
    return names


def _assigned(source, name):
    for node in ast.parse(source).body:
        named = isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        )
        if named and isinstance(node.value, ast.Constant):
            return node.value.value
    return None


class Guard(NamedTuple):
    chain: "str | None"
    order: int
    helpers: "frozenset[str]"


def load_guards(guards_dir=GUARDS):
    """({stem: Guard}, {module: {fragment, ...}}) for every block_/warn_/require_ guard and every helper module a guard imports.

    A helper is a guards/_x module or a top-level rediacc_hooks module outside PLUMBING. A guard importing ANOTHER guard does not inherit its fragments: the imported guard's refusals are its own, and folding them in made three importers of one widely imported guard tie with it.
    """
    guards_dir = pathlib.Path(guards_dir)
    hooks_dir = guards_dir.parent
    guards, modules = {}, {}
    for path in sorted(guards_dir.glob("*.py")):
        stem = path.stem
        if not stem.startswith(GUARD_PREFIXES):
            continue
        source = path.read_text()
        modules[stem] = fragments(source)
        helpers = set()
        for rel in _imports(source) - set(PLUMBING):
            base = rel.rsplit("/", 1)[-1]
            if base.startswith(GUARD_PREFIXES):
                continue
            helper = hooks_dir / (rel + ".py")
            if not helper.is_file():
                continue
            if rel not in modules:
                modules[rel] = fragments(helper.read_text())
            helpers.add(rel)
        for rel, names in EXTERNAL.get(stem, ()):
            ext = REPO / rel
            if not ext.is_file():
                raise SystemExit(
                    "guard-fires: EXTERNAL names %s for %s and it does not exist; fix the table"
                    % (rel, stem)
                )
            frags = fragments(ext.read_text(), names)
            if not frags:
                raise SystemExit(
                    "guard-fires: EXTERNAL %s %s yields no text for %s; fix the table"
                    % (rel, names, stem)
                )
            key = "%s:%s" % (rel, stem)
            modules[key] = frags
            helpers.add(key)
        guards[stem] = Guard(
            _assigned(source, "CHAIN"), _assigned(source, "ORDER") or 0, frozenset(helpers)
        )
    return guards, modules


class Matcher:
    """Finds the module whose text best explains a refusal, then the guard that module speaks for.

    A fragment found in k modules weighs len/k, so the text unique to one module decides. A guard module speaks for itself. A helper module speaks for the guards importing it on the refused tool's chain; of those, the one whose OWN text explains the most of the refusal BEYOND the best module is chosen (a guard binding a helper's row usually adds a line of its own, while a guard that merely holds a copy of the helper's lines adds nothing), and only a tie there falls to the lowest ORDER: dispatch runs a chain in ORDER and stops at the first refusal, so a check shared through a helper refuses under the first guard that runs it. Each refusal decided by ORDER is counted in `by_order`, so the reader sees how much of the census rests on that rule.
    """

    def __init__(self, guards, modules):
        self.guards = guards
        self.modules = modules
        owners = collections.Counter()
        for frags in modules.values():
            owners.update(frags)
        self.weight = {f: len(f) / n for f, n in owners.items()}
        self.speaks = collections.defaultdict(list)
        for stem, g in guards.items():
            self.speaks[stem].append(stem)
            for helper in g.helpers:
                self.speaks[helper].append(stem)
        self.by_order = 0

    def classify(self, tool, text):
        chain = TOOL_CHAIN.get(tool)
        flat = _squash(text)
        scored = []
        for name, frags in self.modules.items():
            cands = [s for s in self.speaks[name] if self.guards[s].chain == chain]
            if not cands:
                continue
            hit = {f for f in frags if f in flat}
            if hit:
                scored.append((sum(self.weight[f] for f in hit), name, cands, hit))
        if not scored:
            return UNMAPPED
        top = max(row[0] for row in scored)
        best = [row for row in scored if row[0] == top]
        shown = set().union(*(row[3] for row in best))
        # A candidate's OWN extra: matched text in its own module beyond what the best module(s) already explain. A fragment overlapping an explained one (either holds the other) is the same words cut at a different line break, so it is not extra.
        extra = {
            row[1]: sum(self.weight[f] for f in row[3] if not any(f in g or g in f for g in shown))
            for row in scored
            if row[1] in self.guards
        }
        cands = sorted(
            {s for row in best for s in row[2]},
            key=lambda s: (-extra.get(s, 0), self.guards[s].order, s),
        )
        if len(cands) > 1 and extra.get(cands[0], 0) == extra.get(cands[1], 0):
            self.by_order += 1
        return cands[0]


def _result_text(block):
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def refusals(paths):
    """Yield (key, session, ts, tool, text) once per refused call."""
    seen = set()
    for path in paths:
        with open(path, "rb") as fh:
            for raw in fh:
                if b"PreToolUse:" not in raw or b"hook error" not in raw:
                    continue
                rec = json.loads(raw)
                if rec.get("type") != "user":
                    continue
                content = (rec.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    text = _result_text(block)
                    m = REFUSAL.match(text)
                    if not m:
                        continue
                    key = block.get("tool_use_id") or (str(path), rec.get("uuid"))
                    if key in seen:
                        continue
                    seen.add(key)
                    yield key, rec.get("sessionId", ""), rec.get("timestamp", ""), m.group(1), text


def _parse_ts(ts):
    return datetime.datetime.fromisoformat(ts)


def ledger_join(rows, ledger_path, seconds):
    """(agree, [(census, ledger stems)], unmatched) of classified rows against the CR7 ledger's refusing stems."""
    lines = []
    with open(ledger_path) as fh:
        for raw in fh:
            rec = json.loads(raw)
            if rec.get("refused_by"):
                lines.append(
                    (rec["session"], rec["chain"], _parse_ts(rec["ts"]), rec["refused_by"])
                )
    if not lines:
        raise SystemExit(
            "guard-fires: %s holds no refusal line; nothing to join against" % ledger_path
        )
    start = min(t for _, _, t, _ in lines)
    agree, disagree, unmatched = 0, [], 0
    for session, ts, tool, stem in rows:
        when = _parse_ts(ts)
        if when < start:
            continue
        chain = TOOL_CHAIN.get(tool)
        hits = {
            g
            for s, c, t, g in lines
            if s == session and c == chain and abs((t - when).total_seconds()) <= seconds
        }
        if not hits:
            unmatched += 1
        elif stem in hits:
            agree += 1
        else:
            disagree.append((stem, sorted(hits)))
    return agree, disagree, unmatched


def census(projects, guards_dir, since, until):
    paths = sorted(pathlib.Path(projects).rglob("*.jsonl"))
    if not paths:
        raise SystemExit(
            "guard-fires: no transcripts under %s; the census would count nothing" % projects
        )
    guards, modules = load_guards(guards_dir)
    if not guards:
        raise SystemExit("guard-fires: no guard modules under %s" % guards_dir)
    matcher = Matcher(guards, modules)
    rows = []
    for _key, session, ts, tool, text in refusals(paths):
        if since <= ts[:10] <= until:
            rows.append((session, ts, tool, matcher.classify(tool, text)))
    return paths, guards, rows, matcher.by_order


def table(guards, rows):
    """(stem, chain, fires, first, last) per guard, never-fired guards included with 0, most-fired first."""
    stats = {}
    for _s, ts, _t, stem in rows:
        n, first, last = stats.get(stem, (0, ts, ts))
        stats[stem] = (n + 1, min(first, ts), max(last, ts))
    out = []
    for stem in sorted(set(guards) | set(stats), key=lambda s: (-stats.get(s, (0,))[0], s)):
        n, first, last = stats.get(stem, (0, "", ""))
        chain = guards[stem].chain if stem in guards else "-"
        out.append((stem, chain, n, first[:10] or "-", last[:10] or "-"))
    return out


def selftest():
    guard_a = 'CHAIN = "pre-bash"\ndef run(ev):\n    """doc: never a fingerprint, said the docstring of this guard."""\n    return ev.deny("BLOCKED: a force push rewrites the remote branch history.\\n  use: git push\\n")\n'
    guard_b = 'CHAIN = "pre-bash"\nMSG = "BLOCKED: this `pkill -f` pattern matches the shell running %s now" % 1\n'
    guard_c = (
        'CHAIN = "pre-edit"\nMSG = "BLOCKED: a force push rewrites the remote branch history.\\n"\n'
    )
    with tempfile.TemporaryDirectory() as tmp:
        g = pathlib.Path(tmp) / "guards"
        g.mkdir()
        (g / "block_a.py").write_text(guard_a)
        (g / "block_b.py").write_text(guard_b)
        (g / "block_c.py").write_text(guard_c)
        (g / "_shared.py").write_text(
            'M = "BLOCKED: the shared helper refuses this commit shape outright."\n'
        )
        (g / "block_d.py").write_text(
            'from rediacc_hooks.guards import _shared\nCHAIN = "pre-bash"\nORDER = 9\n'
        )
        (g / "block_e.py").write_text(
            'from rediacc_hooks.guards import _shared\nCHAIN = "pre-bash"\nORDER = 4\n'
        )
        (g / "block_g.py").write_text(
            'from rediacc_hooks.guards import _shared\nCHAIN = "pre-bash"\nORDER = 20\nX = "  the review row of this guard adds its own closing line."\n'
        )
        (g / "block_f.py").write_text(
            'from rediacc_hooks.guards import block_a\nCHAIN = "pre-bash"\nORDER = 1\n'
        )
        m = Matcher(*load_guards(g))
        checks = [
            # must fire: each guard's own text maps to it, across a re-wrapped line
            (
                "own text",
                m.classify(
                    "Bash",
                    "PreToolUse:Bash hook error: [x]: BLOCKED: a force push rewrites the remote branch\nhistory.\n  use: git push",
                ),
                "block_a",
            ),
            (
                "placeholder split",
                m.classify(
                    "Bash",
                    "PreToolUse:Bash hook error: BLOCKED: this `pkill -f` pattern matches the shell running 7 now",
                ),
                "block_b",
            ),
            # the chain decides between two guards sharing one text
            (
                "chain tiebreak",
                m.classify(
                    "Edit",
                    "PreToolUse:Edit hook error: BLOCKED: a force push rewrites the remote branch history.",
                ),
                "block_c",
            ),
            # a helper's text goes to its first importer in chain ORDER; an imported GUARD's text stays with that guard
            (
                "helper by order",
                m.classify(
                    "Bash",
                    "PreToolUse:Bash hook error: BLOCKED: the shared helper refuses this commit shape outright.",
                ),
                "block_e",
            ),
            (
                "own text over order",
                m.classify(
                    "Bash",
                    "PreToolUse:Bash hook error: BLOCKED: the shared helper refuses this commit shape outright. the review row of this guard adds its own closing line.",
                ),
                "block_g",
            ),
            (
                "imported guard",
                m.classify(
                    "Bash",
                    "PreToolUse:Bash hook error: BLOCKED: a force push rewrites the remote branch history.",
                ),
                "block_a",
            ),
            # must NOT fire: unknown text, a docstring phrase, a tool no chain serves
            (
                "unknown text",
                m.classify(
                    "Bash", "PreToolUse:Bash hook error: something nobody wrote down at all"
                ),
                UNMAPPED,
            ),
            (
                "docstring",
                m.classify(
                    "Bash",
                    "PreToolUse:Bash hook error: doc: never a fingerprint, said the docstring of this guard.",
                ),
                UNMAPPED,
            ),
            (
                "unserved tool",
                m.classify(
                    "Read",
                    "PreToolUse:Read hook error: BLOCKED: a force push rewrites the remote branch history.",
                ),
                UNMAPPED,
            ),
        ]
        t = pathlib.Path(tmp) / "t.jsonl"
        recs = [
            {
                "type": "user",
                "sessionId": "s",
                "timestamp": "2026-10-01T00:00:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "u1",
                            "content": "PreToolUse:Bash hook error: x",
                        }
                    ]
                },
            },
            {
                "type": "user",
                "sessionId": "s",
                "timestamp": "2026-10-01T00:00:01Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "u1",
                            "content": "PreToolUse:Bash hook error: x",
                        }
                    ]
                },
            },
            {
                "type": "user",
                "sessionId": "s",
                "timestamp": "2026-10-01T00:00:02Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "u2",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "PreToolUse:Agent hook additional context: hook error advisory",
                                }
                            ],
                        }
                    ]
                },
            },
            {
                "type": "assistant",
                "sessionId": "s",
                "timestamp": "2026-10-01T00:00:03Z",
                "message": {
                    "content": [{"type": "text", "text": "PreToolUse:Bash hook error: quoted"}]
                },
            },
        ]
        t.write_text("".join(json.dumps(r) + "\n" for r in recs))
        checks.append(
            ("one refusal: dedup, advisory and assistant echo skipped", len(list(refusals([t]))), 1)
        )
    bad = [(name, got, want) for name, got, want in checks if got != want]
    for name, got, want in bad:
        print("SELFTEST FAIL %s: got %r, want %r" % (name, got, want), file=sys.stderr)
    if bad:
        return 1
    print("guard-fires selftest: %d checks passed" % len(checks))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--projects", default=str(DEFAULT_PROJECTS))
    ap.add_argument("--guards", default=str(GUARDS))
    ap.add_argument("--since", default="2026-09-15")
    ap.add_argument("--until", default="2026-11-21")
    ap.add_argument("--write", help="write the TSV table to this path instead of stdout")
    ap.add_argument(
        "--ledger",
        nargs="?",
        const=str(DEFAULT_LEDGER),
        help="join refusals against the CR7 hook ledger instead of printing the table",
    )
    ap.add_argument("--join-seconds", type=float, default=5.0)
    ap.add_argument("--max-unmapped", type=float, default=0.05)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.ledger:
        args.until = "9999-12-31"
    paths, guards, rows, by_order = census(args.projects, args.guards, args.since, args.until)
    if not rows:
        print(
            "guard-fires: %d transcripts read, ZERO refusals in %s..%s; the census is not seeing them"
            % (len(paths), args.since, args.until),
            file=sys.stderr,
        )
        return 1
    rc = 0
    if args.ledger:
        agree, disagree, unmatched = ledger_join(rows, args.ledger, args.join_seconds)
        print(
            "ledger join: %d agree, %d disagree, %d without a ledger line"
            % (agree, len(disagree), unmatched)
        )
        for stem, hits in disagree:
            print("  DISAGREE: census says %s, ledger says %s" % (stem, ",".join(hits)))
        if agree == 0 or disagree:
            rc = 1
    else:
        lines = [
            "# guard\tchain\tfires\tfirst\tlast\t(window %s..%s, generated by scripts/census/guard-fires.py)"
            % (args.since, args.until)
        ]
        lines += ["%s\t%s\t%d\t%s\t%s" % r for r in table(guards, rows)]
        text = "\n".join(lines) + "\n"
        if args.write:
            pathlib.Path(args.write).write_text(text)
        else:
            sys.stdout.write(text)
    total = len(rows)
    unmapped = sum(1 for r in rows if r[3] == UNMAPPED)
    blocking = sorted(g for g in guards if g.startswith("block_"))
    fired = {r[3] for r in rows} - {UNMAPPED}
    never = [g for g in blocking if g not in fired]
    print(
        "guard-fires: %d transcripts, %d refusals in %s..%s, %d mapped to %d of %d guards (%d blocking), %d of them by chain ORDER, %d unmapped"
        % (
            len(paths),
            total,
            args.since,
            args.until,
            total - unmapped,
            len(fired),
            len(guards),
            len(blocking),
            by_order,
            unmapped,
        ),
        file=sys.stderr,
    )
    print("never-fired blocking guards (%d): %s" % (len(never), " ".join(never)), file=sys.stderr)
    if unmapped > args.max_unmapped * total:
        print(
            "guard-fires: unmapped share %.1f%% exceeds %.1f%%; the fingerprints no longer describe the guards"
            % (100.0 * unmapped / total, 100 * args.max_unmapped),
            file=sys.stderr,
        )
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
