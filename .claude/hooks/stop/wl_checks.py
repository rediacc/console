"""wl_checks: the static check battery and the Stop-path orchestration.

This is the v5-v9 main() stop path, extracted, consuming the v10 store fold instead of raw markdown lines, plus the v10 additions: the liveness ladder, the deferral autonomy window, and the judge verdict cache. Ordering is load-bearing throughout -- emit() exits the process, so anything after a block never runs -- and every WHY comment travels with its check.
"""

import contextlib
import datetime
import hashlib
import json
import os
import pathlib
import random
import re
import subprocess
import sys as _sys
import time
import types as _types
from typing import Any

import wl_admit
import wl_agents as A
import wl_backlog
import wl_bgsweep
import wl_checklist
import wl_ci
import wl_claimcheck
import wl_common
import wl_core as C
import wl_defersettle
import wl_deflect
import wl_git
import wl_hints
import wl_histfirst
import wl_judge
import wl_leasehelp
import wl_liveness
import wl_planenforce
import wl_planfid
import wl_planfile
import wl_planindex as PI
import wl_popup
import wl_reggate
import wl_report
import wl_roster
import wl_roundlog
import wl_rules
import wl_shapedup
import wl_standdown
import wl_store as S
import worklist_messages as M

# BEST-EFFORT, NOT A SIBLING: onboard.py lives one directory over, in .claude/hooks/context/, so a copy-the-stop-dir fixture (test_wl_cadence's hookcrash case) or any tree missing that directory leaves it unimportable.
# The read it feeds is purely observational (N_ONBOARD_DELIVERED changes no verdict), so losing it must never take the whole hook down the way a real sibling failing to import correctly does.
onboard: _types.ModuleType | None
try:
    _sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "context"))
    import onboard
except ImportError:  # absent here just means the notice line stays silent
    onboard = None

# Heading, any level, so "## Remaining" and "### Remaining work" both count.
REMAINING_HEADING = re.compile(r"^[ \t]{0,3}#{1,4}[ \t]*Remaining\b", re.MULTILINE | re.IGNORECASE)

# Consecutive stops that may move nothing before the hook demands a planning or investigation agent. Three is the operator's number, not a guess.
STUCK_ROUNDS = int(os.environ.get("WORKLIST_STUCK_ROUNDS", "3"))
# How recently the in-flight item must have been refreshed for the session to count as SUPERVISING a long background job rather than having forgotten it.
#
# 70, and for a deliberate reason: JUST OVER the hourly work loop. A session on an hourly cron refreshes its item once an hour, so any threshold under 60 leaves a window every hour where a perfectly healthy campaign reads as unsupervised. It was 45 for exactly one evening and fired twice that way -- at 46 and 48 minutes, both times on a batch that was
# running fine and reported again minutes later. A threshold tighter than the reporting cadence does not detect neglect, it just re-times the false alarm.
STUCK_SUPERVISED_MAX_MIN = int(os.environ.get("WORKLIST_STUCK_SUPERVISED_MAX_MIN", "70"))

# v12 CI-WAITING FORCE (operator, 2026-07-30: "is current session sitting for CI pipeline? If so, it should FORCE current session to work on waiting items!!! There is no valid reason to wait."). When every running background task is a CI watch, deferrals that have sat at least CI_FORCE_MIN_AGE are demanded, CI_FORCE_PER_STOP at a time. The age floor is itself an exit: a deferral
# re-justified with a fresh WHY/HOW leaves the demand window, so an honest answer -- not only doing the work -- always reaches an allowed stop.
CI_FORCE_MIN_AGE = int(os.environ.get("WORKLIST_CI_FORCE_MIN_AGE", "15"))
CI_FORCE_PER_STOP = int(os.environ.get("WORKLIST_CI_FORCE_PER_STOP", "3"))

DESIGN_DOCS = os.environ.get("WORKLIST_DESIGN_DOCS", "docs/ci-overhaul")
DOCS_DRIFT_MAX = int(os.environ.get("WORKLIST_DOCS_DRIFT_MAX", "10"))
# What counts as "the program surface": changing these is changing the thing the design docs describe.
PROGRAM_SURFACE = os.environ.get("WORKLIST_PROGRAM_SURFACE", ".ci .github .claude").split()


def broken_schedules(event, now=None):
    """The scheduled tasks whose schedule this hook cannot parse, as "<schedule> -- <label>" rows. Empty when every schedule is readable.

    THIS IS WHAT SURVIVES the v18 deletion of the NEXT WAKEUPS section (operator, 2026-08-04: "we don't need to print next wakeup times. We should just track the hook moments and notify/warn when needed. let's go
    for efficient ai context usage"). The section printed every task's next
    firing on every single stop, which is context spent on a fact nobody acts on -- the schedules are in the harness, and a session that wants them can read them there.

    One line of it WAS actionable and does not survive deletion on its own: a schedule the hook cannot parse. That task will never be reasoned about by the cron-shape checks or the loop-death detector, and a list that silently omitted it would read as "nothing else is scheduled" -- the pass-quietly failure this hook bans. So the timing display is gone and the
    warning stays, which is exactly the trade the instruction asks
    for: silent when there is nothing to act on, one focused message when
    there is."""
    rows = []
    for c in event.get("session_crons") or []:
        sched = str(c.get("schedule", ""))
        if C.cron_next(sched, now) is not None:
            continue
        stripped_prompt = str(c.get("prompt", "")).strip()
        label = stripped_prompt.splitlines()[0][:90] if stripped_prompt else "(no prompt)"
        rows.append("    %r -- %s" % (sched, label))
    return rows


# ---- stuck detection --------------------------------------------------------


def stuck_rounds(worklist, session_id, tasks, head, exempt, supervised=False, own_stamp=""):
    """(count, fired, why) -- how many consecutive stops have moved NOTHING?

    THE OPERATOR'S RULE, IN THEIR WORDS: "I'd go with employing a planning/investigation agent if we cannot solve in last 3 round." Three identical stops means the APPROACH is wrong, not that it deserves a fourth attempt. The remedy is prescribed rather than left open, because "try harder" is what a stuck session already believes it is doing.

    The signature is deliberately COARSE: the harness task list plus HEAD. A commit moves it, ticking a task moves it, changing a task's status moves it. Talking does not. That is the point, since every one of the failures this catches involved a session that was producing text and no artifacts.

    It fires and then RESETS, so it nags at 3, 6, 9 rather than every stop once stuck. A session needs room to actually run the agent it was told to run, and a check that fires forever is one the session learns to route around.

    TWO TIERS, because a single signature can be bought off. The first version of this shipped with a DEAD head leg (it resolved the repo from the worklist's own tmp directory, so git returned nothing and the docstring's "a commit moves it" was false for every real stop). Fixing that naively would have been worse than the bug: any commit, including a one-line doc tweak, would reset
    the counter, so the commit-trivia treadmill and the eleven-push storm would both escape. So:

      * TASKS-ONLY signature, threshold 2x. Commits cannot touch it. This is
        what catches a session committing noise while the real problem sits.
      * TASKS+HEAD signature, threshold 1x. Real progress resets this sooner.

    Commits buy slack, never immunity.

    `exempt` (a live background task) suppresses the ordinary fire, because the remedy is already running. It does NOT stop the counting: a watch left running forever would otherwise silence this permanently, so at 3x the threshold it fires anyway to say the remedy itself has stalled.

    `supervised` is the ONE case where that 3x overrun is wrong. The overrun exists to catch a FORGOTTEN watch -- the deadlocked-poller failure, where a background task is alive but nobody is reading it. It cannot, on its own, tell that apart from a long job the session is actively supervising: a multi-hour render or migration legitimately changes no task status for hours, and
    firing at it every stop teaches the session to argue with this check rather than act on it, which is how a check stops being believed.

    So the caller passes supervised=True only when BOTH hold: a background task
    is live AND the session's in-flight worklist item was refreshed recently. That second half is what a forgotten watch can never satisfy, because refreshing the item is exactly the thing nobody is doing. Counting still continues, and the moment the session stops reporting, the item goes quiet and this fires as designed.
    """
    # tasks are (id, subject, status); the STATUS is what has to move. v14 gap 2: `own_stamp` (the newest upd stamp across this session's own worklist items) rides both signatures. The v13 night proved the harness task list alone is too narrow an evidence base: a session shipping commits and ticking worklist items hourly read as "stuck 92 stops" because its long-horizon harness
    # tasks legitimately never flipped. Worklist activity is real movement; a genuinely stuck session produces none, so the catch is intact.
    base = "|".join(sorted("%s:%s" % (i, st) for i, _, st in tasks)) + "@" + (own_stamp or "")

    def dig(s):
        return hashlib.sha1(s.encode("utf-8", "replace")).hexdigest()[:12]

    sigs = (dig(base), dig(base + "#" + (head or "")))
    p = worklist.with_suffix(".stuck-%s" % (session_id or "unknown")[:8])
    try:
        parts = p.read_text().strip().split()
        prev, counts = (parts[0], parts[1]), [int(parts[2]), int(parts[3])]
    except (OSError, ValueError, IndexError):
        prev, counts = ("", ""), [0, 0]
    counts = [c + 1 if sigs[i] == prev[i] else 1 for i, c in enumerate(counts)]

    # thresholds: tasks-only is slower to fire, tasks+HEAD is the normal one
    limits = (STUCK_ROUNDS * 2, STUCK_ROUNDS)
    hit = [i for i in (0, 1) if counts[i] >= limits[i]]
    why = ""
    if hit and exempt:
        # A running agent excuses the ordinary fire, but not forever.
        hit = [i for i in hit if counts[i] >= limits[i] * 3]
        # ...unless the session is demonstrably watching it. See the docstring: the overrun targets a forgotten watch, not a supervised long job.
        if supervised:
            hit = []
        why = "exempt-overrun" if hit else ""
    elif hit:
        why = "tasks-only" if 0 in hit else "tasks+head"
    fired = bool(hit)
    with contextlib.suppress(OSError):
        p.write_text(
            "%s %s %d %d" % (sigs[0], sigs[1], *[0 if i in hit else counts[i] for i in (0, 1)])
        )
    return max(counts), fired, why


# ---- citations and completion evidence --------------------------------------

CITE_RE = re.compile(
    # LEADING DOT ALLOWED. `\b[\w]` cannot start on a dot, so `.ci/x.sh:9` matched but CAPTURED `ci/x.sh`, which resolves to nothing on disk. That silently excluded `.ci/`, `.github/` and `.claude/`, which is most of this program's surface: a citation check that looked strict was unsatisfiable
    # for exactly the paths it most needed to accept. Caught by the check firing
    # on a tick of mine that cited .ci/scripts/autopilot/autopilot-gate.sh. `astro` and `css` added 2026-08-19. They were missing, and the omission was not cosmetic: 107 tracked .astro files and 19 .css files could not be cited AT ALL, and .astro is the primary component format in packages/www. So a session doing www work could not cite the files it had just changed, which pushes
    # it toward citing something unrelated or not ticking. Found by a tick of mine being refused while citing main.css and BaseLayout.astro. `mdx`, `svg`, `cast`, `txt` added 2026-08-19, the SAME class of gap as the astro/css one directly above and found the same way: a tick of mine citing tutorial-create-repo.mdx:15 was refused as evidence-free. 260 tracked .mdx files (every
    # tutorial doc), 86 .svg, 18 .cast and 14 .txt could not be cited AT ALL. Binary formats (png, pdf) stay OUT on purpose: a line number in a binary cites nothing. EXTENSIONLESS ROOT DOTFILES, added 2026-09-06. Same class as the three gaps above and found the same way: a tick of mine citing .gitignore:9 was refused as evidence-free. The first branch requires a `.<ext>` suffix,
    # and a name like `.gitignore` or `.dead-bash-allowlist` has its only dot at the FRONT, so 22 of this repo's 24 tracked root dotfiles could not be cited AT ALL. That set is not incidental: it is every one of the 16 allowlists and blocklists the whole suppressions discipline is built on, plus .gitignore, .npmrc, .gitattributes and .gitmodules. A session draining an allowlist
    # entry, which is exactly the work that most needs a record, could not cite the file it had just edited. The branch carries no slash on purpose, so it
    # reaches root dotfiles and cannot swallow the `.ci` prefix of a real path;
    # the first branch is tried first and wins for anything with an extension. Over-matching is cheap here anyway: citation_state still has to RESOLVE the path on disk, so a stray `.foo:3` in prose fails there rather than passing. `jsonl` added 2026-09-23, the SAME class of gap as astro/css and mdx/svg/cast/txt above, found by a background report naming it directly rather than by
    # a live refusal: `agent/worklist/<prefix>.jsonl` and `agent/ledgers/*.jsonl` are this hook's own store and investigation ledger, cited constantly in evidence lines and tick messages, and every one of those citations was silently unresolvable to citation_state -- `json` matched the shorter prefix nowhere near far enough, since the alternation requires an EXACT trailing match up to `:`.
    r"(?<![\w./-])("
    r"\.?[\w][\w./-]*\.(?:py|ts|tsx|js|cjs|mjs|sh|json|jsonl|md|ya?ml|go|toml|astro|css|mdx|svg|cast|txt)"
    # NESTED DOTFILES, 2026-09-24: the optional directory prefix below. `private/account/.env:12` and `.ci/policy/.dead-bash-allowlist:19` could not be cited at all, because the lookbehind refuses a dot right after `/` and the branch had no way to consume the directories in front of it. Found while building wl_defersettle, whose settle evidence cites an env key's line.
    r"|(?:\.?[\w][\w.-]*/)*\.[\w][\w-]*"
    r")"
    r":(\d+)(?:-\d+)?\b"
)


def _resolve_cite_path(root, rel, p):
    """One hop through a plan-move stub, shared by `citation_state` and `cited_excerpts`.

    A closed plan moves into `agent/plans/**` and leaves a five-line pointer at its old path, which is what keeps citations of that path resolving. A `<path>:<line>` citation is the case the pointer alone does NOT serve: the file exists and every line number past five is suddenly out of range, so an evidence line written months ago starts reading as a fabrication. Two
    callers used to take this hop separately, and one of them drifted: `cited_excerpts` read `p` raw and handed the judge an empty quote for exactly the citations that survived a plan move. One definition now, so the two cannot diverge again. Exactly one hop: `check:ci-plan-folders` F5 refuses a stub that points at a stub.

    CALLED EVEN WHEN `p` DOES NOT EXIST, since the 2026-09-22 cleanup: `S.plan_stub_target` falls back to a slug-derived folder search when there is no file left to read at `p` at all, which is the shape every one of the 103 deleted flat-layout stubs now leaves behind. Both callers used to check `p.is_file()` before taking the hop, which is exactly backwards once the
    stub itself can be the missing part.
    """
    moved_to = S.plan_stub_target(p)
    if moved_to:
        target = pathlib.Path(root) / moved_to
        if target.is_file():
            return moved_to, target
    return rel, p


def citation_state(root, text):
    """(ok, detail) -- does this line cite a source that REALLY says so?

    The Wave C failure was a blocker nobody had verified: "blocked on Wave B landing", when 05-execution-guide.md:108 says the opposite in plain words. Nothing in the hook challenged it, because the shape of the report was valid and only its content was wrong.

    Requiring a <path>:<line> is not bureaucracy, it is a FORCING FUNCTION: producing the citation means opening the file, and opening that file is the exact moment the claim collapses. So the check is deliberately cheap and deliberately not clever. It proves the file exists and the line is real, nothing more. Whether the cited text actually SUPPORTS the claim is the judge's
    question, and the citation is what lets the judge read it.
    """
    m = CITE_RE.search(text or "")
    if not m:
        return False, "carries no <path>:<line> citation"
    rel, line = m.group(1), int(m.group(2))
    p = pathlib.Path(root) / rel
    rel, p = _resolve_cite_path(root, rel, p)
    if not p.is_file():
        return False, "cites %s, which does not exist" % rel
    try:
        n = len(p.read_text(errors="replace").splitlines())
    except OSError:
        return False, "cites %s, which cannot be read" % rel
    if line > n:
        return False, "cites %s:%d but that file has only %d lines" % (rel, line, n)
    return True, "%s:%d" % (rel, line)


def cited_excerpts(root, message, limit=3, span=4):
    """Quote what the session cited, so the judge can check it rather than guess.

    The citation check (citation_state) only proves a source EXISTS. That is the cheap half, and on its own it is gameable: any real file and any in-range line satisfies it, including one that says the opposite of the claim. This supplies the text so the expensive half can happen in the judge, which is already being paid for on quiet stops.

    Bounded on purpose. At most `limit` citations, +/- `span` lines each, so the prompt grows by a few hundred tokens rather than with the size of the program. Whole-document injection was considered and rejected: docs/ alone is thousands of lines and the cost would scale with the repo.
    """
    out, seen = [], set()
    for m in CITE_RE.finditer(message or ""):
        rel, line = m.group(1), int(m.group(2))
        if (rel, line) in seen:
            continue
        seen.add((rel, line))
        p = pathlib.Path(root) / rel
        rel, p = _resolve_cite_path(root, rel, p)
        if not p.is_file():
            continue
        try:
            lines = p.read_text(errors="replace").splitlines()
        except OSError:
            continue
        if line > len(lines):
            continue
        lo, hi = max(0, line - 1 - span), min(len(lines), line + span)
        body = "\n".join(
            "    %s%d| %s" % (">" if n == line else " ", n, lines[n - 1])
            for n in range(lo + 1, hi + 1)
        )
        out.append("  %s:%d\n%s" % (rel, line, body))
        if len(out) >= limit:
            break
    return "\n".join(out)


RUN_ID_RE = re.compile(r"\b\d{9,}\b")
# `rc=0` and `rc 0` are exit codes too (agent/plans/PLAN-stop-hook-retro-20260924.md R.8): four ticks on 2026-09-24 were refused for spelling one that way.
EXIT_RE = re.compile(r"\bexit(?:\s+code)?\s*[:=]?\s*\d+\b|\brc\s*[:= ]\s*\d+\b", re.IGNORECASE)
# A bare `name.ext:N`, which resolves when exactly ONE tracked file carries that basename (R.8). Eight refusals on 2026-09-24 cited a real file this way.
BARE_CITE_RE = re.compile(r"(?<![\w./-])([\w-][\w.-]*\.[A-Za-z0-9]+):(\d+)\b")
# `ASKED:<ISO minute>`: an operator /ask answer, which passes only when the lead transcript holds an AskUserQuestion result within ASKED_WINDOW_S of that minute (R.8).
ASKED_RE = re.compile(r"\bASKED:(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?::\d{2})?Z")
ASKED_WINDOW_S = 300
# The transcript tail `ASKED:` is checked against; a 200 MB lead transcript is never read whole.
ASKED_TAIL_BYTES = 64 * 1024 * 1024
URL_RE = re.compile(r"https?://\S+")
SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")


def _bare_cite_resolves(root, text):
    """True when some bare `name.ext:N` in `text` names exactly one tracked file (`git ls-files`) whose length reaches line N. An ambiguous basename resolves nothing: picking one of several would verify a file the tick may not mean."""
    bare = [(m.group(1), int(m.group(2))) for m in BARE_CITE_RE.finditer(text or "")]
    if not bare:
        return False
    listed = C._git(root, "ls-files") or ""
    by_name: dict[str, list[str]] = {}
    for rel in listed.splitlines():
        by_name.setdefault(rel.rsplit("/", 1)[-1], []).append(rel)
    for name, line in bare:
        hits = by_name.get(name) or []
        if len(hits) != 1:
            continue
        try:
            n = len((pathlib.Path(root) / hits[0]).read_text(errors="replace").splitlines())
        except OSError:
            continue
        if 1 <= line <= n:
            return True
    return False


def ask_answer_times(transcript):
    """Epoch seconds of every AskUserQuestion tool_result in the lead transcript's tail, oldest first. [] when there is no transcript or it cannot be read."""
    if not transcript:
        return []
    try:
        with open(transcript, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - ASKED_TAIL_BYTES))
            lines = fh.read().splitlines()
    except (OSError, TypeError):
        return []
    asks, times = set(), []
    for rec in wl_common.records(lines, need=b'"tool_'):
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "AskUserQuestion":
                asks.add(str(block.get("id") or ""))
            elif block.get("type") == "tool_result" and str(block.get("tool_use_id") or "") in asks:
                try:
                    times.append(
                        datetime.datetime.fromisoformat(str(rec.get("timestamp") or "")).timestamp()
                    )
                except ValueError:
                    continue
    return times


def _asked_in_transcript(text, transcript):
    """True when an `ASKED:<minute>` in `text` matches an AskUserQuestion tool_result in the lead transcript within ASKED_WINDOW_S. The transcript is the harness's record of the question being answered, which the session cannot write by describing it."""
    stamps = []
    for m in ASKED_RE.finditer(text or ""):
        with contextlib.suppress(ValueError):
            stamps.append(
                datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M")
                .replace(tzinfo=datetime.UTC)
                .timestamp()
            )
    if not stamps or not transcript:
        return False
    return any(
        abs(at - st) <= ASKED_WINDOW_S for at in ask_answer_times(transcript) for st in stamps
    )


# How far back the tick refusal looks for an operator answer to offer as ready-to-paste `ASKED:` evidence (R20260924.21).
ASK_HINT_WINDOW_S = 2 * 3600


def tick_refusal_hint(transcript, now=None):
    """The line CLI_TICK_NO_EVIDENCE ends with: the newest AskUserQuestion answer of the last ASK_HINT_WINDOW_S as a ready-to-paste `ASKED:<minute>Z`, or "" (R20260924.21). Rows 1 to 3 of the 2026-09-24 tick refusals quoted "16:0xZ" because nothing named the shape or the minute."""
    now = time.time() if now is None else now
    recent = [t for t in ask_answer_times(transcript) if 0 <= now - t <= ASK_HINT_WINDOW_S]
    if not recent:
        return ""
    minute = datetime.datetime.fromtimestamp(max(recent), tz=datetime.UTC).strftime(
        "%Y-%m-%dT%H:%MZ"
    )
    return M.CLI_TICK_ASKED_HINT % minute


def completion_evidence(root, text, transcript=None):
    """Does `text` carry something evidence-shaped for a completion claim?

    Since agent/plans/PLAN-stop-hook-retro-20260924.md R.8 it also accepts `rc=N`, a bare `name.ext:N` that names exactly one tracked file, and `ASKED:<ISO minute>` checked against `transcript` (the lead's own), which only a caller that knows the transcript can verify.

    Shapes, cheapest first: a run-id-sized number, an exit code, a URL, a file:line that RESOLVES (citation_state, so a fabricated path or line fails), or a hex string naming a REAL git object (verified, so a decorative 'deadbee' cannot pass; at most five git subprocess calls total across every candidate and every submodule root, to bound the cost). Deliberately shape-based: whether the evidence SUPPORTS the claim is the reggate
    judge's question, since every new tick already flows into it. This check only guarantees a completion leaves a RECORD, which is exactly what S-2 lacked.

    THE FIVE ARE THE LONGEST CANDIDATES, NOT THE FIRST FIVE, and that is not a tidy-up: taking them in text order blocked five consecutive stops on 2026-08-23, because the mandatory session tag plus three cited worklist ids ate the budget before the real SHA at position 6. Do not "simplify" the ordering back out -- pinned by case 96b in test-worklist-v5.sh."""
    if RUN_ID_RE.search(text) or EXIT_RE.search(text) or URL_RE.search(text):
        return True
    # EVERY citation, not just the first. citation_state uses CITE_RE.search and stops at the first match, which is right for its own job (a forcing
    # function on ONE claim) and wrong here: this asks "did the completion leave
    # a RECORD at all", and a tick carrying five resolving citations plus one typo'd path was reported as evidence-free because the typo happened to come first. Found live 2026-08-14 on a tick whose line cited a bare "05-docs-and-decommission.md" ahead of four full, resolving paths.
    for m in CITE_RE.finditer(text or ""):
        if citation_state(root, m.group(0))[0]:
            return True
    if _bare_cite_resolves(root, text) or _asked_in_transcript(text, transcript):
        return True
    # LONGEST candidates first, then the cap. The cap bounds git calls (above), but taking the first five in TEXT order spent the entire budget on short hex tokens that can never be object ids. Every rendered line opens with the mandatory session tag TWICE (`- [x] (0ad063bf) (0ad063bf) ...`), and cited worklist item ids are 8 hex as well, so an item that cross-references its
    # siblings poisons its own evidence check -- the more carefully it is written, the more certainly it fails. Found live 2026-08-23 on a tick whose only real SHA sat at position 6, behind ['0ad063bf', '0ad063bf', '23d99308', 'ebe8b570', 'e263d2cc']; it blocked five consecutive stops while carrying a tree hash that resolves. This is the same shape as the CITE_RE fix above, which
    # this arm never received. Ordering by length is the cheap discriminator: a 40-hex object id outranks an 8-hex id, and ties keep first-seen order so the choice stays deterministic.
    seen, cands = set(), []
    for i, m in enumerate(SHA_RE.finditer(text)):
        tok = m.group(0)
        if tok not in seen:
            seen.add(tok)
            cands.append((-len(tok), i, tok))
    # SUBMODULE SHAS ARE REAL OBJECTS TOO, just not in `root`'s own database. A commit in private/renet or private/account never resolves via `git -C root rev-parse`, since each submodule keeps its own separate object store -- found live 2026-09-23 ticking real, verified work whose only cited sha lived in private/renet. Checked only after `root` itself misses, in the SAME PRIORITY ORDER `roots` lists them, so a real console sha never falls through to a slower path for no reason.
    #
    # THE BUDGET IS SHARED ACROSS CANDIDATES AND ROOTS, not five calls PER candidate: a repo with several submodules multiplies "at most five candidates" into five times (1 + submodule count) calls the moment none of them resolve, which is exactly the unbounded shape this whole cap exists to prevent (case 96b, planted with 4 real submodules and a fabricated 40-hex sha, measured 25
    # calls before this counter existed). One counter spent depth-first -- root then each submodule for the CURRENT candidate before moving to the next -- keeps a single real submodule sha found on the first candidate cheap (root miss, submodule hit, done in 2 calls) while still hard-capping the worst case at five subprocess calls regardless of how many candidates or submodules exist.
    #
    # ONE `cat-file --batch-check` PER ROOT since R20260924.20, so the cost is the number of roots, never candidates times roots, and every candidate is asked at once. The roots now include the independent repos under private/ (`evidence_roots`): real shas of private/generative and private/growth were refused at 18:37:08Z and 18:37:16Z on 2026-09-24.
    toks = [tok for _, _, tok in sorted(cands)[:EVIDENCE_CANDIDATES]]
    if not toks:
        return False
    return any(_objects_in(r, toks) for r in evidence_roots(root))


# How many hex candidates one batch asks about. A batch costs one subprocess whatever its size; the cap only bounds a pathological line.
EVIDENCE_CANDIDATES = 16
# How deep under private/ an independent repo is looked for (R20260924.20, the Decision "Sibling repos for tick evidence"): private/growth/corporate/legal-tax/maasikas.emta.ee sits at depth 4.
SIBLING_DEPTH = 4
# Directories the walk never descends into: object stores and dependency trees, never a repo of our own.
_WALK_SKIP = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"})
_EVIDENCE_ROOTS: dict[str, list[str]] = {}


def sibling_repo_roots(root):
    """Every git repo under `<root>/private/` down to SIBLING_DEPTH that is not a submodule, found by one walk and cached per root for the process. They are gitignored and independent, so neither `git -C root` nor `wl_git.submodules` ever sees their objects."""
    base = os.path.join(str(root), "private")
    known = {os.path.normpath(os.path.join(str(root), p)) for p, _b in wl_git.submodules(root)}
    found = []
    for cur, dirs, _files in os.walk(base):
        depth = 0 if cur == base else os.path.relpath(cur, base).count(os.sep) + 1
        if (
            depth
            and os.path.exists(os.path.join(cur, ".git"))
            and os.path.normpath(cur) not in known
        ):
            found.append(cur)
        if depth >= SIBLING_DEPTH or os.path.normpath(cur) in known:
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if d not in _WALK_SKIP)
    return found


def evidence_roots(root):
    """The repos a tick's sha may live in, in the order they are asked: `root`, its submodules, then the independent repos under private/ (`sibling_repo_roots`). Cached per root for the process."""
    key = os.path.abspath(str(root))
    if key not in _EVIDENCE_ROOTS:
        subs = [os.path.join(str(root), p) for p, _branch in wl_git.submodules(root)]
        _EVIDENCE_ROOTS[key] = [str(root), *subs, *sibling_repo_roots(root)]
    return _EVIDENCE_ROOTS[key]


def _objects_in(repo, toks):
    """True when `repo`'s object store holds any of `toks`: ONE `git cat-file --batch-check` for all of them. An ambiguous short sha or a missing one answers no; any failure answers no."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "--batch-check"],
            input="".join(t + "\n" for t in toks),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    return any(
        len(parts) >= 2 and parts[1] in ("commit", "tree", "blob", "tag")
        for parts in (ln.split() for ln in proc.stdout.splitlines())
    )


# v16: an issue reference is a URL, and completion_evidence passes on ANY URL by shape, so `--tick <me> <id> 'filed as .../issues/560'` closed a finding. That is the loophole the fix-in-session rule outlaws: filing settles nothing unless one of the three last-resort doors applies, and the tick has to say WHICH. Shape-only, the same division of labor as the WHY/HOW gate: whether the
# named door is TRUE is the judge's question, and every new tick already flows into the reggate/judge path.
ISSUE_REF_RE = re.compile(r"\S*github\.com/\S+/issues/\d+\S*|\bissues?\s+#\d+", re.IGNORECASE)
DOOR_RE = re.compile(r"door:(operator-only|operator-deferred|no-write-access)")


def issue_only_evidence(root, text):
    """True iff the evidence is ONLY an issue reference.

    Three conditions, all required: an issue reference is present, no door is named, and the text with issue references stripped carries no other evidence shape. So a tick that ALSO cites the fix (a real sha, an exit code, a run URL, a resolving file:line) passes, and only "I filed it" is refused.
    """
    if not ISSUE_REF_RE.search(text):
        return False
    if DOOR_RE.search(text):
        return False
    return not completion_evidence(root, ISSUE_REF_RE.sub(" ", text))


# Does this deferral's own WHY depend on the CI wait, or on something the wait cannot remove? The CI-waiting force below tells a session to execute a DEFAULT "because the wait was the only reason to hold it", and for a justified deferral that sentence is BACKWARDS: a justified one is precisely the one whose reason is written down, and the reason is usually not the run.
#
# THE FAILURE, 2026-09-04: an item deferred with "the remaining act is irreversible and outward-facing, gh secret delete cannot be undone" was told, four stops running, to execute its DEFAULT because the wait was all that held it. The session had to decline each time and re-justify, which is a round trip spent arguing with a template.
#
# Textual, not a model call: this runs on every stop and the question is cheap. The test is deliberately asymmetric -- only a WHY that NAMES the wait gets the "execute it now" instruction, so an unparseable or unusual reason falls to the safe side and asks the session rather than ordering it.
_WAIT_WHY = re.compile(
    r"\b(wait(ing)?|in flight|CI run|the run|pipeline|until (CI|the run)|green)\b",
    re.IGNORECASE,
)
# CHECKED FIRST, because a bare keyword match reads a DENIAL as an admission. The real deferral that exposed this opens "what blocks it is not the wait, it is that the remaining act is irreversible" -- and the positive pattern above happily finds `wait` in it. A session that writes down why the run is NOT its blocker must not be told the run was its only blocker.
_NOT_WAIT_WHY = re.compile(
    r"\bnot\s+(?:the\s+)?(?:wait(?:ing)?|blocked\s+on|waiting\s+on)\b"
    r"|\bis\s+NOT\s+waiting\b"
    r"|\bdoes\s+not\s+depend\s+on\s+(?:the\s+)?(?:run|wait|CI)\b"
    r"|\bnot\s+blocked\s+on\s+(?:any\s+)?run\b",
    re.IGNORECASE,
)


def deferral_waits_on_ci(rec):
    """True only when the deferral's WHY itself points at the run in progress."""
    why = (S.deferral_justification(rec) or {}).get("why") or ""
    if _NOT_WAIT_WHY.search(why):
        return False
    return bool(_WAIT_WHY.search(why))


def deferral_is_justified(rec):
    """Does this [?] carry a usable WHY and HOW (event field or inline tokens)? The shape test only; whether the justification is TRUE is the judge audit's question."""
    j = S.deferral_justification(rec)
    return bool(j.get("why") and j.get("how"))


# ---- v21: THE IDLE-STALL GATE ---------------------------------------------- WHY (operator, 2026-08-26): "it's very annoying that neither you have background agent nor running monitor/shell but you do stop even with remaining items! I see they're not blocked because of dependencies/questioning to me. You misuse the intention of the stop hook."
#
# The loophole was NOT that open items pass unnoticed -- `open-items` has always been a violation. It is that `open-items` sits in the ROTATING tier, so the cadence gate (see CADENCE_MAX_PAUSES and the `pause` computation in run_stop) ALLOWS the stop as long as the assistant said something new since the last demand. Case 214 pins exactly that: block -> new message -> allow. And the
# cap on consecutive pauses resets whenever the outstanding key set SHRINKS, so clearing any one rotating check -- a STATE.md rewrite, a refreshed brief, a plan touch-up -- refills the pause budget. Together those make an endless supply of hook-satisfying non-work: do one thing, stop, be pushed back, do one thing, stop.
#
# This gate is in the ALWAYS tier, which is the one thing the cadence cannot pause (guard A). It fires ONLY on the shape the operator described -- open work, nobody else carrying it, and nothing left the open state this turn -- and every one of its three exits (tick, lease, defer) is completable by the session alone in the same turn, so it converts into action rather than a
# deadlock.

#: A '## Remaining' line ASSERTING that an item has no blocker. That claim is
#: self-refuting: an item nobody is blocking is the next thing to do, not a
#: remainder. Deliberately narrow -- a bare "nothing" (as in "## Remaining\n-
#: nothing", which means the list is EMPTY) must not match, only an explicit
#: not-blocked assertion.
UNBLOCKED_CLAIM_RE = re.compile(
    r"blocked[ \t]*(?:on|by)?[ \t]*[:\-\u2014]?[ \t]*(?:nothing|none|no[ \t-]?one|nobody|n/?a)\b"
    r"|\bnot[ \t]+blocked\b"
    r"|\bno[ \t]+blocker[s]?\b"
    r"|\bunblocked\b"
    r"|\bready[ \t]+to[ \t]+(?:start|go|begin)\b",
    re.IGNORECASE,
)


def _strip_quoted_spans(text):
    """Blank out backticked and quoted spans.

    Shared by every detector whose trigger phrases appear in prose ABOUT the rule -- this file, CLAUDE.md and the hook's own messages all quote them. A gate that cannot survive being written about is too broad, and the fix is not a narrower pattern but ignoring the spans where quoting happens.

    THE IMPLEMENTATION MOVED TO wl_core (2026-08-27) when wl_admit's pending-ask gate needed the same treatment. This stays as the name six call sites here already use; what it must never become again is a SECOND copy of the regex, because the two would drift and only one of them would be the one anybody tested.
    """
    return C.strip_quoted_spans(text)


def unblocked_claims(last_msg, limit=6):
    """The '## Remaining' lines that claim an item is unblocked, at most `limit`.

    Backticked and quoted spans are stripped first, following the V_FOUND_NOT_FIXED / loop_finished_declared precedent that a gate which cannot survive being WRITTEN ABOUT is too broad -- and it matters here because any message discussing this check quotes its own trigger phrases.
    """
    if not last_msg:
        return []
    m = REMAINING_HEADING.search(last_msg)
    if not m:
        return []
    out = []
    for ln in last_msg[m.start() :].splitlines()[1:]:
        stripped = _strip_quoted_spans(ln)
        if UNBLOCKED_CLAIM_RE.search(stripped):
            out.append(ln.strip()[:140])
        if len(out) >= limit:
            break
    return out


# The "found, not fixed" FAMILY, not just that one phrase.
#
# The original detector matched `found,? not fixed` at line-lead and nothing
# else, so every near-synonym walked past it. Measured against one real session
# (2026-08-26): "Reported, not fixed (not my file)", "Agent finding I didn't fix", and "Findings in code I do not own -- not fixed, reported" ALL escaped, and the findings sat unfixed until the operator asked for them by hand. The rule they violate is the same one in every case; only the wording differed.
#
# Deliberately anchored at line-lead and stripped of quoted/backticked spans, on the V_FOUND_NOT_FIXED precedent: a gate that cannot survive being written about is too broad, and this file and CLAUDE.md both discuss the rule.
DEFERRED_FINDING_RE = re.compile(
    r"^[ \t>*_#-]{0,6}(?:"
    r"(?:found|reported|flagged|noticed|spotted)\s*[,:-]?\s*(?:but\s+)?not\s+fixed"
    r"|(?:findings?|defects?|issues?)\b[^\n]{0,60}?\bnot\s+fixed"
    # This one alternative is allowed to sit mid-line, because the phrasing that escaped in practice was "- Agent finding I didn't fix: ..." -- the admission trails the subject rather than leading it. Still bounded to a LIST line, so ordinary prose in a paragraph does not reach it.
    r"|[^\n]{0,80}?\b(?:did\s+not|didn't|have\s+not|haven't)\s+fix(?:ed)?\b"
    r"|not\s+fixed\s*[,(]?\s*(?:reported|flagged|not\s+my)"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


def deferred_findings(last_msg, limit=6):
    """Lines that report a finding the session chose not to fix, at most `limit`."""
    text = _strip_quoted_spans(last_msg or "")
    out = []
    for line in text.split("\n"):
        if DEFERRED_FINDING_RE.search(line):
            trimmed = line.strip()[:160]
            if trimmed and trimmed not in out:
                out.append(trimmed)
        if len(out) >= limit:
            break
    return out


def closed_sig(fold, session_id):
    """A digest of MY items that are NOT open, as id:state pairs.

    It moves when an item LEAVES the open state -- ticked, leased, or parked on the operator -- and for no other reason. Deliberately blind to `--update` and to new [ ] items: progress notes and fresh findings are talk and intake, neither of which is an item getting off the list, and the whole failure this gate exists for was a session that produced text every turn.

    Returns "" when the store cannot be read, and the caller treats "" as "unknown" and stays quiet -- an unreadable store must never manufacture an accusation.
    """
    try:
        rows = sorted(
            "%s:%s" % (r["id"], r["state"])
            for r in fold.items
            if r["state"] != " " and C.owned_by_me(r.get("owner"), session_id)
        )
    except Exception:  # noqa: BLE001 -- a signature must never wedge a stop
        return ""
    return hashlib.sha1(("|".join(rows)).encode("utf-8", "replace")).hexdigest()[:16]


def idle_stall(state_doc, fold, session_id, open_items, live_bg, in_flight):
    """(fired, why) -- is this stop the operator's stall?

    Fires when ALL hold:
      * at least one open `[ ]` item is MINE (peers' items never block here),
      * no background worker is running, so nothing is carrying work for me,
      * no live `[>]` lease is outstanding (classify_items has already failed an
        expired or malformed lease back into `open_items`, so this is a fresh or
        OS-verified one),
      * a baseline from a previous stop exists, and nothing has left the open
        state since it was taken.

    FIRST SIGHT NEVER FIRES. With no baseline there is no evidence about the turn, and the ordinary `open-items` violation blocks that stop anyway, so the quiet direction costs nothing and keeps the gate from accusing on a fact it has not observed.

    Deliberately NOT conditioned on a live work cron, which is what separates this from the I6 idle check next door: I6 asks "will anything ever wake this session again", and a cron answers it. This asks "is there work in hand that only I can do", and a cron does not answer that at all -- it just schedules the same stall for later.
    """
    sig = closed_sig(fold, session_id)
    prev = (state_doc.get("idlestall") or {}).get("sig")
    if sig:
        state_doc.setdefault("idlestall", {})["sig"] = sig
    if not open_items:
        return False, ""
    if live_bg:
        return False, "a background worker is running"
    if in_flight:
        return False, "an item is leased to a live worker"
    if not sig or prev is None:
        return False, "no baseline yet"
    if sig != prev:
        return False, "an item left the open state this turn"
    return True, "idle"


# ---- cron memory and docs drift --------------------------------------------


def loop_finished_declared(last_msg):
    """True when the session explicitly declares its work loop is over.

    V_LOOP_DIED offers two ways out: recreate the cron, OR "say out loud in your message that the loop is deliberately finished". The second branch DID NOT EXIST -- cron_memory compared a high-water mark and never read the message. A session that finished its campaign, retired its cron on purpose and said so plainly was blocked again on the very next stop, with no wording that
    could ever satisfy the check. The block text promised an affordance the code did not implement, which is worse than not offering it: it sends the session hunting for the right phrase instead of telling it to recreate the cron.

    Backticked and quoted spans are stripped before matching, following the V_FOUND_NOT_FIXED precedent that a gate which cannot survive being written about is too broad. It matters more here than there: this is an OPT-OUT, so a message merely QUOTING the instruction (as any message discussing this check does) must not silently switch the check off.
    """
    if not last_msg:
        return False
    stripped = re.sub(r"`[^`]*`|\"[^\"]*\"|“[^”]*”", " ", last_msg)
    done = r"(?:finished|done|completed?|retired|ended|over)"
    how = r"(?:deliberately|intentionally|on purpose)"
    return bool(
        re.search(r"\bloop\b[^.\n]{0,60}?\b%s\s+%s\b" % (how, done), stripped, re.IGNORECASE)
        or re.search(r"\b%s\s+%s\b[^.\n]{0,60}?\bloop\b" % (how, done), stripped, re.IGNORECASE)
    )


def cron_memory(worklist, session_id, live_count, declared_done=False):
    """(died, remembered_max) -- was a loop running before that is gone now?

    WHY THIS REPLACED A DECLARATION. v5 first made the session declare its next cron fire and blocked when that timestamp went stale. That check fired on its author twice: once on genuinely bad date arithmetic, and once simply because the loop had fired and the declaration had not been renewed yet. The second is not a defect, it is the design demanding maintenance of a fact the
    harness already reports.

    `session_crons` in the Stop event is authoritative, so the only thing worth remembering is the HIGH-WATER count. A session that once had a cron and now has none has lost its loop, which is the failure the operator actually cares about ("sometimes you stop the hourly loop and never start it again"). A session that never had one is not doing anything wrong.

    v9: the caller passes the WORK-cron count. Every live cron is a work cron now, so this equals the live cron count.
    """
    p = worklist.with_suffix(".croncount-%s" % (session_id or "unknown")[:8])
    try:
        remembered = int(p.read_text().strip())
    except (OSError, ValueError):
        remembered = 0
    if live_count > remembered:
        with contextlib.suppress(OSError):
            p.write_text(str(live_count))
        remembered = live_count
    if declared_done and live_count == 0 and remembered >= 1:
        # FORGET the high-water mark, do not merely skip this one stop. Without the reset the declaration would clear the block once and the check would fire again on the next stop, and the next, forever -- which is exactly what happened to the session that found this. A loop declared finished is finished; if a new one starts, live_count climbs above 0 again and the mark rebuilds
        # itself on its own.
        with contextlib.suppress(OSError):
            p.write_text("0")
        return False, remembered
    return (remembered >= 1 and live_count == 0), remembered


def docs_drift(root):
    """(state, drift_commits, docs_dir) -- how far the code has moved past the docs.

    THE FAILURE THIS CATCHES, measured on the session that asked for it: 44 commits touching .ci/.github/.claude since the design docs were last updated. Those documents are how a NEW or freshly-compacted session understands what is being built and why, so code moving without them does not merely leave stale prose behind, it deletes the next session's starting context.

    'absent' when there is no such directory, so the check scopes itself to projects that actually keep design docs and says so rather than passing quietly.
    """
    docs = pathlib.Path(root) / DESIGN_DOCS
    if not docs.is_dir():
        return "absent", 0, str(docs)
    last_docs = C._git(root, "log", "-1", "--format=%H", "--", DESIGN_DOCS)
    base = last_docs or C._git(root, "merge-base", "HEAD", "origin/main")
    if not base:
        return "absent", 0, str(docs)
    n = C._git(root, "rev-list", "--count", "%s..HEAD" % base, "--", *PROGRAM_SURFACE)
    drift = int(n) if n.isdigit() else 0
    # UNCOMMITTED doc edits count. The baseline above is the last COMMIT touching the docs, and this repo's standing rule is that work stays uncommitted until the operator asks for it. Without this, a session that dutifully updated the design docs was told at EVERY stop that they had drifted, and the only way to satisfy the check was to commit -- which that same rule forbids doing
    # unilaterally. The check could not distinguish "nobody updated the docs" from "somebody did, and is not allowed to commit yet", so it demanded the one action it must not provoke.
    if drift > DOCS_DRIFT_MAX and C._git(root, "status", "--porcelain", "--", DESIGN_DOCS):
        return "pending", drift, str(docs)
    return ("drifted" if drift > DOCS_DRIFT_MAX else "ok"), drift, str(docs)


# ---- v16: the plan-file convention (agent/PLAN-<slug>.md) -----------------
#
# A plan is the DURABLE design record: committed, so it survives compaction and a lost machine. That is what distinguishes it from the per-session agent/<me>/ directories beside it, whose STATE.md is the volatile cursor. A plan sits one level UP, at the tree root, because it belongs to the work rather than to whoever happened to write it. Plans are historical once executed, so only
# draft/executing/UNKNOWN ones are surfaced; done and superseded appear as a count. An unparseable Status line reads as UNKNOWN and is shown LOUDLY, per the V_PR_UNREADABLE convention that a check which cannot read must say so rather than pass quietly.
#
# Cost: SessionStart and PostCompact only. The Stop battery never reads plan files; the guide's single os.path.exists probe per TRIAGED item is the only plan-related work on the stop path.
#
# HANDOFF CHECKLISTS ARE THE EXCEPTION, and deliberately so (v20, wl_checklist). agent/programs/<slug>/CHECKLIST.md IS the enforcement point, so the full Stop battery does read those files -- a gate that refuses to look at its own subject is not a gate. A repo that keeps no handoffs pays one glob and nothing else.

# Accepts the shape the plans in this repo ACTUALLY use, which the first version did not: `**Status: DESIGNED, not started. <prose>**`. Requiring a bare `Status: word` line meant five of twelve real plans parsed as UNKNOWN -- a FORMAT mismatch reported as a content problem, which would have sent someone rewriting perfectly good plans to satisfy a regex. Optional markdown emphasis,
# and the first word wins with any trailing prose ignored.
#
# SECOND ROUND OF THE SAME BUG, 2026-08-25. The anchored form still required `Status:` to START a line, and two more real plans state it mid-line: agent/plans/PLAN-test-advisor.md Owner: b7baf3ee · 2026-08-24 · status: BUILT agent/plans/PLAN-chunk-store-browse-server.md Branch: `0815-1`. Status: design only, ... Both parsed UNKNOWN, and UNKNOWN is loud by design, so the stop hook
# told a session to go fix two plans that were already accurate and were not even its own. Exactly the failure the paragraph above describes, in a new format.
#
# So: try the anchored form first (unchanged precedence, so a real leading `Status:` line always wins), then fall back to `Status:` anywhere in the header block. The fallback is case-insensitive because `status: BUILT` is what the deviating plans write.
PLAN_STATUS_RE = re.compile(r"^\*{0,2}Status\*{0,2}:\s*([A-Za-z-]+)", re.MULTILINE)
PLAN_STATUS_INLINE_RE = re.compile(r"\bStatus\*{0,2}:\s*([A-Za-z-]+)", re.IGNORECASE)
PLAN_HEADER_LINES = 10
# `Owner: <session-prefix>` in the same header block. plan_drift_rows is scoped to the plans THIS session owns, so it needs to read the field, not just the status.
PLAN_OWNER_RE = re.compile(r"^\*{0,2}Owner\*{0,2}:\s*[`'\"]?([0-9A-Za-z_-]{4,})", re.MULTILINE)
# `compacted` joins the two original words for the same reason they are here: a compacted record is HISTORY, so plans_block counts it rather than listing it as live work, and plan_status_excerpt never picks one as "the newest live plan". `parked` is deliberately NOT here -- its work is unfinished, so it stays visible.
PLAN_DONE_STATES = ("done", "superseded", "compacted")
PLAN_EXCERPT_CHARS = 1500
PLAN_DRIFT_MAX = int(os.environ.get("WORKLIST_PLAN_DRIFT_MAX", "5"))
# How many of MY items must have moved past a plan before it counts as behind.
PLAN_DRIFT_MIN_MOVES = int(os.environ.get("WORKLIST_PLAN_DRIFT_MIN", "4"))


def plan_dir(root):
    return S.agent_plan_dir(root)


# A session id, as a whole token: 8 hex from the CLI, 12 from the old markdown. An `Owner:` value that is not one of these cannot be a session, so it must not be compared against one -- see plan_owner.
PLAN_OWNER_ID_RE = re.compile(r"\b([0-9a-fA-F]{8}|[0-9a-fA-F]{12})\b")
# A plan that says it is unowned is UNOWNED, whoever drafted it.
PLAN_UNOWNED_RE = re.compile(r"\bunowned\b", re.IGNORECASE)


def plan_owner(root, rel):
    """The owning SESSION ID in a plan's header block, or None when it declares none.

    Read separately rather than widened into `plan_records`'s tuple, which has three other callers that would all have to change arity for one consumer's benefit.

    WHY THIS IS NOT JUST THE FIRST WORD AFTER `Owner:`. It was, and that made 13 of the 46 plans in this repo PERMANENTLY invisible to every consumer -- 28% of the corpus, measured 2026-09-02. `owned_by_me` compares the value against a session id prefix, so a value that is not a session id matches NO session, forever, and the plan reads as peer-owned to everyone. Nothing errors;
    the plans just quietly leave scope. Three real shapes, all silently exempt:

        Owner: unowned (drafted by 9d92d9b6, 2026-08-28)  -> "unowned"
        Owner: whichever session picks it up              -> "whichever"
        Owner: session 9d92d9b6, branch 0826-3            -> "session"

    The last is the sharpest: the real id is RIGHT THERE and was thrown away.

    So: an explicit `unowned` wins outright, otherwise take the first session-shaped token on the line, otherwise None. `unowned` is checked FIRST on purpose -- "unowned (drafted by 9d92d9b6)" names an id that is not an owner, and reading it as one would hand the plan to a session that disclaimed it.
    """
    try:
        text = (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    head = "\n".join(text.splitlines()[:PLAN_HEADER_LINES])
    m = PLAN_OWNER_RE.search(head)
    if not m:
        return None
    line = head[m.start() :].split("\n", 1)[0]
    if PLAN_UNOWNED_RE.search(line):
        return None
    hit = PLAN_OWNER_ID_RE.search(line)
    return hit.group(1) if hit else None


def plan_records(root):
    """[(relpath, status, lines)] for every plan under agent/, folders included.

    status is the parsed value lowercased, or 'UNKNOWN' when no Status line sits in the first PLAN_HEADER_LINES lines. Newest mtime first. Empty list when the directory is absent, so callers never have to know whether this project uses the convention.

    THE GLOB IS `wl_store.agent_plan_files` AND NOT A LITERAL HERE. A plan lives in one of four folders since the tree-lifecycle change, and a pointer left behind by a move is dropped there rather than filtered here, so this function, the census and the box ledger cannot disagree about what the corpus is.
    """
    rows = []
    for f in S.agent_plan_files(root):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            mtime = f.stat().st_mtime
        except OSError:
            continue
        lines = text.splitlines()
        head = "\n".join(lines[:PLAN_HEADER_LINES])
        m = PLAN_STATUS_RE.search(head) or PLAN_STATUS_INLINE_RE.search(head)
        status = m.group(1).lower() if m else "UNKNOWN"
        try:
            rel = str(f.relative_to(root))
        except ValueError:
            rel = str(f)
        rows.append((rel, status, len(lines), mtime))
    rows.sort(key=lambda r: -r[3])
    return [(rel, status, n) for rel, status, n, _mt in rows]


_EPOCH_MIN = C.parse_stamp("1970-01-01T00:00:00Z")


def plan_drift_rows(root, fold, session_id, plan_max_read=12):
    """[(relpath, status)] for NON-DONE plans this session has worked past.

    The gap the operator named: plans were surfaced at SessionStart and PostCompact and NOWHERE else, so a session could work all day while the committed design record describing that work went stale. Nothing bound the two together. `plan_records` already existed; it simply had no caller on the stop path.

    THE TRIGGER IS WORK, NEVER THE CLOCK -- the lesson STATE.md's check paid for twice. A plan is not stale because time passed; a week-old plan whose work nobody touched is perfectly accurate. It is stale when THIS session has ticked, added or updated its own items since the plan was last written, because that is exactly when the durable record stops describing the work.

    Only DRAFT / EXECUTING / UNKNOWN plans count. A plan marked done or superseded is history, and demanding edits to history is how a check earns its way into being ignored.

    Ownership-scoped like every other signature here: a PEER's items moving is not a reason to rewrite MY plan.
    """
    recs = plan_records(root)
    if not recs:
        return []
    mine = [r for r in fold.items if C.owned_by_me(r.get("owner"), session_id)]
    if not mine:
        return []

    rows = []
    for rel, status, _lines in recs[:plan_max_read]:
        # OWNERSHIP, the half this check was missing. The docstring above has always promised "a PEER's items moving is not a reason to rewrite MY plan", but the scoping was applied only to the ITEMS: any executing plan in agent/ was then matched against them, so MY items moving demanded I rewrite a plan whose header says `Owner: <someone else>`. That is the exact shape recorded at
        # PLAN_STATUS_RE above -- "two plans that were already accurate and were not even its own" -- where only the status half was fixed. A plan with no Owner line stays in scope, matching the untagged-item rule in C.owned_by_me.
        owner = plan_owner(root, rel)
        if not C.owned_by_me(owner, session_id):
            continue
        # ONLY `executing` (and UNKNOWN, which is loud by design). A plan that SAYS it is being executed while this session's work moved past it is a direct contradiction, and that is the whole signal.
        #
        # `draft` and `ready` are deliberately exempt: a proposal not yet started is not made wrong by unrelated work happening elsewhere. The first cut flagged every non-done plan and produced TWELVE rows at once, most of them drafts this session had never touched -- a wall that teaches the reader to skip the check, which is worse than not having it. Drafts still surface at
        # SessionStart and PostCompact, where orientation is the point and enforcement is not.
        if str(status).lower() not in ("executing", "unknown"):
            continue
        try:
            mtime = (pathlib.Path(root) / rel).stat().st_mtime
        except OSError:
            # Unreadable is REPORTED, never silently skipped: a plan the check cannot stat is exactly the one worth naming out loud, per the V_PR_UNREADABLE convention that a check which cannot read must say so rather than pass quietly.
            rows.append((rel, "UNREADABLE"))
            continue
        # HOW MUCH work moved past it, not merely whether ANY did. A single tick is not a plan going stale, and treating it as one made the check UNSATISFIABLE: update the plan, tick the next item, and it is stale again before you have drawn breath. That is the same self-inflicted churn `state_world_sig` was fixed for -- a document staled by the very bookkeeping that follows
        # refreshing it.
        #
        # The threshold is what makes the exit real: update the plan and it stays quiet for the next few ticks, which is exactly how long a plan actually stays accurate.
        #
        # AND ONLY THIS PLAN'S WORK. Every item the session owned used to count against every executing plan it owned, so a session driving several plans at once saw each of them flagged by work on the others -- found 2026-09-24 when PLAN-stop-hook-refactor-enforcement.md, freshly updated, was re-flagged by ticks on an npm migration and a temp-dir leak fix. The only exit left was to touch an accurate plan, which is the fake freshness the message above forbids. An item belongs to a plan when its text names the plan's file, the shape every `--plan` tracker and hand-added plan item already carries.
        base = rel.rsplit("/", 1)[-1]
        moved = sum(
            1
            for r in mine
            if base in str(r.get("text") or r.get("basetext") or "")
            and (C.parse_stamp(str(r.get("upd") or "")) or _EPOCH_MIN).timestamp() > mtime
        )
        if moved >= PLAN_DRIFT_MIN_MOVES:
            note = "%s, %d item(s) moved since" % (status, moved)
            if str(status).lower() == "unknown":
                # The reader here has no context by construction. Give them the subject and the files rather than only the complaint.
                title, files = plan_orientation(root, rel)
                if title:
                    note += ' -- "%s"' % title
                if files:
                    note += "; opens: " + ", ".join(files)
            rows.append((rel, note))

    return rows


# An UNKNOWN plan is the one a fresh context most needs help with, so it gets the most help rather than the least.
PLAN_ORIENT_BYTES = int(os.environ.get("WORKLIST_PLAN_ORIENT_BYTES", "8192"))
PLAN_ORIENT_FILES = int(os.environ.get("WORKLIST_PLAN_ORIENT_FILES", "4"))
# A path-shaped token: at least one directory separator and a known source or doc extension. Deliberately narrow -- a prose sentence containing a slash is not a file, and a wrong pointer is worse than none for a reader with no context.
_PLAN_PATH_RE = re.compile(
    r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.(?:go|ts|tsx|js|py|sh|md|json|yml|yaml|toml|sql)"
)


def plan_orientation(root, rel):
    """(title, [files]) for a plan whose Status could not be read.

    An UNKNOWN status says "this plan cannot be parsed" and stops, which tells the one reader who has no context precisely nothing. The operator asked for the opposite: a short description and the file names the plan mentions, so a new or compacted session knows what to open FIRST.

    Bounded on purpose. Only the first PLAN_ORIENT_BYTES are read (plans run to 10-20KB and the stop path must not become a file reader), and at most PLAN_ORIENT_FILES paths are reported, most-mentioned first -- a plan's own subject is the path it keeps returning to, while a passing reference is mentioned once.
    """
    try:
        with open(os.path.join(str(root), rel), encoding="utf-8", errors="replace") as fh:
            head = fh.read(PLAN_ORIENT_BYTES)
    except OSError:
        return "", []

    title = ""
    for line in head.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()[:90]
            break

    counts = {}
    for m in _PLAN_PATH_RE.finditer(head):
        hit = m.group(0)
        # The plan's own path is not a pointer to anywhere useful.
        if hit and not rel.endswith(hit):
            counts[hit] = counts.get(hit, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    return title, [f for f, _n in ranked[:PLAN_ORIENT_FILES]]


def plan_box_census(root, recs):
    """(per_relpath_counts, open_total, done_total, in_scope, exempt) for the boxes.

    S1 of agent/plans/PLAN-plan-file-lifecycle.md, and it exists because the operator asked "I feel like it only catches single file?" -- which was right, for TWO reasons and the smaller one was the known one.  # style-ok
    wl_planfile renders one plan per stop AND its NOT_STARTED_STATES filter drops the rest before it ever opens them: measured 2026-09-02, six of the eight box-carrying plans
    read `Status: draft`, hiding 72 of 88 open boxes, because `draft` has become this repo's default header on plans under ACTIVE execution rather than a marker for proposals.

    This census answers with the whole number instead. It runs from plans_block, which fires at SessionStart and PostCompact OUTSIDE the outq, so it cannot be starved the way the per-stop advisory was -- that one was shown once across six sessions in a day, at drain position 20 of 22 behind eleven priority-1 producers.

    Counts only, never quoted tasks: the advisory owns the quoting, and duplicating it here would rebuild the wall this is meant to replace.

    `wl_planfile` is the module-level import at the top of this file, not a deferred one. The first cut wrapped it in try/ImportError for "blindness", which was wrong twice over: wl_checks cannot load at all without it, so the arm was unreachable, and the control written to prove the arm had to fake `sys.modules` to reach it -- a control for a branch production can never take is
    the vacuous shape this file polices elsewhere. Both are gone. The caller's own `except Exception` at the plan-tasks advisory is what keeps a parser fault from wedging a stop.
    """
    counts, o_tot, d_tot, in_scope, exempt = {}, 0, 0, 0, 0
    for rel, status, _n in recs:
        try:
            text = (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        open_t, done_t = wl_planfile.plan_boxes(text)
        if not (open_t or done_t):
            continue
        counts[rel] = (len(open_t), len(done_t))
        o_tot += len(open_t)
        d_tot += len(done_t)
        if wl_planfile.in_scope_status(status):
            in_scope += 1
        else:
            exempt += 1
    return counts, o_tot, d_tot, in_scope, exempt


def plans_block(root):
    """(listing, live_records): the non-done plans, one line each, plus one count line for the executed ones. ("", []) when there is nothing to say, so a project without plans emits no block at all.

    Each line carries its BOX COUNTS, and two summary lines carry the tree-wide totals -- see plan_box_census for why the per-stop advisory cannot supply them.

    W12 P1.7: THE NUMBERS COME FROM `agent/INDEX.md` NOW, not from opening every plan. Measured on this tree before the change, 166 `read_text` calls across 83 files and 2,018,737 bytes, on every SessionStart and every PostCompact, to print 56 lines. `wl_planindex.index_census` answers the same question from ONE file read plus a `stat` per plan.

    THE FALLBACK IS THE OLD PATH AND IT IS LOUD. An absent or stale index does not shorten this listing and does not empty it -- it rebuilds it by reading the plans, exactly as before, and PREPENDS a banner naming the state, the disagreement and the regeneration command. A plans block that went quiet because its index was missing would be a worse defect than the cost it saves, so
    the degraded path is slow-and-correct and never fast-and-blind.
    """
    stats = PI.plan_stats(root)
    if not stats:
        return "", []
    rows, state, detail = PI.index_census(root, stats=stats)
    if state != PI.CENSUS_FRESH:
        rows = PI.census_rows(root, plan_records=plan_records, plan_box_census=plan_box_census)
    head = PI.banner(state, detail, len(stats))
    # NEWEST FIRST, restored from the `stat` pass rather than from the committed file. `plan_records` has always sorted this way and `plan_status_excerpt` takes `live[0]` as "the newest live plan", so an index that dropped mtime would silently change which plan a compacted session gets excerpted. The sort is stable, so the by-path order inside an mtime tie is the same order
    # `sorted(d.glob(...))` gave the old path.
    mtimes = {rel: mt for rel, _sz, mt in stats}
    rows = sorted(rows, key=lambda r: -mtimes.get(r[0], 0.0))
    live = [r for r in rows if r[1] not in PLAN_DONE_STATES]
    big = PI.big_pieces(live)
    if not live:
        # PLANS EXIST BUT NONE ARE LIVE. This used to return ("", []), which made "every plan is done" indistinguishable from "this project has no plans" -- both printed nothing. It is a real and reportable state, so it now renders its summary lines. The `not stats` guard above still returns ("", []) for a project with no plans at all, which is the case the early return was
        # actually written for.
        tail = _plan_census_summary(rows)
        return (head + "\n".join(tail)) if tail else "", []
    # Big pieces sort FIRST, ahead of the mtime order otherwise in force -- the plan this session should finish next is not necessarily the one it touched most recently. `sorted` is stable, so ties within "big" and within "not big" keep their existing mtime order.
    ordered = sorted(live, key=lambda r: r[0] not in big)
    lines = []
    for rel, status, n, n_open, n_done, _size in ordered:
        suffix = ", %d open box(es), %d ticked" % (n_open, n_done) if (n_open or n_done) else ""
        mark = "! BIG PIECE ! " if rel in big else ""
        lines.append("  %s%s [%s] (%d lines%s)" % (mark, rel, status, n, suffix))
    done = len(rows) - len(live)
    if done:
        lines.append(
            "  (+%d done or superseded plan(s) in the same directory: historical "
            "record, read one only if you need the reasoning behind it)" % done
        )
    lines.extend(_plan_census_summary(rows))
    return head + "\n".join(lines), [(r[0], r[1], r[2]) for r in live]


def _plan_census_summary(rows):
    """The two tree-wide totals lines, or [] when no plan carries a box.

    Split out of plans_block because both of its exits need them and because the arithmetic is the part that has to agree with `plan_box_census` exactly: a plan with no boxes contributes NO row to the counts, which is why the filter is on `(open or ticked)` and not on the plan set.
    """
    boxed = [r for r in rows if r[3] or r[4]]
    if not boxed:
        return []
    o_tot = sum(r[3] for r in boxed)
    d_tot = sum(r[4] for r in boxed)
    in_scope = sum(1 for r in boxed if wl_planfile.in_scope_status(r[1]))
    return [
        "  %d plan file(s) carry %d open box(es) and %d ticked, tree-wide."
        % (len(boxed), o_tot, d_tot),
        "  %d of them are in scope for the per-stop advisory; %d are exempt by "
        "Status, so their boxes are counted HERE and nowhere else."
        % (in_scope, len(boxed) - in_scope),
    ]


def plan_status_excerpt(root, live):
    """(relpath, body) of the newest non-done plan's '## Status' section, capped. ("", "") when there is none, which is the honest answer for a draft that has not been taken over yet."""
    if not live:
        return "", ""
    rel = live[0][0]
    try:
        text = (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rel, ""
    for chunk in text.split("\n## ")[1:]:
        title, _nl, body = chunk.partition("\n")
        if title.strip().lower() == "status":
            return rel, body.strip()[:PLAN_EXCERPT_CHARS]
    return rel, ""


def triage_context(root, worklist, session_id=""):
    """The facts the CLI can honestly gather about a finding's blast radius.

    Passed to the triage judge AND printed in degraded mode, so the session self-assesses on exactly the same facts the model would have seen. `git status --porcelain` is the load-bearing one: it names the files this session already has in flight, which is what makes "is the fix's file set disjoint" an answerable question rather than a guess.
    """
    branch = C.git_branch(root)
    d = plan_dir(root)
    recs = plan_records(root)
    if not d.is_dir():
        plans = "%s does not exist yet (creating it is part of writing a plan)" % d
    else:
        plans = "%s exists, %d plan file(s)" % (d, len(recs))
    status = C._git(root, "status", "--porcelain") or ""
    rows = [ln for ln in status.splitlines() if ln.strip()][:40]
    files = "\n".join("    " + ln for ln in rows) or "    (working tree clean)"
    try:
        fold = S.load(worklist, sync=False)
        open_n = sum(
            1
            for r in fold.items
            if r["state"] in (" ", ">", "?")
            and (not session_id or C.owned_by_me(r["owner"], session_id))
        )
        opens = "%d" % open_n
    except Exception:  # noqa: BLE001 -- a context fact must never break the verb
        opens = "unknown (the store could not be read)"
    return (
        "  branch: %s\n"
        "  plan directory: %s\n"
        "  files this session already has in flight (git status --porcelain, "
        "first 40):\n%s\n"
        "  open items this session is already tracking: %s"
        % (branch or "(none)", plans, files, opens)
    )


# ---- v11: the store-derived stop guide -------------------------------------- WHY (operator, 2026-07-30): "--list should be used always on stop hook to output enforced guided instructions." The defect this fixes is structural: v10 stamped every item and the hand-authored Remaining prose never read the store, so the tracing existed and the report ignored it. The guide is emitted
# on EVERY full stop, allow and block alike, so the session bases its report on the store instead of memory.
#
# BOUNDED HARD, because the live store folds 831 items (550 KB as a raw --list) and this hook fires on every stop: only the ACTIONABLE slice is emitted (open, in-flight, deferrals and expired leases -- never [x]), at most GUIDE_MAX lines, each capped, and a cap that drops anything SAYS SO with the count, because a silent cap reads as "that is everything".

GUIDE_MAX = int(os.environ.get("WORKLIST_GUIDE_MAX", "12"))
# How long a SUBMODULE POINTER MOVED warning stays latched for one (path, sha) signature. Time-boxed on purpose: a permanent acknowledgement would go silent on a pointer somebody forgot, and a forgotten pointer ships whatever the parent last recorded. A move to a new sha re-fires immediately regardless.
SUBMODULE_LATCH_MIN = int(os.environ.get("WORKLIST_SUBMODULE_LATCH_MIN", "15"))
# How long the same warning stays latched once a session has RECORDED a decision about that exact (path, sha). Longer than the bare latch by a lot, and still NOT permanent, because the reason the bare latch is time-boxed applies here too: a decision can go stale, and a pointer nobody revisits ships whatever the parent last recorded. A day means a decided pointer stops interrupting
# a working session and still gets re-examined tomorrow.
SUBMODULE_DECIDED_LATCH_MIN = int(os.environ.get("WORKLIST_SUBMODULE_DECIDED_LATCH_MIN", "1440"))


def _json_or_none(line):
    """One JSONL row, or None when the line is not a row. A ledger is append-only under a lock, so a torn final line is possible and is not an error worth propagating."""
    try:
        return json.loads(line)
    except (ValueError, TypeError):
        return None


# A decision word in an item's note (R20260924.23), upper case as the lead writes it.
_DECISION_RE = re.compile(r"\b(?:KEEP|DROP)\b")
_SHA_PREFIX_RE = re.compile(r"\b[0-9a-f]{7,40}\b")


def _open_item_decides(rec, path, sha, session_id):
    """True when `rec` is an open or `[>]` item this session owns whose latest note carries KEEP or DROP, `path`, and a sha prefix of 7 or more characters of `sha` (R20260924.23)."""
    if rec.get("state") not in (" ", ">") or not C.owned_by_me(rec.get("owner"), session_id):
        return False
    note = str(rec.get("lastnote") or rec.get("basetext") or rec.get("text") or "")
    if path not in note or not _DECISION_RE.search(note):
        return False
    target = str(sha).lower()
    return any(
        target.startswith(tok) or tok.startswith(target)
        for tok in _SHA_PREFIX_RE.findall(note.lower())
    )


def submodule_decision_recorded(root, path, sha, fold=None, session_id=None):
    """Has ANY session ticked an item naming this submodule path and target sha, or has THIS session recorded KEEP or DROP for it in an open item?

    THE OPEN-ITEM ARM (R20260924.23): with `fold` and `session_id`, an owned open or `[>]` item whose latest note carries KEEP or DROP, the path, and a sha prefix of 7+ characters counts too (`_open_item_decides`). On 2026-09-24 the move `private/account 9fda8c7c2 -> aea435154` blocked twice, 17.5 minutes apart, while #f2dd1732's note already read "9fda8c7 -> aea4351 ...: KEEP"; the lead then staged the gitlink only to silence the check. Only THIS session's items: a decision in a peer's open item is still in flight, while a TICKED one below binds everyone.

    The check offers two doors, KEEP (stage it) and DROP (`git submodule update --checkout`), and there is a third that is often the right one: leave the worktree alone and never stage it, which is correct when the parent's HEAD already matches and the checkout belongs to a peer session. Nothing in the warning could see that such a decision existed, so a session that had decided,
    ticked and documented it was told off every fifteen minutes.

    Reads the ledgers of EVERY session, not just this one, because a submodule pointer is shared state: a peer's ruling on it is as binding as ours.

    FAIL-SAFE BY CONSTRUCTION. Any error at all returns False, which restores exactly the previous behaviour. This function runs inside the stop hook of every session in the worktree, so the cost of it being wrong is not local, and the safe direction is to warn too often rather than too rarely.
    """
    if fold is not None and session_id:
        with contextlib.suppress(AttributeError, TypeError):
            if any(_open_item_decides(rec, path, sha, session_id) for rec in fold.by_id.values()):
                return True
    try:
        store = pathlib.Path(root) / "agent" / "worklist"
        if not store.is_dir():
            return False
        short = str(sha)[:9]
        for led in store.glob("*.jsonl"):
            try:
                text = led.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # TWO PASSES, because the decision is the ITEM and not any one event. A tick is `ev: state` with `s: "x"` -- that is the schema, not a guess: the store has no "tick" or "done" event kind at all, and a first draft looking for one matched nothing and would have shipped a predicate that could never fire. The other state value is "?" for a deferral, and a deferral is
            # explicitly NOT a decision.
            #
            # The sha usually appears in the item's TITLE, on its `add` event, rather than in the tick evidence, and that is not an accident: a submodule commit is a gitlink and never an object in this repository, so `completion_evidence` REFUSES a tick whose only evidence is such a sha. The tick therefore describes the decision in prose while the title carries the pair. Matching
            # one line at a time misses that, which a both-direction test caught here.
            ticked = set()
            events = []
            for line in text.splitlines():
                ev = _json_or_none(line)
                if ev is None:
                    continue
                events.append(ev)
                if ev.get("ev") == "state" and ev.get("s") == "x" and ev.get("id"):
                    ticked.add(ev["id"])
            for ev in events:
                if ev.get("id") not in ticked:
                    continue
                blob = " ".join(v for v in ev.values() if isinstance(v, str))
                if path in blob and short in blob:
                    return True
        return False
    except (OSError, ValueError, TypeError):
        # NARROW ON PURPOSE, and still fail-safe: these are what a missing store, an unreadable ledger or a malformed row can raise. A blind `except` here would also swallow a real programming error in this function and report "no decision", which is the safe DIRECTION but hides the bug forever. This runs in the stop hook of every session in the worktree, so a mistake is not local,
        # but neither is a defect nobody can see.
        return False


GUIDE_TEXT_CHARS = 90

# The allow-report diet (operator, 2026-07-31: "Why I see such a big output?"). Slow-moving advisory sections re-show only when their content changes or after this many minutes, whichever comes first.
REPORT_REFRESH_MIN = int(os.environ.get("WORKLIST_REPORT_REFRESH_MIN", "360"))

# ---- the allow-report OUTPUT QUEUE ------------------------------------------ The diet above deduplicated sections; this bounds how many reach one stop. Sections are ENQUEUED AT COMPUTE TIME, at their producer's call site, never in the emit block -- because emit() exits the process, and two producers (the liveness ladder and dead-session archiving) spend a
# one-shot budget BEFORE the block emit at run_stop's violations branch. Their text was only ever appended on the allow path, so a stop that blocked for an unrelated reason swallowed them for good: the rung is recorded, the item is already [~], the [?] is already appended, and nothing re-fires. An entry that lands in the state doc the moment its producer spends that budget survives
# a block, a judge block, a crash and a restart.
# Fixed at 3, not tunable. A prior env knob (WORKLIST_REPORT_PER_STOP) let a session widen the drain to see everything at once, which is exactly the emergency valve that made the queue's own backlog invisible. The two tests pinning this number -- test_181 (tier order) and the padded test_201/209K fixtures (randomization robustness) -- assume this exact value; raising it again
# reopens the vacuity those tests were rescued from.
OUTQ_PER_STOP = 3
OUTQ_MAX = int(os.environ.get("WORKLIST_OUTQ_MAX", "40"))


def _outq(state_doc):
    """The queue sub-doc, seeded from the v11 report_seen ledger on first sight.

    Without the seed the first upgraded stop re-shows every already-latched advisory at once, which is precisely the symptom being fixed. report_seen is left in place unread rather than deleted: a sole-operator clean break still should not make that stop the noisiest one the session ever saw."""
    q = state_doc.get("outq")
    if not isinstance(q, dict):
        q = {"seq": 0, "items": [], "shown": dict(state_doc.get("report_seen") or {})}
        state_doc["outq"] = q
    q.setdefault("seq", 0)
    q.setdefault("items", [])
    q.setdefault("shown", {})
    return q


def _outq_cap(q):
    """Hold OUTQ_MAX by dropping non-sticky entries, lowest priority first then oldest first. A sticky entry is NEVER dropped, even when stickies alone exceed the cap: a one-shot the cap ate is a one-shot lost."""
    items = q["items"]
    if len(items) <= OUTQ_MAX:
        return
    for e in sorted(
        (e for e in items if not e.get("sticky")),
        key=lambda e: (-int(e.get("prio") or 0), int(e.get("seq") or 0)),
    ):
        if len(items) <= OUTQ_MAX:
            break
        items.remove(e)


def outq_add(
    worklist, session_id, state_doc, key, text, prio, sticky=False, refresh_min=None, on_change=True
):
    """Queue one allow-report section. Persists the state doc immediately.

    Returns True when an entry was added or refreshed, False when the call was absorbed (unchanged content inside its refresh window, or already queued). The return value is for the suite and for a caller that wants to skip building an expensive body; nothing in run_stop needs it.

    PERSISTS ON EVERY CALL, deliberately. Six of run_stop's emit paths do not save the state doc before emitting, so a "save at the end" contract would lose exactly what this queue exists to keep. The cost is at most about ten tempfile+os.replace writes on a path that already runs git and gh subprocesses."""
    q = _outq(state_doc)
    items = q["items"]
    sig = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:12]
    # A one-shot's entry key carries its own sig, so two different bodies under one section name never overwrite each other. There is deliberately NO shown-ledger for sticky keys: a one-shot producer cannot re-fire, so a ledger that could suppress one is a way to lose it. Showing one twice is cosmetic; dropping one is the failure this queue exists to prevent.
    ekey = "%s:%s" % (key, sig) if sticky else key
    cur = next((e for e in items if e.get("key") == ekey), None)
    added = False
    if sticky:
        if cur is None:
            q["seq"] = int(q.get("seq") or 0) + 1
            items.append(
                {
                    "key": ekey,
                    "prio": prio,
                    "sticky": True,
                    "sig": sig,
                    "text": text,
                    "at": C.stamp_now(),
                    "seq": q["seq"],
                }
            )
            added = True
    elif cur is not None and not on_change:
        # Identity is the KEY alone: the backoff tip's wording carries a live minute counter, so a content hash would re-enqueue it every stop. The freshest wording rides the position the entry already earned.
        if cur.get("text") != text:
            cur["text"], cur["sig"] = text, sig
            added = True
    elif cur is not None:
        if cur.get("sig") != sig:
            # Changed content re-enqueues AT ITS PRIORITY: a new seq sends it to the back of its own class rather than jumping the queue.
            q["seq"] = int(q.get("seq") or 0) + 1
            cur["text"], cur["sig"], cur["seq"] = text, sig, q["seq"]
            cur["at"] = C.stamp_now()
            added = True
    else:
        window = REPORT_REFRESH_MIN if refresh_min is None else refresh_min
        prev = q["shown"].get(key) or {}
        age = C.stamp_age_min(prev.get("at", ""))
        fresh = age is not None and age < window
        if not (fresh and (prev.get("sig") == sig or not on_change)):
            q["seq"] = int(q.get("seq") or 0) + 1
            items.append(
                {
                    "key": key,
                    "prio": prio,
                    "sticky": False,
                    "sig": sig,
                    "text": text,
                    "at": C.stamp_now(),
                    "seq": q["seq"],
                }
            )
            added = True
    if added:
        _outq_cap(q)
        S.save_state(worklist, session_id, state_doc)
    return added


def blocklog(worklist, me8, key, named=(), judge=None):
    """Append one row per BLOCKED stop to `.blocklog-<me8>.jsonl` beside the worklist: the key the block leads with, every other outstanding key it named, and the judge's flags when the judge blocked (agent/plans/PLAN-stop-hook-retro-20260924.md R.10).

    The retro counts blocks per key from this file instead of grepping a 222 MB transcript. One small O_APPEND line; a log that cannot be written never changes the block.
    """
    row = {"at": C.stamp_now(), "key": key, "named": list(named)[:40], "judge": judge or {}}
    with contextlib.suppress(OSError):
        fd = os.open(
            str(worklist.with_suffix(".blocklog-%s.jsonl" % me8)),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o644,
        )
        try:
            os.write(fd, (json.dumps(row) + "\n").encode("utf-8"))
        finally:
            os.close(fd)


def judge_flags(verdict, reggate=""):
    """The judge facts a blocklog row carries: the verdict, and which obligations its reason shows fired."""
    reason = str((verdict or {}).get("reason") or "")
    return {
        "verdict": str((verdict or {}).get("verdict") or ""),
        "sweep": "SWEEP THE CLASS" in reason,
        "proof": "PROOF OBLIGATION" in reason,
        "reggate": reggate,
    }


def outq_drain(worklist, session_id, state_doc, n, rng=None, only=None):
    """(texts, remaining): up to n entries, TIER ORDER preserved, same-tier choice randomized.

    Priority tiers are still released strictly ascending (a priority-3 item never displaces a priority-1 one), but which entries fill a tier's share of the budget is now picked at random rather than FIFO by `seq`. This is deliberate: at a fixed budget of `OUTQ_PER_STOP`, FIFO meant an old same-tier item could sit queued indefinitely behind a stream of newer arrivals at
    the same priority, which is exactly the starvation shape `test_176`'s planted-defect control exists to catch -- randomization spreads that risk across every same-tier entry instead of concentrating it on whichever one happened to queue first.

    `rng` is the whole determinism seam: `None` resolves to the module-level `random` for real stops, and a test passes `random.Random(seed)` to drive the same code path in-process rather than trying to reach a subprocess's random state.

    Removes exactly those entries BY IDENTITY (never by slicing or clearing -- a clear silently eats every one-shot that had not reached its turn), records shown[] for the volatile ones, and persists before returning, because the caller emits and emit() exits the process.

    `only`, when given, is a predicate over the entry's display key: entries it rejects are neither candidates nor touched, and stay queued (focus mode's batching). The returned remaining count still counts them."""
    q = _outq(state_doc)
    r = rng if rng is not None else random
    tiers: dict[Any, Any] = {}
    for e in q["items"]:
        if only is not None and not only(_outq_display_key(e)):
            continue
        tiers.setdefault(int(e.get("prio") or 0), []).append(e)
    take = []
    budget = max(0, n)
    for prio in sorted(tiers):
        if budget <= 0:
            break
        pool = tiers[prio]
        if len(pool) <= budget:
            take.extend(pool)
            budget -= len(pool)
        else:
            take.extend(r.sample(pool, budget))
            budget = 0
    # A DIGEST, NOT A QUEUE OF FACTS. Every settled regression-gate outcome is a sticky one-line fact that is not asked again; released one per stop they took a stop each, and a long session accumulated twenty-five of them. When one comes due, ALL of its siblings ride the same stop as one section, so the queue holds at most one of them however many fixes settled.
    is_settled = lambda e: str(e.get("key", "")).startswith("reg-settled:")  # noqa: E731
    if any(is_settled(e) for e in take):
        ordered = sorted(
            (e for e in q["items"] if is_settled(e)), key=lambda e: int(e.get("seq") or 0)
        )
        merged = dict(ordered[0])
        merged["text"] = "\n".join(e.get("text", "") for e in ordered)
        q["items"] = [e for e in q["items"] if not is_settled(e)] + [merged]
        take = [e for e in take if not is_settled(e)] + [merged]
    picked = {id(e) for e in take}
    for e in take:
        if not e.get("sticky"):
            q["shown"][e["key"]] = {"sig": e.get("sig", ""), "at": C.stamp_now()}
    q["items"] = [e for e in q["items"] if id(e) not in picked]
    S.save_state(worklist, session_id, state_doc)
    return [e.get("text", "") for e in take], len(q["items"])


OUTQ_DIGEST_MAX = 6
# A blocked stop carries the rotating behavioral hint at most this often (agent/plans/PLAN-stop-hook-continuity.md P0.5). A sealed literal: a hint on every block would be the always-fires prompt that gets skimmed.
BLOCK_HINT_MIN = 30


def _outq_display_key(e):
    """The section name a reader recognises: a sticky entry's key carries `:<sig>` for identity, which is noise on a digest line."""
    key = str(e.get("key") or "")
    sig = str(e.get("sig") or "")
    return key[: -len(sig) - 1] if e.get("sticky") and sig and key.endswith(":" + sig) else key


def _outq_group_line(key, entries):
    """The one digest line for every multi-line entry under `key`. The ladder names its quiet subjects by id; any other key shows its newest entry's first line and a count."""
    if key == "ladder":
        ids = []
        for e in entries:
            for ident in re.findall(r"#([0-9a-f]{6,})", str(e.get("text") or "")):
                if ident not in ids:
                    ids.append(ident)
        return M.N_OUTQ_LADDER_LINE % (len(ids), ", ".join("#" + i for i in ids[:8]))
    newest = max(entries, key=lambda e: int(e.get("seq") or 0))
    first = (str(newest.get("text") or "").strip("\n").splitlines() or [""])[0]
    return first if len(entries) == 1 else "%d queued, newest: %s" % (len(entries), first)


def outq_digest(worklist, session_id, state_doc, n=OUTQ_DIGEST_MAX, skip=(), only=None):
    """The blocked stop's view of the advisory queue: (digest text or "", delivered count).

    One line per entry, `key: first line`, highest priority (lowest number) first then oldest, at most `n` lines. An entry whose WHOLE text is one line has been fully shown by that line, so it is DELIVERED: removed by identity and, for a volatile entry, recorded in `shown` exactly as `outq_drain` records it. A multi-line body stays queued for a clean stop, where it is released in full. Keys in `skip` are neither named nor delivered: the caller already shows them in full, and entries `only` rejects (a predicate over the display key) are left queued untouched. Persists before returning, because the caller emits and emit() exits."""
    q = _outq(state_doc)
    items = sorted(
        (
            e
            for e in q["items"]
            if _outq_display_key(e) not in skip and (only is None or only(_outq_display_key(e)))
        ),
        key=lambda e: (int(e.get("prio") or 0), int(e.get("seq") or 0)),
    )
    if not items:
        return "", 0
    # SAME-KEY MULTI-LINE ENTRIES COLLAPSE INTO ONE LINE (agent/plans/PLAN-stop-hook-retro-20260924.md R.9): six identical `ladder` lines once filled the whole digest, stop after stop, so no one-line advisory behind them was ever delivered. A one-line entry keeps its own line, because that line IS its delivery.
    rows: list[tuple[str, Any]] = []
    grouped: dict[str, list[dict]] = {}
    for e in items:
        body = str(e.get("text") or "").strip("\n")
        if "\n" in body:
            key = _outq_display_key(e)
            if key in grouped:
                grouped[key].append(e)
                continue
            grouped[key] = [e]
            rows.append(("group", key))
        else:
            rows.append(("one", e))
    head, rest = rows[: max(0, n)], len(rows) - max(0, n)
    lines, delivered = [], set()
    for kind, what in head:
        if kind == "group":
            lines.append("    %s: %s" % (what, _outq_group_line(what, grouped[what])[:150]))
            continue
        e = what
        body = str(e.get("text") or "").strip("\n")
        first = (body.splitlines() or [""])[0]
        lines.append("    %s: %s" % (_outq_display_key(e), first[:150]))
        if len(first) <= 150:
            delivered.add(id(e))
            if not e.get("sticky"):
                q["shown"][e["key"]] = {"sig": e.get("sig", ""), "at": C.stamp_now()}
    if rest > 0:
        lines.append(M.N_OUTQ_DIGEST_MORE % rest)
    if delivered:
        q["items"] = [e for e in q["items"] if id(e) not in delivered]
        S.save_state(worklist, session_id, state_doc)
    return M.N_OUTQ_DIGEST % (len(items), "\n".join(lines)), len(delivered)


def agent_hint_queue(worklist, session_id, state_doc, haystack):
    """Queue the specialist-agent hint for this stop, if one is earned.

    ADVISORY, never a block. `vadd` (46 call sites) stops the session; blocking a session for not consulting a specialist is the fastest possible way to get this feature switched off, and it would compete for the single focused slot with real violations.

    PRIORITY 3, which is the whole noise control and it costs nothing: every
    existing advisory is 2 or better and outq_drain releases OUTQ_PER_STOP=3 of
    them per stop, so a hint is only ever emitted on a stop that has room left after everything more important. The per-agent key plus REFRESH_MIN then means the same specialist cannot be suggested twice inside the window, and the state-doc ledger enforces MAX_PER_SESSION across all agents.

    The cap counts ADDS, not matches: outq_add absorbs a hint that is already queued or still inside its refresh window, and counting an absorbed hint would spend the session's budget on lines nobody ever saw.
    """
    corpus, errors = A.load_corpus(A.agents_dir())
    if errors:
        # LOUD, and its own section: a corpus this hook cannot read is exactly the silent-degradation this feature exists to end. Priority 3 too -- it is still advice, and it must not displace a real report section.
        outq_add(
            worklist,
            session_id,
            state_doc,
            "agent-corpus-err",
            M.N_AGENT_CORPUS_ERR % "\n".join("  " + e for e in errors),
            3,
            refresh_min=A.REFRESH_MIN,
        )
    if not A.ENABLED or not corpus:
        return None
    shown = state_doc.get("agent_hints")
    if not isinstance(shown, dict):
        shown = {}
        state_doc["agent_hints"] = shown
    if len(shown) >= A.MAX_PER_SESSION:
        return None
    hit = A.best_hint(haystack, A.discriminative(corpus))
    if not hit:
        return None
    name, _score, hits = hit
    added = outq_add(
        worklist,
        session_id,
        state_doc,
        "agent-hint:%s" % name,
        M.N_AGENT_HINT % (name, name, ", ".join(hits[:6])),
        3,
        refresh_min=A.REFRESH_MIN,
    )
    if not added:
        return None
    shown[name] = C.stamp_now()
    S.save_state(worklist, session_id, state_doc)
    return name


def guided_slice(fold, session_id, verdicts=None, me=None, root=None, full=False):
    """The bounded, guided, store-derived instruction block.

    One line per actionable item: state, #id, age from the store's own stamps, the capped text, and the EXACT verb that moves it -- an open item gets --tick, a live lease gets --update, an undefaulted [?] gets --defer, an expired-window [?] gets its default-execution order. Sorted by priority (obligations first) so truncation drops the least urgent. `verdicts` (from
    wl_liveness.verify_background) annotates lease workers when the caller has an event to verify against; the CLI does not.

    v16 FOLLOW-THROUGH: an item triaged 'plan-subagent' whose recorded plan file is NOT on disk is promoted to priority 0 with the demand to write it, and one whose plan EXISTS advertises the path. This is one os.path.exists per triaged item, bounded by the fold, and it is report-only: a guide line, never a new block, so the stop path stays cheap and the guide's no-new-block
    invariant holds. `root` is passed by both callers; None derives it, which the direct-library callers rely on.

    `full=True` LIFTS the GUIDE_MAX cap. The cap exists to bound the Stop
    hook's payload, so the hook keeps it; the CLI does not, and until now it silently inherited it -- which made GUIDE_TRUNCATED's own advice a loop, since it points at `--list --open` "for the full slice" and that command re-rendered the same 12 rows. A human asking for the slice by hand gets every row and no truncation footer.
    """
    me_arg = (me or "<me>")[:8] if me else "<me>"
    verdicts = verdicts or {}
    rows = []  # (priority, line)
    by_id = {r["id"]: r for r in fold.items}
    for rec in fold.items:
        if session_id and not C.owned_by_me(rec["owner"], session_id):
            continue
        st = rec["state"]
        if st == "x":
            continue
        txt = S.brief_text(rec, GUIDE_TEXT_CHARS)
        upd = C.stamp_age_min(rec.get("upd", ""))
        age = "?" if upd is None else "%dm" % upd
        rid = rec["id"]
        tri = rec.get("triage") or {}
        plan = tri.get("plan", "") if tri.get("v") == "plan-subagent" else ""
        if plan and st in (" ", ">"):
            if root is None:
                # No event in scope here -- guided_slice takes none. Passing one was a NameError that failed SOFT: the caller wraps this in a bare except and replaces the whole guide with "WORKLIST GUIDE unavailable", so the operator's entire worklist surface would have degraded silently on any triaged-BIG item.
                root = C.project_root(C.project_start())
            if not os.path.exists(os.path.join(root, plan)):
                rows.append(
                    (
                        0,
                        "  - [%s] #%s (upd %s) %s\n        TRIAGED BIG, plan file missing: %s\n        NEXT: write the plan (Plan agent) or re-triage: --triage %s --id %s <finding>"
                        % (st, rid, age, txt, plan, me_arg, rid),
                    )
                )
                continue
        else:
            plan = ""
        before = len(rows)
        # An EXPIRED queue lease on an item still waiting on its BLOCKED_BY blocker reads as waiting too, the same answer wl_store.classify_items gives it (agent/plans/PLAN-stop-hook-retro-20260925.md R20260925.5); the guide said "LEASE DEAD ... re-lease" for it while the stop allowed.
        queue_wait = (
            st == ">"
            and rec.get("worker") == wl_leasehelp.QUEUE_WORKER
            and C.lease_state(rec["line"]) == "expired"
        )
        waiting = wl_leasehelp.waiting_on(rec, by_id) if st == " " or queue_wait else []
        if waiting:
            rows.append(
                (
                    3,
                    "  - [%s] #%s waiting (%s) %s\n        NEXT: nothing until they close; it reopens by itself"
                    % (st, rid, ", ".join("#" + w for w in waiting), txt),
                )
            )
        elif st == " ":
            rows.append(
                (
                    0,
                    "  - [ ] #%s (upd %s) %s\n        NEXT: do it, then --tick %s %s '<evidence>'"
                    % (rid, age, txt, me_arg, rid),
                )
            )
        elif st == ">":
            wm = C.WORKER.search(rec["line"])
            wid = rec.get("worker") or (wm.group(1) if wm else "")
            if C.lease_state(rec["line"]) == "fresh" or rec.get("lease_tolerated"):
                osw = verdicts.get(wid, "")
                wtag = "worker:%s%s" % (wid or "?", " [%s]" % osw if osw else "")
                if rec.get("lease_tolerated"):
                    wtag += " (lease expired, worker verified alive: auto-honored; renew or tick when it lands)"
                # THE DEADLINE IS RENDERED RELATIVE AS WELL AS ABSOLUTE, because the absolute form alone is misread the moment the reader's LOCAL date has rolled over while UTC has not. Measured 2026-09-08T22:37Z: local was already 2026-09-09 00:37 CEST, the item carried `until:2026-09-08T23:36Z`, and the stop-gate judge read that as "in the past" and refused a legitimate stop.
                # `lease_state` had it right all along -- it compares in UTC -- so nothing was wrong except what the line SHOWED.
                wtag += C.lease_remaining_tag(rec["line"])
                rows.append(
                    (
                        3,
                        "  - [>] #%s (quiet %s, %s) %s\n        NEXT: --update %s %s '<one line of what moved>'"
                        % (rid, age, wtag, txt, me_arg, rid),
                    )
                )
            else:
                rows.append(
                    (
                        0,
                        "  - [>] #%s LEASE DEAD (quiet %s) %s\n        NEXT: finish it and --tick %s %s '<evidence>', or re-lease: --lease %s %s +60 worker:<bg-id>"
                        % (rid, age, txt, me_arg, rid, me_arg, rid),
                    )
                )
        elif st == "?":
            if not C.DEFAULT_TOKEN.search(rec["line"]):
                rows.append(
                    (
                        2,
                        "  - [?] #%s (age %s, NO DEFAULT) %s\n        NEXT: --defer %s %s '<question> DEFAULT: <action> WHY: <reason> HOW: <resolution>'"
                        % (rid, age, txt, me_arg, rid),
                    )
                )
            elif upd is not None and upd >= S.DEFER_WINDOW_MIN:
                rows.append(
                    (
                        1,
                        "  - [?] #%s WINDOW CLOSED (waited %s) %s\n        NEXT: execute its DEFAULT now, then --tick %s %s '<evidence>'"
                        % (rid, age, txt, me_arg, rid),
                    )
                )
            else:
                left = "?" if upd is None else "%dm" % max(0, S.DEFER_WINDOW_MIN - upd)
                rows.append(
                    (
                        4,
                        "  - [?] #%s (age %s) %s\n        operator may answer; its DEFAULT executes in %s"
                        % (rid, age, txt, left),
                    )
                )
        # The design EXISTS: advertise where it lives, so the guide points at the plan instead of leaving the next session to find it.
        if plan and len(rows) > before:
            prio, line = rows[-1]
            rows[-1] = (prio, line + "\n        plan: %s" % plan)
    if not rows:
        return M.GUIDE_EMPTY
    rows.sort(key=lambda r: r[0])
    shown = rows if full else rows[:GUIDE_MAX]
    out = [M.GUIDE_HEADER] + [line for _p, line in shown]
    if len(rows) > len(shown):
        out.append(M.GUIDE_TRUNCATED % (len(rows) - len(shown), GUIDE_MAX))
    return "\n".join(out)


# ---- SessionStart / PostCompact ---------------------------------------------


def mark_context_fresh(event, why):
    """Record that this session's context was just (re)built, so the next judged stop states the judge's FULL approval reason instead of the bare stamp. Never raises: a context marker must not be able to wedge a SessionStart."""
    try:
        wl = C.worklist_for(C.project_start(event))
        sid = event.get("session_id", "")
        doc = S.load_state(wl, sid)
        doc["ctx_fresh"] = {"why": why, "at": C.stamp_now()}
        S.save_state(wl, sid, doc)
    except Exception:  # noqa: BLE001 -- a marker must never wedge a SessionStart
        pass


def handle_session_start(event):
    # FIRST statement, not last: the design-docs/plans blocks below return early when a project has neither, and such a project would otherwise never be marked.
    source = str(event.get("source") or "").strip().lower()
    # A COMPACTION IS ATTRIBUTED FIRST, exactly as handle_post_compact does it (R20260924.16): a sub-agent's compaction arrives with the lead's session_id and transcript_path and no agent_id, and stamping the lead's ctx_fresh for it is the defect R.16 fixed on the PostCompact path and left open here (retro writer A's finding, second retro of 2026-09-24). Any other source is the session's own start.
    if source != "compact" or _compaction_owner(event, event.get("session_id", "")) == "lead":
        mark_context_fresh(event, "session-start:" + (source or "unknown"))
    # COMPACT IS NOT A NEW SESSION. Claude Code fires SessionStart with
    # source=compact on every compaction, on TOP of the PostCompact hook, and
    # this handler used to ignore the source entirely: a session working on something else got "READ ALL OF THEM before acting" pointed at the standing program docs, mid-task, as if it had just started. It is also a straight duplicate -- handle_post_compact already re-points at DESIGN_DOCS and already hands back the durable plans, plus STATE.md, RULES.md and the trap titles, which
    # is the briefing a compacted session actually needs. So compaction is handled in exactly one place: mark the context fresh (the judge stamp depends on it) and say nothing here.
    if source == "compact":
        return
    # TWO INDEPENDENT BLOCKS, and the structure is the point. This used to RETURN EARLY when the design-docs directory was absent, which meant a project keeping plans but no docs/ci-overhaul got nothing at all: the plans block would have been eaten by a check about a different thing. Each block is built on its own and the hook emits when EITHER has something to say.
    root = C.project_root(C.project_start(event))
    docs = pathlib.Path(root) / DESIGN_DOCS
    blocks, summary = [], []
    if docs.is_dir():
        files = sorted(f for f in docs.iterdir() if f.is_file() and f.suffix == ".md")
        listing = "\n".join(
            "  %s (%d lines)"
            % (f.relative_to(root), len(f.read_text(errors="replace").splitlines()))
            for f in files
        )
        state, drift, _ = docs_drift(root)
        stale = (
            ""
            if state != "drifted"
            else M.CTX_SESSION_START_STALE % (drift, " ".join(PROGRAM_SURFACE))
        )
        blocks.append(
            M.CTX_SESSION_START % (" ".join(PROGRAM_SURFACE), DESIGN_DOCS, listing, stale)
        )
        # "pending" is NOT silence: the docs were updated but the edit is uncommitted, so a fresh session must be told a commit is owed rather than inferring from a clean line that nothing is outstanding.
        if state == "drifted":
            note = " (DRIFTED by %d commits)" % drift
        elif state == "pending":
            note = (
                " (updated but UNCOMMITTED; %d commits of drift are covered by that edit)" % drift
            )
        else:
            note = ""
        summary.append("%d standing program doc(s) in %s%s" % (len(files), DESIGN_DOCS, note))
    listing, live = plans_block(root)
    if listing:
        blocks.append(M.CTX_PLANS % listing)
        summary.append("%d open plan(s) in agent/" % len(live))
    # A THIRD independent block, for the reason the two above are independent: a repo with live handoff checklists and no design docs and no plans must still be told about the checklists, because the Stop hook will block on them and a session that has never heard of them cannot act.
    cl_listing, cl_n = wl_checklist.checklists_block(root)
    if cl_listing:
        blocks.append(M.CTX_CHECKLISTS % cl_listing)
        summary.append("%d live handoff checklist(s)" % cl_n)
    if not blocks:
        return
    C.emit(
        {
            "systemMessage": "SessionStart: " + ", ".join(summary),
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n\n".join(blocks),
            },
        }
    )


def _compaction_owner(event, sid):
    """ "lead", "agent:<id>" or "unknown" for this PostCompact (R20260924.16). An `agent_id` in the payload settles it; the measured sub-agent payload carries none, so otherwise the transcripts decide (ctx_budget.compaction_owner). Any failure is "unknown", which acts like a sub-agent: no retro order, no ctx_fresh."""
    if event.get("agent_id"):
        return "agent:%s" % event.get("agent_id")
    try:
        import wl_retro as _RT  # noqa: PLC0415 -- optional; the briefing must not need it

        return _RT.ctx().compaction_owner(event.get("transcript_path"), sid)
    except Exception:  # noqa: BLE001 -- attribution must never cost the briefing
        return "unknown"


def handle_post_compact(event):
    sid = event.get("session_id", "")
    # WHOSE COMPACTION, before anything acts on it. A sub-agent's PostCompact arrives with the lead's session_id and transcript_path and no agent_id (measured 2026-09-24T19:01:44Z), so without this check it stamped the lead's ctx_fresh and took the lead's one post-compact retro.
    owner = _compaction_owner(event, sid)
    # FIRST action for the lead, for the same reason as handle_session_start, and this is the case the marker is genuinely load-bearing for: a compacted session KEEPS its state doc, so the judge-reason signature below would otherwise read as unchanged and hand it the stamp alone.
    if owner == "lead":
        mark_context_fresh(event, "post-compact")
    # PostCompact hook: the model has just lost its context. Hand the documents straight back as additionalContext so continuity does not depend on it remembering to go looking. Since the agent-notes split this returns MORE than the old handover ever could: STATE.md in full, RULES.md in full, and the TRAPS.md titles -- the first time a compacted session gets the standing rules at
    # all, delivered exactly once per
    # compaction. Full TRAPS.md is deliberately excluded (designed to grow);
    # titles plus the path is the same economy the judge uses.
    root = C.project_root(C.project_start(event))
    # THE PROMPT CARRIES RESIDUE, NOT TITLES. A trap whose Enforced-By resolves to a live gate or hook is enforced whether or not anyone reads about it, so spending prompt on its title buys nothing; a JUDGMENT-ONLY trap is enforced by attention alone, which is exactly what a prompt can supply. 48 titles -> 43 residue sentences today, and the ratio improves every time a trap gets
    # mechanized, which is the incentive worth creating.
    traps = S.trap_prompt_lines(root)
    traps_block = "\n".join("  - " + h for h in traps) or "  (none recorded)"
    # Bound before the arms so the agent-hint haystack below has one shape on both of them; only the arm that reads a section fills it. There is no third, no-branch arm any more (2026-08-18): the document is keyed on the session, so a detached HEAD can no longer cost a compacted session its briefing -- which was the worst possible moment to withhold it.
    text = ""
    # shape + presence only, but for THIS session's own section.
    state, _age, text = S.agent_state_state(root, session_id=sid)
    _, peers, _npeers = S.agent_state_briefing(root, sid, C.projects_dir(root))
    if state in ("missing", "no-dir"):
        msg = M.CTX_POSTCOMPACT_MISSING % (
            S.agent_state_path(root, sid),
            (sid or "unknown")[:8],
        )
    else:
        try:
            rules = (
                S.agent_rules_path(root, sid).read_text(encoding="utf-8", errors="replace").strip()
            )
        except OSError:
            rules = "(none)"
        msg = M.CTX_POSTCOMPACT_BRIEFING % (
            DESIGN_DOCS,
            text.strip(),
            rules,
            S.agent_traps_path(root),
            traps_block,
        )
    # THE COMPUTED FACTS, beside the body (P1.2): what the hook itself reads right now -- branch, HEAD and this session's own guide slice -- so STATE.md only has to carry judgment. Facts a document restates go stale; facts rendered at read time cannot.
    with contextlib.suppress(Exception):
        _fold = S.load(C.worklist_for(C.project_start(event)), sync=False)
        msg += "\n\n" + M.CTX_POSTCOMPACT_FACTS % (
            C.git_branch(root) or "(detached)",
            C._git(root, "rev-parse", "--short", "HEAD") or "?",
            guided_slice(_fold, sid, None, (sid or "")[:8], root)
            or "  (nothing open, in flight or deferred)",
        )
        # FOCUS MODE survives compaction in the store; the compacted session must know that writer spawns are refused.
        _pc_focus = wl_standdown.active_focus(_fold.focus, lambda o: C.owned_by_me(o, sid))
        if _pc_focus:
            msg += "\n\n" + M.CTX_POSTCOMPACT_FOCUS % (
                _pc_focus.get("mode"),
                _pc_focus.get("pr") or "?",
                _pc_focus.get("branch"),
                _pc_focus.get("at"),
                _pc_focus.get("pr") or "<n>",
                (sid or "")[:8],
            )
    # AFTER the briefing, on BOTH arms. Own section first is the point: a compacted session reads top-down, and the block it must act on is its own. On the missing arm this is the whole state content there is -- before sections, that arm returned none at all, so a compacted session sharing a checkout was told to reconstruct from nothing while a peer's section sat in the file
    # unread.
    if peers:
        msg += "\n\n" + M.CTX_POSTCOMPACT_PEERS % peers
    # v16: the durable half of the briefing, appended to BOTH arms above. STATE.md says what is true right now and can be missing or stale; a plan file says what was DESIGNED and is committed, so it is the one artifact a compacted session can always fall back on. The newest non-done plan's '## Status' section rides along, capped, because that section is exactly the progress cursor
    # the lost context held.
    listing, live = plans_block(root)
    if listing:
        msg += "\n\n" + M.CTX_PLANS % listing
        rel, body = plan_status_excerpt(root, live)
        if body:
            msg += "\n\n" + M.CTX_PLANS_EXCERPT % (rel, body)
    # v20: and the handoff checklists, appended on both arms above
    # for the same reason. A compacted session that forgets a live checklist
    # rediscovers it as a block it cannot explain.
    cl_listing, _cl_n = wl_checklist.checklists_block(root)
    if cl_listing:
        msg += "\n\n" + M.CTX_CHECKLISTS % cl_listing
    # THE STOP-HOOK RETRO (agent/plans/PLAN-stop-hook-retro-20260924.md R20260924.12), after the briefing, the facts and the plans, once per session: the `ordered` row in agent/ledgers/stop-hook-retros.jsonl is the dedupe record. Ordered ONLY when the lead itself compacted (R20260924.16): a sub-agent's or an unattributable compaction orders nothing, and the briefing itself is emitted either way.
    # Suppressed like the hint below, because a compaction that cannot hand back the briefing is far worse than a missing retro order.
    with contextlib.suppress(Exception):
        if sid and owner == "lead":
            import wl_retro as _RT  # noqa: PLC0415 -- optional; the briefing must not need it

            _ctxb = _RT.ctx()
            _me8 = _ctxb.session_slug(sid)
            if _ctxb.retro_ordered(_ctxb.retro_rows(root), _me8, "post-compact") is None:
                _sp = S.agent_state_path(root, sid)
                _row = _ctxb.retro_order_row(
                    root,
                    _me8,
                    "post-compact",
                    event.get("transcript_path"),
                    state_md_at=_ctxb.utc_stamp(_sp.stat().st_mtime) if _sp.is_file() else "",
                )
                msg += "\n\n" + M.CTX_POSTCOMPACT_RETRO % {
                    "transcript": _row["transcript"] or "(no transcript_path in the event)",
                    "when": M.CTX_POSTCOMPACT_RETRO_WHEN_MISSING
                    if state in ("missing", "no-dir")
                    else M.CTX_POSTCOMPACT_RETRO_WHEN_BRIEFED,
                    "me8": _me8,
                    "date": _RT.today(),
                    "from": _row["from_off"],
                    "to": _row["to_off"],
                }
    # v21: the specialist-agent hint, and this is the highest-value delivery it has. Post-compaction is precisely when a session has forgotten that a specialist exists, and additionalContext is read rather than skimmed. ONCE PER COMPACTION BY CONSTRUCTION, so it needs no rate limiting and no ledger; the haystack is the document the session just got back plus its own open items.
    # Suppressed rather than guarded, because a compaction that cannot hand back the briefing is a far worse outcome than a missing hint.
    with contextlib.suppress(Exception):
        if A.ENABLED:
            items = []
            with contextlib.suppress(Exception):
                wl = C.worklist_for(C.project_start(event))
                items = S.classify_items(S.load(wl, sync=False), sid)[0]
            hit, _errs = A.hint_for(text + "\n" + "\n".join(items))
            if hit:
                msg += "\n\n" + M.N_AGENT_HINT % (hit[0], hit[0], ", ".join(hit[2][:6]))
    # W12 P2.3. A compaction has just thrown away whatever this session knew about WHY the files it has in flight are the shape they are; those files have not changed. So the compacted plan records that name them go into the same briefing, from the working tree's own dirty list.
    #
    # ADDS NOTHING WHEN NOTHING MATCHES -- `why_for_paths` returns "" -- and never raises: this is one append to a briefing that must be emitted either way.
    with contextlib.suppress(Exception):
        import wl_planrec as _R  # noqa: PLC0415 -- optional; the briefing must not need it

        _why = _R.why_for_paths(root, sorted(_R.dirty_paths(root, "."))[:60])
        if _why:
            msg += "\n\n" + _why
    # The Decision on a sub-agent's briefing: keep all of it, and say first whose compaction it was, since the STATE.md above is the lead's.
    if owner.startswith("agent:"):
        msg = M.CTX_POSTCOMPACT_SUBAGENT % owner[len("agent:") :] + "\n\n" + msg
    C.emit(
        {
            "systemMessage": "PostCompact: STATE.md %s (agent/%s/STATE.md)"
            % (state, S.agent_session_slug(sid)),
            "hookSpecificOutput": {
                "hookEventName": "PostCompact",
                "additionalContext": msg,
            },
        }
    )


PHANTOM_MIN = float(os.environ.get("WORKLIST_PHANTOM_MIN", "30"))
# Writers in the event log that are not identities at all. `compact` is stamped by S.compact when it rewrites history; the others are the store's own fallbacks. Naming them here beats inferring intent from shape.
PHANTOM_NOT_IDENTITIES = frozenset({"compact", "unknown", "md"})


def phantom_identities(worklist, session_id, fold):
    """([(prefix, events, age_min, owns)], blind_reason) for identities that WRITE to this store but have never stopped.

    THE BACKSTOP for what the CLI check cannot reach: history already written, and the deliberate hole where the environment cannot name the caller. Both are real -- the incident put 240 events into the live store under an identity that never existed, and a plain operator terminal has no session id to check against.

    THE SIGNATURE IS EXACT AND BINARY. `<worklist>.lastevent-<prefix>.json` is written at exactly ONE place, inside run_stop below; worklist.py's --lease and --reap only READ it. So an identity with no `.lastevent-` file is one
    for which a Stop hook has NEVER RUN, and a real session always stops. The
    byte-size asymmetry on `.state-` (the CLI writes only state_sig, the hook writes the whole document) says the same thing less reliably; this is the better test.

    FOUR GATES, and each one is a false positive that was measured in the live store rather than imagined:
      1. not me                -- obviously
      2. no `.lastevent-`      -- the signature above
      3. older than PHANTOM_MIN -- a brand-new session writes before its first
         stop, and that window is not a phantom
      4. owns OPEN work        -- `state-spotchk1`, `state-spotchk2` and a
         session that died before its first stop all sit in the live store with
         no `.lastevent-`. A phantom that owns nothing is not worth a word.

    THE INSTRUMENT CONTROL IS INSIDE THE CHECK. If the store holds ZERO `.lastevent-*` files the test is blind -- a wiped TMPDIR, a fresh worktree -- and it would otherwise indict every identity at once. It reports the BLINDNESS in words and flags nobody. A check that cannot fail must say so.
    """
    try:
        seen = list(worklist.parent.glob(worklist.stem + ".lastevent-*.json"))
    except OSError:
        return [], ""
    if not seen:
        return [], (
            "no .lastevent-*.json exists in %s, so the phantom-identity check "
            "is BLIND this stop (it recognises a phantom by the ABSENCE of one, "
            "and with none present every identity would look like one). Nothing "
            "is being flagged. A wiped TMPDIR is the usual cause." % worklist.parent
        )
    stopped = {p.name.split(".lastevent-")[-1][:-5] for p in seen}
    # THE WHOLE STORE, not the legacy file, and BOTH the writer and the owner of each event. Reading one path here would have made every identity in the tracked store invisible; reading `by` alone made every identity invisible after a COMPACTION, which rewrites the writer of the entire history to "compact" while preserving the owner. The derivation now lives in
    # wl_store.identity_activity, shared with --reassign's age gate, because two different answers to "is this identity a phantom" is how the backstop and its repair verb drifted apart in the first place -- the backstop saw nobody to report while --reassign refused the very items it was pointed at as "has written no events at all".
    _act = S.identity_activity(worklist)
    counts = {k: n for k, (n, _) in _act.items()}
    first_at = {k: at for k, (_, at) in _act.items()}
    out = []
    for by, n in sorted(counts.items()):
        if C.same_session(by, session_id) or by[:8] in stopped:
            continue
        age = C.stamp_age_min(first_at.get(by, ""))
        if age is None or age < PHANTOM_MIN:
            continue
        owns = []
        n_items = sum(
            1
            for rec in fold.items
            if rec["state"] in (" ", "?", ">")
            and rec["owner"] is not None
            and C.same_session(rec["owner"], by)
        )
        if n_items:
            owns.append("%d open item(s)" % n_items)
        if not owns:
            continue
        out.append((by, n, age, " and ".join(owns)))
    return out, ""


# ---- the Stop battery -------------------------------------------------------


def _agent_state_because(astate, aage):
    """The parenthetical after the STATE.md verdict: WHY, not just how old.

    It used to print "(%d min old, limit %d)" for every verdict, and that single string is why a session read the check as pure wall-clock and concluded the code disagreed with its own documentation (plan section 1.4). Two separate lies were in it:

      - For `stale` the age is a SYMPTOM, not the cause. The trigger is the
        world signature moving; a document a week old whose world never moved is
        never stale. Leading with minutes invites the reader to "fix" it by
        rewriting the same content, which changes nothing.
      - For `thin`, `bloated` and `aimless` the age is irrelevant ENTIRELY.
        Those are shape verdicts about the body. Printing a staleness limit
        beside them suggests waiting or re-stamping would help; nothing about
        the clock does.

    Age survives only for `stale`, and only as trailing context after the cause.
    """
    if astate == "stale":
        base = "; your world signature moved since it was written"
        return " (%s)" % base.lstrip("; ") if aage is None else " (%d min old%s)" % (aage, base)
    if astate == "waitled":
        # Also age-irrelevant, and the cause has to be stated or the reader rewrites the same ordering: the document leads its '## Next action'
        # with a wait, which hands the next session "sit and watch" as its
        # instruction and survives compaction to say it again.
        return (
            " (its '## Next action' LEADS with a wait; a watch is a condition,"
            " not the next action -- put the real work first)"
        )

    return ""


# ---- v22: THE SOLO GRIND ADVISORY ------------------------------------------- WHY (operator, 2026-08-19): "we're on an inefficient way for the remaining items! Normally, for each wave we should use sub-agents that way we can go in parallel and save context for the current session."
#
# The session it was said to had ~39 open items and was working them ONE AT A TIME in its own context, with zero writer teammates, on waves whose file sets were naturally disjoint. Nothing was wrong with any single decision; the failure was only visible in aggregate, which is exactly the shape a human notices and a per-stop check does not.
#
# ADVISORY, never blocking, and the asymmetry is deliberate. The DETECTABLE half is a fact: this many open items, this many live teammates. The half that decides whether delegation is right is a JUDGEMENT the hook cannot make -- items can be strictly sequential (the i18n cascade is), interdependent, or too small to be worth a brief. Blocking on a fact that only sometimes implies
# the remedy would teach sessions to route around it, and a session that spawns two agents onto serial work has been made worse, not better.
#
# ONCE PER EPISODE, not once per stop. It re-arms only after the queue drops back under the floor, so a long wave is asked once rather than nagged for hours -- the same reason the no-op ladder needs a streak before it speaks.
SOLO_GRIND_MIN_ITEMS = int(os.environ.get("WORKLIST_SOLO_MIN", "12"))

# How long a teammate's unread report may sit before it stops being news and becomes a debt. The first rung matches BG_REPORT_MIN's 15 minutes -- the interval this file already treats as "long enough that a session should have noticed" -- and the second is three of those.
UNREAD_ROTATE_MIN = float(os.environ.get("WORKLIST_UNREAD_ROTATE_MIN", "15"))
UNREAD_INVARIANT_MIN = float(os.environ.get("WORKLIST_UNREAD_INVARIANT_MIN", "45"))


def _prf_covered(fold, token):
    """Is a pr-babysit finish-line box TICKED?

    True only for a store record that carries the linkage token AND is closed (`x`). An OPEN item carrying it is the session having claimed the box, not having done it -- and that open item blocks on its own, in the same mission tier, so nothing is lost by refusing to count it here.

    Word-bounded and literal-escaped, exactly as wl_checklist._covering_items is, so `pr:5/reviewed` never matches `pr:53/reviewed`.
    """
    rx = re.compile(r"\b%s\b" % re.escape(token))
    return any(
        rec.get("state") == "x" and rx.search(rec.get("line") or rec.get("text") or "")
        for rec in (getattr(fold, "items", None) or [])
    )


def solo_grind_due(n_open, n_teammates, state_doc):
    """True when a long solo queue deserves ONE mention. Mutates state_doc.

    Returns False the moment any teammate is live: the session has already made the call, and repeating the advice at that point is noise.
    """
    # int() at the boundary, NOT a bare comparison. live_teammate_transcripts returns None when it has no view to report, and a try/except around the CALL does not catch a bad RETURN: the first suite run after this landed crashed the whole hook with "'>' not supported between instances of 'NoneType' and 'int'". A fact-gatherer that cannot answer must read as "no teammates seen",
    # which is the conservative direction here (it lets the advisory speak) rather than silently suppressing it.
    n_teammates = int(n_teammates or 0)
    n_open = int(n_open or 0)
    if n_open < SOLO_GRIND_MIN_ITEMS or n_teammates > 0:
        # Episode over. Re-arm so a queue that grows again is asked again.
        state_doc.pop("solognd", None)
        return False
    # THE STAMP IS NO LONGER WRITTEN HERE. It is registered as a display-time latch by the caller (see spend_display_latches in run_stop): this function runs on every stop, and writing `solognd` from it burned the one mention this advisory ever gets on stops that never rendered it. The DISARM above stays at compute time -- it is not a suppression, it is the episode genuinely being
    # over.
    return not state_doc.get("solognd")


# ---- CADENCE (operator-approved 2026-08-15, PLAN-stop-hook-cadence.md sec 3) -- The operator's ask: "1 report/update 1 others/order flow" -- the hook should not demand on every single stop, because a context that is never allowed to finish a thought reports worse, not better.
#
# THE ACCEPTANCE TEST, and it is the plan's own sentence: the cadence must make it easier to be HEARD, not easier to STOP. Every guard below exists because the obvious implementation fails that test.
CADENCE_MAX_PAUSES = int(os.environ.get("WORKLIST_CADENCE_MAX", "3"))

# Guard C. These block on the hook's OWN failure to get an honest verdict, or on the evidence discipline that keeps the ledger from becoming a lie. Pausing any of them would let a session stop by simply saying something new, which is the precise regression the cadence must not become.
JUDGE_TIER_KEYS = frozenset(
    {"unjustified", "defer-expired", "completion", "undefaulted", "no-remaining"}
)


# --------------------------------------------------------------------------- v21: THE PRIORITY LADDER (operator, 2026-08-28: "Stop hook should have a list
# for prioritization items to pick for each case. There should be list of 'has
# to show with this order' until we check all of them, we should not be able to say 'but this stop is YOURS'.")
#
# WHAT WAS WRONG. Rotation was LRU over check keys with the BATTERY'S LINE ORDER as the tiebreak, and every never-served key ties at -1, so the first stop of a crowded session picked whichever check happened to be written earliest in this file. Measured on the failing night: 23 rotating keys sorted ahead of an owed check, so it could not
# be reached until the twenty-fourth stop -- while its escalation ladder burned a rung per stop, unseen. Line order is a shape of the source file. It is not a statement about which unfinished thing matters most, and it was being read as one.
#
# THE LADDER IS THE STATEMENT, made explicit and orderable. Four tiers, and the order is an argument about WHO IS STUCK, not about how alarming a message is:
#
# T_MISSION (0) The thing this session was ASKED to do is not done. Read off markdown checkboxes that already exist -- the worklist's `- [ ]` items, agent/programs/<slug>/CHECKLIST.md's deliverable and wave boxes, and the pr-babysit finish line. Nothing else can matter more, because everything else is housekeeping around work that has not landed. This is the operator's own example:
# "if there is an open-pr and if it's red we must continue to work until making it green."
#
# T_OWED (1) Somebody ELSE is blocked, and cannot see that this session stood down. A teammate's finished report, a worker owing
#                   its status, a background job whose check-in is due.
# Above integrity because a stalled worker is stalled work, and hook blindness only costs this one.
#
# T_INTEGRITY (2) A gate, the hook, or the evidence ledger cannot SEE. Its silence is not evidence, so nothing below it can be trusted
#                   while it is outstanding.
#
# T_HYGIENE (3) Everything else: STATE.md, the brief, docs drift, a submodule pointer, a stale PR body. Real, and last. This is the DEFAULT, so a new check is hygiene until somebody argues it up -- which is the safe direction for a ladder whose top tier can never be rotated away.
#
# T_MISSION ALSO DEFEATS THE CADENCE PAUSE. That is the operator's sentence rendered as code: the "but this stop is YOURS" stand-down may spend the DEMAND, but never while the asked-for work is still unfinished.
#
# MATCHING IS BY EXACT KEY OR BY `prefix:` -- several checks are scoped per subject (`cl-producing:<slug>`, `agent-pushback:<agent>`), and a ladder that only understood whole keys would silently drop every one of them to hygiene.
T_MISSION, T_OWED, T_INTEGRITY, T_HYGIENE = 0, 1, 2, 3

PRIORITY_LADDER = (
    (
        T_MISSION,
        frozenset(
            {
                # The worklist's own `- [ ]` boxes, and the two states that turn a parked box back into an order.
                "open-items",
                # In focus mode, the open items carrying the focus PR's `pr:<n>`: the babysit loop's own fix work (wl_standdown).
                "focus-pr-items",
                # A plan this session ADOPTED (its Owner line says so) with boxes nothing tracks: the adoption is the statement that it is being executed.
                "plan-adopted",
                # The same question widened from "adopted" to ALL, per the operator's own ruling, and bounded by a descending ceiling rather than by a fire cap. T_MISSION is the ladder's own argument rather than a promotion: "the thing this session was ASKED to do is not done ... everything else is housekeeping around work that has not landed". See wl_planenforce.
                "plan-unimplemented",
                "defer-expired",
                "undefaulted",
                # agent/programs/<slug>/CHECKLIST.md -- deliverable and wave boxes, same four-state markdown the worklist uses.
                "cl-producing",
                "cl-flip",
                "cl-waves",
                # The pr-babysit finish line, box by box (green / ready / reviewed / threads), and the red that keeps it unticked.
                "pr-finish",
                "ci-red",
                # Not a genuine CI failure (CI_NONBLOCKING_CONTEXTS keeps it out of "ci-red" on purpose) but the local session has context a remote job does not, so it joins ci-red's tier rather than sitting in hygiene where it could be starved by real work.
                "review-red",
            }
        ),
    ),
    (
        T_OWED,
        frozenset(
            {
                "bg-report",
                "unread-reports",
                "agent-pushback",
                "giveup-claim",
                # NB `ladder-ping` is an outq advisory, not a vadd key, so it is deliberately absent: test-always-tier.py fails on a ladder entry that no check can ever produce.
                "ladder-investigate",
                "ladder-gone",
                "ladder-idle",
                "ladder-resolve",
                "unconfirmed",
                # The parallel-writer roster (wl_roster), placed here by the operator's own order: a writer over the cap, a worker owing its 20-minute status, and a worker gone silent are supervision owed while other agents edit the tree.
                "roster-cap",
                "roster-silent",
            }
        ),
    ),
    (
        T_INTEGRITY,
        frozenset(
            {
                "hook-blind",
                "event-unparseable",
                "adhoc-watch",
                "adhoc-watch-broken",
                "ci-unreadable",
                "ci-waiting",
                "review-unreadable",
                "pr-unreadable",
                "cl-shape",
                "plan-fidelity",
                "agent-bootstrap",
                "pending-ask",
                "stuck",
                "idle-stall",
                "unblocked-claim",
                "completion",
                "unjustified",
                "uncited",
                "unstated",
                "mislabelled",
                "out-of-sync",
                "loop-died",
                "broken-schedule",
                "many-work-crons",
                # The roster's integrity half: a live writer nothing leases, and a lease on a worker with no live agent in its lineage. Both are claims about in-flight work that the store and the harness contradict.
                "roster-unleased",
                "roster-dead",
                # Queued writer work with a writer slot free (agent/plans/PLAN-stop-hook-retro-20260924.md R.5): split out of roster-dead, because a queue is not a finished worker.
                "queue-slot",
            }
        ),
    ),
)

# The invariant (`always=True`) tier is deliberately SCARCE -- this file's own
# warning, at the sweep prompt below, is that "a prompt that fires always is a prompt that gets skimmed". So on a stop where several invariants are outstanding, at most this many are QUOTED IN FULL; the rest are NAMED, one line each, with their opening line. Nothing is dropped, and the count in the header stays truthful either way.
ALWAYS_FULL_MAX = int(os.environ.get("WORKLIST_ALWAYS_FULL_MAX", "2"))


def check_tier(key):
    """Where a violation key sits on the priority ladder. Unknown keys are HYGIENE, which is the safe default: a new check has to be argued upward rather than inheriting a promotion it never asked for."""
    head = str(key).split(":", 1)[0]
    for tier, keys in PRIORITY_LADDER:
        if key in keys or head in keys:
            return tier
    return T_HYGIENE


def planfid_check(worklist, session_id, event, fold, lines, me8, last_msg, vadd):
    """v20 PLAN FIDELITY (see wl_planfid.py). Returns a degraded-note string.

    Appends at most ONE violation, keyed 'plan-fidelity', in the ALWAYS tier.

    IT LIVES INSIDE THE BATTERY, not after it, and that placement is the whole reason it can see anything. The state it detects -- an approved plan tracked as two umbrella items -- ALWAYS coexists with open items, and open items make the battery emit long before the admission detector or the judge is reached. A plan-fidelity check placed beside those two would have run only on a
    clean board, which is precisely the board this defect never produces. Measured against the 2026-08-19 incident: the session held two open items for the whole episode, so a post-battery check would have fired zero times.

    ALWAYS tier, because its text costs a model call to compute. Rotating it away would spend the call and swallow the answer, which is the same argument the tier comment above makes for latched one-shots.

    Every failure DEGRADES to a queued note rather than blocking. See wl_planfid's header for why this one does not share wl_judge's no-escape-hatch contract.
    """
    sp = wl_planfid.state_path(worklist, session_id)
    state, forgot = wl_planfid.load_state(sp)
    # ONE line, never silence, on every path out of here -- the same fail-safe contract wl_reggate states for its own marker. The first draft returned it only from the blocking branch, which meant a corrupt marker on a stop with no plan (the common shape) forgot every settled verdict and said nothing.
    lost = " [plan-fidelity marker was corrupt; settled verdicts forgotten]" if forgot else ""
    plan_path, scanned = wl_planfid.scan_plan_exit(
        event.get("transcript_path", ""), int(state.get("scanned") or 0)
    )
    if plan_path:
        state["plan"] = plan_path
    state["scanned"] = max(int(scanned or 0), 0)
    plan_text = wl_planfid.read_plan(state.get("plan") or "")
    if not plan_text:
        # No approved plan in this session, which is the common case and must stay free: no model call, no note, no violation.
        wl_planfid.save_state(sp, state)
        return lost
    tasks = wl_planfid.plan_tasks(plan_text)
    mine = [
        (r["id"], r["state"], S.brief_text(r, cap=220))
        for r in fold.items
        if C.owned_by_me(r.get("owner"), session_id)
    ]
    sig = wl_planfid.plan_sig(state["plan"], plan_text)
    if wl_planfid.is_settled(state, sig, len(mine)):
        wl_planfid.save_state(sp, state)
        return lost
    hits = wl_planfid.prefilter(tasks, mine)
    if not hits:
        wl_planfid.save_state(sp, state)
        return lost
    pf, err = wl_judge.run_planfid(plan_text, wl_planfid.render_items(mine), last_msg or "")
    wl_planfid.save_state(sp, state)
    signals = sorted({k for k, _d in hits})
    if err:
        wl_planfid.record_verdict(
            worklist, session_id, sig, "error", signals, len(tasks), len(mine), err[:160]
        )
        return (M.V_PLANFID_DEGRADED % err[:160]) + lost
    kind, payload, detail = wl_planfid.apply_planfid_verdict(
        pf, plan_text, mine, sig, lines, me8, C.ITEM
    )
    # ONE call site for every non-error outcome, placed BEFORE the branching so a branch added later cannot be added without passing through it. The settle verdicts carry their own name (`faithful` / `deferred` / `unevidenced`), which is the distinction the whole log exists to count.
    wl_planfid.record_verdict(
        worklist,
        session_id,
        sig,
        payload if kind == "settle" else kind,
        signals,
        len(tasks),
        len(mine),
        detail[:160] if isinstance(detail, str) else "",
        extra=None
        if kind != "block"
        else {"n_umbrella": len(payload["umbrella"]), "n_missing": len(payload["missing"])},
    )
    if kind == "malformed":
        return (M.V_PLANFID_DEGRADED % ("the judge returned %s" % payload)[:160]) + lost
    if kind == "settle":
        # STICKY by plan signature, never by item set: a settled plan is not re-asked, and editing the plan reopens the question. Keying on the items instead would re-pay the call on every item a correct decomposition adds.
        state.setdefault("settled", {})[sig] = {
            "verdict": payload,
            # Only meaningful for `unevidenced`; see wl_planfid.is_settled for why that verdict expires when the worklist grows and the other two do not.
            "items": len(mine),
            "detail": detail[:200],
            "at": C.stamp_now(),
        }
        wl_planfid.save_state(sp, state)
        return lost
    vadd(
        "plan-fidelity",
        True,
        M.V_PLANFID
        % (
            state["plan"],
            "\n".join("    #%s %s" % (i, t) for i, t in payload["umbrella"]) or "    (none named)",
            "\n".join("    - %s" % m for m in payload["missing"]) or "    (none named)",
            payload["instruction"] or "decompose the plan into one item per task",
            me8,
            me8,
            payload["token"],
        ),
    )
    return lost


def _resprofile_report(worklist, session_id, state_doc):
    """Report-only structural findings from the previous CI run's captures, and the tier-0 -> tier-1 fold. NEVER blocks: the judge gates an exit so "cannot decide" must not be an escape, but this describes how work was done, so "we did not measure" must never become "the stop is refused". Every failure is swallowed; the off switch is
    WORKLIST_PROFILE=off. See agent/plans/PLAN-shell-resource-profiling.md section 3."""
    if os.environ.get("WORKLIST_PROFILE") == "off":
        return
    with contextlib.suppress(Exception):
        import wl_resprofile  # noqa: PLC0415

        wl_resprofile.fold()
    with contextlib.suppress(Exception):
        import wl_profile  # noqa: PLC0415

        root = C.project_root(C.project_start())
        cdir = pathlib.Path(root) / ".ci" / "cache" / "profiles.prev"
        if not cdir.is_dir():
            return
        caps = [c for c in (wl_profile.load_capture(x) for x in sorted(cdir.glob("*.jsonl"))) if c]
        j = sum(c.judgeable for c in caps)
        if not caps or j < 0.5 * len(caps):
            return  # unjudgeable is silence, never a verdict
        findings = wl_profile.derive(caps)
        if not findings:
            return
        lines = ["%s  %s" % (f["class"], f["why"]) for f in findings[:8]]
        outq_add(
            worklist,
            session_id,
            state_doc,
            "resprofile",
            "RESOURCE PROFILE (report-only, %d judgeable capture(s) from the last `npm run ci`):\n  "
            % j
            + "\n  ".join(lines)
            + "\n  Verdicts live in check:ci-resprofile; nothing here blocks.",
            3,
        )


def _ctx_late_band(session_id):
    """True when this session's context sits in the LATE band (~2% before auto-compact, ctx_budget.BANDS).

    The cap-saturated wait keeps the STATE.md demand only then: the recovery document must be current before the context is summarised. Unknown (no context module, as in an LKG snapshot, or no band state yet) is False; the PreCompact snapshot covers that case.
    """
    try:
        import wl_retro  # noqa: PLC0415 -- the context module is loaded by path, lazily

        cb = wl_retro.ctx()
        band = int(cb.load_state(session_id).get("band", -1))
        names = [b[0] for b in cb.BANDS]
        return band >= names.index("late")
    except Exception:  # noqa: BLE001 -- a fact-gatherer must never wedge a stop
        return False


def _focus_refused_count(worklist, me8, since):
    """Writer spawns block_focus_spawn refused since `since`, from its `.focusrefused-<me8>.jsonl` ledger."""
    n = 0
    with contextlib.suppress(OSError):
        for line in (
            worklist.with_suffix(".focusrefused-%s.jsonl" % me8)
            .read_text(encoding="utf-8")
            .splitlines()
        ):
            with contextlib.suppress(ValueError, AttributeError):
                if str(json.loads(line).get("at") or "") >= str(since or ""):
                    n += 1
    return n


def focus_ended_line(sd, why, refused):
    """The one-line parked summary (M.N_FOCUS_ENDED): top 6 parked keys by stops parked, then "+N more", capped at 300 characters."""
    parked = sd.get("parked") if isinstance(sd.get("parked"), dict) else {}
    ranked = sorted(parked.items(), key=lambda kv: (-int(kv[1] or 0), kv[0]))
    names = ", ".join("%s x%d" % (k, int(n or 0)) for k, n in ranked[:6]) or "nothing"
    if len(ranked) > 6:
        names += " +%d more" % (len(ranked) - 6)
    what = "%s PR #%s since %s" % (sd.get("mode") or "?", sd.get("pr") or "?", sd.get("focus_at"))
    return (M.N_FOCUS_ENDED % (why, what, names, int(sd.get("adv_held") or 0), refused))[:300]


def focus_advisory_filter(focus, state_doc):
    """The `only=` predicate for this stop's advisory release: None (everything) outside focus or when the batch is due, else the PR's own advisory keys."""
    if not focus or wl_standdown.batch_due(state_doc.get("standdown")):
        return None
    return wl_standdown.advisory_kept


def focus_advisory_bookkeeping(worklist, session_id, focus, state_doc):
    """After a focused release: restamp `batch_at` when the batch was due, and count what is still held. Persists."""
    sd = state_doc.get("standdown")
    if not focus or not isinstance(sd, dict):
        return
    if wl_standdown.batch_due(sd):
        sd["batch_at"] = C.stamp_now()
    sd["adv_held"] = sum(
        1 for e in _outq(state_doc)["items"] if not wl_standdown.advisory_kept(_outq_display_key(e))
    )
    S.save_state(worklist, session_id, state_doc)


def focus_resolve(root, worklist, session_id, me8, fold, state_doc):
    """(focus, ended): this stop's active focus event or None, and the parked summary line or "".

    Ends an expired or finished focus, and queues the summary when a focus that was on at the last stop is not the one on now. The summary is a priority-0 sticky entry, so the allow drain delivers it; the block path appends it in full and forgets the entry, because a block's digest shows only 150 characters of it.
    """
    owned = lambda o: C.owned_by_me(o, session_id)  # noqa: E731
    focus = None
    why = ""
    with contextlib.suppress(Exception):
        focus = wl_standdown.active_focus(fold.focus, owned)
    if focus:
        if wl_standdown.expired(focus):
            why = "expired"
        else:
            try:
                why, err = wl_ci.focus_pr_end(root, worklist, session_id, focus)
            except Exception as exc:  # noqa: BLE001 -- a blind read continues focus, and says so
                why, err = "", "%s: %s" % (type(exc).__name__, str(exc)[:120])
            if err:
                outq_add(
                    worklist,
                    session_id,
                    state_doc,
                    "focus-pr-unreadable",
                    M.N_FOCUS_PR_UNREADABLE
                    % (
                        focus.get("pr") or "?",
                        focus.get("branch"),
                        str(err)[:120],
                        wl_standdown.FOCUS_MAX_HOURS,
                    ),
                    1,
                )
        if why:
            with contextlib.suppress(Exception):
                S.focus_event(
                    worklist,
                    me8,
                    focus.get("o") or me8,
                    "off",
                    branch=focus.get("branch"),
                    pr=focus.get("pr"),
                    why=why,
                )
            focus = None
    ended = ""
    sd = state_doc.get("standdown")
    if (
        isinstance(sd, dict)
        and sd.get("focus_at")
        and (not focus or sd.get("focus_at") != focus.get("at"))
    ):
        if not why:
            # Ended by the verb (or replaced by a newer on-event): the newest owned event says why.
            newest: dict[str, Any] = max(
                (e for o, e in (fold.focus or {}).items() if o and owned(o)),
                key=lambda e: (str(e.get("at") or ""), int(e.get("ns") or 0)),
                default={},
            )
            why = (
                str(newest.get("why") or "operator")
                if newest.get("mode") == "off"
                else "replaced by a new focus"
            )
        ended = focus_ended_line(sd, why, _focus_refused_count(worklist, me8, sd.get("focus_at")))
        outq_add(worklist, session_id, state_doc, "focus-ended", ended, 0, sticky=True)
        state_doc.pop("standdown", None)
        S.save_state(worklist, session_id, state_doc)
    return focus, ended


def outq_forget(state_doc, key, text):
    """Drop the queued sticky entry `key` whose text is `text`: the caller delivered it in full."""
    q = _outq(state_doc)
    q["items"] = [
        e
        for e in q["items"]
        if not (_outq_display_key(e) == key and str(e.get("text") or "") == text)
    ]


def run_stop(event, event_ok, worklist, hook_file):
    """The full stop battery. Gathers EVERY static violation, then emits ONE block (five independent blocking checks would cost five turns to clear, which is the "stuck in a loop" the old MAX_BLOCKS existed to paper over), then consults the judge on stops where work remains, then allows with a report."""
    session_id = event.get("session_id", "")
    me8 = (session_id or "unknown")[:8]
    # SESSION-SCOPED, like `.stuck-<sid8>` and `.state-<sid8>` beside it. It was a single shared `.blocks` for the whole worktree, so one peer's clean allow deleted MY judge streak and one peer's block inflated it. With ~48 addressable sessions here that is not a rare race, it is the normal case, and every decision keyed off the streak was reading someone else's work. Fixed before
    # the cadence lands because the cadence's cap is the next thing to key off block streaks, and a shared counter would make the cap fire on a stranger's behaviour.
    counter = worklist.with_suffix(".blocks-%s" % me8)
    root = C.project_root(C.project_start(event))

    fold = S.load(worklist, sync=True)
    state_doc = S.load_state(worklist, session_id)
    _resprofile_report(worklist, session_id, state_doc)

    archived, orphaned = [], []
    # Dead-session cleanup runs before classification so a tombstoned item is invisible to this very pass. Never let it break the gate.
    projects_dir = os.environ.get("WORKLIST_PROJECTS_DIR") or (
        os.path.dirname(event["transcript_path"]) if event.get("transcript_path") else ""
    )
    try:
        archived, orphaned, cleaned = S.cleanup_dead_sessions(
            worklist, fold, session_id, projects_dir
        )
        if cleaned:
            fold = S.load(worklist, sync=True)
    except Exception:  # noqa: BLE001 -- cleanup must never break gating
        archived, orphaned = [], []
    if archived:
        # STICKY, and queued HERE rather than in the allow tail: the store is already flipped to [~], so an archived item never reports twice.
        outq_add(
            worklist,
            session_id,
            state_doc,
            "archived",
            "Worklist: archived %d dead-session item(s) (state -> [~]):\n%s"
            % (len(archived), "\n".join("  " + a for a in archived)),
            1,
            sticky=True,
        )

    # ---- FOCUS MODE (agent/plans/PLAN-stop-hook-focus-mode.md section 3), resolved before classification: a PR wind-down the session declared with `--focus`. Expiry first, then the cheap merged/closed read; an end writes the `off` event, and this stop then runs the full battery. The parked summary is queued on the stop that sees the end, whoever ended it.
    _focus, _focus_ended = focus_resolve(root, worklist, session_id, me8, fold, state_doc)

    lines = fold.lines()
    # v14 gap 4: computed HERE (it used to sit below) so classification can tolerate an expired lease whose worker the OS still shows RUNNING: a full CI battery legitimately outlives the 120-minute lease cap, and the v13 night cost three manual renewals for a watcher that was verifiably alive the whole time. A worker the OS cannot see keeps failing closed.
    live_bg = [b for b in (event.get("background_tasks") or []) if b.get("status") == "running"]
    # v18: REAP A ROSTER THE SESSION CANNOT VERIFY. After a compaction, or an operator reopening the session, the harness still reports every teammate ever spawned as `running` -- measured: 20 claimed, exactly 1 transcript still growing. That roster drives real checks (_in_pure_wait, the 15-minute BG_REPORT_MIN obligation), so a permanently stale one means a
    # session is told it supervises twenty workers forever and confirms phantoms every fifteen minutes -- ritual without signal.
    _bg_dropped, _bg_unknown = [], 0
    # A roster heuristic must never wedge a stop, so every failure is swallowed.
    with contextlib.suppress(Exception):
        live_bg, _bg_dropped, _bg_unknown = wl_liveness.prune_background(
            live_bg, worklist, session_id, event.get("cwd")
        )
    _live_worker_ids = wl_liveness.live_worker_ids(event, live_bg, event.get("cwd"), session_id)
    # worker:lead (agent/plans/PLAN-stop-hook-continuity.md P2.1) is live exactly while something of this session is running to wake the lead.
    with contextlib.suppress(Exception):
        if wl_leasehelp.lead_covered(live_bg, wl_liveness.verify_background(live_bg)):
            _live_worker_ids.add(wl_leasehelp.LEAD_WORKER)
    # AUTO-LEASE FROM A LIVE TASK'S OWN WORDS (P2.2): an open item this session owns, named `#<id>` in a live agent's first prompt or a live shell's description, is leased to that task here, at stop time, against the live event. It replaces the hand `--lease` every spawn used to need, and it also closes the lease-time blindness to a just-spawned worker (PLAN-parallel-writer-roster F3).
    with contextlib.suppress(Exception):
        _metas = wl_roster.load_metas(wl_roster.session_subagents_dir(event.get("cwd"), session_id))
        _prompt_texts = {}
        for _b in live_bg:
            _tid = str(_b.get("id") or "")
            if _b.get("type") == "subagent" and _tid in _metas:
                _prompt_texts[_tid] = wl_leasehelp.first_prompt(_metas[_tid]["jsonl"])
            elif _b.get("type") == "shell" and _tid:
                _prompt_texts[_tid] = str(_b.get("description") or "")
        _auto = wl_leasehelp.auto_lease_candidates(
            fold.items,
            lambda r: C.owned_by_me(r.get("owner"), session_id),
            _prompt_texts,
            _live_worker_ids,
        )
        if _auto:
            _until = C.stamp_ahead(wl_leasehelp.AUTO_LEASE_MIN)[:16] + "Z"
            for _rid, _tid in _auto:
                S.lease_item(
                    worklist,
                    me8,
                    _rid,
                    _until,
                    _tid,
                    "auto-lease: named by live task %s" % _tid,
                    worker_verified=True,
                )
            fold = S.load(worklist, sync=False)
    open_items, _others, deferred_recs, in_flight_recs = S.classify_items(
        fold, session_id, live_worker_ids=_live_worker_ids
    )
    # THE HOOK RENEWS A COVERED LEAD LEASE (P2.1), so an item the lead drives inline across several background tasks needs no manual renewal; with nothing live it has already failed closed above.
    with contextlib.suppress(Exception):
        for _r in in_flight_recs:
            if _r.get("worker") != wl_leasehelp.LEAD_WORKER:
                continue
            _left = C.stamp_age_min(_r.get("until") or "")
            if _left is None or -_left < wl_leasehelp.LEAD_RENEW_BELOW_MIN:
                S.lease_item(
                    worklist,
                    me8,
                    _r["id"],
                    C.stamp_ahead(C.MAX_LEASE_MIN)[:16] + "Z",
                    wl_leasehelp.LEAD_WORKER,
                    "",
                    worker_verified=True,
                )
    # UNBLOCKED (P2.4): an item that was `waiting` on the last stop and is open now has had every blocker close. One sticky line says so, because the item re-enters `open-items` without any other sign of why.
    with contextlib.suppress(Exception):
        _waiting_now = sorted(r["id"] for r in fold.items if r.get("waiting_on"))
        for _rid in sorted(set(state_doc.get("waiting") or []) - set(_waiting_now)):
            _rec = fold.by_id.get(_rid)
            if _rec is not None and _rec.get("state") == " ":
                outq_add(
                    worklist,
                    session_id,
                    state_doc,
                    "unblocked",
                    M.N_UNBLOCKED % (_rid, S.brief_text(_rec, GUIDE_TEXT_CHARS)),
                    1,
                    sticky=True,
                )
        state_doc["waiting"] = _waiting_now
    # THE PARALLEL-WRITER ROSTER (wl_roster), computed ONCE here from the RAW event rather than the pruned `live_bg`: a reaped id whose transcript is not proven finished is still a live writer, and the cap must see it. Read by the bg-report predicate below; its defects are added after the ladder, and its HONEST verdict is applied just before the cadence gate. None means it could not be
    # computed, and then nothing roster-shaped happens: no suppression, no roster key, the battery exactly as before.
    _roster = None
    with contextlib.suppress(Exception):
        _roster = wl_roster.roster(
            event, fold, session_id, state_doc=state_doc, cwd=event.get("cwd")
        )
    # QUEUE LEASES RENEW WHILE THE CAP IS FULL (agent/plans/PLAN-stop-hook-cap-saturated-wait.md step 2). A queue lease is bounded by its own expiry, and an expired one fails closed into an OPEN item; with every writer slot live, that turned a queue the lead could not start into a stream of "open items" every two hours. Renewed only while saturated, only when under
    # LEAD_RENEW_BELOW_MIN is left (or already expired), and never a HOLD_FOR reservation, whose expiry bounds the slot it reserves (R.5). A roster that could not be computed renews nothing.
    with contextlib.suppress(Exception):
        if (
            _roster
            and not _roster.get("blind")
            and len(_roster.get("writers") or ()) >= wl_roster.WRITER_CAP
        ):
            _renewed = 0
            for _r in fold.items:
                if _r.get("state") != ">" or not C.owned_by_me(_r.get("owner"), session_id):
                    continue
                if _r.get("worker") != wl_roster.QUEUE_WORKER or wl_roster.hold_target(_r):
                    continue
                _age = C.stamp_age_min(_r.get("until") or "")
                if _age is None or -_age < wl_leasehelp.LEAD_RENEW_BELOW_MIN:
                    S.lease_item(
                        worklist,
                        me8,
                        _r["id"],
                        C.stamp_ahead(C.MAX_LEASE_MIN)[:16] + "Z",
                        wl_roster.QUEUE_WORKER,
                        "auto-renew: writer cap full",
                        worker_verified=False,
                    )
                    _renewed += 1
            if _renewed:
                fold = S.load(worklist, sync=False)
                open_items, _others, deferred_recs, in_flight_recs = S.classify_items(
                    fold, session_id, live_worker_ids=_live_worker_ids
                )
                _roster = wl_roster.roster(
                    event, fold, session_id, state_doc=state_doc, cwd=event.get("cwd")
                )
    # brief_line, NOT r["line"] -- and this was a live regression worth naming.
    #
    # v14 introduced brief_text precisely because rec["text"] accumulates every update forever and "every block that mentioned it printed them all" (wl_store.brief_text docstring). classify_items duly renders OPEN items through brief_line... and then hands deferred and in-flight back as raw records, so these two call sites reached past the fix to the full text.
    #
    # [?] and [>] are exactly the states a long-running item lives in, so the two states that accumulate the most history were the two still printing all of it. Measured on this session: one [>] item carried 75,672 chars (~19k tokens) and was replayed on EVERY block, which made the stop hook the single largest consumer of the context it was trying to protect.
    #
    # Nothing is discarded: the full text stays in the append-only store and in `--list`; only the human-facing render is brief, which is the rule the rest of this module already follows.
    deferred = [S.brief_line(r) for r in deferred_recs]
    in_flight = [S.brief_line(r) for r in in_flight_recs]

    def handoff_note():
        """Work owned by a session that is NOT running here.

        A live colleague's items are theirs and are not reported (the peer listing was deleted 2026-09-24, P0.3). This one reports the opposite case -- a session that has STOPPED (a restart, a machine switch, a crash) whose remaining work is now owned by nobody present. It is the case a
        compaction loses: the items are in the store, they block nobody, and the summary that would have mentioned them is the thing being summarised.

        Still never a block. It names /migrate, which asks before it moves.
        """
        try:
            cands = S.migrate_candidates(worklist, fold, session_id, projects_dir)
        except Exception:  # noqa: BLE001 -- an advisory must never wedge a stop
            return ""
        cands = [c for c in cands if not c.get("handed_off")][:6]
        if not cands:
            return ""
        lines = [
            "HANDOFF CANDIDATES (not yours, and never blocking): %d session(s) with "
            "remaining work and no live process here." % len(cands)
        ]
        for c in cands:
            n = c["counts"]
            lines.append(
                "  %s  %d item(s) [open %d, in-flight %d, deferred %d]  %s%s  -- %s"
                % (
                    c["prefix"],
                    n["open"] + n["inflight"] + n["deferred"],
                    n["open"],
                    n["inflight"],
                    n["deferred"],
                    ("branch %s  " % c["branch"]) if c["branch"] else "",
                    c["host"],
                    c["evidence"],
                )
            )
            lines.extend(
                "      - [%s] #%s %s" % (it["state"], it["id"], it["text"][:110])
                for it in c["items"][:3]
            )
            plans_show = int(os.environ.get("WORKLIST_MIGRATE_PLANS_SHOW", "3"))
            plans = c.get("plans") or []
            lines.extend(
                "      PLAN %s  [%s]  %d open / %d ticked"
                % (p["rel"], p["status"], p["open"], p["ticked"])
                for p in plans[:plans_show]
            )
            if len(plans) > plans_show:
                lines.append("      +%d more plan(s)" % (len(plans) - plans_show))
        lines.append(
            "  Continue one or more: /migrate  (it lists them, ASKS which, and moves "
            "nothing unasked)."
        )
        lines.append(
            "  Until then list them under '## Remaining' as \"inherited from <prefix>, "
            'unclaimed" so a compaction summary carries them.'
        )
        return "\n".join(lines)

    # ---- v7: regression-gate detection (see wl_reggate). Never breaks gating.
    reg_marker = wl_reggate.reggate_path(worklist, session_id)
    reg_signals, reg_ids, reg_new_ticks, reg_sig, reg_head, reg_banked = [], [], [], "", "", []
    reg_state, reg_forgot, reg_settled = None, False, None
    reg_done_tasks, reg_flood = [], 0
    try:
        reg_state, reg_forgot = wl_reggate.load_reggate(reg_marker)
        if reg_forgot:
            # STICKY: load_reggate has already discarded the marker, so the flag is true only on the discovering pass.
            outq_add(
                worklist,
                session_id,
                state_doc,
                "reg-forgot",
                "Regression marker was corrupt and has been re-initialised; previously "
                "settled verdicts were forgotten, so an old fix-set may be asked once more.",
                1,
                sticky=True,
            )
        reg_cur_tasks = C.task_statuses(session_id, event.get("transcript_path"))
        if not reg_state["head"]:
            # FAIL SAFE: first sight (or a corrupt marker just discarded) initialises to the present and asks nothing this stop. Seeding the check-script hashes here is what keeps prove_new_gate from ever treating the ~90 pre-existing gates as candidates, and seeding task statuses is what keeps I7 from demanding evidence
            # for completions that predate the marker.
            reg_state["head"] = C._git(root, "rev-parse", "HEAD")
            reg_state["seen_ticks"] = wl_reggate.mine_tick_ids(fold.items, session_id)
            reg_state["gate_runs"] = wl_reggate.seed_gate_hashes(root)
            reg_state["task_status"] = {i: st for i, (st, _s) in reg_cur_tasks.items()}
            wl_reggate.save_reggate(reg_marker, reg_state)
        else:
            # I7: a task that FLIPPED to completed since the last stop must carry evidence (checked in the violations pass below).
            prev_ts = reg_state.get("task_status") or {}
            reg_done_tasks = [
                (i, sub)
                for i, (st, sub) in sorted(reg_cur_tasks.items())
                if st == "completed" and prev_ts.get(i) in ("pending", "in_progress")
            ]
            reg_signals, reg_ids, reg_new_ticks, reg_head, reg_banked = wl_reggate.fix_signals(
                root, fold.items, session_id, reg_state
            )
            if len(reg_new_ticks) > wl_reggate.TICK_FLOOD:
                # The v10 upgrade guard: a flood of "new" ticks is rendering drift, not a burst of fixes. Absorb, say so once, keep any commit-derived signals.
                reg_flood = len(reg_new_ticks)
                reg_state["seen_ticks"] = sorted(
                    set(reg_state["seen_ticks"]) | {t for t, _ln, _ev in reg_new_ticks}
                )
                wl_reggate.save_reggate(reg_marker, reg_state)
                tick_ids = {t for t, _ln, _ev in reg_new_ticks}
                reg_new_ticks = []
                reg_ids = [i for i in reg_ids if i not in tick_ids]
                reg_signals = [s for s in reg_signals if not s.startswith("tick: ")]
                # STICKY: the absorbed ticks are already banked in seen_ticks.
                outq_add(
                    worklist,
                    session_id,
                    state_doc,
                    "reg-flood",
                    "Regression gate: %d historical ticks were absorbed as bookkeeping "
                    "(store-format change), not asked about." % reg_flood,
                    1,
                    sticky=True,
                )
            # QUEUE DEPTH IS REPORTED, not hidden in the marker. The reggate asks about ONE fix per stop; without this the operator sees a single question and has no way to know eight more are behind it. Not a worklist item per queued fix, deliberately: a `- [?]` carrying a `reggate:` token is exactly what apply_regression_verdict settles as 'deferred', so auto-creating those lines
            # would settle the whole queue unasked and turn the gate into a no-op.
            reg_queued = sum(1 for d in reg_signals if d.startswith("(") and "queued" in d)
            if reg_queued:
                outq_add(
                    worklist,
                    session_id,
                    state_doc,
                    "reg-queue",
                    "Regression gate: more fixes are queued behind this one and will be "
                    "asked on later stops, one per stop.",
                    1,
                )
            if reg_ids:
                reg_sig = hashlib.sha1("|".join(reg_ids).encode("utf-8")).hexdigest()[:12]
            if reg_ids and reg_sig in reg_state["fixsets"]:
                # Already settled: absorb and never re-ask. The whole cost story.
                reg_state["head"] = reg_head or reg_state["head"]
                reg_state["seen_ticks"] = sorted(
                    set(reg_state["seen_ticks"])
                    | {t for t, _ln, _ev in reg_new_ticks}
                    | set(reg_banked)
                )
                wl_reggate.save_reggate(reg_marker, reg_state)
                reg_signals, reg_ids = [], []
            elif not reg_ids and reg_head and reg_head != reg_state["head"]:
                # Only non-fix or doc-only-fix commits landed: nothing to ask, ever, so the marker just advances.
                reg_state["head"] = reg_head
                reg_state["seen_ticks"] = sorted(set(reg_state["seen_ticks"]) | set(reg_banked))
                wl_reggate.save_reggate(reg_marker, reg_state)
            elif reg_banked and not reg_ids:
                # BANKED, NOT ASKED, HEAD UNCHANGED. A stop with only docs-only ticks and no new commit fell through both branches above and saved nothing, so the same ticks were rediscovered and re-filtered on every later stop forever -- caught in review, not by a control. This is the missing third case: nothing to ask, nothing to advance the head for, but real ids to mark seen.
                reg_state["seen_ticks"] = sorted(set(reg_state["seen_ticks"]) | set(reg_banked))
                wl_reggate.save_reggate(reg_marker, reg_state)
    except Exception:  # noqa: BLE001 -- detection must never break gating
        reg_signals, reg_ids, reg_sig, reg_done_tasks, reg_banked = [], [], "", [], []
        if reg_state is None:
            reg_state = {"head": "", "seen_ticks": [], "fixsets": {}, "gate_runs": {}}

    # ---- gather EVERY static violation, then emit ONE block -----------------
    judged_ok = None
    verdict = None
    tasks = C.pending_tasks(session_id, event.get("transcript_path"))
    # THE EVENT ALREADY CARRIES ALL OF THIS. Transcript parsing, a flush retry and a whole-turn accumulator were built before a captured Stop payload showed `last_assistant_message`, `session_crons` and `background_tasks` sitting in it. The transcript path stays as a FALLBACK for older payloads, but the event is authoritative: it is exact, unraced, and immune to the narration-block
    # bug that made this check fire on its own author.
    last_msg = event.get("last_assistant_message") or ""
    msg_readable = bool(last_msg)
    if not msg_readable:
        last_msg, _tools, msg_readable = C.transcript_tail(
            event.get("transcript_path", ""), want=REMAINING_HEADING
        )
    live_crons = event.get("session_crons") or []
    # Every live cron is a work cron: the one shape is a single work loop.
    live_work_crons = live_crons
    # live_bg is computed above, beside classify_items, since v14 gap 4. Keep the raw event: when a check fires wrongly the first question is always "what did the hook actually receive", and that is unanswerable afterwards.
    with contextlib.suppress(OSError):
        worklist.with_suffix(".lastevent-%s.json" % me8).write_text(
            json.dumps({k: v for k, v in event.items() if k != "transcript"}, indent=2),
            encoding="utf-8",
        )
    # THE HOOK STAMPS THE BRIEF ITSELF (agent/plans/PLAN-stop-hook-continuity.md P1.1); there is no `brief` check any more.
    with contextlib.suppress(Exception):
        S.auto_brief(worklist, root, session_id, fold)

    lstate, lnext, llabel, _others_loops, lcrons = S.loop_state(worklist, session_id)
    # The world signature is computed ONCE, after every shared-state write of this stop (sync, cleanup, escalation), and reused by the STATE.md check and the judge cache, so both describe one world.
    cur_sig = S.world_sig(
        root, worklist, session_id, fold=fold, transcript_path=event.get("transcript_path")
    )
    # JUDGMENT FACTS ONLY for the STATE.md verdict (P1.2): the owned item set, and the items `## Next action` names. The judge keeps cur_sig; the report banking below keys on the owned items' structure (R.4).
    items_sig = S.state_items_sig(fold, session_id)
    # session_id, not blank: the verdict is about THIS session's own section. Without it the check judged whichever document happened to be on disk, so a peer's write reset everyone's clock and -- worse than a skipped stop -- the adopt below banked the PEER'S world signature as this session's own, making a document describing someone else's world read as this one's recovery
    # artifact.
    astate, aage, _atext = S.agent_state_state(
        root,
        session_id=session_id,
        cur_sig=items_sig,
        saved_sig=state_doc.get("state_sig"),
        fold=fold,
    )
    if astate == "ok":
        # ADOPT: an "ok" verdict banks the signature so a second session arriving in the checkout inherits the document instead of being ordered to rewrite it. The adopt fires ONLY on "ok" -- banking on a "stale" verdict would let the next stop compare cur_sig against a signature recorded DURING the block, find them equal, and allow: a gate that clears itself without a rewrite
        # (control T7b pins this by asserting it blocks TWICE on an unchanged world). Must sit above S.save_state below; emit() exits, so anything written after a later emit path never lands.
        state_doc["state_sig"] = items_sig

    remaining_lines = (
        ["[ ] " + i for i in open_items]
        + ["task #%s [%s] %s" % (i, st, sub) for i, sub, st in tasks]
        + ["[?] " + d for d in deferred]
        + ["[>] " + f for f in in_flight]
    )
    something_remains = bool(remaining_lines)
    # ACTIONABLE remainder, which is NOT the same as "something remains". A `[?]` is by construction the one shape this session cannot advance: it is parked on an operator decision or an operator-only capability. When every remaining line is a `[?]`, "nothing moved" is the CORRECT outcome rather than a stall, and the stuck check's remedy -- delegate to a Plan or Explore agent --
    # cannot work, because the constraint is authority, not knowledge. Measured 2026-08-15: the two survivors were "set four Worker secrets with the operator's Cloudflare session" and "delete the last restore path once a machine has round-tripped a repo"; no agent can return an approach to either, so the check could only be satisfied by spawning a decorative agent, i.e. by gaming
    # it. `[>]` still counts as actionable: work on a worker genuinely can stall, and the bg-wait check reports it separately.
    actionable_remains = bool(open_items or tasks or in_flight)
    # v14 gap 6: BANK a message that carries a '## Remaining' section, keyed to the owned items' structure. A later stop on an UNCHANGED item set is then not ordered to re-type a byte-identical table; an add, tick, deferral or state change moves the key and the demand returns. Banked before the battery so the stop that writes the report banks it even when it blocks
    # for some other reason.NOT the retired `state_world_sig` any more (agent/plans/PLAN-stop-hook-retro-20260924.md R.4): that one also hashed HEAD and the harness task statuses, and a peer's commit or a shell finishing is not a change to what this session has left to do.
    report_sig = S.report_items_sig(fold, session_id)
    if msg_readable and REMAINING_HEADING.search(last_msg or ""):
        state_doc["last_report_sig"] = report_sig

    # ---- v15 PURE BACKGROUND WAIT (operator, 2026-07-31): "sometimes you only have background jobs and wait for them without any other pending task. The hook should respect that but have information about them,
    # with a 15 min timeout to have a report, since they may stuck."
    # The state: live background work, no open items, no expired deferral. In it, waiting is LEGITIMATE (the judge is told so below), and the hook's demand shrinks to a bounded 15-minute check-in whose facts the hook gathers ITSELF from each worker's output stream (mtime/size), because file growth is evidence no self-report can fake. Latched on fire, so the check-in costs one
    # focused block per window, never a drumbeat.
    bg_facts, bgwait_due, bgwait_prev, bgwait_next = [], False, "", ""
    _bg_actionable = []
    bg_verdicts = {}
    _in_pure_wait = False
    # The fresh-teammate count behind the widened predicate; also read by the check-in's row render, so it lives outside the due arm.
    _mates_fresh = None
    if live_bg and not open_items:
        _expired_any = any(
            C.DEFAULT_TOKEN.search(r["line"])
            and (C.stamp_age_min(r.get("upd", "")) or 0) >= S.DEFER_WINDOW_MIN
            for r in deferred_recs
        )
        if not _expired_any:
            _in_pure_wait = True
            # v19: the wait is only PURE if the harness queue is also empty of work this session could do right now. A pending task with no unresolved blocker makes the check-in fire (even for an all-live roster) and name it, instead of certifying the wait.
            try:
                _bg_actionable = C.actionable_tasks(session_id, event.get("transcript_path"))
            except Exception:  # noqa: BLE001 -- a fact-gatherer must never wedge a stop
                _bg_actionable = []
            try:
                bg_facts = wl_liveness.bg_output_facts(event.get("cwd"), session_id, live_bg)
            except Exception:  # noqa: BLE001 -- a fact-gatherer must never wedge a stop
                bg_facts = []
            try:
                # Read on EVERY pure-wait stop since v17, not only when the check-in is due: a worker dying is the one change a byte-level view cannot see.
                bg_verdicts = wl_liveness.verify_background(live_bg)
            except Exception:  # noqa: BLE001 -- a fact-gatherer must never wedge a stop
                bg_verdicts = {}
            _bgw = state_doc.get("bgwait") or {}
            _last = _bgw.get("at", "")
            _age = C.stamp_age_min(_last)
            bgwait_prev = _bgw.get("fired", "")
            if _age is None:
                # First sight of the wait state SEEDS the clock silently: the check-in is "you have been waiting 15 minutes, report", never "you started waiting, report".
                _bgw["at"] = C.stamp_now()
                state_doc["bgwait"] = _bgw
            elif _age >= wl_liveness.BG_REPORT_MIN:
                # RESTAMPED EITHER WAY, fired only when some running task has no positive liveness answer. Suppressing without restamping would leave the clock expired, so the first stop after any unverified background job joined the wait would fire the check-in INSTANTLY -- the `you started waiting, report` behaviour the seed above exists to prevent, reintroduced through the back
                # door.
                _bgw["at"] = C.stamp_now()
                state_doc["bgwait"] = _bgw
                # Plan stop-hook-overhaul 1.3: every task with a POSITIVE automatic liveness answer (an OS-confirmed shell process, a subagent whose joined transcript stream is fresh, or a teammate roster its fresh transcripts fully cover). Kept as ONE named predicate so a further liveness term is a one-term add. A dead, suspect or unverifiable worker still fires.
                if any(b.get("type") == "teammate" for b in live_bg):
                    with contextlib.suppress(Exception):
                        _mates_fresh = wl_liveness.live_teammate_transcripts(
                            event.get("cwd"), session_id=session_id
                        )
                _all_live = False
                with contextlib.suppress(Exception):
                    _all_live = wl_liveness.all_waits_live(
                        live_bg, bg_verdicts, _mates_fresh, bg_facts
                    ) or (
                        # The roster's term: every live task is a roster-verified subagent (live, not silent, owing no status). Subagents move to the 20-minute status clock; a shell or a teammate keeps this check-in.
                        wl_roster.roster_covers_all(live_bg, _roster)
                    )
                if not _all_live or _bg_actionable:
                    bgwait_due = True
            bgwait_next = C.stamp_ahead(wl_liveness.BG_REPORT_MIN)
    if not _in_pure_wait:
        # v17 THE LATCH RESET, and it is a fix not a tidy-up. The clock was only ever WRITTEN inside the wait state, so leaving it (an open item appears, a deferral expires, the workers finish) froze the stamp.
        # Re-entering a wait an hour later then found _age >= 15 on the FIRST
        # stop back and fired the check-in immediately -- precisely the "you started waiting, report" behaviour the seed above exists to prevent, and the reason a session that flickers in and out of waiting saw the roster demand over and over. Dropping the key re-seeds it silently.
        state_doc.pop("bgwait", None)

    # THE CAP-SATURATED WAIT (agent/plans/PLAN-stop-hook-cap-saturated-wait.md). A sibling of the pure wait, not a widening of it: pure wait owns the shell/teammate check-in clock and never reads the roster, while this state needs the verified roster and stands down far more (the judge, report shape, hygiene). Every writer slot live and nothing this session could start:
    # the work orders stand down, and only the keys in wl_standdown.CAP_WAIT still block.
    _in_cap_wait = False
    with contextlib.suppress(Exception):
        _cap_tasks = (
            _bg_actionable
            if _in_pure_wait
            else C.actionable_tasks(session_id, event.get("transcript_path"))
        )
        _in_cap_wait = wl_roster.cap_saturated_wait(_roster, open_items, _cap_tasks)
    # EITHER STAND-DOWN skips every paid judge call and counts as supervision for the stuck detector: focus mode is the operator's declared wind-down, and its orders are the PR's own checks (agent/plans/PLAN-stop-hook-focus-mode.md section 4).
    _in_standdown = _in_cap_wait or bool(_focus)

    # STUCK DETECTION. Runs before the others so the count advances on every stop, including the ones where something else already fired: a session blocked three times running on the same check has also moved nothing.
    # SUPERVISED = a live background task AND an in-flight item the session is still
    # refreshing. Only that pair distinguishes "watching a long job" from "left a watch running and wandered off"; a forgotten watch cannot refresh the item, because refreshing it is precisely what nobody is doing. CORRELATED, not just "some [>] item is fresh": a session can hold two concurrent leases, one genuinely tracking the live background task and one unrelated and still
    # being renewed for some other reason. Taking the freshest across ALL in-flight records let the unrelated one silence the exempt-overrun even while the item tracking the ACTUAL watched job had gone stale -- exactly the forgotten-watch case this exemption exists to exclude. Only records whose worker:<id> tag names a task in live_bg can supervise it (mirrors wl_liveness.ladder's
    # wid-not-in-now_bg check).
    _supervised = False
    if live_bg:
        try:
            _live_ids = _live_worker_ids
            _correlated = []
            for r in in_flight_recs:
                wm = C.WORKER.search(r["line"])
                wid = r.get("worker") or (wm.group(1) if wm else "")
                if wid and wid in _live_ids:
                    _correlated.append(r)
            if _correlated:
                _freshest = min(wl_liveness._age_min(r.get("upd", "")) for r in _correlated)
                _supervised = _freshest is not None and _freshest <= STUCK_SUPERVISED_MAX_MIN
        except Exception:  # noqa: BLE001 -- never let a suppression heuristic wedge a stop
            _supervised = False

    # Newest own stamp PLUS the own item set (id+state): stamps are second-resolution, so two moves inside one second would otherwise read as none, and an added-then-ticked item is movement even when the clock cannot show it.
    _mine = [r for r in fold.items if C.owned_by_me(r.get("owner"), session_id)]
    _own_stamp = "%s#%s" % (
        max((str(r.get("upd") or "") for r in _mine), default=""),
        ",".join(sorted("%s%s" % (r["id"], r["state"]) for r in _mine)),
    )
    stuck_n, stuck_fired, stuck_why = stuck_rounds(
        worklist,
        session_id,
        tasks,
        C._git(root, "rev-parse", "HEAD"),
        bool(live_bg),
        # A cap-saturated wait is supervision by construction (every slot is a verified-live writer); counting it as unsupervised made the 3x overrun fire on the first stop after the wait ended.
        supervised=_supervised or _in_standdown,
        own_stamp=_own_stamp,
    )

    # ---- v10: the liveness ladder. Bookkeeping runs on EVERY stop (blocked or allowed), and the state doc is saved before any emit below.
    ladder_pings, ladder_inv, ladder_res, ladder_gone, ladder_idle = [], [], [], [], []
    worker_rows, worker_verdicts = [], {}
    try:
        worker_rows, worker_verdicts = wl_liveness.worker_facts(event, session_id)
        ladder_pings, ladder_inv, ladder_res, ladder_gone, ladder_idle, _lchanged = (
            wl_liveness.ladder(fold, session_id, event, state_doc)
        )
    except Exception:  # noqa: BLE001 -- liveness must never break gating
        ladder_pings, ladder_inv, ladder_res, ladder_gone, ladder_idle = [], [], [], [], []
    # ONE ENTRY, REBUILT EVERY STOP (agent/plans/PLAN-stop-hook-retro-20260924.md R.9). The pings are recomputed on every stop from the items' own ages (wl_liveness.ladder does not fire-once the 45-minute rung), so the entry is regenerable and needs no sticky key. As a sticky `ladder:<sig>` per ping set it was never retracted when its item moved, and on 2026-09-24 twenty of them held the
    # digest's head for every blocked stop: 0 of 52 one-line advisories delivered. Class 0 still: the wording is a direct instruction that becomes a block at the 90-minute rung. The first line drops the legacy sticky entries, a migration that is a no-op once they are gone.
    _q = _outq(state_doc)
    _q["items"] = [e for e in _q["items"] if not str(e.get("key") or "").startswith("ladder:")]
    if ladder_pings:
        outq_add(
            worklist,
            session_id,
            state_doc,
            "ladder",
            M.N_LADDER_PING % ("\n".join("  " + p for p in ladder_pings), me8),
            0,
            refresh_min=wl_liveness.LADDER_PING_MIN,
            on_change=False,
        )
    else:
        _q["items"] = [e for e in _q["items"] if e.get("key") != "ladder"]
    S.save_state(worklist, session_id, state_doc)

    # ---- v11: the store-derived guide, present on EVERY full stop (allow and block alike), so the session reports from the store, not memory. Never breaks gating, and a broken guide SAYS SO rather than vanishing.
    try:
        guide = guided_slice(fold, session_id, worker_verdicts, me8, root)
    except Exception as exc:  # noqa: BLE001
        guide = (
            "WORKLIST GUIDE unavailable (hook bug, fix wl_checks.guided_slice): %s"
            % (str(exc)[:160])
        )
    # v18: AN EMPTY GUIDE IS NOT INFORMATION. "no actionable items in the store" was a deliberate v11 choice -- "a short honest line, never ambiguous silence" -- and the operator has now overruled it on the same breath as the wakeup section ("silent when there is nothing to act on... efficient ai context usage"), quoting a stop whose entire output was this line followed by the
    # wakeup times. The ambiguity argument has also aged out: silence is the session's normal signal for "nothing to do" rather than something it has to guess about. The line is dropped from every emit path; a guide with real rows, and the unavailable-guide bug report, are both untouched.
    guide_empty = guide == M.GUIDE_EMPTY
    if guide_empty:
        guide = ""
    # Every block path appends the guide as a trailing section; this keeps the separator with the content, so a suppressed guide leaves no blank tail.
    guide_tail = "" if guide_empty else "\n\n" + guide
    # THE NEXT WAKEUPS SECTION USED TO RIDE THE GUIDE HERE, and it is deleted rather than shortened (operator, 2026-08-04: "we don't need to print next wakeup times. We should just track the hook moments and notify/warn when needed. let's go for efficient ai context usage"). It printed every scheduled task's next firing and prompt label on EVERY full stop, which is a recurring
    # context cost for a fact that is already in the harness and that no reader ever had to act on. The schedules are still tracked -- the cron-shape checks, the loop-death detector and the judge's loop line all read session_crons directly -- and the one genuinely actionable thing the section carried is now its own warning (broken_schedules, below), which
    # is silent when there is nothing wrong.

    # ---- v13: keyed, tiered violations (operator, 2026-07-31: "single and focused message at a time"). Each entry is (key, always, text) -- KEEP THE TUPLE 3-WIDE; six unpack sites below depend on it, and the priority ladder is derived from the key rather than carried as a fourth field precisely so that stays true. `always` marks the INVARIANT tier, which is never rotated away;
    # everything else rotates one per stop, ordered by the ladder at PRIORITY_LADDER above.
    #
    # THE ADMISSION RULE FOR `always=True`, written down because it was
    # previously only implied and three checks violated it while nobody could point at the sentence they broke. A check is an INVARIANT iff at least one of these holds:
    #
    # I1 COMPUTE-TIME BUDGET. The producer spends a latch, bumps a counter, or pays for an API call while computing its text. Hiding that text spends the budget on a line nobody read. (`plan-fidelity` pays for a
    #       model call; `submodule` and `solo-grind` stamp a suppression window.)
    #
    # I2 SOMEONE ELSE PAYS. The remedy is owed to a party that cannot observe this session's silence -- a teammate whose finished report sits unread, a worker owed its status.
    #
    # I3 HOOK INTEGRITY. The hook or a gate cannot see, so its silence is not evidence and nothing below it can be trusted.
    #
    # COROLLARY THAT KEEPS THE TIER SMALL: a check qualifying ONLY under I1 should have its latch moved to display time rather than be promoted -- see `submodule` and `solo-grind`, which now stamp only on the stop that actually showed them. And when several invariants are outstanding at once, at most ALWAYS_FULL_MAX are quoted in full and the rest are NAMED; the tier buys
    # un-rotatability, not unlimited column inches.
    violations = []

    # Checks whose text is carried verbatim through a cadence pause. The rule is not "important" -- every check here is important -- it is WHO PAYS for the silence. These are the ones where somebody else is already blocked, so a bare label tells this session to stand down while telling the waiting party nothing at all.
    #
    # DERIVED FROM THE LADDER SINCE 2026-08-28, not hand-listed: a hand-listed set left the checks where another party pays ROTATABLE, so each could be starved 23 keys deep by a check that had nothing to do with anyone else. "Somebody else is blocked" is now a TIER, and the carry list reads it.
    # Anything the ladder calls T_OWED is carried, with no second place to remember to add it.
    def carried_through_pause(key):
        return check_tier(key) == T_OWED

    def vadd(key, always, text):
        violations.append((key, always, text))

    # ---- LATCHES THAT MUST BE SPENT AT DISPLAY TIME, NOT COMPUTE TIME.
    #
    # A handful of checks suppress themselves after speaking once: `submodule` writes a time-boxed `subptr` window, `solo-grind` writes `solognd` and never asks again. Both used to stamp that state inside their vadd block -- i.e. on the stop that COMPUTED them, whether or not the session ever saw a word of it. So a rotation miss (or, since the cadence landed, a paused stop)
    # silently opened a suppression window for a message nobody read, and the mechanism was strictly worse than having no latch at all: it went quiet about a real pointer AND left no trace of having done so.
    #
    # This is the tier comment's I1 corollary in code. Rather than promote these two to the invariant tier -- which would fix the swallowing by making them unskippable, at the cost of the scarcity that tier depends on -- the latch moves to the moment the text is actually rendered. Register the mutation here; `spend_display_latches` runs it for the keys this stop really shows.
    display_latch = {}

    def spend_display_latches(keys):
        for key in keys:
            fn = display_latch.pop(key, None)
            if fn is not None:
                fn()

    # ---- THE PARALLEL-WRITER ROSTER'S DEFECTS (wl_roster), in the ALWAYS tier: never rotated away, and they defeat the cadence pause (guard A). The cap and the 20-minute ping are checked in EVERY roster state; honesty only decides what is suppressed further down. Every remedy printed is an action the session completes alone.
    if _roster is not None:
        _rrows = wl_roster.defect_rows(_roster)
        if _roster["over_cap"]:
            vadd(
                "roster-cap",
                True,
                M.V_ROSTER_CAP
                % (
                    len(_roster["writers"]),
                    wl_roster.WRITER_CAP,
                    _rrows["cap"],
                    " ".join(_roster["over_cap"]),
                    me8,
                ),
            )
        # ONE KEY FOR "NO EVIDENCE" (operator ruling 2026-09-24, "Evidence counts as status"): the roster reads transcript growth and in-flight tool calls as status itself, so a worker still owing one after that is exactly a silent worker. `roster-status` is gone.
        _no_evidence = set(_roster["silent"]) | set(_roster["status_due"])
        if _no_evidence:
            vadd(
                "roster-silent",
                True,
                M.V_ROSTER_SILENT
                % (len(_no_evidence), wl_roster.STATUS_PING_MIN, _rrows["silent"], me8),
            )
        if _roster["unleased"]:
            vadd(
                "roster-unleased",
                True,
                M.V_ROSTER_UNLEASED % (len(_roster["unleased"]), _rrows["unleased"], me8),
            )
        if _roster["leased_dead"]:
            vadd(
                "roster-dead",
                True,
                M.V_ROSTER_DEAD % (len(_roster["leased_dead"]), _rrows["dead"], me8, me8),
            )
        if _roster.get("queue_start"):
            vadd(
                "queue-slot",
                True,
                M.V_QUEUE_SLOT
                % {
                    "free": _roster["queue_free"],
                    "queued": _roster["queued"],
                    "ids": ", ".join("#" + i for i in _roster["queue_start"]),
                    "me": me8,
                },
            )

    if bgwait_due:
        # A silent stream alone cannot distinguish "stuck" from "a poll loop that prints only at the end", so OS-verify before accusing: a worker whose process is confirmed alive is reported in those words. Fired live 2026-07-31 on a healthy `until ... completed` CI watch, 29 minutes silent by design.
        _bg_verd = bg_verdicts
        _rows: Any = []
        _mate_ids = {str(b.get("id") or "") for b in live_bg if b.get("type") == "teammate"}
        _subagent_ids = {str(b.get("id") or "") for b in live_bg if b.get("type") == "subagent"}
        # Plan 1.3: a stream-less teammate row is accused only when the fresh-transcript count cannot cover the claimed roster (or cannot be read). No join names WHICH teammate is dead, so every teammate row carries the count.
        _mates_short = bool(_mate_ids) and (_mates_fresh is None or _mates_fresh < len(_mate_ids))
        for tid, desc, age, size, stale in bg_facts:
            if age is None:
                _mate_suffix = ""
                if tid in _mate_ids and _mates_short:
                    _mate_suffix = "  <- POSSIBLY STUCK: %s of %d teammate transcript(s) fresh" % (
                        "unknown" if _mates_fresh is None else str(_mates_fresh),
                        len(_mate_ids),
                    )
                elif tid in _subagent_ids:
                    # A subagent's `.output` is a symlink to its own transcript, so a missing stream is not "reports at completion": the join failed or the transcript is gone.
                    _mate_suffix = "  <- POSSIBLY STUCK: no transcript stream for this subagent"
                _rows.append(
                    "    %s (%s): no output stream yet (a teammate agent reports at completion)%s"
                    % (tid, desc, _mate_suffix)
                )
            else:
                if stale and _bg_verd.get(tid) == "confirmed":
                    _suffix = (
                        "  <- silent but its OS process is VERIFIED ALIVE"
                        " (a loop that prints only at the end is healthy)"
                    )
                elif stale:
                    # DO NOT soften this to "finished, or died". It was tried on 2026-09-04 after a completed one-shot command was accused, and cases 163f and 180e caught it within the hour: 163f's control KILLS a live worker and requires the verdict to flip back to POSSIBLY STUCK, which is the only proof the alive-detection is not vacuous. A vanished process is a DEAD WORKER
                    # and a FINISHED one-shot alike, and nothing here can tell them apart -- so the accusation stays and the reader disambiguates from the stream. The real defect behind the false positive is the harness reporting a completed task as `running`; see the v18 note above, same shape for teammates.
                    _suffix = "  <- POSSIBLY STUCK, investigate or restart"
                else:
                    _suffix = ""
                _rows.append(
                    "    %s (%s): output last grew %dm ago, %d bytes%s"
                    % (tid, desc, age, size, _suffix)
                )
        if _bg_unknown:
            _mates = len([b for b in live_bg if b.get("type") == "teammate"])
            _rows.append(
                M.N_ROSTER_STALE
                % (
                    _mates,
                    _mates - _bg_unknown,
                    _bg_unknown,
                    str(pathlib.Path(__file__).resolve().parent / "worklist.py"),
                    me8,
                )
            )
        if _bg_actionable:
            vadd(
                "bg-report",
                True,
                M.V_BG_REPORT_TASKS
                % (
                    bgwait_prev or "never (this is the first one of this wait)",
                    bgwait_next,
                    wl_liveness.BG_REPORT_MIN,
                    len(live_bg),
                    len(_bg_actionable),
                    "\n".join("    task #%s %s" % a for a in _bg_actionable),
                    "\n".join(_rows),
                ),
            )
        else:
            vadd(
                "bg-report",
                True,
                M.V_BG_REPORT
                % (
                    bgwait_prev or "never (this is the first one of this wait)",
                    bgwait_next,
                    wl_liveness.BG_REPORT_MIN,
                    len(live_bg),
                    "\n".join(_rows),
                ),
            )
    if stuck_fired and actionable_remains:
        # TIER-ACCURATE HEADLINE. This used to assert "not one task changed status AND HEAD did not advance" for every tier, which is FALSE for the tasks-only tier: that one fires precisely BECAUSE commits do not count, so it fires while HEAD is moving. A blocker that overstates its own evidence teaches the session to distrust it.
        vadd(
            "stuck",
            True,
            M.V_STUCK
            % (
                M.STUCK_HEADLINES.get(stuck_why, "NOTHING HAS MOVED"),
                stuck_n,
                M.STUCK_DETAILS.get(stuck_why, ""),
            ),
        )
    if not event_ok:
        vadd("event-unparseable", True, M.V_EVENT_UNPARSEABLE % hook_file)
    if open_items:
        vadd(
            "open-items",
            False,
            M.V_OPEN_ITEMS % (len(open_items), "\n".join("    " + i for i in open_items)),
        )
    # FOCUS MODE: the PR's own fix work (items carrying the focus's `pr:<n>`) still blocks; `open-items` above is still produced and the FOCUS profile parks it, so the rest is counted and named on exit.
    if _focus:
        _pr_open = [i for i in open_items if wl_standdown.pr_linked(i, _focus)]
        if _pr_open:
            vadd(
                "focus-pr-items",
                False,
                M.V_OPEN_ITEMS % (len(_pr_open), "\n".join("    " + i for i in _pr_open)),
            )
    # ---- v21 THE IDLE-STALL GATE, in the ALWAYS tier, directly beside the rotating `open-items` it backstops. It must not be rotated or paused: the whole failure is that `open-items` CAN be, so a copy of it in the same tier would buy nothing. Wrapped, because a stall detector that crashes a stop is worse than one that is absent -- on any exception the ordinary `open-items` block
    # above still stands.
    try:
        _stall_fired, _stall_why = idle_stall(
            state_doc, fold, session_id, open_items, live_bg, in_flight
        )
        _stall_claims = unblocked_claims(last_msg) if open_items else []
    except Exception:  # noqa: BLE001 -- never wedge a stop
        _stall_fired, _stall_why, _stall_claims = False, "check raised", []
    if _stall_fired:
        _rows = "\n".join("    " + i for i in open_items[:8])
        if _stall_claims:
            # The tell rides the stall rather than becoming a second block: it is the same refusal with sharper evidence, and two always-tier messages saying one thing is how a gate teaches itself to be skimmed.
            _rows += "\n  and your own message says they are not blocked:\n" + "\n".join(
                "    " + c for c in _stall_claims
            )
        vadd("idle-stall", True, M.V_IDLE_STALL % (len(open_items), _rows, me8, me8, me8))
    elif _stall_claims:
        vadd(
            "unblocked-claim",
            True,
            M.V_UNBLOCKED_CLAIM % (len(open_items), "\n".join("    " + c for c in _stall_claims)),
        )
    # ---- v23 THE PENDING-ASK GATE (wl_admit.pending_ask), ALWAYS tier, and directly beside idle-stall because it is the same failure through a different door: a stop that yields the operator's turn without needing to. The detector, its regexes and its state signature all live in wl_admit -- this file is ~5,000 lines and is what every stop-gate change has to be read against, so it
    # gets the call site and the key and nothing else.
    #
    # ALWAYS, not rotating, for the reason case 214 pins: the cadence can pause a rotating check, and a PAUSED stop still ends the turn. Ending the turn is precisely the cost this gate exists to remove, so a rotating copy of it would buy nothing.
    #
    # WRAPPED, because a stall detector that crashes a stop is worse than one that is absent. On any exception the rest of the battery still stands.
    try:
        _pa_tools, _ = wl_admit.turn_tools(event.get("transcript_path", ""))
        _pa_deferred = wl_admit.defer_created(state_doc, fold, session_id)
        _pa_fired, _pa_line = wl_admit.pending_ask(last_msg, _pa_tools, _pa_deferred)
    except Exception:  # noqa: BLE001 -- never wedge a stop
        _pa_fired, _pa_line = False, ""
    if _pa_fired:
        vadd("pending-ask", True, M.V_PENDING_ASK % (_pa_line, me8))
    # ---- THE SWEEP PROMPT, and its whole value is WHEN it fires.
    #
    # Not on a stall (idle-stall owns that), not on every stop (a prompt that fires always is a prompt that gets skimmed). It fires at the one moment that is genuinely cheap: the queue is EMPTY, nothing is in flight, and something just left the open state -- i.e. work finished cleanly and the session is about to walk away with its context still warm.
    #
    # That is exactly when the findings noticed in passing get abandoned. The operator had to ask for them by hand ("let's also fix all what you've found on the way") after a session reported several and fixed none. Rediscovery costs a whole session; asking here costs one line.
    #
    # ROTATING, not always: it is a nudge, not a refusal, and "there was nothing" is a complete answer.
    try:
        # COUPLED TO idle_stall'S EARLY-RETURN TEXT, and said out loud because the first version of this line looked for "closed" -- a word that string never contains -- so the prompt could never have fired. A silently vacuous nudge is worse than no nudge. The test below pins both halves, so changing that string turns a test red instead of turning this check off.
        _just_closed = "left the open state" in str(_stall_why or "")
        _sweep_moment = (
            not open_items and not in_flight and not live_bg and bool(fold) and _just_closed
        )
    except Exception:  # noqa: BLE001 -- a nudge must never wedge a stop
        _sweep_moment = False
    if _sweep_moment:
        vadd("sweep-moment", False, M.V_SWEEP_MOMENT % "an item this turn")

    undefaulted = [d for d in deferred if not C.DEFAULT_TOKEN.search(d)]
    if undefaulted:
        vadd(
            "undefaulted",
            False,
            M.V_UNDEFAULTED % (len(undefaulted), "\n".join("    " + d[:150] for d in undefaulted)),
        )
    # ---- v10 AUTONOMY: a DEFAULT past its window is EXECUTED, not restated. The operator: "usually I went through the 'Recommended' action". So the recommendation IS the decision once the window closes; the block demands the execution (bounded per stop, so a migrated backlog drains as a queue rather than a wall). Fresh deferrals still just report.
    expired = [
        r
        for r in deferred_recs
        if C.DEFAULT_TOKEN.search(r["line"])
        and (C.stamp_age_min(r.get("upd", "")) or 0) >= S.DEFER_WINDOW_MIN
    ]
    # A corroborated `execute_default` from wl_defersettle joins this same demand early: a standing rule already requires the DEFAULT, so the window has nothing left to wait for. Suppressed: an advisory must never wedge a stop.
    with contextlib.suppress(Exception):
        expired += wl_defersettle.accelerated(state_doc, deferred_recs, expired)
    if expired:
        shown = expired[: S.DEFER_EXEC_PER_STOP]
        vadd(
            "defer-expired",
            False,
            M.V_DEFER_EXPIRED
            % (
                len(expired),
                S.DEFER_WINDOW_MIN,
                "\n".join("    #%s %s" % (r["id"], S.brief_text(r, 150)) for r in shown),
                ""
                if len(expired) <= len(shown)
                else "    (and %d more, held back so this drains %d per stop)\n"
                % (len(expired) - len(shown), S.DEFER_EXEC_PER_STOP),
                me8,
            ),
        )
    # ---- v12 JUSTIFICATION: a [?] must earn its seat. New deferrals are gated at --defer; the markdown inbox and older sessions can still park one without a WHY/HOW, so those are demanded once aged -- bounded, the same drain shape as the expired queue. Expired items are excluded: they already carry the stronger execute-the-DEFAULT demand above.
    expired_ids = {r["id"] for r in expired}
    unjustified = [
        r
        for r in deferred_recs
        if r["id"] not in expired_ids
        and C.DEFAULT_TOKEN.search(r["line"])
        and (C.stamp_age_min(r.get("upd", "")) or 0) >= S.JUSTIFY_AGE_MIN
        and not deferral_is_justified(r)
    ]
    if unjustified:
        shown = unjustified[: S.JUSTIFY_PER_STOP]
        vadd(
            "unjustified",
            False,
            M.V_UNJUSTIFIED
            % (
                len(unjustified),
                S.JUSTIFY_AGE_MIN,
                "\n".join("    #%s %s" % (r["id"], S.brief_text(r, 150)) for r in shown),
                ""
                if len(unjustified) <= len(shown)
                else "    (and %d more, held back so this drains %d per stop)\n"
                % (len(unjustified) - len(shown), S.JUSTIFY_PER_STOP),
                me8,
                me8,
            ),
        )
    # ---- I7: a completion claim must leave a RECORD (see wl_reggate) --------
    ev_ticks = [
        ev[:150]
        for _tid, _line, ev in reg_new_ticks
        if not completion_evidence(root, ev, event.get("transcript_path"))
    ]
    ev_tasks = []
    for i, sub in reg_done_tasks:
        row = next(
            (ln for ln in (last_msg or "").splitlines() if re.search(r"#%s\b" % re.escape(i), ln)),
            "",
        )
        if not (row and completion_evidence(root, row)):
            ev_tasks.append("#%s %s" % (i, sub))
    if ev_ticks or ev_tasks:
        vadd(
            "completion",
            False,
            M.V_COMPLETION_EVIDENCE
            % (
                ""
                if not ev_ticks
                else M.V_COMPLETION_TICKS % "\n".join("    " + t for t in ev_ticks),
                ""
                if not ev_tasks
                else M.V_COMPLETION_TASKS % "\n".join("    " + t for t in ev_tasks),
            ),
        )
    # Persist ONLY the transitions that passed: an unevidenced completion keeps its previous status in the marker, so it is re-detected and re-checked next stop rather than slipping through on a later block.
    if reg_state is not None and reg_state.get("head"):
        try:
            held = {t.split()[0].lstrip("#") for t in ev_tasks}
            prev_ts = reg_state.get("task_status") or {}
            new_ts = {
                i: st
                for i, (st, _s) in C.task_statuses(session_id, event.get("transcript_path")).items()
            }
            for i in held:
                if i in prev_ts:
                    new_ts[i] = prev_ts[i]
            if new_ts != prev_ts:
                reg_state["task_status"] = new_ts
                wl_reggate.save_reggate(reg_marker, reg_state)
        except Exception:  # noqa: BLE001 -- bookkeeping must never break gating
            pass
    # ---- THE WORK GATE. A brief goes stale when the WORLD moves, not when the clock does: a sentence that still describes what this session is doing is still true at 91 minutes, and demanding a rewrite of an accurate sentence is noise that
    # trains the reader to dismiss the check. Same contract the STATE.md check already runs on, and the same signature, so the two cannot disagree about whether anything happened.
    #
    # Only the STALE verdict is gated. "missing" still fires unconditionally: a session that never briefed is invisible to its peers no matter how quiet the world is, and that is the case the roster exists for.
    #
    # Note this does NOT touch sole_live_session, which reads the brief's raw timestamp rather than this verdict, so the liveness oracle keeps its wall-clock meaning while the nag stops firing on an unchanged world. ---- INTENT (plan section 4). Two effects, both deliberately small.
    _intent, _intent_expired = S.live_intent(worklist, session_id)
    # v18 THE EXPIRED INTENT THAT COVERED NOTHING OPEN. V_INTENT_EXPIRED tells the reader "what it covered is still outstanding" -- and the check never verified that. It fired live on an intent whose ONE covered item had been ticked with evidence, so the message asserted something demonstrably false. A check that says the wrong thing is worse than one that stays quiet: it trains
    # the reader to skim the whole battery.
    #
    # Firing is SUPPRESSED only when every covered id resolves to a closed item. Two cases keep it firing on purpose: an intent that named NOTHING (absence of a claim is not proof the claim was met), and a covered id this fold cannot resolve (unreadable is not the same as done -- the V_PR_UNREADABLE rule).
    _cov_ids = list(_intent_expired.get("covers") or []) if _intent_expired else []
    _by_id = {r["id"]: r for r in fold.items}

    def _cover_still_open(cid):
        r = _by_id.get(cid)
        return r is None or r.get("state") in (" ", "?", ">")

    _intent_all_closed = bool(_cov_ids) and not any(_cover_still_open(c) for c in _cov_ids)
    if _intent_expired is not None and not _intent and not _intent_all_closed:
        _cov = ", ".join(_intent_expired.get("covers") or []) or "(nothing named)"
        _when = C.parse_stamp(str(_intent_expired.get("at") or ""))
        _age = int((C.utcnow() - _when).total_seconds() / 60.0) if _when else 0
        vadd(
            "intent-expired",
            False,
            M.V_INTENT_EXPIRED
            % (
                str(_intent_expired.get("text") or "")[:200],
                _age,
                int(_intent_expired.get("min") or 0),
                _cov,
            ),
        )

    # ---- PLAN DRIFT. Binds the session to its own committed design record. Costs one glob plus the first 10 lines of each non-done plan, and only on a branch that HAS a plan directory: a project not using the convention pays the glob and nothing else. Rotating tier, not always: a stale plan is a real debt but never an integrity failure, and it must not outrank the checks that
    # stop work being abandoned. NOT gated on something_remains, and that was a real bug in the first cut. `something_remains` means open ITEMS, not an unfinished message, so gating on it meant a session that had ticked everything was never told its plan was stale -- which is precisely the moment it matters most: the work is finished and the committed record still says `executing`.
    # The exit is satisfiable either way (edit the plan, or set its Status), so this cannot become a nag with no way out.
    try:
        _pdrift = plan_drift_rows(root, fold, session_id)
    except Exception:  # noqa: BLE001 -- a plan read must never break the battery
        _pdrift = []
    if _pdrift:
        # CAPPED, with the remainder COUNTED rather than dropped: twelve rows in one block is a context bomb, and the no-silent-caps doctrine says a gate that truncates must say what it truncated or it reads as "that is all of them". Newest-first, so the plans nearest the work lead.
        _shown = _pdrift[:PLAN_DRIFT_MAX]
        _rest = len(_pdrift) - len(_shown)
        vadd(
            "plan-drift",
            False,
            M.V_PLAN_DRIFT
            % (
                len(_pdrift),
                "\n".join("    %s  [Status: %s]" % (rel, st) for rel, st in _shown)
                + ("\n    + %d more, same verdict" % _rest if _rest else ""),
            ),
        )

    # ---- PLAN FILE vs WORKLIST (wl_planfile). The sibling of plan-drift above: that one asks "has the plan gone stale against the work", this one asks "are the plan's own checkbox TASKS tracked at all". Different questions, and neither implies the other -- a plan can be freshly rewritten and still have eighteen boxes nothing tracks, which is exactly what was measured on
    # agent/plans/PLAN-secret-namespace-migration.md on 2026-09-02.
    #
    # AN ADVISORY, NOT A `vadd`, and the reason is a deadlock rather than politeness: a plan carrying 18 open tasks would, as a block, refuse every turn of every session in this repo until a multi-week migration finished. See wl_planfile's design note 1. The queue also supplies the whole noise
    # policy for free -- OUTQ_PER_STOP=3, plus outq_add's content signature,
    # which re-fires the moment the untracked set changes and otherwise stays quiet for REPORT_REFRESH_MIN.
    #
    # PRIORITY 2, alongside the other real advisories and above the agent hint at 3: the operator asked for this specifically, so it should not queue behind a suggestion, but it must not outrank a report a peer is blocked on at 1. ONE plan per stop, the newest with findings, remainder counted.
    try:
        _pf_rows, _pf_unread = wl_planfile.plan_rows(
            root, plan_records(root), fold, session_id, plan_owner
        )
        if _pf_rows:
            # S2: up to PLAN_PLANS_SHOW plans, sharing ONE quote budget. `render_all` owns both the cap and the remainder line that `render`'s n_more_plans used to carry, so the call site no longer does that arithmetic. THE ORDER, distinct from the advisory below and keyed apart from it on purpose: `plan-tasks` must never become a `vadd` (test-planfile.py pins that), because a plan
            # a session merely OWNS can carry eighteen boxes and would wedge every turn. A plan the session ADOPTED is different in kind -- the adoption is a committed sentence saying it is being executed -- and it blocks only while boxes are untracked or stale, so tracking them (or deferring, or handing the plan back) ends it in one turn.
            for _row in _pf_rows:
                if _row.get("census") or not (_row["untracked"] or _row["stale_open"]):
                    continue
                if not wl_planfile.is_adopted(root, _row["rel"]):
                    continue
                _gap = list(_row["untracked"]) + list(_row["stale_open"])
                vadd(
                    "plan-adopted",
                    False,
                    M.V_PLAN_ADOPTED
                    % {
                        "rel": _row["rel"],
                        "n_open": _row["n_open"],
                        "n_gap": len(_gap),
                        "recipes": "\n".join(
                            '    .claude/hooks/stop/worklist.py --add %s "%s"'
                            % (
                                session_id[:8],
                                wl_planfile._quote(t if isinstance(t, str) else str(t)),
                            )
                            for t in _gap[:3]
                        )
                        + (
                            "\n    + %d more, same verdict" % (len(_gap) - 3)
                            if len(_gap) > 3
                            else ""
                        ),
                        "me": session_id[:8],
                    },
                )
                break
            _pf_text = wl_planfile.render_all(_pf_rows, _pf_unread)
            # Not produced in focus mode: plan boxes park until the PR is done.
            if _pf_text and not _focus:
                outq_add(worklist, session_id, state_doc, "plan-tasks", _pf_text, 2)
    except Exception:  # noqa: BLE001 -- a plan read must never wedge a stop
        pass

    # ---- PLAN BACKLOG NOMINATION (wl_backlog). Answers the question `plan-tasks` above does not: which committed, undone design should THIS session implement next. The operator's own words: "we plan but don't implement". DESC by mtime (plan_records' own order), validated against a live worklist claim and a peer's liveness -- see wl_backlog's module docstring and
    # agent/plans/PLAN-stop-hook-plan-backlog-nudge.md. ADVISORY, never a vadd, same tier and same reasoning as plan-tasks: a blocking nomination over a standing backlog nobody here created would wall every session behind work it did not cause.
    # SKIPPED IN FOCUS MODE, not filtered: producing it spends `backlog_nominated` on a nomination nobody would see.
    try:
        _bl_candidate, _bl_reason, _bl_stats = (
            (None, "", {})
            if _focus
            else wl_backlog.next_plan(
                root,
                plan_records(root),
                fold,
                session_id,
                plan_owner,
                worklist,
                state_doc,
                projects_dir,
            )
        )
        if _bl_candidate is not None:
            _bl_text = wl_backlog.render(_bl_candidate, _bl_reason, _bl_stats, session_id)
            _bl_added = outq_add(
                worklist,
                session_id,
                state_doc,
                "plan-backlog:%s" % _bl_candidate["rel"],
                _bl_text,
                2,
            )
            if _bl_added:
                _bl_cap = state_doc.get("backlog_nominated")
                if not isinstance(_bl_cap, dict):
                    _bl_cap = {}
                    state_doc["backlog_nominated"] = _bl_cap
                _bl_cap[_bl_candidate["rel"]] = C.stamp_now()
                S.save_state(worklist, session_id, state_doc)
    except Exception:  # noqa: BLE001 -- a plan read must never wedge a stop
        pass

    # ---- PLANNED BUT NOT IMPLEMENTED (wl_planenforce). The third question in this neighbourhood and the only BLOCKING one: `plan-tasks` above asks whether a plan's boxes are TRACKED, `plan-backlog` asks which plan to start NEXT, and this asks whether the corpus is being DRAINED. The operator was offered three narrower scopes after seeing the census and chose ALL, so there is no
    # status exemption here and NOT_STARTED_STATES is deliberately not honoured -- `draft` carries most of the debt in this tree, and exempting it would leave the block asserting almost nothing.
    #
    # BOUNDED BY A CEILING, NOT BY A FIRE CAP, which is the whole reason this is allowed to be a T_MISSION vadd at all. `wl_planfile`'s design note 1 and the `plan-adopted` call-site comment above both refuse exactly this widening, and they are right about the wedge: a block over 221 standing boxes with no reachable exit would be the fourth repeated-nag incident in this hook. The
    # ceiling is the answer -- silent at or under it, and the block's own text prints the number of boxes that ends it.
    #
    # WARN RIDES THE QUEUE, BLOCK RIDES THE LADDER. Inside the warn band the same body goes out as a priority-2 advisory, where outq_add's content signature keeps it from repeating while nothing changes; over the ceiling it is a vadd. One renderer, two deliveries, so the two can never describe the tree differently.
    try:
        _pe_state, _pe_text, _pe_detail = wl_planenforce.evaluate(
            root, plan_records(root), session_id, plan_owner, worklist, projects_dir
        )
        if _pe_state == wl_planenforce.BLOCK and _pe_text:
            vadd("plan-unimplemented", False, M.V_PLAN_UNIMPLEMENTED % {"body": _pe_text})
        elif _pe_state == wl_planenforce.WARN and _pe_text and not _focus:
            outq_add(worklist, session_id, state_doc, "plan-clock", _pe_text, 2)
    except Exception:  # noqa: BLE001 -- a plan read must never wedge a stop
        pass

    pstate, pahead, pref = wl_ci.publish_divergence(root)
    if pstate == "stale-local":
        vadd("stale-local", False, M.V_STALE_LOCAL % (pref, pahead))
    if pstate == "diverged":
        vadd("diverged", False, M.V_DIVERGED % (pref, pahead, pref))
    # Before the PR checks, because a moved pointer changes what the PR IS.
    moves = wl_ci.submodule_pointer_moves(root)
    if moves:
        # LATCHED PER (path, target sha), NOT silenced. Before this, an unpushed pointer re-fired on EVERY stop, including after a deliberate decision to keep it unpushed for now -- so a session doing exactly the right thing was told off once a minute, which is how a real warning becomes wallpaper.
        #
        # The latch is TIME-BOXED, never permanent, and that distinction is the whole design. A permanent "I acknowledged this" flag would go silent on a pointer somebody genuinely forgot, which is worse than the noise it removes: the check exists because a forgotten pointer ships whatever the parent last recorded. So it re-fires every SUBMODULE_LATCH_MIN, and a pointer moving to a
        # NEW sha re-fires immediately because the signature changes.
        _sub_sig = hashlib.sha1(
            "|".join("%s@%s" % (p, b) for p, _a, b, _w in moves).encode("utf-8")
        ).hexdigest()[:12]
        _sub = state_doc.get("subptr") or {}
        _same = _sub.get("sig") == _sub_sig
        _sub_age = C.stamp_age_min(_sub.get("at")) if _same else None
        # A RECORDED DECISION LENGTHENS THE LATCH; it never removes it. See submodule_decision_recorded: the third door (leave it, never stage it) is invisible to this warning, so a session that decided correctly was told off every fifteen minutes. A day is long enough to stop interrupting the work and short enough that a stale decision is re-examined rather than enshrined.
        _decided = all(
            submodule_decision_recorded(root, p, b, fold=fold, session_id=session_id)
            for p, _a, b, _w in moves
        )
        _latch = SUBMODULE_DECIDED_LATCH_MIN if _decided else SUBMODULE_LATCH_MIN
        _due = (not _same) or _sub_age is None or _sub_age >= _latch
        if _due:
            vadd(
                "submodule",
                False,
                M.V_SUBMODULE_POINTER
                % (
                    len(moves),
                    "; ".join("%s %s -> %s, %s" % (p, a, b, w) for p, a, b, w in moves),
                ),
            )
            # DISPLAY-TIME, see spend_display_latches: stamping here used to open the suppression window on a stop that rotated the text away.
            display_latch["submodule"] = lambda sig=_sub_sig: state_doc.__setitem__(
                "subptr", {"sig": sig, "at": C.stamp_now()}
            )
    elif state_doc.get("subptr"):
        # Pointers match again (pushed, or reverted): drop the latch so the next genuine move fires at once rather than inheriting a stale window.
        state_doc.pop("subptr", None)
    # ---- v13: CI-queue backpressure (operator, 2026-07-31). Computed before the freshness check because a saturated queue changes what that check should say. A slack-granter must fail toward pressure: any error here reads as "unknown", which is exactly today's behavior.
    try:
        qstate, qdetail = wl_ci.ci_queue_state(root, worklist, session_id)
    except Exception:  # noqa: BLE001 -- blindness must not grant slack
        qstate, qdetail = "unknown", None
    queue_note = ""
    # FOCUS MODE ARMS BOTH PR READS from the focus's own branch: `--focus` declared the PR this session's (agent/plans/PLAN-stop-hook-focus-mode.md section 3).
    _focus_ref = str((_focus or {}).get("branch") or "") or None
    fstate, fdetail = wl_ci.pr_body_freshness(root, ref=_focus_ref)
    pr_stale_folded = False
    if fstate == "stale":
        if qstate == "saturated":
            # Its whole rationale is saving a CI round; mid-jam there is no round to save yet. The reminder folds into the queue note below.
            pr_stale_folded = True
        else:
            vadd("pr-stale", False, M.V_PR_STALE % fdetail)
    elif fstate == "unreadable":
        vadd("pr-unreadable", True, M.V_PR_UNREADABLE % fdetail)
    if qstate == "saturated" and qdetail:
        queue_note = M.N_CI_QUEUE % (
            qdetail.get("ref", "?"),
            qdetail.get("queued", 0),
            qdetail.get("newest_age_min", 0),
            M.N_CI_QUEUE_PR_STALE_LINE if pr_stale_folded else "",
        )
        # Class 0, volatile, and refresh_min=0 so the shown-ledger NEVER
        # suppresses it: a jam that is still a jam must say so on every stop. The change-or-window latch is for slow-moving advisories; applying it here would mute an actionable note for six hours after one showing.
        outq_add(worklist, session_id, state_doc, "ci-queue", queue_note, 0, refresh_min=0)
    # v10: CI trouble on the open PR. `live_bg` is already running-only, which ci_watch_armed relies on. ci_report is a non-blocking note; it rides the allow path AND is appended to the block body, so a downgraded CI failure cannot vanish behind an unrelated violation.
    # A hand-rolled CI watch blocks the turn. Structurally ABOVE ci_trouble because it needs no network at all: it reads the live background roster the caller already has. Unconditional by design -- see V_ADHOC_WATCH.
    try:
        _adhoc_id, _adhoc_blob = wl_ci.adhoc_watch(live_bg)
    except Exception as exc:  # noqa: BLE001 -- a broken check must SAY SO
        _adhoc_id, _adhoc_blob = "", ""
        vadd(
            "adhoc-watch-broken",
            True,
            "THIS IS A HOOK BUG: adhoc_watch failed: %s: %s" % (type(exc).__name__, str(exc)[:120]),
        )
    if _adhoc_id:
        vadd("adhoc-watch", True, M.V_ADHOC_WATCH % (_adhoc_id, _adhoc_blob))

    ci_report = ""
    try:
        cistate, cidetail = wl_ci.ci_trouble(
            root,
            worklist,
            session_id,
            live_bg,
            (last_msg or "") + "\n" + "\n".join(deferred),
            ref=_focus_ref,
            owned=bool(_focus_ref),
        )
    except Exception as exc:  # noqa: BLE001 -- a broken CI check must SAY SO, not vanish
        cistate, cidetail = "unreadable", "%s: %s" % (type(exc).__name__, str(exc)[:120])
    # FILL IN THE FOCUS PR NUMBER once the CI read knows it: the spawn guard matches fix work on `pr:<n>`, so the store needs it. Same `at`, so neither the 24-hour cap nor the parked ledger restarts.
    if _focus and not _focus.get("pr") and isinstance(cidetail, dict):
        with contextlib.suppress(Exception):
            _ci_info = cidetail.get("info") if "info" in cidetail else cidetail
            _ci_pr = _ci_info.get("pr") if isinstance(_ci_info, dict) else None
            if _ci_pr:
                S.focus_event(
                    worklist,
                    me8,
                    _focus.get("o") or me8,
                    _focus.get("mode"),
                    branch=_focus.get("branch"),
                    pr=_ci_pr,
                    why="pr-resolved",
                    at=_focus.get("at"),
                )
                _focus = dict(_focus, pr=int(_ci_pr))
    if cistate == "unreadable":
        vadd("ci-unreadable", True, M.V_CI_UNREADABLE % cidetail)
    elif cistate in ("trouble", "downgraded", "soft"):
        _rows = cidetail["hard"] or cidetail["soft"]
        _txt = wl_ci.ci_rows_text(_rows, cidetail["info"])
        _pr = cidetail["info"].get("pr", "?")
        # THE COMMITS THAT COULD HAVE CAUSED IT, printed with the red rather than left for the session to think of. It demands nothing and adds no blocking path -- it only appends facts to a block already being emitted -- so it cannot become a wall. This has to be MECHANICAL and live here: `C.emit` below ends in `sys.exit(0)`, upstream of `wl_judge.run_judge`, so a judged rule
        # could never fire on a red-CI stop at all.
        _histkind, _hist = wl_histfirst.apply_verdict(root, _rows, None)
        if _histkind == "fire":
            _txt = "%s\n\n%s" % (_txt, _hist)
        if cistate == "trouble":
            vadd(
                "ci-red",
                True,
                M.V_CI_RED
                % (
                    _pr,
                    len(cidetail["hard"]),
                    "(per-JOB conclusions, never the run rollup -- a cancelled run with no "
                    "failed job is not counted here). The run is still %s.%s"
                    % (
                        "in progress, so more jobs may appear" if cidetail["live"] else "final",
                        # Partial sight is still partial: say so rather than let the list read as complete.
                        ""
                        if not cidetail["info"].get("truncated")
                        else " NOTE: only the first %d of %s checks were read, so this list may be incomplete."
                        % (len(cidetail["info"]["contexts"]), cidetail["info"].get("total", "?")),
                    ),
                    _txt,
                    wl_ci.CI_MAX_BLOCKS,
                    cidetail["n"],
                    me8,
                ),
            )
        elif cistate == "soft":
            ci_report = M.CI_NOTE_RETRYABLE % (
                _pr,
                len(cidetail["soft"]),
                ", ".join(wl_ci.CI_RETRY_PATTERNS),
                _txt,
            )
        else:
            ci_report = M.CI_NOTE_DOWNGRADED % (
                _pr,
                len(cidetail["hard"]),
                cidetail["n"],
                " (you named %s, which counts as acknowledged)" % ", ".join(cidetail["acked"])
                if cidetail["acked"]
                else "",
                _txt,
            )
    elif cistate == "ok":
        # CI is genuinely clean. Separate from the hard/soft bucket above ON PURPOSE: "Review Complete" is deliberately excluded from ci_classify (CI_NONBLOCKING_CONTEXTS) so it can never read as a CI failure, but that exclusion also means a red "Review Complete" was previously INVISIBLE here -- identical to a fully clean head. This session has the context (what it just pushed,
        # what the review is about) that a remote job does not, so it is the right place to surface it.
        try:
            rstate, rdetail = wl_ci.review_red(
                root,
                worklist,
                session_id,
                cidetail,
                (last_msg or "") + "\n" + "\n".join(deferred),
            )
        except Exception as exc:  # noqa: BLE001 -- a broken check must SAY SO
            rstate, rdetail = "unreadable", "%s: %s" % (type(exc).__name__, str(exc)[:120])
        if rstate == "unreadable":
            vadd("review-unreadable", True, M.V_REVIEW_UNREADABLE % rdetail)
        elif rstate == "trouble":
            vadd(
                "review-red",
                True,
                M.V_REVIEW_RED
                % (
                    rdetail["pr"],
                    rdetail["sha"],
                    rdetail["title"],
                    rdetail["summary"],
                    rdetail["owner"],
                    rdetail["name"],
                    rdetail["pr"],
                    rdetail["owner"],
                    rdetail["name"],
                    rdetail["pr"],
                    rdetail["owner"],
                    rdetail["name"],
                    rdetail["pr"],
                    rdetail["owner"],
                    rdetail["name"],
                    rdetail["pr"],
                    wl_ci.REVIEW_MAX_BLOCKS,
                    rdetail["n"],
                    me8,
                    rdetail["pr"],
                ),
            )
        elif rstate == "downgraded":
            ci_report = (ci_report + "\n\n" if ci_report else "") + M.REVIEW_NOTE_DOWNGRADED % (
                rdetail["pr"],
                rdetail["title"],
                rdetail["n"],
                rdetail["owner"],
                rdetail["name"],
                rdetail["pr"],
            )
    # ---- v21: THE pr-babysit FINISH LINE, as the markdown checkboxes it is.
    #
    # THE OPERATOR'S OWN EXAMPLE for the priority ladder: "if there is an open-pr and if it's red we must continue to work until making it green. That should be determined by our markdown tasks. You know we already have empty/checked boxes."
    #
    # `ci-red` already blocks on the red -- but it has a HARD CEILING of CI_MAX_BLOCKS and then downgrades to a report, for good reasons that are about a red nobody here can fix. Nothing then held the WAVE open. A session could reach green, leave the PR sitting in draft with the review never requested and threads unresolved, and stop clean: every check on the board was satisfied
    # while the thing it was asked to do was unfinished. That is the state a mission tier exists to refuse.
    #
    # THE FOUR BOXES ARE READ OFF `.claude/commands/pr-babysit.md`, not invented here -- "The console PR rides as a draft until green; stops at green + Claude-reviewed + threads-resolved PRs; never merges."
    #
    # WHAT GATES IT, so it cannot become a tax on every session that happens to have a PR: a pr-babysit ROUND LOG must exist for this branch. That file is the wave's own artifact (wl_roundlog.roundlog_path, the path the skill already writes), so the check fires for a session running the loop and is structurally silent for one that is not.
    #
    # THE LAST TWO BOXES ARE STORE-BACKED, and deliberately not guessed. The hook cannot see a `<!-- claude-reviewed: <sha> -->` marker or a resolved review thread without spending another GraphQL round trip, and a box that ticks itself on an unreliable read is worse than one the session ticks
    # with evidence. So they are covered by a TICKED worklist item carrying
    # `pr:<n>/reviewed` / `pr:<n>/threads` -- the same `cl:<slug>/<wN>` linkage agent/programs/<slug>/CHECKLIST.md already uses, and the same evidence discipline every other tick carries.
    try:
        _prf_info = None
        if cistate == "ok":
            _prf_info = cidetail
        elif cistate in ("trouble", "downgraded", "soft", "watched") and isinstance(cidetail, dict):
            _prf_info = cidetail.get("info")
        _prf_num = (_prf_info or {}).get("pr")
        # The branch is read LOCALLY. `agent_branch` is not bound until the unread-reports surface several hundred lines below, and referencing it here raised UnboundLocalError -- caught by the fail-closed arm, which turned the whole check into a HOOK BUG banner on the proving case. That is the arm working; it is not a reason to leave it reachable.
        _prf_branch = C.git_branch(root) or ""
        _prf_log = wl_roundlog.roundlog_path(projects_dir, _prf_branch) if projects_dir else None
        if _prf_num and _prf_branch and _prf_log is not None and _prf_log.is_file():
            _prf_green = cistate == "ok"
            _prf_ready = not (_prf_info or {}).get("draft")
            _prf_rev = _prf_covered(fold, "pr:%s/reviewed" % _prf_num)
            _prf_thr = _prf_covered(fold, "pr:%s/threads" % _prf_num)
            _prf_boxes = [
                (_prf_green, "green -- every check on PR #%s passing" % _prf_num),
                (_prf_ready, "ready for review -- the console PR is out of draft"),
                (_prf_rev, "Claude-reviewed (tick an item carrying pr:%s/reviewed)" % _prf_num),
                (_prf_thr, "threads resolved (tick an item carrying pr:%s/threads)" % _prf_num),
            ]
            if not all(done for done, _ in _prf_boxes):
                vadd(
                    "pr-finish",
                    False,
                    M.V_PR_FINISH
                    % (
                        _prf_branch,
                        _prf_num,
                        "\n".join(
                            "    - [%s] %s" % ("x" if done else " ", label)
                            for done, label in _prf_boxes
                        ),
                        hook_file,
                        me8,
                        _prf_num,
                        hook_file,
                        me8,
                    ),
                )
    except Exception as exc:  # noqa: BLE001 -- a blind finish line must SAY SO
        vadd(
            "pr-finish",
            True,
            "THIS IS A HOOK BUG: the pr-babysit finish-line check failed: %s: %s"
            % (type(exc).__name__, str(exc)[:120]),
        )
    if ci_report:
        # Class 0, volatile, refresh_min=0 for the same reason as the queue
        # note: ci_trouble recomputes this from the live run every stop, and a PR that is still red must keep saying so. Case 128 pins it: the downgraded note is what remains after the block budget is spent, so latching it would leave a red PR reported exactly once.
        outq_add(worklist, session_id, state_doc, "ci-report", ci_report, 0, refresh_min=0)
    # v9: count WORK crons. The work loop dying quietly is the exact failure the operator named.
    loop_died, had_crons = cron_memory(
        worklist, session_id, len(live_work_crons), loop_finished_declared(last_msg)
    )
    if loop_died:
        vadd("loop-died", False, M.V_LOOP_DIED % had_crons)
    # THE PUSH-BACK: the session just declared something impossible in a domain
    # a written specialist covers. `always=True` because this is a latched
    # one-shot whose producer marks state at COMPUTE time -- rotating the text away would spend the latch on a line nobody ever saw, which is the exact bug the `always` tier exists to prevent.
    #
    # It is a BLOCK rather than an advisory, and that is the operator's own standard applied to their own request: "a document an agent can skip is not a control". The advisory tier already carries the topic hint, and the session this was built for had ALREADY been shown that file. One unskippable challenge per specialist is the smallest thing that could have changed the outcome.
    with contextlib.suppress(Exception):  # never wedge a stop on a prompt
        _pb, _pb_errs = A.pushback_for((last_msg or "") + "\n" + "\n".join(remaining_lines))
        _pb_claims, _pb_hit = _pb
        if _pb_hit:
            _pb_name, _pb_hits = _pb_hit
            _pb_seen = state_doc.get("agent_pushbacks")
            if not isinstance(_pb_seen, dict):
                _pb_seen = {}
                state_doc["agent_pushbacks"] = _pb_seen
            if _pb_name not in _pb_seen:
                vadd(
                    "agent-pushback:%s" % _pb_name,
                    True,
                    M.V_AGENT_PUSHBACK % (", ".join(_pb_claims), _pb_name, ", ".join(_pb_hits[:6])),
                )
                _pb_seen[_pb_name] = C.stamp_now()
                S.save_state(worklist, session_id, state_doc)
        elif _pb_claims:
            # THE AGENT-FREE HALF: a give-up claim fired but no specialist cleared the hint's own confidence floor. Latched on the CLAIM SET, not on a name -- there is no name here, and the same claim set repeating (a session re-asserting the same impossibility) must not re-fire every stop.
            _gc_key = ",".join(sorted(_pb_claims))
            _gc_seen = state_doc.get("giveup_claims_seen")
            if not isinstance(_gc_seen, dict):
                _gc_seen = {}
                state_doc["giveup_claims_seen"] = _gc_seen
            if _gc_key not in _gc_seen:
                vadd("giveup-claim:%s" % _gc_key, True, M.V_GIVEUP_CLAIM % ", ".join(_pb_claims))
                _gc_seen[_gc_key] = C.stamp_now()
                S.save_state(worklist, session_id, state_doc)
    # Explicit state mapping, NOT `!= "ok"`: a missing DIRECTORY gets the
    # bootstrap wall exactly once per session, latched on agent_boot_told, rather than the block every other bad verdict earns.
    #
    # THE "no-branch" ARM IS GONE (2026-08-18). It existed only because the document's path needed a branch to resolve, and it made this check REPORT-ONLY on a detached HEAD -- which this operator gets on every interactive rebase, so the one artifact designed to survive compaction went unenforced for the whole of one. Keying the path on the session removed the cause instead of
    # softening the symptom, and `agent_note` and the `agent-blind` note went with it: a note describing a state that can no longer occur is a check that cannot fire.
    #
    # A live intent answers the STALE verdict only. `missing`, `thin`, `bloated` and `aimless` are about the DOCUMENT's shape and content, which no statement of plan can substitute for.
    if astate == "stale" and _intent:
        astate = "ok"
    # `waitled` is in this tuple and its absence was a real hole: the rule was enforced at WRITE time by the verb and invisible at READ time here, so a document that predates the rule, or one written by any path that bypasses the verb, would sail through the Stop check forever. A rule enforced on only one of two paths is a rule with a documented way around it.
    # v22 SOLO GRIND. Advisory tier (always=False) so the cadence can pause it:
    # it is a prompt to think, not a fact that must be answered this turn.
    try:
        _n_mates = wl_liveness.live_teammate_transcripts(event.get("cwd"), session_id=session_id)
    except Exception:  # noqa: BLE001 -- a fact-gatherer must never wedge a stop
        _n_mates = 0
    if solo_grind_due(len(open_items), _n_mates, state_doc):
        vadd("solo-grind", False, M.V_SOLO_GRIND % (len(open_items), SOLO_GRIND_MIN_ITEMS))
        _sg_n = len(open_items)
        display_latch["solo-grind"] = lambda: state_doc.__setitem__("solognd", _sg_n)

    if something_remains and astate in (
        "missing",
        "thin",
        "bloated",
        "aimless",
        "stale",
        "waitled",
    ):
        vadd(
            "agent-state",
            False,
            M.V_AGENT_STATE
            % (
                S.agent_session_slug(session_id),
                astate,
                _agent_state_because(astate, aage),
                S.AGENT_STATE_MIN_CHARS,
                S.AGENT_STATE_MAX_CHARS,
                me8,
            ),
        )
    elif astate == "no-dir":
        # The latch used to key on the BRANCH, so one session whose checkout changed branch met the same wall a second time. It keys on the slug the wall actually names, which cannot change under a live session.
        _boot_key = S.agent_session_slug(session_id)
        if state_doc.get("agent_boot_told") != _boot_key:
            vadd(
                "agent-bootstrap",
                True,
                M.V_AGENT_BOOTSTRAP % ((_boot_key,) * 2),
            )
            state_doc["agent_boot_told"] = _boot_key
            S.save_state(worklist, session_id, state_doc)
        elif something_remains:
            vadd(
                "agent-absent",
                False,
                M.V_AGENT_STILL_ABSENT % S.agent_session_slug(session_id),
            )
    # NO PEER LISTING since 2026-09-24 (agent/plans/PLAN-stop-hook-continuity.md P0.3): the `agent-peers`, `others` and `others-items` advisories had no reader under the single-terminal ruling. Orphaned items and handoff candidates -- work nobody present owns -- are still reported below.
    # v18: unread sub-agent reports, on ORDINARY stops as well as at the two boundaries wl_report already covers by hook. SessionStart and PostCompact catch a fresh or compacted session; this catches the far commoner case of a long-running session whose teammate finished twenty minutes ago and whose SendMessage has since scrolled out of reach.
    #
    # IT GRADUATES, since 2026-08-28. The old rule here was "REPORT-ONLY, never a violation", on the stated grounds that "there is no honest evidence a stop could demand for 'I read it'". That grounds is simply untrue: `wl_report.py --read <me> <id>` is exactly such evidence, and the advisory ALREADY PRINTS THAT COMMAND two lines below its own excuse.
    #
    # And the cost of the excuse was measured, not theorised: `outq_drain` has exactly one call site, on the ALLOW path, so a continuously blocking session never sees a queued advisory at all. One session carried FOUR unread teammate reports through 57 consecutive blocking stops and was never once told. A teammate's finished report is the clearest case of somebody else having paid
    # to produce something this session is not reading, which is the T_OWED tier's whole definition.
    #
    # THE LADDER, so it stays proportionate to how long the report has waited: < UNREAD_ROTATE_MIN advisory only, as before -- a report that landed minutes ago is news, not a debt.
    #   >= UNREAD_ROTATE_MIN     a rotating violation at T_OWED.
    #   >= UNREAD_INVARIANT_MIN, an invariant: at that age the advisory queue
    # or any [SILENT] one has demonstrably not delivered it, and a [SILENT] report is the case that is indistinguishable from a healthy agent unless somebody looks.
    #
    # The branch is read HERE and nowhere else on this path now: the report store is keyed per branch in TMPDIR (wl_report.store_root), which is a different tree from agent/ and keeps its own key.
    agent_branch = C.git_branch(root)
    try:
        _unread = wl_report.unread(
            wl_report.store_root(root), agent_branch or wl_report.NO_BRANCH, session_id
        )
        # AUTO-READ WHAT THE LEAD ALREADY RECEIVED (agent/plans/PLAN-stop-hook-continuity.md P1.5): a completed task notification with a non-empty result in this session's own transcript is the report delivered, so demanding `--read` for it was restating a fact the hook holds. [SILENT] reports are never auto-read.
        if _unread:
            _dids, state_doc["report_delivery"] = wl_report.delivered_ids(
                event.get("transcript_path"), state_doc.get("report_delivery")
            )
            _unread = wl_report.mark_delivered(wl_report.store_root(root), me8, _unread, _dids)
        if _unread:
            _rp = str(pathlib.Path(__file__).resolve().parent / "wl_report.py")
            _rows = "\n".join(
                "    %s%-12s %-22s %s"
                % (
                    "[SILENT] " if e.get("silent") else "",
                    e["id"],
                    str(e.get("agent"))[:22],
                    e.get("title") or "(stopped without reporting)",
                )
                for e in _unread[-10:]
            )
            if len(_unread) > 10:
                _rows = "    (%d older not shown)\n%s" % (len(_unread) - 10, _rows)
            _ur_text = M.N_UNREAD_REPORTS % (
                len(_unread),
                agent_branch or "?",
                _rows,
                _rp,
                _rp,
                me8,
            )
            # OLDEST first, so the age is the age of the longest-ignored one.
            _ur_age = max((C.stamp_age_min(e.get("at")) or 0) for e in _unread)
            _ur_silent = any(e.get("silent") for e in _unread)
            if _ur_age >= UNREAD_INVARIANT_MIN or _ur_silent:
                vadd("unread-reports", True, _ur_text)
            elif _ur_age >= UNREAD_ROTATE_MIN:
                vadd("unread-reports", False, _ur_text)
            else:
                outq_add(worklist, session_id, state_doc, "unread-reports", _ur_text, 2)
    except Exception:  # noqa: BLE001 -- an advisory surface must never wedge a stop
        pass
    # v23: the pre-ask refusal ledger, surfaced. `block-settled-questions.sh` refuses permission-shaped git questions and, until now, left no trace anywhere the operator looks -- which .claude/hooks/test-hooks.sh names as the flaw in its own design: "a false positive is invisible by construction: the operator never learns what was not asked". The hook now appends one row per
    # refusal; this is the read side.
    #
    # ROTATING AND ADVISORY, never a violation. A refusal is the gate working;
    # the only thing worth saying is that the file exists, has rows, and is where a wrong refusal becomes visible.
    try:
        _ar_n, _ar_path = wl_admit.ask_refusals(worklist, session_id)
        if _ar_n:
            outq_add(
                worklist,
                session_id,
                state_doc,
                "ask-refusals",
                M.N_ASK_REFUSALS % (_ar_n, _ar_path),
                2,
            )
    except Exception:  # noqa: BLE001 -- an advisory surface must never wedge a stop
        pass
    # v19 L2: identities that write to this store but have never stopped. The CLI check refuses them at the door from now on; this is the backstop for what it cannot reach -- history already written, and the deliberate hole where the environment cannot name the caller.
    #
    # PRIORITY 1, not 2, and the reason is mechanical: OUTQ_PER_STOP is 3 and outq_drain is highest-priority-first, so a priority-2 note can still queue behind others for many stops on a busy branch. An identity split is not something to ration. REPORT-ONLY: this runs on every session's Stop path and the repair is not always this session's to make.
    try:
        _phantoms, _blind = phantom_identities(worklist, session_id, fold)
        _wp = str(pathlib.Path(hook_file).resolve())
        if _blind:
            outq_add(
                worklist, session_id, state_doc, "phantom-blind", M.N_PHANTOM_BLIND % _blind, 1
            )
        elif _phantoms:
            _rows = "\n".join(
                "    %-12s %4d event(s), first seen %dm ago, owns %s" % (p, n, age, owns)
                for p, n, age, owns in _phantoms
            )
            outq_add(
                worklist,
                session_id,
                state_doc,
                "phantom-identity",
                M.N_PHANTOM_IDENTITY % (len(_phantoms), _rows, _wp, me8),
                1,
            )
    except Exception:  # noqa: BLE001 -- a backstop must never wedge a stop
        pass
    # NO STOP-TIME DOCS-DRIFT CHECK since 2026-09-24 (agent/plans/PLAN-stop-hook-continuity.md P1.3). It counted any commit under `.claude`, so hook work -- which the CI-overhaul design docs do not describe -- ordered edits to unrelated documents. The SessionStart block still reports DRIFTED or pending, which is where a fresh session reads the docs.
    # ---- v20: the /handoff checklist gate (agent/programs/<slug>/CHECKLIST.md) -------- WHY: /handoff wrote a design suite and INSTRUCTED, in prose, that the next session seed the worklist. Prose gates nothing, so a handoff whose PROMPT.md was ignored or compacted away dropped program work silently and nobody found out. CHECKLIST.md is the machine-readable half of the same
    # handoff: deliverables are FILE-VERIFIED (the tick is bookkeeping, the file is the truth) and waves are store-linked through the `cl:<slug>/<wN>` token, so both ends of the handoff are checkable rather than promised. See wl_checklist for the adjudication.
    try:
        _cl_v, _cl_a = wl_checklist.checklist_findings(root, fold, session_id, projects_dir)
        for _k, _always, _t in _cl_v:
            vadd(_k, _always, _t)
        for _k, _t, _p in _cl_a:
            outq_add(worklist, session_id, state_doc, _k, _t, _p)
    except Exception as exc:  # noqa: BLE001 -- fail CLOSED: a blind gate must say so
        vadd("cl-shape", True, M.V_CL_UNREADABLE % str(exc)[:160])
    if len(live_work_crons) > 1:
        vadd(
            "many-work-crons",
            False,
            M.V_MANY_WORK_CRONS
            % (
                len(live_work_crons),
                ", ".join(
                    "%s (%s)" % (c.get("id", "?"), c.get("schedule", "?")) for c in live_work_crons
                ),
            ),
        )
    # v18: the surviving half of the deleted NEXT WAKEUPS section. A schedule this hook cannot parse is invisible to every check above -- it is not a countable work cron -- so it must be said out loud rather than left implicit in a list nobody prints any more.
    try:
        _broken_scheds = broken_schedules(event)
    except Exception:  # noqa: BLE001 -- a shape check must never wedge a stop
        _broken_scheds = []
    if _broken_scheds:
        vadd(
            "broken-schedule",
            False,
            M.V_BROKEN_SCHEDULE % (len(_broken_scheds), "\n".join(_broken_scheds)),
        )
    # A "blocked on you" claim the operator never confirmed is a guess about someone else's intent, and it is how work parks itself indefinitely. The confirmed form carries the operator's own words back.
    unconfirmed = [
        i
        for i, _, _ in tasks
        if re.search(r"#%s\b[^\n]*\bYou\b" % re.escape(i), last_msg or "")
        and not re.search(r"#%s\b[^\n]*You \(User Thinks So\)" % re.escape(i), last_msg or "")
    ]
    if unconfirmed:
        vadd("unconfirmed", False, M.V_UNCONFIRMED % ", ".join("#" + i for i in unconfirmed))
    # THE TASK LIST IS THE OPERATOR'S VIEW. They see "23 tasks (17 done, 6 open)" in the app, so a Remaining section that omits one of those six is out of sync with what they are looking at. Every open task id must appear.
    missing_ids = [i for i, _, _ in tasks if not re.search(r"#%s\b" % re.escape(i), last_msg or "")]
    # EVERY REMAINING ITEM MUST DECLARE ITS STATE. "who it is blocked on" is not the same question as "is anyone working it": a list where six items all look alike cannot tell the operator what is moving and what is parked. The word must also AGREE with the harness, which is the list they see in their app.
    state_re = re.compile(
        r"\b(ongoing|in progress|in-progress|in_progress|pending|blocked|parked)\b",
        re.IGNORECASE,
    )
    ongoing_words = {"ongoing", "in progress", "in-progress", "in_progress"}
    unstated, mislabelled, uncited = [], [], []
    if REMAINING_HEADING.search(last_msg or ""):
        section = (last_msg or "")[REMAINING_HEADING.search(last_msg).start() :]
        for tid, _sub, status in tasks:
            line = next(
                (ln for ln in section.splitlines() if re.search(r"#%s\b" % re.escape(tid), ln)),
                "",
            )
            if not line:
                continue  # the missing-id check below already covers this
            found = state_re.search(line)
            if not found:
                unstated.append(tid)
                continue
            word = found.group(1).lower()
            # A BLOCKER IS A CLAIM ABOUT REALITY, SO IT NEEDS A SOURCE. Scoped deliberately narrow. Exempt anything already backed by machinery this hook can SEE: a running background task or a live lease means there is a real, named object being waited on, and "blocked on the operator" has its own check above. What survives the filter is exactly the Wave C class: a prose blocker
            # naming a phase of this project, which is the one shape nobody can check.
            if (
                word in ("blocked", "parked")
                and not live_bg
                and not in_flight
                and not re.search(r"\byou\b", line, re.IGNORECASE)
            ):
                ok, detail = citation_state(root, line)
                if not ok:
                    uncited.append("#%s %s" % (tid, detail))
            if status == "in_progress" and word not in ongoing_words:
                mislabelled.append("#%s is in_progress but reads '%s'" % (tid, word))
            elif status == "pending" and word in ongoing_words:
                mislabelled.append("#%s is pending but reads '%s'" % (tid, word))
    # ---- I6: static idle detection (v8; below the scan since v9) ------------ Disjoint from the stuck detector by geometry: stuck is active-but-futile and needs three stops; this is inactive-with-nothing-inbound, whose deadliest form produces NO further stops, so the counter never fires. Scoped to tasks: open [ ] items and undefaulted [?] already block above, and a worklist of
    # defaulted [?] is time-boxed autonomy, which may stop. Any live cron counts as a wake-up.
    idle_tasks = [
        i
        for i, _, _ in tasks
        if not re.search(r"#%s\b[^\n]*You \(User Thinks So\)" % re.escape(i), last_msg or "")
    ]
    if idle_tasks and not in_flight and not live_bg and not live_work_crons and not open_items:
        vadd("idle", False, M.V_IDLE % ", ".join("#" + i for i in idle_tasks[:8]))
    # ---- v10: the blocking ladder rungs. Rung 1 (ping) NEVER blocks; it rides the report below. Each blocking rung fired at most once per (item, stamp) -- see wl_liveness.ladder.
    facts = "\n".join("    " + w for w in worker_rows) or "    (no background tasks running)"
    if ladder_inv:
        vadd(
            "ladder-investigate",
            True,
            M.V_LADDER_INVESTIGATE % ("\n".join("    " + s for s in ladder_inv), facts, me8),
        )
    if ladder_gone:
        vadd(
            "ladder-gone",
            True,
            M.V_LADDER_INVESTIGATE_GONE
            % ("\n".join("    " + s for s in ladder_gone), facts, me8, me8),
        )
    if ladder_idle:
        # ITS OWN VERDICT, not folded into `gone`. A gone worker is absent from the harness list; an idle one FINISHED ITS TURN and said so in its own transcript, and may still be resumable. Same remedies, different fact, and conflating them would put "is not in the harness list any more" in front of a teammate that is merely between turns.
        vadd(
            "ladder-idle",
            True,
            M.V_LADDER_INVESTIGATE_GONE
            % ("\n".join("    " + s for s in ladder_idle), facts, me8, me8),
        )
    if ladder_res:
        vadd(
            "ladder-resolve",
            True,
            M.V_LADDER_RESOLVE % ("\n".join("    " + s for s in ladder_res), facts, me8),
        )
    # ---- v12 CI-WAITING FORCE. The observed failure, three times in one night: the only thing in flight is a CI watch, the run is healthy, and the stop is a Remaining table while 30+ aged [?] sit untouched. When watching CI is ALL the in-flight work, waiting is not a valid stop: the aged backlog is demanded, oldest first, bounded per stop. Every named item has a single-turn solo
    # exit (do it and tick, execute its DEFAULT early, or re-justify with --defer, which resets its age below CI_FORCE_MIN_AGE), so pressure converts into action, never a deadlock.
    ci_watching, watch_desc = wl_ci.ci_watch_only(live_bg)
    if ci_watching:
        backlog = [
            r for r in deferred_recs if (C.stamp_age_min(r.get("upd", "")) or 0) >= CI_FORCE_MIN_AGE
        ]
        if backlog:
            backlog.sort(key=lambda r: (-(C.stamp_age_min(r.get("upd", "")) or 0), r.get("id", "")))
            rows = []
            for r in backlog[:CI_FORCE_PER_STOP]:
                if not C.DEFAULT_TOKEN.search(r["line"]):
                    verb = (
                        "give it a DEFAULT and a WHY/HOW with --defer %s %s, "
                        "or just do it and --tick" % (me8, r["id"])
                    )
                elif not deferral_is_justified(r):
                    verb = (
                        "do it now and --tick %s %s '<evidence>', or justify "
                        "it with --defer (WHY/HOW)" % (me8, r["id"])
                    )
                elif deferral_waits_on_ci(r):
                    verb = (
                        "execute its DEFAULT now and --tick %s %s "
                        "'<evidence>'; the wait was the only reason to hold it" % (me8, r["id"])
                    )
                else:
                    # Its WHY names something the run cannot settle, so ordering the DEFAULT here would order past a reason this session already wrote down and the judge already audited.
                    verb = (
                        "the WAIT is not what holds this one -- its WHY says: %s. "
                        "Advance whatever part of it you own and --update %s %s, or "
                        "--tick it if that part is finished. Do not execute a DEFAULT "
                        "whose WHY reserves the act."
                        % (
                            ((S.deferral_justification(r) or {}).get("why") or "")[:110].strip()
                            or "(unreadable)",
                            me8,
                            r["id"],
                        )
                    )
                rows.append(
                    "    #%s (sat %dm) %s\n        NEXT: %s"
                    % (r["id"], C.stamp_age_min(r.get("upd", "")) or 0, S.brief_text(r, 120), verb)
                )
            vadd("ci-waiting", False, M.V_CI_WAITING % (watch_desc, len(backlog), "\n".join(rows)))
    # CLAUDE.md rule 2 says discovery is always in scope and FIXING is the default;
    # the "found, not fixed" list is meant as a last resort, not a parking bay. A session that ends every turn with one has converted a fixing rule into a reporting habit, which is exactly what the operator objected to. ANCHORED TO A LINE START, because the first version matched the phrase ANYWHERE and promptly fired on a message that was DESCRIBING this very check ("2. \"Found,
    # not fixed\" is now a blocking phrase"). A gate that cannot survive being written about is too broad. A real list leads a line, optionally behind markdown emphasis or a heading marker; a mention sits mid-sentence or inside quotes or backticks, none of which match here.
    if uncited:
        vadd("uncited", False, M.V_UNCITED % "\n".join("    " + u for u in uncited))
    if re.search(
        r"^[ \t>*_#-]{0,6}found,?[ \t]+not[ \t]+fixed\b",
        last_msg or "",
        re.IGNORECASE | re.MULTILINE,
    ):
        vadd("found-not-fixed", False, M.V_FOUND_NOT_FIXED)
    # The same rule, the phrasings the narrow pattern above never saw. Kept as a SEPARATE key so the original stays exactly as pinned by its own tests.
    try:
        _deferred = deferred_findings(last_msg or "")
    except Exception:  # noqa: BLE001 -- a detector must never crash a stop
        _deferred = []
    if _deferred:
        vadd(
            "deferred-finding",
            False,
            M.V_DEFERRED_FINDING % "\n".join("    " + d for d in _deferred),
        )
    try:
        _deflect_fired, _deflect_text = wl_deflect.check(
            worklist, session_id, event.get("transcript_path")
        )
    except Exception:  # noqa: BLE001 -- a detector must never crash a stop
        _deflect_fired, _deflect_text = False, ""
    if _deflect_fired:
        vadd("deflected-finding", False, M.V_DEFLECTED_FINDING % _deflect_text)
    try:
        _bg_orphans = wl_bgsweep.sweep(live_ids={str(b.get("id")) for b in live_bg})
    except Exception:  # noqa: BLE001 -- a detector must never crash a stop
        _bg_orphans = []
    if _bg_orphans:
        _rows = "\n".join(
            "    pid %d, %s min old: %s"
            % (pid, ("%.1f" % age_min) if age_min is not None else "unknown", cmdline[:70])
            for pid, age_min, cmdline in _bg_orphans
        )
        vadd(
            "bg-orphan",
            False,
            M.V_BG_ORPHAN % (len(_bg_orphans), wl_bgsweep.BGSWEEP_AGE_MIN, _rows + "\n"),
        )
    if unstated:
        vadd("unstated", False, M.V_UNSTATED % ", ".join("#" + i for i in unstated))
    if mislabelled:
        vadd("mislabelled", False, M.V_MISLABELLED % "; ".join(mislabelled))
    # ---- v20 PLAN FIDELITY. Cheap when there is no approved plan (one bounded transcript scan, incremental after the first stop), and it spends a model call only when a plan EXISTS and the tracked items look coarse against it. A degraded run is QUEUED rather than blocked or dropped: the queue survives the block stops this session is likely to be having, so the note lands on the
    # first clean one instead of vanishing. The trade is that a session which never reaches a clean stop is told late, the same trade the agent hint already makes and for the same reason.
    # Paid (a model call); its verdict would be stood down in a cap-saturated wait anyway, so it is not bought.
    if not wl_judge.JUDGE_DISABLED and not _in_standdown:
        _pf_note = ""
        try:
            _pf_note = planfid_check(worklist, session_id, event, fold, lines, me8, last_msg, vadd)
        except Exception as exc:  # noqa: BLE001 -- a heuristic must never wedge a stop
            _pf_note = M.V_PLANFID_DEGRADED % ("it raised %s: %s" % (type(exc).__name__, exc))[:160]
        if _pf_note:
            outq_add(
                worklist, session_id, state_doc, "planfid-degraded", _pf_note, 1, refresh_min=60
            )
    # DELIBERATELY NOT CHECKED: "no task is in_progress". A queue where everything is honestly parked is a legitimate state, and blocking on it would nag a session that is correctly waiting. The case that actually matters -- driving something while the operator's list still shows it pending -- is caught by the agreement check above, which fires when the message says "ongoing" and
    # the harness disagrees.
    if tasks and REMAINING_HEADING.search(last_msg or "") and missing_ids:
        vadd(
            "out-of-sync",
            False,
            M.V_OUT_OF_SYNC % (len(missing_ids), ", ".join("#" + i for i in missing_ids)),
        )
    if something_remains and not msg_readable:
        vadd(
            "hook-blind",
            True,
            M.V_HOOK_BLIND
            % (
                event.get("transcript_path", ""),
                worklist.with_suffix(".lastevent-%s.json" % me8),
                hook_file,
            ),
        )
    elif (
        something_remains
        and not REMAINING_HEADING.search(last_msg or "")
        # v14 gap 6: an unchanged world accepts the banked report instead of demanding a byte-identical restatement.
        and state_doc.get("last_report_sig") != report_sig
    ):
        vadd(
            "no-remaining",
            False,
            M.V_NO_REMAINING % "\n".join("    " + r for r in remaining_lines[:12]),
        )

    # ---- ADMISSION PREFILTER, ABOVE THE BLOCK EXIT (agent/plans/PLAN-stop-hook-continuity.md P0.4). wl_admit's docstring promises Tier R is appended "always, BEFORE any model call", and until 2026-09-24 that was false on every blocked stop: the prefilter sat after the block exit, so a busy session that admitted a mistake left no record at all. The regex pass is under 0.4 ms
    # with zero tokens; the model call stays on the judge path below. Recorded once per turn signature, so a turn that stays blocked across several stops is one row, not one per stop.
    admit_text = wl_admit.turn_text(event.get("transcript_path", "")) or last_msg
    admit_sig = wl_admit.turn_sig(admit_text)
    admit_settled, _admit_corrupt = wl_admit.load_settled(worklist, session_id)
    admit_hits = [] if admit_sig in admit_settled else wl_admit.prefilter(admit_text)
    if admit_hits and state_doc.get("admit_tier_r") != admit_sig:
        wl_admit.record_hits(worklist, session_id, admit_hits, admit_sig)
        state_doc["admit_tier_r"] = admit_sig

    # Saved EAGERLY. The state doc is bookkeeping that must survive every exit
    # below, and one of them (the WORKLIST_FOCUS=off block) emits without
    # saving at all -- exactly the shape that made the output queue lose latched sections before it was moved to compute-time persistence.
    S.save_state(worklist, session_id, state_doc)
    # ---- THE ROSTER'S HONEST SUPPRESSION (wl_roster.ROSTER_SUPPRESSES), in ONE place, just ahead of the cadence gate so every check has had its say. An HONEST roster means every item in flight is leased to a live worker the hook verified itself, so the pushes that exist to ask "is the waiting real" have their answer. Only those keys drop: CI red, pr-finish, the
    # judge tier and every integrity check still block, and the roster's own cap and ping keys were added above in every state. `agent-state` drops only for `stale`; `bg-report` only when no task outside the roster (a shell the OS did not confirm, a teammate) is running and no harness task is actionable, because those keep their 15-minute check-in.
    _guide_pre_roster, _guide_empty_pre_roster = guide, guide_empty
    if _roster is not None and _roster["state"] == "HONEST":
        _outside = [
            b
            for b in live_bg
            if not (
                (b.get("type") == "subagent" and str(b.get("id") or "") in _roster["verified"])
                or (
                    b.get("type") == "shell"
                    and bg_verdicts.get(str(b.get("id") or "")) == "confirmed"
                )
            )
        ]

        def _roster_drops(key):
            if key not in wl_roster.ROSTER_SUPPRESSES:
                return False
            if key == "agent-state":
                return astate == "stale"
            if key == "bg-report":
                return not _outside and not _bg_actionable
            return True

        violations = [v for v in violations if not _roster_drops(v[0])]
        if bgwait_due and not any(k == "bg-report" for k, _a, _t in violations):
            bgwait_due = False  # stood down, not delivered: the "last delivered" stamp stays true
        if not violations:
            # The allow carries the roster in place of a push, AHEAD of the guide, so the session can see what it is being trusted with and when the next status is owed.
            _honest = M.N_ROSTER_HONEST % (
                len(_roster["writers"]),
                wl_roster.WRITER_CAP,
                len(_roster["readers"]),
                wl_roster.next_status_due(_roster),
                "\n".join(wl_roster.summary_lines(_roster)),
            )
            guide = _honest + ("\n\n" + guide if guide else "")
            guide_empty = False
    # ---- THE STAND-DOWN, a stricter second pass after the HONEST one: the cap-saturated wait (agent/plans/PLAN-stop-hook-cap-saturated-wait.md step 6) or focus mode (agent/plans/PLAN-stop-hook-focus-mode.md section 4), whose keep-lists live in wl_standdown. FOCUS governs when both hold: it is the operator's declaration, and its judge skip covers the cap wait's. The STATE.md demand
    # survives only when compaction is imminent (the late band, ~2% before auto-compact) and the document is not current.
    _profile = wl_standdown.FOCUS if _focus else wl_standdown.CAP_WAIT if _in_cap_wait else None
    if _profile is not None:
        _compaction_due = astate in (
            "missing",
            "thin",
            "bloated",
            "aimless",
            "stale",
            "waitled",
            "no-dir",
        ) and _ctx_late_band(session_id)
        _dropped = sorted(
            {
                v[0]
                for v in violations
                if not wl_standdown.keeps(_profile, v[0], v[1], _compaction_due)
            }
        )
        violations = [
            v for v in violations if wl_standdown.keeps(_profile, v[0], v[1], _compaction_due)
        ]
        if _compaction_due:
            _cnote = M.N_FOCUS_COMPACTION if _focus else M.N_CAP_WAIT_COMPACTION
            violations = [
                (k, a, t + "\n" + _cnote) if k in _profile.compaction_keys else (k, a, t)
                for k, a, t in violations
            ]
        if bgwait_due and not any(k == "bg-report" for k, _a, _t in violations):
            bgwait_due = False  # stood down, not delivered
        if _focus:
            state_doc.pop("capwait", None)
            _sd = state_doc.get("standdown")
            if not isinstance(_sd, dict) or _sd.get("focus_at") != _focus.get("at"):
                # A new focus: the batch clock starts now, so the first stop holds rather than releasing everything.
                _sd = {"focus_at": _focus.get("at"), "parked": {}, "adv_held": 0}
                _sd["batch_at"] = C.stamp_now()
            _sd["mode"], _sd["pr"] = _focus.get("mode"), _focus.get("pr")
            _parked = _sd.setdefault("parked", {})
            for _base in {str(k).split(":", 1)[0] for k in _dropped}:
                _parked[_base] = int(_parked.get(_base) or 0) + 1
            _sd["parked_now"] = len(_dropped)
            state_doc["standdown"] = _sd
            if not violations:
                # N_FOCUS replaces the guide on a focused allow; it is rendered after the drain, which is what knows how many advisories are held.
                guide, guide_empty = "", True
        else:
            state_doc["capwait"] = {
                "at": C.stamp_now(),
                "dropped": _dropped,
                "astate": astate,
                "compaction_due": _compaction_due,
            }
            if not violations:
                _rv = (
                    _roster or {}
                )  # never empty here: cap_saturated_wait is False without a roster
                _note = M.N_CAP_WAIT % (
                    len(_rv.get("writers") or ()),
                    wl_roster.WRITER_CAP,
                    ", ".join(str(w)[:8] for w in _rv.get("writers") or ()),
                    int(_rv.get("queued") or 0),
                    len(_dropped),
                    wl_roster.next_status_due(_rv),
                )
                _base = "" if _guide_empty_pre_roster else _guide_pre_roster
                guide = _note + ("\n\n" + _base if _base else "")
                guide_empty = False
    else:
        state_doc.pop("capwait", None)
    if bgwait_due:
        # Delivered for real (this stop emits it either way below), so the stamp the next check-in prints is banked here and saved eagerly:
        # the WORKLIST_FOCUS=off block path emits without saving.
        state_doc.setdefault("bgwait", {})["fired"] = C.stamp_now()
        S.save_state(worklist, session_id, state_doc)

    # ---- THE CADENCE GATE. One report turn between hook demands. ----------- Sits immediately before the block so every check has already been computed: a paused stop still KNOWS everything, it just does not spend the operator's turn demanding it again.
    cad = state_doc.setdefault("cadence", {})
    cad_off = os.environ.get("WORKLIST_CADENCE", "on").lower() in ("off", "0", "no")
    always_now = any(a for _k, a, _t in violations)
    # (F) THE MISSION TIER DEFEATS THE PAUSE, exactly as the always tier does, and this is the operator's sentence made executable: "There should be list of 'has to show with this order' until we check all of them, we should not be able to say 'but this stop is YOURS'."
    #
    # Guard (E) already refuses the pause while `actionable_remains` -- an open item, a pending task, a live lease -- and that covers `open-items`. It does NOT cover the shape the operator actually named: a red PR, an unticked program wave, a wave that never reached its finish line. None of those is a worklist item, so a session with an empty board and a red CI could be handed its
    # quiet turn while the thing it was ASKED to do sat unfinished. (F) is the difference between "nothing is in my queue" and "the job is done", and only the second one earns a stand-down.
    mission_now = any(check_tier(k) == T_MISSION for k, _a, _t in violations)
    rot_now = [k for k, a, _t in violations if not a]
    judge_now = any(k in JUDGE_TIER_KEYS for k, _a, _t in violations)
    msg_sig = hashlib.sha1((last_msg or "").encode("utf-8", "replace")).hexdigest()[:16]
    # (D) The cap resets whenever the outstanding set SHRINKS, mirroring exempt-overrun: a session that is actually clearing checks has earned another pause; one that is standing still has not.
    if len(rot_now) < int(cad.get("rot") or 0):
        cad["n"] = 0
    cad["rot"] = len(rot_now)
    pause = bool(
        violations
        and not cad_off
        and cad.get("owed") == "report"
        # (A) the always tier defeats the pause, unconditionally.
        and not always_now
        # (F) so does the mission tier -- see above.
        and not mission_now
        and rot_now
        # (B) only if the assistant actually SAID something new. Without this a session emits an empty turn after every block and buys a free allow every other stop -- the exact regression.
        and msg_sig != cad.get("msg")
        # (C) the judge and evidence tiers are never paused.
        and not judge_now
        # (E) NOTHING LEFT TO ADVANCE. Operator, 2026-08-27: the pause message fires "too often. It should be the last chance, since we usually have lots to do!"
        #
        # Guards (A)-(D) all ask about the CHECKS -- which tier, whether the message changed, how many pauses have been spent. None of them asks the only question that decides whether ending the turn is defensible: is there work in hand. So a session holding open items got its turn handed back for having produced a defensible report, which is exactly the bar CLAUDE.md refuses: "the
        # bar for stopping is 'there is genuinely nothing I can advance', not 'I have produced a defensible report'."
        #
        # `actionable_remains` is the file's existing answer to that question (open items, pending tasks, or a live `[>]` lease) and is already what the stuck gate consults, so the pause now reads the same fact they do rather than a second definition of "busy".
        #
        # CADENCE_MAX_PAUSES STAYS AT 3, deliberately, and the argument runs both ways. FOR lowering it to 1: the operator asked for a "last chance", and a cap of 1 makes that literal -- one stand-down per outstanding set, then demands forever. AGAINST, which is why it did not move: the cap and this guard measure different things, and with (E) in place the cap is no longer what was
        # misfiring. A stop that reaches here now has NOTHING actionable -- no open item, no task, no lease -- and what is outstanding is a rotating nag (docs drift, a dead loop, an uncited claim). Three quiet turns on a session with no work in hand is not the every-other-stop stand-down the operator described; it is the ordinary shape of a session waiting on something external.
        # Lowering the cap would also silently retune every WORKLIST_CADENCE_MAX-dependent case for a reason unrelated to the complaint. If routine pausing survives (E), lower it then, with the measurement that shows it -- not on the same hunch twice.
        and not actionable_remains
        and int(cad.get("n") or 0) < CADENCE_MAX_PAUSES
    )
    if pause:
        cad["owed"] = "demand"
        cad["msg"] = msg_sig
        cad["n"] = int(cad.get("n") or 0) + 1
        S.save_state(worklist, session_id, state_doc)
        # ALLOWED, but never SILENT. The checks are still outstanding and the operator still gets to see that they are; what the pause spends is the DEMAND, not the information. A pause that hid the list would be the mute button this design is supposed to avoid being.
        #
        # Nothing is skipped by exiting here. The judge only runs on a stop where `violations` is empty, and this branch is unreachable unless it is non-empty, so under the pre-cadence code this stop would have emitted a block and never consulted the judge either.
        C.emit(
            {
                "systemMessage": M.N_CADENCE_PAUSE
                % (
                    len(violations),
                    "; ".join(sorted(rot_now))[:180],
                    int(cad["n"]),
                    CADENCE_MAX_PAUSES,
                    # OWED OBLIGATIONS SURVIVE THE PAUSE INTACT. A
                    # session may defer its OWN work for a turn; deferring a waiting worker without telling it is a different thing, and the worker cannot see that this session stood down. Carried in full, not summarised -- the whole defect was a summary.
                    (
                        M.N_CADENCE_PAUSE_CARRIED
                        % "".join(
                            "\n".join("  " + ln for ln in _t.splitlines()) + "\n"
                            for _k, _a, _t in violations
                            if carried_through_pause(_k)
                        )
                        if any(carried_through_pause(_k) for _k, _a, _t in violations)
                        else ""
                    ),
                )
            }
        )
    elif violations:
        cad["owed"] = "report"
        cad["msg"] = msg_sig
        S.save_state(worklist, session_id, state_doc)
    # A CLEAN STOP CONSUMES THE DEBT. The hook owes a quiet turn to a session it just interrupted, not a voucher redeemable whenever that session next happens to be blocked.
    #
    # Found by case "a CLI-added item blocks like any open item": block, then a clean allow, then a new item -- and the new item was PAUSED, because the debt from the first block was still banked. The session had already been heard in between, so it was owed nothing; the effect was two consecutive allows and a new item that never once surfaced. That is not "1 report / 1 demand", it
    # is one demand and an indefinitely deferred pass.
    elif cad.get("owed") or cad.get("n"):
        cad.pop("owed", None)
        cad["n"] = 0
        S.save_state(worklist, session_id, state_doc)

    if violations and not pause:
        counter.write_text(str(int(counter.read_text()) + 1 if counter.exists() else 1))
        # The reggate fail-safe promises ONE line, never silence, even on a stop that blocks for other reasons. ci_report and queue_note ride along rather than blocking: a downgraded CI failure or a saturated queue must stay visible on a stop that blocks for something else.
        sysmsg_tail = (
            "" if not reg_forgot else " [reggate marker was corrupt; settled verdicts forgotten]"
        )
        extras = ("\n\n" + ci_report if ci_report else "") + (
            "\n\n" + queue_note if queue_note else ""
        )
        # THE ADVISORY QUEUE WAS STARVED BY A PRODUCTIVE SESSION: `outq_drain` runs on the allow path only, and measured 2026-09-17, ten parsed plan boxes went unseen across roughly twenty consecutive blocked stops. The digest (operator ruling 2026-09-24, "One quoted + others named") names up to OUTQ_DIGEST_MAX sections on every block and delivers the one-line ones outright; a
        # multi-line body stays queued for a clean stop, so the focused violation above is never displaced by a wall. The two CI notes are skipped because they already ride `extras` in full.
        if _focus_ended:
            # The parked summary in full, ahead of the digest, which would cap it at 150 characters.
            extras += "\n\n" + _focus_ended
            outq_forget(state_doc, "focus-ended", _focus_ended)
            S.save_state(worklist, session_id, state_doc)
        # FOCUS MODE BATCHES THE REST: only the PR's own advisories are named until the batch comes due (wl_standdown.FOCUS_BATCH_MIN), then everything once.
        _digest, _ = outq_digest(
            worklist,
            session_id,
            state_doc,
            skip=("ci-queue", "ci-report"),
            only=focus_advisory_filter(_focus, state_doc),
        )
        focus_advisory_bookkeeping(worklist, session_id, _focus, state_doc)
        if _digest:
            extras += "\n\n" + _digest
        onboard_marker = onboard.load_marker(session_id) if onboard else {}
        if onboard_marker.get("state") == "delivered":
            extras += "\n\n" + M.N_ONBOARD_DELIVERED % onboard_marker.get("epoch")
        if os.environ.get("WORKLIST_FOCUS", "on").lower() in ("off", "0", "no"):
            # EVERY violation is rendered on this path, so every display latch is genuinely spent. Saved explicitly because this branch emits (and therefore exits) without reaching the save below -- the same trap the queue's compute-time persistence was moved for.
            spend_display_latches([k for k, _a, _t in violations])
            S.save_state(worklist, session_id, state_doc)
            blocklog(worklist, me8, violations[0][0], [k for k, _a, _t in violations[1:]])
            C.emit(
                {
                    "systemMessage": "Stop hook: %d check(s) failed, continuing. %s%s"
                    % (
                        len(violations),
                        violations[0][2].split("\n")[0][:110],
                        sysmsg_tail,
                    ),
                    "decision": "block",
                    "reason": M.R_BLOCK
                    % (
                        len(violations),
                        "\n\n".join("  " + t for _k, _a, t in violations),
                        hook_file,
                    )
                    + extras
                    + guide_tail,
                }
            )
        # ---- v13 FOCUSED BLOCK (default). One rotating check per stop, the ALWAYS tier in full when present, everything else a bare count. The guide deliberately does NOT ride blocks any more (operator, 2026-07-31, superseding the v11 every-full-stop mandate); the wakeup section that used to ride beside it is gone entirely as of v18. The guide still leads every allow stop, and
        # the one check that needs store data (no-remaining) carries its own slice inside its text. Rotation is LRU over check KEYS: prune what is no longer outstanding, serve the least-recently-served, break ties by the battery's own order (which is already severity-shaped). Worst-case wait for any rotating check is (distinct outstanding checks - 1) stops.
        focus = state_doc.setdefault("focus", {})
        seq = int(focus.get("seq") or 0) + 1
        focus["seq"] = seq
        served = focus.setdefault("served", {})
        rot = [v for v in violations if not v[1]]
        outstanding = {k for k, _a, _t in rot}
        for k in [k for k in served if k not in outstanding]:
            del served[k]
        pick = None
        if rot:
            order = {v[0]: i for i, v in enumerate(rot)}
            # Covered keys sort LAST, and are NEVER removed from `violations`, so the header count stays truthful and nothing is silently forgotten. An intent reorders attention; it does not make work disappear.
            _covered = set((_intent or {}).get("covers") or [])
            # THE LADDER REPLACES LINE ORDER AS THE TIEBREAK, and its position in this key is the whole design decision -- so read the ordering before changing it.
            #
            # WHAT WAS WRONG: every never-served key ties at `-1`, and the tie was broken by `order[...]`, i.e. by where a `vadd` call happens to sit in a 5,000-line file. That is not a statement about priority, and it decided the FIRST pick of every crowded session. Measured on the failing night: 23 rotating keys sorted ahead of `no-waiter-asked`.
            #
            # WHY TIER SITS AFTER `served` AND NOT BEFORE IT. Before it, a T_MISSION check is re-picked on every single stop until satisfied and the lower tiers STARVE -- docs drift, a stale PR body and an unpushed submodule pointer become unreachable for as long as one item is open, which is most of a session. After it, the ladder is WALKED IN ORDER instead: on the first stop
            # every key is unserved, so tier decides and MISSION goes first; the next stop takes the next-most-stale, which is the highest remaining tier; and the cycle repeats by staleness with tier breaking every tie. That is the operator's sentence read literally -- "has to show with this order UNTIL WE CHECK ALL OF THEM" -- rather than "show the first one forever".
            #
            # The part of the request that starvation was reaching for is delivered by two other mechanisms, both stronger: T_MISSION defeats the cadence pause (guard F), so the session cannot be released while the job is unfinished, and the genuinely unskippable checks are invariants, which never enter this sort at all.
            pick = min(
                rot,
                key=lambda v: (
                    v[0] in _covered,
                    served.get(v[0], -1),
                    check_tier(v[0]),
                    order[v[0]],
                ),
            )
            served[pick[0]] = seq
        # The keys this stop will actually RENDER: every invariant (quoted in full or named in the collapse below -- either counts as shown, since both put the check in front of the reader) plus the one rotating pick.
        spend_display_latches(
            [k for k, a, _t in violations if a] + ([pick[0]] if pick is not None else [])
        )
        # THE ROTATING HINT RIDES A BLOCK TOO, at most once per BLOCK_HINT_MIN (agent/plans/PLAN-stop-hook-continuity.md P0.5). wl_hints says a hint "rides an output the stop was already going to produce", and a block is such an output; allow-only placement meant a busy session saw none of the corpus. Same ledger as the allow path, so the round-robin is shared.
        _block_hint = ""
        with contextlib.suppress(Exception):  # an advisory must never wedge a stop
            _hl = state_doc.setdefault("hints", {})
            _hage = C.stamp_age_min(_hl.get("block_at") or "")
            # Not in focus mode: the wind-down spends no tokens on advice.
            if not _focus and (_hage is None or _hage >= BLOCK_HINT_MIN):
                _hpick = wl_hints.hint_pick(wl_hints.load_corpus(wl_hints.hints_path(root))[0], _hl)
                if _hpick:
                    _block_hint = "\n\n" + wl_hints.render(*_hpick)
                    _hl["block_at"] = C.stamp_now()
        S.save_state(worklist, session_id, state_doc)
        # ---- THE COLLAPSE. Invariants are ORDERED by the ladder (not by where their vadd sits in this file), at most ALWAYS_FULL_MAX are QUOTED in full, and every remaining one is NAMED on one line with its opening sentence.
        #
        # The tier buys UN-ROTATABILITY, and that is all it should buy. This file's own warning at the sweep prompt -- "a prompt that fires always is a prompt that gets skimmed" -- is the constraint, and three promotions in one change is exactly when it starts to bite: five full blocks on one stop is not five times the attention, it is one skim.
        #
        # NOTHING IS DROPPED, and that is the difference between this and rotation. Every invariant is named on every stop; at most two are quoted. A named one still tells the session which obligation exists and, because these messages all put their verdict on line one, roughly what it is.
        _inv = sorted(
            ((k, t) for k, a, t in violations if a),
            key=lambda kt: check_tier(kt[0]),
        )
        shown = [t for _k, t in _inv[:ALWAYS_FULL_MAX]]
        _named = _inv[ALWAYS_FULL_MAX:]
        if _named:
            shown.append(
                M.R_ALWAYS_COLLAPSED
                % "\n".join(
                    "    %s: %s" % (k, (t.splitlines() or [""])[0][:150]) for k, t in _named
                )
            )
        if pick is not None:
            shown.append(pick[2])
        # ---- THE ROTATING TAIL IS NAMED, NOT COUNTED (operator ruling 2026-09-24, /ask: "One quoted + others named", agent/plans/PLAN-stop-hook-continuity.md P0.1). A bare "N more" cost N full turns to learn what N was; one line each costs a few hundred characters and lets the session work the whole set in one turn. Only the pick is QUOTED, so only the pick spends a display latch
        # (above), and the LRU order is untouched: the next stop still quotes the next-most-stale check in full.
        _rot_named = sorted(
            (v for v in rot if pick is None or v[0] != pick[0]),
            key=lambda v: (served.get(v[0], -1), check_tier(v[0])),
        )
        if _rot_named:
            shown.append(
                M.R_ROTATING_COLLAPSED
                % "\n".join(
                    "    %s: %s" % (k, (t.splitlines() or [""])[0][:150]) for k, _a, t in _rot_named
                )
            )
        # COUNTED AGAINST THE VIOLATIONS, not against `shown`. `shown` may now carry one synthetic entry (the collapse block) and fewer entries than invariants, so `len(violations) - len(shown)` would report a number that is not the number of anything. What the reader needs is how many outstanding checks got neither a quote nor a name, which is exactly the rotating ones this stop
        # did not pick.
        n_more = len(rot) - (1 if pick is not None else 0)
        _lead_key = pick[0] if pick is not None else _inv[0][0]
        blocklog(worklist, me8, _lead_key, [k for k, _a, _t in violations if k != _lead_key])
        C.emit(
            {
                # SURFACED, not len(shown): `shown` may carry the synthetic collapse block, which is one entry standing for several checks. Every invariant is surfaced (quoted or named) plus at most one rotating pick.
                "systemMessage": "Stop hook: %d check(s) outstanding, surfacing %d.%s"
                % (len(violations), len(_inv) + (1 if pick is not None else 0), sysmsg_tail),
                "decision": "block",
                "reason": M.R_BLOCK_FOCUS
                % (
                    "\n\n".join(shown),
                    M.R_FOCUS_MORE % n_more if n_more else M.R_FOCUS_ONLY,
                    hook_file,
                    me8,
                )
                + extras
                + _block_hint,
            }
        )

    # ---- static checks clean. Ask a model whether stopping is honest. ------- v7: a fix-signal stop consults the judge even with an empty queue, because "I fixed it, all done" is exactly the stop the regression question exists for. v10: an identical world and message within the cache TTL reuses the last clean "stop" verdict instead of re-paying the call; fix signals always miss
    # (they change the world signature).
    #
    # v12 DEFERRAL AUDIT (operator: "Haiku should ask 'Why' and 'How' questions... there is no human rights with him"). Aged JUSTIFIED deferrals ride the same judge call as an extra section, so a stop never pays a second model invocation; unjustified ones were demanded statically above and never reach here. Bounded batch, oldest first, and a banked "valid" verdict is keyed to the
    # item's upd stamp, so an untouched item is interrogated exactly once per generation.
    audit_cache = state_doc.setdefault("defer_audit", {})
    for k in [k for k in audit_cache if k not in fold.by_id]:
        del audit_cache[k]  # its item is gone; a banked verdict for it is litter
    audit_batch = []
    # The deferral audit rides the judge call, which a cap-saturated wait and focus mode skip.
    if not wl_judge.JUDGE_DISABLED and not _in_standdown:
        for r in sorted(
            deferred_recs,
            key=lambda r: (-(C.stamp_age_min(r.get("upd", "")) or 0), r.get("id", "")),
        ):
            age = C.stamp_age_min(r.get("upd", "")) or 0
            if age < S.DEFER_AUDIT_MIN:
                break  # sorted oldest-first: everything after is younger
            if not C.DEFAULT_TOKEN.search(r["line"]) or not deferral_is_justified(r):
                continue
            banked = audit_cache.get(r["id"])
            if (
                isinstance(banked, dict)
                and banked.get("stamp") == r.get("upd")
                and banked.get("verdict") == "valid"
            ):
                continue
            audit_batch.append(r)
            if len(audit_batch) >= S.DEFER_AUDIT_BATCH:
                break
    # DEFER-SETTLE (wl_defersettle): aged [?] items carrying a Python-checked fact ride the same judge call, asked whether the fact already settles them. Never blocks and never fails closed; see that module's FAIL SEMANTICS.
    settle_batch = []
    with contextlib.suppress(Exception):
        settle_batch = wl_defersettle.build_batch(
            root, state_doc, deferred_recs, disabled=wl_judge.JUDGE_DISABLED or _in_standdown
        )
    # ADMISSION DETECTOR (wl_admit.py). The prefilter runs on every stop, above the block exit, and is measured at under 0.4 ms with zero tokens, firing on ~1% of real turns. It decides only whether to SPEND a model call; it is never the last word on a negative, because the regexes provably miss the euphemistic phrasings.
    #
    # Tier R recorded the hit up there, before anything that can fail. A hit banked only after a successful verdict would vanish exactly when the judge times out, which is when the record matters most.
    # THE JUDGE-SKIPPED PATH. The main judge runs only when something remains or a fix signal fired. A stop with a clean board and an admission in its final message would otherwise be seen by nobody, and that is a likely shape: the session finished its work, and says on the way out that it broke something along the way.
    # A cap-saturated wait skips the main judge (below), so an admission then takes this path: an admission of breakage must never go unseen.
    if admit_hits and not (
        (something_remains or reg_signals) and not wl_judge.JUDGE_DISABLED and not _in_standdown
    ):
        _ad, _aerr = wl_judge.run_admission(admit_text)
        if _aerr:
            # Recorded, never raised. Tier R already holds the hit, so the admission survives an unavailable judge; this only adds why.
            wl_admit.record_hits(
                worklist,
                session_id,
                admit_hits,
                admit_sig,
                extra={"verdict": "error", "detail": _aerr[:200]},
            )
        else:
            wl_admit.process_admission(
                _ad,
                admit_text,
                worklist,
                session_id,
                me8,
                admit_hits,
                admit_sig,
                admit_settled,
                S.add_item,
            )
        admit_hits = []
    # THE INDEX REFRESH RUNS ON EVERY STOP THAT GETS THIS FAR (agent/plans/PLAN-stop-hook-refactor-enforcement.md, Commit 1): a mechanical counter run with no model call, and the ONLY thing that re-emits the commit-path guard's cache (`.ci/cache/shape-index/`). It first sat behind `judged_ok`, which left the guard disarmed for 36+ minutes of `continue` verdicts. Its second home was still inside the judge section, after `C.emit` on the `continue` verdict and on the deferral-audit blocks -- and `C.emit` calls `sys.exit` -- so a `continue` still exited before it ran, and a stop with nothing remaining and no fix signal never entered the section at all (found 2026-09-24 by the wide-tier writer, verified against wl_core.emit). Here it precedes every judge exit.
    try:
        sd_findings, sd_cerr = wl_shapedup.refresh_index(str(root), state_doc)
    except Exception as exc:  # noqa: BLE001 -- an advisory rule must never wedge a stop
        sd_findings, sd_cerr = [], "shape index refresh errored: %s" % exc
    S.save_state(worklist, session_id, state_doc)
    audit_note = ""
    judge_cached = False
    # THE JUDGE STANDS DOWN IN A CAP-SATURATED WAIT (agent/plans/PLAN-stop-hook-cap-saturated-wait.md step 7). Its orders ("Do the next action", SWEEP THE CLASS, PROOF OBLIGATION) cannot be acted on with every writer slot full; on 2026-09-24 it blocked twice with a reason that itself called the wait legitimate. Unsettled regression fix-sets are not lost: the marker advances
    # only when a fix-set settles, so the next unsaturated stop asks again.
    if (something_remains or reg_signals) and not wl_judge.JUDGE_DISABLED and not _in_standdown:
        streak = int(counter.read_text()) if counter.exists() else 0
        # THE JUDGE IS ASKED ABOUT ITS OWN HISTORY, not the battery's. `counter` counts every stop block from every check; the prompt calls the number "times this gate has already said continue" and tells the judge to distrust itself above 3. On 2026-09-04 it read 69 while the judge had spoken a handful of times. See wl_judge.continue_streak.
        judge_log = wl_judge.judge_log_path(worklist, me8)
        judge_streak = wl_judge.continue_streak(judge_log)
        reg_scripts = wl_reggate.package_scripts(root) if reg_signals else {}
        # GROUND THE JUDGE IN A REAL FILE LIST, computed here rather than left to the model's own prose: twice in one session the judge fabricated a "bulk transform" naming files that did not exist anywhere in the tree, pattern-matching a worked example in PF.PROOF_PROMPT rather than reading the actual diff (agent/plans/PLAN-judge-prompt-trap-conflation.md). Computed
        # UNCONDITIONALLY (one cheap git call when reg_ids is empty) so a follow-up proof/sweep question on a later stop is grounded too, not only a fresh fire.
        reg_fixset_files, reg_fixset_provenance = [], None
        with contextlib.suppress(Exception):
            reg_fixset_files, reg_fixset_provenance = wl_reggate.fixset_files(
                root,
                reg_ids,
                live_paths=wl_roster.live_writer_paths(event.get("cwd"), session_id, event),
            )
        reg_extra = ""
        # v19: the claim-check profile for the ONE tick this fix-set is about, or None when no claim was put to the judge. `claim_prior` is the latch record as it stood BEFORE the ask, which is what makes the fire count increment by one rather than reset. See wl_claimcheck.
        claim_prof, claim_prior = None, None
        if reg_signals:
            reg_extra = M.REGGATE_PROMPT % {
                "fixset": "\n".join("  " + s for s in reg_signals[:12]),
                "keys": "\n".join(
                    "  " + k for k in sorted(k for k in reg_scripts if k.startswith("check:"))
                )
                or "  (none)",
            }
            # ARTIFACT-DERIVED HINT, appended only when git says every non-bookkeeping file in the fix-set is gate machinery. It never skips a fix-set; it gives question (0) something to bite on. See wl_reggate.gate_only_fixset. Suppressed on any failure: a hint must never raise into the stop path.
            with contextlib.suppress(Exception):
                if wl_reggate.gate_only_fixset(root, reg_ids):
                    reg_extra += M.REGGATE_GATE_MAINTENANCE
            # DOES THE EVIDENCE DEMONSTRATE THE CLAIM. One more question on the judge call the fix signal already forces, never a second call -- the same trade the class sweep and the proof obligation make. Asked ONLY on a TICK-based fix-set: a commit-only fix-set carries no completion claim, and the fix-set's own file list is reused rather than recomputed. The latch bounds the
            # ask for the path where the regression gate BLOCKS instead of settling; a settled fix-set is absorbed above and never reaches here again. Suppressed on any failure: an advisory must never raise into the stop path.
            with contextlib.suppress(Exception):
                if reg_new_ticks and not wl_claimcheck.exhausted(reg_sig):
                    _prof = wl_claimcheck.profile(root, reg_new_ticks[0][2], reg_fixset_files)
                    # v20: when the claim names a plan box, the investigation row written BEFORE the work rides along. No new judge call and no change to this rule's advisory character -- the judge was being asked whether the evidence demonstrates the claim while a written statement of what the session found first sat unread in a committed ledger. None for an ordinary worklist
                    # tick, which is the common case, and an absent row is never reported as a gap here: whether a box may close without one is --plan-tick's mechanical refusal, not a judgement.
                    _section = wl_claimcheck.prompt_section(
                        _prof, wl_claimcheck.investigation_for_claim(root, reg_new_ticks[0][2])
                    )
                    if _section:
                        reg_extra += _section
                        claim_prof = _prof
                        claim_prior = wl_claimcheck.demand_for(reg_sig).peek()
        audit_extra = ""
        if audit_batch:
            arows = []
            for r in audit_batch:
                j = S.deferral_justification(r)
                arows.append(
                    "  id=%s  sat %dm  %s\n    WHY: %s\n    HOW: %s%s"
                    % (
                        r["id"],
                        C.stamp_age_min(r.get("upd", "")) or 0,
                        r["text"][:160],
                        j.get("why", "(none)")[:200],
                        j.get("how", "(none)")[:200],
                        "".join(
                            "\n    %s: %s" % (k.upper(), j[k][:120])
                            for k in ("tried", "needs", "blocked_on")
                            if j.get(k)
                        ),
                    )
                )
            audit_extra = M.DEFER_AUDIT_PROMPT % {
                "n": len(audit_batch),
                "window": S.DEFER_WINDOW_MIN,
                "items": "\n".join(arows),
            }
        verdict = None
        if not reg_signals and not audit_batch and not settle_batch:
            verdict = wl_judge.cached_stop_verdict(state_doc, cur_sig, last_msg)
            judge_cached = verdict is not None
        err = None
        if verdict is None:
            # The judge's loop line prefers the COMPUTED truth from the live cron expansion; the declared .loop record is only the fallback when no cron is visible, because its stamped next-fire goes stale on write (operator, 2026-07-30: the hook was not giving the correct message).
            if live_work_crons:
                _wc = live_work_crons[0]
                _wnext = C.cron_next(str(_wc.get("schedule", "")))
                _wlabel = (str(_wc.get("prompt", "")).strip().splitlines() or ["unlabelled"])[0][
                    :70
                ]
                loop_desc = "%s, next fire %s (%d cron%s, live schedule %s)" % (
                    _wlabel,
                    _wnext.strftime("%Y-%m-%dT%H:%M:%SZ") if _wnext else "unparseable",
                    len(live_work_crons),
                    "" if len(live_work_crons) == 1 else "s",
                    _wc.get("schedule", "?"),
                )
            elif lstate == "none":
                loop_desc = "none declared"
            else:
                loop_desc = "%s, next fire %s (%d cron%s)" % (
                    llabel or "unlabelled",
                    lnext.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    lcrons,
                    "" if lcrons == 1 else "s",
                )
            queue_extra = (
                "\nNOTE: the CI queue on the publish ref is SATURATED and the "
                "session has been instructed to work locally and not push this "
                "turn; do not direct it to push.\n"
                if queue_note
                else ""
            )
            # v15: waiting on background workers with nothing else pending is a recognized state; the judge must not manufacture work for it.
            if live_bg and not open_items and bg_facts:
                queue_extra += (
                    "\nNOTE: the session is in a recognized PURE BACKGROUND "
                    "WAIT (%d live worker(s); the hook checks their output "
                    "streams every %d min). Waiting is legitimate here; do "
                    "not direct the session to find unrelated work.\n"
                    % (len(live_bg), wl_liveness.BG_REPORT_MIN)
                )
            verdict, err = wl_judge.run_judge(
                remaining_lines,
                len(in_flight),
                last_msg,
                judge_streak,
                loop_desc,
                cited_excerpts(root, last_msg),
                extra=reg_extra
                + audit_extra
                + wl_defersettle.prompt_section(settle_batch)
                + queue_extra
                # Only on a firing stop, so an ordinary judge call is byte-identical to what it was before this existed.
                + (M.ADMISSION_PROMPT if admit_hits else ""),
                # Headings only (operator decision 2026-07-30): titles of hard-won facts let the judge tell a real constraint from an excuse, without turning a file designed to grow forever into a per-stop cost multiplier.
                #
                # COST IS STATED PER HEADING, DELIBERATELY, because the total is a moving target and every attempt to pin it here has rotted. It read "~145 tokens" and was stale by ~5x. That was corrected to a measured 43-heading total on 2026-08-23, and the very next appended entry staled it again -- twice more the same day, at 44 and 45. Three corrections in one session is the
                # file telling you the shape of the number is wrong, not the value.
                #
                # Measured 2026-08-23 over 45 real headings: ~70 chars each once the " - " prefix is counted, so ~17 tokens per entry. Multiply by `grep -c '^## ' docs/agent-reference/TRAPS.md`
                # for today's figure rather than trusting a number written
                # here. The ceiling is bounded by S.TRAP_HEADING_CAP: at 120 headings that is ~8,400 chars, ~2,100 tokens, which is the only figure in this comment that cannot rot, because the cap is enforced in code at wl_store.trap_headings().
                traps=S.trap_prompt_lines(root),
                fixset_files=reg_fixset_files,
                fixset_provenance=reg_fixset_provenance,
                transcript=event.get("transcript_path") or None,
                fixset_instance=(
                    (str(root), list(reg_ids)) if reg_fixset_provenance == "diff-tree" else None
                ),
            )
        if err is not None:
            # FAIL CLOSED, by operator instruction. A judge that cannot answer must not become the way out.
            counter.write_text(str(streak + 1))
            wl_judge.log_verdict(judge_log, "unavailable", "", err)
            blocklog(worklist, me8, "judge-unavailable", judge={"error": err[:160]})
            C.emit(
                {
                    "systemMessage": "Stop hook: judge unavailable (%s). Blocking, per "
                    "no-escape-hatch." % err[:110],
                    "decision": "block",
                    "reason": M.R_JUDGE_UNAVAILABLE % (err, hook_file, wl_judge.JUDGE_MODEL)
                    + guide_tail,
                }
            )
        # UNGROUNDED SWEEP AND PROOF FIRES (R20260924.19): queued, never blocked on, and before any path below that can exit. STICKY, because the fix-set that raised one is banked and never re-asked.
        for _adv in verdict.get("advisories") or []:
            outq_add(worklist, session_id, state_doc, "sweep-ungrounded", str(_adv), 2, sticky=True)
        # DEFER-SETTLE VERDICT: banks, corroborates, and acts only through wl_defersettle's own evidence-gated tick. It cannot block, so it runs before any path below that can exit.
        if settle_batch:
            with contextlib.suppress(Exception):
                for _ds_note in wl_defersettle.apply_stop(
                    verdict, settle_batch, state_doc, root, worklist
                ):
                    outq_add(
                        worklist, session_id, state_doc, "defer-settle", _ds_note, 2, sticky=True
                    )
            S.save_state(worklist, session_id, state_doc)
        # ADMISSION VERDICT. Processed first and separately, because unlike every other verdict here it CANNOT block: its whole consequence is one tracked item. The Stop battery already refuses to end a turn while an item tagged with this session is open, so detection borrows proven enforcement instead of adding another blocking path.
        if admit_hits:
            wl_admit.process_admission(
                verdict.get("admission"),
                admit_text,
                worklist,
                session_id,
                me8,
                admit_hits,
                admit_sig,
                admit_settled,
                S.add_item,
            )
            admit_hits = []  # handled; the standalone path below must not re-ask

        # v19: THE CLAIM-CHECK VERDICT, read before the regression gate and entirely outside it. It cannot block, and it must not sit behind a path an earlier emit() exits past: the reggate's malformed and block arms both emit and END THE PROCESS, so an advisory computed after them would be lost on exactly the stops that carry the most evidence. Nothing here writes to
        # `verdict`; the advisory reaches the session through the report queue, which drains on the allow path. See wl_claimcheck's ADVISORY, NEVER BLOCKING.
        claim_record = None
        if claim_prof is not None:
            claim_kind, claim_note = wl_claimcheck.apply_verdict(verdict, claim_prof)
            claim_record = {
                "kind": claim_kind,
                "shape": claim_prof["shape"],
                "note": claim_note[:200],
            }
            # BANKED ON THE ASK, not on the answer. What this latch bounds is the ASKING, so a degraded answer that left the count untouched would make a malfunctioning judge the way to be asked forever.
            with contextlib.suppress(Exception):
                wl_claimcheck.demand_for(reg_sig).bank(
                    {"sig": reg_sig, "kind": claim_kind}, claim_prior
                )
            # ONE ROW PER VERDICT, so the graduation criterion in wl_claimcheck's docstring is answerable from rows rather than from memory. Suppressed: a census must never raise into gating.
            with contextlib.suppress(Exception):
                wl_claimcheck.census(
                    root,
                    {
                        "sig": reg_sig,
                        "kind": claim_kind,
                        "shape": claim_prof["shape"],
                        "cites": [
                            {"cite": c["cite"], "verdict": c["verdict"], "overlap": c["overlap"]}
                            for c in claim_prof["citations"]
                        ],
                        "fixset_n": claim_prof["fixset_n"],
                        "note": claim_note[:300],
                    },
                )
            if claim_kind in ("yes", "degraded"):
                # NEITHER OF THESE EARNS A REPORT SLOT, and the suite proved it rather than a reviewer: a degraded verdict queued at priority 2 pushed the regression gate's own "settled as one-off" line out of the per-stop drain window, so an advisory that had learned NOTHING displaced the outcome of the question that did. Both still reach the session, in the one field it always
                # reads, exactly as wl_judge annotates a degraded class_sweep. The census row carries the verdict either way.
                verdict["reason"] = (
                    "%s [claim-check: %s]" % (verdict.get("reason", ""), claim_kind)
                )[:400]
            else:
                # STICKY: the latch and the fixset record both suppress a re-ask, so this text cannot be regenerated on a later stop and a volatile entry would simply be lost. Priority 2, the same class as the other one-line outcomes, which keeps it behind every real violation.
                outq_add(worklist, session_id, state_doc, "claim-check", claim_note, 2, sticky=True)

        # v7: the regression verdict is processed BEFORE the stop/continue verdict, so a settle persists (and a regression block fires) even when the judge would also say continue for other reasons.
        if reg_signals:
            kind, payload, detail = wl_reggate.apply_regression_verdict(
                verdict.get("regression_gate"),
                reg_scripts,
                root,
                reg_state,
                reg_sig,
                lines,
                me8,
            )
            wl_reggate.save_reggate(reg_marker, reg_state)  # persist gate_runs regardless
            if kind == "malformed":
                counter.write_text(str(streak + 1))
                blocklog(
                    worklist, me8, "reggate-malformed", judge=judge_flags(verdict, "malformed")
                )
                C.emit(
                    {
                        "systemMessage": "Stop hook: fix landed but the judge "
                        "returned no usable regression_gate. Blocking, per "
                        "no-escape-hatch.",
                        "decision": "block",
                        "reason": M.R_REGGATE_MALFORMED % (payload, hook_file) + guide_tail,
                    }
                )
            if kind == "settle":
                rg = verdict.get("regression_gate") or {}
                reg_state["fixsets"][reg_sig] = {
                    "verdict": payload,
                    "existing_gate": str(rg.get("existing_gate", ""))[:100],
                    "blind_spot": str(rg.get("blind_spot", ""))[:300],
                    # THE ROUTING IS EVIDENCE, so it is kept. Found by dogfooding on 2026-08-24: sixteen settled fixsets, not one carrying a surface, because the judge produced it, apply_regression_verdict routed the proof with it, and the settle path dropped it. That makes the one question worth asking of this machinery -- "is the routing any good?" -- unanswerable from the
                    # record. It had already misrouted a www DOM change to packages/e2e-tests, and nothing recorded that.
                    "surface": str(rg.get("surface", ""))[:20],
                    "artifact": str(rg.get("artifact", ""))[:200],
                    # THE CLAIM VERDICT SETTLES WITH THE FIX-SET, on the same stop and under the same key, so a claim is asked about exactly once -- the identical mechanism that makes the regression gate cost-bounded. `None` when no claim was put (a commit-only fix-set, or the latch was already spent) and that is not the same as a claim that passed; the census rows carry the
                    # verdicts, this field carries only the fact that this fix-set's claim was answered.
                    "claim_check": claim_record,
                    "at": C.stamp_now(),
                }
                reg_state["head"] = reg_head or reg_state["head"]
                reg_state["seen_ticks"] = sorted(
                    set(reg_state["seen_ticks"])
                    | {t for t, _ln, _ev in reg_new_ticks}
                    | set(reg_banked)
                )
                wl_reggate.save_reggate(reg_marker, reg_state)
                # The fix-set is settled and is absorbed on every later stop, so the claim latch has nothing left to bound; dropping its marker keeps the judge's tmp directory from accumulating one file per fix-set ever seen.
                with contextlib.suppress(Exception):
                    wl_claimcheck.demand_for(reg_sig).clear()
                reg_settled = (payload, detail)
                # SPEND THE BUDGET, and only here. `proven` is the one settle that cost a real artifact and a real CI round; the cheap settles (covered/one-off/not-applicable/deferred) cost neither, and charging them would let a session farm the budget with five honest one-offs to buy a pass on the sixth, real gate. Suppressed on failure: the ledger must never raise into gating.
                if payload == "proven":
                    with contextlib.suppress(Exception):
                        wl_reggate.charge(C.git_branch(root), reg_sig, "proven")
                # STICKY: the fixset is persisted, so every later stop absorbs this verdict silently and the text never returns.
                outq_add(
                    worklist,
                    session_id,
                    state_doc,
                    "reg-settled",
                    "Regression gate: fix-set %s settled as %s (%s); it will not be asked again."
                    % (reg_sig[:8], reg_settled[0], (reg_settled[1] or "")[:160]),
                    # PRIORITY 2, NOT 1, and the difference was measured: 25 of the 33 sections queued in one long session were these one-line outcomes, and at priority 1 they drained first, one per stop, ahead of every actionable priority-2 section (open plan boxes, unread sub-agent reports, refused questions), which therefore never surfaced. See outq_drain's digest for the other
                    # half.
                    2,
                    sticky=True,
                )
            if kind == "block":
                # ---- THE EFFORT CAP (operator ruling 2026-09-05T01:55Z) ------ The judge was still ASKED and still ANSWERED: the finding above is fully computed and every claim already verified against artifacts. Only its SCHEDULE changes here. A cap that skipped the question would produce a debt with no content, which is indistinguishable from the machinery breaking.
                #
                # Failure is suppressed and falls through to the normal block:
                # if the ledger cannot be read, the cap does not fire, so a
                # broken ledger can only make the hook STRICTER, never laxer.
                capped = False
                with contextlib.suppress(Exception):
                    br = C.git_branch(root)
                    charged, remaining, _debts, forgot = wl_reggate.budget_state(br, root)
                    if not forgot and remaining <= 0:
                        rg = verdict.get("regression_gate") or {}
                        wl_reggate.append_ledger(
                            br,
                            {
                                "kind": "debt",
                                "sig": reg_sig,
                                "blind_spot": str(rg.get("blind_spot", ""))[:300],
                                "surface": str(rg.get("surface", ""))[:20],
                                "artifact": str(rg.get("artifact", ""))[:200],
                                "charged": charged,
                            },
                            root=root,
                        )
                        wl_reggate.charge(br, reg_sig, "capped")
                        reg_state["fixsets"][reg_sig] = {
                            "verdict": "capped",
                            "existing_gate": "",
                            "blind_spot": str(rg.get("blind_spot", ""))[:300],
                            "surface": str(rg.get("surface", ""))[:20],
                            "artifact": str(rg.get("artifact", ""))[:200],
                            "at": C.stamp_now(),
                        }
                        wl_reggate.save_reggate(reg_marker, reg_state)
                        outq_add(
                            worklist,
                            session_id,
                            state_doc,
                            "reg-capped",
                            "Regression gate CAPPED at %d/%d on branch %s: fix-set %s "
                            "is now a tracked DEBT, not a dropped finding. It returns "
                            "as a hard block when the branch lands or after %dm."
                            % (
                                charged,
                                wl_reggate.REGGATE_CAP,
                                br,
                                reg_sig[:8],
                                wl_reggate.REGGATE_DEBT_GRACE_MIN,
                            ),
                            1,
                            sticky=True,
                        )
                        capped = True
                if not capped:
                    counter.write_text(str(streak + 1))
                    # EVERY OBLIGATION THIS VERDICT FIRED, IN ONE BLOCK (agent/plans/PLAN-stop-hook-continuity.md P2.7). The class sweep and the proof order were already written into the verdict's reason and next_action by `wl_rules.apply_order`, and emitting the gate payload alone dropped them until a later judged stop re-asked, one obligation per turn. Rendering only: the judge call and the demand markers are unchanged.
                    _also = ""
                    if verdict.get("verdict") == "continue" and (
                        verdict.get("reason") or verdict.get("next_action")
                    ):
                        _also = M.R_REGGATE_ALSO % (
                            str(verdict.get("reason") or "")[:700],
                            str(verdict.get("next_action") or "")[:200],
                        ) + wl_rules.render_owed(verdict)
                    blocklog(worklist, me8, "reggate", judge=judge_flags(verdict, kind))
                    C.emit(
                        {
                            "systemMessage": "Stop hook: a fix landed with no "
                            "regression gate (fix-set %s). Blocking." % reg_sig[:8],
                            "decision": "block",
                            "reason": payload + _also + guide_tail,
                        }
                    )
        # v12: the audit verdicts are processed BEFORE stop/continue, same precedence argument as the regression gate: a banked "valid" must persist, and a do_now must fire, whatever the judge said about the stop itself.
        if audit_batch:
            akind, avalids, aorders = wl_judge.apply_defer_audit(
                verdict.get("defer_audit"), audit_batch
            )
            if akind == "malformed":
                counter.write_text(str(streak + 1))
                blocklog(worklist, me8, "defer-audit-malformed", judge=judge_flags(verdict))
                C.emit(
                    {
                        "systemMessage": "Stop hook: a deferral audit was "
                        "requested but the judge returned no usable "
                        "defer_audit. Blocking, per no-escape-hatch.",
                        "decision": "block",
                        "reason": M.R_AUDIT_MALFORMED
                        % (repr(verdict.get("defer_audit"))[:200], hook_file)
                        + guide_tail,
                    }
                )
            for rid, stamp, reason in avalids:
                audit_cache[rid] = {
                    "stamp": stamp,
                    "verdict": "valid",
                    "reason": reason[:160],
                    "at": C.stamp_now(),
                }
            S.save_state(worklist, session_id, state_doc)
            if avalids:
                audit_note = M.N_DEFER_AUDIT_OK % (
                    len(avalids),
                    "\n".join("  #%s: %s" % (rid, reason[:160]) for rid, _st, reason in avalids),
                )
                # STICKY: the verdicts were banked into defer_audit above, and a banked item is never interrogated again at that stamp, so this note cannot be regenerated.
                outq_add(worklist, session_id, state_doc, "audit", audit_note, 1, sticky=True)
            if aorders:
                # The REOPEN is the enforcement: a rejected deferral becomes an ordinary open [ ] item, so the existing open-items machinery (and the tick evidence gate) owns it from here. The exits are the open item's exits: do it and tick with evidence, or re-defer with a justification that carries the fact the judge missed -- which is itself re-audited.
                for rid, order in aorders:
                    S.set_state(
                        worklist,
                        "judge",
                        rid,
                        " ",
                        "REOPENED by the stop-gate judge: %s" % order[:160],
                    )
                counter.write_text(str(streak + 1))
                blocklog(worklist, me8, "defer-audit", judge=judge_flags(verdict))
                C.emit(
                    {
                        "systemMessage": "Stop hook: the deferral audit "
                        "rejected %d justification(s); those items are open "
                        "work again." % len(aorders),
                        "decision": "block",
                        "reason": M.V_DEFER_AUDIT
                        % (
                            len(aorders),
                            "\n".join("  #%s  ORDER: %s" % (rid, order) for rid, order in aorders),
                            me8,
                        )
                        + guide_tail,
                    }
                )
        judged_ok = verdict["verdict"] == "stop"
        wl_judge.log_verdict(judge_log, verdict["verdict"], verdict.get("reason", ""))
        if verdict["verdict"] == "continue":
            counter.write_text(str(streak + 1))
            blocklog(worklist, me8, "judge", judge=judge_flags(verdict))
            C.emit(
                {
                    "systemMessage": "Stop hook: judge says continue (%d in a row). %s"
                    % (judge_streak + 1, verdict["reason"][:110]),
                    "decision": "block",
                    "reason": M.R_JUDGE_CONTINUE
                    % (
                        # The STILL OWED lines ride directly under the reason, each on its own line and outside every cap (R20260924.18).
                        verdict["reason"] + wl_rules.render_owed(verdict),
                        verdict["next_action"],
                        "\n".join("  " + r for r in remaining_lines[:12]),
                    )
                    + guide_tail,
                }
            )
        # IS THIS THE NTH COPY. The third judged rule, and the only one that does NOT ride the judge's call: the trim that was supposed to pay for a fourth object in that prompt freed 62 characters, not the ~2,300 the plan estimated, and a fix stop already carries ~17,700 characters of rubric across three calibrated sections. So it makes its own `claude -p`, and earns it by being
        # rare -- a MECHANICAL counter gates the call, and only a shape that was not in the seed and has just reached its third copy opens it.
        #
        # ON THE ALLOW PATH ONLY, deliberately. A judge that already said continue has placed an order; a second order in the same block is how a block stops being read (the same argument wl_judge makes for skipping brave_default after the sweep fires). The shape is still there next stop.
        if judged_ok:
            try:
                if sd_findings is None:
                    sd_fired, sd_reason, sd_action, sd_note = False, "", "", ""
                else:
                    sd_fired, sd_reason, sd_action, sd_note = wl_shapedup.judge(
                        str(root), sd_findings, sd_cerr
                    )
            except Exception as exc:  # noqa: BLE001 -- an advisory rule must never wedge a stop
                sd_fired, sd_reason, sd_action, sd_note = (
                    False,
                    "",
                    "",
                    "shape rule errored: %s" % exc,
                )
            S.save_state(worklist, session_id, state_doc)
            if sd_note:
                # A paid question that produced no answer must still be visible; this rule never fails closed (see wl_shapedup FAIL SEMANTICS).
                outq_add(worklist, session_id, state_doc, "shapedup", sd_note[:300], 2)
            if sd_fired:
                counter.write_text(str(streak + 1))
                blocklog(worklist, me8, "shapedup", judge=judge_flags(verdict))
                C.emit(
                    {
                        "systemMessage": "Stop hook: a shape reached its Nth copy. %s"
                        % sd_reason[:110],
                        "decision": "block",
                        "reason": M.R_JUDGE_CONTINUE
                        % (
                            sd_reason,
                            sd_action,
                            "\n".join("  " + r for r in remaining_lines[:12]),
                        )
                        + guide_tail,
                    }
                )
        # THE WIDE TIER (agent/plans/PLAN-stop-hook-refactor-enforcement.md, Commit 3): the same question over the counter's `advisory` profile, which CI never runs. OUTSIDE `if judged_ok:` on purpose -- the narrow tier's reason for sitting inside it ("a second order in the same block is how a block stops being read") applies only to a rule that blocks, and this one never does: it never reaches `wl_rules.apply_order` and its whole output is one priority-2 section through `outq_add`, which survives a blocked stop.
        #
        # THE MOMENT IS THE PLAN'S STATED FALLBACK, not its first design. The plan triggered on `sig_moved or (reg_signals and <a fix-set file matches a wide pathspec>)`, with a 3s ceiling on the widened counter and "gate the wide run behind reg_signals only" as the answer if the ceiling was breached. Measured 2026-09-24 through `counter_findings(root, profile="advisory")` on this tree: 3.11 / 3.22 / 3.02 / 3.00 / 3.05s cold (median 3.05s, 386 files, 96 findings; the gate profile is 1.93s on the same machine), so the fallback applies and an edit alone no longer buys a 3s scan. A fix landing in a wide family is the moment -- the one the operator named -- and `wide_sig_moved` survives only as a filter, so a second fix signal over an unchanged wide corpus (a tick, then the commit of the same files) does not pay 3s for the findings it already has.
        try:
            wide_moment = (
                reg_signals
                and wl_shapedup.touches_wide(reg_fixset_files)
                and wl_shapedup.wide_sig_moved(str(root), state_doc)
            )
            sw_text, sw_note = "", ""
            if wide_moment:
                sw_text, sw_note = wl_shapedup.wide_run(str(root), state_doc, C.git_branch(root))
        except Exception as exc:  # noqa: BLE001 -- an advisory rule must never wedge a stop
            sw_text, sw_note = "", "wide shape tier errored: %s" % exc
        S.save_state(worklist, session_id, state_doc)
        if sw_text:
            outq_add(worklist, session_id, state_doc, "shapedup-wide", sw_text, 2)
        if sw_note:
            outq_add(worklist, session_id, state_doc, "shapedup-wide-note", sw_note[:300], 2)
        if judged_ok and not judge_cached and not reg_signals:
            wl_judge.bank_stop_verdict(state_doc, cur_sig, last_msg, verdict.get("reason", ""))
            S.save_state(worklist, session_id, state_doc)

    counter.unlink(missing_ok=True)
    # The guide LEADS the allow report: it is the thing the session copies into its Remaining section, so it comes before everything else. Absent entirely when it had no rows (v18), which is what lets a clean stop with nothing queued emit zero bytes.
    parts = [] if guide_empty else [guide]
    if judged_ok:
        # NEVER QUEUED, deliberately: this line exists so a paid model call can never be invisible, and the operator requires a context-fresh session to get the full statement unconditionally. Queuing it would make both properties probabilistic. What is rationed is the VERBOSITY -- the reason is reading material on the stop where the context was just rebuilt or the reason actually
        # changed, and a bare stamp otherwise. The pop sits inside this branch so a blocked stop cannot consume the
        # marker and a WORKLIST_JUDGE=off session holds it until its first
        # judged stop.
        fresh = state_doc.pop("ctx_fresh", None)
        rsn = (verdict or {}).get("reason", "")
        rsig = hashlib.sha1(rsn.encode("utf-8", "replace")).hexdigest()[:12]
        stamp = "approved (cached)" if judge_cached else "approved"
        if fresh or (not judge_cached and rsig != state_doc.get("judge_reason_sig")):
            # Set ONLY when the full reason is shown, so the next genuinely different reason still fires. bank_stop_verdict already truncates at 200, so 400 is a ceiling that bites only a fresh uncached one.
            parts.append(M.N_JUDGE_STAMP_FULL % (wl_judge.JUDGE_MODEL, stamp, rsn[:400]))
            state_doc["judge_reason_sig"] = rsig
        else:
            parts.append(M.N_JUDGE_STAMP % (wl_judge.JUDGE_MODEL, stamp))
    # Every section with an earlier producer was queued at that producer's call site, so it survives a stop that blocks. The four below have no earlier producer: the allow path is the only place they exist, and they are enqueued here in the order the report used to carry them.
    #
    if orphaned:
        outq_add(
            worklist,
            session_id,
            state_doc,
            "orphans",
            "Worklist: %d ORPHANED item(s) (owner session dead; auto-archive after %sh):\n%s"
            % (
                len(orphaned),
                os.environ.get("WORKLIST_ARCHIVE_HOURS", "168"),
                "\n".join("  " + o for o in orphaned),
            ),
            2,
        )
    # The in-flight and deferred sections that used to sit here were pure duplication (operator, 2026-07-31: "Why I see such a big output?"): guided_slice already lists every owned [>] and [?] with its LATEST and NEXT verb, and the guide LEADS this very report. One source, said once.
    # THE HANDOFF BLOCK, on every allow path and not only when I am idle. A stopped session's work is invisible precisely when I am busy, which is when a compaction is most likely.
    _handoff = handoff_note()
    if _handoff:
        outq_add(worklist, session_id, state_doc, "handoff", _handoff, 1, refresh_min=60)
    # The specialist-agent hint, LAST of the producers and lowest priority of them, on the ALLOW PATH ONLY and deliberately: a blocked session already has something more urgent being said to it every stop. The trade is that a session which never reaches a clean stop is never hinted, which is acceptable for exactly the same reason.
    with contextlib.suppress(Exception):  # an advisory must never wedge a stop
        # Not in focus mode: a hint would spend the session's hint budget on a line the batch holds.
        if not _focus:
            agent_hint_queue(
                worklist,
                session_id,
                state_doc,
                (last_msg or "") + "\n" + "\n".join(remaining_lines),
            )
    # THE BEHAVIORAL-HINT QUEUE PRODUCERS, matching agent_hint_queue's own placement exactly: BEFORE outq_drain, so anything queued here has the SAME chance to drain on THIS stop that every other producer gets, rather than only ever being seen on the next one -- a corpus error queued after the drain call would otherwise sit until a LATER, possibly genuinely-silent stop, and single-handedly break that stop's silence. These two are ordinary queue items and are NOT gated on other content already firing; only the hint LINE ITSELF, picked below, carries that gate.
    hint_entries, hint_errs = [], []
    with contextlib.suppress(Exception):  # an advisory must never wedge a stop
        hint_entries, hint_errs = wl_hints.load_corpus(wl_hints.hints_path(root))
        if hint_errs:
            outq_add(
                worklist,
                session_id,
                state_doc,
                "hint-corpus-err",
                M.N_HINT_CORPUS_ERR % "\n".join("  " + e for e in hint_errs),
                3,
            )
        pending = wl_hints.pending_proposals(root)
        if pending:
            outq_add(
                worklist,
                session_id,
                state_doc,
                "hint-proposals",
                M.N_HINT_PROPOSALS_PENDING % len(pending),
                3,
                refresh_min=wl_hints.PROPOSAL_REFRESH_MIN,
            )
    # UP TO OUTQ_PER_STOP sections per stop, highest priority first and randomized inside a priority class. The "+N more" tail is MANDATORY for the reason spelled out at the guide's own truncation: a silent cap reads as "that is everything", and there is no knob left to widen it for one turn.
    # FOCUS MODE releases only the PR's own advisories in full; the rest is held and delivered one line each when the batch comes due (agent/plans/PLAN-stop-hook-focus-mode.md section 6).
    _drain_only = wl_standdown.advisory_kept if _focus else None
    texts, remaining = outq_drain(worklist, session_id, state_doc, OUTQ_PER_STOP, only=_drain_only)
    parts.extend(texts)
    if _focus:
        if wl_standdown.batch_due(state_doc.get("standdown")):
            _batch, _ = outq_digest(
                worklist,
                session_id,
                state_doc,
                only=lambda k: not wl_standdown.advisory_kept(k),
            )
            if _batch:
                parts.append(_batch)
        focus_advisory_bookkeeping(worklist, session_id, _focus, state_doc)
        _fsd = state_doc.get("standdown") or {}
        parts.insert(
            0,
            M.N_FOCUS
            % (
                _focus.get("mode"),
                _focus.get("pr") or "?",
                _focus.get("at"),
                int(_fsd.get("parked_now") or 0),
                int(_fsd.get("adv_held") or 0),
                me8,
            ),
        )
    elif remaining:
        parts.append(M.N_OUTQ_MORE % remaining)
    # THE ROTATING BEHAVIORAL HINT, LAST. Normally gated on parts already being non-empty: it rides an output the stop was already going to produce, so it is not usually the reason one exists.
    #
    # wl_popup.should_pop() is the one deliberate exception (PLAN-popup-reminder.md): a ~20% independent roll that lets this same hint fire on an otherwise-silent stop too, "out of the blue" by design.
    #
    # Checked here, not inside wl_hints, because "did anything else fire this stop, or did the roll" is exactly what this one condition already answers -- a second check inside the module would just ask the same question twice and could drift from this one.
    if not _focus and (parts or wl_popup.should_pop()):
        with contextlib.suppress(Exception):  # an advisory must never wedge a stop
            ledger = state_doc.setdefault("hints", {})
            picked = wl_hints.hint_pick(hint_entries, ledger)
            if picked:
                parts.append(wl_hints.render(*picked))
    # outq_drain persisted the queue already; this save carries the judge-line marker pop and any late state mutation, and one redundant atomic write is cheaper than reasoning about which came last. It happens BEFORE the exit below, because a silent allow must still bank everything a loud one does.
    S.save_state(worklist, session_id, state_doc)
    if not parts:
        # v18: nothing actionable, nothing queued, no judge line to show. This used to be impossible (the guide was unconditional) and is now the common shape of a clean stop, so it exits with zero bytes, exit 0. Everything above still ran and still persisted -- the silence is the report, not a skipped battery.
        raise SystemExit(0)
    C.emit({"systemMessage": "\n\n".join(parts)})
