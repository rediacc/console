#!/usr/bin/env python3
"""Controls for wl_rebase (PLAN-two-track-merge-dev RB1), on real temporary repositories.

A bare repository plays the remote; clones play the main checkout and the lease (a lease is a detached tree at the live branch's tip, which a detached clone reproduces). Exit 0 when every control holds.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

import wl_rebase as RB

FAILS: list[str] = []
RAN = [0]


def control(label: str, ok: bool, detail: str = "") -> None:
    RAN[0] += 1
    if not ok:
        FAILS.append("%s %s" % (label, detail))


def sh(cwd, *args) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def commit(cwd, name: str) -> str:
    (pathlib.Path(cwd) / name).write_text(name + "\n", encoding="utf-8")
    sh(cwd, "add", name)
    sh(cwd, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", name)
    return sh(cwd, "rev-parse", "HEAD")


def world(td: pathlib.Path):
    td.mkdir(parents=True)
    remote = td / "remote.git"
    sh(td, "init", "-q", "--bare", "-b", "main", str(remote))
    main = td / "main"
    sh(td, "clone", "-q", str(remote), str(main))
    sh(main, "checkout", "-q", "-B", "main")
    base = commit(main, "base.txt")
    sh(main, "push", "-q", "origin", "main")
    lease = td / "lease"
    sh(td, "clone", "-q", str(remote), str(lease))
    sh(lease, "checkout", "-q", "--detach", base)
    return main, lease, base


def run() -> int:
    with tempfile.TemporaryDirectory() as raw:
        td = pathlib.Path(raw)

        # A lease with no commits of its own is skipped.
        main, lease, base = world(td / "a")
        got = RB.behind_base(lease, sh(lease, "rev-parse", "HEAD"), base, "main")
        control("SKIP: a lease with no commits is skipped", got.state == "skipped", repr(got))

        # A lease at the base reads clean.
        head = commit(lease, "lease-one.txt")
        got = RB.behind_base(lease, head, base, "main")
        control("CLEAN: a lease at the base reads clean", got.state == "clean", repr(got))

        # The base moves on the remote: the lease reads behind, by one commit.
        commit(main, "main-two.txt")
        sh(main, "push", "-q", "origin", "main")
        got = RB.behind_base(lease, head, base, "main")
        control(
            "BEHIND: a lease whose base moved reads behind",
            got.state == "behind" and got.behind == 1,
            repr(got),
        )

        # MUTANT: with the fetch dropped, the lease's stale origin/main reads it as current, which the BEHIND control would catch.
        main_m, lease_m, base_m = world(td / "m")
        head_m = commit(lease_m, "lease-one.txt")
        commit(main_m, "main-two.txt")
        sh(main_m, "push", "-q", "origin", "main")
        real = RB._fetch
        RB._fetch = lambda *_a: (0, "")
        try:
            stale = RB.behind_base(lease_m, head_m, base_m, "main")
        finally:
            RB._fetch = real
        control(
            "MUTANT: a dropped fetch reads a stale ref as clean, which BEHIND catches",
            stale.state == "clean",
            repr(stale),
        )
        fresh = RB.behind_base(lease_m, head_m, base_m, "main")
        control(
            "MUTANT (control): with the fetch the same lease reads behind",
            fresh.state == "behind",
            repr(fresh),
        )

        # A failed fetch allows, with one NOTE line.
        _main_f, lease_f, base_f = world(td / "f")
        head_f = commit(lease_f, "lease-one.txt")
        sh(lease_f, "remote", "set-url", "origin", str(td / "f" / "gone.git"))
        got = RB.behind_base(lease_f, head_f, base_f, "main")
        control(
            "NOTE: a failed fetch allows with a NOTE",
            got.state == "note" and got.note.startswith("NOTE:"),
            repr(got),
        )

        # A rebase-merged parent: the lease was cut on a PR branch carrying p1; main later takes a patch-equivalent copy of p1 with a new sha. The lease reads absorbed, not behind.
        main_r, lease_r, _base_r = world(td / "r")
        sh(main_r, "checkout", "-q", "-b", "pr")
        p1 = commit(main_r, "pr-one.txt")
        sh(main_r, "push", "-q", "origin", "pr")
        sh(lease_r, "fetch", "-q", "origin")
        sh(lease_r, "checkout", "-q", "--detach", p1)
        head_r = commit(lease_r, "lease-own.txt")
        sh(main_r, "checkout", "-q", "main")
        sh(main_r, "-c", "user.name=u", "-c", "user.email=u@example.invalid", "cherry-pick", p1)
        copied = sh(main_r, "rev-parse", "HEAD")
        sh(main_r, "push", "-q", "origin", "main")
        control("ABSORBED (precondition): the copy on main has a new sha", copied != p1)
        got = RB.behind_base(lease_r, head_r, p1, "main")
        control(
            "ABSORBED: a rebase-merged parent reads absorbed, not behind",
            got.state == "absorbed" and got.absorbed == 1,
            repr(got),
        )
        commit(main_r, "main-new.txt")
        sh(main_r, "push", "-q", "origin", "main")
        got = RB.behind_base(lease_r, head_r, p1, "main")
        control(
            "ABSORBED (control): a real new main commit reads behind",
            got.state == "behind" and got.behind == 1 and got.absorbed == 1,
            repr(got),
        )

        # lease_verdicts: only this owner's leases, every repo with a cut point and a head, the rest skipped.
        world_doc = {
            "leases": {
                "mine": {
                    ".": {"path": str(lease), "head": head},
                    "private/x": {"path": str(lease), "head": ""},
                },
                "theirs": {".": {"path": str(lease), "head": head}},
                "nocut": {".": {"path": str(lease), "head": head}},
            },
            "records": {
                "mine": {"owner": "d778be9d-session", "base": {".": base, "private/x": base}},
                "theirs": {"owner": "6c87d631", "base": {".": base}},
                "nocut": {"owner": "d778be9d", "base": {}},
            },
        }
        verdicts = RB.lease_verdicts(world_doc, "d778be9d", "main")
        control(
            "LEASES: only the owner's leases with a cut point and a head are judged",
            sorted(verdicts) == ["mine"] and sorted(verdicts["mine"]) == ["."],
            repr(verdicts),
        )
        control(
            "LEASES: the judged lease reads behind",
            verdicts.get("mine", {}).get(".", RB.Verdict("x")).state == "behind",
            repr(verdicts),
        )

        # REBASE (RB4): a branch of two commits replayed onto a moved base, one with a conflict resolved by hand (its patch moves) and one clean.
        main_p, _lease_p, base_p = world(td / "p")
        (main_p / "f.txt").write_text("a\n", encoding="utf-8")
        sh(main_p, "add", "f.txt")
        sh(main_p, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "f")
        base_p = sh(main_p, "rev-parse", "HEAD")
        sh(main_p, "checkout", "-q", "-b", "dev")
        (main_p / "f.txt").write_text("b\n", encoding="utf-8")
        sh(
            main_p,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-qam",
            "edit f",
        )
        c1 = sh(main_p, "rev-parse", "HEAD")
        c2 = commit(main_p, "g.txt")
        old_tip = c2
        sh(main_p, "checkout", "-q", "main")
        (main_p / "f.txt").write_text("x\n", encoding="utf-8")
        sh(
            main_p,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-qam",
            "main moves f",
        )
        moved = sh(main_p, "rev-parse", "HEAD")
        sh(main_p, "checkout", "-q", "--detach", moved)
        picked = subprocess.run(
            ["git", "-C", str(main_p), "cherry-pick", c1],
            capture_output=True,
            text=True,
            check=False,
        )
        control(
            "REBASE (precondition): the replay of c1 onto the moved base conflicts on f.txt",
            picked.returncode != 0
            and "CONFLICT" in picked.stdout + picked.stderr
            and sh(main_p, "diff", "--name-only", "--diff-filter=U") == "f.txt",
            (picked.stdout + picked.stderr)[-200:],
        )
        (main_p / "f.txt").write_text("b and x\n", encoding="utf-8")
        sh(main_p, "add", "f.txt")
        sh(
            main_p,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "core.editor=true",
            "cherry-pick",
            "--continue",
        )
        c1_new = sh(main_p, "rev-parse", "HEAD")
        sh(main_p, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "cherry-pick", c2)
        c2_new = sh(main_p, "rev-parse", "HEAD")
        proof = RB.rebase_proof(main_p, moved, old_tip, c2_new, {c2_new})
        control("REBASE: the proof reads the rebase", proof is not None, repr(proof))
        proof = proof or {}
        control(
            "REBASE: the conflict-resolved commit is flagged CHANGED (patch-id moved)",
            [(o, n) for o, n, _s in proof.get("changed", [])] == [(c1, c1_new)],
            repr(proof),
        )
        control(
            "REBASE: the clean commit is carried, nothing missing",
            proof.get("carried") == [c2] and proof.get("missing") == [],
            repr(proof),
        )
        control(
            "REBASE: an unreviewed commit is flagged and a reviewed one is not",
            proof.get("unreviewed") == [c2_new] and c1_new not in proof.get("unreviewed", []),
            repr(proof),
        )
        # A dropped commit that shares a common subject with a replayed, conflict-resolved one stays MISSING (review cac6cc8b.1).
        main_w, _lease_w, _b = world(td / "w")
        (main_w / "f.txt").write_text("a\n", encoding="utf-8")
        sh(main_w, "add", "f.txt")
        sh(main_w, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "f")
        base_w = sh(main_w, "rev-parse", "HEAD")
        sh(main_w, "checkout", "-q", "-b", "dev")
        (main_w / "f.txt").write_text("b\n", encoding="utf-8")
        sh(
            main_w,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-qam",
            "wip",
        )
        w1 = sh(main_w, "rev-parse", "HEAD")
        (main_w / "h.txt").write_text("h\n", encoding="utf-8")
        sh(main_w, "add", "h.txt")
        sh(
            main_w,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-qm",
            "wip",
        )
        w2 = sh(main_w, "rev-parse", "HEAD")
        sh(main_w, "checkout", "-q", "main")
        (main_w / "f.txt").write_text("x\n", encoding="utf-8")
        sh(
            main_w,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-qam",
            "main moves f",
        )
        moved_w = sh(main_w, "rev-parse", "HEAD")
        sh(main_w, "checkout", "-q", "--detach", moved_w)
        picked = subprocess.run(
            ["git", "-C", str(main_w), "cherry-pick", w1],
            capture_output=True,
            text=True,
            check=False,
        )
        control(
            "REBASE (precondition): the replay of w1 onto the moved base conflicts on f.txt",
            picked.returncode != 0
            and "CONFLICT" in picked.stdout + picked.stderr
            and sh(main_w, "diff", "--name-only", "--diff-filter=U") == "f.txt",
            (picked.stdout + picked.stderr)[-200:],
        )
        (main_w / "f.txt").write_text("b and x\n", encoding="utf-8")
        sh(main_w, "add", "f.txt")
        sh(
            main_w,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "core.editor=true",
            "cherry-pick",
            "--continue",
        )
        w1_new = sh(main_w, "rev-parse", "HEAD")
        wip = RB.rebase_proof(main_w, moved_w, w2, w1_new, set()) or {}
        control(
            "REBASE: a dropped 'wip' beside a replayed 'wip' is MISSING, not paired",
            [(o, n) for o, n, _s in wip.get("changed", [])] == [(w1, w1_new)]
            and wip.get("missing") == [w2],
            repr(wip),
        )
        notes, ok, detail = RB.proof_rows("console", wip)
        control(
            "REBASE: proof_rows refuses on MISSING and names the CHANGED commit",
            not ok and w2[:12] in detail and any("CHANGED" in n and w1[:12] in n for n in notes),
            repr((notes, ok, detail)),
        )
        reviewed_rows = RB.proof_rows("console", {**wip, "missing": [], "unreviewed": []})
        owed_rows = RB.proof_rows("console", {**wip, "missing": [], "unreviewed": [w1_new]})
        control(
            "REBASE: a CHANGED commit whose replayed partner is unreviewed refuses; reviewed, it passes",
            not owed_rows[1] and "not yet reviewed" in owed_rows[2] and reviewed_rows[1],
            repr((owed_rows, reviewed_rows)),
        )
        control(
            "REBASE: an unreadable range answers None, never an empty pass",
            RB.rebase_proof(main_w, "no-such-ref", w2, w1_new, set()) is None,
        )
        del base_w

        same = RB.rebase_proof(main_p, base_p, old_tip, old_tip, set())
        control(
            "REBASE (identity): with no rebase every commit is carried, none changed or missing",
            same is not None
            and same["carried"] == [c1, c2]
            and same["changed"] == []
            and same["missing"] == [],
            repr(same),
        )

        # RB2: the Stop-hook text. The merged-parent fixture (lease r) read behind once main moved past the absorbed copy.
        merged_verdicts = {"agent-r": {".": RB.behind_base(lease_r, head_r, p1, "main")}}
        text = RB.behind_block(merged_verdicts, True)
        control(
            "RB2: after the merge a behind lease's block names /branch-rebase and the RB4 proof commands",
            "/branch-rebase main" in text
            and "--git rebase-proof" in text
            and "wl_review.py --check" in text
            and "agent-r" in text,
            text[:300],
        )
        control(
            "RB2 (control): while the PR is open nothing blocks",
            RB.behind_block(merged_verdicts, False) == "",
        )
        control(
            "RB2 (control): an absorbed-only lease needs no rebase",
            RB.behind_block({"x": {".": RB.Verdict("absorbed", absorbed=2)}}, True) == "",
        )

        control(
            "BASE: the PR branch while open, main after the merge",
            RB.base_branch(True, "1120-1") == "1120-1"
            and RB.base_branch(False, "1120-1") == "main",
        )

    for line in FAILS:
        print("FAIL", line)
    if FAILS:
        print("%d of %d control(s) failed" % (len(FAILS), RAN[0]))
        return 1
    print("%d control(s) passed" % RAN[0])
    return 0


if __name__ == "__main__":
    sys.exit(run())
