"""Refuse a push whose tree no local gate run has judged.

WHY. A CI round costs ~15 minutes. Measured on PR #579, three of the five reds this wave were `check:format` (1.72s), `check:ci-python-lint` (0.59s) and `check:ci-parity` (1.29s) -- 3.6 seconds of gate time between them, and they cost roughly 45 minutes of CI. The gates were there, the runner was there, and nothing made anyone run them.

PROSE ALREADY TRIED. docs/agent-reference/ci-gates.md says "Run it before pushing to catch issues early" and CLAUDE.md points at it. Five rounds happened anyway. wl_git.py's own header states the principle this guard follows: prose is not a safety mechanism, and the recorded incidents show it failing.

WHY A RECEIPT AND NOT A RUN. This hook sits in the PreToolUse chain, which fires on EVERY Bash call, so it must cost microseconds -- one `git rev-parse` and one file read. The expensive half (the whole quick lane) happens in an ordinary Bash call the session makes itself, where the runner's untruncated failure block is readable. Splitting them is the only shape that is both enforceable and cheap.

KEYED ON `HEAD^{tree}`. CI checks out the pushed commit, so the tree object is
exactly what CI will judge. It is also invariant to the dozens of dirty paths this repo's tree normally carries from OTHER live sessions -- keying on the worktree would invalidate the receipt on someone else's keystroke and make it unobtainable, which is how a guard becomes a wall and then gets bypassed.

A TOUCHED SLOW GATE THE LANE DROPPED IS REFUSED until it has passed (agent/plans/PLAN-gate-drop-receipt-verify.md). On 2026-10-03 ci:quick dropped `check:ci-plan-record`, a gate the diff touched, because it wrote the tree; the drop was printed and then lost, this guard allowed the push, and CI run 37129843955 went red on exactly that gate. The runner now records each such gate in the receipt's `droppedTouched`, and a `run.ts --only <id>` run of it merges its result into `droppedVerified`. Every `droppedTouched` id needs a `droppedVerified` entry at the pushed tree with exit code 0, and a receipt with no `droppedTouched` list at all refuses, failing closed exactly as a missing `whole` does.

A RECORD-ONLY COMMIT ADVANCES THE RECEIPT INSTEAD OF VOIDING IT (agent/plans/PLAN-prepush-full-cpu.md part 5). `worklist.py --review-commit` commits agent/reviews/<branch>/ after every reviewed commit, and on 2026-10-05 nine receipts died that way with no code changed. A receipt for tree T now admits a pushed tree reachable from T through the receipt's `advances`: each step's
diff is recomputed here with `git diff --no-renames`, never read from the step's own `paths`, must lie inside the record globs of .ci/policy/record-paths.json as committed in the pushed tree, and every reader gate of the touched globs must appear in the step's `gates` at exit 0, or red and listed in `failed` so the carry rule judges it. A path outside the set still voids the
receipt. The extra git calls run only on the branch that refused before, so the common push stays one `rev-parse` and one file read.

A LIVE BRANCH BEHIND origin/main IS REFUSED TOO (operator finding 2026-10-03). PR #592's first CI run went red only on Quality / Branch because main had moved three commits after 1003-1 was cut, and the push clone's origin/main was stale. Once the receipt allows, `behind_base_refusal` fetches origin/main itself (a stale ref would pass the ancestry test vacuously) and refuses an MMDD-N push to origin that does not contain it, printing the REBASE LOCALLY recipe CI prints. A fetch that fails or times out cannot judge, says so and allows.

=============================================================================
PORT NOTES
=============================================================================

`command -v jq` IS KEPT, AND IT NOW GUARDS NOTHING THIS FILE DOES. The bash reads the receipt with six `jq -r` calls, so it fails open when jq is missing: "FAIL OPEN ON A BROKEN ENVIRONMENT, never on a broken verdict". This port reads the receipt with `json.loads` and needs no jq at all, so the probe is now a pure environment test with no consumer. It is reproduced anyway, because the port is judged by AGREEMENT with its twin and a machine without jq is a case the differential can be handed. Deleting it is a BEHAVIOUR CHANGE and therefore P6's call, made when the last bash guard goes and the chain head's jq check retires with it. Recorded here so that decision is a decision rather than an omission.

THE `jq` FILTERS, spelled out because their defaults are load-bearing: `.headTree // ""`, `.whole // false`, `.exitCode // 1`, `(.failed // []) | join(", ")`, `.dirtyDigest // ""`, `(.blocked // []) | join(", ")`. `//` is falsy-tested, not null-tested, so a `whole` of `false` and a `whole` that is absent produce the same string, which is what makes the narrowed-run refusal fail CLOSED on a receipt shape the runner has not written yet.

WHAT THIS GUARD USED TO INHERIT FROM `shellscan.target_root`: the TAB-after-`-C` defect, reproduced deliberately until Rule T (PLAN-retire-bash-oracles A4) fixed it at its source. See `block_untagged_commit`'s port notes.
"""

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

from rediacc_hooks import commit_policy, hookio, shellscan, syspath

CHAIN = "pre-bash"
# Re-keyed from 39 to 40 on 2026-09-22 to make room for block_push_to_protected_branch.py at 39: "this branch may not be pushed to at all" is checked before "is this tree gate-verified".
ORDER = 39

# The confinement check is what keeps an advance from being a second way past the tree comparison: without it a step claiming "records only" over a code commit authorises that commit, which is a receipt for a tree no gate judged. The tree comparison itself is pinned by the frozen golden's push-wrong-tree rows.
DEFECT = ("confined = not outside", "confined = True")

PUSH_AT_COMMAND_POS = hookio.rx(
    r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+push([{S}]|$)"
)


REFUSAL_TAIL = """
The pre-push lane exists because three of the five CI reds on PR #579 were
sub-2-second gates that cost ~45 minutes of CI between them. Run it, fix what
it names, then push:

  npm run ci:quick

It is a PARTIAL run and says so: slower gates the change did not touch are
deferred to CI, and it names any it had to defer because a prerequisite was
slow. Every slow gate the change touches runs in the same pass; one it DROPS
(a tree writer outside a disposable clone) is named with the `run.ts --only
<id>` command that clears it, and the push waits for that run. After a commit
confined to .ci/policy/record-paths.json it re-runs only those records'
readers. `npm run ci` is still the whole set.

If a gate it names is not yours -- another session's uncommitted file often
reddens this shared tree -- do not work around it and do not fix their file.
Ask the operator, or leave a [?] worklist item naming the conflict, and
keep working meanwhile:

  .claude/hooks/stop/worklist.py --list --open        # who else is live here

If a gate cannot RUN here (a toolchain this machine lacks), that is not a red
you can fix by pushing: the gate's own message names the install line.
"""


def _env():
    return dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )


# The gate set every fixture tree carries as scripts/ci-runner/gates.lock.json: one required gate, one slow one, one ciOnly one. Receipts built by _v2_body judge exactly these.
FIXTURE_LOCK = [
    {"id": "check:fixture-ok", "run": "npm run check:fixture-ok", "gate": True, "leaves": []},
    {
        "id": "check:fixture-slow",
        "run": "npm run check:fixture-slow",
        "gate": True,
        "slow": True,
        "leaves": [],
    },
    {
        "id": "check:fixture-cionly",
        "run": "npm run check:fixture-cionly",
        "gate": True,
        "slow": True,
        "ciOnly": "fixture: CI runs it in its own step",
        "leaves": [],
    },
]


def _gate_entry(verdict, **over):
    entry = {
        "inputHash": None,
        "defHash": None,
        "filesHash": None,
        "inputs": None,
        "verdict": verdict,
        "exitCode": 1 if verdict == "fail" else 0,
        "findings": None,
        "judgedTree": None,
        "carriedFrom": None,
    }
    entry.update(over)
    return entry


def _v2_body(receipt):
    """`receipt` as a v2 receipt: schema 2 and a `gates` map consistent with its `failed` and `blocked` lists, unless the fixture already says otherwise."""
    body = dict(receipt)
    body.setdefault("schema", 2)
    body.setdefault("failed", [])
    if "gates" not in body:
        gates = {
            "check:fixture-ok": _gate_entry("ok"),
            "check:fixture-cionly": _gate_entry("ciOnly"),
        }
        for gid in body.get("failed") or []:
            gates[gid] = _gate_entry("fail")
        for gid in body.get("blocked") or []:
            gates[gid] = _gate_entry("blocked")
        body["gates"] = gates
    return body


def _write_fixture_lock(path, lock=None):
    target = path / "scripts" / "ci-runner" / "gates.lock.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(FIXTURE_LOCK if lock is None else lock), encoding="utf-8")


def _repo_with_receipt(path, receipt, carried=None):
    """A checkout whose `.ci/cache/prepush-receipt.json` says what we want.

    The receipt's `headTree` is filled in AFTER the commit, because the whole point of the key is that it names the tree object git actually produced. A hand-written hash would make every fixture take the "judged a different tree" branch and the other four would be unreachable.
    """
    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", "-q"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=_env(),
    )
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _write_fixture_lock(path)
    # carried-reds.json is COMMITTED, because the guard reads it from HEAD. Committed and on disk are then the same bytes, so the bash oracle (which reads the worktree) and this port still see one file and the differential compares like with like.
    if carried is not None:
        config = path / ".ci" / "config"
        config.mkdir(parents=True, exist_ok=True)
        (config / "carried-reds.json").write_text(json.dumps(carried), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True, env=_env())
    subprocess.run(
        ["git", "commit", "-q", "-m", "seed"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=_env(),
    )
    if receipt is not None:
        tree = (
            subprocess.run(
                ["git", "rev-parse", "HEAD^{tree}"],
                cwd=str(path),
                check=True,
                capture_output=True,
                env=_env(),
            )
            .stdout.decode()
            .strip()
        )
        body = _v2_body(receipt)
        body.setdefault("headTree", tree)
        # A `droppedVerified` entry names the tree its `--only` run judged, which is only known after the commit, like `headTree` above.
        verified = body.get("droppedVerified")
        if isinstance(verified, dict):
            body["droppedVerified"] = {
                k: dict(v, headTree=tree) if v.get("headTree") == "{TREE}" else v
                for k, v in verified.items()
            }
        cache = path / ".ci" / "cache"
        cache.mkdir(parents=True)
        (cache / "prepush-receipt.json").write_text(json.dumps(body), encoding="utf-8")
    return path


def _repo_with_forged_advance(path):
    """A receipt for the base tree, then a CODE commit behind an advance whose `paths` and `gates` claim a record-only step. The guard must recompute the diff and refuse; with DEFECT planted it admits, which is what lets test_guards_differential prove this guard's differential can fail."""
    path.mkdir(parents=True)

    def git(*args):
        return (
            subprocess.run(
                ["git", *args], cwd=str(path), check=True, capture_output=True, env=_env()
            )
            .stdout.decode()
            .strip()
        )

    git("init", "--initial-branch=main", "-q")
    policy_file = path / RECORD_POLICY_REL
    policy_file.parent.mkdir(parents=True)
    policy_file.write_text(
        json.dumps(
            {
                "version": RECORD_POLICY_VERSION,
                "records": [
                    {
                        "glob": "agent/reviews/**",
                        "except": [],
                        "readers": [{"id": "check:fixture-reader", "evidence": "fixture:1"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _write_fixture_lock(path)
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    base = git("rev-parse", "HEAD^{tree}")
    if not base:
        raise RuntimeError("the forged-advance fixture could not read its seed tree")
    (path / "seed.txt").write_text("seed, and a code change no gate judged\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "code")
    head = git("rev-parse", "HEAD^{tree}")
    cache = path / ".ci" / "cache"
    cache.mkdir(parents=True)
    (cache / "prepush-receipt.json").write_text(
        json.dumps(
            _v2_body(
                {
                    "headTree": base,
                    "whole": True,
                    "exitCode": 0,
                    "droppedTouched": [],
                    "advances": [
                        {
                            "from": base,
                            "to": head,
                            "paths": ["agent/reviews/main/clean.jsonl"],
                            "gates": {"check:fixture-reader": 0},
                            "finishedAt": "2026-10-05T00:00:00Z",
                        }
                    ],
                }
            )
        ),
        encoding="utf-8",
    )
    return path


# A CARRIED GATE, as the incremental runner records it. Commit A judges check:fx (reads src/**) and archives its receipt; commit B is the pushed tree and its receipt CARRIES check:fx from A. `variant` plants what the guard must catch.
V2_FX = "check:fx"
V2_FX_INPUTS: dict[str, list[str]] = {"globs": ["src/**"], "files": [], "scripts": ["check:fx"]}
V2_LOCK = [
    *FIXTURE_LOCK,
    {
        "id": V2_FX,
        "run": "npm run check:fx",
        "gate": True,
        "leaves": [],
        "paths": ["src/**"],
    },
]
V2_FX_SCRIPT = "echo fx"
V2_PKG = {"name": "fixture", "scripts": {"check:fx": V2_FX_SCRIPT, "check:other": "echo other"}}


def _repo_v2_carried(path, variant, origin_verdict="ok"):
    """variant: `ok` (B touches only docs/), `stale-input` (B edits src/a.txt after the carry), `red-dropped` (a carried fail missing from `failed`), `verdict-flipped` (origin said fail, the carried entry says ok), `no-origin` (no archived origin receipt)."""
    path.mkdir(parents=True)

    def git(*args):
        return (
            subprocess.run(
                ["git", *args], cwd=str(path), check=True, capture_output=True, env=_env()
            )
            .stdout.decode()
            .strip()
        )

    git("init", "--initial-branch=main", "-q")
    (path / "src").mkdir()
    (path / "src" / "a.txt").write_text("a\n", encoding="utf-8")
    (path / "docs").mkdir()
    (path / "docs" / "n.txt").write_text("n\n", encoding="utf-8")
    (path / "package.json").write_text(json.dumps(V2_PKG), encoding="utf-8")
    _write_fixture_lock(path, V2_LOCK)
    git("add", "-A")
    git("commit", "-q", "-m", "A")
    tree_a = git("rev-parse", "HEAD^{tree}")
    lines = v2_input_lines(
        v2_ls_tree(str(path), tree_a), V2_FX_INPUTS["globs"], V2_FX_INPUTS["files"]
    )
    def_hash = v2_def_hash(V2_LOCK[-1], {"check:fx": V2_FX_SCRIPT})
    files_hash = v2_files_hash(lines)
    input_hash = v2_sha("input\n%s\n%s\nfixture-salt\n" % (def_hash, files_hash))
    findings = ["fx:finding-1"] if origin_verdict == "fail" else None
    fx = _gate_entry(
        origin_verdict,
        inputHash=input_hash,
        defHash=def_hash,
        filesHash=files_hash,
        inputs=V2_FX_INPUTS,
        findings=findings,
        judgedTree=tree_a,
    )
    origin = _v2_body(
        {
            "headTree": tree_a,
            "whole": True,
            "exitCode": 1 if origin_verdict == "fail" else 0,
            "failed": [V2_FX] if origin_verdict == "fail" else [],
            "droppedTouched": [],
            "gates": {
                "check:fixture-ok": _gate_entry("ok"),
                "check:fixture-cionly": _gate_entry("ciOnly"),
                V2_FX: fx,
            },
        }
    )
    cache = path / ".ci" / "cache"
    (cache / "receipts").mkdir(parents=True)
    if variant != "no-origin":
        (cache / "receipts" / (tree_a + ".json")).write_text(json.dumps(origin), encoding="utf-8")
    target = path / ("src/a.txt" if variant == "stale-input" else "docs/n.txt")
    target.write_text("changed after A\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "B")
    tree_b = git("rev-parse", "HEAD^{tree}")
    carried = dict(fx, carriedFrom={"headTree": tree_a, "finishedAt": "2026-10-06T00:00:00Z"})
    failed = [V2_FX] if origin_verdict == "fail" else []
    if variant == "red-dropped":
        failed = []
    if variant == "verdict-flipped":
        carried["verdict"] = "ok"
    body = _v2_body(
        {
            "headTree": tree_b,
            "whole": True,
            "exitCode": 1 if failed else 0,
            "failed": failed,
            "droppedTouched": [],
            "gates": {
                "check:fixture-ok": _gate_entry("ok"),
                "check:fixture-cionly": _gate_entry("ciOnly"),
                V2_FX: carried,
            },
        }
    )
    (cache / "prepush-receipt.json").write_text(json.dumps(body), encoding="utf-8")
    return path


# The 2026-10-03 drop, as the runner records it (scripts/ci-runner/run.ts `DroppedTouched`).
DROPPED_PLAN_RECORD = {
    "id": "check:ci-plan-record",
    "why": "agent/INDEX.md matches its paths",
    "reason": "it writes the shared tree (tree:repo), which the quick lane does not do",
    "kind": "tree",
    "run": "npx tsx scripts/ci-runner/run.ts --only check:ci-plan-record",
}

# The receipt worlds this guard distinguishes. Without them the corpus sees whatever receipt this shared worktree happens to hold at the moment the test runs, which is BOTH undiscriminating and a race: another session running `ci:quick` between the bash pass and the Python pass would rewrite the file and the difference would be reported as a port defect.
FIXTURES = {
    "push-no-receipt": lambda p: _repo_with_receipt(p, None),
    # RECEIPT v2 (PLAN-fast-loop F3): a carried gate is honoured only while the hashes recomputed at the pushed tree equal the recorded ones.
    "push-v1-receipt": lambda p: _repo_with_receipt(
        p, {"schema": None, "whole": True, "exitCode": 0, "droppedTouched": []}
    ),
    "push-v2-carried-ok": lambda p: _repo_v2_carried(p, "ok"),
    "push-v2-carried-stale-input": lambda p: _repo_v2_carried(p, "stale-input"),
    "push-v2-carried-red": lambda p: _repo_v2_carried(p, "red-dropped", origin_verdict="fail"),
    "push-v2-carried-red-flipped": lambda p: _repo_v2_carried(
        p, "verdict-flipped", origin_verdict="fail"
    ),
    "push-v2-carried-red-honest": lambda p: _repo_v2_carried(p, "ok", origin_verdict="fail"),
    "push-green": lambda p: _repo_with_receipt(
        p, {"whole": True, "exitCode": 0, "droppedTouched": []}
    ),
    "push-narrowed": lambda p: _repo_with_receipt(p, {"whole": False, "exitCode": 0}),
    # PF25: a forged record-only advance over a code commit. The one world the confinement DEFECT flips.
    "push-advance-forged": _repo_with_forged_advance,
    "push-wrong-tree": lambda p: _repo_with_receipt(
        p, {"headTree": "0" * 40, "whole": True, "exitCode": 0}
    ),
    "push-red-unnamed": lambda p: _repo_with_receipt(
        p,
        {
            "whole": True,
            "exitCode": 1,
            "failed": ["check:format", "check:ci-parity"],
            "droppedTouched": [],
        },
    ),
    # A TOUCHED SLOW GATE THE LANE DROPPED, before and after its `--only` run merged a pass into the receipt.
    "push-dropped-unverified": lambda p: _repo_with_receipt(
        p, {"whole": True, "exitCode": 0, "droppedTouched": [DROPPED_PLAN_RECORD]}
    ),
    "push-dropped-verified": lambda p: _repo_with_receipt(
        p,
        {
            "whole": True,
            "exitCode": 0,
            "droppedTouched": [DROPPED_PLAN_RECORD],
            "droppedVerified": {
                "check:ci-plan-record": {
                    "exitCode": 0,
                    "headTree": "{TREE}",
                    "finishedAt": "2026-10-04T00:00:00Z",
                    "judgedRoot": "/fixture",
                    "stable": True,
                }
            },
        },
    ),
    # A whole-gate carry: `"*"` over a gate whose receipt entry is null (it emits no `::finding::` lines), with a reason past the stricter 160-character bar.
    "push-red-carried": lambda p: _repo_with_receipt(
        p,
        {
            "whole": True,
            "exitCode": 1,
            "failed": ["check:format"],
            "findings": {"check:format": None},
            "blocked": ["check:ci-go-vet"],
            "droppedTouched": [],
        },
        carried={
            "version": 2,
            "carried": [
                {
                    "gate": "check:format",
                    "findings": "*",
                    "reason": (
                        "A reason of at least one hundred and sixty characters, because a whole-gate "
                        "carry is only for a gate that emits no finding keys yet, and the bar for "
                        "carrying everything it will ever report is higher than for carrying one key."
                    ),
                }
            ],
        },
    ),
    "push-red-stale": lambda p: _repo_with_receipt(
        p,
        {"whole": True, "exitCode": 1, "failed": ["check:ci-parity"], "droppedTouched": []},
        carried={
            "version": 2,
            "carried": [
                {
                    "gate": "check:format",
                    "findings": ["fmt:packages/a.ts"],
                    "reason": (
                        "A reason of at least eighty characters, kept deliberately long so "
                        "that this entry passes the substantive-reason bar and reaches the "
                        "stale-entry arm instead of being filtered out first."
                    ),
                }
            ],
        },
    ),
    # FINDING LEVEL (PLAN-carried-red-finding-keys): the carried gate is failing and named, but it emitted a key the entry does not carry, so the push refuses naming it; the sibling world carries exactly the emitted keys and is allowed.
    "push-red-finding-new": lambda p: _repo_with_receipt(
        p,
        {
            "whole": True,
            "exitCode": 1,
            "failed": ["check:ci-plan-implementation"],
            "findings": {
                "check:ci-plan-implementation": [
                    "P-A2:no-row:agent/plans/PLAN-a.md#0a1b2c3d",
                    "P-A2:no-row:agent/plans/PLAN-b.md#4e5f6a7b",
                ]
            },
            "droppedTouched": [],
        },
        carried={
            "version": 2,
            "carried": [
                {
                    "gate": "check:ci-plan-implementation",
                    "findings": ["P-A2:no-row:agent/plans/PLAN-a.md#0a1b2c3d"],
                    "reason": (
                        "A reason of at least eighty characters, so the entry clears the "
                        "substance bar and the verdict turns on the finding keys alone."
                    ),
                }
            ],
        },
    ),
    "push-red-finding-carried": lambda p: _repo_with_receipt(
        p,
        {
            "whole": True,
            "exitCode": 1,
            "failed": ["check:ci-plan-implementation"],
            "findings": {
                "check:ci-plan-implementation": [
                    "P-A2:no-row:agent/plans/PLAN-a.md#0a1b2c3d",
                    "P-A2:no-row:agent/plans/PLAN-b.md#4e5f6a7b",
                ]
            },
            "droppedTouched": [],
        },
        carried={
            "version": 2,
            "carried": [
                {
                    "gate": "check:ci-plan-implementation",
                    "findings": [
                        "P-A2:no-row:agent/plans/PLAN-a.md#0a1b2c3d",
                        "P-A2:no-row:agent/plans/PLAN-b.md#4e5f6a7b",
                    ],
                    "reason": (
                        "A reason of at least eighty characters, so the entry clears the "
                        "substance bar and the verdict turns on the finding keys alone."
                    ),
                }
            ],
        },
    ),
}

# The last variant is this checkout's SHAPE, and it closes the second half of the race the FIXTURES comment above names. Keying on `HEAD^{tree}` survives a dirty tree by design, but it does NOT survive a commit: with one interleaved between the differential's bash pass and its Python side, this guard named two different tree hashes in the same refusal, one per side. The
# world has a history and a branch and neither moves; since 2026-09-24 it is synthetic rather than a clone, so a golden frozen from it stays true. See `_synthetic_this_worktree` in test_guards_differential.py.
ENVS = [(name, {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in sorted(FIXTURES)] + [
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {})
]

EDGE_CASES = [
    ("a plain push", "git push origin 0831-1"),
    # A dry run publishes nothing and buys no CI round.
    ("a dry run", "git push --dry-run origin 0831-1"),
    # #641e2fce: one dry run does not exempt a real push beside it.
    ("a dry run beside a real push", "git push --dry-run origin x; git push origin 0831-1"),
    ("a dry run behind a global option", "git -C . push --dry-run origin 0831-1"),
    ("prose about pushing", "echo 'remember to git push once green'"),
    ("git pull is not git push", "git pull --rebase"),
    # SUBMODULE PUSHES ARE OUT OF SCOPE, deliberately.
    ("cd into a submodule", "cd private/account && git push origin 0831-1"),
    ("git -C into a submodule", "git -C private/renet push"),
    # A TAB after `-C` is a blank like any other since the Rule T fix to shellscan.target_root (A4); /tmp is not a repository, so the push is judged against this tree either way.
    ("git -C with a TAB is still a -C", "git -C\t/tmp push"),
    ("a push in another tree", "cd /tmp && git push"),
]


def _jq_join(value, sep=", "):
    """`(.x // []) | join(", ")` -- a jq join, over a list that may be absent.

    jq stringifies a non-string element rather than refusing, which is why this does not assume the list holds strings.
    """
    if not isinstance(value, list):
        return ""
    out = []
    for item in value:
        if isinstance(item, str):
            out.append(item)
        elif item is None:
            out.append("")
        elif isinstance(item, bool):
            out.append("true" if item else "false")
        else:
            out.append(json.dumps(item, separators=(",", ":")))
    return sep.join(out)


def _alt(doc, key, fallback):
    """`.key // <fallback>`: FALSY, not null. `false` and `0` take the fallback."""
    if not isinstance(doc, dict):
        return fallback
    value = doc.get(key)
    if value is None or value is False:
        return fallback
    return value


def _refuse(ev, reason):
    # AN EARLIER CLAUSE MAY MOVE HEAD OR REWRITE THE RECEIPT (R20260924.22). This guard judges `HEAD^{tree}`, the receipt and carried-reds.json at HEAD as they are before the command runs, so a `git commit` or `npm run ci:quick` earlier in the same command changes all three. 2026-09-24 19:28:10: a carry-file fix committed by an earlier clause was judged at the pre-commit HEAD, and the refusal
    # never said so.
    ev.warn_raw(
        shellscan.split_refusal(
            shellscan.earlier_mutators(
                ev.field("tool_input", "command"), "git push", {"commit", "ci"}
            ),
            "git push",
            "HEAD^{tree}, the pre-push receipt and .ci/config/carried-reds.json at HEAD",
        )
    )
    ev.warn_raw("BLOCKED: %s\n%s" % (reason, REFUSAL_TAIL))
    return hookio.DENY


CARRIED_REL = ".ci/config/carried-reds.json"


def _carried_at_head(root):
    """carried-reds.json as committed at HEAD in `root`, parsed; None when HEAD has no such file or it does not parse."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "show", "HEAD:%s" % CARRIED_REL],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def _read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Every read in the bash is `jq ... 2>/dev/null`, so an unreadable or malformed file behaves exactly like an absent key: the `//` default.
        return None


#: The substance bar for a keyed entry: the one .dead-bash-allowlist uses and gate-test:dead-bash pins with a low-effort-BLOCKER case. A bare "known issue" excuses nothing.
REASON_MIN = 80
#: The stricter bar for `"findings": "*"`, a whole-gate carry. It is only for a gate that does not speak the `::finding::` protocol yet, so it must say more.
STAR_REASON_MIN = 160
CARRIED_VERSION = 2


def parse_carried(doc):
    """carried-reds.json v2 -> (`{gate: set(keys) | "*"}`, schema_error or None).

    SCHEMA ERRORS REFUSE, they are never skipped: a v1 entry (`{gate, reason}` with no `findings`), an empty `findings`, a missing `version: 2`, or `"*"` beside keyed entries for one gate. A malformed entry skipped silently is how a carry file quietly stops carrying what its author thinks it carries.

    An entry whose reason is under its bar (REASON_MIN, or STAR_REASON_MIN for `"*"`) is well-formed but carries nothing, so its gate then refuses as unnamed. Several keyed entries for one gate union their keys.
    """
    if doc is None:
        return {}, None
    if not isinstance(doc, dict) or doc.get("version") != CARRIED_VERSION:
        return {}, 'carried-reds.json at HEAD is not `"version": %d`.' % CARRIED_VERSION
    entries = doc.get("carried")
    if not isinstance(entries, list):
        return {}, "carried-reds.json at HEAD has no `carried` list."
    carried: dict[str, set[str] | str] = {}
    shapes: dict[str, str] = {}
    for i, entry in enumerate(entries):
        gate = entry.get("gate") if isinstance(entry, dict) else None
        if not isinstance(gate, str) or not gate:
            return {}, "carried-reds.json entry %d names no gate." % i
        findings = entry.get("findings")
        if findings == "*":
            shape = "*"
        elif (
            isinstance(findings, list)
            and findings
            and all(isinstance(k, str) and k for k in findings)
        ):
            shape = "keys"
        else:
            return {}, (
                "carried-reds.json entry %d (%s) has no `findings`: v2 carries a non-empty list of"
                ' finding keys, or "*" for a gate that emits none.' % (i, gate)
            )
        if shapes.setdefault(gate, shape) != shape:
            return {}, (
                '%s is carried both by "*" and by keys; carry a gate one way or the other.' % gate
            )
        reason = entry.get("reason")
        reason = reason if isinstance(reason, str) else ""
        if len(reason) < (STAR_REASON_MIN if shape == "*" else REASON_MIN):
            continue
        if shape == "*":
            carried[gate] = "*"
            continue
        keys = carried.get(gate)
        if not isinstance(keys, set):
            keys = carried[gate] = set()
        keys.update(findings)
    return carried, None


def push_source(push_line):
    """The source of the one `<src>:<dst>` refspec in a canonical push line, or "" when it pushes HEAD, a bare ref, or several refspecs. A leading `+` is dropped; a delete (`:dst`) has no source."""
    words = push_line.split()
    try:
        after = words[words.index("push") + 1 :]
    except ValueError:
        return ""
    specs = [w for w in after if not w.startswith("-") and ":" in w and "://" not in w]
    if len(specs) != 1:
        return ""
    src = specs[0].split(":", 1)[0].lstrip("+")
    return "" if src in ("", "HEAD") or src.startswith("HEAD") else src


def pushes_only_origin_main(root, pushes):
    """True when every push in the command names an explicit source that resolves to exactly the commit `origin/main` names."""
    if not pushes:
        return False
    sources = {push_source(line) for line in pushes}
    if "" in sources:
        return False
    want = hookio.git_out(
        ["-C", root, "rev-parse", "-q", "--verify", "origin/main^{commit}"], want_rc=True
    )
    if not want:
        return False
    for src in sources:
        got = hookio.git_out(
            ["-C", root, "rev-parse", "-q", "--verify", "%s^{commit}" % src], want_rc=True
        )
        if got != want:
            return False
    return True


def pushed_tree(root, pushes):
    """The tree the push sends, which is the tree the receipt must have judged.

    HEAD's tree unless every push names one and the same explicit source: `git push origin origin/<branch>:main`, the fast-forward fallback, sends the branch's pushed tip whatever the checkout's HEAD is. Measured 2026-10-03 on #591: with an unpushed local commit on top, the receipt for the pushed tip b47559569 was refused as "a different tree" because HEAD's was compared.
    """
    sources = {push_source(line) for line in pushes} if pushes else {""}
    if len(sources) == 1 and "" not in sources:
        got = hookio.git_out(["-C", root, "rev-parse", "%s^{tree}" % sources.pop()], want_rc=True)
        if got:
            return got
    return hookio.git_out(["-C", root, "rev-parse", "HEAD^{tree}"], want_rc=True)


#: The base every live branch is judged against, and the remote it is fetched from.
BASE = "main"
BASE_REMOTE = "origin"
#: Seconds the base fetch may take before the check reports that it cannot judge.
FETCH_TIMEOUT = 20


def rebase_recipe(base, head):
    """The REBASE LOCALLY block `rediacc_ci.quality.branch.recipe(base, head)` prints, line for line.

    REPRODUCED, NOT IMPORTED: a hook cannot import the rediacc_ci package. test-block_unverified_push.py pins this text equal to that function's in a child process, so the two cannot drift apart unnoticed.
    """
    suffix = " (branch: %s)" % head if head else ""
    return [
        "",
        "==============================================",
        "REBASE LOCALLY%s" % suffix,
        "==============================================",
        "",
        "  /branch-rebase %s" % base,
        "",
        "    Rebases the console repo AND every submodule carrying a branch of the",
        "    same name, resolving the gitlink conflicts that a plain 'git rebase'",
        "    gets wrong. It rebases and verifies only; it lands nothing.",
        "",
        "  If the rebase halts on a conflict:",
        "",
        "    .claude/hooks/stop/worklist.py --git rebase-resolve",
        "        reports where it stopped and stages the paths it can decide",
        "        (gitlinks by ancestry, registry unions). All-or-nothing: if any",
        "        path needs you, nothing is written.",
        "    .claude/hooks/stop/worklist.py --git rebase-continue --execute",
        "        continues the rebase once every conflicted path is staged.",
        "",
        "  Prove no commit was lost across the rebase:",
        "",
        "    .claude/hooks/stop/worklist.py --git snapshot > /tmp/pre.snap   # BEFORE",
        "    .claude/hooks/stop/worklist.py --git verify-rebase /tmp/pre.snap origin/%s" % base,
        "",
        "==============================================",
    ]


def _push_remote(args):
    """The remote a `git push <args>` names (its first positional), "" when it names none."""
    k = 0
    while k < len(args):
        arg = args[k]
        if arg == "--":
            return args[k + 1] if k + 1 < len(args) else ""
        if arg in commit_policy._PUSH_WITH_VALUE:
            k += 2
            continue
        if not arg.startswith("-"):
            return arg
        k += 1
    return ""


def live_pushes(cmd, root):
    """`[(sha, branch)]` for every push in `cmd` that publishes an MMDD-N branch to origin.

    A push naming no refspec (`git push`, `git push origin`) and a `HEAD` destination send the checked-out branch. A source that does not resolve is skipped: git itself refuses that push, so there is no commit to judge. The remote must be spelled `origin` (or left out); a mirror or a URL is another guard's business.
    """
    current = hookio.git_out(["-C", root, "branch", "--show-current"], want_rc=True) or ""
    # Detached prints nothing here, never the literal "HEAD" `rev-parse --abbrev-ref` would; a "HEAD" from any other path is no branch either, so it judges nothing.
    if current == "HEAD":
        current = ""
    out = []
    for run in commit_policy.git_runs(cmd, "push"):
        _, _, args = commit_policy.git_split(run.argv)
        if _push_remote(args) not in ("", BASE_REMOTE):
            continue
        dests = commit_policy.push_destinations(args)
        if not dests and not any(
            a in ("--delete", "-d", "--all", "--mirror", "--tags") for a in args
        ):
            dests = [("HEAD", current)]
        for src, named in dests:
            dst = current if named == "HEAD" else named
            if not commit_policy.BRANCH_SHAPE.match(dst or ""):
                continue
            sha = hookio.git_out(
                ["-C", root, "rev-parse", "-q", "--verify", "%s^{commit}" % (src or "HEAD")],
                want_rc=True,
            )
            if sha:
                out.append((sha, dst))
    return out


def behind_base_refusal(ev, root, cmd):
    """A refusal when a pushed live branch does not contain origin/main, else None.

    WHY. PR #592's first CI run (run 37110619739) went red only on Quality / Branch, "Check whether the branch is behind its base": main had moved three commits after 1003-1 was cut, and the local ci:quick ran in a push clone whose origin/main was stale. The CI gate (.ci/rediacc_ci/quality/branch.py) fetches the base itself before judging, so this does too: a stale `refs/remotes/origin/main` would make the ancestry test pass vacuously.

    A FAILED OR TIMED-OUT FETCH CANNOT JUDGE, and says so and allows: a base check must never become a push outage, the same fail-open-on-a-broken-environment line the receipt arm draws.
    """
    if hookio.git_out(["-C", root, "remote", "get-url", BASE_REMOTE], want_rc=True) is None:
        return None
    judged = live_pushes(cmd, root)
    if not judged:
        return None
    base_ref = "%s/%s" % (BASE_REMOTE, BASE)
    try:
        fetched = subprocess.run(
            [
                "git",
                "-C",
                root,
                "fetch",
                BASE_REMOTE,
                "+refs/heads/%s:refs/remotes/%s" % (BASE, base_ref),
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=FETCH_TIMEOUT,
            check=False,
            env=dict(os.environ, GIT_TERMINAL_PROMPT="0"),
        )
        failure = (
            ""
            if fetched.returncode == 0
            else (fetched.stderr.strip() or "exit %d" % fetched.returncode)
        )
    except subprocess.TimeoutExpired:
        failure = "timed out after %ds" % FETCH_TIMEOUT
    except OSError as exc:
        failure = str(exc)
    if failure:
        ev.warn("NOTE: cannot judge whether this push is behind %s: fetching it failed" % base_ref)
        ev.warn("  (%s)." % failure.splitlines()[-1])
        ev.warn(
            "  Allowed. CI's Quality / Branch step still checks it, and a red there costs a round."
        )
        return None
    for sha, branch in judged:
        if (
            hookio.git_out(["-C", root, "merge-base", "--is-ancestor", base_ref, sha], want_rc=True)
            is not None
        ):
            continue
        behind = hookio.git_out(["-C", root, "rev-list", "--count", "%s..%s" % (sha, base_ref)])
        recent = hookio.git_out(["-C", root, "log", "--oneline", "-5", "%s..%s" % (sha, base_ref)])
        return (
            "%s (%s) is %s commit(s) behind %s, freshly fetched.\n"
            "  CI's Quality / Branch step refuses exactly this, after a ~15-minute round.\n"
            "  Recent commits on %s not in this branch:\n%s\n%s\n"
            % (
                branch,
                sha[:12],
                behind or "?",
                base_ref,
                BASE,
                "\n".join("    %s" % line for line in recent.splitlines()),
                "\n".join(rebase_recipe(BASE, branch)),
            )
        )
    return None


#: The record set: globs a commit may touch without voiding a receipt, each with the gates that read it. Read from the PUSHED tree, never the worktree, for the reason carried-reds.json is read from HEAD.
def _policy_rel(name):
    """`.ci/policy/<name>` through rediacc_ci.policy_paths, so the policy directory is written down once (check:ci-policy-inventory). A scoped, removed sys.path insert, the shape block_host_toolchain_run._ci_seams uses: a hook cannot import rediacc_ci at module level, and a permanent `.ci` entry would leak into every later guard the dispatcher runs."""
    cipath = str(hookio.repo_root() / ".ci")
    inserted = syspath.on_sys_path(cipath)
    try:
        from rediacc_ci.policy_paths import policy_rel  # noqa: PLC0415 - deliberately late
    finally:
        if inserted and cipath in sys.path:
            sys.path.remove(cipath)
    return policy_rel(name)


RECORD_POLICY_REL = _policy_rel("record-paths.json")
RECORD_POLICY_VERSION = 1
#: A tree object name, SHA-1 or SHA-256. Anything else in an advance is refused before git sees it, so an option-shaped value cannot become an argument to `git diff`.
TREE_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def record_glob_re(glob):
    """`glob` as an anchored regex over a repo-relative path: `**` spans directories, `*` and `?` do not.

    The same three rules .ci/scripts/quality/check_record_paths.py applies (`glob_re` there); .ci/rediacc_ci/tests/gates/test_gate_record_paths.py pins the two equal on one corpus, because a hook cannot import the rediacc_ci package and a gate should not import a hook.
    """
    out = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("^%s$" % "".join(out))


def record_of(path, records):
    """The record entry whose glob covers `path` and none of whose `except` globs does, else None."""
    for rec in records:
        if not record_glob_re(rec["glob"]).match(path):
            continue
        if any(record_glob_re(x).match(path) for x in rec["except"]):
            continue
        return rec
    return None


def parse_record_policy(doc):
    """record-paths.json -> ([{glob, except, readers}], schema_error or None). A malformed policy judges nothing, so it is an error, never an empty set.

    The shape the runner's `parseRecordPolicy` (scripts/ci-runner/run.ts) reads too: `{"version": 1, "records": [{"glob", "except": [globs], "readers": [{"id", "evidence"}]}]}`. Other keys (`probes`, `notReaders`) are check:ci-record-paths' own.
    """
    if not isinstance(doc, dict) or doc.get("version") != RECORD_POLICY_VERSION:
        return [], '%s is not `"version": %d`' % (RECORD_POLICY_REL, RECORD_POLICY_VERSION)
    raw = doc.get("records")
    if not isinstance(raw, list) or not raw:
        return [], "%s has no `records` list" % RECORD_POLICY_REL
    records = []
    for i, rec in enumerate(raw):
        glob = rec.get("glob") if isinstance(rec, dict) else None
        excepted = rec.get("except", []) if isinstance(rec, dict) else None
        readers = rec.get("readers") if isinstance(rec, dict) else None
        if (
            not isinstance(glob, str)
            or not glob
            or not isinstance(excepted, list)
            or not all(isinstance(x, str) and x for x in excepted)
            or not isinstance(readers, list)
            or not all(
                isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"] for r in readers
            )
        ):
            return (
                [],
                "%s record %d needs a `glob`, an `except` list and a `readers` list of {id}"
                % (
                    RECORD_POLICY_REL,
                    i,
                ),
            )
        records.append(
            {"glob": glob, "except": excepted, "readers": sorted(r["id"] for r in readers)}
        )
    return records, None


def _record_policy_at(root, tree):
    """(records, error) for the record policy as committed in `tree`."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "show", "%s:%s" % (tree, RECORD_POLICY_REL)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return [], "git could not read %s (%s)" % (RECORD_POLICY_REL, exc)
    if proc.returncode != 0:
        return [], "the pushed tree has no %s" % RECORD_POLICY_REL
    try:
        doc = json.loads(proc.stdout)
    except ValueError:
        return [], "%s in the pushed tree does not parse" % RECORD_POLICY_REL
    return parse_record_policy(doc)


def _diff_names(root, frm, to):
    """Every path that differs between two trees, renames split into delete plus add (else a code file renamed into a record directory would list only its record-side name), or None when git cannot diff them."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "diff", "--name-only", "--no-renames", "-z", frm, to],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


#: The exit code the runner records for a reader that could not run (a missing toolchain), as opposed to one that ran and failed.
COULD_NOT_RUN = 77


def step_refusal(root, step, records, judged):
    """Why one advance does not carry the receipt from its `from` to its `to`, else None.

    The step's `paths` is never read: the diff is recomputed, so a runner (or a hand) that wrote "records only" over a code commit is caught here.

    A READER THAT IS NOT GREEN AT THE STEP. An advance records exit codes only and never touches `failed`, `findings` or `blocked`, which still describe `headTree` (scripts/ci-runner/run.ts `runAdvance`). So a red reader is admitted only when it was already red at `headTree` (`judged["failed"]`) AND carried-reds.json at HEAD carries it whole (`"*"`): a keyed carry names findings this step never recorded, so it cannot vouch for them. A reader that could not run (exit 77) is admitted only when the receipt already lists it as `blocked`, the state the 2026-08-27 ruling warns on rather than refuses.
    """
    frm, to = step["from"], step["to"]
    paths = _diff_names(root, frm, to)
    if paths is None:
        return "git cannot diff %s..%s here" % (frm[:12], to[:12])
    matched = {p: record_of(p, records) for p in paths}
    outside = sorted(p for p, rec in matched.items() if rec is None)
    # THE CONFINEMENT CHECK. DEFECT plants `True` here, and the code-commit cases of test-block_unverified_push.py must then go green-for-the-wrong-reason and red the suite.
    confined = not outside
    if not confined:
        return (
            "its diff touches %d path(s) outside the record set (%s): %s%s.\n"
            "  An advance covers record-only commits; anything else needs a new gate run."
            % (
                len(outside),
                RECORD_POLICY_REL,
                ", ".join(outside[:5]),
                " and %d more" % (len(outside) - 5) if len(outside) > 5 else "",
            )
        )
    readers = sorted({r for rec in matched.values() if rec is not None for r in rec["readers"]})
    gates = step.get("gates")
    gates = gates if isinstance(gates, dict) else {}
    missing = []
    unjudged = []
    for reader in readers:
        code = gates.get(reader)
        if not isinstance(code, int) or isinstance(code, bool):
            missing.append(reader)
            continue
        passed = code == 0
        blocked_already = code == COULD_NOT_RUN and reader in judged["blocked"]
        carried_whole = reader in judged["failed"] and reader in judged["star"]
        if not (passed or blocked_already or carried_whole):
            unjudged.append("%s (exit %d)" % (reader, code))
    if missing:
        return (
            "the readers of the records it touched were not re-run at that tree: %s.\n"
            "  A record's readers are the gates whose verdict depends on it (%s)."
            % (", ".join(missing), RECORD_POLICY_REL)
        )
    if unjudged:
        return (
            "these readers did not pass at that tree: %s.\n"
            "  An advance admits a red reader only when it was already red at the receipt's tree\n"
            '  and .ci/config/carried-reds.json carries it whole ("*"), and a reader that could not\n'
            "  run only when the receipt lists it as blocked. Fix it, or re-run npm run ci:quick."
            % ", ".join(unjudged)
        )
    return None


def advance_chain(root, receipt, start, end):
    """(trees from `start` to `end` along verified advances, None) when the receipt's `advances` reach `end`; (None, refusal) when they do not; (None, None) when the receipt holds no advance at all, so the caller keeps its own unchanged refusal.

    Steps are read in order and a step counts only when its `from` is a tree an earlier verified step (or the receipt itself) reached, which admits both a chain (T0 to T1 to T2) and repeated advances from the receipt tree (T0 to T1, T0 to T2).
    """
    steps = receipt.get("advances") if isinstance(receipt, dict) else None
    if not isinstance(steps, list) or not steps:
        return None, None
    head = (
        "the gate run judged tree %s; this push sends %s, and the receipt's advances do not reach it"
        % (
            start,
            end,
        )
    )
    records, error = _record_policy_at(root, end)
    if error is not None:
        return None, "%s: %s." % (head, error)
    judged = {}
    for key in ("failed", "blocked"):
        listed = receipt.get(key)
        judged[key] = (
            {g for g in listed if isinstance(g, str)} if isinstance(listed, list) else set()
        )
    carried, _schema_error = parse_carried(_carried_at_head(root))
    judged["star"] = {g for g, keys in carried.items() if keys == "*"}
    parent: dict[str, str | None] = {start: None}
    problems = []
    for i, step in enumerate(steps):
        frm = step.get("from") if isinstance(step, dict) else None
        to = step.get("to") if isinstance(step, dict) else None
        if not (
            isinstance(frm, str)
            and isinstance(to, str)
            and TREE_RE.match(frm)
            and TREE_RE.match(to)
        ):
            problems.append("advance %d does not name two tree hashes" % i)
            continue
        if frm not in parent:
            problems.append(
                "advance %d starts at %s, which no verified step reached" % (i, frm[:12])
            )
            continue
        why = step_refusal(root, step, records, judged)
        if why is not None:
            problems.append("advance %d (%s..%s): %s" % (i, frm[:12], to[:12], why))
            continue
        parent.setdefault(to, frm)
        if to == end:
            break
    if end not in parent:
        return None, "%s:\n%s\n  Run npm run ci:quick at this HEAD." % (
            head,
            "\n".join("    %s" % p for p in problems) or "    no advance ends at the pushed tree",
        )
    trees = []
    node = end
    while node is not None:
        trees.append(node)
        node = parent[node]
    return list(reversed(trees)), None


def dropped_verdict(receipt, tree, trees=None):
    """A refusal naming every touched-but-dropped gate with no passing run at `tree`, else None. PURE, like `carried_verdict`.

    `droppedTouched` is the runner's list of slow gates the change set touched and the quick lane did not run; `droppedVerified[id]` is a `run.ts --only <id>` run merged into the same receipt. An id counts as proven only when that entry names `tree` and exit code 0. A failed re-run is also in `failed`, which `carried_verdict` judges. A receipt with no `droppedTouched` list (a runner older than the field) refuses: a guard that read absence as "nothing dropped" would fail open on exactly the receipts that cannot say.

    `trees` is the verified advance chain ending at `tree` (`advance_chain`), when the push rides one. A run at any tree on it counts: every step is confined to the record set, so a gate that reads no record judged the same inputs, and a gate that does read one was re-run at that step or the chain would not exist.
    """
    judged_at = set(trees) if trees else {tree}
    dropped = receipt.get("droppedTouched") if isinstance(receipt, dict) else None
    if not isinstance(dropped, list):
        return (
            "that receipt has no `droppedTouched` list, so it cannot say whether the lane\n"
            "  dropped a slow gate the change touched. It predates the field; re-run npm run ci:quick."
        )
    verified = receipt.get("droppedVerified")
    verified = verified if isinstance(verified, dict) else {}
    outstanding = []
    for entry in dropped:
        gate = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(gate, str) or not gate:
            outstanding.append(
                "    %s (malformed entry)" % json.dumps(entry, separators=(",", ":"))
            )
            continue
        run_ = verified.get(gate)
        code = run_.get("exitCode") if isinstance(run_, dict) else None
        ran_here = (
            isinstance(run_, dict)
            and run_.get("headTree") in judged_at
            and isinstance(code, int)
            and not isinstance(code, bool)
        )
        if ran_here and code == 0:
            continue
        # A RED RE-RUN AT THIS TREE IS A KNOWN FAILURE, NOT AN UNKNOWN ONE, once the merge has also listed it in `failed`: from there `carried_verdict` judges it like any whole-lane failure, so it refuses unless carried-reds.json carries it with a reason. Without this a gate whose host cannot run every case (check:ci-pytest's WSL-only and live-container skips, 2026-10-04) had no path to a push at all.
        if ran_here and gate in (receipt.get("failed") or []):
            continue
        reason = entry.get("reason") if isinstance(entry.get("reason"), str) else "(no reason)"
        command = (
            entry.get("run")
            if isinstance(entry.get("run"), str)
            else "npx tsx scripts/ci-runner/run.ts --only %s" % gate
        )
        outstanding.append("    %s: %s\n      %s" % (gate, reason, command))
    if not outstanding:
        return None
    return (
        "the gate run DROPPED %d slow gate(s) the change touched that have not passed here since:\n"
        "%s\n"
        "  CI runs them for real. Run each command above; a pass merges into this receipt\n"
        "  (droppedVerified) and clears it. On 2026-10-03 exactly such a drop went red in CI."
        % (len(outstanding), "\n".join(outstanding))
    )


def carried_verdict(receipt, doc):
    """(refusal or None, note parts) for a RED receipt against carried-reds.json `doc` (parsed, from HEAD; None when absent). PURE: no git, no filesystem, so the tests and the push-clone proof drive exactly the function the guard runs.

    GATE LEVEL first, as before: a failed gate nothing carries refuses (unnamed), and a carried gate that is not failing refuses (stale). Then FINDING LEVEL, from `receipt["findings"]` (`{gate: [keys] | null}`, scripts/ci-runner/findings.ts): a keyed carry needs the gate's keys, and refuses on (a) a key the gate emitted that is not carried and (b) a carried key the gate no longer emits. A `"*"` carry is refused for a gate that DOES emit keys. A receipt with no `findings` field (an older runner) reads as null for every gate, so a keyed carry fails closed.
    """
    carried, schema_error = parse_carried(doc)
    if schema_error is not None:
        return schema_error + (
            '\n  Each entry is {"gate", "findings": [keys] | "*", "reason"} under'
            ' `"version": 2`; the keys are the gate\'s `::finding::` lines, recorded in the'
            " receipt's `findings`."
        ), []

    failed = receipt.get("failed") if isinstance(receipt, dict) else None
    failed = [g for g in failed if isinstance(g, str)] if isinstance(failed, list) else []
    rf = receipt.get("findings") if isinstance(receipt, dict) else None
    rf = rf if isinstance(rf, dict) else {}

    unnamed = "".join(" %s" % g for g in failed if g not in carried)
    if unnamed:
        return (
            "the gate run went RED and these failures are neither fixed nor carried:%s.\n"
            "  To carry one deliberately, add it to .ci/config/carried-reds.json with a reason\n"
            "  that says WHY it cannot be fixed now. CI still runs it and still fails on it --\n"
            "  carrying only records the decision instead of routing around it." % unnamed
        ), []

    # STALE ENTRIES REFUSE. An excuse that outlives its failure is exactly how an allowlist rots into a permanent hole -- the npm side of this repo once carried 101 dead entries for that reason. If a carried gate is no longer failing, the entry must go before the next push.
    stale = "".join(" %s" % g for g in sorted(carried) if g not in failed)
    if stale:
        return (
            "these gates are carried in .ci/config/carried-reds.json but are NOT failing"
            " any more:%s.\n"
            "  Remove the entries. A carried red that has gone green is a standing excuse for\n"
            "  a problem that no longer exists, which is how an allowlist becomes permanent."
            % stale
        ), []

    notes = []
    for g in failed:
        emitted = rf.get(g)
        emitted = [k for k in emitted if isinstance(k, str)] if isinstance(emitted, list) else None
        if carried[g] == "*":
            if emitted is not None:
                return (
                    "%s emits findings (%d in this receipt); carry them by key, not '*'. Copy the"
                    " keys from the receipt's `findings` into its entry." % (g, len(emitted))
                ), []
            notes.append("%s (*)" % g)
            continue
        if emitted is None:
            return (
                "%s reported no parsable findings (or the receipt predates finding keys); a keyed"
                " carry cannot be verified -- re-run npm run ci:quick" % g
            ), []
        new = sorted(set(emitted) - carried[g])
        if new:
            return (
                "%s has NEW findings that .ci/config/carried-reds.json does not carry:\n%s\n"
                "  A carried gate carries the findings it names, not every finding it will ever"
                " have. Fix these, or carry them with a reason."
                % (g, "".join("    %s\n" % k for k in new).rstrip("\n"))
            ), []
        gone = sorted(carried[g] - set(emitted))
        if gone:
            return (
                "%s no longer reports these carried findings -- remove them from"
                " .ci/config/carried-reds.json:\n%s"
                % (g, "".join("    %s\n" % k for k in gone).rstrip("\n"))
            ), []
        notes.append("%s (%d findings carried)" % (g, len(carried[g])))
    return None, notes


# --- receipt v2 (PLAN-fast-loop Part 1, F3) ---------------------------------------------
# A v2 receipt records, per gate, a verdict and (for a gate the runner CARRIED instead of re-running) the hashes of what the gate reads. The functions below implement the plan's frozen "Hash contract" byte for byte; scripts/ci-runner/input-hash.ts implements the same text, and the parity test compares the two on one corpus. v2_verdict recomputes a carried gate's hashes at the PUSHED tree, so a carry the runner mis-judged, or a hand-edited receipt, is refused here rather than judged by CI.
RECEIPT_SCHEMA = 2
LOCK_REL = "scripts/ci-runner/gates.lock.json"
CARRY_EXEMPT_REL = _policy_rel("carry-exempt.json")
V2_VERDICTS = ("ok", "fail", "blocked")
V2_REGEN = "npm run ci:quick"


def v2_canon(x):
    """JSON with keys sorted at every depth, no spaces, non-ASCII kept as UTF-8."""
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def v2_sha(s):
    """Lowercase hex sha256 of the UTF-8 bytes."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def v2_def_hash(entry, scripts):
    """The gate's lock entry plus the npm script texts it runs: a changed gate re-runs."""
    return v2_sha("def\n" + v2_canon(entry) + "\n" + v2_canon(scripts))


_GLOB_RES: dict[str, re.Pattern[str]] = {}


def v2_match_glob(glob, path):
    """`**` matches any run of characters including `/`, `*` any run without `/`, every other character (`?` included) is literal."""
    rx = _GLOB_RES.get(glob)
    if rx is None:
        out = []
        i = 0
        while i < len(glob):
            if glob.startswith("**", i):
                out.append(".*")
                i += 2
            elif glob[i] == "*":
                out.append("[^/]*")
                i += 1
            else:
                out.append(re.escape(glob[i]))
                i += 1
        rx = _GLOB_RES[glob] = re.compile("".join(out), re.DOTALL)
    return rx.fullmatch(path) is not None


def v2_ls_tree(root, tree):
    """`git ls-tree -r --full-tree` of one tree as (mode, type, oid, path); a gitlink is `160000 commit <oid>`. Empty when git cannot answer."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "ls-tree", "-r", "-z", "--full-tree", tree],
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    out = []
    for rec in proc.stdout.decode("utf-8", "surrogateescape").split("\0"):
        meta, sep, path = rec.partition("\t")
        parts = meta.split(" ")
        if sep and len(parts) == 3:
            out.append((parts[0], parts[1], parts[2], path))
    return out


def v2_input_lines(entries, globs, files):
    """`<mode> <oid>\\t<path>` (no newline) for every entry a glob matches or `files` names, sorted by path bytes."""
    named = set(files)
    picked = [e for e in entries if e[3] in named or any(v2_match_glob(gl, e[3]) for gl in globs)]
    picked.sort(key=lambda e: e[3].encode("utf-8", "surrogateescape"))
    return ["%s %s\t%s" % (e[0], e[2], e[3]) for e in picked]


def _line_path(line):
    return line.partition("\t")[2].encode("utf-8", "surrogateescape")


def v2_files_hash(lines):
    return v2_sha("files\n" + "".join(line + "\n" for line in sorted(lines, key=_line_path)))


def _show_at(root, tree, rel):
    """`git show <tree>:<rel>` as text, or None when the tree has no such file."""
    try:
        proc = subprocess.run(
            ["git", "-C", root, "show", "%s:%s" % (tree, rel)], capture_output=True, check=False
        )
    except OSError:
        return None
    return proc.stdout.decode("utf-8") if proc.returncode == 0 else None


def _exempt_ids(doc):
    """Ids named by .ci/policy/carry-exempt.json, `{"schema": 1, "exempt": [{"id", "reason"}]}`. Any other shape is an error (ValueError), never an empty set."""
    items = doc.get("exempt") if isinstance(doc, dict) else None
    if (
        not isinstance(doc, dict)
        or doc.get("schema") != 1
        or not isinstance(items, list)
        or not all(isinstance(i, dict) and isinstance(i.get("id"), str) for i in items)
    ):
        raise ValueError("carry-exempt.json is not {schema: 1, exempt: [{id, reason}]}")
    return {i["id"] for i in items}


def _carried_refusal(root, tree, gid, entry, lock_entry, entries, exempt):
    """Why one carried entry is not honoured, or ''. Names the gate and the field."""
    carried = entry.get("carriedFrom")
    inputs = entry.get("inputs")
    if not isinstance(inputs, dict) or not isinstance(carried, dict):
        return "%s is carried but records no inputs/carriedFrom (field inputs)" % gid
    if gid in exempt:
        return "%s is listed in %s and may never be carried (field carriedFrom)" % (
            gid,
            CARRY_EXEMPT_REL,
        )
    names = inputs.get("scripts") or []
    pkg = _show_at(root, tree, "package.json")
    try:
        texts = json.loads(pkg).get("scripts", {}) if pkg else {}
    except (ValueError, AttributeError):
        texts = {}
    if not isinstance(names, list) or any(n not in texts for n in names):
        return "%s: a script in inputs.scripts is absent from package.json (field defHash)" % gid
    def_hash = v2_def_hash(lock_entry, {n: texts[n] for n in names})
    if def_hash != entry.get("defHash"):
        return "%s: defHash differs at the pushed tree (the gate or its scripts changed)" % gid
    lines = v2_input_lines(entries, inputs.get("globs") or [], inputs.get("files") or [])
    if v2_files_hash(lines) != entry.get("filesHash"):
        return "%s: filesHash differs at the pushed tree (an input changed after the carry)" % gid
    origin = carried.get("headTree")
    if not isinstance(origin, str) or not TREE_RE.match(origin):
        return "%s: carriedFrom.headTree is not a tree hash (field carriedFrom)" % gid
    origin_doc = _read_json("%s/.ci/cache/receipts/%s.json" % (root, origin))
    base = (origin_doc.get("gates") if isinstance(origin_doc, dict) else None) or {}
    was = base.get(gid) if isinstance(base, dict) else None
    if not isinstance(was, dict):
        return "%s: the archived origin receipt for %s is missing or lacks it (carriedFrom)" % (
            gid,
            origin,
        )
    for field in ("inputHash", "verdict", "findings"):
        if was.get(field) != entry.get(field):
            return "%s: %s differs from the archived origin receipt %s" % (gid, field, origin)
    return ""


def v2_verdict(root, tree, receipt):
    """The v2 acceptance of a receipt for the pushed `tree`: '' accepts, anything else is the refusal text."""
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        return (
            "that receipt is not schema %d (an older runner wrote it). `%s` writes a v2 receipt."
            % (RECEIPT_SCHEMA, V2_REGEN)
        )
    gates = receipt.get("gates")
    if not isinstance(gates, dict):
        return "the receipt has no per-gate `gates` map. `%s` writes it." % V2_REGEN
    text = _show_at(root, tree, LOCK_REL)
    try:
        lock = json.loads(text) if text else None
    except ValueError:
        lock = None
    if not isinstance(lock, list):
        return "%s is unreadable at the pushed tree, so no gate set can be required." % LOCK_REL
    by_id = {g["id"]: g for g in lock if isinstance(g, dict) and isinstance(g.get("id"), str)}
    for gid, g in sorted(by_id.items()):
        if g.get("gate") is not True or g.get("ciOnly"):
            continue
        entry = gates.get(gid)
        verdicts = V2_VERDICTS + (("deferred",) if g.get("slow") else ())
        if entry is None and g.get("slow"):
            continue
        if not isinstance(entry, dict) or entry.get("verdict") not in verdicts:
            return "the receipt has no judged verdict for %s. Re-run `%s`." % (gid, V2_REGEN)
    for gid, g in sorted(by_id.items()):
        entry = gates.get(gid)
        if g.get("ciOnly") and isinstance(entry, dict) and entry.get("verdict") != "ciOnly":
            return "%s is ciOnly, so its receipt verdict must be ciOnly (field verdict)." % gid
    carried = sorted(
        gid for gid, e in gates.items() if isinstance(e, dict) and e.get("carriedFrom") is not None
    )
    if carried:
        entries = v2_ls_tree(root, tree)
        exempt_text = _show_at(root, tree, CARRY_EXEMPT_REL)
        try:
            exempt = _exempt_ids(json.loads(exempt_text)) if exempt_text else set()
        except ValueError as exc:
            return "%s is unreadable at the pushed tree: %s." % (CARRY_EXEMPT_REL, exc)
        for gid in carried:
            if gid not in by_id:
                return "%s is carried but is not in %s (field defHash)" % (gid, LOCK_REL)
            why = _carried_refusal(root, tree, gid, gates[gid], by_id[gid], entries, exempt)
            if why:
                return "a carried verdict is not valid here: %s. Re-run `%s`." % (why, V2_REGEN)
    failed = receipt.get("failed")
    red = {gid for gid, e in gates.items() if isinstance(e, dict) and e.get("verdict") == "fail"}
    if not isinstance(failed, list) or red != set(failed):
        return (
            "the receipt's `failed` list (%s) is not the set of gates with verdict fail (%s)."
            % (_jq_join(failed), ", ".join(sorted(red)))
        )
    want = 1 if red else 0
    if receipt.get("exitCode") != want or isinstance(receipt.get("exitCode"), bool):
        return "the receipt's exitCode must be %d for %d failed gate(s)." % (want, len(red))
    return ""


def every_push_deletes_only(scan):
    """True when every `git ... push` segment in the command only deletes remote refs.

    A segment deletes only when it carries `--delete`/`-d`, or when every refspec after the remote is `:<ref>`. Anything else in any segment -- a plain branch, `HEAD`, `--tags`, `--all`, `--mirror` -- makes the whole command a publishing push.
    """
    pushes = [seg for seg in re.split(r"[;&|\n]+", scan) if hookio.grep_q(PUSH_AT_COMMAND_POS, seg)]
    if not pushes:
        return False
    for seg in pushes:
        words = seg.split()
        tail = words[words.index("push") + 1 :] if "push" in words else []
        if any(w in ("--all", "--mirror", "--tags") for w in tail):
            return False
        if "--delete" in tail or "-d" in tail:
            continue
        refspecs = [w for w in tail if not w.startswith("-")][1:]
        if not refspecs or not all(r.startswith(":") and len(r) > 1 for r in refspecs):
            return False
    return True


def run(ev):
    state = shellscan.hook_init(ev.payload)
    if state is None:
        return hookio.ALLOW
    cmd, scan = state

    # Command position, so prose about pushing is not a push. Same anchor as block-untagged-commit.sh; see lib/command-scan.sh for why the raw string is never matched directly.
    if not hookio.grep_q(PUSH_AT_COMMAND_POS, scan):
        return hookio.ALLOW

    # A dry run publishes nothing and buys no CI round, but only when EVERY push in the command is one (#641e2fce): the text match it replaced let `git push --dry-run x; git push origin y` skip the receipt. Judged per push on the lexer's canonical spelling, so `git -C . push --dry-run` counts too.
    pushes = [line for line in commit_policy.push_texts(cmd).split("\n") if line]
    if pushes and all("--dry-run" in line.split() for line in pushes):
        return hookio.ALLOW

    # A DELETE-ONLY PUSH publishes no tree either, so there is nothing for a gate run to have judged. Found 2026-09-24 refusing `git push origin --delete <merged-branch>` during a branch cleanup, which pointed the session at `npm run ci:quick` for a push that removes a ref and carries no commits. Judged PER PUSH SEGMENT, so `git push origin --delete x && git push origin y` is still refused on the second segment.
    if every_push_deletes_only(scan):
        return hookio.ALLOW

    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    if root == "":
        return hookio.ALLOW

    # ANOTHER REPO'S PUSH IS NOT THIS TREE'S BUSINESS, and it was being refused as though it were. Reproduced 2026-09-01: `git -C <scratch-repo> push origin main` exited 2 here, because the gate-run stamp compared below belongs to CONSOLE and the scratch tree can never match it. The message then reads as "your gates are stale" about a repo the gates were never run against. Same
    # class as block-untagged-commit.sh:52-69; the resolution now lives in lib/command-scan.sh rather than being written a third time.
    if shellscan.target_root(scan, root, verb="push") != "":
        return hookio.ALLOW

    # THE SHELL'S OWN WORKING DIRECTORY NAMES THE REPO TOO, not only `-C`/`cd` in the command. A plain `git push origin 0923-1` run with the tool's cwd already inside private/account was judged against the CONSOLE receipt and refused as "a different tree" (#e83d9ba9, 2026-09-25). A payload cwd whose top level is not this root's is another repository's push.
    cwd = ev.raw("cwd")
    if cwd not in ("", "null"):
        top = hookio.git_out(["-C", cwd, "rev-parse", "--show-toplevel"], want_rc=True)
        if top and os.path.realpath(top) != os.path.realpath(root):
            return hookio.ALLOW

    # SUBMODULE PUSHES ARE OUT OF SCOPE, deliberately. They advance no console branch and trigger no console CI; cancel-old-ci.sh draws the same line for the same reason. The pointer-bump commit that DOES advance console is covered by the ordinary path.
    if hookio.case_glob(
        cmd,
        "*-C %s/private/*" % root,
        "*cd %s/private/*" % root,
        "*git -C private/*",
        "*cd private/*",
    ):
        return hookio.ALLOW

    receipt_path = "%s/.ci/cache/prepush-receipt.json" % root
    # A PUSH OF WHAT origin/main ALREADY IS needs no local receipt: GitHub's required CI judged that exact commit before main could move to it. That is the GitLab mirror push of /pr-merge step 6b (operator ruling 2026-10-03, worklist #1cad85a1), whose shape block_push_to_protected_branch admits.
    if pushes_only_origin_main(root, pushes):
        return hookio.ALLOW
    tree = pushed_tree(root, pushes)
    if tree is None or tree == "":
        return hookio.ALLOW

    # FAIL OPEN ON A BROKEN ENVIRONMENT, never on a broken verdict. No jq, no git, no repo: allow, exactly as warn-remote-drift.sh does -- "a drift CHECK must never become a push outage". A MISSING or STALE receipt is a different thing and is refused below, because that is the condition this guard exists for.
    if not hookio.have("jq"):
        return hookio.ALLOW

    if not pathlib.Path(receipt_path).is_file():
        return _refuse(ev, "no local gate run has judged this tree.")

    receipt = _read_json(receipt_path)
    r_tree = _alt(receipt, "headTree", "")
    r_whole = _alt(receipt, "whole", False)
    r_exit = _alt(receipt, "exitCode", 1)
    r_dirty = _alt(receipt, "dirtyDigest", "")
    r_blocked = _jq_join(receipt.get("blocked") if isinstance(receipt, dict) else None)
    # `R_TREE=$(jq -r ...)` is a STRING in the bash, whatever the JSON type, so
    # a numeric or boolean field is compared as jq would have printed it.
    r_tree = r_tree if isinstance(r_tree, str) else json.dumps(r_tree, separators=(",", ":"))
    r_whole = (
        "true"
        if r_whole is True
        else (r_whole if isinstance(r_whole, str) else json.dumps(r_whole, separators=(",", ":")))
    )
    r_exit = r_exit if isinstance(r_exit, str) else json.dumps(r_exit, separators=(",", ":"))

    # A RECEIPT WITHOUT `schema: 2` IS REFUSED, with the command that writes one (clean break: there is no v1 reading path). Before the tree comparison, so an old receipt is told it is old rather than that it judged another tree.
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        return _refuse(ev, v2_verdict(root, tree, receipt))

    chain = None
    if r_tree != tree:
        # A RECORD-ONLY COMMIT ADVANCES, it does not void (module docstring). Only this branch pays for the extra git calls, and a receipt with no `advances` keeps today's refusal byte for byte, so the frozen golden's rows do not move.
        chain, why = advance_chain(root, receipt, r_tree, tree)
        if chain is None:
            return _refuse(
                ev,
                why
                or "the gate run judged a different tree (%s), not this one (%s)." % (r_tree, tree),
            )

    # A NARROWED RUN PROVES ALMOST NOTHING. `--quick --only <one-gate>` produces a receipt that is otherwise indistinguishable from all 254, so the runner records whether the lane ran WHOLE and this reads the flag rather than parsing the selection prose -- a guard that parses English fails open on a rewording.
    if r_whole != "true":
        return _refuse(
            ev, "that receipt came from a NARROWED run (--only/--skip), not the whole lane."
        )

    # THE PER-GATE VERDICTS, and every carried one recomputed at the pushed tree (v2_verdict). After `whole` so a narrowed receipt keeps its own message.
    v2 = v2_verdict(root, tree, receipt)
    if v2:
        return _refuse(ev, v2)

    # A TOUCHED SLOW GATE THE LANE DROPPED is refused until a `--only` run of it passed at this tree. After `whole`, so a narrowed receipt keeps its own message; before the base fetch, so a push refused here never pays for one.
    dropped = dropped_verdict(receipt, tree, chain)
    if dropped is not None:
        return _refuse(ev, dropped)

    # A LIVE BRANCH BEHIND origin/main IS REFUSED HERE, not by CI (operator finding 2026-10-03, PR #592). Judged once the receipt is whole and names the pushed tree, so a push the receipt already refuses never pays for a fetch, and the frozen goldens for refused pushes stay byte-identical. Run ci:quick after the rebase, not before it.
    behind = behind_base_refusal(ev, root, cmd)
    if behind is not None:
        ev.warn_raw("BLOCKED: %s" % behind)
        return hookio.DENY

    if r_exit != "0":
        # A RED RECEIPT MAY STILL AUTHORISE A PUSH, but only when every failure is named and justified in .ci/config/carried-reds.json. All-or-nothing is the shape that gets a guard routed around; naming the exception keeps the refusal informative and leaves the excuse in git where it can be reviewed.
        #
        # READ FROM THE TREE BEING PUSHED, not the worktree. The receipt is keyed on HEAD^{tree}, so the excuses that clear it must come from the same tree. Reading the worktree let another writer's uncommitted edit to this file change the verdict on a push that does not contain that edit (2026-09-24: a working copy that dropped one entry refused a push whose HEAD still carried it). An absent file at HEAD means nothing is carried.
        refusal, notes = carried_verdict(receipt, _carried_at_head(root))
        if refusal is not None:
            return _refuse(ev, refusal)
        ev.warn("NOTE: pushing with CARRIED reds, each named in .ci/config/carried-reds.json:")
        ev.warn("  %s" % ", ".join(notes))
        ev.warn("  CI runs these for real and will fail on them. Carrying is a record of a")
        ev.warn("  deliberate decision, not a way to make CI green.")
    else:
        # A GREEN RECEIPT STILL MEETS RULE 2. carried_verdict's stale check ran only on a red receipt, so a carried gate that had gone green rode every green push unremarked: on 2026-10-02 the check:ci-external-links carry (95dc0f1f9) passed the push of afe0503db after its gate went green. With nothing failing, every carried entry is stale.
        refusal, _notes = carried_verdict(receipt, _carried_at_head(root))
        if refusal is not None:
            return _refuse(ev, refusal)

    # A GATE THAT COULD NOT RUN WARNS, IT DOES NOT REFUSE (operator decision, 2026-08-27). Measured that day: twelve reds on a normal developer tree, ten of them ambient, several purely "this machine has no ruff / no workers-types". A missing toolchain is not evidence about the code, and refusing on it would make the receipt unobtainable -- an unobtainable receipt is a guard people route around, which costs more than the rounds it saves.
    #
    # Never silent, though. "A linter that cannot run is a gate that cannot fail" stays true; this makes that state loud instead of forgiving it, and CI still runs those gates for real.
    if r_blocked:
        ev.warn("NOTE: these gates could NOT RUN locally, so nothing here judged what they cover:")
        ev.warn("  %s" % r_blocked)
        ev.warn("  They are not a verdict on your code and they do not block this push --")
        ev.warn("  but CI runs them for real, so a finding in them lands there instead.")
        ev.warn("  Each names its own install line; `.ci/scripts/lib/toolchain.sh --report`")
        ev.warn("  lists what this machine is missing against the pinned versions.")

    # THE HONEST RESIDUAL, stated rather than hidden: the gates ran against the
    # WORKING TREE, not against `HEAD^{tree}`. If the dirty set has moved since,
    # something the gates read has changed. That is a warning and not a refusal -- this tree carries dozens of dirty paths from other sessions at any moment, so refusing on it would make the receipt unobtainable, and an unobtainable receipt is a guard nobody keeps.
    now_dirty = _dirty_digest(root)
    r_dirty = r_dirty if isinstance(r_dirty, str) else ""
    if now_dirty and r_dirty and now_dirty != r_dirty:
        ev.warn("NOTE: the working tree has changed since the gates ran (they judged the")
        ev.warn("  worktree, this push carries HEAD^{tree}). The receipt still matches the")
        ev.warn("  committed tree, so this is allowed -- but if you changed something a gate")
        ev.warn("  reads, re-run: npm run ci:quick")
    return hookio.ALLOW


def _dirty_digest(root):
    """`git status --porcelain=v1 -z | sha256sum | cut -c1-16`.

    `sha256sum` prints `<hex> -`, and `cut -c1-16` takes the first sixteen characters of the hex, never of the filename field. A pipeline, so a git failure yields an empty digest rather than an error, and the caller treats an empty digest as "no comparison to make".
    """
    try:
        proc = subprocess.run(
            ["git", "-C", root, "status", "--porcelain=v1", "-z"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return ""
    if proc.returncode != 0:
        # The bash pipeline still runs sha256sum over whatever git wrote, which
        # for a failure is nothing at all: sha256sum of the empty input.
        return hashlib.sha256(b"").hexdigest()[:16]
    return hashlib.sha256(proc.stdout).hexdigest()[:16]
