"""THE COLLAPSE: one hook command per (event, matcher) pattern, and the proof it decides what 30 commands decided.

`.claude/settings.json` names ONE command per pattern. The commands it used to name live in `lifecycle.PATTERNS`, so two things have to be true and neither is visible to any other test in this tree.

CLAUSE 1 IS THE COUNT, and on its own it is worthless. A settings file with eleven entries that run nothing at all satisfies it perfectly, which is why the box that asked for this collapse wrote the second clause down in the same breath.

CLAUSE 2 IS THE VERDICT SET. Every payload the guard corpus recovers is driven twice: once through the members as SEPARATE commands, the way the harness ran them before the collapse, and once through `.claude/hooks/chain-head.sh`, the single command that replaced them. The comparison is on the whole observable contract -- exit code, stdout and stderr, byte for byte -- rather than
on a refused/allowed bit, because "blocked, here is the correct command" and "blocked, good luck" are the same bit and a different answer.

WHAT MAKES THE GREEN MEAN SOMETHING. A differential between two runs of the same table would pass with every member deleted from both sides, so the controls delete a member from ONE side and require the comparison to go red. One member, `why-on-edit.py`, is not reachable from the harvested corpus at all: its refusal needs a `tool_name` of Write and a `file_path`, and the suite's
`edit_json` builder emits neither. That is a gap in the corpus rather than in the collapse, and it is closed here with a payload built for it, because a control that plants nothing proves nothing.
"""

import contextlib
import json
import os
import subprocess

import pytest

from rediacc_hooks import guards, lifecycle
from rediacc_hooks.tests import guardcorpus

ROOT = guardcorpus.repo_root()
HEAD_SCRIPT = ROOT / lifecycle.HEAD_SCRIPT

# The patterns whose members are pure verdicts on a payload, so the whole corpus can be driven through them without touching the network, the PR or the worklist. The other eight are pinned structurally by `test_the_table_is_what_settings_json_runs` and are not executed here; `post-bash` cancels CI runs and rewrites a PR body, and the lifecycle patterns write the session's own
# state.
DRIVEN = ("pre-bash", "pre-edit", "pre-ask")

# The settings file under test: the live one, unless a proposed one is named through the shared seam.
settings_path = lifecycle.settings_path


def per_pattern(doc):
    """`{(event, matcher): [entry, ...]}`, with the harness's own `type` key dropped."""
    out = {}
    for event, blocks in (doc.get("hooks") or {}).items():
        for block in blocks or []:
            key = (event, block.get("matcher"))
            for hook in block.get("hooks") or []:
                out.setdefault(key, []).append({k: v for k, v in hook.items() if k != "type"})
    return out


def table_per_pattern():
    return {
        (p["event"], p["matcher"]): lifecycle.flat_commands(key)
        for key, p in lifecycle.PATTERNS.items()
    }


def hook_env():
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    return env


def run_separately(members, payload, env):
    """The members as the harness ran them before the collapse: one command each.

    Exit 2 is the blocking refusal and stops the block; any other non-zero is surfaced and the block continues. The same rule `lifecycle.run_pattern` implements, written out a second time here on purpose, because a differential whose two sides share the code under test measures nothing.
    """
    out, err, failed = [], [], False
    for member in members:
        proc = subprocess.run(
            ["bash", "-c", member["command"]],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=member.get("timeout", lifecycle.DEFAULT_TIMEOUT),
        )
        out.append(proc.stdout)
        err.append(proc.stderr)
        if proc.returncode == 2:
            return 2, lifecycle.merge_stdout(out), "".join(err)
        if proc.returncode != 0:
            failed = True
    return (1 if failed else 0), lifecycle.merge_stdout(out), "".join(err)


def run_collapsed(key, payload, env):
    """The one command `.claude/settings.json` registers for this pattern."""
    proc = subprocess.run(
        ["bash", str(HEAD_SCRIPT), key],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=lifecycle.entry_timeout(key),
    )
    return proc.returncode, proc.stdout, proc.stderr


def corpus_by_chain():
    """`{chain: {payload: label}}` for the driven patterns, deduplicated by payload.

    A payload is routed by the chain of the guard whose case it came from, because that is the pattern the harness would have handed it to. Duplicates collapse: the chain runs every member regardless of which guard a case was written for, so the same bytes twice is the same comparison twice.
    """
    cases, _ = guardcorpus.harvest_cases()
    routed = {}
    for guard, payload, label, _rc in cases:
        if guard.startswith("guards/"):
            chain = guards.load(guard[len("guards/") : -len(".py")]).CHAIN
        else:
            chain = guard.split("/")[0]
        if chain in DRIVEN:
            routed.setdefault(chain, {}).setdefault(payload, label)
    return routed


CORPUS = corpus_by_chain()


def without(tool, tmp_path):
    """A PATH holding everything the current one does, minus one tool.

    A SYMLINK FARM RATHER THAN A STUB, because `command -v` is what both toolchain checks ask and a stub named `jq` would answer it. Everything else stays reachable so the members behave as they normally do; both sides of the comparison get the same farm, so whatever a missing tool changes cancels and only the refusal remains.
    """
    farm = tmp_path / ("path-without-" + tool)
    farm.mkdir(parents=True, exist_ok=True)
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory or not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if name == tool or (farm / name).exists():
                continue
            with contextlib.suppress(OSError):
                (farm / name).symlink_to(os.path.join(directory, name))
    env = hook_env()
    env["PATH"] = str(farm)
    return env


def plan_duplicate_payload(tmp_path):
    """A Write of a new plan whose slug is a superset of an existing one: why-on-edit's refusal.

    Built against a throwaway root rather than the repository's own `agent/`, so the case does not depend on which plans happen to exist today.
    """
    (tmp_path / "agent").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agent" / "PLAN-collapse-control.md").write_text("x", encoding="utf-8")
    target = tmp_path / "agent" / "PLAN-collapse-control-duplicate.md"
    return json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(target), "content": "x"},
            "session_id": "settings-collapse-control",
        }
    )


def member_plant(member, prefix, pool, env, tmp_path):
    """`(payload, env)` on which this member, and no member ahead of it, refuses.

    THE PREFIX MATTERS AND COST A ROUND OF THIS TEST. `block-pathspecless-git-commit.sh` ran last in the pre-bash pattern, behind the dispatcher, and the first corpus payload it refused was also refused by the dispatcher ahead of it. The chain stops at the first refusal, so deleting the last member changed nothing and the control reported it as unread. A plant has to be an input
    the members AHEAD of it ALLOW. W7 P6 ported that member into the dispatcher, so the pre-bash pattern has one member again and the lesson now applies to post-bash, whose three members sit in a row.
    """
    command = member["command"]
    for tool in lifecycle.head_checks():
        # The head's two checks are one script with two modes since 2026-09-21, so the plant is keyed on the MODE rather than on a filename. Both modes name the same file, and a plant keyed on that would hand the jq farm to the python3 check.
        if command.endswith("--check " + tool):
            return min(pool), without(tool, tmp_path)
    if "why-on-edit.py" in command:
        control_env = hook_env()
        control_env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        return plan_duplicate_payload(tmp_path), control_env
    # Everything else is a verdict on a payload, so the corpus holds one. The first that this member refuses and every member ahead of it allows is taken, which keeps the plant deterministic.
    for payload in pool:
        rc, _, _ = run_separately([member], payload, env)
        if rc == 0:
            continue
        ahead, _, _ = run_separately(prefix, payload, env)
        if ahead == 0:
            return payload, env
    return None


# --------------------------------------------------------------------------- Clause 1: the shape ---------------------------------------------------------------------------


def test_the_table_is_what_settings_json_runs():
    """Every pattern's flattened members are exactly the commands the settings file declares.

    This is what lets every other reader of the wiring -- the resolvable gate, the wiring test, the guard-position test -- keep seeing 30 commands after the file was cut to 11. It is also what makes the differential below durable: the old side is the table, and the table is pinned here against the file.
    """
    doc = json.loads(settings_path().read_text(encoding="utf-8"))
    live, table = per_pattern(doc), table_per_pattern()
    assert set(live) == set(table), (
        "the settings file and lifecycle.PATTERNS disagree about which (event, matcher) patterns "
        "exist: only in the file %s, only in the table %s"
        % (sorted(map(str, set(live) - set(table))), sorted(map(str, set(table) - set(live))))
    )
    wrong = []
    for key in sorted(live, key=str):
        want = table[key]
        got = live[key]
        if len(got) == 1 and lifecycle.routed_key(got[0]["command"]):
            got = lifecycle.expand(got[0]["command"])
        if got != want:
            wrong.append("%s\n  settings: %s\n  table:    %s" % (key, got, want))
    assert not wrong, (
        "a member is in one record and not the other, which is a hook that either stopped "
        "running or started:\n" + "\n".join(wrong)
    )


def test_one_entry_per_pattern():
    """Clause 1 of the box: the entry count equals the number of distinct patterns.

    Worthless alone, and stated as such in the module docstring. It is here because the count is what the collapse was asked for, and because an entry that quietly came back is a fork paid on every tool call.
    """
    doc = json.loads(settings_path().read_text(encoding="utf-8"))
    live = per_pattern(doc)
    fat = {str(k): len(v) for k, v in live.items() if len(v) != 1}
    assert not fat, "these patterns still register more than one command: %s" % fat
    assert len(live) == len(lifecycle.PATTERNS), (
        "%d pattern(s) in the settings file against %d in the table"
        % (len(live), len(lifecycle.PATTERNS))
    )


@pytest.mark.parametrize("tool", lifecycle.head_checks())
def test_the_head_script_runs_the_declared_check(tool, tmp_path):
    """`chain-head.sh` really refuses when a tool `lifecycle.HEAD` declares is missing.

    The head is bash and the table is Python, so nothing but this compares them, and since the two checks were inlined on 2026-09-21 their absence is a missing LINE rather than a missing file: the head still exists, still leads every guarded chain, and would still be reported as resolving by `check_hooks_resolvable`. Driven rather than read, because a head that grepped right and
    decided nothing is the shape this whole tree exists to refuse.
    """
    payload = min(CORPUS["pre-bash"])
    rc, _out, err = run_collapsed("pre-bash", payload, without(tool, tmp_path))
    assert rc == 2, "the head allowed a Bash payload with %s missing from PATH (rc %s)" % (tool, rc)
    assert "BLOCKED: %s is not installed" % tool in err, (
        "the head refused with %s missing but said something else: %r" % (tool, err[:400])
    )


def test_every_head_pattern_leads_with_the_toolchain_checks():
    """A pattern marked `head` starts with the jq check then the python3 check, and no other does.

    Position is the whole contract of both checks, and the collapse moved that position out of the settings file and into this table. `.claude/hooks/chain-head.sh` states it in its own header; `check_hooks_resolvable.first_guard_verdicts` states it for the gate.
    """
    want = ["--check " + tool for tool in lifecycle.head_checks()]
    for key, pattern in lifecycle.PATTERNS.items():
        flat = [m["command"] for m in lifecycle.flat_commands(key)]
        lead = [c for c in flat[: len(want)] if "--check " in c]
        if pattern["head"]:
            assert [c.rsplit('" ', 1)[-1] for c in lead] == want, (
                "%s is a head pattern but does not lead with both checks in order: %s"
                % (key, flat[: len(want)])
            )
        else:
            assert not lead, "%s is not a head pattern but names a toolchain check: %s" % (
                key,
                flat[: len(want)],
            )


# --------------------------------------------------------------------------- Clause 2: the verdict set ---------------------------------------------------------------------------


def test_the_corpus_is_large_enough_to_mean_something():
    """A differential over four payloads would agree for reasons that have nothing to do with the collapse."""
    sizes = {chain: len(CORPUS.get(chain, {})) for chain in DRIVEN}
    assert min(sizes.values()) > 0, "a driven pattern recovered no payloads at all: %s" % sizes
    assert sum(sizes.values()) >= 300, "the corpus recovered only %s payload(s)" % sum(
        sizes.values()
    )


@pytest.mark.parametrize("chain", DRIVEN)
def test_verdict_set_is_unchanged(chain):
    """The whole corpus, through the members separately and through the one collapsed command."""
    env = hook_env()
    members = lifecycle.flat_commands(chain)
    wrong = []
    pool = CORPUS[chain]
    for payload, label in sorted(pool.items()):
        old = run_separately(members, payload, env)
        new = run_collapsed(chain, payload, env)
        if old != new:
            wrong.append("%s %s\n  separate: %r\n  collapsed: %r" % (chain, label, old, new))
    assert not wrong, "%d of %d payload(s) decided differently:\n%s" % (
        len(wrong),
        len(pool),
        "\n".join(wrong[:5]),
    )


@pytest.mark.parametrize("chain", DRIVEN)
def test_dropping_a_member_turns_the_differential_red(chain, tmp_path):
    """The control. Every member is deleted in turn, on a payload that member DECIDES.

    A DIFFERENTIAL BETWEEN TWO RUNS OF ONE TABLE IS VACUOUS, and this is what stops it being that: each member is handed an input it refuses, and the comparison must then notice its absence. A member with no such input is reported as blind rather than skipped, because a control that plants nothing proves nothing.

    THE PLANT IS BUILT PER MEMBER, not fished out of the corpus, and two of them could not have been fished out at all. The head's jq and python3 checks refuse only when their tool is MISSING, so no payload distinguishes them on a machine that has both; they are driven against a PATH with that one tool taken out of it. `why-on-edit.py` refuses only a Write of a new plan
    whose slug duplicates an existing one, and the suite's `edit_json` builder emits neither a `tool_name` nor a `file_path`, so its refusal is unreachable from the whole harvested corpus. That is a gap in the corpus rather than in the collapse, and it is closed here.
    """
    env = hook_env()
    members = lifecycle.flat_commands(chain)
    pool = sorted(CORPUS[chain])
    blind = []
    unchanged = []
    for i, member in enumerate(members):
        found = member_plant(member, members[:i], pool, env, tmp_path)
        if found is None:
            blind.append(member["command"])
            continue
        payload, plant_env = found
        crippled = [m for j, m in enumerate(members) if j != i]
        if run_separately(members, payload, plant_env) == run_separately(
            crippled, payload, plant_env
        ):
            unchanged.append(member["command"])
    assert not blind, (
        "no input in this test makes these member(s) of the %s pattern decide anything, so the "
        "differential certifies them for free: %s" % (chain, blind)
    )
    assert not unchanged, (
        "deleting these member(s) from the %s pattern changed NO decision on an input they "
        "themselves refuse, so the comparison is not reading them: %s" % (chain, unchanged)
    )
