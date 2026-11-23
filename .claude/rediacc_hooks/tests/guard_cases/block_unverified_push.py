"""The test tables of `block_unverified_push`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import json
import os
import subprocess

from rediacc_hooks.guards.block_unverified_push import (
    RECORD_POLICY_REL,
    RECORD_POLICY_VERSION,
    v2_def_hash,
    v2_files_hash,
    v2_input_lines,
    v2_ls_tree,
    v2_sha,
)


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
    if not head:
        raise RuntimeError("the forged-advance fixture could not read its head tree")
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
    if not tree_a:
        raise RuntimeError("fixture: rev-parse HEAD^{tree} printed nothing")
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
    if not tree_b:
        raise RuntimeError("fixture: rev-parse HEAD^{tree} printed nothing")
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
ENVS: list = [
    (name, {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in sorted(FIXTURES)
] + [("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {})]


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
    # A TAB after `-C` is a blank like any other since the Rule T fix to shellscan.target_root (A4); /tmp is no repository but a real directory outside this checkout, so the push is another repository's and allowed either way (finding #5810a9f3).
    ("git -C with a TAB is still a -C", "git -C\t/tmp push"),
    ("a push in another tree", "cd /tmp && git push"),
]
