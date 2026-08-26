#!/usr/bin/env python3
"""Every agent under .claude/agents must be REACHABLE by the stop hook's hint matcher.

WHY THIS EXISTS. On 2026-08-15 the operator had to say "there is bench server
deployment" by hand, because the word `bench` appeared ZERO times across all
seven agent `description` fields and exactly once in the whole directory:
account-dev.md:81, in the BODY. The knowledge existed and the matching surface
did not. A specialist nobody can be pointed at is a specialist nobody uses, and
nothing in the tree could tell the difference between "the matcher is healthy
and this stop is quiet" and "the matcher is dead".

WHY "IS THE MATCHER SILENT" IS THE WRONG TEST, and this is the whole design.
A healthy matcher on a quiet stop emits nothing, exactly like a broken one.
Counting hints cannot separate them. So this plants a one-line specimen per
agent -- the sentence a session would actually type -- and asserts the matcher
picks that agent, above threshold and by margin. In the SAME run it asserts
five neutral haystacks match nothing at all. Either half alone is worthless:
"everything fires" and "everything is silent" both pass a one-sided test.

ADDING AN AGENT MEANS ADDING A SPECIMEN. That is deliberate friction, and it is
the assertion that carries the feature: the specimen table's key set must EQUAL
the set of agent files, in both directions, so a new agent with a vague
description fails here rather than being quietly unreachable for six months.

CONTROL-FIRST. Before the real corpus is judged at all, the matcher and this
gate's own evaluator are driven against a synthetic fixture with planted
defects: a blanked description must be reported DEAD, a specimen for a deleted
agent must be reported STALE, an agent with no specimen must be reported
UNPROVEN, and a threshold raised out of reach must silence a match that
otherwise fires. If any planted defect passes, this gate declares itself broken
and exits non-zero WITHOUT issuing a verdict on the real corpus. A verdict from
an instrument that cannot fail is worse than no verdict.

Design: agent/PLAN-agent-hints-implementation.md (sections 5 and 6).
"""

from __future__ import annotations

import os
import re
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
AGENTS_DIR = os.path.join(REPO_ROOT, ".claude", "agents")
HOOK_DIR = os.path.join(REPO_ROOT, ".claude", "hooks", "stop")

# A corpus this small cannot discriminate anything, and a directory that lost
# its files would otherwise look exactly like a corpus where every agent passes.
MIN_AGENTS = 3

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# The thresholds are IMPORTED from the hook module, never re-declared here (see
# resolve_thresholds): a gate that carries its own copy proves a configuration
# nothing runs. These are only the names to look for.
SCORE_ATTRS = ("AGENT_HINT_MIN_SCORE", "MIN_SCORE", "HINT_MIN_SCORE", "DEFAULT_MIN_SCORE")
MARGIN_ATTRS = ("AGENT_HINT_MIN_MARGIN", "MIN_MARGIN", "HINT_MIN_MARGIN", "DEFAULT_MIN_MARGIN")

MAX_SPECIMEN_CHARS = 200

# One line per agent, phrased the way a session states its task. None is a
# substring of its agent's description: the lazy specimen is "paste the
# description in", which proves only that a string matches itself.
SPECIMENS = {
    # REGRESSION 2026-08-15. "bench" appeared ZERO times in any agent description
    # and once in account-dev's BODY (account-dev.md:81). The knowledge existed
    # and the matching surface did not, so the operator had to hint by hand. If
    # this specimen stops firing, someone has removed the bench nouns from the
    # description again.
    "account-dev": "there is bench server deployment, deploy the account worker to bench and reset the D1",
    "ops-vms": "spin up the fleet of VMs for the bridge test and check hypervisor status",
    "backup-storage": "the restore drill fails on round-trip verification of a snapshot",
    "i18n-guardian": "German locale file has Arabic values, re-run naturalize for the www translations",
    "licensing-ops": "license activation cap wrong after a fork, re-metering the datastore",
    "media-pipeline": "regenerate the tutorial narration, the captions drift by two seconds",
    "pr-babysitter": "push the branch and watch CI until every job is green, flip the PR ready",
    "config-universe": "rdc config remote enable fails with Decryption failed after the passkey unlock",
    "e2e-local": "an e2e test is failing, run the bridge suite locally against the VM fleet instead of pushing to CI",
    "browser-probe": "drive the page in a real browser with agent-browser and measure the rendered layout",
    "gate-author": "write a regression gate, drain its baseline, and verify the three-point wiring in the ci-runner manifest",
    "www-site": "restyle the solution page hero and the docs layout in the Astro marketing site",
    "test-advisor": "this fix landed and nothing stops it coming back, decide which regression surface owns it",
}

# Neutral haystacks. Every one of them is ordinary work that no specialist owns.
# They run inline on EVERY invocation, never behind a flag: a control you have to
# remember to run is how a control stops controlling anything.
CONTROLS = (
    "fix a typo in the README",
    "update CLAUDE.md session defaults and the worklist stop hook docs",
    "rename a variable in packages/shared and rebuild the dist output",
    "the test suite has one failing assertion, find it and fix it",
    "bump the eslint version and re-run the linter",
)


def die(msg: str) -> None:
    print(f"{RED}✗{NC} {msg}", file=sys.stderr)
    raise SystemExit(1)


def agent_names(agents_dir: str) -> set[str]:
    return {f[:-3] for f in os.listdir(agents_dir) if f.endswith(".md")}


def load_matcher():
    # ORDER MATTERS. The agents directory is checked by the caller BEFORE this
    # runs, because against the anti-vacuity harness's empty fixture neither
    # .claude/agents nor .claude/hooks exists, and an unguarded import would die
    # with ModuleNotFoundError: a non-zero exit for an environment reason wearing
    # a vacuity failure's exit code.
    if not os.path.isdir(HOOK_DIR):
        die(f"{HOOK_DIR} not found; cannot judge a matcher that is not there")
    if not os.path.isfile(os.path.join(HOOK_DIR, "wl_agents.py")):
        die(
            f"{HOOK_DIR}/wl_agents.py not found. The hint matcher is gone or renamed; "
            "fix the wiring deliberately rather than letting this gate pass over its absence."
        )
    sys.path.insert(0, HOOK_DIR)
    try:
        # Deferred deliberately: HOOK_DIR must be on sys.path first, and a
        # top-level import would make this gate uncollectable outside the repo.
        import wl_agents  # noqa: PLC0415
    except ImportError as exc:
        die(f"cannot import wl_agents ({exc}). Refusing to pass while measuring nothing.")
    for fn in ("load_corpus", "discriminative", "tokenize", "score", "best_hint"):
        if not hasattr(wl_agents, fn):
            die(
                f"wl_agents.{fn}() is missing (renamed? removed?). The matcher's frozen "
                "contract changed; update this gate deliberately rather than letting it pass."
            )
    return wl_agents


def resolve_thresholds(matcher) -> tuple[float, float]:
    def pick(attrs):
        for attr in attrs:
            if hasattr(matcher, attr):
                return getattr(matcher, attr)
        return None

    min_score = pick(SCORE_ATTRS)
    min_margin = pick(MARGIN_ATTRS)
    if min_score is None or min_margin is None:
        die(
            "wl_agents exports no default threshold under any of "
            f"{SCORE_ATTRS} / {MARGIN_ATTRS}. This gate must judge the SAME numbers the "
            "hook runs; hardcoding a copy here would prove a configuration nothing uses."
        )
    return float(min_score), float(min_margin)


def ranking(matcher, haystack: str, uniq) -> list[tuple[float, str]]:
    """[(score, name)] descending, whatever shape score() returns its rows in."""
    rows = matcher.score(haystack, uniq)
    return [(float(row[0]), str(row[1])) for row in rows]


def evaluate(matcher, corpus, uniq, specimens, names, min_score, min_margin) -> list[str]:
    """Findings, one string per problem. Empty means every agent is reachable."""
    out: list[str] = []

    # (a) Universe equality, both directions. This is the assertion that makes
    # "prove your new agent is reachable" a build requirement.
    out.extend(
        f"UNPROVEN: {missing} has no specimen. Add one line to SPECIMENS phrased the way "
        "a session would state that task, so the agent is provably reachable."
        for missing in sorted(names - set(specimens))
    )
    out.extend(
        f"STALE SPECIMEN: {stale} has no agent file under {AGENTS_DIR}. "
        "The agent was renamed or deleted; the specimen must follow it."
        for stale in sorted(set(specimens) - names)
    )

    for name in sorted(set(specimens) & names):
        text = specimens[name]

        # (e) Anti-tautology. The empty check comes first because "" is a
        # substring of every description, so an emptied specimen would otherwise
        # be reported as tautological, which sends the reader to the wrong fix.
        if not text.strip():
            out.append(
                f"EMPTY SPECIMEN: {name} has no specimen text, so nothing about it is proven. "
                "Write the line a session would actually type."
            )
            continue
        if len(text) > MAX_SPECIMEN_CHARS:
            out.append(
                f"OVERSIZED SPECIMEN: {name} is {len(text)} characters, over the "
                f"{MAX_SPECIMEN_CHARS} limit. A specimen is one line a session would type."
            )
            continue
        desc = (corpus.get(name) or {}).get("desc", "")
        if text.strip().lower() in desc.lower():
            out.append(
                f"TAUTOLOGICAL SPECIMEN: {name}'s specimen is a verbatim substring of its own "
                "description, so it proves only that a string matches itself. Rephrase it."
            )
            continue

        rows = ranking(matcher, text, uniq)
        own = next((s for s, n in rows if n == name), 0.0)
        top_score, top_name = rows[0] if rows else (0.0, "")
        runner_up = rows[1][0] if len(rows) > 1 else 0.0

        if own < min_score:
            out.append(
                f"DEAD: {name} scored {own:g} on its own specimen, under MIN_SCORE={min_score:g}. "
                "Its description lacks the nouns people actually type. Sharpen the description."
            )
        elif top_name != name:
            out.append(
                f"CROSS-MATCHED to {top_name}: {name} scored {own:g} but {top_name} won with "
                f"{top_score:g}. Two descriptions overlap; sharpen one of them."
            )
        elif own - runner_up < min_margin:
            out.append(
                f"AMBIGUOUS (margin {own - runner_up:g} < {min_margin:g}): {name} won at {own:g} "
                f"with a runner-up at {runner_up:g}. At runtime the matcher stays SILENT here "
                "rather than reporting a near miss, so this is the only place it is visible."
            )
        else:
            # The ranking and the hook's own entry point must agree, or this gate
            # is grading something the hook never calls.
            hint = matcher.best_hint(text, uniq, min_score, min_margin)
            if hint is None or hint[0] != name:
                got = "nothing" if hint is None else hint[0]
                out.append(
                    f"CONTRACT DRIFT: {name} wins the ranking at {own:g} but best_hint() returned "
                    f"{got}. The scorer and the entry point disagree, so one of them is not what "
                    "the hook runs."
                )
    return out


def write_agent(path: str, name: str, description: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            f"---\nname: {name}\ndescription: {description}\ntools: Bash\nmodel: opus\n---\n"
            "body text that the matcher must not read\n"
        )


def controls_fired(matcher, min_score, min_margin) -> list[str]:
    """Drive the matcher and THIS gate's evaluator against planted defects.

    Returns the list of planted defects that were NOT caught. Anything in it
    means the instrument cannot fail, so no verdict may be issued.
    """
    missed: list[str] = []
    fixture_specs = {
        "alpha-sprocket": "recalibrate the quantum widget on the sprocket rig",
        "beta-orchard": "the cider press pruning schedule drifted by a week",
    }
    with tempfile.TemporaryDirectory() as tmp:
        alpha = os.path.join(tmp, "alpha-sprocket.md")
        beta = os.path.join(tmp, "beta-orchard.md")
        write_agent(alpha, "alpha-sprocket", "Quantum widget calibration for the sprocket rig.")
        write_agent(beta, "beta-orchard", "Orchard pruning schedules for the cider press.")

        def judge(specimens):
            corpus, errors = matcher.load_corpus(tmp)
            if errors:
                die(f"the synthetic control corpus reported errors, which it must not: {errors}")
            uniq = matcher.discriminative(corpus)
            names = agent_names(tmp)
            return (
                corpus,
                uniq,
                evaluate(matcher, corpus, uniq, specimens, names, min_score, min_margin),
            )

        # CONTROL 0: on a HEALTHY fixture the evaluator must be silent. Without
        # this every "caught it" below could be an evaluator that fails always.
        _corpus, uniq, findings = judge(fixture_specs)
        if findings:
            die(
                "CONTROL 0 FAILED: the evaluator reported findings on a healthy synthetic "
                f"corpus, so every planted-defect result below is meaningless: {findings}"
            )

        # CONTROL 1: a threshold out of reach must silence a match that fires.
        if matcher.best_hint(fixture_specs["alpha-sprocket"], uniq, 999.0, min_margin) is not None:
            missed.append("a match survived MIN_SCORE=999, so the threshold is not applied")

        # CONTROL 2: a description with none of the specimen's nouns must be DEAD.
        write_agent(alpha, "alpha-sprocket", "A general purpose helper for assorted tasks.")
        _, _, findings = judge(fixture_specs)
        if not any(f.startswith(("DEAD", "CROSS-MATCHED")) for f in findings):
            missed.append("a blanked description was not reported DEAD")
        write_agent(alpha, "alpha-sprocket", "Quantum widget calibration for the sprocket rig.")

        # CONTROL 3: a specimen for an agent that no longer exists must be STALE.
        _, _, findings = judge({**fixture_specs, "ghost-agent": "the ghost agent does something"})
        if not any(f.startswith("STALE SPECIMEN") for f in findings):
            missed.append("a specimen for a missing agent was not reported STALE")

        # CONTROL 4: an agent with no specimen must be UNPROVEN.
        write_agent(
            os.path.join(tmp, "gamma-lathe.md"),
            "gamma-lathe",
            "Lathe tooling inventory and spindle alignment.",
        )
        _, _, findings = judge(fixture_specs)
        if not any(f.startswith("UNPROVEN") for f in findings):
            missed.append("an agent with no specimen was not reported UNPROVEN")

    return missed


def glued_stopword_seams(src: str) -> list:
    """Literal seams in _STOPWORD_TEXT that silently merge two words into one.

    THE DEFECT, 2026-08-26. Adjacent Python string literals concatenate with
    NOTHING between them, so a literal that does not end in a space glues its
    last word to the next literal's first word. Two waves rebased together each
    appended a line to this list; one lacked the trailing space, `touched` and
    `see` became `touchedsee`, and BOTH tokens stopped being stopwords. Nothing
    failed: the list still parsed, still had a plausible length, and the two
    lost words simply started scoring as domain terms again.

    That is the shape this whole gate exists for -- a matcher that is quietly
    less healthy than it looks -- so the check belongs here rather than in a new
    gate of its own.

    COMMENT LINES ARE STRIPPED FIRST. The comments in that block quote phrases
    in double quotes ("just push and SEE what CI says"), and a naive scan reads
    them as literals and reports seventeen seams instead of one. Mention is not
    execution, in an analysis tool as much as in a guard.
    """
    m = re.search(r"_STOPWORD_TEXT = \((.*?)\n\)", src, re.S)
    if not m:
        return [("_STOPWORD_TEXT", "not found -- the list moved or was renamed")]
    code = "\n".join(
        ln for ln in m.group(1).split("\n") if not ln.lstrip().startswith("#")
    )
    lits = re.findall(r'"([^"]*)"', code)
    seams = []
    for i, lit in enumerate(lits[:-1]):
        nxt = lits[i + 1]
        if lit and nxt and not lit.endswith(" ") and not nxt.startswith(" "):
            seams.append((lit.split()[-1] if lit.split() else lit,
                          nxt.split()[0] if nxt.split() else nxt))
    return seams


def main() -> int:
    # --- vacuity, before anything is imported or scored ----------------------
    if not os.path.isdir(AGENTS_DIR):
        print(
            f"{RED}✗ VACUOUS INPUT{NC}: no agent files under {AGENTS_DIR}, so no hint can be "
            "proven. An empty corpus makes every reachability assertion true over nothing, "
            "which reads exactly like a healthy corpus. Refusing to report a pass.",
            file=sys.stderr,
        )
        return 1
    # A glued seam loses two real stopwords without failing anything.
    with open(os.path.join(HOOK_DIR, "wl_agents.py"), encoding="utf-8") as fh:
        seams = glued_stopword_seams(fh.read())
    if seams:
        print(
            f"{RED}✗ {len(seams)} glued literal seam(s) in wl_agents._STOPWORD_TEXT{NC}:",
            file=sys.stderr,
        )
        for a, b in seams:
            print(f"    {a!r} + {b!r}  ->  {a + b!r}", file=sys.stderr)
        print(
            "  Adjacent Python literals concatenate with nothing between them, so BOTH\n"
            "  words stop being stopwords and start scoring as domain terms again.\n"
            "  Add a trailing space to the earlier literal.",
            file=sys.stderr,
        )
        return 1

    names = agent_names(AGENTS_DIR)
    if len(names) < MIN_AGENTS:
        print(
            f"{RED}✗ VACUOUS INPUT{NC}: only {len(names)} agent file(s) under {AGENTS_DIR}, "
            f"under the floor of {MIN_AGENTS}. A corpus that small discriminates nothing and "
            "every specimen below would be judged against an empty term set.",
            file=sys.stderr,
        )
        return 1

    matcher = load_matcher()
    min_score, min_margin = resolve_thresholds(matcher)

    # --- control-first: prove this instrument can fail -----------------------
    missed = controls_fired(matcher, min_score, min_margin)
    if missed:
        print(
            f"{RED}✗{NC} CONTROLS DID NOT FIRE, so this gate cannot detect what it exists for:",
            file=sys.stderr,
        )
        for m in missed:
            print(f"  {m}", file=sys.stderr)
        return 1

    corpus, errors = matcher.load_corpus(AGENTS_DIR)
    if errors:
        print(
            f"{RED}✗{NC} the agent corpus does not parse, so the matcher is degraded:",
            file=sys.stderr,
        )
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    uniq = matcher.discriminative(corpus)

    findings = evaluate(matcher, corpus, uniq, SPECIMENS, names, min_score, min_margin)

    # --- negative controls, inline, same run ---------------------------------
    fired = []
    for control in CONTROLS:
        hint = matcher.best_hint(control, uniq, min_score, min_margin)
        if hint is not None:
            fired.append(f'"{control}" -> {hint[0]} at {float(hint[1]):g} on {hint[2]}')
    if fired:
        # Reported FIRST and alone: with the matcher firing on wallpaper, a green
        # specimen table means everything matches everything.
        print(
            f"{RED}✗{NC} NEGATIVE CONTROL FIRED. The matcher is too loose, so no verdict on the "
            "specimens is meaningful:",
            file=sys.stderr,
        )
        for line in fired:
            print(f"  {line}", file=sys.stderr)
        print(
            "\n  Raise WORKLIST_AGENT_HINT_MIN_SCORE/MIN_MARGIN or extend the stopword list in\n"
            "  .claude/hooks/stop/wl_agents.py. Ordinary work must match no specialist at all.",
            file=sys.stderr,
        )
        return 1

    if findings:
        print(f"{RED}✗{NC} agents that the stop hook's hint matcher cannot reach:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "\n  The description field IS the matching surface (bodies were measured and\n"
            "  rejected: they destroy discrimination). Put the concrete nouns a session would\n"
            "  type into .claude/agents/<name>.md's description, then re-run this gate.",
            file=sys.stderr,
        )
        return 1

    # --- the PUSH-BACK, over the same specimen table -------------------------
    # Reusing the specimens is the point, not a shortcut: it makes push-back
    # coverage automatic for every agent that exists now and every agent added
    # later, with no second table to keep in sync. A new agent that earns a
    # specimen earns its push-back the same day.
    #
    # Asserted in BOTH directions in one pass, because either half alone is
    # worthless. A rule that fires on everything and a rule that fires on
    # nothing both pass a one-sided test.
    pb_findings = []
    for name in sorted(names):
        specimen = SPECIMENS.get(name)
        if not specimen:
            continue  # the equality assertion above already failed for this
        # POSITIVE: the same sentence a session would type, prefixed with the
        # surrender that motivated this feature.
        # ONE SENTENCE, joined by a colon. Two sentences would put the claim
        # and its subject in different haystacks, which the checker rejects on
        # purpose -- and a gate that asserted the two-sentence shape would be
        # demanding the very false positive this feature was fixed to stop
        # making. The colon form is what the live sentence actually looked like.
        giving_up = f"It doesn't reproduce: {specimen}"
        hit, errs = matcher.pushback_for(giving_up, AGENTS_DIR)
        if errs:
            pb_findings.append(f"{name}: corpus errors during push-back: {errs}")
        elif not hit:
            pb_findings.append(
                f"{name}: a give-up claim in its own domain did NOT push back "
                f'(specimen: "{specimen[:60]}...")'
            )
        elif hit[0] != name:
            pb_findings.append(f"{name}: push-back named {hit[0]} instead")
        # NEGATIVE: the identical sentence WITHOUT a give-up claim must stay
        # silent. This is the half that keeps the push-back from degrading into
        # a second, louder copy of the topic hint.
        quiet, _ = matcher.pushback_for(specimen, AGENTS_DIR)
        if quiet:
            pb_findings.append(
                f"{name}: pushed back on a specimen carrying NO give-up claim "
                f"({quiet[2]}), so it fires on topic alone"
            )
    # NEGATIVE: give-up language with no specialist domain must stay silent too.
    # The last two are LIVE REGRESSIONS, both from the first hour this check
    # existed, and both were false positives it produced about ITSELF:
    #   - a message that quotes the trigger phrases while explaining them
    #     (a mention is not a claim), and
    #   - a give-up sentence whose domain words sit in a LATER sentence, which
    #     scored 5.0 against pr-babysitter while the true ceph case scored 4.0
    #     -- proof that no threshold separates them and that the claim's own
    #     sentence is the only honest haystack.
    for neutral in (
        "This cannot be done without a token, so it is pre-existing and not mine.",
        "It doesn't reproduce and there is no local way to check the changelog wording.",
        (
            'Firing on "cannot" alone would be unbearable. This fired live on "it '
            "doesn't reproduce: neither local worker has /etc/ceph\". Remaining: the "
            "wave, console review."
        ),
        (
            "It doesn't reproduce and this is pre-existing. Remaining: the wave, "
            "console review, commit and check."
        ),
        # THE FOUR THAT ACTUALLY MISFIRED, 2026-08-26, verbatim.
        #
        # Each drew a push-back from a specialist on ORDINARY ENGLISH, because
        # discriminative() asks only whether a term is unique across 13
        # documents, and uniqueness there is a weak proxy for specificity.
        # `while` reached media-pipeline ("render finished pairs WHILE the GPU
        # narrates"); `miss`/`see`/`suite` reached e2e-local ("MISSING
        # bin/renet", "just push and SEE what CI says", "E2E SUITES");
        # `step`/`stop` reached gate-author; `next` reached media-pipeline.
        #
        # THEY BELONG HERE, NOT IN CONTROLS. Placing them there first was a
        # control that could not fire: CONTROLS is judged by the HINT matcher at
        # MIN_SCORE=2, and these sentences score 1.0, so removing a stopword
        # left the gate green. Measured, not reasoned: deleting `while` from the
        # stopword list passed a run with them in CONTROLS and fails with them
        # here. The push-back floor is 1.0, which is where the damage was.
        #
        # The fix could NOT have been to raise PUSHBACK_MIN_SCORE: it sits below
        # the hint's floor deliberately, and the sentence this whole check was
        # built for -- "neither local worker has /etc/ceph" -- scores exactly 1.0
        # on `ceph`, so lifting it to 2 would silence the motivating incident,
        # which is pinned as a positive regression a few lines below.
        # THE MISFIRE THAT ACTUALLY REPRODUCES, 2026-08-26, verbatim.
        #
        # `while` reached media-pipeline because its description says "render
        # finished pairs WHILE the GPU narrates", and discriminative() asks only
        # whether a term is unique across 13 documents. Uniqueness there is a
        # weak proxy for specificity, so ordinary English scored as a domain
        # term. Deleting the conjunction line from wl_agents._STOPWORD_TEXT makes
        # this line fire and this gate exit 1; that was measured, not assumed.
        #
        # ONLY ONE OF THE FOUR MISFIRES IS PINNED HERE, deliberately. The other
        # three (miss/see/suite, step/stop, next) score above the push-back floor
        # but are suppressed by pushback_for's mention-is-not-a-claim rule, which
        # is correct behaviour, so no phrasing of them can fail this gate. They
        # were written, measured silent under their own planted defects, and
        # removed rather than left in looking like coverage. A control that
        # cannot fire is worse than an absent one: it reports protection nobody
        # has. Their stopwords are still covered by the four planted defects the
        # anti-vacuity harness runs above.
        "pre-existing bug fixed while there: setup ran bare npm install",
    ):
        stray, _ = matcher.pushback_for(neutral, AGENTS_DIR)
        if stray:
            pb_findings.append(
                f'"{neutral[:44]}..." pushed back to {stray[0]} on {stray[1]}, '
                "so give-up language alone is enough to fire it"
            )
    # POSITIVE REGRESSION: the sentence the operator pushed back on by hand. It
    # is pinned verbatim because two separate bugs silenced it during
    # development -- splitting on its colon, and stripping its apostrophe as a
    # quote -- and both looked like a healthy quiet check from the outside.
    _motivating = (
        "It doesn't reproduce: neither local worker has /etc/ceph or rbd. "
        "ops up fleet, ceph never provisioned."
    )
    _mhit, _ = matcher.pushback_for(_motivating, AGENTS_DIR)
    if not _mhit or _mhit[0] != "ops-vms":
        pb_findings.append(
            "the motivating sentence no longer pushes back to ops-vms (got %r). "
            "This check exists for that sentence; if it is silent the check is dead." % (_mhit,)
        )

    if pb_findings:
        print(
            f"{RED}✗{NC} the give-up push-back is broken (wl_agents.pushback_for):",
            file=sys.stderr,
        )
        for finding in pb_findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "\n  It must fire on (give-up claim AND specialist domain) and on nothing else.\n"
            "  Firing on topic alone duplicates the advisory hint; firing on give-up alone\n"
            "  makes every honest 'cannot' an accusation.",
            file=sys.stderr,
        )
        return 1

    print(f"{GREEN}✓{NC} all {len(names)} agents are reachable by the hint matcher")
    print(
        f"  every specimen wins its own agent at MIN_SCORE={min_score:g} MIN_MARGIN={min_margin:g}, "
        f"and all {len(CONTROLS)} neutral controls stayed silent"
    )
    print(
        f"  push-back fires for all {len(SPECIMENS)} agents on a give-up claim, and stays "
        "silent on the same specimen without one"
    )
    print("  4 planted defects were caught first, so this green means the check can fail")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
