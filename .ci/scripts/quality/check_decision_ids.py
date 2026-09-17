#!/usr/bin/env python3
"""check:ci-decision-ids -- every cited decision id resolves to a row, and a
supersession is stated out loud.

WHY THIS GATE EXISTS, and it has a measurement rather than an opinion.

Three id schemes collided on the same-looking token and two ADJACENT boxes of `agent/PLAN-tooling-transformation.md` ended up pointing at OPPOSITE FILES. `W12 P2.7` cited "A5 in `docs/ci-overhaul/04-decisions.md`"; `grep` for that token in that file returns 0, because it meant the GATE RULE at `.ci/scripts/quality/check_plan_boxes.py:41`. Box X0.1 fixed the source on 2026-09-08 by
PREFIXING: gate rules became `G-A<n>`, operator decisions `D-A<n>`. A prefix stops the collision recurring by transcription. It does not, on its own, stop a `D-` id from naming nothing at all, which is the same failure one step later: a pointer that looks authoritative and resolves to no row.

So this gate is the other half of X0.1. `agent/DECISIONS.md` holds the rows; this holds the rows and their citations to each other.

WHAT "ENFORCING A LICENCE" CAN MEAN, stated here so nobody builds the impossible. `D-A6` is a standing operator licence to substitute a better design, provided the substitution is stated out loud. NO GATE CAN TELL A GOOD SUBSTITUTION FROM A BAD ONE. What a gate CAN assert is the licence's PRECONDITION: that the substitution was stated, at a pointer that resolves, naming the licence
it was taken under.

THE RULES.

  R1  Every row is well formed: the id matches `D-<SRC><n>`, no id repeats, and
      `Status` is either `live` or `superseded-by D-<id>`.
  R2  Every row's `Source` resolves to a real file and a real line, through
      `wl_planrec.resolve` and NOTHING ELSE. There is deliberately no second
      resolver here: `citation_state`'s path regex carries five separately
      paid-for extension rounds (dotfiles, .astro, .mdx, .cast, leading dots),
      and a fresh regex in this file would re-open every one of them. This is
      the same stance `check_plan_citations.py` takes, for the same reason.
  R3  A `superseded-by D-x` names a row that exists and is not the row itself.
  R4  A row's `Licence`, when present, names a row that exists and is itself
      still `live`. A licence that has been superseded cannot authorise
      anything, and a row still leaning on one is the interesting case.
  R5  THE LICENCE PRECONDITION. A supersession that is in HEAD and was not in the
      base must be cited by a commit in `base..HEAD`. This is the only rule here
      that reads git history, and it is the one that makes a substitution
      audible: the id appears where a reader of `git log` will find it, not only
      where a reader of the register will.
  R6  Every `D-<SRC><n>` token cited anywhere in the tracked `agent/**` and
      `docs/**` markdown corpus resolves to a row.

WHAT R5 CANNOT SEE, stated so a green is not read as more than it is. It compares two COMMITTED versions of the register, so a supersession sitting uncommitted in a working tree is not judged until it is committed. That is not a hedge, it is the rule's own definition: the requirement is a COMMIT citing the id, and an uncommitted edit has no commit to cite it. In CI on a pull
request the working tree is the head commit, so the same code path answers the same question with nothing outstanding. When there is no usable base, R5 is SKIPPED and the summary says so, because a skip must never read as a clean result.

ANTI-VACUITY, three refusals, because "no findings" and "read nothing" look identical from the outside.

  * A register with ZERO rows is a failure. Every other rule here is a statement
    about rows, so with no rows they all pass and the green means nothing.
  * A corpus scan that reads ZERO files is a failure. The glob has collapsed.
  * ZERO cited ids across the whole corpus is a failure. `D-A6` is cited four
    times today; the day the extractor breaks, every citation becomes invisible
    and R6 reports a clean tree it never looked at.

The success line prints the SHAPE, not just a verdict: rows, source keys, cited ids, files scanned, and how many rows are superseded. A reader can then notice when a number collapses.

Exit 0 green, 1 findings or vacuous input, 2 instrument control failed.

---- gate ---- step: Decision ids needs: none lane: quality-branch
env-GITHUB_BASE_REF: ${{ github.base_ref }}
---- end gate ----
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

import _cipath  # noqa: F401
from rediacc_ci import controls, paths

ROOT = pathlib.Path(
    os.environ.get("DECISION_IDS_ROOT") or pathlib.Path(__file__).resolve().parents[3]
)
# The hop onto the Stop hook's directory, through the package's own resolver. `paths.on_sys_path` is idempotent where a bare `sys.path.insert(0, d)` is not, and `paths.hooks_stop_dir` is the ONE place the `.claude/hooks/stop` literal lives, so the move planned for that program is a one-line change there rather than a sweep of nine call sites. ROOT is passed explicitly: this gate
# honours its own DECISION_IDS_ROOT override, which the resolver's default root does not read.
paths.on_sys_path(paths.hooks_stop_dir(ROOT))

try:
    import wl_planrec as R
except ImportError as _exc:  # pragma: no cover -- exercised by the anti-vacuity harness
    # A check that cannot see must SAY it cannot see. Every pointer this gate resolves goes through that module on purpose; without it there is no oracle and no verdict to give.
    print(
        "VACUOUS INPUT: cannot import the citation resolver from %s (%s). This gate "
        "resolves pointers ONLY through wl_planrec, so without it it has no oracle."
        % (ROOT / ".claude" / "hooks" / "stop", _exc),
        file=sys.stderr,
    )
    sys.exit(1)

#: The register, relative to ROOT. `DECISION_IDS_REGISTER` is the test seam: it
#: lets a control drive a mutated register through the REAL entry point without
#: writing to the tracked file, the same shape as `LANGUAGE_POLICY_ALLOWLIST`.
REGISTER_REL = "agent/DECISIONS.md"

#: An id. The uppercase source key is the whole point of the prefix: it is what
#: keeps `D-6` (an OPEN DECISION POINT label in docs/ci-overhaul/04-decisions.md,
#: which is a question and not a decision) out of this grammar by construction
#: rather than by a reader being careful.
ID_RE = re.compile(r"\bD-[A-Z]+[0-9]+\b")
ID_EXACT_RE = re.compile(r"^D-[A-Z]+[0-9]+$")
SUPERSEDED_RE = re.compile(r"^superseded-by\s+(D-[A-Z]+[0-9]+)$")

#: Where a citation may live. Markdown only: the measured population is entirely
#: prose, and widening to source files would put every gate's own docstring in
#: scope on a different day's evidence.
CORPUS_DIRS = ("agent", "docs")


def _git(root, *args):
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
        ).stdout
    except OSError:
        return ""


def register_path(root):
    override = os.environ.get("DECISION_IDS_REGISTER")
    return pathlib.Path(override) if override else pathlib.Path(root) / REGISTER_REL


def register_label():
    """What a finding should CALL the register. Under the seam that is the
    override path, not `agent/DECISIONS.md`: a control that reds while naming a
    file it did not read is a control a reader cannot check."""
    return os.environ.get("DECISION_IDS_REGISTER") or REGISTER_REL


def parse_rows(text):
    """[{id, decision, source, status, licence, notes, line}] from a register.

    THE TABLE IS THE GRAMMAR. A row is a markdown table line whose first cell is an exact id, which is why the separator row, the source-key table above it and every sentence of prose in the file are invisible here without a single special case. A cell is stripped; an empty cell is the empty string.
    """
    rows = []
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or not ID_EXACT_RE.match(cells[0]):
            continue
        rows.append(
            {
                "id": cells[0],
                "decision": cells[1],
                "source": cells[2],
                "status": cells[3],
                "licence": cells[4] if len(cells) > 4 else "",
                "notes": cells[5] if len(cells) > 5 else "",
                "line": n,
            }
        )
    return rows


def superseded_target(status):
    """The id a `superseded-by` status names, or None. Not a truthiness test:
    `live` and a malformed status are different findings and R1 tells them
    apart."""
    m = SUPERSEDED_RE.match((status or "").strip())
    return m.group(1) if m else None


def judge_rows(root, rows, label=REGISTER_REL):
    """R1 to R4 over the parsed rows. Returns a list of finding strings."""
    out = []
    seen = {}
    for row in rows:
        rid = row["id"]
        if rid in seen:
            out.append(
                "%s:%d: id %s repeats (first at line %d); an id that names two rows "
                "resolves to neither" % (label, row["line"], rid, seen[rid])
            )
        seen[rid] = row["line"]
    ids = set(seen)

    for row in rows:
        # -- R2 the source pointer -----------------------------------------
        src = row["source"]
        if not src:
            out.append(
                "%s:%d: %s has no Source. A decision with no pointer to where it was "
                "made cannot be checked by anyone" % (label, row["line"], row["id"])
            )
        else:
            ok, why = R.resolve(root, "fileline", src)
            if not ok:
                out.append(
                    "%s:%d: %s cites Source `%s` -- %s" % (label, row["line"], row["id"], src, why)
                )

        # -- R1/R3 the status ----------------------------------------------
        status = row["status"]
        target = superseded_target(status)
        if status != "live" and target is None:
            out.append(
                "%s:%d: %s has Status `%s`; it must be `live` or `superseded-by D-<id>`"
                % (label, row["line"], row["id"], status)
            )
        elif target is not None:
            if target == row["id"]:
                out.append(
                    "%s:%d: %s is superseded by itself, which supersedes nothing"
                    % (label, row["line"], row["id"])
                )
            elif target not in ids:
                out.append(
                    "%s:%d: %s is superseded by %s, which is not a row here. Add the "
                    "superseding decision as a row; do not point at an id that does not exist"
                    % (label, row["line"], row["id"], target)
                )

        # -- R4 the licence --------------------------------------------------
        lic = row["licence"]
        if lic:
            if not ID_EXACT_RE.match(lic):
                out.append(
                    "%s:%d: %s has Licence `%s`, which is not an id"
                    % (label, row["line"], row["id"], lic)
                )
            elif lic not in ids:
                out.append(
                    "%s:%d: %s was taken under licence %s, which is not a row here"
                    % (label, row["line"], row["id"], lic)
                )
            else:
                lic_row = next(r for r in rows if r["id"] == lic)
                if superseded_target(lic_row["status"]) is not None:
                    out.append(
                        "%s:%d: %s leans on licence %s, which is itself %s. A superseded "
                        "licence cannot authorise anything; re-state the substitution "
                        "under the licence that replaced it"
                        % (
                            label,
                            row["line"],
                            row["id"],
                            lic,
                            lic_row["status"],
                        )
                    )
    return out


def corpus_files(root):
    """Tracked markdown under the corpus dirs, plus the register itself.

    `git ls-files`, so an untracked scratch file cannot red the tree and a deleted one cannot survive in it. THE REGISTER IS ADDED UNCONDITIONALLY when it exists on disk, because on the change that introduces it the register is still untracked and `ls-files` does not list it -- which would have left the citation count at 1 on the very run that added twenty-one rows, a number one
    step from the vacuity floor for a reason that has nothing to do with the tree.
    """
    out = []
    for d in CORPUS_DIRS:
        for raw in _git(root, "ls-files", "--", d).split("\n"):
            rel = raw.strip()
            if rel.endswith(".md"):
                out.append(rel)
    if REGISTER_REL not in out and (pathlib.Path(root) / REGISTER_REL).is_file():
        out.append(REGISTER_REL)
    return sorted(out)


def cited_ids(root, files):
    """{id: [rel:line, ...]} over the corpus. The extractor R6 is floored on."""
    hits = {}
    for rel in files:
        try:
            text = (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, raw in enumerate(text.splitlines(), start=1):
            for tok in ID_RE.findall(raw):
                hits.setdefault(tok, []).append("%s:%d" % (rel, n))
    return hits


def added_supersessions(root, base):
    """{id: target} for supersessions in HEAD that the base did not have.

    Reads two COMMITTED versions of the register through `git show`, which no working tree can rewrite. Returns None when there is no usable base, so the caller can SKIP loudly rather than report a clean R5.
    """
    if not base:
        return None
    head_text = _git(root, "show", "HEAD:%s" % REGISTER_REL)
    if not head_text:
        return {}
    base_text = _git(root, "show", "%s:%s" % (base, REGISTER_REL))
    was = {r["id"]: superseded_target(r["status"]) for r in parse_rows(base_text)}
    now = {r["id"]: superseded_target(r["status"]) for r in parse_rows(head_text)}
    return {rid: t for rid, t in now.items() if t is not None and was.get(rid) != t}


def commit_cited_ids(root, base):
    """Every id named by a commit message in `base..HEAD`."""
    log = _git(root, "log", "%s..HEAD" % base, "--format=%B%x1e")
    return set(ID_RE.findall(log))


def resolve_base(root):
    """The MERGE BASE against the PR base, or '' when none resolves.

    The same ladder `check_plan_citations.resolve_base` walks, and for the same reason: `GITHUB_BASE_REF` is a bare branch name in CI, the fork point is what R5 must compare against rather than the base tip, and a checkout with no remote still has to answer. `DECISION_IDS_BASE` is the test seam and is taken LITERALLY, so a control can pin an exact commit.
    """
    pinned = os.environ.get("DECISION_IDS_BASE") or ""
    if pinned:
        return (
            pinned
            if _git(root, "rev-parse", "--verify", "--quiet", "%s^{commit}" % pinned).strip()
            else ""
        )
    br = os.environ.get("GITHUB_BASE_REF") or ""
    cand = "origin/%s" % br if br else "origin/main"
    for ref in (cand, cand.replace("origin/", ""), "origin/main", "main"):
        if not ref:
            continue
        got = _git(root, "merge-base", "HEAD", ref).strip()
        if got:
            return got
    return ""


def run(root):
    reg = register_path(root)
    if not reg.is_file():
        print(
            "VACUOUS INPUT: no decision register at %s. Every rule here is a statement "
            "about its rows, so without it this gate has nothing to judge and its green "
            "would mean nothing." % reg,
            file=sys.stderr,
        )
        return 1

    rows = parse_rows(reg.read_text(encoding="utf-8", errors="replace"))
    if not rows:
        print(
            "VACUOUS INPUT: %s parsed to ZERO rows. Either the register is empty or the "
            "table grammar has drifted; either way every rule below would pass by having "
            "no subject." % reg,
            file=sys.stderr,
        )
        return 1

    findings = judge_rows(root, rows, register_label())
    ids = {r["id"] for r in rows}

    files = corpus_files(root)
    if not files:
        print(
            "VACUOUS INPUT: the corpus glob over %s resolved ZERO tracked markdown files. "
            "R6 would report a clean tree it never read." % ", ".join(CORPUS_DIRS),
            file=sys.stderr,
        )
        return 1

    hits = cited_ids(root, files)
    if not hits:
        print(
            "VACUOUS INPUT: ZERO decision ids were found across %d tracked file(s). The "
            "extractor is blind, so R6's silence would mean nothing." % len(files),
            file=sys.stderr,
        )
        return 1

    for tok in sorted(hits):
        if tok not in ids:
            where = ", ".join(hits[tok][:4])
            findings.append(
                "%s is cited but is not a row in %s (%s). Add the row, or fix the "
                "citation; a decision id that resolves to nothing is the failure this "
                "register exists to end" % (tok, REGISTER_REL, where)
            )

    base = resolve_base(root)
    added = added_supersessions(root, base)
    if added is None:
        r5 = "R5 SKIPPED: no base ref resolved, so no commit range to read"
    else:
        cited = commit_cited_ids(root, base) if added else set()
        for rid, target in sorted(added.items()):
            if target not in cited:
                findings.append(
                    "%s was superseded by %s in this range, and no commit in %s..HEAD "
                    "names %s. A substitution must be stated out loud where a reader of "
                    "`git log` will find it: put %s in the commit message"
                    % (rid, target, base, target, target)
                )
        r5 = "R5: %d supersession(s) added since %s" % (len(added), base)

    n_superseded = sum(1 for r in rows if superseded_target(r["status"]) is not None)
    keys = sorted({re.sub(r"[0-9]+$", "", r["id"]) for r in rows})

    if findings:
        print("✗ %d decision-register finding(s):" % len(findings), file=sys.stderr)
        for f in findings:
            print("    %s" % f, file=sys.stderr)
        return 1

    print(
        "✓ decision ids: %d row(s) across %d source key(s) (%s), %d cited id(s) in "
        "%d tracked file(s), %d superseded. %s"
        % (
            len(rows),
            len(keys),
            ", ".join(keys),
            len(hits),
            len(files),
            n_superseded,
            r5,
        )
    )
    return 0


# --------------------------------------------------------------------------- CONTROL FIRST. Every mutant is built with the `plant` harness, never by raw substitution: a substitution that silently matches nothing hands the gate its CLEAN fixture and the control reports a pass for an assertion it never made (check:ci-python-control-plants).


CLEAN = """
| Id | Decision | Source | Status | Licence | Notes |
|---|---|---|---|---|---|
| D-A6 | the licence | package.json:1 | live | | |
| D-A7 | taken under it | package.json:1 | live | D-A6 | |
"""


def selftest():
    c = controls.Controls("decision-ids", floor=14)

    # -- the parser, both directions ---------------------------------------
    c.check("the clean fixture parses to two rows", len(parse_rows(CLEAN)), 2)
    c.check(
        "CONTROL: a table row that is not an id is NOT a row",
        len(parse_rows("| Note | a | b | c |\n")),
        0,
    )
    c.check(
        "CONTROL: the source-key table above the register is NOT a row",
        len(parse_rows("| `A` | docs/ci-overhaul/04-decisions.md section A |\n")),
        0,
    )
    c.check("a row keeps its licence cell", parse_rows(CLEAN)[1]["licence"], "D-A6")

    # -- the id grammar, both directions -----------------------------------
    c.truthy("D-A6 is an id", ID_EXACT_RE.match("D-A6"))
    c.falsy(
        "CONTROL: D-6 is NOT an id, which is what keeps the open-decision-point "
        "labels of docs/ci-overhaul/04-decisions.md out of this grammar",
        ID_EXACT_RE.match("D-6"),
    )
    c.falsy("CONTROL: G-A5 is NOT a decision id", ID_EXACT_RE.match("G-A5"))
    c.check("the extractor finds an id in prose", ID_RE.findall("see D-A6 there"), ["D-A6"])
    c.check("CONTROL: the extractor does NOT find D-1 in prose", ID_RE.findall("see D-1"), [])

    # -- R3, R4 and the row rules, each planted then withdrawn -------------
    root = str(ROOT)
    c.check("CONTROL: the clean fixture yields no finding", judge_rows(root, parse_rows(CLEAN)), [])

    dangling = controls.plant(
        CLEAN,
        "| D-A7 | taken under it | package.json:1 | live |",
        "| D-A7 | taken under it | package.json:1 | superseded-by D-ZZ9 |",
    )
    c.check(
        "R3: a superseded-by naming no row is a finding",
        len(judge_rows(root, parse_rows(dangling))),
        1,
    )
    self_sup = controls.plant(
        CLEAN,
        "| D-A7 | taken under it | package.json:1 | live |",
        "| D-A7 | taken under it | package.json:1 | superseded-by D-A7 |",
    )
    c.truthy(
        "R3: a row superseded by itself is a finding",
        any("superseded by itself" in f for f in judge_rows(root, parse_rows(self_sup))),
    )
    dead_src = controls.plant(
        CLEAN,
        "| D-A6 | the licence | package.json:1 |",
        "| D-A6 | the licence | package.json:999999 |",
    )
    c.truthy(
        "R2: a Source line that does not exist is a finding",
        any("Source" in f for f in judge_rows(root, parse_rows(dead_src))),
    )
    dead_lic = controls.plant(CLEAN, "| live | D-A6 |", "| live | D-QQ1 |")
    c.truthy(
        "R4: a licence that is not a row is a finding",
        any("licence D-QQ1" in f for f in judge_rows(root, parse_rows(dead_lic))),
    )
    stale_lic = controls.plant(
        CLEAN,
        "| D-A6 | the licence | package.json:1 | live |",
        "| D-A6 | the licence | package.json:1 | superseded-by D-A7 |",
    )
    c.truthy(
        "R4: leaning on a SUPERSEDED licence is a finding",
        any("cannot authorise" in f for f in judge_rows(root, parse_rows(stale_lic))),
    )
    dup = controls.plant(CLEAN, "| D-A7 | taken under it", "| D-A6 | taken under it")
    c.truthy(
        "R1: a repeated id is a finding",
        any("repeats" in f for f in judge_rows(root, parse_rows(dup))),
    )
    bad_status = controls.plant(
        CLEAN,
        "| D-A6 | the licence | package.json:1 | live |",
        "| D-A6 | the licence | package.json:1 | maybe |",
    )
    c.truthy(
        "R1: a status outside the vocabulary is a finding",
        any("must be `live`" in f for f in judge_rows(root, parse_rows(bad_status))),
    )

    # -- THE REAL REGISTER, read the way run() reads it. A helper that works on fixtures while the tracked file it is aimed at yields nothing is the vacuity this repo keeps paying for.
    real = pathlib.Path(ROOT) / REGISTER_REL
    n_real = len(parse_rows(real.read_text(encoding="utf-8"))) if real.is_file() else 0
    c.truthy(
        "the tracked register at %s parses to %d row(s), which must be non-zero"
        % (REGISTER_REL, n_real),
        n_real > 0,
    )

    return 0 if c.report() else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    rc = controls.controls_first("decision ids", selftest)
    if rc:
        return rc
    return run(ROOT)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
