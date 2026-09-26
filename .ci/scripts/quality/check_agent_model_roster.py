#!/usr/bin/env python3
"""check:ci-agent-model-roster -- flipping any agent to a cheap model tier leaves a written reason behind, in the same commit.

WHY THIS GATE AND NOT THE ONE FIRST PROPOSED. A gate that infers task SHAPE from an agent's prose and flags drift from convention cannot have an honest control: the planted defect would be "a description implying the wrong shape", which is exactly the judgement call `docs/agent-reference/model-routing.md` exists to have a human make. A gate that cannot state what a planted defect looks like is a gate that cannot fail, which `.claude/agents/gate-author.md`'s own anti-vacuity discipline forbids.

THE BARGAIN THIS GATE MAKES INSTEAD, the same one `scripts/gates/check-naturalization-model-policy.ts` already makes for locale naturalization: it does not judge whether `haiku` is the RIGHT tier for any given agent. It only insists that a non-`opus` model is a decision made ON PURPOSE, named by filename with its reason in `docs/agent-reference/model-routing.md`, in the same commit as the frontmatter that carries it. That is a keyset equality problem, the same shape `.ci/scripts/quality/check_agent_hint_liveness.py` already solves for specimen coverage, so this gate is built the same way: a small corpus scan, a doc scan, and a set comparison in both directions.

FAMILY, NOT VENDOR OR VERSION. `model_family` matches the substring `opus`/`haiku`/`sonnet` case-insensitively, so a version bump within a family (`claude-haiku-4-5` to a later haiku release) passes silently while a change of family or vendor (`gpt-4`, a bare `claude-3`) does not -- the same discrimination `scripts/gates/check-naturalization-model-policy.ts:51` draws for the naturalization ledger's `$meta.models`.

Design: agent/plans/PLAN-haiku-model-routing.md, section 4.

---- gate ----
step: Agent model roster matches its documented reasons
needs: none
selftest: true
lane: quality-content
---- end gate ----
"""

from __future__ import annotations

import os
import re
import sys
import tempfile

import _cipath  # noqa: F401
from rediacc_ci import paths  # noqa: F401  (kept for parity with the sibling gate's import shape)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
AGENTS_DIR = os.path.join(REPO_ROOT, ".claude", "agents")
ROUTING_DOC = os.path.join(REPO_ROOT, "docs", "agent-reference", "model-routing.md")

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# A corpus this small cannot discriminate anything, and a directory that lost its files would otherwise look exactly like a corpus where every agent is fine.
MIN_AGENTS = 3

FAMILIES = ("opus", "haiku", "sonnet")

# Every mention this gate trusts as "the doc documents this agent" is the FULL relative path, exactly how docs/agent-reference/model-routing.md always spells it (`.claude/agents/test-advisor.md`). A bare agent name would also match unrelated prose ("the test-advisor line above"), and a bare `.md` would match CLAUDE.md/PLAN-*.md mentions that have nothing to do with an agent roster.
AGENT_MD_RE = re.compile(r"\.claude/agents/([\w-]+)\.md")

MODEL_RE = re.compile(r"^model:\s*(\S+)\s*$", re.MULTILINE)


def model_family(value):
    """The FAMILY `value` belongs to (`opus`/`haiku`/`sonnet`), or None when it matches none."""
    low = (value or "").strip().lower()
    for fam in FAMILIES:
        if fam in low:
            return fam
    return None


def read_frontmatter_model(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = MODEL_RE.search(text)
    return m.group(1) if m else None


def agent_roster(agents_dir):
    """{name: model_string_or_None} for every `.claude/agents/*.md`."""
    out = {}
    for fn in sorted(os.listdir(agents_dir)):
        if fn.endswith(".md"):
            out[fn[:-3]] = read_frontmatter_model(os.path.join(agents_dir, fn))
    return out


def doc_named_agents(doc_text):
    """The set of agent names `docs/agent-reference/model-routing.md` documents by filename."""
    return set(AGENT_MD_RE.findall(doc_text))


def findings(roster, doc_text):
    """Every roster/doc mismatch, in both directions. Empty means the roster and its doc agree."""
    out = []
    named = doc_named_agents(doc_text)
    for name, model in sorted(roster.items()):
        fam = model_family(model)
        if fam is None:
            out.append(
                f"{name}.md declares model: {model!r}, which matches no recognised family "
                f"({', '.join(FAMILIES)}) -- a version bump within a family is fine, a change "
                "of family or vendor is not"
            )
        elif fam != "opus" and name not in named:
            out.append(
                f"{name}.md declares model: {model} but is not named by filename "
                f"(`.claude/agents/{name}.md`) in {ROUTING_DOC}"
            )
    for name in sorted(named):
        if name not in roster:
            out.append(f"{ROUTING_DOC} names {name}.md, which no longer exists under {AGENTS_DIR}")
        elif model_family(roster[name]) == "opus":
            out.append(
                f"{ROUTING_DOC} names {name}.md as a non-opus agent, but its frontmatter now "
                f"says model: {roster[name]} -- the doc entry is stale"
            )
    return out


def write_agent(path, model):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            f"---\nname: fixture\ndescription: A fixture agent.\ntools: Bash\nmodel: {model}\n---\n"
            "body text this gate must not read\n"
        )


def controls_fired():
    """Drive `findings` against planted defects. Returns the list NOT caught -- anything in it means the instrument cannot fail, so no verdict on the real roster may be issued."""
    missed = []
    with tempfile.TemporaryDirectory() as tmp:
        healthy = os.path.join(tmp, "steady-widget.md")
        write_agent(healthy, "opus")
        healthy_doc = ""

        # CONTROL 0: a healthy fixture (one opus agent, nothing to document) must be silent.
        roster = agent_roster(tmp)
        if findings(roster, healthy_doc):
            missed.append(
                "CONTROL 0: findings() reported on a healthy synthetic corpus, so every "
                "planted-defect result below is meaningless"
            )
            return missed

        # CONTROL 1: an unrecognised family/vendor is reported.
        write_agent(os.path.join(tmp, "rogue.md"), "gpt-4")
        roster = agent_roster(tmp)
        if not any("recognised family" in f for f in findings(roster, healthy_doc)):
            missed.append("an agent with model: gpt-4 was not reported")
        os.remove(os.path.join(tmp, "rogue.md"))

        # CONTROL 2: a non-opus agent absent from the doc is reported.
        write_agent(os.path.join(tmp, "quick-triage.md"), "haiku")
        roster = agent_roster(tmp)
        if not any("not named by filename" in f for f in findings(roster, healthy_doc)):
            missed.append("an agent with model: haiku absent from the doc was not reported")

        # CONTROL 2b (the positive control beside 2): the SAME agent, documented, is silent.
        documented_doc = "`.claude/agents/quick-triage.md` stays haiku because BLOCKER: fixture."
        if findings(roster, documented_doc):
            missed.append(
                "CONTROL 2b: a documented non-opus agent still fired, so the positive path "
                "of the same check that caught CONTROL 2 cannot pass on anything"
            )
        os.remove(os.path.join(tmp, "quick-triage.md"))

        # CONTROL 3: a doc entry for a deleted agent is reported.
        roster = agent_roster(tmp)
        ghost_doc = "`.claude/agents/ghost-agent.md` stays haiku because BLOCKER: fixture."
        if not any("no longer exists" in f for f in findings(roster, ghost_doc)):
            missed.append("a doc entry for a deleted agent was not reported")

        # CONTROL 4: a doc entry for an agent that reverted to opus is reported.
        write_agent(os.path.join(tmp, "reverted.md"), "opus")
        roster = agent_roster(tmp)
        reverted_doc = "`.claude/agents/reverted.md` stays haiku because BLOCKER: fixture."
        if not any("doc entry is stale" in f for f in findings(roster, reverted_doc)):
            missed.append("a doc entry for an agent that reverted to opus was not reported")

    return missed


def main():
    if not os.path.isdir(AGENTS_DIR):
        print(
            f"{RED}✗ VACUOUS INPUT{NC}: no agent files under {AGENTS_DIR}, so no roster claim "
            "can be proven. Refusing to report a pass over an empty corpus.",
            file=sys.stderr,
        )
        return 1

    missed = controls_fired()
    if missed:
        print(
            f"{RED}✗{NC} CONTROLS DID NOT FIRE, so this gate cannot detect what it exists for:",
            file=sys.stderr,
        )
        for m in missed:
            print(f"  {m}", file=sys.stderr)
        return 1

    roster = agent_roster(AGENTS_DIR)
    if len(roster) < MIN_AGENTS:
        print(
            f"{RED}✗ VACUOUS INPUT{NC}: only {len(roster)} agent file(s) under {AGENTS_DIR}, "
            f"under the floor of {MIN_AGENTS}.",
            file=sys.stderr,
        )
        return 1

    try:
        with open(ROUTING_DOC, encoding="utf-8") as fh:
            doc_text = fh.read()
    except OSError as exc:
        print(f"{RED}✗{NC} cannot read {ROUTING_DOC}: {exc}", file=sys.stderr)
        return 1

    found = findings(roster, doc_text)
    if found:
        print(
            f"{RED}✗{NC} the agent model roster and its documented reasons disagree:",
            file=sys.stderr,
        )
        for f in found:
            print(f"  {f}", file=sys.stderr)
        print(
            f"\n  Name any new non-opus agent by its full path in {ROUTING_DOC}, with the reason "
            "it earns the cheap tier, in the SAME commit as the frontmatter change. This gate "
            "never judges whether the tier is right -- only that the choice was made on purpose.",
            file=sys.stderr,
        )
        return 1

    non_opus = sum(1 for m in roster.values() if model_family(m) != "opus")
    print(
        f"{GREEN}✓{NC} agent model roster: {len(roster)} agent(s), {non_opus} non-opus, "
        "each named with a reason"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
